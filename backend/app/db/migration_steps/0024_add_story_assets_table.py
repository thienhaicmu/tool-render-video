"""
Migration 0024: story_assets table (offline asset library — AL0).

Indexes a user's offline asset library (characters / backgrounds / objects / frames)
under APP_DATA_DIR/asset_library so Story Mode can pick from it instead of always
calling AI image gen (cheaper + consistent). One row per file on disk; the scanner
(db/story_asset_repo.scan_library) fills it from the path convention
``{kind}/{region}/{genre}/{slug}.png``.

Purely additive: a new table with all-defaulted columns. Idempotent. Sacred
Contract #7 (additive-only) honoured.
"""
VERSION = 24
NAME = "add_story_assets_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_assets (
            id          TEXT PRIMARY KEY,
            kind        TEXT NOT NULL DEFAULT 'character',
            region      TEXT NOT NULL DEFAULT '',
            genre       TEXT NOT NULL DEFAULT '',
            slug        TEXT NOT NULL DEFAULT '',
            name        TEXT NOT NULL DEFAULT '',
            tags        TEXT NOT NULL DEFAULT '',
            style       TEXT NOT NULL DEFAULT '',
            path        TEXT NOT NULL DEFAULT '',
            transparent INTEGER NOT NULL DEFAULT 0,
            license     TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_assets_kind "
        "ON story_assets(kind, region, genre)"
    )
