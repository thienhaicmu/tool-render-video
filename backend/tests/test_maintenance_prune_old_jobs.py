"""Audit FINDING-DB05 / MT-7 / ST-12 closure (Batch 10A 2026-06-06).

``prune_old_jobs`` is the env-gated DB row retention helper invoked from
the periodic cleanup loop in main.py. Contracts:

1. ``max_age_days <= 0`` is a no-op (the env-default ``JOB_RETENTION_DAYS=0``
   case — feature DISABLED out of the box, like every retention setting
   in this app).
2. Active jobs (``status IN ('running', 'queued')``) are NEVER deleted
   regardless of age. Sacred Contract 7: the row IS the in-flight job's
   recovery state.
3. Completed/failed/cancelled/interrupted jobs older than the cutoff ARE
   deleted, along with their job_parts rows (FK cascade is not in the
   schema — the prune issues two DELETEs in one transaction).
4. The function NEVER raises — failures degrade to a zero-count return
   plus a WARN log so the cleanup loop keeps marching on a transient DB
   error.
"""
from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    """Build a fresh SQLite file with jobs + job_parts tables, point
    connection.py at it. ``init_db()`` creates the full schema."""
    db_path = tmp_path / "retention.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    yield db_path


def _insert_job(db_path, job_id: str, status: str, age_days: int, *, parts: int = 0):
    """Insert a jobs row with ``updated_at`` shifted into the past by
    ``age_days``, plus optional job_parts rows aged identically."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO jobs (job_id, kind, channel_code, status, stage,
                              progress_percent, message, payload_json, result_json,
                              created_at, updated_at)
            VALUES (?, 'render', 'test', ?, 'done', 100, '', '{}', '{}',
                    datetime('now', ?), datetime('now', ?))
            """,
            (job_id, status, f"-{age_days} days", f"-{age_days} days"),
        )
        for n in range(parts):
            conn.execute(
                """
                INSERT INTO job_parts (job_id, part_no, part_name, status,
                                       created_at, updated_at)
                VALUES (?, ?, ?, 'done',
                        datetime('now', ?), datetime('now', ?))
                """,
                (job_id, n, f"part_{n}", f"-{age_days} days", f"-{age_days} days"),
            )
        conn.commit()
    finally:
        conn.close()


def _count(db_path, table: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_zero_max_age_is_noop(_isolated_db):
    """The env-default ``JOB_RETENTION_DAYS=0`` MUST be a no-op — the
    feature is off out of the box."""
    from app.services.maintenance import prune_old_jobs

    _insert_job(_isolated_db, "old-job", "completed", age_days=400, parts=3)

    result = prune_old_jobs(0)

    assert result == {"removed_jobs": 0, "removed_parts": 0}
    assert _count(_isolated_db, "jobs") == 1, "0-day max age must not delete"
    assert _count(_isolated_db, "job_parts") == 3


def test_negative_max_age_is_noop(_isolated_db):
    """Defensive: an int that's somehow negative is also a no-op."""
    from app.services.maintenance import prune_old_jobs

    _insert_job(_isolated_db, "old-job", "completed", age_days=400)

    result = prune_old_jobs(-7)

    assert result == {"removed_jobs": 0, "removed_parts": 0}
    assert _count(_isolated_db, "jobs") == 1


def test_active_jobs_never_pruned(_isolated_db):
    """Sacred Contract 7: ``running`` + ``queued`` rows are the in-flight
    job's state. NEVER prune them regardless of age."""
    from app.services.maintenance import prune_old_jobs

    _insert_job(_isolated_db, "running-old", "running", age_days=999, parts=2)
    _insert_job(_isolated_db, "queued-old", "queued", age_days=999, parts=1)

    result = prune_old_jobs(30)

    assert result == {"removed_jobs": 0, "removed_parts": 0}
    assert _count(_isolated_db, "jobs") == 2
    assert _count(_isolated_db, "job_parts") == 3


def test_prunes_old_terminal_jobs_and_their_parts(_isolated_db):
    """Completed/failed/cancelled/interrupted jobs older than the cutoff
    ARE deleted, along with their job_parts."""
    from app.services.maintenance import prune_old_jobs

    _insert_job(_isolated_db, "old-completed",  "completed",            age_days=100, parts=4)
    _insert_job(_isolated_db, "old-failed",     "failed",               age_days=100, parts=2)
    _insert_job(_isolated_db, "old-cancelled",  "cancelled",            age_days=100, parts=1)
    _insert_job(_isolated_db, "old-cwerr",      "completed_with_errors", age_days=100, parts=3)
    _insert_job(_isolated_db, "old-interrupt",  "interrupted",          age_days=100, parts=0)

    result = prune_old_jobs(30)

    assert result["removed_jobs"] == 5
    assert result["removed_parts"] == 10
    assert _count(_isolated_db, "jobs") == 0
    assert _count(_isolated_db, "job_parts") == 0


def test_keeps_recent_jobs_under_cutoff(_isolated_db):
    """A 7-day-old completed job must survive a 30-day prune."""
    from app.services.maintenance import prune_old_jobs

    _insert_job(_isolated_db, "fresh", "completed", age_days=7, parts=2)
    _insert_job(_isolated_db, "stale", "completed", age_days=60, parts=2)

    result = prune_old_jobs(30)

    assert result["removed_jobs"] == 1
    assert result["removed_parts"] == 2
    # Fresh row + its parts survive.
    assert _count(_isolated_db, "jobs") == 1
    assert _count(_isolated_db, "job_parts") == 2


def test_never_raises_on_db_error(monkeypatch):
    """Cleanup loop integrity: a transient DB error must NOT bubble up.
    The function returns a zero-count dict + logs a WARN."""
    from app.services import maintenance

    class _Boom:
        def __enter__(self): raise sqlite3.OperationalError("forced")
        def __exit__(self, *a): return False

    monkeypatch.setattr("app.db.connection.db_conn", lambda: _Boom())

    result = maintenance.prune_old_jobs(30)

    assert result == {"removed_jobs": 0, "removed_parts": 0}
