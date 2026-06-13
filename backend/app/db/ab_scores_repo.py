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


def update_feedback_rating(*, job_id: str, part_no: int, rating: int) -> bool:
    """Set feedback_rating for (job_id, part_no). Returns True when row existed."""
    try:
        from app.db.connection import db_conn
        with db_conn() as conn:
            cur = conn.execute(
                "UPDATE render_ab_scores SET feedback_rating = ? "
                "WHERE job_id = ? AND part_no = ?",
                (int(rating), job_id, part_no),
            )
            return (cur.rowcount or 0) > 0
    except Exception as exc:
        logger.warning("update_feedback_rating(%s, %d) failed: %s", job_id, part_no, exc)
        return False


def list_channels() -> list[dict]:
    """Return distinct channels that have score rows, newest activity first.

    Each entry: {channel_code, score_count, last_scored_at}. Returns [] on error.
    """
    try:
        from app.db.connection import db_conn
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT channel_code, COUNT(*) AS score_count, "
                "MAX(scored_at) AS last_scored_at "
                "FROM render_ab_scores "
                "GROUP BY channel_code ORDER BY last_scored_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("list_channels() failed: %s", exc)
        return []


def channel_score_summary(channel_code: str, since: "str | None" = None) -> list[dict]:
    """Return per-structure_bias aggregates for a channel, best score first.

    Each entry: {structure_bias, clip_count, avg_viral, avg_hook,
    avg_retention, avg_rank_score, best_output_count}. Returns [] on error.

    ``since``: optional ISO-8601 datetime string — when provided, only rows
    with ``created_at >= since`` are included (Sprint L-C time-window filter).
    """
    try:
        from app.db.connection import db_conn
        with db_conn() as conn:
            if since:
                rows = conn.execute(
                    "SELECT structure_bias, "
                    "COUNT(*) AS clip_count, "
                    "AVG(viral_score) AS avg_viral, "
                    "AVG(hook_score) AS avg_hook, "
                    "AVG(retention_score) AS avg_retention, "
                    "AVG(output_rank_score) AS avg_rank_score, "
                    "SUM(is_best_output) AS best_output_count "
                    "FROM render_ab_scores WHERE channel_code = ? AND created_at >= ? "
                    "GROUP BY structure_bias ORDER BY avg_rank_score DESC",
                    (channel_code, since),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT structure_bias, "
                    "COUNT(*) AS clip_count, "
                    "AVG(viral_score) AS avg_viral, "
                    "AVG(hook_score) AS avg_hook, "
                    "AVG(retention_score) AS avg_retention, "
                    "AVG(output_rank_score) AS avg_rank_score, "
                    "SUM(is_best_output) AS best_output_count "
                    "FROM render_ab_scores WHERE channel_code = ? "
                    "GROUP BY structure_bias ORDER BY avg_rank_score DESC",
                    (channel_code,),
                ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("channel_score_summary(%r) failed: %s", channel_code, exc)
        return []


def list_ab_scores_for_job(job_id: str) -> dict[int, dict]:
    """Return all score rows for a job keyed by part_no. Returns {} on error.

    Phase F — Multi-Output Compare. Used by the outputs endpoint to merge
    rank/score data with job_parts output_file paths.
    """
    try:
        from app.db.connection import db_conn
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM render_ab_scores WHERE job_id = ? ORDER BY output_rank ASC",
                (job_id,),
            ).fetchall()
        return {int(r["part_no"]): dict(r) for r in rows}
    except Exception as exc:
        logger.warning("list_ab_scores_for_job(%r) failed: %s", job_id, exc)
        return {}


def delete_job_scores(job_id: str) -> int:
    """Delete all score rows for a job. Returns row count deleted, 0 on error."""
    try:
        from app.db.connection import db_conn
        with db_conn() as conn:
            cur = conn.execute(
                "DELETE FROM render_ab_scores WHERE job_id = ?", (job_id,)
            )
            return cur.rowcount or 0
    except Exception as exc:
        logger.warning("delete_job_scores(%r) failed: %s", job_id, exc)
        return 0


def list_channel_scores(channel_code: str, limit: int = 500, offset: int = 0) -> list[dict]:
    """Return recent scores for a channel, newest first. Returns [] on error."""
    try:
        from app.db.connection import db_conn
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM render_ab_scores "
                "WHERE channel_code = ? ORDER BY scored_at DESC LIMIT ? OFFSET ?",
                (channel_code, limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("list_channel_scores(%r) failed: %s", channel_code, exc)
        return []
