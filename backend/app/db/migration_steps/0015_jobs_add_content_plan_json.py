"""
Migration 0015: jobs.content_plan_json — nullable column for the ContentPlan blob.

Content Mode (render_format="content") persists a ContentPlan JSON per job
(scenes → narration → emotion/speed/pause + subtitle-style suggestion).
Additive, NULL-by-default, never read by pre-migration code — backward-compat
guaranteed for stored payloads and in-flight jobs.

Sacred Contract #2 (defaults to NULL = disabled) and #7 (additive ALTER TABLE,
no DROP/RENAME/type-change) honoured. Idempotent: PRAGMA table_info skip + the
runner's schema_versions record. Mirrors migration 0012 (recap_plan_json).
"""
from __future__ import annotations

import sqlite3


VERSION = 15
NAME = "jobs_add_content_plan_json"


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cur.fetchall()}
    if "content_plan_json" not in existing:
        cur.execute("ALTER TABLE jobs ADD COLUMN content_plan_json TEXT DEFAULT NULL")
