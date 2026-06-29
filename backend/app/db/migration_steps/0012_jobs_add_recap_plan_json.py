"""
Migration 0012: jobs.recap_plan_json — nullable column for the RecapPlan blob.

Recap/Review Film mode (render_format="recap") persists a RecapPlan JSON per
job (acts → scenes). Additive, NULL-by-default, never read by pre-migration
code — backward-compat guaranteed for stored payloads and in-flight jobs.

Sacred Contract #2 (defaults to NULL = disabled) and #7 (additive ALTER TABLE,
no DROP/RENAME/type-change) honoured. Idempotent: PRAGMA table_info skip + the
runner's schema_versions record.
"""
from __future__ import annotations

import sqlite3


VERSION = 12
NAME = "jobs_add_recap_plan_json"


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cur.fetchall()}
    if "recap_plan_json" not in existing:
        cur.execute("ALTER TABLE jobs ADD COLUMN recap_plan_json TEXT DEFAULT NULL")
