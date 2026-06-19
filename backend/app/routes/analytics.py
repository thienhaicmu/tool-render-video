"""
routes/analytics.py — Analytics Dashboard REST endpoints.

GET /api/analytics/overview
    Snapshot: job counts, feedback totals, avg scores, editorial overrides.

GET /api/analytics/scores/trend?channel_code=&days=30
    Daily avg viral/hook/retention scores from render_ab_scores.

GET /api/analytics/feedback/by-hook?channel_code=&days=30
    Like/dislike counts and like_rate grouped by hook_type.

GET /api/analytics/jobs/trend?days=30
    Daily completed/failed job counts from the jobs table.

All queries are read-only, use db_conn(), and never raise.
Blast radius: LOW — new file, no existing routes modified.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.db.connection import db_conn

logger = logging.getLogger("app.routes.analytics")
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _days_clause(days: int, col: str) -> str:
    """SQLite WHERE clause fragment for rows within the last N days."""
    return f"{col} >= datetime('now', '-{int(days)} days')"


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return round(float(v), 2) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v) if v is not None else default
    except (TypeError, ValueError):
        return default


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview():
    """Snapshot summary across all channels."""
    jobs = _query_job_counts()
    feedback = _query_feedback_totals()
    scores = _query_avg_scores()
    overrides = _query_editorial_overrides()
    return {
        "jobs": jobs,
        "feedback": feedback,
        "scores": scores,
        "editorial_overrides": overrides,
    }


@router.get("/scores/trend")
def get_scores_trend(
    channel_code: str = Query("", description="Filter by channel. Empty = all channels."),
    days: int = Query(30, ge=1, le=365),
):
    """Daily avg scores from render_ab_scores, newest first."""
    try:
        with db_conn() as conn:
            where = [_days_clause(days, "scored_at")]
            params: list = []
            if channel_code.strip():
                where.append("channel_code = ?")
                params.append(channel_code.strip())
            where_sql = "WHERE " + " AND ".join(where) if where else ""
            rows = conn.execute(
                f"""
                SELECT strftime('%Y-%m-%d', scored_at) AS date,
                       AVG(viral_score)       AS avg_viral,
                       AVG(hook_score)        AS avg_hook,
                       AVG(retention_score)   AS avg_retention,
                       AVG(output_rank_score) AS avg_rank_score,
                       COUNT(*)               AS count
                FROM render_ab_scores
                {where_sql}
                GROUP BY date
                ORDER BY date DESC
                """,
                params,
            ).fetchall()
        return [
            {
                "date":           r["date"],
                "avg_viral":      _safe_float(r["avg_viral"]),
                "avg_hook":       _safe_float(r["avg_hook"]),
                "avg_retention":  _safe_float(r["avg_retention"]),
                "avg_rank_score": _safe_float(r["avg_rank_score"]),
                "count":          _safe_int(r["count"]),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("analytics/scores/trend failed: %s", exc)
        return []


@router.get("/feedback/by-hook")
def get_feedback_by_hook(
    channel_code: str = Query("", description="Filter by channel. Empty = all channels."),
    days: int = Query(30, ge=1, le=365),
):
    """Like/dislike breakdown grouped by hook_type, sorted by like_rate desc."""
    try:
        with db_conn() as conn:
            where = [_days_clause(days, "rated_at")]
            params: list = []
            if channel_code.strip():
                where.append("channel_code = ?")
                params.append(channel_code.strip())
            where_sql = "WHERE " + " AND ".join(where)
            rows = conn.execute(
                f"""
                SELECT hook_type,
                       SUM(CASE WHEN rating =  1 THEN 1 ELSE 0 END) AS likes,
                       SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) AS dislikes,
                       COUNT(*) AS total
                FROM clip_feedback
                {where_sql}
                GROUP BY hook_type
                ORDER BY likes DESC
                """,
                params,
            ).fetchall()
        result = []
        for r in rows:
            likes    = _safe_int(r["likes"])
            dislikes = _safe_int(r["dislikes"])
            total    = _safe_int(r["total"])
            like_rate = round(likes / total, 3) if total > 0 else 0.0
            result.append({
                "hook_type": r["hook_type"] or "none",
                "likes":     likes,
                "dislikes":  dislikes,
                "total":     total,
                "like_rate": like_rate,
            })
        # Sort: highest like_rate first, then by total volume
        result.sort(key=lambda x: (-x["like_rate"], -x["total"]))
        return result
    except Exception as exc:
        logger.warning("analytics/feedback/by-hook failed: %s", exc)
        return []


@router.get("/jobs/trend")
def get_jobs_trend(
    days: int = Query(30, ge=1, le=365),
):
    """Daily completed/failed job counts, newest first."""
    try:
        with db_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT strftime('%Y-%m-%d', updated_at) AS date,
                       SUM(CASE WHEN status IN ('completed', 'completed_with_errors')
                                THEN 1 ELSE 0 END) AS completed,
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                       COUNT(*) AS total
                FROM jobs
                WHERE {_days_clause(days, 'updated_at')}
                  AND status IN ('completed', 'completed_with_errors', 'failed')
                GROUP BY date
                ORDER BY date DESC
                """,
            ).fetchall()
        return [
            {
                "date":      r["date"],
                "completed": _safe_int(r["completed"]),
                "failed":    _safe_int(r["failed"]),
                "total":     _safe_int(r["total"]),
            }
            for r in rows
        ]
    except Exception as exc:
        logger.warning("analytics/jobs/trend failed: %s", exc)
        return []


