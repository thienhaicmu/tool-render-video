"""
strategy_reasoner.py — Best Strategy Reasoning Engine. Phase 51C.

Turns Phase 51B variant evaluation into clear, creator-facing reasoning that explains
why the best strategy variant was selected and what tradeoffs it represents.

Reasoning is explanation-only — no variant is executed, no render pipeline is altered,
no executor authority is affected.

Public API:
    build_best_strategy_reasoning(edit_plan) -> BestStrategyReasoning

Safety contract:
    ❌ No render pipeline rewrite
    ❌ No FFmpeg mutation
    ❌ No subtitle timing rewrite
    ❌ No executor override
    ❌ No autonomous execution
    ❌ No variant application to render
    ✅ Deterministic — same inputs always produce same output
    ✅ Never raises
    ✅ Reasoning-only — explains, never executes
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

from app.ai.strategy_variants.reasoning_schema import (
    BestStrategyReasoning,
    ALLOWED_STRENGTHS,
    _CONF_WEAK_MAX,
    _CONF_MODERATE_MAX,
    _SCORE_GAP_STRONG,
)

logger = logging.getLogger("app.ai.strategy_variants.reasoner")

# Human-readable labels for variant IDs
_VARIANT_LABELS = {
    "creator_safe":     "Creator Safe",
    "market_balanced":  "Market Balanced",
    "quality_focused":  "Quality Focused",
}

# Creator-facing dimension names
_DIM_LABELS = {
    "creator_fit": "creator alignment",
    "market_fit":  "market alignment",
    "quality_fit": "quality and readability",
    "safety_fit":  "safety confidence",
}


def build_best_strategy_reasoning(edit_plan: Any) -> BestStrategyReasoning:
    """Build creator-facing reasoning for the best evaluated strategy. Never raises.

    Args:
        edit_plan: AIEditPlan with variant_evaluation (51B), strategy_variants (51A),
                   and creator_preference_profile (50D).

    Returns:
        BestStrategyReasoning — explanation-only, never applied to render.
    """
    try:
        return _build(edit_plan)
    except Exception as exc:
        logger.debug("strategy_reasoning_error: %s", exc)
        return BestStrategyReasoning(
            warnings=[f"reasoning_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any) -> BestStrategyReasoning:
    if edit_plan is None:
        return BestStrategyReasoning(warnings=["no_edit_plan"])

    ve      = _attr(edit_plan, "variant_evaluation")
    profile = _attr(edit_plan, "creator_preference_profile")

    if not ve.get("available"):
        return BestStrategyReasoning(warnings=["evaluation_unavailable"])

    ranking     = ve.get("ranking") or []
    best_id     = ve.get("best_variant_id")
    ve_conf     = _safe_float(ve.get("confidence"))

    if not best_id or not ranking:
        return BestStrategyReasoning(
            confidence=ve_conf,
            warnings=["no_best_variant"],
        )

    best   = next((r for r in ranking if r.get("id") == best_id), None)
    runner = ranking[1] if len(ranking) > 1 else None

    if best is None:
        return BestStrategyReasoning(
            confidence=ve_conf,
            warnings=["best_variant_not_in_ranking"],
        )

    label    = _VARIANT_LABELS.get(best_id, best_id.replace("_", " ").title())
    strength = _recommendation_strength(ve_conf, best, runner)
    why      = _build_why_selected(best_id, best, profile)
    tradeoffs = _build_tradeoffs(best_id, best, runner)
    summary  = _build_summary(best_id, strength, best, profile)

    return BestStrategyReasoning(
        selected_variant_id=best_id,
        selected_label=label,
        confidence=ve_conf,
        summary=summary,
        why_selected=why,
        tradeoffs=tradeoffs,
        recommendation_strength=strength,
    )


# ---------------------------------------------------------------------------
# Recommendation strength
# ---------------------------------------------------------------------------

def _recommendation_strength(
    conf: float, best: dict, runner: Optional[dict]
) -> str:
    if conf <= 0.0:
        return "none"
    if conf < _CONF_WEAK_MAX:
        return "weak"
    if conf <= _CONF_MODERATE_MAX:
        return "moderate"
    # conf > 0.82 — strong only if score gap is clear AND a runner-up exists to compare
    if runner is None:
        return "moderate"
    best_score   = int(best.get("score") or 0)
    runner_score = int(runner.get("score") or 0)
    gap = best_score - runner_score
    if gap >= _SCORE_GAP_STRONG:
        return "strong"
    return "moderate"


# ---------------------------------------------------------------------------
# Why-selected reasoning
# ---------------------------------------------------------------------------

def _build_why_selected(
    best_id: str, best: dict, profile: dict
) -> List[str]:
    lines: List[str] = []

    creator_f = int(best.get("creator_fit") or 0)
    market_f  = int(best.get("market_fit")  or 0)
    quality_f = int(best.get("quality_fit") or 0)
    safety_f  = int(best.get("safety_fit")  or 0)

    # Variant-specific primary strength explanation
    if best_id == "creator_safe":
        if creator_f >= 70:
            lines.append("Directly preserves your established subtitle and camera preferences")
        else:
            lines.append("Keeps AI changes aligned with your content style")
    elif best_id == "market_balanced":
        if market_f >= 65:
            lines.append("Best alignment with target market audience expectations")
        else:
            lines.append("Balances creator style with market performance signals")
    elif best_id == "quality_focused":
        if quality_f >= 70:
            lines.append("Strongest subtitle readability and camera smoothness scores")
        else:
            lines.append("Optimized for overall output quality signals")

    # Highest scoring dimension (skip safety_fit as primary — it's structural)
    dims = [
        ("creator_fit", creator_f),
        ("market_fit",  market_f),
        ("quality_fit", quality_f),
    ]
    top_dim, top_score = max(dims, key=lambda x: x[1])
    if top_score >= 60:
        lines.append(
            f"Highest {_DIM_LABELS[top_dim]} score among evaluated strategies"
        )

    # Safety confidence mention when high
    if safety_f >= 85:
        lines.append("High safety confidence — conservative, bounded strategy")

    # Creator profile alignment note
    if profile.get("available") and best_id != "creator_safe":
        p_sub   = (profile.get("subtitle") or {}).get("style", "unknown")
        b_style = (best.get("subtitle")    or {}).get("style", "unknown")
        if p_sub != "unknown" and p_sub == b_style:
            lines.append("Subtitle style aligns with your creator preferences")

    return lines[:4]


# ---------------------------------------------------------------------------
# Tradeoffs
# ---------------------------------------------------------------------------

def _build_tradeoffs(
    best_id: str, best: dict, runner: Optional[dict]
) -> List[str]:
    if runner is None:
        return []

    lines: List[str] = []
    runner_id    = str(runner.get("id") or "")
    runner_label = _VARIANT_LABELS.get(runner_id, runner_id.replace("_", " ").title())
    best_score   = int(best.get("score")   or 0)
    runner_score = int(runner.get("score") or 0)
    gap          = best_score - runner_score

    # Only surface tradeoff when runner is within 15 points
    if gap <= 15 and runner_id:
        best_label = _VARIANT_LABELS.get(best_id, best_id.replace("_", " ").title())
        lines.append(
            f"{best_label} was selected over {runner_label}"
            f" for stronger {_leading_dimension(best, runner)} alignment"
        )

    # Mention what the runner offers that the winner doesn't lead on
    if runner_id == "market_balanced":
        runner_market = int(runner.get("market_fit") or 0)
        best_market   = int(best.get("market_fit")   or 0)
        if runner_market > best_market + 10:
            lines.append(
                f"The {runner_label} strategy offers stronger market alignment"
                " if platform reach is the primary goal"
            )
    elif runner_id == "creator_safe":
        runner_cf = int(runner.get("creator_fit") or 0)
        best_cf   = int(best.get("creator_fit")   or 0)
        if runner_cf > best_cf + 10:
            lines.append(
                f"The {runner_label} strategy more closely mirrors your historical preferences"
            )
    elif runner_id == "quality_focused":
        runner_qf = int(runner.get("quality_fit") or 0)
        best_qf   = int(best.get("quality_fit")   or 0)
        if runner_qf > best_qf + 10:
            lines.append(
                f"The {runner_label} strategy offers stronger readability and smoothness"
            )

    return lines[:2]


def _leading_dimension(best: dict, runner: dict) -> str:
    """Return human-readable name of the dimension where best leads runner most."""
    dims = ["creator_fit", "market_fit", "quality_fit", "safety_fit"]
    gaps = {
        d: int(best.get(d) or 0) - int(runner.get(d) or 0)
        for d in dims
    }
    top_dim = max(gaps, key=lambda d: gaps[d])
    return _DIM_LABELS.get(top_dim, top_dim.replace("_", " "))


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _build_summary(
    best_id: str, strength: str, best: dict, profile: dict
) -> str:
    label = _VARIANT_LABELS.get(best_id, best_id.replace("_", " ").title())

    if strength == "none":
        return "No confident AI strategy recommendation available."

    quality_f = int(best.get("quality_fit") or 0)
    creator_f = int(best.get("creator_fit") or 0)
    market_f  = int(best.get("market_fit")  or 0)

    if best_id == "creator_safe":
        if strength == "strong":
            return (
                f"{label} strategy strongly recommended — "
                "matches your established content preferences with high confidence."
            )
        return (
            f"{label} strategy recommended — "
            "aligned with your creator preferences and output quality signals."
        )

    if best_id == "market_balanced":
        if strength == "strong":
            return (
                f"{label} strategy strongly recommended — "
                "best balance of market performance and content quality."
            )
        return (
            f"{label} strategy recommended — "
            "balances your style with target market audience expectations."
        )

    if best_id == "quality_focused":
        if strength == "strong":
            return (
                f"{label} strategy strongly recommended — "
                "highest readability and smoothness scores across evaluated variants."
            )
        return (
            f"{label} strategy recommended — "
            "optimized for subtitle readability and camera smoothness quality."
        )

    # Generic fallback
    return f"{label} strategy selected as best evaluated option."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attr(obj: Any, name: str) -> dict:
    try:
        val = getattr(obj, name, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_float(v: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(v or 0.0))), 2)
    except (TypeError, ValueError):
        return 0.0
