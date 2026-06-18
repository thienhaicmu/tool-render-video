"""Tests for app.db.history_repo.clear_history (the clear-history / reset
feature, 2026-06-18).

Contracts:
1. Terminal jobs + their parts + download_jobs are deleted.
2. preserve_active=True keeps running/queued render jobs and
   queued/downloading downloads (Sacred Contract #7 — never orphan a live
   job); preserve_active=False wipes everything.
3. Settings (creator_prefs) and presets (render_presets) are NEVER touched.
4. Never raises.
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "clearhist.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    yield db_path


def _job(db_path, job_id, status, parts=0):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO jobs (job_id, kind, channel_code, status, stage, "
            "progress_percent, message, payload_json, result_json) "
            "VALUES (?, 'render', 'test', ?, 'done', 100, '', '{}', '{}')",
            (job_id, status),
        )
        for n in range(parts):
            conn.execute(
                "INSERT INTO job_parts (job_id, part_no, part_name, status) "
                "VALUES (?, ?, ?, 'done')",
                (job_id, n, f"part_{n}"),
            )
        conn.commit()
    finally:
        conn.close()


def _download(db_path, dl_id, status):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO download_jobs (id, url, platform, status) "
            "VALUES (?, 'http://x', 'youtube', ?)",
            (dl_id, status),
        )
        conn.commit()
    finally:
        conn.close()


def _count(db_path, table):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_clear_history_wipes_all_when_not_preserving(_isolated_db):
    from app.db.history_repo import clear_history
    _job(_isolated_db, "j1", "done", parts=3)
    _job(_isolated_db, "j2", "running", parts=2)
    _download(_isolated_db, "d1", "done")
    _download(_isolated_db, "d2", "downloading")

    deleted = clear_history(preserve_active=False)

    assert _count(_isolated_db, "jobs") == 0
    assert _count(_isolated_db, "job_parts") == 0
    assert _count(_isolated_db, "download_jobs") == 0
    assert deleted["jobs"] == 2 and deleted["job_parts"] == 5


def test_clear_history_preserves_active(_isolated_db):
    from app.db.history_repo import clear_history
    _job(_isolated_db, "done1", "done", parts=2)
    _job(_isolated_db, "run1", "running", parts=2)
    _job(_isolated_db, "queued1", "queued", parts=1)
    _download(_isolated_db, "ddone", "done")
    _download(_isolated_db, "dlive", "downloading")

    clear_history(preserve_active=True)

    # Active render job + its parts survive; terminal one is gone.
    assert _count(_isolated_db, "jobs") == 2          # run1 + queued1
    assert _count(_isolated_db, "job_parts") == 3     # 2 (run1) + 1 (queued1)
    assert _count(_isolated_db, "download_jobs") == 1  # only the live download


def test_clear_history_preserves_settings_and_presets(_isolated_db):
    from app.db.history_repo import clear_history
    conn = sqlite3.connect(str(_isolated_db))
    try:
        conn.execute("INSERT INTO creator_prefs (id, prefs_json) VALUES (1, '{}')")
        conn.execute(
            "INSERT INTO render_presets (preset_id, name, params_json) "
            "VALUES ('p1', 'Preset', '{}')"
        )
        conn.commit()
    finally:
        conn.close()
    _job(_isolated_db, "j1", "done", parts=1)

    clear_history(preserve_active=False)

    assert _count(_isolated_db, "creator_prefs") == 1
    assert _count(_isolated_db, "render_presets") == 1
    assert _count(_isolated_db, "jobs") == 0


def test_clear_history_never_raises_on_bad_db(monkeypatch):
    from app.db import history_repo

    class _Boom:
        def __enter__(self): raise RuntimeError("db down")
        def __exit__(self, *a): return False

    # clear_history imports db_conn from app.db.connection at call time.
    monkeypatch.setattr("app.db.connection.db_conn", lambda: _Boom())
    assert history_repo.clear_history() == {}