# ── Sub-queries used by /overview ─────────────────────────────────────────────

def _query_job_counts() -> dict:
    try:
        with db_conn() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status IN ('completed','completed_with_errors') THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status = 'failed'    THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status IN ('running','queued') THEN 1 ELSE 0 END) AS running,
                    COUNT(*) AS total
                FROM jobs
                """
            ).fetchone()
        return {
            "completed": _safe_int(row["completed"]) if row else 0,
            "failed":    _safe_int(row["failed"])    if row else 0,
            "running":   _safe_int(row["running"])   if row else 0,
            "total":     _safe_int(row["total"])     if row else 0,
        }
    except Exception:
        return {"completed": 0, "failed": 0, "running": 0, "total": 0}


def _query_feedback_totals() -> dict:
    try:
        with db_conn() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN rating =  1 THEN 1 ELSE 0 END) AS liked,
                    SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) AS disliked,
                    COUNT(*) AS total
                FROM clip_feedback
                """
            ).fetchone()
        liked    = _safe_int(row["liked"])    if row else 0
        disliked = _safe_int(row["disliked"]) if row else 0
        total    = _safe_int(row["total"])    if row else 0
        return {
            "liked":     liked,
            "disliked":  disliked,
            "total":     total,
            "like_rate": round(liked / total, 3) if total > 0 else 0.0,
        }
    except Exception:
        return {"liked": 0, "disliked": 0, "total": 0, "like_rate": 0.0}


def _query_avg_scores() -> dict:
    try:
        with db_conn() as conn:
            row = conn.execute(
                """
                SELECT AVG(viral_score)       AS avg_viral,
                       AVG(hook_score)        AS avg_hook,
                       AVG(retention_score)   AS avg_retention,
                       AVG(output_rank_score) AS avg_rank_score,
                       COUNT(*)               AS total_clips
                FROM render_ab_scores
                """
            ).fetchone()
        if not row or not row["total_clips"]:
            return {"avg_viral": 0.0, "avg_hook": 0.0, "avg_retention": 0.0,
                    "avg_rank_score": 0.0, "total_clips": 0}
        return {
            "avg_viral":      _safe_float(row["avg_viral"]),
            "avg_hook":       _safe_float(row["avg_hook"]),
            "avg_retention":  _safe_float(row["avg_retention"]),
            "avg_rank_score": _safe_float(row["avg_rank_score"]),
            "total_clips":    _safe_int(row["total_clips"]),
        }
    except Exception:
        return {"avg_viral": 0.0, "avg_hook": 0.0, "avg_retention": 0.0,
                "avg_rank_score": 0.0, "total_clips": 0}


def _query_editorial_overrides() -> dict:
    """Read current session counter values from the Prometheus registry.

    Returns {} when prometheus_client is not installed (NoOp path) or
    when the counter has never been incremented this session.
    """
    try:
        from app.services.metrics import RENDER_ENGINE_EDITORIAL_OVERRIDES
        # _NoOpMetric has no .collect() — check for real Counter
        if not hasattr(RENDER_ENGINE_EDITORIAL_OVERRIDES, "collect"):
            return {}
        result: dict = {}
        for metric_family in RENDER_ENGINE_EDITORIAL_OVERRIDES.collect():
            for sample in metric_family.samples:
                field = sample.labels.get("field", "unknown")
                result[field] = int(sample.value)
        return result
    except Exception:
        return {}
