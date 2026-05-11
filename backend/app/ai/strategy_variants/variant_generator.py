"""
variant_generator.py — Safe Strategy Variant Generator. Phase 51A.

Generates up to 3 deterministic, metadata-only candidate strategy variants
from unified creator preference, market intelligence, and quality intelligence.

Variants are candidate-only — never evaluated, never selected, never applied.
Phase 51B Variant Evaluation Engine will evaluate and rank them.

Public API:
    generate_strategy_variants(edit_plan) -> StrategyVariantPack

Safety contract:
    ❌ No render pipeline rewrite
    ❌ No FFmpeg mutation
    ❌ No subtitle timing rewrite
    ❌ No motion_crop rewrite
    ❌ No executor override
    ❌ No autonomous execution
    ✅ Deterministic — same inputs always produce same output
    ✅ Never raises
    ✅ Candidate-only — no evaluation, no selection, no execution
"""
from __future__ import annotations

import logging
from typing import Any, List

from app.ai.strategy_variants.variant_schema import (
    StrategyVariant,
    StrategyVariantPack,
    StrategyVariantSubtitle,
    StrategyVariantCamera,
    StrategyVariantRanking,
    ALLOWED_SUBTITLE_STYLES,
    ALLOWED_SUBTITLE_DENSITY,
    ALLOWED_KEYWORD_EMPHASIS,
    ALLOWED_CAMERA_MOTION,
    ALLOWED_STABILITY_PRIORITY,
    ALLOWED_CROP_AGGRESSIVENESS,
    ALLOWED_RANKING_PRIORITY,
)

logger = logging.getLogger("app.ai.strategy_variants.generator")


