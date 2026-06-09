"""CRUD for render_ab_scores — per-output score tracking for AI quality analysis.

All functions swallow exceptions and never raise — callers are render pipeline
stages where a DB failure must never abort a render job.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.db.ab_scores")


def upsert_ab_score(
    *,
    job_id: str,
    part_no: int,
    channel_code: str,
    structure_bias: str,
    viral_score: float,
    hook_score: float,
    retention_score: float,
    output_rank_score: float,
    output_rank: int,
    is_best_output: bool,
) -> None:
    """Insert or update a score row. Swallows all exceptions."""
    try:
        from app.db.connection import db_conn
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO render_ab_scores
                    (job_id, part_no, channel_code, structure_bias,
                     viral_score, hook_score, retention_score,
                     output_rank_score, output_rank, is_best_output)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, part_no) DO UPDATE SET
                    channel_code      = excluded.channel_code,
                    structure_bias    = excluded.structure_bias,
                    viral_score       = excluded.viral_score,
                    hook_score        = excluded.hook_score,
                    retention_score   = excluded.retention_score,
                    output_rank_score = excluded.output_rank_score,
                    output_rank       = excluded.output_rank,
                    is_best_output    = excluded.is_best_output,
                    scored_at         = datetime('now')
                """,
                (
                    job_id, part_no, channel_code, structure_bias,
                    viral_score, hook_score, retention_score,
                    output_rank_score, output_rank, int(is_best_output),
                ),
            )
    except Exception as exc:
        logger.warning("upsert_ab_score(%s, %d) failed: %s", job_id, part_no, exc)


def list_channel_scores(channel_code: str, limit: int = 500) -> list[dict]:
    """Return recent scores for a channel, newest first. Returns [] on error."""
    try:
        from app.db.connection import db_conn
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM render_ab_scores "
                "WHERE channel_code = ? ORDER BY scored_at DESC LIMIT ?",
                (channel_code, limit),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("list_channel_scores(%r) failed: %s", channel_code, exc)
        return []
