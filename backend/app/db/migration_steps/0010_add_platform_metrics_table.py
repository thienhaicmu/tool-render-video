"""Migration 0010 — Add platform_metrics table.

Phase V1 — Platform Performance Ingestion.
Adds a table to store push-based platform performance data
(watch-time, CTR) submitted via /api/feedback/platform-metrics.

Schema:
  metric_id    — ROWID alias, auto-assigned
  channel_code — which channel this metric belongs to
  platform     — tiktok / instagram / youtube / …
  post_id      — platform unique post identifier (optional, "" when unknown)
  watch_pct    — 0.0–1.0, average watch-through percentage
  ctr          — 0.0–1.0, click-through rate
  impressions  — raw impression count (informational)
  recorded_at  — ISO-8601 UTC, when the data was collected on the platform
  ingested_at  — when this row was inserted into our DB (auto-set)

Unique constraint: (channel_code, platform, post_id) WHERE post_id != ''
so reposting the same post's metrics updates the row rather than duplicating.

Additive-only — no column removed or renamed.
Idempotent — safe to run multiple times.
"""
from __future__ import annotations

import sqlite3

VERSION = 10
NAME = "add_platform_metrics_table"


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS platform_metrics (
            metric_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_code TEXT    NOT NULL DEFAULT '',
            platform     TEXT    NOT NULL DEFAULT '',
            post_id      TEXT    NOT NULL DEFAULT '',
            watch_pct    REAL    NOT NULL DEFAULT 0.0,
            ctr          REAL    NOT NULL DEFAULT 0.0,
            impressions  INTEGER NOT NULL DEFAULT 0,
            recorded_at  TEXT    NOT NULL DEFAULT '',
            ingested_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_platform_metrics_channel "
        "ON platform_metrics (channel_code, platform, recorded_at DESC)"
    )
    # Partial unique index: only enforce uniqueness when post_id is known.
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_metrics_unique_post "
        "ON platform_metrics (channel_code, platform, post_id) "
        "WHERE post_id != ''"
    )
