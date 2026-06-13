"""Migration 0008: add render_presets table.

Phase E — Smart Render Presets (2026-06-13). Purely additive new table.
Stores named subsets of RenderRequest params so users can apply them
in one click instead of re-filling the render form every time.

is_builtin=1 rows are seeded by services/preset_seeder.py at startup
and cannot be deleted via the API.
"""
VERSION = 8
NAME = "add_render_presets_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS render_presets (
            preset_id    TEXT PRIMARY KEY,
            name         TEXT    NOT NULL,
            description  TEXT    NOT NULL DEFAULT '',
            channel_code TEXT    NOT NULL DEFAULT '',
            platform     TEXT    NOT NULL DEFAULT '',
            params_json  TEXT    NOT NULL DEFAULT '{}',
            is_builtin   INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_presets_platform "
        "ON render_presets(platform, channel_code)"
    )
