"""Migration 0008: add acquisition_queue table for priority download scheduling.

Phase 3 — Asset Catalog Foundation (2026-06-11): new table provides a
priority-ordered queue for pending acquisitions, with retry tracking and
links back to download_jobs and asset_catalog once processed.
Purely additive — no existing table touched.
"""
VERSION = 8
NAME = "add_acquisition_queue"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS acquisition_queue (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            queue_id         TEXT    NOT NULL UNIQUE,
            url              TEXT    NOT NULL,
            platform         TEXT    NOT NULL DEFAULT '',
            quality          TEXT    NOT NULL DEFAULT 'best',
            priority         INTEGER NOT NULL DEFAULT 5,
            output_dir       TEXT    NOT NULL DEFAULT '',
            status           TEXT    NOT NULL DEFAULT 'queued',
            download_job_id  TEXT    NOT NULL DEFAULT '',
            asset_id         TEXT    NOT NULL DEFAULT '',
            retry_count      INTEGER NOT NULL DEFAULT 0,
            max_retries      INTEGER NOT NULL DEFAULT 3,
            error_msg        TEXT    NOT NULL DEFAULT '',
            started_at       TEXT,
            completed_at     TEXT,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_acq_queue_status "
        "ON acquisition_queue(status, priority)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_acq_queue_url "
        "ON acquisition_queue(url)"
    )
