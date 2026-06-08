"""Audit FINDING-BR13 closure (Batch 10B 2026-06-06).

The retry semantic is "fresh plan per retry": ``retry_failed_parts``
re-enqueues the pipeline with ``resume_from_last=True``; the pipeline
then runs LLM Call 1 + Call 2 again and calls
``update_render_plan(job_id, new_plan)``, which OVERWRITES whatever blob
was previously stored.

This file pins the persistence layer's overwrite behaviour so a future
refactor (e.g., adding an "INSERT OR IGNORE"-style guard, or partial
JSON merge) can't silently break the retry path. The retry handler in
``lifecycle.py`` is documented in its docstring; the contract that
matters for correctness lives here in the repo layer.

Tests:

1. ``update_render_plan`` overwrites a prior blob.
2. ``update_render_plan(None)`` clears the blob (NULL column).
3. ``update_render_plan`` on a missing job_id is a silent no-op
   (defensive contract — never crashes the pipeline).
4. ``get_render_plan`` round-trips and returns ``None`` for missing job.
5. Subsequent overwrites win — last write wins (the retry-loop case).
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    """Fresh DB at a tmp path with the full schema applied."""
    db_path = tmp_path / "render_plan.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    yield db_path


def _insert_bare_job(db_path, job_id: str, initial_plan: str | None = None) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO jobs (job_id, kind, channel_code, status, stage,
                              progress_percent, message, payload_json, result_json,
                              render_plan_json,
                              created_at, updated_at)
            VALUES (?, 'render', 'test', 'completed', 'done', 100, '', '{}', '{}',
                    ?, datetime('now'), datetime('now'))
            """,
            (job_id, initial_plan),
        )
        conn.commit()
    finally:
        conn.close()


def _read_plan(db_path, job_id: str):
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT render_plan_json FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row[0] if row else "<missing-row>"
    finally:
        conn.close()


def test_update_render_plan_overwrites_existing_blob(_isolated_db):
    """The retry semantic: a stored stale plan is replaced by the new one."""
    from app.db.jobs_repo import update_render_plan

    _insert_bare_job(_isolated_db, "job-1", initial_plan='{"version":"stale"}')

    update_render_plan("job-1", '{"version":"fresh","clips":[]}')

    assert _read_plan(_isolated_db, "job-1") == '{"version":"fresh","clips":[]}'


def test_update_render_plan_with_none_clears_blob(_isolated_db):
    """Explicit NULL — the "AI emission failed" path leaves the column unset.
    See render_pipeline.py:626-627 ("Flag-OFF / AI-failed jobs leave the
    render_plan_json column NULL — additive-schema safe.")
    """
    from app.db.jobs_repo import update_render_plan

    _insert_bare_job(_isolated_db, "job-2", initial_plan='{"v":"prior"}')

    update_render_plan("job-2", None)

    assert _read_plan(_isolated_db, "job-2") is None


def test_update_render_plan_missing_job_is_silent_noop(_isolated_db):
    """Defensive contract: must NEVER crash the pipeline on an unknown job_id.
    AI emission persistence is called inside an outer try/except for
    safety, but the function itself should also be tolerant — belt and
    suspenders.
    """
    from app.db.jobs_repo import update_render_plan

    # No row inserted for "ghost-job".
    update_render_plan("ghost-job", '{"v":"x"}')  # must not raise

    # And the table is still empty.
    conn = sqlite3.connect(str(_isolated_db))
    try:
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    finally:
        conn.close()


def test_get_render_plan_round_trips(_isolated_db):
    from app.db.jobs_repo import get_render_plan, update_render_plan

    _insert_bare_job(_isolated_db, "job-3")
    payload = '{"version":"1","clips":[{"start":0,"end":1}]}'
    update_render_plan("job-3", payload)

    assert get_render_plan("job-3") == payload


def test_get_render_plan_missing_job_returns_none(_isolated_db):
    from app.db.jobs_repo import get_render_plan

    assert get_render_plan("nonexistent-job") is None


def test_get_render_plan_null_column_returns_none(_isolated_db):
    """A job exists but its plan column is NULL (AI-failed path)."""
    from app.db.jobs_repo import get_render_plan, update_render_plan

    _insert_bare_job(_isolated_db, "job-4", initial_plan='{"v":"old"}')
    update_render_plan("job-4", None)

    assert get_render_plan("job-4") is None


def test_repeated_overwrites_last_write_wins(_isolated_db):
    """Retry loop: a job retried 3 times stores the THIRD plan, not the
    first two — proves there is no accumulating or ORed merge behaviour."""
    from app.db.jobs_repo import get_render_plan, update_render_plan

    _insert_bare_job(_isolated_db, "job-5")
    update_render_plan("job-5", '{"attempt":1}')
    update_render_plan("job-5", '{"attempt":2}')
    update_render_plan("job-5", '{"attempt":3}')

    assert get_render_plan("job-5") == '{"attempt":3}'
