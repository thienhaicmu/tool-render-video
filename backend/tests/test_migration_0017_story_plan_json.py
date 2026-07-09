"""Story-to-Video P0 — migration 0017 (jobs.story_plan_json) smoke tests.

Pins the additive contract for ``jobs.story_plan_json`` (mirrors migration 0014):
1. up() adds a nullable TEXT column.
2. up() is idempotent.
3. Pre-existing rows survive with the new column NULL (Sacred Contract #7).
4. Round-trip: the column accepts + returns a StoryPlan JSON blob.
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_STEP_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "db" / "migration_steps"
    / "0017_jobs_add_story_plan_json.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_0017", _STEP_PATH)
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


def test_migration_adds_story_plan_json_column():
    conn = sqlite3.connect(":memory:")
    _seed_jobs_table(conn)
    _load_migration().up(conn)
    cols = {row[1]: row for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "story_plan_json" in cols
    col = cols["story_plan_json"]
    assert col[2].upper() == "TEXT"
    assert col[3] == 0, "column must be nullable"


def test_migration_is_idempotent():
    conn = sqlite3.connect(":memory:")
    _seed_jobs_table(conn)
    mod = _load_migration()
    mod.up(conn)
    mod.up(conn)  # MUST NOT raise
    cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "story_plan_json" in cols


def test_existing_rows_survive_with_null_column():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_jobs_table(conn)
    conn.execute(
        "INSERT INTO jobs (job_id, channel_code, status, payload_json) VALUES (?, ?, ?, ?)",
        ("legacy-job", "vn", "succeeded", '{"render_format": "clips"}'),
    )
    _load_migration().up(conn)
    row = conn.execute("SELECT * FROM jobs WHERE job_id = 'legacy-job'").fetchone()
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["story_plan_json"] is None


def test_column_round_trip():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed_jobs_table(conn)
    _load_migration().up(conn)
    conn.execute("INSERT INTO jobs (job_id, status) VALUES ('j', 'queued')")
    payload = '{"schema_version":1,"scenes":[{"index":0,"shots":[]}]}'
    conn.execute("UPDATE jobs SET story_plan_json = ? WHERE job_id = 'j'", (payload,))
    row = conn.execute("SELECT story_plan_json FROM jobs WHERE job_id='j'").fetchone()
    assert row["story_plan_json"] == payload
