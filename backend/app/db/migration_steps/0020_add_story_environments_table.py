"""
Migration 0020: environments table (Story Mode World/Environment DB).

Canonical per-location record so scenes set in the same place (e.g. a recurring
sect hall) stay visually consistent across shots + chapters. Scoped to a series
(FK story_series.id ON DELETE CASCADE); a one-off chapter never writes here.

Purely additive; idempotent. Sacred Contract #7 honoured.
"""
VERSION = 20
NAME = "add_story_environments_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS environments (
            id                   TEXT PRIMARY KEY,
            series_id            TEXT NOT NULL DEFAULT '',
            name                 TEXT NOT NULL DEFAULT '',
            canonical_desc       TEXT NOT NULL DEFAULT '',
            reference_image_path TEXT NOT NULL DEFAULT '',
            created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            FOREIGN KEY (series_id) REFERENCES story_series(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_environments_series "
        "ON environments(series_id)"
    )
