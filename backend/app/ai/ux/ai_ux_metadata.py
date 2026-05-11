"""
ai_ux_metadata.py — Stable UI-safe AI UX metadata contract. Phase 49A.

Consumes Phase 47 (orchestration) and Phase 48 (influence) outputs and
produces a compact, UI-safe ``ai_ux`` dict that the frontend can render
without knowing internal AI subsystem shapes.

Public API:
    build_ai_ux_metadata(edit_plan, output_ranking=None) -> dict

Design rules:
- Metadata contract only — no render mutation, no executor override
- Deterministic: identical inputs produce identical outputs
- Fallback-safe: never raises, returns {"available": False} on any failure
- UI-safe: no raw debug JSON, no stack traces, no internal class names
- Additive only: does not modify or remove any existing result fields
- Confidence clamped [0.0, 1.0], rounded to 2 decimal places
- All list outputs bounded by _MAX_ITEMS

Safety contract:
    ❌ No FFmpeg mutation
    ❌ No render rewrite
    ❌ No playback_speed mutation
    ❌ No subtitle timing rewrite
    ❌ No rerender
    ❌ No executor override
    ❌ No autonomous execution
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.ux.ai_ux_metadata")

# Maximum list lengths exposed to UI (prevents flooding the frontend)
_MAX_RECOMMENDATIONS = 5
_MAX_WHY = 5
_MAX_INFLUENCE_ITEMS = 5

# Strings that look like internal debug output — filter from UI-exposed lists
_DEBUG_PREFIXES = (
    "error:",
    "unavailable",
    "explainability_unavailable",
    "fallback",
    "conservative_default",
)

# Human-readable labels for Phase 47 recommended_strategy fields
_SUBTITLE_STYLE_LABELS: dict[str, str] = {
    "compact":        "Compact subtitle style",
    "readable":       "Clean readable subtitles",
    "clean_readable": "Clean readable subtitles",
    "medium_density": "Medium-density subtitles",
    "clean_pro":      "Professional clean subtitles",
    "minimal":        "Minimal subtitle style",
}

_PACING_LABELS: dict[str, str] = {
    "energetic":  "High-energy pacing",
    "balanced":   "Balanced pacing",
    "slow":       "Calm measured pacing",
    "dynamic":    "Dynamic pacing",
    "relaxed":    "Relaxed pacing",
    "fast":       "Fast-cut pacing",
}

_CAMERA_LABELS: dict[str, str] = {
    "dynamic_subject": "Dynamic subject tracking",
    "smooth_subject":  "Smooth subject tracking",
    "smooth_social":   "Smooth social-optimized motion",
    "static":          "Static camera framing",
    "cinematic":       "Cinematic camera movement",
}

_HOOK_LABELS: dict[str, str] = {
    "strong":   "Strong hook emphasis",
    "moderate": "Moderate hook emphasis",
}

_RANKING_LABELS: dict[str, str] = {
    "retention":   "Retention-focused clip ranking",
    "creator_fit": "Creator-style aligned ranking",
    "market_fit":  "Market-optimized clip ranking",
    "preset_fit":  "Preset-matched clip ranking",
    "quality":     "Quality-first clip ranking",
}

# Human-readable labels for Phase 48 safe_influence fields
_SUBTITLE_STYLE_BIAS_LABELS: dict[str, str] = {
    "viral_bold":    "Bold viral subtitle style applied",
    "clean_pro":     "Cleaner subtitle style applied",
    "boxed_caption": "Structured caption box style applied",
}

_SUBTITLE_DENSITY_BIAS_LABELS: dict[str, str] = {
    "lighter": "Lighter subtitle density recommended",
}

_CAMERA_BIAS_LABELS: dict[str, str] = {
    "smooth_subject": "Smoother subject tracking bias",
    "smooth_social":  "Smoother social motion bias",
    "cinematic":      "Cinematic smoothing bias",
    "static":         "Static stabilization bias",
}

_RANKING_BIAS_LABELS: dict[str, str] = {
    "retention":   "Retention-boosted clip ranking",
    "creator_fit": "Creator-fit boosted ranking",
    "market_fit":  "Market-fit boosted ranking",
    "preset_fit":  "Preset-fit boosted ranking",
    "quality":     "Quality-score boosted ranking",
}


def build_ai_ux_metadata(
    edit_plan: Any,
    output_ranking: Optional[dict] = None,
) -> dict:
    """Build UI-safe AI UX metadata from Phase 47/48 outputs.

    Args:
        edit_plan:      AIEditPlan (or None) with Phase 47/48 fields populated.
        output_ranking: Phase 30 output ranking dict (or None).

    Returns:
        {
            "available": bool,
            "strategy": {
                "title": str,
                "creator_style": str,
                "target_market": str,
                "confidence": float,
                "recommendations": [str, ...],
                "why": [str, ...]
            },
            "safe_influence": {
                "applied": bool,
                "items": [str, ...]
            },
            "best_export": {
                "enabled": bool,
                "why": [str, ...]
            }
        }
        or {"available": False} on missing/failed data.
    """
    try:
        return _build(edit_plan, output_ranking or {})
    except Exception as exc:
        logger.debug("ai_ux_metadata_error: %s", exc)
        return {"available": False}


def _build(edit_plan: Any, output_ranking: dict) -> dict:
    # Require a valid edit plan with Phase 47 orchestration output
    mso = _get_dict(edit_plan, "multi_signal_orchestration")
    if not mso or not mso.get("available"):
        return {"available": False}

    confidence_scores = mso.get("confidence_scores") or {}
    agg_conf = _clamp_confidence(confidence_scores.get("aggregate_confidence"))

    if agg_conf == 0.0 and not mso.get("enabled"):
        return {"available": False}

    strategy = _build_strategy(edit_plan, mso, agg_conf)
    safe_influence = _build_safe_influence(edit_plan)
    best_export = _build_best_export(edit_plan, output_ranking, safe_influence)

    return {
        "available": True,
        "strategy": strategy,
        "safe_influence": safe_influence,
        "best_export": best_export,
    }


def _build_strategy(edit_plan: Any, mso: dict, agg_conf: float) -> dict:
    rec = mso.get("recommended_strategy") or {}
    explainability = mso.get("explainability") or {}
    aggregated = mso.get("aggregated_signals") or {}

    creator_style = _extract_creator_style(edit_plan)
    target_market = _extract_target_market(aggregated)
    recommendations = _build_recommendations(rec)
    why = _build_why(explainability)

    return {
        "title": "AI Strategy",
        "creator_style": creator_style,
        "target_market": target_market,
        "confidence": agg_conf,
        "recommendations": recommendations,
        "why": why,
    }


def _build_recommendations(rec: dict) -> list[str]:
    items: list[str] = []

    subtitle_style = str(rec.get("subtitle_style") or "")
    pacing_style = str(rec.get("pacing_style") or "")
    camera_motion = str(rec.get("camera_motion") or "")
    hook_emphasis = str(rec.get("hook_emphasis") or "")
    ranking_priority = str(rec.get("ranking_priority") or "")

    if subtitle_style in _SUBTITLE_STYLE_LABELS:
        items.append(_SUBTITLE_STYLE_LABELS[subtitle_style])
    if pacing_style in _PACING_LABELS:
        items.append(_PACING_LABELS[pacing_style])
    if camera_motion in _CAMERA_LABELS:
        items.append(_CAMERA_LABELS[camera_motion])
    if hook_emphasis in _HOOK_LABELS:
        items.append(_HOOK_LABELS[hook_emphasis])
    if ranking_priority in _RANKING_LABELS:
        items.append(_RANKING_LABELS[ranking_priority])

    return items[:_MAX_RECOMMENDATIONS]


def _build_why(explainability: dict) -> list[str]:
    raw: list = explainability.get("why_this_strategy") or []
    cleaned = [
        str(s) for s in raw
        if isinstance(s, str)
        and s
        and not any(s.lower().startswith(p) for p in _DEBUG_PREFIXES)
    ]
    return cleaned[:_MAX_WHY]


def _build_safe_influence(edit_plan: Any) -> dict:
    sip = _get_dict(edit_plan, "safe_influence_pack")
    applied = bool(sip.get("enabled")) if sip else False

    items: list[str] = []
    if applied:
        si = sip.get("safe_influence") or {}

        style_bias = str(si.get("subtitle_style_bias") or "")
        if style_bias in _SUBTITLE_STYLE_BIAS_LABELS:
            items.append(_SUBTITLE_STYLE_BIAS_LABELS[style_bias])

        density_bias = str(si.get("subtitle_density_bias") or "")
        if density_bias in _SUBTITLE_DENSITY_BIAS_LABELS:
            items.append(_SUBTITLE_DENSITY_BIAS_LABELS[density_bias])

        camera_bias = str(si.get("camera_motion_bias") or "")
        if camera_bias in _CAMERA_BIAS_LABELS:
            items.append(_CAMERA_BIAS_LABELS[camera_bias])

        ranking_bias = str(si.get("ranking_priority_bias") or "")
        if ranking_bias in _RANKING_BIAS_LABELS:
            items.append(_RANKING_BIAS_LABELS[ranking_bias])

    return {
        "applied": applied,
        "items": items[:_MAX_INFLUENCE_ITEMS],
    }


def _build_best_export(
    edit_plan: Any,
    output_ranking: dict,
    safe_influence: dict,
) -> dict:
    best_id = str(output_ranking.get("best_output_id") or "")
    enabled = bool(output_ranking.get("available") and best_id)

    why: list[str] = []
    if enabled:
        # Derive simple factual why-strings from available ranking context
        sip = _get_dict(edit_plan, "safe_influence_pack")
        gate_tier = str(((sip.get("gate") or {}).get("tier")) or "") if sip else ""
        ranking_bias = str(
            ((sip.get("safe_influence") or {}).get("ranking_priority_bias")) or ""
        ) if sip else ""

        if ranking_bias == "retention":
            why.append("Retention-optimized clip selected as best export")
        elif ranking_bias == "creator_fit":
            why.append("Creator-style aligned clip selected as best export")
        elif ranking_bias == "quality":
            why.append("Highest quality-score clip selected as best export")
        elif ranking_bias:
            why.append(f"AI-ranked best export ({ranking_bias} priority)")

        if gate_tier == "strong":
            why.append("High AI confidence in selection")
        elif gate_tier == "soft":
            why.append("Moderate AI confidence in selection")

        if not why:
            why.append("Best output ranked by AI scoring")

    return {
        "enabled": enabled,
        "why": why[:_MAX_WHY],
    }


def _extract_creator_style(edit_plan: Any) -> str:
    # Try creator_style field (Phase 14)
    cs = _get_dict(edit_plan, "creator_style")
    label = str(cs.get("style_label") or cs.get("creator_style") or "")
    if label:
        return label

    # Try creator_style_adaptation (Phase 23)
    csa = _get_dict(edit_plan, "creator_style_adaptation")
    adapted = str(csa.get("adapted_style") or "")
    if adapted:
        return adapted

    return ""


def _extract_target_market(aggregated_signals: dict) -> str:
    market = aggregated_signals.get("market_signal") or {}
    return str(market.get("target_market") or "").upper()


def _clamp_confidence(raw: Any) -> float:
    try:
        v = float(raw or 0.0)
        return round(max(0.0, min(1.0, v)), 2)
    except (TypeError, ValueError):
        return 0.0


def _get_dict(edit_plan: Any, attr: str) -> dict:
    try:
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}
