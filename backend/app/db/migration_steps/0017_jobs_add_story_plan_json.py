"""
Migration 0017: jobs.story_plan_json — nullable column for the StoryPlan blob.

Story Mode (render_format="story") persists a StoryPlan JSON per job
(story_bible → scenes → shots → narration/visual). Additive, NULL-by-default,
never read by pre-migration code — backward-compat guaranteed for stored
payloads and in-flight jobs.

Sacred Contract #2 (defaults to NULL = disabled) and #7 (additive ALTER TABLE,
no DROP/RENAME/type-change) honoured. Idempotent: PRAGMA table_info skip + the
runner's schema_versions record. Mirrors migration 0015 (content_plan_json).
"""
from __future__ import annotations

import sqlite3


VERSION = 17
NAME = "jobs_add_story_plan_json"


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cur.fetchall()}
    if "story_plan_json" not in existing:
        cur.execute("ALTER TABLE jobs ADD COLUMN story_plan_json TEXT DEFAULT NULL")
