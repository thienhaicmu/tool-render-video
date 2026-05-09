"""
preset_evolution_engine.py — Creator preset evolution orchestrator. Phase 46.

Public API:
    build_preset_evolution_pack(edit_plan, payload=None, context=None)
        -> AIPresetEvolutionPack

Rules:
- Deterministic only
- Never raises
- Assistive-only
- No payload mutation
- No render execution
- No autonomous preset replacement
- No FFmpeg mutation
- No playback_speed mutation
- No subtitle timing rewrite
- No executor override

Evolution behavior:
    Combines creator style + market optimization + feedback + quality signals
    to produce evolved preset recommendations.

    TikTok Viral    → TikTok Viral v2  (stronger hook, compact subtitle, faster pacing)
    Podcast Clean   → Podcast Clean v2 (readability-first subtitle, calm pacing, stable framing)
    Educational     → Educational Pro  (clean subtitle, clarity-first pacing)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.preset_evolution.preset_schema import AICreatorPreset, AIPresetEvolutionPack
from app.ai.preset_evolution.preset_memory import load_evolved_presets, save_evolved_presets
from app.ai.preset_evolution.preset_scoring import score_creator_preset
from app.ai.preset_evolution.preset_safety import sanitize_preset, _clamp_score, _clamp_confidence

logger = logging.getLogger("app.ai.preset_evolution.engine")

# Minimum scoring threshold to recommend a preset
_MIN_RECOMMEND_SCORE = 40.0

# Minimum confidence to generate an evolved variant
_MIN_EVOLUTION_CONFIDENCE = 0.30

# Maximum recommended presets returned
_MAX_RECOMMENDED = 5


# ---------------------------------------------------------------------------
# Evolution templates: market → evolved style overrides
# ---------------------------------------------------------------------------

_EVOLUTION_TEMPLATES: dict[str, dict] = {
    "tiktok": {
        "name_suffix": "v2",
        "name_label": "TikTok Viral v2",
        "subtitle_style": "compact",
        "pacing_style": "fast_hook",
        "camera_style": "dynamic_safe",
        "hook_style": "strong_open",
        "explanation": "Stronger hook, compact subtitle, faster pacing",
    },
    "viral_tiktok": {
        "name_suffix": "v2",
        "name_label": "TikTok Viral v2",
        "subtitle_style": "compact",
        "pacing_style": "fast_hook",
        "camera_style": "dynamic_safe",
        "hook_style": "strong_open",
        "explanation": "Stronger hook, compact subtitle, faster pacing",
    },
    "youtube_shorts": {
        "name_suffix": "v2",
        "name_label": "YouTube Shorts v2",
        "subtitle_style": "readable",
        "pacing_style": "medium_fast",
        "camera_style": "creator_framing",
        "hook_style": "curiosity_hook",
        "explanation": "Curiosity hook, readable subtitle, medium-fast pacing",
    },
    "facebook_reels": {
        "name_suffix": "v2",
        "name_label": "Facebook Reels v2",
        "subtitle_style": "medium_density",
        "pacing_style": "smooth_engagement",
        "camera_style": "social_framing",
        "hook_style": "emotional_hook",
        "explanation": "Emotional hook, social framing, engagement pacing",
    },
    "podcast": {
        "name_suffix": "v2",
        "name_label": "Podcast Clean v2",
        "subtitle_style": "readable",
        "pacing_style": "calm_storytelling",
        "camera_style": "static_podcast",
        "hook_style": "soft_open",
        "explanation": "Readability-first subtitle, calm pacing, stable framing",
    },
    "educational": {
        "name_suffix": "Pro",
        "name_label": "Educational Pro",
        "subtitle_style": "clean_readable",
        "pacing_style": "clarity_first",
        "camera_style": "static_framing",
        "hook_style": "curiosity_hook",
        "explanation": "Clean subtitle, clarity-first pacing",
    },
}


def build_preset_evolution_pack(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> AIPresetEvolutionPack:
    """Build preset evolution pack from AI plan signals. Never raises.

    Args:
        edit_plan: AIEditPlan (or None) with Phase 41–45 signals.
        payload:   Render request (read-only, never mutated).
        context:   Optional session context.

    Returns:
        AIPresetEvolutionPack with recommended and evolved presets.
    """
    try:
        return _build(edit_plan, payload, context)
    except Exception as exc:
        logger.debug("preset_evolution_engine_error: %s", exc)
        return AIPresetEvolutionPack(
            available=True,
            enabled=False,
            warnings=[f"preset_evolution_error:{type(exc).__name__}"],
        )


def _build(
    edit_plan: Any,
    payload: Any,
    context: Optional[dict],
) -> AIPresetEvolutionPack:
    ctx = context or {}
    warnings: list[str] = []

    # Resolve target market/style
    target_market = _resolve_target_market(edit_plan, payload, ctx)

    # Load evolved presets (falls back to built-ins on error)
    logger.debug("ai_preset_evolution_started market=%s", target_market)
    presets = load_evolved_presets()

    # Score all loaded presets
    scored: list[tuple[float, AICreatorPreset]] = []
    for preset in presets:
        score = score_creator_preset(preset, edit_plan=edit_plan, context=ctx)
        scored.append((score, preset))

    # Sort descending by score
    scored.sort(key=lambda x: x[0], reverse=True)

    # Select recommended presets
    recommended: list[dict] = []
    for score, preset in scored[:_MAX_RECOMMENDED]:
        if score >= _MIN_RECOMMEND_SCORE:
            d = sanitize_preset(preset.to_dict())
            d["_score"] = round(score, 2)
            recommended.append(d)
            logger.debug("ai_preset_recommended preset_id=%s score=%.1f", preset.preset_id, score)

    # Evolve: generate next-generation variants based on target market
    evolved: list[dict] = []
    best_preset_id = ""

    confidence = _compute_confidence(edit_plan)
    if confidence >= _MIN_EVOLUTION_CONFIDENCE and target_market:
        base_preset = _find_best_base_preset(scored, target_market)
        if base_preset is not None:
            evolved_preset = _evolve_preset(base_preset, target_market, edit_plan)
            if evolved_preset is not None:
                evolved_score = score_creator_preset(evolved_preset, edit_plan=edit_plan, context=ctx)
                d = sanitize_preset(evolved_preset.to_dict())
                d["_score"] = round(evolved_score, 2)
                evolved.append(d)
                best_preset_id = evolved_preset.preset_id
                logger.info(
                    "ai_preset_evolved preset_id=%s generation=%d market=%s score=%.1f",
                    evolved_preset.preset_id, evolved_preset.evolution_generation,
                    target_market, evolved_score,
                )
    elif not target_market:
        warnings.append("preset_evolution_skipped_no_target_market")
        logger.debug("ai_preset_evolution_skipped reason=no_target_market")
    else:
        warnings.append(f"preset_evolution_skipped_confidence_too_low:{confidence:.2f}")
        logger.debug("ai_preset_evolution_skipped reason=confidence_too_low confidence=%.2f", confidence)

    # Best preset from recommended if no evolved preset yet
    if not best_preset_id and recommended:
        best_preset_id = recommended[0].get("preset_id", "")

    if recommended:
        logger.info("ai_preset_recommended count=%d best=%s", len(recommended), best_preset_id)

    enabled = bool(recommended or evolved)

    return AIPresetEvolutionPack(
        available=True,
        enabled=enabled,
        evolution_mode="assistive_only",
        recommended_presets=recommended,
        evolved_presets=evolved,
        best_preset_id=best_preset_id,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_target_market(edit_plan: Any, payload: Any, ctx: dict) -> str:
    """Resolve target market from context > payload > edit_plan. Never raises."""
    try:
        # Context takes priority
        if ctx.get("target_market"):
            return str(ctx["target_market"]).lower()

        # Payload attributes
        for attr in ("ai_target_market", "ai_mode"):
            val = getattr(payload, attr, None)
            if val:
                return str(val).lower()

        # Edit plan creator_style_adaptation or mode
        if edit_plan is not None:
            csa = _get_dict(edit_plan, "creator_style_adaptation")
            if csa.get("adapted_style"):
                return str(csa["adapted_style"]).lower()
            mode = getattr(edit_plan, "mode", None)
            if mode:
                return str(mode).lower()

        return ""
    except Exception:
        return ""


def _find_best_base_preset(
    scored: list[tuple[float, AICreatorPreset]],
    target_market: str,
) -> Optional[AICreatorPreset]:
    """Find the best-scoring preset that matches the target market. Never raises."""
    try:
        # Prefer exact market_type match
        for score, preset in scored:
            if preset.market_type == target_market or preset.creator_style == target_market:
                return preset
        # Fall back to generation-1 builtin of matching style
        for score, preset in scored:
            if target_market in preset.tags:
                return preset
        # Final fallback: top preset
        if scored:
            return scored[0][1]
        return None
    except Exception:
        return None


def _evolve_preset(
    base: AICreatorPreset,
    target_market: str,
    edit_plan: Any,
) -> Optional[AICreatorPreset]:
    """Generate a next-generation evolved preset from base. Never raises."""
    try:
        template = _EVOLUTION_TEMPLATES.get(target_market) or _EVOLUTION_TEMPLATES.get(
            base.creator_style
        )
        if template is None:
            return None

        next_gen = base.evolution_generation + 1
        evolved_id = f"{base.preset_id.rstrip('0123456789').rstrip('_v')}_v{next_gen}"
        evolved_name = template.get("name_label") or f"{base.preset_name} {template.get('name_suffix', 'v2')}"

        # Amplify scores using Phase 44 market profile confidence
        quality_boost = _market_quality_boost(edit_plan)
        creator_boost = _adaptive_creator_boost(edit_plan)

        new_quality = _clamp_score(base.quality_score + quality_boost)
        new_creator_fit = _clamp_score(base.creator_fit_score + creator_boost)
        new_market_fit = _clamp_score(base.market_fit_score + quality_boost)
        new_confidence = _clamp_confidence(base.confidence + 0.05)

        evolved = AICreatorPreset(
            preset_id=evolved_id,
            preset_name=evolved_name,
            creator_style=base.creator_style,
            market_type=base.market_type or target_market,
            subtitle_style=template.get("subtitle_style") or base.subtitle_style,
            pacing_style=template.get("pacing_style") or base.pacing_style,
            camera_style=template.get("camera_style") or base.camera_style,
            hook_style=template.get("hook_style") or base.hook_style,
            quality_score=new_quality,
            creator_fit_score=new_creator_fit,
            market_fit_score=new_market_fit,
            evolution_generation=next_gen,
            confidence=new_confidence,
            tags=list(base.tags) + [f"gen{next_gen}"],
            warnings=[],
            explanation=[template.get("explanation") or f"Evolved from {base.preset_name}"],
        )
        return evolved
    except Exception as exc:
        logger.debug("preset_evolve_error: %s", exc)
        return None


def _market_quality_boost(edit_plan: Any) -> float:
    """Derive quality boost from Phase 44 market confidence. Never raises."""
    try:
        if edit_plan is None:
            return 0.0
        moi = _get_dict(edit_plan, "market_optimization_intelligence")
        if not moi.get("enabled"):
            return 0.0
        profile = moi.get("market_profile") or {}
        confidence = float(profile.get("confidence") or 0.0)
        return _clamp_score(confidence * 10.0)
    except Exception:
        return 0.0


def _adaptive_creator_boost(edit_plan: Any) -> float:
    """Derive creator fit boost from Phase 42 adaptive signals. Never raises."""
    try:
        if edit_plan is None:
            return 0.0
        aci = _get_dict(edit_plan, "adaptive_creator_intelligence")
        if not aci.get("enabled"):
            return 0.0
        profile = aci.get("creator_profile") or {}
        style_conf = float(profile.get("style_confidence") or 0.0)
        return _clamp_score(style_conf * 8.0)
    except Exception:
        return 0.0


def _compute_confidence(edit_plan: Any) -> float:
    """Compute evolution confidence from signal richness. Never raises."""
    try:
        signals = 0
        if edit_plan is not None:
            for attr in ("adaptive_creator_intelligence", "creator_feedback_intelligence",
                         "market_optimization_intelligence", "render_quality_evaluation",
                         "creator_retrieval"):
                d = _get_dict(edit_plan, attr)
                if d and (d.get("available") or d.get("enabled") or len(d) > 1):
                    signals += 1
        return _clamp_confidence(min(1.0, signals / 5.0))
    except Exception:
        return 0.0


def _get_dict(edit_plan: Any, attr: str) -> dict:
    """Safely retrieve a dict attribute from edit_plan. Never raises."""
    try:
        if edit_plan is None:
            return {}
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}
