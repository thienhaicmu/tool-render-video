"""Architecture-review Batch D-2-thin (2026-06-30) — migration 0014 smoke tests.

Pins the additive contract for ``jobs.scene_map_json``:

1. ``up()`` adds the column with the expected type + default NULL.
2. ``up()`` is idempotent (safe to re-run on a partially-applied DB).
3. Pre-existing rows survive with the new column NULL — no data loss
   (Sacred Contract #7: additive ALTER, never destructive).
4. Round-trip: column accepts text writes and reads them back.
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_STEP_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "db" / "migration_steps"
    / "0014_jobs_add_scene_map_json.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_0014", _STEP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _seed_jobs_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            channel_code TEXT,
            status TEXT,
            payload_json TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _apply_migration(conn: sqlite3.Connection) -> None:
    _load_migration().up(conn)


def test_migration_adds_scene_map_json_column():
    conn = sqlite3.connect(":memory:")
    _seed_jobs_table(conn)
    _apply_migration(conn)
    cols = {row[1]: row for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "scene_map_json" in cols, "scene_map_json column not added"
    col = cols["scene_map_json"]
    assert col[2].upper() == "TEXT"
    assert col[3] == 0, "column must be nullable"


def test_migration_is_idempotent():
    conn = sqlite3.connect(":memory:")
    _seed_jobs_table(conn)
    _apply_migration(conn)
    _apply_migration(conn)  # MUST NOT raise
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "scene_map_json" in cols


def test_existing_rows_survive_migration_with_null_column():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_jobs_table(conn)
    conn.execute(
        "INSERT INTO jobs (job_id, channel_code, status, payload_json) VALUES (?, ?, ?, ?)",
        ("legacy-job", "vn", "succeeded", '{"render_format": "clips"}'),
    )
    _apply_migration(conn)
    row = conn.execute("SELECT * FROM jobs WHERE job_id = 'legacy-job'").fetchone()
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["scene_map_json"] is None


def test_column_accepts_text_payload_round_trip():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_jobs_table(conn)
    _apply_migration(conn)
    conn.execute(
        "INSERT INTO jobs (job_id, channel_code, status) VALUES (?, ?, ?)",
        ("new-job", "vn", "queued"),
    )
    payload = '{"schema_version": 1, "shots": [{"start": 0.0, "end": 5.0}]}'
    conn.execute(
        "UPDATE jobs SET scene_map_json = ? WHERE job_id = ?",
        (payload, "new-job"),
    )
    row = conn.execute(
        "SELECT scene_map_json FROM jobs WHERE job_id = 'new-job'"
    ).fetchone()
    assert row["scene_map_json"] == payload


def test_column_default_is_null_for_inserts_omitting_it():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_jobs_table(conn)
    _apply_migration(conn)
    conn.execute(
        "INSERT INTO jobs (job_id, channel_code, status) VALUES (?, ?, ?)",
        ("default-test", "vn", "queued"),
    )
    row = conn.execute(
        "SELECT scene_map_json FROM jobs WHERE job_id = 'default-test'"
    ).fetchone()
    assert row["scene_map_json"] is None
