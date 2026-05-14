"""
segment_promotion_engine.py — Phase 59C Segment Selection Promotion.

Promotes AI-selected segments (from edit_plan.selected_segments) into the
actual render segment order. This is the first AI execution promotion that
affects WHICH clips are rendered and in WHAT ORDER.

Promoted behavior:
    scored list — reordered to put AI-endorsed segments first (by AI score)

Advisory only (no new timestamps, no new segments):
    The existing `scored` list is reordered using overlap-matching against
    AI selected_segments. No new segment dicts are created. No timestamps
    are modified. Non-AI-endorsed segments are preserved at the end.

Design rules:
  - Never raises — returns original scored + fallback report on any error.
  - ai_director_enabled + ai_render_influence_enabled both required.
  - segment_ai_lock on payload blocks all promotion.
  - All AI segments validated before use (start >= 0, end > start, no NaN).
  - Overlap-based matching: AI segment must overlap scored segment by >= threshold.
  - Confidence: mean normalized AI segment score >= _CONF_THRESHOLD_PROMOTION.
  - Reorder only — never reduces final list below _MIN_FINAL_SEGMENTS.
  - Never generates new timestamps.
  - Never modifies individual scored segment dicts.
  - Deterministic: same inputs → same output.
  - Executor remains final authority.

Public API:
    promote_segment_selection(scored, edit_plan, payload, context=None)
        -> tuple[list, dict]

    scored:    list of dicts from score_segments() — must be returned intact.
    edit_plan: AIEditPlan (or duck-typed object/dict) with selected_segments.
    payload:   RenderRequest-compatible object for gate checks.
    context:   Optional dict with "job_id" for logging.

Promotion report shape:
    {
        "segment_selection_promotion": {
            "applied": true,
            "selected_count": 3,
            "total_count": 5,
            "source": "ai_selected_segments",
            "confidence": 0.84,
            "reasoning": ["AI selected high-score segments moved to front"],
            "fallback_used": false
        }
    }

Fallback shape:
    {
        "segment_selection_promotion": {
            "applied": false,
            "selected_count": 0,
            "total_count": N,
            "source": "default_segment_builder",
            "confidence": 0.0,
            "reason": "not_eligible",
            "reasoning": [],
            "fallback_used": true
        }
    }

Safety contract:
    ❌ No new timestamp generation
    ❌ No segment dict mutation
    ❌ No ffmpeg mutation
    ❌ No subtitle timing rewrite
    ❌ No ASS generation rewrite
    ❌ No motion_crop rewrite
    ❌ No playback_speed mutation
    ❌ No executor override
    ✅ Reorder only — existing segments preserved intact
    ✅ Overlap-validated matching only
    ✅ Confidence gate enforced before any reorder
    ✅ Original scored list returned unchanged on any gate failure
    ✅ Final list never shorter than _MIN_FINAL_SEGMENTS
    ✅ Deterministic: same inputs → same output
    ✅ Never raises
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

logger = logging.getLogger("app.ai.segment_promotion")

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# Minimum mean normalized AI segment confidence to trigger promotion
_CONF_THRESHOLD_PROMOTION: float = 0.80

# Minimum seconds of overlap for an AI segment to endorse a scored segment
_MIN_OVERLAP_SECONDS: float = 1.0

# Minimum overlap as a fraction of the scored segment's duration
_MIN_OVERLAP_RATIO: float = 0.05

# Never reduce the final segment list below this count
_MIN_FINAL_SEGMENTS: int = 1

# Cap on AI selected segments processed (safety bound)
_MAX_AI_SEGMENTS: int = 100

# Max reasoning lines in the promotion report
_MAX_REASONING: int = 6


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def promote_segment_selection(
    scored: list,
    edit_plan: Any,
    payload: Any,
    context: Optional[dict] = None,
) -> tuple[list, dict]:
    """Promote AI-selected segments into the render segment order.

    Reorders the `scored` list to put AI-endorsed segments first.
    Returns (reordered_scored, promotion_report).

    Args:
        scored:    List of segment dicts from score_segments(). Keys include
                   start, end, duration, viral_score, motion_score, hook_score.
        edit_plan: AIEditPlan (or duck-typed) with selected_segments attribute.
        payload:   RenderRequest-compatible object for gate checks.
        context:   Optional dict with "job_id" for logging.

    Returns:
        (scored, {"segment_selection_promotion": {...}})
        The first element is always a list safe to iterate for rendering.
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        total = len(scored) if isinstance(scored, list) else 0
    except Exception:
        total = 0
    try:
        result_scored, report = _promote(scored, edit_plan, payload, job_id, total)
        return result_scored, report
    except Exception as exc:
        logger.warning(
            "segment_promotion_unexpected_error job_id=%s: %s", job_id, exc
        )
        safe_scored = list(scored) if isinstance(scored, list) else []
        return safe_scored, _fallback_report("promotion_error", total=total)


