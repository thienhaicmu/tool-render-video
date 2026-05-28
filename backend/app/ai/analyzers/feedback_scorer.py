"""
feedback_scorer.py — Applies clip feedback history as a bias signal (Phase 6).

Reads historical ratings for a channel+goal and returns per-candidate bonuses
and penalties that clip_selector adds to the base score.

Public API:
    build_feedback_context(channel_code, goal) -> dict | None
    apply_feedback_bias(candidates, feedback_context) -> list[dict]
    FEEDBACK_SCORING_ENABLED: bool

Design notes:
  - Max bonus: +4, max penalty: -4 (same order as audio_energy and structure bonuses)
  - hook_type with net_score >= +2 → +bonus (scales linearly)
  - hook_type with net_score <= -2 → -penalty (scales linearly)
  - Position bias: if liked clips cluster in one region, nudge candidates there
  - Never raises — returns candidates unchanged on any error
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger("app.ai.analyzers.feedback_scorer")

FEEDBACK_SCORING_ENABLED: bool = (
    os.environ.get("FEEDBACK_SCORING_ENABLED", "1") == "1"
)

_MAX_BIAS = 4.0          # hard cap on bonus and penalty contribution
_MIN_NET_SCORE = 2.0     # net score threshold before bias kicks in
_POSITION_WINDOW = 0.20  # ±20% position match window for liked-position bonus


def build_feedback_context(channel_code: str, goal: str = "") -> dict | None:
    """Load and aggregate channel feedback into a scoring context dict.

    Returns None if no feedback exists or scoring is disabled.
    Result is safe to pass directly to apply_feedback_bias().
    """
    if not FEEDBACK_SCORING_ENABLED or not channel_code:
        return None
    try:
        from app.db.feedback_repo import list_feedback_for_channel
        records = list_feedback_for_channel(channel_code, goal=goal, limit=500)
        if not records:
            return None

        # Net score per hook_type: +1 per like, -1 per dislike
        hook_net: dict[str, float] = {}
        for r in records:
            ht = r.get("hook_type") or "none"
            hook_net[ht] = hook_net.get(ht, 0.0) + float(r["rating"])

        # Net score per clip_type
        clip_type_net: dict[str, float] = {}
        for r in records:
            ct = r.get("clip_type") or "unknown"
            clip_type_net[ct] = clip_type_net.get(ct, 0.0) + float(r["rating"])

        # Average video position of liked clips (start_sec as fraction of total duration)
        # Used to give a mild bonus to candidates near where liked clips tend to start.
        liked_positions = []
        for r in records:
            if r.get("rating") != 1:
                continue
            dur = float(r.get("duration_sec") or 0.0)
            start = float(r.get("start_sec") or 0.0)
            if dur > 0:
                liked_positions.append(start / dur)

        avg_liked_pos = (
            sum(liked_positions) / len(liked_positions) if liked_positions else None
        )

        return {
            "hook_net":      hook_net,
            "clip_type_net": clip_type_net,
            "avg_liked_pos": avg_liked_pos,
            "total":         len(records),
        }
    except Exception as exc:
        logger.debug("build_feedback_context failed: %s", exc)
        return None


def apply_feedback_bias(
    candidates: list[dict],
    feedback_context: dict | None,
) -> list[dict]:
    """Apply feedback-derived bonuses/penalties to candidate scores.

    Modifies candidate dicts in place (score and reason fields only).
    Re-sorts by score after applying. Never raises.
    """
    if not feedback_context or not candidates:
        return candidates
    if not FEEDBACK_SCORING_ENABLED:
        return candidates

    try:
        hook_net      = feedback_context.get("hook_net") or {}
        clip_type_net = feedback_context.get("clip_type_net") or {}
        avg_liked_pos = feedback_context.get("avg_liked_pos")

        for cand in candidates:
            bias = 0.0

            # Hook-type bias
            ht = cand.get("hook_intelligence_type") or cand.get("_hook_type") or "none"
            ht_net = float(hook_net.get(ht, 0.0))
            if abs(ht_net) >= _MIN_NET_SCORE:
                ht_bias = min(_MAX_BIAS, abs(ht_net) * 0.8) * (1 if ht_net > 0 else -1)
                bias += ht_bias

            # Clip-type bias
            ct = cand.get("clip_type") or "unknown"
            ct_net = float(clip_type_net.get(ct, 0.0))
            if ct != "unknown" and abs(ct_net) >= _MIN_NET_SCORE:
                ct_bias = min(_MAX_BIAS * 0.5, abs(ct_net) * 0.5) * (1 if ct_net > 0 else -1)
                bias += ct_bias

            # Position bias: mild bonus when candidate starts near the liked-position centroid
            if avg_liked_pos is not None:
                pos_ratio = cand.get("_position_ratio")
                if pos_ratio is not None:
                    dist = abs(float(pos_ratio) - avg_liked_pos)
                    if dist <= _POSITION_WINDOW:
                        position_bonus = (1.0 - dist / _POSITION_WINDOW) * 1.5
                        bias += position_bonus

            if abs(bias) < 0.01:
                continue

            cand["score"] = round(max(0.0, min(100.0, cand["score"] + bias)), 2)
            reason = cand.get("reason", "ai_scored")
            tag = "feedback_boost" if bias > 0 else "feedback_penalty"
            cand["reason"] = f"{reason}, {tag}" if reason else tag

        candidates.sort(key=lambda x: float(x.get("score", 0.0)), reverse=True)
    except Exception as exc:
        logger.debug("apply_feedback_bias failed: %s", exc)

    return candidates
