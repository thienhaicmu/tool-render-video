"""
market_optimizer.py — Market-aware optimization engine. Phase 44.

Public API:
    build_market_optimization_pack(edit_plan, payload=None, context=None)
        -> AIMarketOptimizationPack

Rules:
- Deterministic only
- Never raises
- Assistive-only (influences metadata, never overrides user settings)
- No payload mutation in-place
- No render execution
- No autonomous override
- No internet, no cloud AI, no model fine-tuning
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.market.market_schema import AIMarketOptimizationPack, AIMarketOptimizationProfile
from app.ai.market.market_profiles import get_market_profile
from app.ai.market.market_safety import sanitize_market_profile

logger = logging.getLogger("app.ai.market.optimizer")

# Bias bounds
_MAX_BIAS = 0.30
_MIN_BIAS = 0.0

# Adaptive amplifier — how much Phase 42/43 intelligence amplifies market bias
_ADAPTIVE_AMPLIFIER = 0.08
_FEEDBACK_AMPLIFIER = 0.06


def build_market_optimization_pack(
    edit_plan: Any,
    payload: Optional[Any] = None,
    context: Optional[dict] = None,
) -> AIMarketOptimizationPack:
    """Build market optimization pack from target platform and edit plan signals.

    Resolves market profile, computes optimization biases, incorporates
    adaptive/feedback intelligence signals. Never raises.

    Args:
        edit_plan:  AIEditPlan with all Phase 1–43 metadata.
        payload:    Optional render request (read-only). Never mutated.
        context:    Optional session context (e.g. target_market).

    Returns:
        AIMarketOptimizationPack with market_profile, subtitle/pacing/camera/hook biases.
    """
    try:
        return _build_pack(edit_plan, payload, context)
    except Exception as exc:
        logger.debug("market_optimizer_build_error: %s", exc)
        return AIMarketOptimizationPack(
            available=False,
            enabled=False,
            optimization_mode="assistive_only",
            warnings=[f"market_optimizer_error:{type(exc).__name__}"],
        )


def _build_pack(
    edit_plan: Any,
    payload: Optional[Any],
    context: Optional[dict],
) -> AIMarketOptimizationPack:
    ctx = context or {}
    warnings: list[str] = []

    # Resolve target market from context > payload > edit_plan
    target_market = _resolve_target_market(ctx, payload, edit_plan)

    # Load market profile
    profile = get_market_profile(target_market)

    if profile.warnings:
        warnings.extend(profile.warnings)

    logger.info(
        "ai_market_profile_loaded market_id=%s platform=%s confidence=%.2f",
        profile.market_id, profile.platform_type, profile.confidence,
    )

    # Build optimization biases
    subtitle_bias = _build_subtitle_bias(profile, edit_plan, ctx)
    pacing_bias = _build_pacing_bias(profile, edit_plan, ctx)
    camera_bias = _build_camera_bias(profile, edit_plan, ctx)
    hook_bias = _build_hook_bias(profile, edit_plan, ctx)

    # Amplify with adaptive and feedback signals
    _amplify_with_adaptive(subtitle_bias, pacing_bias, camera_bias, edit_plan)
    _amplify_with_feedback(subtitle_bias, pacing_bias, camera_bias, edit_plan)

    enabled = profile.confidence >= 0.50

    pack = AIMarketOptimizationPack(
        available=True,
        enabled=enabled,
        optimization_mode="assistive_only",
        target_market=target_market,
        market_profile=sanitize_market_profile(profile.to_dict()),
        subtitle_market_bias=subtitle_bias,
        pacing_market_bias=pacing_bias,
        camera_market_bias=camera_bias,
        hook_market_bias=hook_bias,
        warnings=warnings,
    )

    if enabled:
        logger.info(
            "ai_market_optimization_applied market=%s subtitle_bias=%.3f pacing_bias=%.3f",
            target_market,
            subtitle_bias.get("weight", 0.0),
            pacing_bias.get("weight", 0.0),
        )
    else:
        logger.debug("ai_market_optimization_skipped market=%s low_confidence", target_market)

    return pack


def _resolve_target_market(ctx: dict, payload: Optional[Any], edit_plan: Any) -> str:
    """Resolve the target market from available sources. Never raises."""
    try:
        # 1. Explicit context
        m = str(ctx.get("target_market", "") or "").strip()
        if m:
            return m

        # 2. Payload ai_mode or ai_target_market
        if payload is not None:
            m = str(getattr(payload, "ai_target_market", "") or "").strip()
            if m:
                return m
            m = str(getattr(payload, "ai_mode", "") or "").strip()
            if m:
                return m

        # 3. Edit plan creator style
        if edit_plan is not None:
            csa = getattr(edit_plan, "creator_style_adaptation", None) or {}
            if isinstance(csa, dict):
                m = str(csa.get("adapted_style") or "").strip()
                if m:
                    return m
            mode = str(getattr(edit_plan, "mode", "") or "").strip()
            if mode:
                return mode

    except Exception:
        pass
    return "generic"


def _build_subtitle_bias(
    profile: AIMarketOptimizationProfile,
    edit_plan: Any,
    ctx: dict,
) -> dict:
    """Build subtitle market bias metadata. Never raises."""
    try:
        weight = _bound(profile.subtitle_density_bias * 0.40)
        return {
            "preferred_style": profile.preferred_subtitle_style,
            "density_bias": round(float(profile.subtitle_density_bias), 4),
            "weight": weight,
            "market_id": profile.market_id,
            "assistive_only": True,
        }
    except Exception:
        return {"assistive_only": True}


def _build_pacing_bias(
    profile: AIMarketOptimizationProfile,
    edit_plan: Any,
    ctx: dict,
) -> dict:
    """Build pacing market bias metadata. Never raises."""
    try:
        weight = _bound(profile.pacing_energy_bias * 0.40)
        return {
            "preferred_style": profile.preferred_pacing_style,
            "energy_bias": round(float(profile.pacing_energy_bias), 4),
            "weight": weight,
            "market_id": profile.market_id,
            "assistive_only": True,
        }
    except Exception:
        return {"assistive_only": True}


def _build_camera_bias(
    profile: AIMarketOptimizationProfile,
    edit_plan: Any,
    ctx: dict,
) -> dict:
    """Build camera market bias metadata. Never raises."""
    try:
        weight = _bound(profile.camera_motion_bias * 0.35)
        return {
            "preferred_style": profile.preferred_camera_style,
            "motion_bias": round(float(profile.camera_motion_bias), 4),
            "weight": weight,
            "market_id": profile.market_id,
            "assistive_only": True,
        }
    except Exception:
        return {"assistive_only": True}


def _build_hook_bias(
    profile: AIMarketOptimizationProfile,
    edit_plan: Any,
    ctx: dict,
) -> dict:
    """Build hook market bias metadata. Never raises."""
    try:
        weight = _bound(profile.hook_strength_bias * 0.35)
        return {
            "preferred_style": profile.preferred_hook_style,
            "strength_bias": round(float(profile.hook_strength_bias), 4),
            "weight": weight,
            "market_id": profile.market_id,
            "assistive_only": True,
        }
    except Exception:
        return {"assistive_only": True}


def _amplify_with_adaptive(
    subtitle_bias: dict,
    pacing_bias: dict,
    camera_bias: dict,
    edit_plan: Any,
) -> None:
    """Amplify market biases using Phase 42 adaptive profile. Never raises."""
    try:
        aci = getattr(edit_plan, "adaptive_creator_intelligence", None)
        if not isinstance(aci, dict) or not aci.get("enabled"):
            return

        influences = aci.get("adaptive_influences", {}) or {}

        sub_w = float(influences.get("subtitle_enhancement_weight", 0.0) or 0)
        if sub_w > 0:
            subtitle_bias["weight"] = _bound(
                subtitle_bias.get("weight", 0.0) + sub_w * _ADAPTIVE_AMPLIFIER
            )

        pac_w = float(influences.get("pacing_enhancement_weight", 0.0) or 0)
        if pac_w > 0:
            pacing_bias["weight"] = _bound(
                pacing_bias.get("weight", 0.0) + pac_w * _ADAPTIVE_AMPLIFIER
            )

        cam_w = float(influences.get("camera_enhancement_weight", 0.0) or 0)
        if cam_w > 0:
            camera_bias["weight"] = _bound(
                camera_bias.get("weight", 0.0) + cam_w * _ADAPTIVE_AMPLIFIER
            )

    except Exception as exc:
        logger.debug("market_adaptive_amplify_error: %s", exc)


def _amplify_with_feedback(
    subtitle_bias: dict,
    pacing_bias: dict,
    camera_bias: dict,
    edit_plan: Any,
) -> None:
    """Amplify market biases using Phase 43 feedback signals. Never raises."""
    try:
        cfi = getattr(edit_plan, "creator_feedback_intelligence", None)
        if not isinstance(cfi, dict) or not cfi.get("enabled"):
            return

        biases = cfi.get("ranking_biases", {}) or {}

        sub_b = float(biases.get("subtitle_weighting_bias", 0.0) or 0)
        if sub_b > 0:
            subtitle_bias["weight"] = _bound(
                subtitle_bias.get("weight", 0.0) + sub_b * _FEEDBACK_AMPLIFIER
            )

        pac_b = float(biases.get("pacing_weighting_bias", 0.0) or 0)
        if pac_b > 0:
            pacing_bias["weight"] = _bound(
                pacing_bias.get("weight", 0.0) + pac_b * _FEEDBACK_AMPLIFIER
            )

        cam_b = float(biases.get("camera_weighting_bias", 0.0) or 0)
        if cam_b > 0:
            camera_bias["weight"] = _bound(
                camera_bias.get("weight", 0.0) + cam_b * _FEEDBACK_AMPLIFIER
            )

    except Exception as exc:
        logger.debug("market_feedback_amplify_error: %s", exc)


def _bound(value: float) -> float:
    """Clamp bias to [0.0, 0.30]. Never raises."""
    try:
        return round(max(_MIN_BIAS, min(_MAX_BIAS, float(value))), 4)
    except Exception:
        return 0.0
