"""Architecture-review Batch D-2-thin (2026-06-30) — jobs.scene_map_json round-trip.

Mirrors test_jobs_repo_story_model from Batch C — same defensive contract:

  1. Round-trip: write JSON blob, read it back unchanged.
  2. None on missing job.
  3. None on a job that never had a SceneMap written.
  4. Setting to None clears the column.
  5. Write failures never raise (Sacred Contract #3 spirit).
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "scene_map.db"
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
    from app.db.jobs_repo import update_scene_map, get_scene_map
    _seed_job(_isolated_db, "j1")
    payload = '{"schema_version": 1, "shots": [{"start": 0.0, "end": 5.0}]}'
    update_scene_map("j1", payload)
    assert get_scene_map("j1") == payload


def test_get_returns_none_on_missing_job(_isolated_db):
    from app.db.jobs_repo import get_scene_map
    assert get_scene_map("nope") is None


def test_get_returns_none_when_never_written(_isolated_db):
    from app.db.jobs_repo import get_scene_map
    _seed_job(_isolated_db, "fresh-job")
    assert get_scene_map("fresh-job") is None


def test_update_to_none_clears_column(_isolated_db):
    from app.db.jobs_repo import update_scene_map, get_scene_map
    _seed_job(_isolated_db, "clearme")
    update_scene_map("clearme", '{"shots": []}')
    assert get_scene_map("clearme") is not None
    update_scene_map("clearme", None)
    assert get_scene_map("clearme") is None


def test_write_never_raises_on_unknown_job(_isolated_db):
    """Sacred Contract #3 spirit — log and return instead of raising."""
    from app.db.jobs_repo import update_scene_map
    update_scene_map("ghost-job", '{"shots": []}')


def test_unicode_payload_round_trip(_isolated_db):
    from app.db.jobs_repo import update_scene_map, get_scene_map
    _seed_job(_isolated_db, "vi-job")
    payload = '{"shots": [{"start": 0.0, "end": 5.0, "label": "Cảnh mở đầu"}]}'
    update_scene_map("vi-job", payload)
    assert get_scene_map("vi-job") == payload
