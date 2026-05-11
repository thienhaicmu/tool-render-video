"""
strategy_planner.py — Unified render strategy planner. Phase 47.

Produces a recommendation-only render strategy from aggregated signals
and conflict-resolution results.

Rules:
- Recommendation ONLY — never applied to render execution
- Deterministic output for identical inputs
- Conservative fallback when aggregate confidence < 0.30
- No FFmpeg mutation, no playback_speed, no subtitle_timing
- No executor interaction
- Never raises
"""
from __future__ import annotations

import logging
from collections import Counter

logger = logging.getLogger("app.ai.orchestrator.strategy_planner")

# Deterministic maps: raw style value → canonical strategy value
_SUBTITLE_DENSITY: dict[str, str] = {
    "compact":          "high",
    "readable":         "medium",
    "clean_readable":   "medium",
    "medium_density":   "medium",
    "clean_pro":        "medium",
    "minimal":          "low",
    "default":          "medium",
    "":                 "medium",
}

_CAMERA_MOTION: dict[str, str] = {
    "dynamic_safe":     "dynamic_subject",
    "creator_framing":  "smooth_subject",
    "social_framing":   "smooth_social",
    "static_podcast":   "static",
    "static_framing":   "static",
    "cinematic_smooth": "cinematic",
    "default":          "smooth_subject",
    "":                 "smooth_subject",
}

_CLIP_BIAS: dict[str, str] = {
    "fast_hook":            "retention",
    "medium_fast":          "retention",
    "calm_storytelling":    "story",
    "clarity_first":        "story",
    "smooth_engagement":    "retention",
    "default":              "retention",
    "":                     "retention",
}

_RANKING_PRIORITY: dict[str, str] = {
    "creator_preference":     "creator_fit",
    "feedback_preference":    "creator_fit",
    "preset_recommendation":  "preset_fit",
    "market_preference":      "market_fit",
    "retrieval_recommendation": "creator_fit",
    "quality_evaluation":     "quality",
    "conservative_default":   "creator_fit",
}

# Aggregate confidence below this threshold → conservative defaults only
_CONSERVATIVE_THRESHOLD = 0.30


def plan_render_strategy(
    aggregated_signals: dict,
    confidence_scores: dict,
    resolved_conflicts: dict,
) -> dict:
    """Produce a recommendation-only render strategy.

    Args:
        aggregated_signals: From signal_aggregation.aggregate_signals()
        confidence_scores:  From confidence_engine.compute_signal_confidence()
        resolved_conflicts: From conflict_resolver.resolve_conflicts()

    Returns:
        {
            "recommended_strategy": {
                "subtitle_style":      str,
                "subtitle_density":    str,
                "camera_motion":       str,
                "hook_emphasis":       str,
                "clip_selection_bias": str,
                "ranking_priority":    str,
            },
            "strategy_confidence": float,
            "strategy_mode": "recommendation_only",
        }
    """
    try:
        return _plan(aggregated_signals, confidence_scores, resolved_conflicts)
    except Exception as exc:
        logger.debug("strategy_planner_error: %s", exc)
        return _conservative_strategy(confidence=0.0, note="planner_error")


def _plan(signals: dict, confidence: dict, conflicts: dict) -> dict:
    agg_conf = float(confidence.get("aggregate_confidence") or 0.0)

    # Subtitle style from conflict resolution, fall back to preset then default
    sub_res = conflicts.get("subtitle_style") or {}
    subtitle_style = str(sub_res.get("value") or "")
    if not subtitle_style:
        preset = signals.get("preset_signal") or {}
        subtitle_style = str(preset.get("best_subtitle_style") or "default")

    subtitle_density = _SUBTITLE_DENSITY.get(subtitle_style, "medium")

    # Camera motion from conflict resolution
    cam_res = conflicts.get("camera_style") or {}
    camera_raw = str(cam_res.get("value") or "")
    camera_motion = _CAMERA_MOTION.get(camera_raw, "smooth_subject")

    # Hook emphasis from conflict resolution
    hook_res = conflicts.get("hook_emphasis") or {}
    hook_emphasis = str(hook_res.get("value") or "default")

    # Clip selection bias from pacing conflict resolution
    pac_res = conflicts.get("pacing_style") or {}
    pacing_val = str(pac_res.get("value") or "")
    clip_selection_bias = _CLIP_BIAS.get(pacing_val, "retention")

    # Ranking priority from dominant winning signal source
    dominant_winner = _dominant_winner(conflicts)
    ranking_priority = _RANKING_PRIORITY.get(dominant_winner, "creator_fit")

    # Conservative guard: low confidence → safe defaults
    if agg_conf < _CONSERVATIVE_THRESHOLD:
        return _conservative_strategy(
            confidence=agg_conf,
            note="conservative_low_confidence_fallback",
            subtitle_style=subtitle_style or "default",
        )

    return {
        "recommended_strategy": {
            "subtitle_style":      subtitle_style or "default",
            "subtitle_density":    subtitle_density,
            "camera_motion":       camera_motion,
            "hook_emphasis":       hook_emphasis,
            "clip_selection_bias": clip_selection_bias,
            "ranking_priority":    ranking_priority,
        },
        "strategy_confidence": round(agg_conf, 4),
        "strategy_mode": "recommendation_only",
    }


def _dominant_winner(conflicts: dict) -> str:
    """Most common winning signal source across resolved dimensions."""
    winners = [
        str((conflicts.get(dim) or {}).get("winner") or "")
        for dim in ("subtitle_style", "pacing_style", "camera_style", "hook_emphasis")
    ]
    non_empty = [w for w in winners if w]
    if not non_empty:
        return "conservative_default"
    return Counter(non_empty).most_common(1)[0][0]


def _conservative_strategy(
    confidence: float = 0.0,
    note: str = "",
    subtitle_style: str = "default",
) -> dict:
    result: dict = {
        "recommended_strategy": {
            "subtitle_style":      subtitle_style,
            "subtitle_density":    "medium",
            "camera_motion":       "smooth_subject",
            "hook_emphasis":       "default",
            "clip_selection_bias": "retention",
            "ranking_priority":    "creator_fit",
        },
        "strategy_confidence": round(float(confidence), 4),
        "strategy_mode": "recommendation_only",
    }
    if note:
        result["strategy_note"] = note
    return result
