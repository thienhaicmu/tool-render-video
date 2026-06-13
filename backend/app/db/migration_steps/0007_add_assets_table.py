"""Migration 0007: add assets table + asset_id FK columns.

Phase C — Asset Library (2026-06-13). Purely additive:
  - New `assets` table: per-file identity, enrichment metadata, deduplication key.
  - New nullable `asset_id` column on `download_jobs` and `jobs` so both tables
    can reference the asset they originated from.
  - Two indexes for fast lookup by file_path and original_url.

No existing table is dropped, renamed, or column-type-changed.
"""
VERSION = 7
NAME = "add_assets_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            asset_id                TEXT PRIMARY KEY,
            file_path               TEXT NOT NULL,
            original_url            TEXT NOT NULL DEFAULT '',
            title                   TEXT NOT NULL DEFAULT '',
            duration_sec            REAL NOT NULL DEFAULT 0,
            width                   INTEGER NOT NULL DEFAULT 0,
            height                  INTEGER NOT NULL DEFAULT 0,
            fps                     REAL NOT NULL DEFAULT 0,
            file_size_bytes         INTEGER NOT NULL DEFAULT 0,
            language                TEXT NOT NULL DEFAULT '',
            content_type            TEXT NOT NULL DEFAULT '',
            transcription_cache_path TEXT DEFAULT NULL,
            thumbnail_path          TEXT DEFAULT NULL,
            created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            enriched_at             TEXT DEFAULT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_assets_file_path "
        "ON assets(file_path)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_assets_original_url "
        "ON assets(original_url)"
    )

    # Add asset_id FK to download_jobs if not already present.
    existing_dj = {
        row[1]
        for row in conn.execute("PRAGMA table_info(download_jobs)").fetchall()
    }
    if "asset_id" not in existing_dj:
        conn.execute(
            "ALTER TABLE download_jobs ADD COLUMN asset_id TEXT DEFAULT NULL"
        )

    # Add asset_id FK to jobs if not already present.
    existing_j = {
        row[1]
        for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
    }
    if "asset_id" not in existing_j:
        conn.execute(
            "ALTER TABLE jobs ADD COLUMN asset_id TEXT DEFAULT NULL"
        )