def generate_strategy_variants(edit_plan: Any) -> StrategyVariantPack:
    """Generate safe candidate strategy variants from available AI metadata.

    Deterministic order: creator_safe → market_balanced → quality_focused.
    Maximum 3 variants. Never raises.

    Args:
        edit_plan: AIEditPlan with Phase 50D creator_preference_profile,
                   Phase 44 market_optimization_intelligence, and
                   Phase 45 render_quality_evaluation.

    Returns:
        StrategyVariantPack — candidate-only, never applied to render.
    """
    try:
        return _generate(edit_plan)
    except Exception as exc:
        logger.debug("strategy_variants_generation_error: %s", exc)
        return StrategyVariantPack(
            available=False,
            warnings=[f"generation_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Core generation
# ---------------------------------------------------------------------------

def _generate(edit_plan: Any) -> StrategyVariantPack:
    if edit_plan is None:
        return StrategyVariantPack(available=False, warnings=["no_edit_plan"])

    profile = _attr(edit_plan, "creator_preference_profile")
    market  = _attr(edit_plan, "market_optimization_intelligence")
    quality = _attr(edit_plan, "render_quality_evaluation")

    variants: List[StrategyVariant] = []
    warnings: List[str] = []

    # 1. creator_safe — always first; fallback when profile unavailable
    v_creator = _build_creator_safe(profile)
    if v_creator is not None:
        variants.append(v_creator)
    else:
        variants.append(_build_fallback_creator_safe())
        warnings.append("creator_profile_unavailable:conservative_fallback_used")

    # 2. market_balanced — only when market data is present
    v_market = _build_market_balanced(market)
    if v_market is not None:
        variants.append(v_market)

    # 3. quality_focused — only when quality scores are present
    v_quality = _build_quality_focused(quality)
    if v_quality is not None:
        variants.append(v_quality)

    return StrategyVariantPack(
        available=True,
        strategy_variants=variants,
        variant_count=len(variants),
        generation_mode="candidate_only",
        warnings=warnings[:5],
    )


# ---------------------------------------------------------------------------
# Variant builders
# ---------------------------------------------------------------------------

def _build_creator_safe(profile: dict) -> StrategyVariant | None:
    """Build creator_safe variant from Phase 50D unified creator preference profile."""
    if not profile.get("available"):
        return None

    sub  = profile.get("subtitle") or {}
    cam  = profile.get("camera")   or {}
    clip = profile.get("clip")     or {}
    conf = _safe_float(profile.get("confidence"))

    subtitle = StrategyVariantSubtitle(
        style=_safe_val(sub.get("style"),            ALLOWED_SUBTITLE_STYLES),
        density=_safe_val(sub.get("density"),         ALLOWED_SUBTITLE_DENSITY),
        keyword_emphasis=_safe_val(sub.get("keyword_emphasis"), ALLOWED_KEYWORD_EMPHASIS),
    )
    camera = StrategyVariantCamera(
        motion_style=_safe_val(cam.get("motion_style"),        ALLOWED_CAMERA_MOTION),
        stability_priority=_safe_val(cam.get("stability_priority"), ALLOWED_STABILITY_PRIORITY),
        crop_aggressiveness=_safe_val(cam.get("crop_aggressiveness"), ALLOWED_CROP_AGGRESSIVENESS),
    )

    ranking_pref = _safe_val(clip.get("ranking_preference"), ALLOWED_RANKING_PRIORITY)
    if ranking_pref == "unknown":
        ranking_pref = "creator_fit"
    ranking = StrategyVariantRanking(priority=ranking_pref)

    style  = subtitle.style
    motion = camera.motion_style
    reasoning = ["Matches unified creator preference profile from Phase 50D fusion"]
    if style != "unknown" or motion != "unknown":
        reasoning.append(
            f"Preserves subtitle style={style!r} and camera motion={motion!r}"
        )

    return StrategyVariant(
        id="creator_safe",
        label="Creator Safe",
        intent="preserve creator preference",
        subtitle=subtitle,
        camera=camera,
        ranking=ranking,
        confidence=conf,
        reasoning=reasoning,
    )


def _build_fallback_creator_safe() -> StrategyVariant:
    """Conservative fallback creator_safe when Phase 50D profile is unavailable."""
    return StrategyVariant(
        id="creator_safe",
        label="Creator Safe",
        intent="fallback conservative strategy",
        subtitle=StrategyVariantSubtitle(),
        camera=StrategyVariantCamera(),
        ranking=StrategyVariantRanking(priority="balanced"),
        confidence=0.0,
        reasoning=["Conservative fallback — creator preference profile not available"],
    )


def _build_market_balanced(market: dict) -> StrategyVariant | None:
    """Build market_balanced variant from Phase 44 market intelligence."""
    mp = market.get("market_profile") or {}
    if not mp:
        return None

    target = str(mp.get("target_market") or "").lower().strip()
    if not target or target == "unknown":
        return None

    mp_conf = _safe_float(mp.get("confidence"))
    # Conservative discount: market variant carries slightly lower confidence
    confidence = round(max(0.0, mp_conf - 0.05), 2)

    subtitle = StrategyVariantSubtitle(
        style=_safe_val(_market_subtitle_style(target), ALLOWED_SUBTITLE_STYLES),
        density=_safe_val(_market_subtitle_density(target), ALLOWED_SUBTITLE_DENSITY),
        keyword_emphasis=_safe_val(_market_keyword_emphasis(target), ALLOWED_KEYWORD_EMPHASIS),
    )
    camera = StrategyVariantCamera(
        motion_style=_safe_val(_market_camera_motion(target), ALLOWED_CAMERA_MOTION),
        stability_priority="medium",
        crop_aggressiveness="medium",
    )
    ranking = StrategyVariantRanking(
        priority=_safe_val(_market_ranking_priority(target), ALLOWED_RANKING_PRIORITY)
    )

    return StrategyVariant(
        id="market_balanced",
        label="Market Balanced",
        intent="balance creator profile with target market",
        subtitle=subtitle,
        camera=camera,
        ranking=ranking,
        confidence=confidence,
        reasoning=[
            f"Balanced with {target!r} market profile",
            "Market-optimized subtitle style and camera motion",
        ],
    )


def _build_quality_focused(quality: dict) -> StrategyVariant | None:
    """Build quality_focused variant from Phase 45 render quality evaluation."""
    output_scores = quality.get("output_scores") or []
    scores = [s for s in output_scores if isinstance(s, dict)]
    if not scores:
        return None

    sub_scores = [float(s.get("subtitle_readability") or 0.0) for s in scores]
    cam_scores  = [float(s.get("camera_smoothness")   or 0.0) for s in scores]

    avg_sub = sum(sub_scores) / len(sub_scores) if sub_scores else 0.0
    avg_cam = sum(cam_scores) / len(cam_scores) if cam_scores else 0.0

    # Subtitle: readability first
    if avg_sub >= 0.70:
        sub_style = "clean_pro"
        density   = "light"
        emphasis  = "subtle"
    else:
        sub_style = "unknown"
        density   = "medium"
        emphasis  = "moderate"

    # Camera: smoothness first
    if avg_cam >= 0.40:
        cam_motion = "smooth_subject"
    else:
        cam_motion = "static_center"

    confidence = round(max(0.0, min(1.0, avg_sub * 0.5 + avg_cam * 0.5)), 2)

    subtitle = StrategyVariantSubtitle(
        style=_safe_val(sub_style, ALLOWED_SUBTITLE_STYLES),
        density=_safe_val(density, ALLOWED_SUBTITLE_DENSITY),
        keyword_emphasis=_safe_val(emphasis, ALLOWED_KEYWORD_EMPHASIS),
    )
    camera = StrategyVariantCamera(
        motion_style=_safe_val(cam_motion, ALLOWED_CAMERA_MOTION),
        stability_priority="high",
        crop_aggressiveness="low",
    )
    ranking = StrategyVariantRanking(priority="readability")

    return StrategyVariant(
        id="quality_focused",
        label="Quality Focused",
        intent="prefer readability, smoothness, and quality alignment",
        subtitle=subtitle,
        camera=camera,
        ranking=ranking,
        confidence=confidence,
        reasoning=[
            "Optimizes for subtitle readability and camera smoothness",
            f"Derived from {len(scores)} quality score(s):"
            f" sub={avg_sub:.2f}, cam={avg_cam:.2f}",
        ],
    )


# ---------------------------------------------------------------------------
# Market signal helpers (deterministic, local-only)
# ---------------------------------------------------------------------------

def _market_subtitle_style(target: str) -> str:
    if "tiktok" in target or "reels" in target or "instagram" in target:
        return "viral_bold"
    if "podcast" in target or "educational" in target:
        return "clean_pro"
    if "youtube" in target or "shorts" in target:
        return "clean_pro"
    return "unknown"


def _market_subtitle_density(target: str) -> str:
    if "tiktok" in target or "reels" in target:
        return "dense"
    if "podcast" in target or "educational" in target:
        return "light"
    return "medium"


def _market_keyword_emphasis(target: str) -> str:
    if "tiktok" in target or "reels" in target or "instagram" in target:
        return "strong"
    if "podcast" in target or "educational" in target:
        return "subtle"
    if "youtube" in target or "shorts" in target:
        return "moderate"
    return "unknown"


def _market_camera_motion(target: str) -> str:
    if "tiktok" in target or "reels" in target or "instagram" in target:
        return "dynamic_subject"
    if "podcast" in target or "educational" in target:
        return "static_center"
    if "youtube" in target or "shorts" in target:
        return "smooth_subject"
    return "unknown"


def _market_ranking_priority(target: str) -> str:
    if "tiktok" in target or "reels" in target:
        return "hook_strength"
    if "educational" in target or "podcast" in target:
        return "retention"
    if "youtube" in target or "shorts" in target:
        return "retention"
    return "balanced"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attr(obj: Any, name: str) -> dict:
    try:
        val = getattr(obj, name, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_val(v: Any, allowed: frozenset) -> str:
    s = str(v or "unknown").strip()
    return s if s in allowed else "unknown"


def _safe_float(v: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(v or 0.0))), 2)
    except (TypeError, ValueError):
        return 0.0