# ---------------------------------------------------------------------------
# Core promotion
# ---------------------------------------------------------------------------

def _promote(
    scored: list,
    edit_plan: Any,
    payload: Any,
    job_id: str,
    total: int,
) -> tuple[list, dict]:
    """Core logic. May raise — caller wraps in try/except."""

    # ── Gate 1: safety list ────────────────────────────────────────────────
    if not isinstance(scored, list) or not scored:
        return [], _fallback_report("empty_scored_list", total=0)

    # ── Gate 2: AI flags ───────────────────────────────────────────────────
    if not bool(getattr(payload, "ai_director_enabled", False)):
        return list(scored), _fallback_report("ai_director_disabled", total=total)

    if not bool(getattr(payload, "ai_render_influence_enabled", False)):
        return list(scored), _fallback_report("ai_render_influence_disabled", total=total)

    # ── Gate 3: explicit user override ────────────────────────────────────
    if bool(getattr(payload, "segment_ai_lock", False)):
        logger.debug("segment_promotion_skipped job_id=%s reason=segment_ai_lock", job_id)
        return list(scored), _fallback_report("user_override", note="segment_ai_lock=true", total=total)

    if edit_plan is None:
        return list(scored), _fallback_report("no_edit_plan", total=total)

    # ── Gate 4: selected_segments exist ───────────────────────────────────
    raw_segs = _get_selected_segments(edit_plan)
    if not raw_segs:
        return list(scored), _fallback_report("no_selected_segments", total=total)

    # ── Validate AI segments ───────────────────────────────────────────────
    valid_ai = []
    for seg in raw_segs[:_MAX_AI_SEGMENTS]:
        if _validate_ai_segment(seg):
            valid_ai.append(seg)

    if not valid_ai:
        return list(scored), _fallback_report("no_valid_ai_segments", total=total)

    # ── Confidence gate ────────────────────────────────────────────────────
    scores_norm = [_normalize_score(_get_seg_attr(s, "score", 50.0)) for s in valid_ai]
    mean_conf = sum(scores_norm) / len(scores_norm)

    if mean_conf < _CONF_THRESHOLD_PROMOTION:
        logger.debug(
            "segment_promotion_skipped job_id=%s reason=low_confidence conf=%.3f",
            job_id, mean_conf,
        )
        return list(scored), _fallback_report(
            "low_confidence", confidence=mean_conf, total=total
        )

    # ── Overlap matching ───────────────────────────────────────────────────
    endorsed_with_score: list[tuple[dict, float]] = []
    non_endorsed: list[dict] = []

    for sc_seg in scored:
        best_ai_score = _best_endorsement_score(sc_seg, valid_ai)
        if best_ai_score > 0.0:
            endorsed_with_score.append((sc_seg, best_ai_score))
        else:
            non_endorsed.append(sc_seg)

    if not endorsed_with_score:
        logger.debug(
            "segment_promotion_skipped job_id=%s reason=no_overlap_found ai_segs=%d",
            job_id, len(valid_ai),
        )
        return list(scored), _fallback_report(
            "no_overlap_found", confidence=mean_conf, total=total
        )

    # ── Build promoted order ───────────────────────────────────────────────
    # Sort endorsed by AI score desc (stable within equal scores → original order)
    endorsed_with_score.sort(key=lambda x: x[1], reverse=True)
    endorsed = [seg for seg, _ in endorsed_with_score]

    # Safety: never reduce below _MIN_FINAL_SEGMENTS
    result = endorsed + non_endorsed
    if len(result) < _MIN_FINAL_SEGMENTS:
        result = list(scored)
        return result, _fallback_report("safety_min_segments", confidence=mean_conf, total=total)

    logger.info(
        "segment_promotion_applied job_id=%s endorsed=%d non_endorsed=%d total=%d conf=%.3f",
        job_id, len(endorsed), len(non_endorsed), len(result), mean_conf,
    )

    reasoning = [
        f"AI endorsed {len(endorsed)}/{total} segments (mean_conf={mean_conf:.3f})",
    ]
    if non_endorsed:
        reasoning.append(
            f"{len(non_endorsed)} non-endorsed segment(s) preserved at end"
        )
    if len(endorsed) < total:
        reasoning.append("Reorder only — no segments dropped")

    return result, {
        "segment_selection_promotion": {
            "applied":        True,
            "selected_count": len(endorsed),
            "total_count":    len(result),
            "source":         "ai_selected_segments",
            "confidence":     round(mean_conf, 4),
            "reason":         "promotion_applied",
            "reasoning":      reasoning[:_MAX_REASONING],
            "fallback_used":  False,
        }
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_selected_segments(edit_plan: Any) -> list:
    """Duck-typed selected_segments access. Never raises."""
    try:
        if isinstance(edit_plan, dict):
            return list(edit_plan.get("selected_segments") or [])
        segs = getattr(edit_plan, "selected_segments", None)
        return list(segs) if segs else []
    except Exception:
        return []


def _validate_ai_segment(seg: Any) -> bool:
    """Return True if the AI segment has valid, safe time boundaries."""
    try:
        start = float(_get_seg_attr(seg, "start", None) or 0.0)
        end   = float(_get_seg_attr(seg, "end", None) or 0.0)
        if math.isnan(start) or math.isnan(end):
            return False
        if math.isinf(start) or math.isinf(end):
            return False
        return start >= 0.0 and end > start
    except (TypeError, ValueError):
        return False


def _best_endorsement_score(scored_seg: dict, valid_ai: list) -> float:
    """Return the highest AI score among AI segments that overlap scored_seg.

    Returns 0.0 if no valid endorsement found.
    """
    sc_start = float(scored_seg.get("start") or 0.0)
    sc_end   = float(scored_seg.get("end") or 0.0)
    sc_dur   = float(scored_seg.get("duration") or max(0.0, sc_end - sc_start))

    best = 0.0
    for ai_seg in valid_ai:
        ai_start = float(_get_seg_attr(ai_seg, "start", 0.0) or 0.0)
        ai_end   = float(_get_seg_attr(ai_seg, "end", 0.0) or 0.0)

        overlap = max(0.0, min(ai_end, sc_end) - max(ai_start, sc_start))
        if overlap < _MIN_OVERLAP_SECONDS:
            continue
        # Also require minimum fractional overlap to avoid noise
        if sc_dur > 0 and (overlap / sc_dur) < _MIN_OVERLAP_RATIO:
            continue

        ai_score_norm = _normalize_score(_get_seg_attr(ai_seg, "score", 50.0))
        if ai_score_norm > best:
            best = ai_score_norm

    return best


def _get_seg_attr(seg: Any, attr: str, default: Any) -> Any:
    """Duck-typed attribute access for both dicts and dataclass objects."""
    try:
        if isinstance(seg, dict):
            return seg.get(attr, default)
        return getattr(seg, attr, default)
    except Exception:
        return default


def _normalize_score(score: Any) -> float:
    """Normalize a segment score to [0, 1].

    Handles both 0-100 scale (AIClipPlan default 50.0) and 0-1 scale.
    Values > 1.0 are treated as 0-100 and divided by 100.
    """
    try:
        s = float(score or 0.0)
        if s > 1.0:
            return min(1.0, s / 100.0)
        return max(0.0, min(1.0, s))
    except (TypeError, ValueError):
        return 0.0


def _fallback_report(
    reason: str,
    note: str = "",
    confidence: float = 0.0,
    total: int = 0,
) -> dict:
    full_reason = f"{reason}:{note}" if note else reason
    return {
        "segment_selection_promotion": {
            "applied":        False,
            "selected_count": 0,
            "total_count":    total,
            "source":         "default_segment_builder",
            "confidence":     round(confidence, 4),
            "reason":         full_reason,
            "reasoning":      [],
            "fallback_used":  True,
        }
    }
