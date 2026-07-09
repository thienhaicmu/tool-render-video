"""
Migration 0019: characters table (Story Mode Character DB).

Canonical per-character record so a character drawn in chapter 1 stays visually
+ vocally consistent in chapter 186: canonical_desc drives image-prompt injection,
reference_image_path is the pinned Character Reference Sheet used to condition
generation, and voice_engine/voice_id drive per-character TTS casting.

Scoped to a series (FK story_series.id ON DELETE CASCADE). A one-off chapter
(empty series_id) never writes here.

Purely additive; idempotent. Sacred Contract #7 honoured. FK cascade mirrors
migration 0003.
"""
VERSION = 19
NAME = "add_story_characters_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id                   TEXT PRIMARY KEY,
            series_id            TEXT NOT NULL DEFAULT '',
            name                 TEXT NOT NULL DEFAULT '',
            canonical_desc       TEXT NOT NULL DEFAULT '',
            reference_image_path TEXT NOT NULL DEFAULT '',
            voice_engine         TEXT NOT NULL DEFAULT '',
            voice_id             TEXT NOT NULL DEFAULT '',
            age                  TEXT NOT NULL DEFAULT '',
            gender               TEXT NOT NULL DEFAULT '',
            created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            FOREIGN KEY (series_id) REFERENCES story_series(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_characters_series "
        "ON characters(series_id)"
    )
