"""Migration 0006: add created_at column to render_ab_scores.

Sprint L-C (2026-06-09): adds an immutable created_at timestamp so
time-window analytics can filter by render date. scored_at is updated
on every upsert; created_at is set on first INSERT and never changes.

Additive — ALTER TABLE ADD COLUMN with a DEFAULT value. Existing rows
receive datetime('now') (the migration timestamp) as their created_at,
which is acceptable for historical data. Uses PRAGMA table_info to
guard against duplicate-column errors on repeated runs.
"""
VERSION = 6
NAME = "add_created_at_to_render_ab_scores"


def up(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(render_ab_scores)").fetchall()}
    if "created_at" not in cols:
        conn.execute(
            "ALTER TABLE render_ab_scores ADD COLUMN "
            "created_at TEXT NOT NULL DEFAULT (datetime('now'))"
        )
