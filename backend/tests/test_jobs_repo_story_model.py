"""Architecture-review Batch C (2026-06-30) — jobs.story_model_json round-trip.

Pins the contract for ``update_story_model`` / ``get_story_model``:

1. Round-trip: write a JSON blob, read it back unchanged.
2. None on missing job (defensive — never raises).
3. None on a job that never had a StoryModel written.
4. Setting to None clears the column.
5. Failure of the write helper does NOT raise (Sacred Contract #3 spirit).
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "story_model.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    yield db_path


def _seed_job(db_path, job_id: str = "job-x") -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO jobs (job_id, kind, channel_code, status, stage, "
            "progress_percent, message, payload_json, result_json) "
            "VALUES (?, 'render', 'test', 'queued', 'starting', 0, '', '{}', '{}')",
            (job_id,),
        )
        conn.commit()
    finally:
        conn.close()


def test_round_trip_writes_and_reads_back(_isolated_db):
    from app.db.jobs_repo import update_story_model, get_story_model
    _seed_job(_isolated_db, "j1")
    payload = '{"schema_version": 3, "summary": "the film recap"}'
    update_story_model("j1", payload)
    assert get_story_model("j1") == payload


def test_get_returns_none_on_missing_job(_isolated_db):
    from app.db.jobs_repo import get_story_model
    assert get_story_model("nope") is None


def test_get_returns_none_when_never_written(_isolated_db):
    from app.db.jobs_repo import get_story_model
    _seed_job(_isolated_db, "fresh-job")
    assert get_story_model("fresh-job") is None


def test_update_to_none_clears_column(_isolated_db):
    from app.db.jobs_repo import update_story_model, get_story_model
    _seed_job(_isolated_db, "clearme")
    update_story_model("clearme", '{"x": 1}')
    assert get_story_model("clearme") is not None
    update_story_model("clearme", None)
    assert get_story_model("clearme") is None


def test_write_never_raises_on_unknown_job(_isolated_db):
    """Sacred Contract #3 spirit — the helper logs and returns instead of
    raising, so a failing persistence call never crashes a live render."""
    from app.db.jobs_repo import update_story_model
    # No row exists for this job_id; UPDATE matches zero rows but does NOT raise.
    update_story_model("ghost-job", '{"summary": "ignored"}')


def test_unicode_payload_round_trip(_isolated_db):
    """The column must survive non-ASCII content unchanged — recap narration
    is routinely Vietnamese."""
    from app.db.jobs_repo import update_story_model, get_story_model
    _seed_job(_isolated_db, "vi-job")
    payload = '{"summary": "Bộ phim kể về một quán cà phê"}'
    update_story_model("vi-job", payload)
    assert get_story_model("vi-job") == payload
