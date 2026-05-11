"""
variant_evaluator.py — Variant Evaluation Engine. Phase 51B.

Deterministically scores and ranks the safe strategy variants produced by Phase 51A
using four signal dimensions: creator_fit, market_fit, quality_fit, safety_fit.

Evaluation is metadata-only — no variant is selected for execution, no render
pipeline is altered, no executor authority is affected.

Public API:
    evaluate_strategy_variants(edit_plan) -> VariantEvaluationPack

Safety contract:
    ❌ No render pipeline rewrite
    ❌ No FFmpeg mutation
    ❌ No subtitle timing rewrite
    ❌ No executor override
    ❌ No autonomous execution
    ❌ No variant application to render
    ✅ Deterministic — same inputs always produce same output
    ✅ Never raises
    ✅ Evaluation-only — scores and ranks, never executes
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from app.ai.strategy_variants.evaluation_schema import (
    VariantEvaluationPack,
    VariantScore,
)

logger = logging.getLogger("app.ai.strategy_variants.evaluator")

# ---------------------------------------------------------------------------
# Scoring weights (must sum to 1.0)
# ---------------------------------------------------------------------------

_W_CREATOR = 0.35
_W_QUALITY = 0.30
_W_MARKET  = 0.20
_W_SAFETY  = 0.15

# Deterministic variant ordering for tie-breaking
_VARIANT_ORDER = {"creator_safe": 0, "market_balanced": 1, "quality_focused": 2}


def evaluate_strategy_variants(edit_plan: Any) -> VariantEvaluationPack:
    """Score and rank Phase 51A strategy variants. Never raises.

    Args:
        edit_plan: AIEditPlan with strategy_variants (51A), creator_preference_profile (50D),
                   market_optimization_intelligence (44), and render_quality_evaluation (45).

    Returns:
        VariantEvaluationPack — evaluation-only, never applied to render.
    """
    try:
        return _evaluate(edit_plan)
    except Exception as exc:
        logger.debug("variant_evaluation_error: %s", exc)
        return VariantEvaluationPack(
            available=False,
            warnings=[f"evaluation_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def _evaluate(edit_plan: Any) -> VariantEvaluationPack:
    if edit_plan is None:
        return VariantEvaluationPack(available=False, warnings=["no_edit_plan"])

    sv_pack  = _attr(edit_plan, "strategy_variants")
    profile  = _attr(edit_plan, "creator_preference_profile")
    market   = _attr(edit_plan, "market_optimization_intelligence")
    quality  = _attr(edit_plan, "render_quality_evaluation")

    variants = sv_pack.get("strategy_variants") or []
    if not variants:
        return VariantEvaluationPack(
            available=False,
            warnings=["no_variants_to_evaluate"],
        )

    # Pre-compute shared quality averages once
    q_avg_sub, q_avg_cam = _quality_averages(quality)

    scored: List[VariantScore] = []
    for v in variants:
        if not isinstance(v, dict):
            continue
        vs = _score_variant(v, profile, market, quality, q_avg_sub, q_avg_cam)
        if vs is not None:
            scored.append(vs)

    if not scored:
        return VariantEvaluationPack(
            available=False,
            warnings=["no_valid_variants_scored"],
        )

    # Deterministic sort: score desc → safety_fit desc → creator_fit desc → order asc
    scored.sort(
        key=lambda x: (
            -x.score,
            -x.safety_fit,
            -x.creator_fit,
            _VARIANT_ORDER.get(x.id, 99),
        )
    )

    best_id   = scored[0].id
    pack_conf = _compute_pack_confidence(scored, profile, market, quality)
    reasoning = _build_pack_reasoning(scored, best_id, profile)

    return VariantEvaluationPack(
        available=True,
        best_variant_id=best_id,
        ranking=scored,
        confidence=pack_conf,
        reasoning=reasoning,
        evaluation_mode="evaluation_only",
    )


# ---------------------------------------------------------------------------
# Single variant scoring
# ---------------------------------------------------------------------------

def _score_variant(
    variant:   dict,
    profile:   dict,
    market:    dict,
    quality:   dict,
    q_avg_sub: float,
    q_avg_cam: float,
) -> Optional[VariantScore]:
    vid = str(variant.get("id") or "unknown")
    if not vid or vid == "unknown":
        return None

    conf       = _safe_float(variant.get("confidence"))
    creator_f  = _score_creator_fit(vid, variant, profile)
    market_f   = _score_market_fit(vid, variant, market, profile)
    quality_f  = _score_quality_fit(vid, variant, q_avg_sub, q_avg_cam)
    safety_f   = _score_safety_fit(vid, variant, conf)

    composite = round(
        creator_f * _W_CREATOR
        + quality_f * _W_QUALITY
        + market_f  * _W_MARKET
        + safety_f  * _W_SAFETY
    )
    composite = max(0, min(100, composite))

    reasoning = _build_variant_reasoning(vid, creator_f, market_f, quality_f, safety_f)

    return VariantScore(
        id=vid,
        score=composite,
        creator_fit=creator_f,
        market_fit=market_f,
        quality_fit=quality_f,
        safety_fit=safety_f,
        confidence=conf,
        reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Dimension scorers
# ---------------------------------------------------------------------------

def _score_creator_fit(vid: str, variant: dict, profile: dict) -> int:
    conf  = _safe_float(profile.get("confidence"))
    p_sub = profile.get("subtitle") or {}
    p_cam = profile.get("camera")   or {}

    if vid == "creator_safe":
        if not profile.get("available"):
            return 35
        base = int(conf * 80)           # 0–80 from profile confidence
        v_sub = variant.get("subtitle") or {}
        v_cam = variant.get("camera")   or {}
        if v_sub.get("style", "unknown") != "unknown":
            base += 8                   # known style present
        if v_cam.get("motion_style", "unknown") != "unknown":
            base += 7                   # known motion present
        return _clamp(base)

    elif vid == "market_balanced":
        base = 45
        v_sub   = variant.get("subtitle") or {}
        v_cam   = variant.get("camera")   or {}
        c_style = p_sub.get("style", "unknown")
        c_mot   = p_cam.get("motion_style", "unknown")
        if c_style != "unknown" and c_style == v_sub.get("style"):
            base += 20
        if c_mot != "unknown" and c_mot == v_cam.get("motion_style"):
            base += 10
        return _clamp(base)

    elif vid == "quality_focused":
        base = 40
        read  = p_sub.get("readability_priority", "unknown")
        smooth = p_cam.get("smoothness_priority", "unknown")
        if read == "high":
            base += 20
        elif read == "medium":
            base += 8
        if smooth in ("high", "medium"):
            base += 10
        return _clamp(base)

    return 40


def _score_market_fit(
    vid: str, variant: dict, market: dict, profile: dict
) -> int:
    mp     = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower().strip()
    mp_conf = _safe_float(mp.get("confidence"))

    if not target or target == "unknown":
        # No market data — all variants get conservative neutral score
        return 45

    if vid == "market_balanced":
        # Variant is directly market-derived; score from market confidence
        base = int(mp_conf * 70) + 15
        return _clamp(base)

    elif vid == "creator_safe":
        # Check if creator preferences happen to align with market target
        v_sub = variant.get("subtitle") or {}
        v_cam = variant.get("camera")   or {}
        base  = 40
        if v_sub.get("style") == _market_subtitle_style(target):
            base += 25
        if v_cam.get("motion_style") == _market_camera_motion(target):
            base += 15
        return _clamp(base)

    elif vid == "quality_focused":
        # Quality-focused fits quality-oriented markets better
        base = 45
        if "educational" in target or "podcast" in target:
            base += 20
        elif "youtube" in target or "shorts" in target:
            base += 10
        return _clamp(base)

    return 45


def _score_quality_fit(
    vid: str, variant: dict, q_avg_sub: float, q_avg_cam: float
) -> int:
    has_scores = q_avg_sub > 0.0 or q_avg_cam > 0.0

    if vid == "quality_focused":
        if not has_scores:
            return 55   # Designed for quality even without score data
        base = int((q_avg_sub * 0.55 + q_avg_cam * 0.45) * 65) + 25
        return _clamp(base)

    elif vid == "creator_safe":
        v_sub = variant.get("subtitle") or {}
        v_cam = variant.get("camera")   or {}
        base  = 45
        density = v_sub.get("density", "unknown")
        if density in ("light", "medium"):
            base += 12
        if v_cam.get("stability_priority") == "high":
            base += 8
        if v_cam.get("crop_aggressiveness") == "low":
            base += 5
        if has_scores:
            base += int(q_avg_sub * 15)
        return _clamp(base)

    elif vid == "market_balanced":
        base = 45
        if has_scores:
            base += int((q_avg_sub * 0.3 + q_avg_cam * 0.3) * 30)
        return _clamp(base)

    return 45


def _score_safety_fit(vid: str, variant: dict, conf: float) -> int:
    # All Phase 51A variants are structurally safe — safety_fit is always high
    base = 75
    if conf >= 0.75:
        base += 15
    elif conf >= 0.50:
        base += 8
    elif conf > 0.0:
        base += 3
    # Bonus for stability/low-crop indicators
    v_cam = variant.get("camera") or {}
    if v_cam.get("stability_priority") == "high":
        base += 5
    if v_cam.get("crop_aggressiveness") == "low":
        base += 3
    return _clamp(base)


# ---------------------------------------------------------------------------
# Pack-level confidence
# ---------------------------------------------------------------------------

def _compute_pack_confidence(
    scored:  List[VariantScore],
    profile: dict,
    market:  dict,
    quality: dict,
) -> float:
    sources: List[float] = []

    if profile.get("available"):
        sources.append(_safe_float(profile.get("confidence")))

    mp = market.get("market_profile") or {}
    mp_conf = _safe_float(mp.get("confidence"))
    if mp_conf > 0.0:
        sources.append(mp_conf)

    q_sub, q_cam = _quality_averages(quality)
    if q_sub > 0.0 or q_cam > 0.0:
        sources.append((q_sub + q_cam) / 2.0)

    if scored:
        avg_var_conf = sum(v.confidence for v in scored) / len(scored)
        sources.append(avg_var_conf)

    if not sources:
        return 0.0

    return round(max(0.0, min(1.0, sum(sources) / len(sources))), 2)


# ---------------------------------------------------------------------------
# Reasoning builders
# ---------------------------------------------------------------------------

def _build_variant_reasoning(
    vid: str, cf: int, mf: int, qf: int, sf: int
) -> List[str]:
    lines: List[str] = []

    if vid == "creator_safe":
        lines.append("Directly mirrors creator preference profile — maximum creator alignment")
    elif vid == "market_balanced":
        lines.append("Derived from target market profile — balanced market optimization")
    elif vid == "quality_focused":
        lines.append("Optimizes subtitle readability and camera smoothness signals")

    dominant = max(("creator_fit", cf), ("market_fit", mf),
                   ("quality_fit", qf), ("safety_fit", sf),
                   key=lambda x: x[1])
    lines.append(f"Highest dimension: {dominant[0]}={dominant[1]}")
    return lines


def _build_pack_reasoning(
    scored: List[VariantScore], best_id: str, profile: dict
) -> List[str]:
    lines: List[str] = []
    if scored:
        best = scored[0]
        lines.append(
            f"'{best_id}' ranked first with composite score={best.score}"
        )
        if len(scored) > 1:
            gap = best.score - scored[1].score
            lines.append(
                f"Score gap to runner-up '{scored[1].id}': {gap} point(s)"
            )
    if profile.get("available"):
        lines.append("Creator preference profile available — creator_fit dimension active")
    return lines[:3]


# ---------------------------------------------------------------------------
# Market helpers (mirrors Phase 51A generator, local-only)
# ---------------------------------------------------------------------------

def _market_subtitle_style(target: str) -> str:
    if "tiktok" in target or "reels" in target or "instagram" in target:
        return "viral_bold"
    if "podcast" in target or "educational" in target:
        return "clean_pro"
    if "youtube" in target or "shorts" in target:
        return "clean_pro"
    return "unknown"


def _market_camera_motion(target: str) -> str:
    if "tiktok" in target or "reels" in target or "instagram" in target:
        return "dynamic_subject"
    if "podcast" in target or "educational" in target:
        return "static_center"
    if "youtube" in target or "shorts" in target:
        return "smooth_subject"
    return "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _quality_averages(quality: dict) -> Tuple[float, float]:
    scores = quality.get("output_scores") or []
    valid  = [s for s in scores if isinstance(s, dict)]
    if not valid:
        return 0.0, 0.0
    avg_sub = sum(float(s.get("subtitle_readability") or 0.0) for s in valid) / len(valid)
    avg_cam = sum(float(s.get("camera_smoothness")   or 0.0) for s in valid) / len(valid)
    return avg_sub, avg_cam


def _attr(obj: Any, name: str) -> dict:
    try:
        val = getattr(obj, name, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_float(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _clamp(v: float) -> int:
    return max(0, min(100, round(v)))
