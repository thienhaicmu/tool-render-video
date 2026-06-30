"""
Migration 0014: jobs.scene_map_json — nullable column for the SceneMap blob.

Architecture-review Batch D-2-thin (2026-06-30). The Comprehension stage
hoist (Batch C, migration 0013) added story_model_json. This sibling
migration adds a column for the SceneMap substrate produced by the new
scene_map_stage from the PySceneDetect output. The column lays the
durable foundation that future D-2-snap (pass-3 snap-to-shot) and
D-2-motion (motion crop subject path from persisted shots) consume.

Additive, NULL-by-default, never read by pre-migration code — backward-compat
guaranteed for stored payloads and in-flight jobs. Both Recap and Clip jobs
have the column; only jobs that ran the scene_map stage populate it.

Sacred Contract #2 (defaults to NULL = disabled) and #7 (additive ALTER TABLE,
no DROP / RENAME / type-change) honoured. Idempotent: PRAGMA table_info skip +
the runner's schema_versions record.
"""
from __future__ import annotations

import sqlite3


VERSION = 14
NAME = "jobs_add_scene_map_json"


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cur.fetchall()}
    if "scene_map_json" not in existing:
        cur.execute("ALTER TABLE jobs ADD COLUMN scene_map_json TEXT DEFAULT NULL")
