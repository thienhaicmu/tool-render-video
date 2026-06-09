"""Migration 0004: add render_ab_scores table for per-output score tracking.

Sprint G-3 closure (2026-06-09): new table stores viral/hook/retention scores
per (job_id, part_no) so AI selection quality can be queried and correlated
with structure_bias variants over time. Purely additive — no existing table
touched.
"""
VERSION = 4
NAME = "add_render_ab_scores_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS render_ab_scores (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id            TEXT    NOT NULL,
            part_no           INTEGER NOT NULL,
            channel_code      TEXT    NOT NULL DEFAULT '',
            structure_bias    TEXT    NOT NULL DEFAULT 'balanced',
            viral_score       REAL    NOT NULL DEFAULT 50.0,
            hook_score        REAL    NOT NULL DEFAULT 50.0,
            retention_score   REAL    NOT NULL DEFAULT 50.0,
            output_rank_score REAL    NOT NULL DEFAULT 50.0,
            output_rank       INTEGER NOT NULL DEFAULT 0,
            is_best_output    INTEGER NOT NULL DEFAULT 0,
            feedback_rating   INTEGER NOT NULL DEFAULT 0,
            scored_at         TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(job_id, part_no),
            FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ab_scores_channel "
        "ON render_ab_scores(channel_code, structure_bias)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ab_scores_job "
        "ON render_ab_scores(job_id, part_no)"
    )
