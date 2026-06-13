"""
platform_metrics_repo.py — CRUD for platform_metrics table (Phase V1).

Stores push-based platform performance data (watch-time, CTR) submitted via
/api/feedback/platform-metrics. Pure DB access — no AI, no subprocess.
Never raises — returns safe defaults on error (Sacred Contract #3 spirit).
"""
from __future__ import annotations

import logging

from app.db.connection import db_conn

logger = logging.getLogger("app.db.platform_metrics")


def upsert_platform_metric(
    *,
    channel_code: str,
    platform: str,
    post_id: str = "",
    watch_pct: float = 0.0,
    ctr: float = 0.0,
    impressions: int = 0,
    recorded_at: str = "",
) -> bool:
    """Insert or update a platform metric row.

    When post_id is non-empty, a second submission for the same
    (channel_code, platform, post_id) updates the existing row.
    When post_id is empty, each call appends a new row.
    Returns True on success.
    """
    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO platform_metrics
                    (channel_code, platform, post_id,
                     watch_pct, ctr, impressions, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(channel_code, platform, post_id)
                    WHERE post_id != ''
                DO UPDATE SET
                    watch_pct   = excluded.watch_pct,
                    ctr         = excluded.ctr,
                    impressions = excluded.impressions,
                    recorded_at = excluded.recorded_at,
                    ingested_at = datetime('now')
                """,
                (
                    channel_code or "",
                    platform or "",
                    post_id or "",
                    float(watch_pct),
                    float(ctr),
                    int(impressions),
                    recorded_at or "",
                ),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_platform_metric failed: %s", exc)
        return False


def get_channel_platform_summary(
    channel_code: str,
    platform: str = "",
    limit: int = 100,
) -> dict:
    """Return aggregated watch_pct and ctr averages for a channel.

    Returns:
      avg_watch_pct        float  — average watch-through percentage (0.0–1.0)
      avg_ctr              float  — average click-through rate (0.0–1.0)
      platform_sample_size int    — number of rows aggregated

    Never raises — returns zeros on error.
    """
    _empty = {"avg_watch_pct": 0.0, "avg_ctr": 0.0, "platform_sample_size": 0}
    try:
        with db_conn() as conn:
            if platform:
                row = conn.execute(
                    """
                    SELECT AVG(watch_pct), AVG(ctr), COUNT(*)
                    FROM (
                        SELECT watch_pct, ctr
                        FROM platform_metrics
                        WHERE channel_code = ? AND platform = ?
                        ORDER BY recorded_at DESC
                        LIMIT ?
                    )
                    """,
                    (channel_code, platform, limit),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT AVG(watch_pct), AVG(ctr), COUNT(*)
                    FROM (
                        SELECT watch_pct, ctr
                        FROM platform_metrics
                        WHERE channel_code = ?
                        ORDER BY recorded_at DESC
                        LIMIT ?
                    )
                    """,
                    (channel_code, limit),
                ).fetchone()
        if row is None or row[2] == 0:
            return _empty
        return {
            "avg_watch_pct": round(float(row[0] or 0.0), 4),
            "avg_ctr": round(float(row[1] or 0.0), 4),
            "platform_sample_size": int(row[2]),
        }
    except Exception as exc:
        logger.warning("get_channel_platform_summary failed: %s", exc)
        return _empty


def list_platform_metrics(
    channel_code: str,
    platform: str = "",
    limit: int = 100,
) -> list[dict]:
    """Return recent platform_metrics rows for a channel.

    Never raises — returns empty list on error.
    """
    try:
        with db_conn() as conn:
            if platform:
                rows = conn.execute(
                    """
                    SELECT metric_id, channel_code, platform, post_id,
                           watch_pct, ctr, impressions, recorded_at, ingested_at
                    FROM platform_metrics
                    WHERE channel_code = ? AND platform = ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    (channel_code, platform, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT metric_id, channel_code, platform, post_id,
                           watch_pct, ctr, impressions, recorded_at, ingested_at
                    FROM platform_metrics
                    WHERE channel_code = ?
                    ORDER BY recorded_at DESC
                    LIMIT ?
                    """,
                    (channel_code, limit),
                ).fetchall()
        keys = (
            "metric_id", "channel_code", "platform", "post_id",
            "watch_pct", "ctr", "impressions", "recorded_at", "ingested_at",
        )
        return [dict(zip(keys, r)) for r in rows]
    except Exception as exc:
        logger.warning("list_platform_metrics failed: %s", exc)
        return []
