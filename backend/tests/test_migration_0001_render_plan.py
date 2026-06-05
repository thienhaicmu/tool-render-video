"""
Sprint 2.1 — test migration 0001: jobs.render_plan_json additive column.

Pins:
- adds the column when missing
- idempotent if rerun against a DB that already has it
- additive: every legacy `jobs` row reads NULL for the new column
- doesn't touch any other table
"""
import importlib.util
import sqlite3
from pathlib import Path

import pytest


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "db"
    / "migration_steps"
    / "0001_jobs_add_render_plan_json.py"
)


def _load_migration():
    """Filename starts with a digit — cannot be imported normally. Load by
    file path each time, in a fresh module so we don't share state across
    test invocations."""
    spec = importlib.util.spec_from_file_location("_m0001", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _seed_legacy_jobs_table(conn: sqlite3.Connection) -> None:
    """Build a `jobs` table with the pre-Sprint-2.1 column set."""
    conn.execute(
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
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        "INSERT INTO jobs (job_id, kind, channel_code, status) VALUES (?, ?, ?, ?)",
        ("legacy-job-1", "render", "test-channel", "completed"),
    )
    conn.commit()


def test_migration_adds_column():
    m = _load_migration()
    assert m.VERSION == 1
    assert m.NAME == "jobs_add_render_plan_json"

    conn = sqlite3.connect(":memory:")
    try:
        _seed_legacy_jobs_table(conn)
        # Confirm the column is absent before migration.
        before = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert "render_plan_json" not in before

        m.up(conn)

        after = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert "render_plan_json" in after
        # Existing legacy row reads NULL on the new column.
        row = conn.execute("SELECT render_plan_json FROM jobs WHERE job_id='legacy-job-1'").fetchone()
        assert row is not None and row[0] is None
    finally:
        conn.close()


def test_migration_is_idempotent():
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_legacy_jobs_table(conn)
        m.up(conn)
        # Second run must not raise (sqlite would otherwise error: 'duplicate column name').
        m.up(conn)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        assert "render_plan_json" in cols
    finally:
        conn.close()


def test_migration_does_not_touch_other_tables():
    _load_migration()  # validate it loads — actual application via runner below
    m = _load_migration()
    conn = sqlite3.connect(":memory:")
    try:
        _seed_legacy_jobs_table(conn)
        conn.execute(
            "CREATE TABLE job_parts (id INTEGER PRIMARY KEY, job_id TEXT, part_no INTEGER)"
        )
        conn.execute("INSERT INTO job_parts (job_id, part_no) VALUES ('legacy-job-1', 1)")
        conn.commit()

        m.up(conn)

        parts_cols = {row[1] for row in conn.execute("PRAGMA table_info(job_parts)").fetchall()}
        # job_parts schema untouched.
        assert "render_plan_json" not in parts_cols
        # job_parts row preserved.
        count = conn.execute("SELECT COUNT(*) FROM job_parts").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_runner_records_version_when_invoked_via_run_pending():
    """End-to-end: invoke run_pending_migrations against a memory DB and
    check schema_versions reflects version 1."""
    from app.db.migrations import run_pending_migrations, applied_versions

    conn = sqlite3.connect(":memory:")
    try:
        _seed_legacy_jobs_table(conn)
        result = run_pending_migrations(conn)
        assert 1 in result["applied"]
        assert 1 in applied_versions(conn)
        # Rerun: skipped, not reapplied.
        result2 = run_pending_migrations(conn)
        assert 1 in result2["skipped"]
        assert 1 not in result2["applied"]
    finally:
        conn.close()
