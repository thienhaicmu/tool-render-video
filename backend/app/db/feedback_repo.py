"""
feedback_repo.py — CRUD for clip_feedback table (Phase 6).

Schema is created by init_db() in connection.py.
Sprint 5.3 (audit 2026-06-02 P2-D9): migrated from raw get_conn() + manual
close to db_conn() context manager so connections are released even when
an exception fires inside the block. The outer try/except that returns
safe defaults stays — Contract 3 spirit.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.db.connection import db_conn

logger = logging.getLogger("app.db.feedback")


def upsert_clip_feedback(
    *,
    job_id: str,
    part_no: int,
    channel_code: str,
    goal: str,
    rating: int,                # 1 (like) or -1 (dislike)
    hook_type: str = "none",
    clip_type: str = "unknown",
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    duration_sec: float = 0.0,
) -> bool:
    """Insert or update a clip rating. Returns True on success."""
    if rating not in (1, -1):
        return False
    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO clip_feedback
                    (job_id, part_no, channel_code, goal, rating,
                     hook_type, clip_type, start_sec, end_sec, duration_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, part_no) DO UPDATE SET
                    rating       = excluded.rating,
                    hook_type    = excluded.hook_type,
                    clip_type    = excluded.clip_type,
                    start_sec    = excluded.start_sec,
                    end_sec      = excluded.end_sec,
                    duration_sec = excluded.duration_sec,
                    rated_at     = datetime('now')
                """,
                (
                    job_id, part_no, channel_code or "", goal or "",
                    rating, hook_type or "none", clip_type or "unknown",
                    start_sec, end_sec, duration_sec,
                ),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_clip_feedback failed: %s", exc)
        return False


def get_clip_feedback(job_id: str, part_no: int) -> Optional[dict]:
    """Return the feedback record for a specific job part, or None."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                """
                SELECT job_id, part_no, channel_code, goal, rating,
                       hook_type, clip_type, start_sec, end_sec, duration_sec, rated_at
                FROM clip_feedback
                WHERE job_id = ? AND part_no = ?
                """,
                (job_id, part_no),
            ).fetchone()
        if row is None:
            return None
        keys = ("job_id", "part_no", "channel_code", "goal", "rating",
                "hook_type", "clip_type", "start_sec", "end_sec", "duration_sec", "rated_at")
        return dict(zip(keys, row))
    except Exception as exc:
        logger.warning("get_clip_feedback failed: %s", exc)
        return None


def list_feedback_for_channel(
    channel_code: str,
    goal: str = "",
    limit: int = 200,
) -> list[dict]:
    """Return up to `limit` feedback records for a channel (optional goal filter)."""
    try:
        with db_conn() as conn:
            if goal:
                rows = conn.execute(
                    """
                    SELECT job_id, part_no, channel_code, goal, rating,
                           hook_type, clip_type, start_sec, end_sec, duration_sec, rated_at
                    FROM clip_feedback
                    WHERE channel_code = ? AND goal = ?
                    ORDER BY rated_at DESC
                    LIMIT ?
                    """,
                    (channel_code, goal, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT job_id, part_no, channel_code, goal, rating,
                           hook_type, clip_type, start_sec, end_sec, duration_sec, rated_at
                    FROM clip_feedback
                    WHERE channel_code = ?
                    ORDER BY rated_at DESC
                    LIMIT ?
                    """,
                    (channel_code, limit),
                ).fetchall()
        keys = ("job_id", "part_no", "channel_code", "goal", "rating",
                "hook_type", "clip_type", "start_sec", "end_sec", "duration_sec", "rated_at")
        return [dict(zip(keys, r)) for r in rows]
    except Exception as exc:
        logger.warning("list_feedback_for_channel failed: %s", exc)
        return []


def get_feedback_signals(
    channel_code: str,
    goal: str = "",
    limit: int = 100,
) -> dict:
    """Return aggregated preference signals from recent feedback for a channel.

    Phase D — Creator Feedback Loop. Aggregates liked vs disliked hook_types
    and clip duration preferences so the LLM prompt can be personalised.

    Returns a dict with keys:
      liked_hook_types   list[str]  — hook types with net positive rating, desc order
      avoided_hook_types list[str]  — hook types with net negative rating, desc order
      preferred_duration tuple|None — (min_sec, max_sec) of liked clips, or None
      sample_size        int        — total feedback rows considered
    Never raises — returns empty signals dict on any error.
    """
    _base: dict = {
        "liked_hook_types": [],
        "avoided_hook_types": [],
        "preferred_duration": None,
        "sample_size": 0,
    }
    if not (channel_code or "").strip():
        return _base

    result: dict = dict(_base)

    # Clip feedback aggregation — independent of V1/V2 signal extensions below.
    try:
        records = list_feedback_for_channel(channel_code, goal=goal, limit=limit)
        if records:
            # Net score per hook_type: +1 per like, -1 per dislike.
            hook_net: dict[str, int] = {}
            liked_durations: list[float] = []
            for r in records:
                ht = (r.get("hook_type") or "none").strip()
                if ht and ht != "none":
                    hook_net[ht] = hook_net.get(ht, 0) + int(r.get("rating") or 0)
                if r.get("rating") == 1:
                    dur = float(r.get("duration_sec") or 0.0)
                    if dur > 0:
                        liked_durations.append(dur)

            liked_hooks = sorted(
                [ht for ht, net in hook_net.items() if net > 0],
                key=lambda h: hook_net[h], reverse=True,
            )
            avoided_hooks = sorted(
                [ht for ht, net in hook_net.items() if net < 0],
                key=lambda h: hook_net[h],
            )

            preferred_duration = None
            if liked_durations:
                liked_durations.sort()
                p10 = liked_durations[max(0, int(len(liked_durations) * 0.10))]
                p90 = liked_durations[min(len(liked_durations) - 1, int(len(liked_durations) * 0.90))]
                preferred_duration = (round(p10, 1), round(p90, 1))

            result.update({
                "liked_hook_types": liked_hooks[:5],
                "avoided_hook_types": avoided_hooks[:3],
                "preferred_duration": preferred_duration,
                "sample_size": len(records),
            })
    except Exception as exc:
        logger.warning("get_feedback_signals clip aggregation failed: %s", exc)

    # Phase V1: platform performance signals (independent of clip feedback).
    try:
        from app.db.platform_metrics_repo import get_channel_platform_summary
        result.update(get_channel_platform_summary(channel_code))
    except Exception:
        pass

    # Phase V2: cover quality signals (independent of clip feedback).
    try:
        from app.db.jobs_repo import get_channel_cover_quality_summary
        result.update(get_channel_cover_quality_summary(channel_code))
    except Exception:
        pass

    # Phase V3: segment repeat rate — content fingerprinting signal.
    try:
        from app.db.jobs_repo import get_channel_segment_repeat_rate
        result.update(get_channel_segment_repeat_rate(channel_code))
    except Exception:
        pass

    return result


def delete_clip_feedback(job_id: str, part_no: int) -> bool:
    """Remove a feedback record. Returns True on success."""
    try:
        with db_conn() as conn:
            conn.execute(
                "DELETE FROM clip_feedback WHERE job_id = ? AND part_no = ?",
                (job_id, part_no),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_clip_feedback failed: %s", exc)
        return False
