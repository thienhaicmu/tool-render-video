"""
Migration 0021: story graph tables (relationships, story_timeline, chapter_summary).

Cross-chapter story memory (Story Mode):
  - relationships: char↔char edges (ally/rival/romance…) for multi-thread stories.
  - story_timeline: ordered events per chapter for continuity.
  - chapter_summary: rolling summary per chapter so a later chapter grounds on
    what happened before (the cross-chapter understanding memory).

All scoped to a series (FK story_series.id ON DELETE CASCADE). A1/A4 graph
consumers ship later (roadmap P8); these tables exist now so the Story
Intelligence phase (P1) can persist without a follow-up migration.

Purely additive; idempotent. Sacred Contract #7 honoured.
"""
VERSION = 21
NAME = "add_story_graph_tables"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id  TEXT NOT NULL DEFAULT '',
            char_a     TEXT NOT NULL DEFAULT '',
            char_b     TEXT NOT NULL DEFAULT '',
            type       TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            FOREIGN KEY (series_id) REFERENCES story_series(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_relationships_series ON relationships(series_id)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_timeline (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id       TEXT NOT NULL DEFAULT '',
            chapter_no      INTEGER NOT NULL DEFAULT 0,
            event           TEXT NOT NULL DEFAULT '',
            characters_json TEXT DEFAULT NULL,
            order_no        INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            FOREIGN KEY (series_id) REFERENCES story_series(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_timeline_series "
        "ON story_timeline(series_id, chapter_no, order_no)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chapter_summary (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            series_id       TEXT NOT NULL DEFAULT '',
            chapter_no      INTEGER NOT NULL DEFAULT 0,
            rolling_summary TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            FOREIGN KEY (series_id) REFERENCES story_series(id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_chapter_summary_series "
        "ON chapter_summary(series_id, chapter_no)"
    )
