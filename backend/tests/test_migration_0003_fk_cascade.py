"""Audit MT-6 closure (Batch 10L 2026-06-06) — FINDING-BR03.

Migration 0003 retrofits ``FOREIGN KEY (job_id) REFERENCES jobs(job_id)
ON DELETE CASCADE`` onto the ``job_parts`` and ``clip_feedback`` tables
for EXISTING databases. New databases get the FK from the
``init_db`` baseline DDL.

Tests:

1. Fresh ``init_db`` has the FK on both tables (baseline path).
2. A pre-MT-6 database (built without FKs) is correctly migrated by 0003.
3. ``ON DELETE CASCADE`` actually fires after the migration:
   - Delete a row from ``jobs`` and observe ``job_parts`` + ``clip_feedback``
     rows for that job_id vanish.
4. The migration is idempotent — re-running it on a post-migration DB
   is a no-op (no exceptions, no data changes).
5. Defensive orphan cleanup — orphan rows are deleted before the FK
   retrofit so the INSERT-with-FK doesn't trip.
6. Existing indexes are preserved across the rename
   (``idx_feedback_channel`` on ``clip_feedback``).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _connect_with_fks(db_path: Path) -> sqlite3.Connection:
    """SQLite connection with foreign_keys=ON. The Sacred Contract pragmas
    used by the app's connection helper aren't strictly needed for the
    tests, but we mirror the FK pragma so cascade behavior fires."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _has_fk_to_jobs(conn: sqlite3.Connection, table: str) -> bool:
    rows = conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    return any(str(r[2]).lower() == "jobs" for r in rows)


