"""
subtitle_quality_evaluator.py — Subtitle Quality Intelligence v2 evaluator. Phase 52A.

Orchestrates all subtitle quality dimension scorers into a single
SubtitleQualityV2 result with weighted overall score, risk adjustment,
and creator-facing reasoning.

Public API:
    evaluate_subtitle_quality_v2(edit_plan) -> dict

Safety contract:
    ❌ No subtitle timing rewrite
    ❌ No subtitle segmentation rewrite
    ❌ No ASS generation rewrite
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

from app.ai.subtitle_quality.subtitle_quality_schema import (
    SubtitleQualityV2,
    SCORE_WEIGHTS,
    fallback_subtitle_quality_v2,
)
from app.ai.subtitle_quality.subtitle_quality_scorer import (
    score_mobile_readability,
    score_subtitle_balance,
    score_keyword_emphasis_quality,
    score_safe_zone_fit,
    score_creator_fit,
    score_overload_risk,
    score_fatigue_risk,
    compute_confidence,
)

logger = logging.getLogger("app.ai.subtitle_quality.evaluator")

# Risk penalty scale: each 10 pts of risk reduces overall by this much
_RISK_PENALTY_PER_10 = 1.2


def evaluate_subtitle_quality_v2(edit_plan: Any) -> dict:
    """Evaluate subtitle quality across 5 dimensions + 2 risk scores. Never raises.

    Args:
        edit_plan: AIEditPlan with Phase 17, 32-34, 44, 46, 50A-D signals.

    Returns:
        dict matching the subtitle_quality_v2 schema spec.
        Falls back to all-zero dict on any failure.
    """
    try:
        return _evaluate(edit_plan)
    except Exception as exc:
        logger.debug("subtitle_quality_v2_error: %s", exc)
        return {"subtitle_quality_v2": fallback_subtitle_quality_v2()}


def _evaluate(edit_plan: Any) -> dict:
    if edit_plan is None:
        return {"subtitle_quality_v2": fallback_subtitle_quality_v2()}

    # Score all dimensions
    mobile     = score_mobile_readability(edit_plan)
    balance    = score_subtitle_balance(edit_plan)
    emphasis   = score_keyword_emphasis_quality(edit_plan)
    safe_zone  = score_safe_zone_fit(edit_plan)
    creator    = score_creator_fit(edit_plan)
    overload   = score_overload_risk(edit_plan)
    fatigue    = score_fatigue_risk(edit_plan)
    confidence = compute_confidence(edit_plan)

    # Weighted overall (before risk adjustment)
    raw_overall = (
        mobile    * SCORE_WEIGHTS["mobile_readability"]
        + balance * SCORE_WEIGHTS["subtitle_balance"]
        + emphasis * SCORE_WEIGHTS["keyword_emphasis_quality"]
        + safe_zone * SCORE_WEIGHTS["safe_zone_fit"]
        + creator * SCORE_WEIGHTS["creator_fit"]
    )

    # Conservative risk adjustment: risk scores reduce overall
    avg_risk = (overload + fatigue) / 2.0
    risk_penalty = (avg_risk / 10.0) * _RISK_PENALTY_PER_10
    overall = max(0, min(100, round(raw_overall - risk_penalty)))

    reasoning = _build_reasoning(
        mobile, balance, emphasis, safe_zone, creator,
        overload, fatigue, edit_plan,
    )

    result = SubtitleQualityV2(
        mobile_readability=mobile,
        subtitle_balance=balance,
        keyword_emphasis_quality=emphasis,
        safe_zone_fit=safe_zone,
        creator_fit=creator,
        overload_risk=overload,
        fatigue_risk=fatigue,
        overall=overall,
        confidence=confidence,
        reasoning=reasoning,
    )

    logger.debug(
        "subtitle_quality_v2_done overall=%d confidence=%.2f mobile=%d "
        "balance=%d emphasis=%d safe_zone=%d creator=%d overload=%d fatigue=%d",
        overall, confidence, mobile, balance, emphasis,
        safe_zone, creator, overload, fatigue,
    )

    return {"subtitle_quality_v2": result.to_dict()}


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    mobile: int,
    balance: int,
    emphasis: int,
    safe_zone: int,
    creator: int,
    overload: int,
    fatigue: int,
    edit_plan: Any,
) -> List[str]:
    lines: List[str] = []

    # Mobile readability comment
    if mobile >= 75:
        lines.append("Subtitle density is comfortable for mobile viewing")
    elif mobile >= 55:
        lines.append("Subtitle density is acceptable for mobile viewing")
    else:
        lines.append("Subtitle density may be challenging on small screens")

    # Balance comment
    if balance >= 75:
        lines.append("Subtitle pacing and emphasis are well balanced")
    elif balance < 50:
        lines.append("Subtitle emphasis variation may reduce visual balance")

    # Keyword emphasis comment
    if emphasis >= 70:
        lines.append("Keyword emphasis is well targeted and clear")
    elif emphasis < 45:
        lines.append("Keyword emphasis signals are limited or unbalanced")

    # Safe zone comment
    if safe_zone >= 75:
        lines.append("Subtitle placement fits well within safe display zones")
    elif safe_zone < 50:
        lines.append("Subtitle placement may overlap mobile UI elements")

    # Creator fit comment
    if creator >= 70:
        lines.append("Subtitle style aligns with your creator preferences")
    elif creator >= 55:
        lines.append("Subtitle style partially reflects your creator preferences")

    # Risk warnings (creator-facing, no debug text)
    if overload >= 40:
        lines.append("High subtitle density detected — consider reducing for clarity")
    if fatigue >= 35:
        lines.append("Fast-paced subtitle rhythm may increase viewer fatigue")

    # Phase 53B: optional mobile readability knowledge enrichment
    if len(lines) < 6 and mobile < 75:
        k_hint = _mobile_knowledge_hint()
        if k_hint:
            lines.append(k_hint)

    return lines


def _mobile_knowledge_hint() -> str:
    """Return an optional knowledge-informed mobile readability hint. Never raises.

    Phase 53B subtitle knowledge integration — metadata-only, additive.
    Enriches reasoning when mobile readability score is below optimal.
    """
    try:
        from app.ai.knowledge.subtitle_knowledge_retriever import retrieve_knowledge
        pack = retrieve_knowledge(domain="subtitle", tags=["mobile", "readability"], max_results=1)
        if not pack.available or not pack.items:
            return ""
        patterns = pack.items[0].subtitle_patterns
        if patterns.get("avoid_dense_blocks"):
            return "Compact, dense-free subtitle design supports mobile readability"
        if patterns.get("compact_design"):
            return "Compact subtitle design is recommended for mobile viewers"
        return ""
    except Exception:
        return ""
