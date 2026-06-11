"""Migration 0007: add asset_catalog table for deduplicated asset registry.

Phase 3 — Asset Catalog Foundation (2026-06-11): new table stores downloaded
assets keyed by SHA256(url) for deduplication. Tracks storage tier, lifecycle
status, and ref_count so multiple render jobs can share a single cached asset.
Purely additive — no existing table touched.
"""
VERSION = 7
NAME = "add_asset_catalog"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS asset_catalog (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id         TEXT    NOT NULL UNIQUE,
            dedup_key        TEXT    NOT NULL UNIQUE,
            url              TEXT    NOT NULL,
            platform         TEXT    NOT NULL DEFAULT '',
            title            TEXT    NOT NULL DEFAULT '',
            duration         REAL    NOT NULL DEFAULT 0,
            height           INTEGER NOT NULL DEFAULT 0,
            fps              REAL    NOT NULL DEFAULT 0,
            filesize         INTEGER NOT NULL DEFAULT 0,
            filename         TEXT    NOT NULL DEFAULT '',
            storage_tier     TEXT    NOT NULL DEFAULT 'raw',
            storage_path     TEXT    NOT NULL DEFAULT '',
            thumbnail_url    TEXT    NOT NULL DEFAULT '',
            status           TEXT    NOT NULL DEFAULT 'pending',
            ref_count        INTEGER NOT NULL DEFAULT 0,
            quality          TEXT    NOT NULL DEFAULT 'best',
            error_msg        TEXT    NOT NULL DEFAULT '',
            download_job_id  TEXT    NOT NULL DEFAULT '',
            meta_json        TEXT    NOT NULL DEFAULT '{}',
            expires_at       TEXT,
            archived_at      TEXT,
            deleted_at       TEXT,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_catalog_dedup "
        "ON asset_catalog(dedup_key)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_catalog_status "
        "ON asset_catalog(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_catalog_platform "
        "ON asset_catalog(platform)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_catalog_created "
        "ON asset_catalog(created_at)"
    )
