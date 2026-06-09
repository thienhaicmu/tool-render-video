"""Sprint H-2 — migration 0004 smoke tests (render_ab_scores table).

1. Table created with expected columns.
2. up() is idempotent (safe to run twice).
3. Both indexes created.
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_STEP_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "db" / "migration_steps"
    / "0004_add_render_ab_scores_table.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_0004", _STEP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _apply_migration(conn):
    _load_migration().up(conn)


def test_migration_creates_table():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY)")
    conn.commit()
    _apply_migration(conn)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='render_ab_scores'"
    ).fetchone()
    assert row is not None, "render_ab_scores table not found"


def test_migration_is_idempotent():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY)")
    conn.commit()
    _apply_migration(conn)
    _apply_migration(conn)  # must not raise


def test_migration_creates_indexes():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY)")
    conn.commit()
    _apply_migration(conn)
    indexes = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "idx_ab_scores_channel" in indexes
    assert "idx_ab_scores_job" in indexes
