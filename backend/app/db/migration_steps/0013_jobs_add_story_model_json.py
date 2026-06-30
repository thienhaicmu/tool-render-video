"""
Migration 0013: jobs.story_model_json — nullable column for the StoryModel blob.

Architecture-review Batch C (2026-06-30). Hoists Story Intelligence (pass-1)
out of select_recap_plan into a standalone Comprehension pipeline stage. The
stage persists the produced StoryModel blob per job so re-edit UI, future
Clip consumers (Batch C.1), and "did pass-3 cover every plot turn?" diagnostics
can read it without re-running the LLM.

Additive, NULL-by-default, never read by pre-migration code — backward-compat
guaranteed for stored payloads and in-flight jobs. Both Recap and Clip jobs
have the column; only jobs that ran Comprehension populate it.

Sacred Contract #2 (defaults to NULL = disabled) and #7 (additive ALTER TABLE,
no DROP/RENAME/type-change) honoured. Idempotent: PRAGMA table_info skip + the
runner's schema_versions record.
"""
from __future__ import annotations

import sqlite3


VERSION = 13
NAME = "jobs_add_story_model_json"


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cur.fetchall()}
    if "story_model_json" not in existing:
        cur.execute("ALTER TABLE jobs ADD COLUMN story_model_json TEXT DEFAULT NULL")
