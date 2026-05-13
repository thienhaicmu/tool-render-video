"""
platform_strategy_influence_context.py — Phase 56 Platform-Aware Strategy Influence.

Reads Phase 55E platform_render_strategy and builds per-domain influence
support metadata with bounded confidence deltas and creator-facing reasoning.

This module produces advisory metadata that downstream influence engines can
use to enrich their reasoning. It NEVER:
  - modifies the Phase 48 safety gate evaluation
  - lowers safety thresholds or unblocks blocked influence
  - touches FFmpeg, subtitle timing, motion_crop, or clip boundaries
  - overrides executor authority or mutates render pipeline

Confidence delta bounds (strictly enforced — same contract as Phase 54):
  - max per domain:   0.05
  - max total boost:  0.10
  - final confidence: clamped [0.0, 1.0]

Public API:
    build_platform_strategy_influence(plan) -> dict
        Returns {"platform_strategy_influence": {...}}
    enrich_subtitle_influence_reasoning(influence_dict, platform_subtitle_support) -> dict
    enrich_camera_influence_reasoning(influence_dict, platform_camera_support) -> dict
    enrich_ranking_influence_reasoning(influence_dict, platform_ranking_support) -> dict

Safety contract:
  - Local only: no internet, no subprocess, no cloud API
  - Never raises — fallback-safe
  - Deterministic: same inputs → same output
  - Advisory only: confidence_delta is metadata, NEVER fed into safety gate
  - Safety gates are NEVER bypassed or lowered by platform strategy
  - Bounded: per-domain delta ≤ 0.05, total boost ≤ 0.10
  - Additive only: only appends to existing reasoning, never changes bias values
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("app.ai.knowledge.platform_strategy_influence_context")

# ---------------------------------------------------------------------------
# Confidence delta limits — strictly enforced (same contract as Phase 54)
# ---------------------------------------------------------------------------

_MAX_DELTA_PER_DOMAIN = 0.05
_MAX_TOTAL_DELTA = 0.10

_SUBTITLE_DELTA = 0.04
_CAMERA_DELTA   = 0.03
_RANKING_DELTA  = 0.05

_MAX_REASONING_PER_DOMAIN = 3
_MAX_REASONING_LINES = 5

# ---------------------------------------------------------------------------
# Forbidden execution keys — must never appear in any output dict
# ---------------------------------------------------------------------------

_FORBIDDEN_OUTPUT_KEYS = frozenset({
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
    "crop_coordinates", "direct_execution", "executor_override",
    "output_path", "queue_priority",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_platform_strategy_influence(plan: Any) -> dict:
    """Build per-domain platform strategy influence support from Phase 55E output.

    Reads platform_render_strategy from the plan, derives per-domain influence
    support with bounded confidence deltas, and produces creator-facing reasoning.

    Accepts AIEditPlan or plain dict via duck-typed access.

    Never raises. Fallback returns available=False context.
    Advisory only — confidence_delta is informational metadata, never fed to
    safety gate or influence execution logic.
    """
    try:
        return _build(plan)
    except Exception as exc:
        logger.debug("platform_strategy_influence_build_error: %s", exc)
        return {"platform_strategy_influence": _fallback()}


def enrich_subtitle_influence_reasoning(
    influence_dict: dict,
    platform_subtitle_support: dict,
) -> dict:
    """Append platform-strategy-aware reasons to a subtitle influence dict.

    Additive only — appends to existing 'reasoning' list, caps total at 6.
    Never changes bias values. Never raises.
    """
    try:
        if not influence_dict or not platform_subtitle_support.get("supported"):
            return influence_dict or {}
        reasons = platform_subtitle_support.get("reasoning") or []
        if not reasons:
            return influence_dict
        existing = list(influence_dict.get("reasoning") or [])
        merged = (existing + reasons)[:6]
        return {**influence_dict, "reasoning": merged}
    except Exception:
        return influence_dict or {}


def enrich_camera_influence_reasoning(
    influence_dict: dict,
    platform_camera_support: dict,
) -> dict:
    """Append platform-strategy-aware reasons to a camera influence/tuning dict.

    Additive only — appends to existing 'reasoning' list, caps total at 6.
    Never changes bias or tuning values. Never raises.
    """
    try:
        if not influence_dict or not platform_camera_support.get("supported"):
            return influence_dict or {}
        reasons = platform_camera_support.get("reasoning") or []
        if not reasons:
            return influence_dict
        existing = list(influence_dict.get("reasoning") or [])
        merged = (existing + reasons)[:6]
        return {**influence_dict, "reasoning": merged}
    except Exception:
        return influence_dict or {}


def enrich_ranking_influence_reasoning(
    influence_dict: dict,
    platform_ranking_support: dict,
) -> dict:
    """Append platform-strategy-aware reasons to a ranking influence dict.

    Additive only — appends to existing 'reasoning' or 'explainability' list.
    Caps total at 6. Never changes ranking priorities. Never raises.
    """
    try:
        if not influence_dict or not platform_ranking_support.get("supported"):
            return influence_dict
        reasons = platform_ranking_support.get("reasoning") or []
        if not reasons:
            return influence_dict
        for key in ("reasoning", "explainability"):
            if key in influence_dict:
                existing = list(influence_dict[key] or [])
                return {**influence_dict, key: (existing + reasons)[:6]}
        return influence_dict
    except Exception:
        return influence_dict


# ---------------------------------------------------------------------------
# Internal builder
# ---------------------------------------------------------------------------

def _fallback() -> dict:
    return {
        "available": False,
        "confidence": 0.0,
    }


def _get(plan: Any, key: str) -> Any:
    """Duck-typed read — works for AIEditPlan or dict."""
    if isinstance(plan, dict):
        return plan.get(key)
    return getattr(plan, key, None)


def _build(plan: Any) -> dict:
    if plan is None:
        return {"platform_strategy_influence": _fallback()}

    # Read Phase 55E platform_render_strategy
    prs = _get(plan, "platform_render_strategy") or {}
    if not isinstance(prs, dict) or not prs.get("available"):
        return {"platform_strategy_influence": _fallback()}

    platform = str(prs.get("platform") or "")
    creator_type = str(prs.get("creator_type") or "")
    strategy = prs.get("strategy") or {}
    prs_confidence = float(prs.get("confidence") or 0.0)

    if not strategy:
        return {"platform_strategy_influence": _fallback()}

    subtitle_strategy = strategy.get("subtitle") or {}
    camera_strategy = strategy.get("camera") or {}
    hook_strategy = strategy.get("hook") or {}
    ranking_strategy = strategy.get("ranking") or {}

    influence_support: Dict[str, dict] = {}
    total_delta = 0.0

    # --- Subtitle domain ---
    subtitle_support = _build_subtitle_support(
        platform, creator_type, subtitle_strategy, total_delta,
    )
    if subtitle_support.get("supported"):
        influence_support["subtitle"] = subtitle_support
        total_delta = round(total_delta + float(subtitle_support.get("confidence_delta") or 0.0), 4)

    # --- Camera domain ---
    if total_delta < _MAX_TOTAL_DELTA:
        camera_support = _build_camera_support(
            platform, creator_type, camera_strategy, total_delta,
        )
        if camera_support.get("supported"):
            influence_support["camera"] = camera_support
            total_delta = round(total_delta + float(camera_support.get("confidence_delta") or 0.0), 4)

    # --- Ranking domain (from hook + ranking strategy) ---
    if total_delta < _MAX_TOTAL_DELTA:
        ranking_support = _build_ranking_support(
            platform, creator_type, hook_strategy, ranking_strategy, total_delta,
        )
        if ranking_support.get("supported"):
            influence_support["ranking"] = ranking_support
            total_delta = round(total_delta + float(ranking_support.get("confidence_delta") or 0.0), 4)

    if not influence_support:
        return {"platform_strategy_influence": _fallback()}

    confidence = round(max(0.0, min(1.0, prs_confidence)), 4)
    psi_reasoning = _build_top_reasoning(platform, creator_type, influence_support)

    logger.debug(
        "platform_strategy_influence_built platform=%s creator_type=%s "
        "domains=%s total_delta=%.3f confidence=%.3f",
        platform, creator_type, sorted(influence_support.keys()),
        total_delta, confidence,
    )

    result: dict = {
        "available": True,
        "platform": platform,
        "creator_type": creator_type,
    }
    result.update(influence_support)
    result["confidence"] = confidence
    result["platform_strategy_influence_reasoning"] = psi_reasoning

    return {"platform_strategy_influence": result}


# ---------------------------------------------------------------------------
# Per-domain support builders
# ---------------------------------------------------------------------------

def _build_subtitle_support(
    platform: str,
    creator_type: str,
    subtitle_strategy: dict,
    total_delta: float,
) -> dict:
    style = str(subtitle_strategy.get("style_bias") or "")
    density = str(subtitle_strategy.get("density_bias") or "")
    keyword_emphasis = str(subtitle_strategy.get("keyword_emphasis") or "")

    has_style = bool(style and style != "unknown")
    has_density = bool(density and density != "unknown")
    has_emphasis = bool(keyword_emphasis and keyword_emphasis not in ("none", "unknown"))

    if not (has_style or has_density or has_emphasis):
        return {"supported": False}

    bias: dict = {}
    if has_style:
        bias["style"] = style
    if has_density:
        bias["density"] = density
    if has_emphasis:
        bias["keyword_emphasis"] = keyword_emphasis

    delta = round(min(min(_SUBTITLE_DELTA, _MAX_DELTA_PER_DOMAIN), max(0.0, _MAX_TOTAL_DELTA - total_delta)), 3)
    reasoning = _build_subtitle_reasoning(platform, creator_type, style, density, keyword_emphasis)

    return {
        "supported": True,
        "bias": bias,
        "confidence_delta": delta,
        "reasoning": reasoning,
    }


def _build_camera_support(
    platform: str,
    creator_type: str,
    camera_strategy: dict,
    total_delta: float,
) -> dict:
    motion_energy = str(camera_strategy.get("motion_energy") or "")
    stability = str(camera_strategy.get("stability_priority") or "")
    crop_aggressiveness = str(camera_strategy.get("crop_aggressiveness") or "")

    has_motion = bool(motion_energy and motion_energy != "unknown")
    has_stability = bool(stability and stability != "unknown")
    has_crop = bool(crop_aggressiveness and crop_aggressiveness != "unknown")

    if not (has_motion or has_stability or has_crop):
        return {"supported": False}

    bias: dict = {}
    if has_motion:
        bias["motion_energy"] = motion_energy
    if has_stability:
        bias["stability_priority"] = stability
    if has_crop:
        bias["crop_aggressiveness"] = crop_aggressiveness

    delta = round(min(min(_CAMERA_DELTA, _MAX_DELTA_PER_DOMAIN), max(0.0, _MAX_TOTAL_DELTA - total_delta)), 3)
    reasoning = _build_camera_reasoning(platform, creator_type, motion_energy, stability, crop_aggressiveness)

    return {
        "supported": True,
        "bias": bias,
        "confidence_delta": delta,
        "reasoning": reasoning,
    }


def _build_ranking_support(
    platform: str,
    creator_type: str,
    hook_strategy: dict,
    ranking_strategy: dict,
    total_delta: float,
) -> dict:
    ranking_priority = str(ranking_strategy.get("priority") or "")
    first_3s = str(hook_strategy.get("first_3s_priority") or "")
    retention = str(hook_strategy.get("retention_priority") or "")

    has_ranking = bool(ranking_priority and ranking_priority not in ("unknown", "balanced"))
    has_retention = bool(retention and retention != "unknown")

    if not (has_ranking or has_retention):
        return {"supported": False}

    bias: dict = {}
    if has_ranking:
        bias["priority"] = ranking_priority

    delta = round(min(min(_RANKING_DELTA, _MAX_DELTA_PER_DOMAIN), max(0.0, _MAX_TOTAL_DELTA - total_delta)), 3)
    reasoning = _build_ranking_reasoning(platform, creator_type, ranking_priority, retention, first_3s)

    return {
        "supported": True,
        "bias": bias,
        "confidence_delta": delta,
        "reasoning": reasoning,
    }


# ---------------------------------------------------------------------------
# Reasoning builders — creator-facing, no internal leakage
# ---------------------------------------------------------------------------

def _build_subtitle_reasoning(
    platform: str,
    creator_type: str,
    style: str,
    density: str,
    keyword_emphasis: str,
) -> List[str]:
    plat = platform.replace("_", " ") if platform else ""
    creator = creator_type.replace("_", " ") if creator_type else ""
    lines: List[str] = []

    if platform and creator_type:
        if density and style:
            lines.append(
                f"Platform strategy supports {density} {style} subtitles"
                f" for {plat} {creator} content"
            )
        elif style:
            lines.append(f"Platform strategy supports {style} subtitle style for {creator} creators")
        elif density:
            lines.append(f"Platform strategy supports {density} subtitle density for {plat}")
    elif platform:
        if density:
            lines.append(f"Platform strategy supports {density} subtitle density for {plat}")
        elif style:
            lines.append(f"Platform strategy supports {style} subtitle style for {plat}")
    elif creator_type:
        if style:
            lines.append(f"Platform strategy supports {style} subtitle style for {creator} creators")

    if keyword_emphasis and keyword_emphasis not in ("none", "unknown"):
        lines.append(f"Keyword emphasis guidance: {keyword_emphasis}")

    return lines[:_MAX_REASONING_PER_DOMAIN]


def _build_camera_reasoning(
    platform: str,
    creator_type: str,
    motion_energy: str,
    stability: str,
    crop_aggressiveness: str,
) -> List[str]:
    creator = creator_type.replace("_", " ") if creator_type else ""
    lines: List[str] = []

    if stability in ("high", "medium_high") and creator_type in ("podcast", "talking_head", "educational", "storytelling"):
        lines.append(f"Platform strategy supports stable {creator} framing")
    elif motion_energy and stability:
        lines.append(
            f"Platform strategy recommends {motion_energy} motion energy with {stability} stability"
        )
    elif stability:
        lines.append(f"Platform strategy supports {stability} stability priority")

    if crop_aggressiveness == "low":
        lines.append("Conservative crop aggressiveness preserves stable framing")
    elif crop_aggressiveness and crop_aggressiveness != "unknown":
        lines.append(f"Crop aggressiveness guidance: {crop_aggressiveness}")

    return lines[:_MAX_REASONING_PER_DOMAIN]


def _build_ranking_reasoning(
    platform: str,
    creator_type: str,
    ranking_priority: str,
    retention_priority: str,
    first_3s_priority: str,
) -> List[str]:
    plat = platform.replace("_", " ") if platform else ""
    creator = creator_type.replace("_", " ") if creator_type else ""
    lines: List[str] = []

    if ranking_priority == "retention_creator_fit":
        if plat and creator:
            lines.append(
                f"Platform strategy supports retention and creator-fit ranking"
                f" for {plat} {creator} content"
            )
        else:
            lines.append("Platform strategy supports balanced retention and creator-fit ranking")
    elif ranking_priority == "retention":
        lines.append("Platform strategy supports retention priority in ranking")
    elif ranking_priority == "creator_fit":
        lines.append("Platform strategy supports creator-fit priority in ranking")
    elif ranking_priority == "readability":
        lines.append("Platform strategy prioritizes readability in ranking")
    elif ranking_priority == "hook_strength":
        lines.append("Platform strategy prioritizes hook strength in ranking")
    elif ranking_priority and ranking_priority != "unknown":
        lines.append(f"Platform strategy supports {ranking_priority.replace('_', ' ')} in ranking")

    if first_3s_priority == "high":
        lines.append("Strong first-3-second retention guidance active")

    return lines[:_MAX_REASONING_PER_DOMAIN]


def _build_top_reasoning(
    platform: str,
    creator_type: str,
    influence_support: Dict[str, dict],
) -> List[str]:
    """Build top-level creator-facing reasoning summary. Never raises."""
    lines: List[str] = []
    plat = platform.replace("_", " ").title() if platform else ""
    creator = creator_type.replace("_", " ") if creator_type else ""

    if platform and creator_type:
        lines.append(
            f"{plat} platform guidance and {creator} creator intelligence are informing safe influence."
        )

    sub = influence_support.get("subtitle") or {}
    if sub.get("supported"):
        sub_reasons = sub.get("reasoning") or []
        if sub_reasons:
            lines.append(sub_reasons[0])

    cam = influence_support.get("camera") or {}
    if cam.get("supported"):
        cam_reasons = cam.get("reasoning") or []
        if cam_reasons:
            lines.append(cam_reasons[0])

    rank = influence_support.get("ranking") or {}
    if rank.get("supported"):
        rank_reasons = rank.get("reasoning") or []
        if rank_reasons:
            lines.append(rank_reasons[0])

    return lines[:_MAX_REASONING_LINES]
