"""Story-to-Video P0 — story_repo CRUD tests (against the sandbox app.db).

conftest points APP_DATA_DIR at a throwaway sandbox; init_db() runs all
migration_steps (incl. 0017-0021) so the Story tables exist. Verifies:
1. series upsert/get/list/delete round-trip.
2. character/environment upsert scoped by series + list.
3. empty series_id short-circuits list helpers (one-off chapter path).
4. chapter_summary append + cross-reference ordering (before_chapter filter).

Every repo function is defensive; these tests assert the happy path + the
empty-series guards.
"""
from __future__ import annotations

import uuid

from app.db.connection import init_db
from app.db import story_repo


def _sid() -> str:
    return "test-series-" + uuid.uuid4().hex[:8]


def setup_module(module):  # noqa: D401 - pytest hook
    init_db()


def test_series_crud_round_trip():
    sid = _sid()
    try:
        assert story_repo.upsert_series(sid, title="Bộ 1", language="vi", art_style="wuxia")
        got = story_repo.get_series(sid)
        assert got is not None and got["title"] == "Bộ 1" and got["language"] == "vi"
        # update
        assert story_repo.upsert_series(sid, title="Bộ 1 (sửa)", language="vi")
        assert story_repo.get_series(sid)["title"] == "Bộ 1 (sửa)"
        assert any(s["id"] == sid for s in story_repo.list_series())
    finally:
        story_repo.delete_series(sid)
    assert story_repo.get_series(sid) is None


def test_characters_scoped_by_series():
    sid = _sid()
    try:
        story_repo.upsert_series(sid, title="X")
        cid = sid + "-char"
        assert story_repo.upsert_character(
            cid, series_id=sid, name="Hàn Phong", canonical_desc="áo trắng",
            voice_engine="gemini", voice_id="vi-A",
        )
        chars = story_repo.list_characters(sid)
        assert len(chars) == 1 and chars[0]["name"] == "Hàn Phong"
        assert story_repo.get_character(cid)["voice_engine"] == "gemini"
    finally:
        story_repo.delete_series(sid)


def test_environments_scoped_by_series():
    sid = _sid()
    try:
        story_repo.upsert_series(sid, title="X")
        assert story_repo.upsert_environment(
            sid + "-env", series_id=sid, name="Vạn Kiếm Tông", canonical_desc="trên mây",
        )
        envs = story_repo.list_environments(sid)
        assert len(envs) == 1 and envs[0]["name"] == "Vạn Kiếm Tông"
    finally:
        story_repo.delete_series(sid)


def test_empty_series_id_short_circuits():
    # One-off chapter: no series → list helpers return [] without a query.
    assert story_repo.list_characters("") == []
    assert story_repo.list_environments("") == []
    assert story_repo.list_chapter_summaries("") == []
    assert story_repo.add_chapter_summary("", 1, "x") is False


def test_chapter_summary_cross_reference_ordering():
    sid = _sid()
    try:
        story_repo.upsert_series(sid, title="X")
        assert story_repo.add_chapter_summary(sid, 1, "ch1")
        assert story_repo.add_chapter_summary(sid, 2, "ch2")
        assert story_repo.add_chapter_summary(sid, 3, "ch3")
        # All, oldest first.
        alls = story_repo.list_chapter_summaries(sid)
        assert [s["chapter_no"] for s in alls] == [1, 2, 3]
        # Only chapters before ch3 (context for planning chapter 3).
        prior = story_repo.list_chapter_summaries(sid, before_chapter=3)
        assert [s["chapter_no"] for s in prior] == [1, 2]
    finally:
        story_repo.delete_series(sid)
