"""
hook_quality_evaluator.py — Hook Quality Intelligence v2 evaluator. Phase 52C.

Orchestrates all hook quality dimension scorers into a single
HookQualityV2 result with weighted overall score, risk penalty,
and creator-facing reasoning.

Public API:
    evaluate_hook_quality_v2(edit_plan) -> dict

Safety contract:
    ❌ No hook rewriting
    ❌ No clip rewrite
    ❌ No render mutation
    ❌ No FFmpeg mutation
    ❌ No render pipeline rewrite
    ❌ No executor override
    ❌ No autonomous execution
    ✅ Evaluation-only — enriches quality metadata, never mutates
    ✅ Deterministic — same inputs always produce same output
    ✅ Never raises
    ✅ Fallback-safe — returns all-zero dict on any error
"""
from __future__ import annotations

import logging
from typing import Any, List

from app.ai.hook_quality.hook_quality_schema import (
    HookQualityV2,
    SCORE_WEIGHTS,
    _RISK_PENALTY_PER_10,
    fallback_hook_quality_v2,
)
from app.ai.hook_quality.hook_quality_scorer import (
    score_first_3s_strength,
    score_first_5s_retention,
    score_curiosity_strength,
    score_open_loop_quality,
    score_hook_fatigue_risk,
    score_market_fit,
    score_creator_fit,
    compute_confidence,
)

logger = logging.getLogger("app.ai.hook_quality.evaluator")


def evaluate_hook_quality_v2(edit_plan: Any) -> dict:
    """Evaluate hook quality across 6 dimensions + 1 risk score. Never raises.

    Args:
        edit_plan: AIEditPlan with Phase 4, 12, 16, 17, 42, 44, 46, 50D signals.

    Returns:
        dict matching the hook_quality_v2 schema spec.
        Falls back to all-zero dict on any failure.
    """
    try:
        return _evaluate(edit_plan)
    except Exception as exc:
        logger.debug("hook_quality_v2_error: %s", exc)
        return {"hook_quality_v2": fallback_hook_quality_v2()}


def _evaluate(edit_plan: Any) -> dict:
    if edit_plan is None:
        return {"hook_quality_v2": fallback_hook_quality_v2()}

    # Score all dimensions
    first_3s   = score_first_3s_strength(edit_plan)
    first_5s   = score_first_5s_retention(edit_plan)
    curiosity  = score_curiosity_strength(edit_plan)
    open_loop  = score_open_loop_quality(edit_plan)
    fatigue    = score_hook_fatigue_risk(edit_plan)
    market     = score_market_fit(edit_plan)
    creator    = score_creator_fit(edit_plan)
    confidence = compute_confidence(edit_plan)

    # Weighted positive overall
    raw_overall = (
        first_3s  * SCORE_WEIGHTS["first_3s_strength"]
        + first_5s  * SCORE_WEIGHTS["first_5s_retention"]
        + curiosity * SCORE_WEIGHTS["curiosity_strength"]
        + open_loop * SCORE_WEIGHTS["open_loop_quality"]
        + market    * SCORE_WEIGHTS["market_fit"]
        + creator   * SCORE_WEIGHTS["creator_fit"]
    )

    # Risk penalty: each 10-pt fatigue risk reduces overall conservatively
    risk_penalty = (fatigue / 10.0) * _RISK_PENALTY_PER_10

    overall = max(0, min(100, round(raw_overall - risk_penalty)))

    reasoning = _build_reasoning(
        first_3s, first_5s, curiosity, open_loop, fatigue, market, creator, edit_plan,
    )

    result = HookQualityV2(
        first_3s_strength=first_3s,
        first_5s_retention=first_5s,
        curiosity_strength=curiosity,
        open_loop_quality=open_loop,
        hook_fatigue_risk=fatigue,
        market_fit=market,
        creator_fit=creator,
        overall=overall,
        confidence=confidence,
        reasoning=reasoning,
    )

    logger.debug(
        "hook_quality_v2_done overall=%d confidence=%.2f first_3s=%d first_5s=%d "
        "curiosity=%d open_loop=%d fatigue=%d market=%d creator=%d",
        overall, confidence, first_3s, first_5s,
        curiosity, open_loop, fatigue, market, creator,
    )

    return {"hook_quality_v2": result.to_dict()}


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    first_3s: int,
    first_5s: int,
    curiosity: int,
    open_loop: int,
    fatigue: int,
    market: int,
    creator: int,
    edit_plan: Any,
) -> List[str]:
    lines: List[str] = []

    # First 3s — strongest hook quality signal
    if first_3s >= 75:
        lines.append("Opening sequence creates strong early attention")
    elif first_3s >= 55:
        lines.append("Opening hook provides moderate early engagement")
    else:
        lines.append("Opening hook signals are limited")

    # First 5s retention
    if first_5s >= 75:
        lines.append("First five seconds show strong retention potential")
    elif first_5s < 50:
        lines.append("First-five-second retention signals are weak")

    # Curiosity
    if curiosity >= 72:
        lines.append("Curiosity trigger is well established")
    elif curiosity < 50:
        lines.append("Curiosity signals could be stronger")

    # Open loop
    if open_loop >= 70:
        lines.append("Open loop creates effective payoff expectation")

    # Market fit
    if market >= 70:
        lines.append("Hook pacing aligns with target market preferences")
    elif market >= 55:
        lines.append("Market hook alignment is moderate")

    # Creator fit
    if creator >= 70:
        lines.append("Hook style matches your creator preferences")
    elif creator >= 55:
        lines.append("Hook pacing partially reflects your creator style")

    # Fatigue risk warning (creator-facing, no debug text)
    if fatigue >= 40:
        lines.append("Hook fatigue risk is elevated — consider varying hook style")
    elif fatigue < 15:
        lines.append("Low hook fatigue risk supports engagement")

    # Phase 53D: optional opening-hook knowledge enrichment
    if len(lines) < 6 and first_3s < 55:
        k_hint = _first3s_knowledge_hint()
        if k_hint:
            lines.append(k_hint)

    # Phase 53D: optional curiosity / open-loop knowledge enrichment
    if len(lines) < 6 and curiosity < 50:
        k_hint = _curiosity_knowledge_hint()
        if k_hint:
            lines.append(k_hint)

    # Phase 53D: optional market-specific hook knowledge enrichment
    if len(lines) < 6 and market < 55:
        k_hint = _market_hook_hint(edit_plan)
        if k_hint:
            lines.append(k_hint)

    # Phase 55D: optional platform hook context hint
    if len(lines) < 6:
        p_hint = _platform_hook_hint(edit_plan)
        if p_hint:
            lines.append(p_hint)

    return lines


