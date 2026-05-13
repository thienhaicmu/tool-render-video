"""
platform_render_strategy_engine.py — Phase 55E Platform-Aware Render Strategy engine.

Fuses platform subtitle (55B), camera (55C), and hook (55D) intelligence into
one deterministic advisory platform render strategy.

Public API:
    build_platform_render_strategy(plan) -> dict
        Returns {"platform_render_strategy": {...}}

Reads from plan metadata already populated by Phases 55A–55D:
  - platform_context         (Phase 55A)
  - platform_subtitle_context (Phase 55B)
  - platform_camera_context  (Phase 55C)
  - platform_hook_context    (Phase 55D)
  - creator_preference_profile (Phase 50D)
  - knowledge_reasoning_context (Phase 53E)
  - render_quality_v2        (Phase 52D)

Safety contract:
  - Local only: no internet, no subprocess, no cloud API
  - Never mutates render pipeline, subtitles, camera, hooks, or FFmpeg
  - Never raises — fallback-safe
  - Deterministic: same plan state → same strategy output
  - Advisory-only: strategy informs reasoning, never executes
  - No executor override, no autonomous execution
  - Confidence clamped [0, 1]
  - All output values normalized to explicit allowed sets
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.knowledge.platform_render_strategy_schema import (
    AIPlatformRenderStrategy,
    ALLOWED_SUBTITLE_STYLE_BIAS,
    ALLOWED_SUBTITLE_DENSITY_BIAS,
    ALLOWED_SUBTITLE_KEYWORD_EMPHASIS,
    ALLOWED_SUBTITLE_READABILITY_PRIORITY,
    ALLOWED_CAMERA_MOTION_ENERGY,
    ALLOWED_CAMERA_STABILITY_PRIORITY,
    ALLOWED_CAMERA_CROP_AGGRESSIVENESS,
    ALLOWED_CAMERA_JITTER_SENSITIVITY,
    ALLOWED_HOOK_FIRST_3S_PRIORITY,
    ALLOWED_HOOK_RETENTION_PRIORITY,
    ALLOWED_HOOK_ENERGY,
    ALLOWED_HOOK_CURIOSITY_STYLE,
    ALLOWED_RANKING_PRIORITY,
    _normalize,
    _fallback_strategy,
)

logger = logging.getLogger("app.ai.knowledge.platform_render_strategy_engine")

# ---------------------------------------------------------------------------
# Creator / platform classification sets
# ---------------------------------------------------------------------------

# Creators that prefer trust, stability, and clean presentation
_TRUST_STYLE_CREATORS = frozenset({"podcast", "talking_head"})

# Creators that prioritize clarity, structure, and concept delivery
_CLARITY_CREATORS = frozenset({"educational", "storytelling"})

# Short-form platforms with strong retention pressure
_HIGH_RETENTION_PLATFORMS = frozenset({"tiktok", "youtube_shorts", "instagram_reels"})

# Platforms with very high energy / viral pressure
_HIGH_ENERGY_PLATFORMS = frozenset({"tiktok", "instagram_reels"})

# Map raw hook_style guidance values → curiosity_style allowed values
_HOOK_STYLE_TO_CURIOSITY = {
    "direct_promise": "direct",
    "trust_first": "subtle",
    "concept_first": "soft_direct",
    "soft_open_loop": "open_loop",
    "open_loop": "open_loop",
    "direct": "direct",
    "subtle": "subtle",
    "soft_direct": "soft_direct",
    "conversational": "subtle",
    "emotional_stakes": "soft_direct",
}

# hook_energy from knowledge guidance may use "medium" — map to "moderate"
_HOOK_ENERGY_REMAP = {"medium": "moderate"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_platform_render_strategy(plan: Any) -> dict:
    """Build unified platform-aware advisory render strategy from plan metadata.

    Accepts AIEditPlan or plain dict. Reads domain contexts already computed by
    Phases 55A–55D and fuses them into one strategy with conflict resolution.

    Returns {"platform_render_strategy": {...}} always. Never raises.
    Fallback returns available=False strategy.
    """
    try:
        return _build(plan)
    except Exception as exc:
        logger.debug("platform_render_strategy_build_error: %s", exc)
        return _fallback_strategy()


# ---------------------------------------------------------------------------
# Internal build
# ---------------------------------------------------------------------------

def _get(plan: Any, key: str, default: Any = None) -> Any:
    """Duck-typed read — works for AIEditPlan or dict."""
    if isinstance(plan, dict):
        return plan.get(key, default)
    val = getattr(plan, key, default)
    return val if val is not None else default


def _build(plan: Any) -> dict:
    # --- Read platform contexts populated by Phases 55A–55D ---
    platform_ctx = _get(plan, "platform_context") or {}
    subtitle_ctx = _get(plan, "platform_subtitle_context") or {}
    camera_ctx = _get(plan, "platform_camera_context") or {}
    hook_ctx = _get(plan, "platform_hook_context") or {}

    # --- Supporting contexts ---
    creator_profile = _get(plan, "creator_preference_profile") or {}
    quality_ctx = _get(plan, "render_quality_v2") or {}

    # --- Extract platform and creator_type ---
    platform = (
        str(platform_ctx.get("platform") or "").strip().lower()
        or str(subtitle_ctx.get("platform") or "").strip().lower()
        or str(camera_ctx.get("platform") or "").strip().lower()
        or str(hook_ctx.get("platform") or "").strip().lower()
    )
    creator_type = (
        str(platform_ctx.get("creator_type") or "").strip().lower()
        or str(subtitle_ctx.get("creator_type") or "").strip().lower()
        or str(camera_ctx.get("creator_type") or "").strip().lower()
        or str(hook_ctx.get("creator_type") or "").strip().lower()
    )

    # Strategy is only meaningful when we have at least platform or creator_type
    any_ctx_available = any(
        bool(ctx.get("available")) if isinstance(ctx, dict) else False
        for ctx in [platform_ctx, subtitle_ctx, camera_ctx, hook_ctx]
    )

    if not any_ctx_available and not platform and not creator_type:
        return _fallback_strategy()

    # --- Compute fused confidence ---
    conf_values = []
    for ctx in [platform_ctx, subtitle_ctx, camera_ctx, hook_ctx]:
        if isinstance(ctx, dict) and ctx.get("available"):
            c = float(ctx.get("confidence") or 0.0)
            if c > 0.0:
                conf_values.append(c)
    if conf_values:
        raw_confidence = sum(conf_values) / len(conf_values)
    elif platform or creator_type:
        raw_confidence = 0.5
    else:
        raw_confidence = 0.0
    confidence = round(max(0.0, min(1.0, raw_confidence)), 4)

    # --- Extract domain guidance dicts ---
    subtitle_guidance = subtitle_ctx.get("guidance") or {} if isinstance(subtitle_ctx, dict) else {}
    camera_guidance = camera_ctx.get("guidance") or {} if isinstance(camera_ctx, dict) else {}
    hook_guidance = hook_ctx.get("guidance") or {} if isinstance(hook_ctx, dict) else {}

    # --- Build per-domain strategies with conflict resolution ---
    subtitle_strategy = _build_subtitle_strategy(platform, creator_type, subtitle_guidance)
    camera_strategy = _build_camera_strategy(platform, creator_type, camera_guidance)
    hook_strategy = _build_hook_strategy(platform, creator_type, hook_guidance)
    ranking_strategy = _build_ranking_strategy(platform, creator_type, quality_ctx)

    strategy = {
        "subtitle": subtitle_strategy,
        "camera": camera_strategy,
        "hook": hook_strategy,
        "ranking": ranking_strategy,
    }

    reasoning = _build_reasoning(
        platform, creator_type,
        subtitle_ctx, camera_ctx, hook_ctx,
        subtitle_strategy, camera_strategy, hook_strategy, ranking_strategy,
    )

    result = AIPlatformRenderStrategy(
        available=True,
        platform=platform,
        creator_type=creator_type,
        strategy=strategy,
        confidence=confidence,
        reasoning=reasoning,
    )

    logger.debug(
        "platform_render_strategy_built platform=%s creator_type=%s confidence=%.3f",
        platform, creator_type, confidence,
    )

    return {"platform_render_strategy": result.to_dict()}


# ---------------------------------------------------------------------------
# Subtitle strategy (Phase 55B context + conflict resolution)
# ---------------------------------------------------------------------------

def _build_subtitle_strategy(
    platform: str,
    creator_type: str,
    guidance: dict,
) -> dict:
    is_trust = creator_type in _TRUST_STYLE_CREATORS
    is_clarity = creator_type in _CLARITY_CREATORS
    is_high_energy = platform in _HIGH_ENERGY_PLATFORMS
    is_retention = platform in _HIGH_RETENTION_PLATFORMS

    # style_bias — trust/clarity creators always use clean_pro regardless of platform
    raw_style = str(guidance.get("style_preference") or "").strip().lower()
    if is_trust or is_clarity:
        style_bias = "clean_pro"
    elif platform == "instagram_reels":
        style_bias = _normalize(raw_style, ALLOWED_SUBTITLE_STYLE_BIAS, "boxed_caption")
        if style_bias == "unknown":
            style_bias = "boxed_caption"
    elif is_high_energy:
        style_bias = _normalize(raw_style, ALLOWED_SUBTITLE_STYLE_BIAS, "viral_bold")
        if style_bias == "unknown":
            style_bias = "viral_bold"
    else:
        style_bias = _normalize(raw_style, ALLOWED_SUBTITLE_STYLE_BIAS, "clean_pro")
        if style_bias == "unknown":
            style_bias = "clean_pro"

    # density_bias — compact is safe for both retention platforms and trust creators
    raw_density = str(guidance.get("density_bias") or "").strip().lower()
    density_bias = _normalize(raw_density, ALLOWED_SUBTITLE_DENSITY_BIAS)
    if density_bias == "unknown":
        if is_retention or is_trust:
            density_bias = "compact"
        elif is_clarity:
            density_bias = "balanced"
        else:
            density_bias = "balanced"

    # keyword_emphasis — trust/clarity creators use selective; viral on high-energy platform moderate
    raw_emphasis = str(guidance.get("keyword_emphasis") or "").strip().lower()
    keyword_emphasis = _normalize(raw_emphasis, ALLOWED_SUBTITLE_KEYWORD_EMPHASIS)
    if keyword_emphasis == "unknown":
        if is_trust or is_clarity:
            keyword_emphasis = "selective"
        elif is_high_energy and creator_type == "viral_short_form":
            keyword_emphasis = "moderate"
        else:
            keyword_emphasis = "selective"

    # readability_priority — default high across all platform/creator combinations
    raw_readability = str(guidance.get("readability_priority") or "").strip().lower()
    readability_priority = _normalize(raw_readability, ALLOWED_SUBTITLE_READABILITY_PRIORITY)
    if readability_priority == "unknown":
        readability_priority = "high"

    return {
        "style_bias": style_bias,
        "density_bias": density_bias,
        "keyword_emphasis": keyword_emphasis,
        "readability_priority": readability_priority,
    }


# ---------------------------------------------------------------------------
# Camera strategy (Phase 55C context + conflict resolution)
# ---------------------------------------------------------------------------

def _build_camera_strategy(
    platform: str,
    creator_type: str,
    guidance: dict,
) -> dict:
    is_trust = creator_type in _TRUST_STYLE_CREATORS
    is_clarity = creator_type in _CLARITY_CREATORS
    is_high_energy = platform in _HIGH_ENERGY_PLATFORMS
    is_retention = platform in _HIGH_RETENTION_PLATFORMS

    # motion_energy — trust/clarity creators cap energy; high-energy platform vs trust = low_medium
    raw_motion = str(guidance.get("motion_energy") or "").strip().lower()
    motion_energy = _normalize(raw_motion, ALLOWED_CAMERA_MOTION_ENERGY)
    if motion_energy == "unknown":
        if is_trust:
            motion_energy = "low_medium" if is_retention else "low"
        elif is_clarity:
            motion_energy = "low_medium"
        elif is_high_energy and creator_type == "viral_short_form":
            motion_energy = "medium_high"
        elif is_retention:
            motion_energy = "medium"
        else:
            motion_energy = "medium"
    elif is_trust and motion_energy in ("high", "medium_high"):
        # Conflict: trust creator safety overrides high platform energy signal
        motion_energy = "low_medium"
    elif is_clarity and motion_energy in ("high", "medium_high"):
        motion_energy = "medium"
    elif is_clarity and motion_energy == "medium":
        # Clarity creators prefer low_medium for clean, deliberate framing
        motion_energy = "low_medium"

    # stability_priority — trust/clarity creators require high stability
    raw_stability = str(guidance.get("stability_priority") or "").strip().lower()
    stability_priority = _normalize(raw_stability, ALLOWED_CAMERA_STABILITY_PRIORITY)
    if stability_priority == "unknown":
        if is_trust or is_clarity:
            stability_priority = "high"
        elif is_high_energy and creator_type == "viral_short_form":
            stability_priority = "medium"
        else:
            stability_priority = "medium_high"
    elif is_trust and stability_priority in ("low", "medium"):
        # Conflict: trust creator demands at least medium_high stability
        stability_priority = "high"

    # crop_aggressiveness — conservative for trust/clarity creators
    raw_crop = str(guidance.get("crop_aggressiveness_guidance") or "").strip().lower()
    crop_aggressiveness = _normalize(raw_crop, ALLOWED_CAMERA_CROP_AGGRESSIVENESS)
    if crop_aggressiveness == "unknown":
        if is_trust or is_clarity:
            crop_aggressiveness = "low"
        elif is_high_energy and creator_type == "viral_short_form":
            crop_aggressiveness = "medium"
        else:
            crop_aggressiveness = "low"
    elif is_trust and crop_aggressiveness == "high":
        crop_aggressiveness = "low"

    # jitter_sensitivity — high for trust/clarity creators; high is the safe default
    raw_jitter = str(guidance.get("jitter_sensitivity") or "").strip().lower()
    jitter_sensitivity = _normalize(raw_jitter, ALLOWED_CAMERA_JITTER_SENSITIVITY)
    if jitter_sensitivity == "unknown":
        jitter_sensitivity = "high"

    return {
        "motion_energy": motion_energy,
        "stability_priority": stability_priority,
        "crop_aggressiveness": crop_aggressiveness,
        "jitter_sensitivity": jitter_sensitivity,
    }


# ---------------------------------------------------------------------------
# Hook strategy (Phase 55D context + conflict resolution)
# ---------------------------------------------------------------------------

def _build_hook_strategy(
    platform: str,
    creator_type: str,
    guidance: dict,
) -> dict:
    is_trust = creator_type in _TRUST_STYLE_CREATORS
    is_clarity = creator_type in _CLARITY_CREATORS
    is_high_energy = platform in _HIGH_ENERGY_PLATFORMS
    is_retention = platform in _HIGH_RETENTION_PLATFORMS

    # first_3s_priority
    raw_first3s = str(guidance.get("first_3s_priority") or "").strip().lower()
    first_3s_priority = _normalize(raw_first3s, ALLOWED_HOOK_FIRST_3S_PRIORITY)
    if first_3s_priority == "unknown":
        first_3s_priority = "high" if platform == "tiktok" else "medium"

    # retention_priority
    raw_retention = str(guidance.get("retention_priority") or "").strip().lower()
    retention_priority = _normalize(raw_retention, ALLOWED_HOOK_RETENTION_PRIORITY)
    if retention_priority == "unknown":
        retention_priority = "high" if is_retention else "medium"

    # hook_energy — key conflict resolution point
    raw_hook_energy = str(guidance.get("hook_energy") or "").strip().lower()
    raw_hook_energy = _HOOK_ENERGY_REMAP.get(raw_hook_energy, raw_hook_energy)
    hook_energy = _normalize(raw_hook_energy, ALLOWED_HOOK_ENERGY)
    if hook_energy == "unknown":
        if is_trust:
            # Conflict: platform may want high energy but trust creator needs moderate/low
            hook_energy = "moderate" if is_high_energy else "low"
        elif is_clarity:
            hook_energy = "moderate"
        elif is_high_energy and creator_type == "viral_short_form":
            hook_energy = "high"
        elif is_retention:
            hook_energy = "moderate"
        else:
            hook_energy = "moderate"
    elif is_trust and hook_energy == "high":
        # Conflict resolution: trust creator safety caps hook energy
        hook_energy = "moderate"

    # curiosity_style — mapped from hook_style guidance or derived from platform/creator
    raw_hook_style = str(guidance.get("hook_style") or "").strip().lower()
    curiosity_style = _HOOK_STYLE_TO_CURIOSITY.get(raw_hook_style, "")
    if not curiosity_style or curiosity_style not in ALLOWED_HOOK_CURIOSITY_STYLE:
        if is_trust:
            curiosity_style = "soft_direct" if is_high_energy else "subtle"
        elif is_clarity:
            curiosity_style = "soft_direct"
        elif is_high_energy and creator_type == "viral_short_form":
            curiosity_style = "direct"
        elif is_retention:
            curiosity_style = "soft_direct"
        else:
            curiosity_style = "soft_direct"
    elif is_trust and curiosity_style == "direct":
        # Conflict: trust creator safety caps hard "direct" to "soft_direct"
        curiosity_style = "soft_direct"

    return {
        "first_3s_priority": first_3s_priority,
        "retention_priority": retention_priority,
        "hook_energy": hook_energy,
        "curiosity_style": curiosity_style,
    }


# ---------------------------------------------------------------------------
# Ranking strategy (cross-domain synthesis)
# ---------------------------------------------------------------------------

def _build_ranking_strategy(
    platform: str,
    creator_type: str,
    quality_ctx: dict,
) -> dict:
    is_trust = creator_type in _TRUST_STYLE_CREATORS
    is_clarity = creator_type in _CLARITY_CREATORS
    is_high_energy = platform in _HIGH_ENERGY_PLATFORMS
    is_retention = platform in _HIGH_RETENTION_PLATFORMS

    # Conflict resolution: platform retention pressure vs creator style preference
    if is_retention and (is_trust or is_clarity):
        priority = "retention_creator_fit"
    elif is_trust:
        priority = "creator_fit"
    elif creator_type == "educational":
        priority = "readability"
    elif is_retention and creator_type == "viral_short_form":
        priority = "retention"
    elif is_high_energy:
        priority = "hook_strength"
    elif is_retention:
        priority = "retention"
    elif creator_type:
        priority = "creator_fit"
    else:
        priority = "balanced"

    priority = _normalize(priority, ALLOWED_RANKING_PRIORITY, "balanced")
    return {"priority": priority}


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    platform: str,
    creator_type: str,
    subtitle_ctx: dict,
    camera_ctx: dict,
    hook_ctx: dict,
    subtitle_strategy: dict,
    camera_strategy: dict,
    hook_strategy: dict,
    ranking_strategy: dict,
) -> list:
    lines: list = []
    is_trust = creator_type in _TRUST_STYLE_CREATORS
    is_clarity = creator_type in _CLARITY_CREATORS
    is_high_energy = platform in _HIGH_ENERGY_PLATFORMS
    is_retention = platform in _HIGH_RETENTION_PLATFORMS

    plat_label = platform.replace("_", " ").title() if platform else ""
    creator_label = creator_type.replace("_", " ") if creator_type else ""

    # Platform + creator context line
    if platform and creator_type:
        if is_retention and is_trust:
            lines.append(
                f"{plat_label} platform guidance supports strong early retention "
                f"while {creator_label} creator style keeps framing stable and subtitles clean."
            )
        elif is_retention and is_clarity:
            lines.append(
                f"{plat_label} platform favors retention-focused delivery "
                f"while {creator_label} creator style prioritizes readability and clarity."
            )
        else:
            lines.append(
                f"Platform strategy fuses {plat_label} guidance with "
                f"{creator_label} creator intelligence."
            )
    elif platform:
        lines.append(f"Platform strategy built from {plat_label} platform guidance.")
    elif creator_type:
        lines.append(f"Platform strategy built from {creator_label} creator intelligence.")

    # Subtitle guidance line
    style_bias = subtitle_strategy.get("style_bias", "")
    density_bias = subtitle_strategy.get("density_bias", "")
    if style_bias and density_bias and style_bias != "unknown" and density_bias != "unknown":
        lines.append(
            f"Platform subtitle guidance supports {density_bias} density with {style_bias} style."
        )

    # Camera guidance line
    motion_energy = camera_strategy.get("motion_energy", "")
    stability = camera_strategy.get("stability_priority", "")
    if motion_energy and stability and motion_energy != "unknown" and stability != "unknown":
        lines.append(
            f"Platform camera guidance supports {motion_energy} motion energy "
            f"and {stability} stability priority."
        )

    # Hook/retention guidance line
    hook_energy = hook_strategy.get("hook_energy", "")
    first_3s = hook_strategy.get("first_3s_priority", "")
    if hook_energy and first_3s and hook_energy != "unknown" and first_3s != "unknown":
        lines.append(
            f"Platform hook guidance sets {hook_energy} hook energy "
            f"with {first_3s} first-3-second priority."
        )

    # Conflict resolution note
    if is_high_energy and is_trust:
        lines.append(
            f"Strategy balances {plat_label} retention pressure with "
            f"{creator_label} trust-focused style."
        )
    elif is_retention and is_clarity:
        lines.append(
            "Strategy balances platform retention pressure with creator clarity and readability focus."
        )

    # Ranking note
    ranking_priority = ranking_strategy.get("priority", "")
    if ranking_priority and ranking_priority not in ("unknown", "balanced"):
        lines.append(
            f"Strategy prioritizes {ranking_priority.replace('_', ' ')} in variant ranking."
        )

    return lines[:8]
