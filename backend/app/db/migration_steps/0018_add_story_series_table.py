"""
Migration 0018: story_series table (Story Mode cross-chapter identity).

A "series" groups the chapters of one long story so characters/environments stay
consistent across chapters. Optional — a one-off chapter renders with an empty
series_id and never touches this table.

Purely additive: a new table with all-defaulted columns. No existing table is
dropped, renamed, or column-type-changed. Idempotent (CREATE TABLE IF NOT EXISTS).
Sacred Contract #7 (additive-only) honoured.
"""
VERSION = 18
NAME = "add_story_series_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_series (
            id            TEXT PRIMARY KEY,
            title         TEXT NOT NULL DEFAULT '',
            language      TEXT NOT NULL DEFAULT '',
            art_style     TEXT NOT NULL DEFAULT '',
            world_setting TEXT NOT NULL DEFAULT '',
            created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_series_updated "
        "ON story_series(updated_at DESC)"
    )
