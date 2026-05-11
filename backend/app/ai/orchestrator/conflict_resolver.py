"""
conflict_resolver.py — Deterministic multi-signal conflict resolver. Phase 47.

Resolves conflicts between competing AI signal recommendations.
Uses confidence weighting with conservative-first tie-breaking.

Rules:
- Deterministic — same inputs always produce same outputs
- Explainable — every decision includes a reason string
- Confidence-weighted — higher confidence wins on close calls
- Conservative-first — creator/feedback preference wins on tie
- Fallback-safe — never raises, always returns a valid dict
- No render mutation, no FFmpeg, no executor override
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.orchestrator.conflict_resolver")

# Conservative precedence order — creator signal is highest priority on ties
_PRIORITY_ORDER = [
    "creator_preference",
    "feedback_preference",
    "preset_recommendation",
    "market_preference",
    "retrieval_recommendation",
    "quality_evaluation",
    "conservative_default",
]

# Minimum confidence delta for a lower-priority signal to override a higher-priority one
_OVERRIDE_THRESHOLD = 0.25


def resolve_conflicts(
    aggregated_signals: dict,
    confidence_scores: dict,
) -> dict:
    """Resolve conflicts between competing signal recommendations.

    Args:
        aggregated_signals: Output of signal_aggregation.aggregate_signals()
        confidence_scores:  Output of confidence_engine.compute_signal_confidence()

    Returns:
        {
            "subtitle_style":  {"winner": str, "value": str, "reason": str},
            "pacing_style":    {"winner": str, "value": str, "reason": str},
            "camera_style":    {"winner": str, "value": str, "reason": str},
            "hook_emphasis":   {"winner": str, "value": str, "reason": str},
            "conflict_count":  int,
            "resolution_mode": "deterministic",
        }
    """
    try:
        return _resolve(aggregated_signals, confidence_scores)
    except Exception as exc:
        logger.debug("conflict_resolver_error: %s", exc)
        return _safe_fallback()


def _resolve(signals: dict, confidence: dict) -> dict:
    creator = signals.get("creator_signal") or {}
    market = signals.get("market_signal") or {}
    preset = signals.get("preset_signal") or {}
    feedback = signals.get("feedback_signal") or {}

    creator_conf = float(confidence.get("creator_confidence") or 0.0)
    market_conf = float(confidence.get("market_confidence") or 0.0)
    preset_conf = float(confidence.get("preset_confidence") or 0.0)
    feedback_conf = float(confidence.get("feedback_confidence") or 0.0)

    conflict_count = 0

    # --- Subtitle style resolution ---
    creator_subtitle = str(creator.get("adapted_style") or "")
    feedback_subtitle = str(feedback.get("dominant_subtitle_style") or "")
    preset_subtitle = str(preset.get("best_subtitle_style") or "")
    market_subtitle = _pull_style(market.get("subtitle_bias") or {})

    sub_winner, sub_value, sub_reason = _pick_winner([
        ("creator_preference", creator_subtitle, creator_conf),
        ("feedback_preference", feedback_subtitle, feedback_conf),
        ("preset_recommendation", preset_subtitle, preset_conf),
        ("market_preference", market_subtitle, market_conf),
    ], dimension="subtitle_style")

    if _has_conflict([creator_subtitle, feedback_subtitle, preset_subtitle, market_subtitle]):
        conflict_count += 1

    # --- Pacing style resolution ---
    feedback_pacing = str(feedback.get("dominant_pacing_style") or "")
    preset_pacing = str(preset.get("best_pacing_style") or "")
    market_pacing = _pull_style(market.get("pacing_bias") or {})

    pac_winner, pac_value, pac_reason = _pick_winner([
        ("feedback_preference", feedback_pacing, feedback_conf),
        ("preset_recommendation", preset_pacing, preset_conf),
        ("market_preference", market_pacing, market_conf),
    ], dimension="pacing_style")

    if _has_conflict([feedback_pacing, preset_pacing, market_pacing]):
        conflict_count += 1

    # --- Camera style resolution ---
    preset_camera = str(preset.get("best_camera_style") or "")
    market_camera = _pull_style(market.get("camera_bias") or {})

    cam_winner, cam_value, cam_reason = _pick_winner([
        ("preset_recommendation", preset_camera, preset_conf),
        ("market_preference", market_camera, market_conf),
    ], dimension="camera_style")

    if _has_conflict([preset_camera, market_camera]):
        conflict_count += 1

    # --- Hook emphasis (derived from market hook bias weight) ---
    hook_weight = float((market.get("hook_bias") or {}).get("weight") or 0.0)
    if hook_weight >= 0.20:
        hook_value = "strong"
        hook_winner = "market_preference"
    elif hook_weight >= 0.10:
        hook_value = "moderate"
        hook_winner = "market_preference"
    else:
        hook_value = "default"
        hook_winner = "conservative_default"
    hook_reason = f"market_hook_bias_weight={round(hook_weight, 3)}"

    return {
        "subtitle_style": {"winner": sub_winner, "value": sub_value, "reason": sub_reason},
        "pacing_style":   {"winner": pac_winner, "value": pac_value, "reason": pac_reason},
        "camera_style":   {"winner": cam_winner, "value": cam_value, "reason": cam_reason},
        "hook_emphasis":  {"winner": hook_winner, "value": hook_value, "reason": hook_reason},
        "conflict_count": conflict_count,
        "resolution_mode": "deterministic",
    }


def _pick_winner(
    candidates: list[tuple[str, str, float]],
    dimension: str,
) -> tuple[str, str, str]:
    """Select the winning signal for a single style dimension.

    Args:
        candidates: [(source_name, value, confidence), ...]
        dimension:  Name of the dimension being resolved (for reason string)

    Returns:
        (winner_name, value, reason)
    """
    valid = [(name, val, conf) for name, val, conf in candidates if val.strip()]

    if not valid:
        return ("conservative_default", "", f"no_signal_for_{dimension}")

    if len(valid) == 1:
        name, val, conf = valid[0]
        return (name, val, f"only_signal conf={round(conf, 3)}")

    # Priority candidate (lowest priority-order index)
    prio_cand = min(valid, key=lambda x: (_prio(x[0]), -x[2]))
    prio_name, prio_val, prio_conf = prio_cand

    # Highest confidence candidate
    best_cand = max(valid, key=lambda x: (x[2], -_prio(x[0])))
    best_name, best_val, best_conf = best_cand

    # Override priority only when confidence delta exceeds threshold
    if best_name != prio_name and (best_conf - prio_conf) >= _OVERRIDE_THRESHOLD:
        return (
            best_name,
            best_val,
            f"confidence_dominant conf={round(best_conf, 3)} "
            f"delta={round(best_conf - prio_conf, 3)}",
        )

    return (
        prio_name,
        prio_val,
        f"priority_preferred conf={round(prio_conf, 3)}",
    )


def _prio(name: str) -> int:
    try:
        return _PRIORITY_ORDER.index(name)
    except ValueError:
        return len(_PRIORITY_ORDER)


def _pull_style(bias_dict: dict) -> str:
    """Extract a style hint from a market bias dict."""
    try:
        return str(bias_dict.get("style") or bias_dict.get("preferred_style") or "")
    except Exception:
        return ""


def _has_conflict(values: list[str]) -> bool:
    """True when multiple distinct non-empty values are present."""
    non_empty = [v for v in values if v.strip()]
    return len(set(non_empty)) > 1


def _safe_fallback() -> dict:
    _default = {"winner": "conservative_default", "value": "", "reason": "resolution_error"}
    return {
        "subtitle_style":  dict(_default),
        "pacing_style":    dict(_default),
        "camera_style":    dict(_default),
        "hook_emphasis":   {"winner": "conservative_default", "value": "default", "reason": "resolution_error"},
        "conflict_count":  0,
        "resolution_mode": "deterministic",
    }
