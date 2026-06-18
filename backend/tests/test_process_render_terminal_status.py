"""Regression test for the phantom-running-job bug (2026-06-18).

run_render_pipeline runs setup (setup_render_pipeline / prepare_output_dir)
BEFORE its own try/except. If that setup raised, the exception propagated
through process_render's `except Exception` which re-raised WITHOUT writing a
terminal DB status — leaving the job at status='running' forever. That phantom
"active" job then blocked every new render (queue dedup + the UI's active-job
reattach), so the user "couldn't render again until they killed the job".

process_render now forces the row terminal ('failed') on that path.
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "phantom.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    yield db_path


def _status(db_path, job_id):
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_process_render_marks_failed_when_pipeline_raises_in_setup(_isolated_db, monkeypatch):
    from app.features.render.routers import _common
    from app.db.jobs_repo import upsert_job
    from app.models.schemas import RenderRequest
    from app.core.stage import JobStage

    job_id = "phantom-job-1"
    # Simulate the scheduler having marked the job 'running' at dispatch.
    upsert_job(job_id, "render", "test", "running", {}, {},
               stage=JobStage.STARTING, progress_percent=0, message="")

    # Pipeline raises in its setup phase (before its own try/except).
    def _boom(*a, **kw):
        raise RuntimeError("setup_render_pipeline blew up")
    monkeypatch.setattr(_common, "run_render_pipeline", _boom)

    with pytest.raises(RuntimeError):
        _common.process_render(job_id, RenderRequest(), False)

    # The row must NOT be left 'running' — it must be terminal so it can't
    # block new renders.
    assert _status(_isolated_db, job_id) == "failed"


def test_process_render_does_not_clobber_terminal_status(_isolated_db, monkeypatch):
    """If the pipeline already wrote a terminal status and returned, the
    except path doesn't run — and even if a later raise occurred, we never
    downgrade a 'completed' row."""
    from app.features.render.routers import _common
    from app.db.jobs_repo import upsert_job
    from app.models.schemas import RenderRequest
    from app.core.stage import JobStage

    job_id = "phantom-job-2"
    upsert_job(job_id, "render", "test", "completed", {}, {},
               stage=JobStage.DONE, progress_percent=100, message="done")

    # Pipeline returns normally (the happy path) — no exception.
    monkeypatch.setattr(_common, "run_render_pipeline", lambda *a, **kw: None)
    _common.process_render(job_id, RenderRequest(), False)

    assert _status(_isolated_db, job_id) == "completed"


# ── reconcile_orphaned_render_jobs ────────────────────────────────────────────

def _insert_render(db_path, job_id, status, age_seconds):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO jobs (job_id, kind, channel_code, status, stage, "
            "progress_percent, message, payload_json, result_json, created_at, updated_at) "
            "VALUES (?, 'render', 'test', ?, 'rendering', 40, '', '{}', '{}', "
            "datetime('now', ?), datetime('now', ?))",
            (job_id, status, f"-{age_seconds} seconds", f"-{age_seconds} seconds"),
        )
        conn.commit()
    finally:
        conn.close()


def test_reconcile_marks_stale_untracked_phantom_interrupted(_isolated_db, monkeypatch):
    from app.jobs import manager
    # Phantom: running in DB, NOT tracked by the scheduler, stale.
    _insert_render(_isolated_db, "ghost", "running", age_seconds=600)
    monkeypatch.setattr(manager, "_active_job_ids", set())
    monkeypatch.setattr(manager, "_pending_job_ids", set())

    n = manager.reconcile_orphaned_render_jobs(stale_seconds=120)
    assert n == 1
    assert _status(_isolated_db, "ghost") == "interrupted"


def test_reconcile_skips_tracked_and_fresh_jobs(_isolated_db, monkeypatch):
    from app.jobs import manager
    # Tracked job (genuinely running) must NOT be reconciled.
    _insert_render(_isolated_db, "live", "running", age_seconds=600)
    # Fresh job (just submitted, not yet tracked) must NOT be reconciled.
    _insert_render(_isolated_db, "fresh", "queued", age_seconds=5)
    monkeypatch.setattr(manager, "_active_job_ids", {"live"})
    monkeypatch.setattr(manager, "_pending_job_ids", set())

    n = manager.reconcile_orphaned_render_jobs(stale_seconds=120)
    assert n == 0
    assert _status(_isolated_db, "live") == "running"
    assert _status(_isolated_db, "fresh") == "queued"
