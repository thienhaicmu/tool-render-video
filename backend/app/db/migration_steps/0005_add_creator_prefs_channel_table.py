"""Migration 0005: add creator_prefs_channel table for per-channel CreatorContext.

Sprint I-B (2026-06-09): new table stores per-channel editorial hints so a
creator with multiple channels (e.g. educational vs entertainment) can provide
different AI guidance per channel. Purely additive — no existing table touched.

The render pipeline falls back to the global creator_prefs singleton when no
per-channel row exists, preserving backward compatibility.
"""
VERSION = 5
NAME = "add_creator_prefs_channel_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS creator_prefs_channel (
            channel_code TEXT    PRIMARY KEY,
            prefs_json   TEXT    NOT NULL DEFAULT '{}',
            updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
