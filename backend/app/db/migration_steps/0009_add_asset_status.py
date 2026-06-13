"""Migration 0009 — Add status column to assets table.

Phase U2 — Asset Lifecycle State Machine.
Adds an explicit lifecycle state so consumers can distinguish:
  pending   — registered, enrichment not yet submitted
  enriching — background thread is actively enriching
  ready     — enrichment completed successfully (enriched_at is set)
  failed    — enrichment threw an exception

Backfill: existing rows with enriched_at NOT NULL are set to 'ready';
everything else stays 'pending'.

Additive-only — no column removed or renamed.
Idempotent — safe to run multiple times.
"""
from __future__ import annotations

import sqlite3

VERSION = 9
NAME = "add_asset_status"


def up(conn: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in conn.execute("PRAGMA table_info(assets)")
    }
    if "status" not in existing:
        conn.execute(
            "ALTER TABLE assets ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'"
        )
    # Backfill: rows already enriched should be marked 'ready'.
    conn.execute(
        "UPDATE assets SET status = 'ready' WHERE enriched_at IS NOT NULL AND status = 'pending'"
    )
