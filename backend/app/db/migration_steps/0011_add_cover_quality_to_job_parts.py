"""Migration 0011 — Add cover_quality_json column to job_parts.

Phase V2 — Frame Signal Integration.
Stores the thumbnail quality tags (e.g. "sharp_frame", "good_face_visibility")
selected by thumbnail_quality.select_best_thumbnail() so per-channel visual
quality trends can be aggregated and fed back into FeedbackSignals.

Schema addition:
  cover_quality_json TEXT DEFAULT NULL
    — JSON array of quality reason tags, e.g. ["sharp_frame", "good_exposure"]
    — NULL when S4_THUMBNAIL_QUALITY_ENABLED was off or the part predates V2

Additive-only — no column removed or renamed.
Idempotent — safe to run multiple times.
"""
from __future__ import annotations

import sqlite3

VERSION = 11
NAME = "add_cover_quality_to_job_parts"


def up(conn: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(job_parts)")
    }
    if "cover_quality_json" not in existing:
        conn.execute(
            "ALTER TABLE job_parts ADD COLUMN cover_quality_json TEXT DEFAULT NULL"
        )
