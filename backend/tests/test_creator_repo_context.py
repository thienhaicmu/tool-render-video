"""
Sprint 3.1 — pin the creator_repo.get_creator_context /
upsert_creator_context contract:

- nested storage under the existing prefs_json blob (no schema migration)
- round-trip preserves the exact CreatorContext shape
- None semantics: missing nested key → None; explicit None upsert clears
- helpers never raise on DB error (Sacred Contract #3 spirit)
- other top-level prefs keys are preserved when upserting the nested
  creator_context payload
"""
import sqlite3
import threading
from unittest import mock

import pytest

from app.db.connection import init_db
from app.db.creator_repo import (
    get_creator_context,
    get_creator_prefs,
    upsert_creator_context,
    upsert_creator_prefs,
)
from app.domain.creator_context import CreatorContext


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Re-use the same isolation pattern as
    test_jobs_repo_render_plan.py: redirect connection.py at a fresh
    tmp SQLite file, reset thread-local cache, run init_db()."""
    import app.db.connection as conn
    test_db = tmp_path / "test_app.db"
    monkeypatch.setattr(conn, "DATABASE_PATH", test_db)
    monkeypatch.setattr(conn, "_ACTIVE_DB_PATH", None)
    monkeypatch.setattr(conn, "_tls", threading.local())
    init_db()
    yield test_db


class TestRoundTrip:
    def test_write_then_read_preserves_context(self, isolated_db):
        ctx = CreatorContext(
            creator_id="creator-vn-1",
            channel_name="K1 Cooking",
            brand_voice="authentic",
            target_audience="vn",
            content_pillars=["recipe", "tutorial"],
            language="vi",
            notes="brief",
        )
        returned = upsert_creator_context(ctx)
        assert returned == ctx
        assert get_creator_context() == ctx

    def test_overwrite_in_place(self, isolated_db):
        upsert_creator_context(CreatorContext(channel_name="v1"))
        upsert_creator_context(CreatorContext(channel_name="v2"))
        out = get_creator_context()
        assert out is not None
        assert out.channel_name == "v2"

    def test_unicode_preserved(self, isolated_db):
        ctx = CreatorContext(channel_name="Bếp Việt", notes="Hấp dẫn")
        upsert_creator_context(ctx)
        assert get_creator_context() == ctx


class TestNoneSemantics:
    def test_fresh_db_returns_none(self, isolated_db):
        assert get_creator_context() is None

    def test_legacy_prefs_without_context_returns_none(self, isolated_db):
        """Backward compat: pre-Sprint-3 prefs blobs (without the
        `creator_context` key) deserialise to None and the AI layer
        behaves identically to before Sprint 3."""
        upsert_creator_prefs({"some_other_pref": True, "ui_theme": "dark"})
        assert get_creator_context() is None
        # Other top-level keys untouched.
        prefs = get_creator_prefs()
        assert prefs.get("ui_theme") == "dark"

    def test_explicit_none_clears_field(self, isolated_db):
        upsert_creator_context(CreatorContext(channel_name="k1"))
        assert get_creator_context() is not None
        upsert_creator_context(None)
        assert get_creator_context() is None

    def test_other_prefs_keys_preserved_on_upsert(self, isolated_db):
        """The nested upsert must not nuke other top-level prefs.
        Multi-pref coexistence pin."""
        upsert_creator_prefs({"ui_theme": "dark", "another": 42})
        upsert_creator_context(CreatorContext(channel_name="k1"))
        prefs = get_creator_prefs()
        assert prefs.get("ui_theme") == "dark"
        assert prefs.get("another") == 42
        # And the context is readable.
        out = get_creator_context()
        assert out is not None
        assert out.channel_name == "k1"

    def test_other_prefs_keys_preserved_on_clear(self, isolated_db):
        upsert_creator_prefs({"ui_theme": "dark"})
        upsert_creator_context(CreatorContext(channel_name="k1"))
        upsert_creator_context(None)
        prefs = get_creator_prefs()
        assert prefs.get("ui_theme") == "dark"
        assert "creator_context" not in prefs


class TestNeverRaises:
    def test_get_swallows_db_error(self, isolated_db):
        with mock.patch("app.db.creator_repo.get_creator_prefs", side_effect=sqlite3.OperationalError("boom")):
            assert get_creator_context() is None

    def test_upsert_swallows_read_error(self, isolated_db):
        """Even when the read of current prefs fails, the upsert should
        still attempt to write the new context (treating current as
        empty) — and crucially, must not raise."""
        with mock.patch("app.db.creator_repo.get_creator_prefs", side_effect=sqlite3.OperationalError("boom")):
            # Must not raise.
            upsert_creator_context(CreatorContext(channel_name="k1"))

    def test_upsert_swallows_write_error(self, isolated_db):
        with mock.patch("app.db.creator_repo.upsert_creator_prefs", side_effect=sqlite3.OperationalError("boom")):
            assert upsert_creator_context(CreatorContext(channel_name="k1")) is None