def _first3s_knowledge_hint() -> str:
    """Return an optional knowledge-informed opening-hook hint. Never raises.

    Phase 53D hook knowledge integration — metadata-only, additive.
    Enriches reasoning when first-3s hook strength is limited.
    """
    try:
        from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge
        pack = retrieve_knowledge(domain="hook", tags=["first_3s", "opening"], max_results=1)
        if not pack.available or not pack.items:
            return ""
        patterns = pack.items[0].retention_patterns
        if patterns.get("slow_intro_risk") == "high":
            return "Establishing viewer relevance in the first seconds improves hook strength"
        if patterns.get("direct_value"):
            return "A direct value proposition in the opening frames increases early retention"
        return ""
    except Exception:
        return ""


def _curiosity_knowledge_hint() -> str:
    """Return an optional knowledge-informed curiosity hint. Never raises.

    Phase 53D hook knowledge integration — metadata-only, additive.
    Enriches reasoning when curiosity signals are weak.
    """
    try:
        from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge
        pack = retrieve_knowledge(domain="hook", tags=["curiosity", "open_loop"], max_results=1)
        if not pack.available or not pack.items:
            return ""
        patterns = pack.items[0].retention_patterns
        if patterns.get("open_loop_clarity") == "required":
            return "A clear open loop with explicit payoff expectation improves curiosity strength"
        if patterns.get("narrative_tension"):
            return "Story tension and an unresolved question drive curiosity and watch-through rate"
        return ""
    except Exception:
        return ""


def _platform_hook_hint(edit_plan: Any) -> str:
    """Return an optional platform-aware hook reasoning hint. Never raises.

    Phase 55D platform hook intelligence — metadata-only, additive.
    Reads platform_hook_context from the edit plan when available.
    """
    try:
        ctx = getattr(edit_plan, "platform_hook_context", None)
        if not ctx or not isinstance(ctx, dict) or not ctx.get("available"):
            return ""
        guidance = ctx.get("guidance") or {}
        reasoning = ctx.get("reasoning") or []
        platform = str(ctx.get("platform") or "")
        first_3s = str(guidance.get("first_3s_priority") or "")
        hook_style = str(guidance.get("hook_style") or "")

        if reasoning:
            return str(reasoning[0])
        if platform and first_3s:
            return f"{platform.replace('_', ' ').title()} hook guidance recommends {first_3s} first-3-second attention"
        if hook_style and first_3s:
            return f"Platform guidance supports {hook_style} hook style with {first_3s} first-3-second priority"
        return ""
    except Exception:
        return ""


def _market_hook_hint(edit_plan: Any) -> str:
    """Return an optional knowledge-informed market-specific hook hint. Never raises.

    Phase 53D hook knowledge integration — metadata-only, additive.
    Enriches reasoning when market hook fit is below threshold.
    """
    try:
        moi = {}
        if edit_plan is not None and hasattr(edit_plan, "market_optimization_intelligence"):
            moi = edit_plan.market_optimization_intelligence or {}
        elif isinstance(edit_plan, dict):
            moi = edit_plan.get("market_optimization_intelligence") or {}
        market_code = str(moi.get("target_market") or "").strip().lower()
        if not market_code:
            return ""

        from app.ai.knowledge.hook_knowledge_retriever import retrieve_knowledge
        pack = retrieve_knowledge(
            domain="hook",
            tags=["market_hook", market_code],
            max_results=1,
        )
        if not pack.available or not pack.items:
            return ""
        patterns = pack.items[0].retention_patterns
        if patterns.get("hook_style") == "direct_promise":
            return "Direct promise framing aligns with US market hook expectations"
        if patterns.get("hook_style") == "trust_first":
            return "Trust-first opening aligns with EU market hook preferences"
        if patterns.get("hook_style") == "story_invitation":
            return "Story-invitation style aligns with JP market hook preferences"
        return ""
    except Exception:
        return ""
