"""Story project persistence (SP1) — migration 0022 + repo + endpoints."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.db.connection import init_db, db_conn
from app.db import story_project_repo as repo
from app.features.story.router import (
    StoryProjectSaveRequest,
    save_story_project,
    list_story_projects,
    get_story_project,
    delete_story_project,
)


def setup_module(module):  # noqa: D401
    init_db()


def test_migration_created_table():
    with db_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='story_projects'"
        ).fetchone()
    assert row is not None


def test_repo_crud_roundtrip():
    pid = "proj-" + uuid.uuid4().hex[:8]
    try:
        assert repo.upsert_project(pid, name="My story", language="vi", source="paste",
                                   config_json='{"genre":"wuxia"}', plan_json='{"topic":"x"}',
                                   status="ready")
        got = repo.get_project(pid)
        assert got and got["name"] == "My story" and got["status"] == "ready"
        assert got["config_json"] == '{"genre":"wuxia"}'
        # update in place (same id)
        assert repo.upsert_project(pid, name="Renamed", config_json="{}", plan_json="", status="draft")
        got2 = repo.get_project(pid)
        assert got2["name"] == "Renamed" and got2["status"] == "draft" and got2["plan_json"] == ""
        # list contains it WITHOUT the heavy blobs
        lst = repo.list_projects()
        mine = [p for p in lst if p["id"] == pid]
        assert mine and "config_json" not in mine[0] and "plan_json" not in mine[0]
    finally:
        assert repo.delete_project(pid)
        assert repo.get_project(pid) is None


def test_repo_defensive():
    assert repo.upsert_project("") is False                     # empty id rejected
    assert repo.get_project("nope-" + uuid.uuid4().hex) is None  # missing → None


def test_endpoints_save_get_list_delete():
    out = save_story_project(StoryProjectSaveRequest(
        name="E2E", language="vi", source="idea",
        config={"idea": "a hero rises", "genre": "fantasy"},
        plan={"topic": "Hero", "timeline": [{"id": "b1"}]}, status="ready"))
    pid = out["id"]
    assert pid
    try:
        full = get_story_project(pid)
        assert full["name"] == "E2E" and full["config"]["genre"] == "fantasy"
        assert full["plan"]["topic"] == "Hero"
        assert "config_json" not in full and "plan_json" not in full   # parsed to objects
        # id-preserving update
        out2 = save_story_project(StoryProjectSaveRequest(id=pid, name="E2E-2", config={}, status="draft"))
        assert out2["id"] == pid
        assert get_story_project(pid)["name"] == "E2E-2"
        assert any(p["id"] == pid for p in list_story_projects()["projects"])
    finally:
        delete_story_project(pid)
    with pytest.raises(HTTPException):
        get_story_project(pid)


def test_get_missing_project_404():
    with pytest.raises(HTTPException) as ei:
        get_story_project("does-not-exist-" + uuid.uuid4().hex)
    assert ei.value.status_code == 404