def _build_pre_mt6_db(db_path: Path) -> None:
    """Recreate the schema as it existed BEFORE Batch 10L — no FK
    constraints on job_parts / clip_feedback. This simulates an
    existing user's database that needs the migration."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(
            """
            CREATE TABLE jobs (
                job_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                channel_code TEXT NOT NULL,
                status TEXT NOT NULL,
                stage TEXT DEFAULT '',
                progress_percent INTEGER DEFAULT 0,
                message TEXT DEFAULT '',
                payload_json TEXT,
                result_json TEXT,
                render_plan_json TEXT,
                error_kind TEXT,
                priority INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE job_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                part_no INTEGER NOT NULL,
                part_name TEXT NOT NULL,
                status TEXT NOT NULL,
                progress_percent INTEGER DEFAULT 0,
                start_sec REAL DEFAULT 0,
                end_sec REAL DEFAULT 0,
                duration REAL DEFAULT 0,
                viral_score REAL DEFAULT 0,
                motion_score REAL DEFAULT 0,
                hook_score REAL DEFAULT 0,
                output_file TEXT DEFAULT '',
                message TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(job_id, part_no)
            );

            CREATE TABLE clip_feedback (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id       TEXT    NOT NULL,
                part_no      INTEGER NOT NULL,
                channel_code TEXT    NOT NULL DEFAULT '',
                goal         TEXT    NOT NULL DEFAULT '',
                rating       INTEGER NOT NULL CHECK(rating IN (-1, 1)),
                hook_type    TEXT    NOT NULL DEFAULT 'none',
                clip_type    TEXT    NOT NULL DEFAULT 'unknown',
                start_sec    REAL    NOT NULL DEFAULT 0.0,
                end_sec      REAL    NOT NULL DEFAULT 0.0,
                duration_sec REAL    NOT NULL DEFAULT 0.0,
                rated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(job_id, part_no)
            );

            CREATE INDEX idx_feedback_channel ON clip_feedback(channel_code, goal);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _seed_two_jobs_with_parts_and_feedback(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")  # in case schema already has FKs
        conn.execute(
            "INSERT INTO jobs (job_id, kind, channel_code, status) "
            "VALUES ('job-A', 'render', 'k1', 'completed')"
        )
        conn.execute(
            "INSERT INTO jobs (job_id, kind, channel_code, status) "
            "VALUES ('job-B', 'render', 'k1', 'completed')"
        )
        conn.execute(
            "INSERT INTO job_parts (job_id, part_no, part_name, status) "
            "VALUES ('job-A', 1, 'p_001', 'done')"
        )
        conn.execute(
            "INSERT INTO job_parts (job_id, part_no, part_name, status) "
            "VALUES ('job-A', 2, 'p_002', 'done')"
        )
        conn.execute(
            "INSERT INTO job_parts (job_id, part_no, part_name, status) "
            "VALUES ('job-B', 1, 'p_001', 'done')"
        )
        conn.execute(
            "INSERT INTO clip_feedback (job_id, part_no, rating) "
            "VALUES ('job-A', 1, 1)"
        )
        conn.execute(
            "INSERT INTO clip_feedback (job_id, part_no, rating) "
            "VALUES ('job-B', 1, -1)"
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. Baseline path: a fresh init_db has the FK
# ---------------------------------------------------------------------------


def test_init_db_baseline_creates_fk_on_both_tables(tmp_path, monkeypatch):
    """A pristine database — built via app.db.connection.init_db — must
    already carry the FK constraints. Existing DBs hit migration 0003;
    new ones never need it."""
    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()

    conn = _connect_with_fks(db_path)
    try:
        assert _has_fk_to_jobs(conn, "job_parts"), (
            "job_parts is missing FK to jobs — baseline DDL regressed"
        )
        assert _has_fk_to_jobs(conn, "clip_feedback"), (
            "clip_feedback is missing FK to jobs — baseline DDL regressed"
        )
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 2. Migration converts a pre-MT-6 database
# ---------------------------------------------------------------------------


def test_migration_0003_adds_fk_to_existing_db(tmp_path):
    """Build the pre-Batch-10L schema, seed it, then run migration 0003.
    Verify the FK lands AND row counts are preserved exactly."""
    db_path = tmp_path / "pre_mt6.db"
    _build_pre_mt6_db(db_path)
    _seed_two_jobs_with_parts_and_feedback(db_path)

    pre_jobs = _count(db_path, "jobs")
    pre_parts = _count(db_path, "job_parts")
    pre_fb = _count(db_path, "clip_feedback")
    assert (pre_jobs, pre_parts, pre_fb) == (2, 3, 2), \
        "seed seeded wrong row counts; fix the fixture before testing the migration"

    from app.db.migrations import discover_migrations
    found = {m.version: m for m in discover_migrations()}
    assert 3 in found, "discovery did not find migration 0003"

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN")
        found[3].up(conn)
        conn.commit()
    finally:
        conn.close()

    # Post: FK present on both, no rows lost.
    conn = _connect_with_fks(db_path)
    try:
        assert _has_fk_to_jobs(conn, "job_parts")
        assert _has_fk_to_jobs(conn, "clip_feedback")
    finally:
        conn.close()
    assert _count(db_path, "jobs")          == pre_jobs
    assert _count(db_path, "job_parts")     == pre_parts
    assert _count(db_path, "clip_feedback") == pre_fb


# ---------------------------------------------------------------------------
# 3. ON DELETE CASCADE actually fires after the migration
# ---------------------------------------------------------------------------


def test_cascade_delete_fires_after_migration(tmp_path):
    """The whole point of MT-6: deleting a row from ``jobs`` MUST cascade
    to ``job_parts`` AND ``clip_feedback`` automatically — no helper
    function needed."""
    db_path = tmp_path / "cascade.db"
    _build_pre_mt6_db(db_path)
    _seed_two_jobs_with_parts_and_feedback(db_path)

    from app.db.migrations import discover_migrations
    found = {m.version: m for m in discover_migrations()}
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN")
        found[3].up(conn)
        conn.commit()
    finally:
        conn.close()

    # Now delete job-A directly. With the FK + ON DELETE CASCADE active,
    # the 2 job_parts rows + 1 clip_feedback row for job-A must vanish.
    conn = _connect_with_fks(db_path)
    try:
        conn.execute("DELETE FROM jobs WHERE job_id = 'job-A'")
        conn.commit()
    finally:
        conn.close()

    # job-B's data must be untouched.
    assert _count(db_path, "jobs") == 1
    assert _count_where(db_path, "job_parts", "job_id = 'job-A'") == 0
    assert _count_where(db_path, "job_parts", "job_id = 'job-B'") == 1
    assert _count_where(db_path, "clip_feedback", "job_id = 'job-A'") == 0
    assert _count_where(db_path, "clip_feedback", "job_id = 'job-B'") == 1


# ---------------------------------------------------------------------------
# 4. Idempotency — re-running the migration is a no-op
# ---------------------------------------------------------------------------


def test_migration_is_idempotent_after_first_run(tmp_path):
    db_path = tmp_path / "idem.db"
    _build_pre_mt6_db(db_path)
    _seed_two_jobs_with_parts_and_feedback(db_path)

    from app.db.migrations import discover_migrations
    found = {m.version: m for m in discover_migrations()}

    # First run.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN")
        found[3].up(conn)
        conn.commit()
    finally:
        conn.close()

    snapshot_jobs = _count(db_path, "jobs")
    snapshot_parts = _count(db_path, "job_parts")
    snapshot_fb = _count(db_path, "clip_feedback")

    # Second run on the post-migration DB — must NOT raise and must
    # NOT change any row count (the temp-table dance is gated on
    # PRAGMA foreign_key_list returning empty).
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN")
        found[3].up(conn)
        conn.commit()
    finally:
        conn.close()

    assert _count(db_path, "jobs")          == snapshot_jobs
    assert _count(db_path, "job_parts")     == snapshot_parts
    assert _count(db_path, "clip_feedback") == snapshot_fb


# ---------------------------------------------------------------------------
# 5. Defensive orphan cleanup
# ---------------------------------------------------------------------------


def test_migration_drops_orphans_before_fk_retrofit(tmp_path):
    """If pre-existing data has orphan job_parts / clip_feedback rows
    (job_id pointing to a deleted jobs row), the migration deletes
    them defensively before the INSERT-with-FK so the copy doesn't
    fail. Sacred Contract #7: maintenance should not bypass delete_job,
    but historical DBs may have orphans."""
    db_path = tmp_path / "orphans.db"
    _build_pre_mt6_db(db_path)
    _seed_two_jobs_with_parts_and_feedback(db_path)

    # Insert an orphan job_parts row + an orphan clip_feedback row.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")  # schema has no FK yet anyway
        conn.execute(
            "INSERT INTO job_parts (job_id, part_no, part_name, status) "
            "VALUES ('GHOST', 1, 'orphan', 'failed')"
        )
        conn.execute(
            "INSERT INTO clip_feedback (job_id, part_no, rating) "
            "VALUES ('GHOST', 1, 1)"
        )
        conn.commit()
    finally:
        conn.close()
    # Confirm the orphans are present pre-migration.
    assert _count_where(db_path, "job_parts", "job_id = 'GHOST'") == 1
    assert _count_where(db_path, "clip_feedback", "job_id = 'GHOST'") == 1

    from app.db.migrations import discover_migrations
    found = {m.version: m for m in discover_migrations()}
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN")
        found[3].up(conn)
        conn.commit()
    finally:
        conn.close()

    # Orphans gone, real rows preserved.
    assert _count_where(db_path, "job_parts", "job_id = 'GHOST'") == 0
    assert _count_where(db_path, "clip_feedback", "job_id = 'GHOST'") == 0
    assert _count(db_path, "job_parts")     == 3  # 2 for job-A + 1 for job-B
    assert _count(db_path, "clip_feedback") == 2  # 1 each


# ---------------------------------------------------------------------------
# 6. Index preservation across the rename
# ---------------------------------------------------------------------------


def test_idx_feedback_channel_survives_migration(tmp_path):
    """``idx_feedback_channel`` is an explicit index (not implicit from a
    UNIQUE clause). When the migration drops the old clip_feedback table,
    the index goes with it. The migration body MUST re-create it."""
    db_path = tmp_path / "indexes.db"
    _build_pre_mt6_db(db_path)
    _seed_two_jobs_with_parts_and_feedback(db_path)

    # Pre: index present.
    assert _index_present(db_path, "idx_feedback_channel")

    from app.db.migrations import discover_migrations
    found = {m.version: m for m in discover_migrations()}
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("BEGIN")
        found[3].up(conn)
        conn.commit()
    finally:
        conn.close()

    # Post: index re-created on the new clip_feedback.
    assert _index_present(db_path, "idx_feedback_channel"), (
        "idx_feedback_channel disappeared after migration — the explicit "
        "re-create step in 0003 is missing or broken."
    )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _count(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def _count_where(db_path: Path, table: str, where: str) -> int:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]
    finally:
        conn.close()


def _index_present(db_path: Path, name: str) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
            (name,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()
