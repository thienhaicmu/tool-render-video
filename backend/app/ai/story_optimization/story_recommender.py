"""
story_recommender.py — Story optimization plan builder. Phase 20.

Combines hook, payoff, and arc analyses into a unified advisory plan.
Never raises. No segment reorder. No timing mutation. Advisory only.
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.story_optimization.story_optimization_schema import (
    StoryOptimizationIssue,
    StoryOptimizationPlan,
    _MAX_ISSUES,
    _MAX_RECOMMENDATIONS,
)
from app.ai.story_optimization.hook_optimizer import analyze_hook_quality
from app.ai.story_optimization.payoff_analyzer import analyze_payoff_quality
from app.ai.story_optimization.arc_optimizer import analyze_story_arc

logger = logging.getLogger("app.ai.story_optimization")

# Issue-type → recommendation text (used to avoid duplicate lines)
_ISSUE_RECOMMENDATIONS: dict[str, str] = {
    "weak_hook":       "Strengthen the opening hook",
    "missing_setup":   "Add setup content before the climax",
    "long_setup":      "Tighten setup before climax",
    "weak_build_up":   "Keep high-energy section closer to hook",
    "missing_climax":  "Identify and emphasize the climax moment",
    "weak_payoff":     "Clarify payoff before outro",
    "abrupt_outro":    "Add resolution or call-to-action to outro",
    "unclear_arc":     "Restructure to include hook → setup → climax → payoff flow",
    "retention_risk":  "Address retention risk in highlighted segments",
}

# Positive flow-based recommendations
_FLOW_RECOMMENDATIONS: dict[str, str] = {
    "hook_to_climax": "Maintain the strong hook-to-climax momentum",
    "linear":         "Consider adding a stronger hook for faster viewer engagement",
    "flat":           "Consider restructuring for a clearer narrative arc",
}


def build_story_optimization_plan(
    story_context: Any = None,
    retention_context: Any = None,
    pacing_context: Any = None,
    transcript_chunks: Any = None,
) -> StoryOptimizationPlan:
    """Build a story optimization advisory plan from existing AI metadata.

    Combines hook, payoff, and arc analyses.
    All safe_to_auto_apply=False. Never raises.
    """
    try:
        return _build_plan(
            dict(story_context or {}),
            dict(retention_context or {}),
            dict(pacing_context or {}),
            list(transcript_chunks or []),
        )
    except Exception as exc:
        logger.debug("build_story_optimization_plan_failed: %s", exc)
        return StoryOptimizationPlan(
            available=False,
            warnings=[f"story_optimization_error:{type(exc).__name__}"],
        )


def _build_plan(
    story_ctx: dict,
    retention_ctx: dict,
    pacing_ctx: dict,
    chunks: list,
) -> StoryOptimizationPlan:
    warnings: list[str] = []

    # --- Hook quality ---
    hook_issues = analyze_hook_quality(
        story_context=story_ctx,
        retention_context=retention_ctx,
        transcript_chunks=chunks,
    )

    # --- Payoff quality ---
    payoff_issues = analyze_payoff_quality(
        story_context=story_ctx,
        retention_context=retention_ctx,
    )

    # --- Story arc ---
    arc_result = analyze_story_arc(
        story_context=story_ctx,
        pacing_context=pacing_ctx,
        retention_context=retention_ctx,
    )
    arc_issues: list[StoryOptimizationIssue] = arc_result.get("issues") or []
    flow_type: str = arc_result.get("flow_type") or "unknown"
    narrative_score: float = float(arc_result.get("narrative_score") or 0.0)
    warnings.extend(arc_result.get("warnings") or [])

    # --- Merge and deduplicate issues by issue_type ---
    all_issues: list[StoryOptimizationIssue] = []
    seen_types: set[str] = set()

    for issue in hook_issues + payoff_issues + arc_issues:
        key = issue.issue_type
        if key not in seen_types:
            seen_types.add(key)
            issue.safe_to_auto_apply = False  # enforce advisory
            all_issues.append(issue)
        if len(all_issues) >= _MAX_ISSUES:
            break

    # --- Build recommendations ---
    recommendations: list[str] = []

    # Issue-driven recommendations
    for issue in all_issues:
        rec = _ISSUE_RECOMMENDATIONS.get(issue.issue_type)
        if rec and rec not in recommendations:
            recommendations.append(rec)
        if len(recommendations) >= _MAX_RECOMMENDATIONS:
            break

    # Flow-type recommendation
    flow_rec = _FLOW_RECOMMENDATIONS.get(flow_type)
    if flow_rec and flow_rec not in recommendations and len(recommendations) < _MAX_RECOMMENDATIONS:
        recommendations.append(flow_rec)

    # Availability: plan is meaningful if at least one issue or a non-unknown flow
    available = bool(all_issues) or flow_type not in ("unknown",)
    if not all_issues and flow_type == "unknown":
        warnings.append("no_story_structure_detected")

    logger.info(
        "ai_story_optimization_generated available=%s flow_type=%s "
        "narrative_score=%.1f issues=%d recommendations=%d",
        available, flow_type, narrative_score, len(all_issues), len(recommendations),
    )

    if all_issues:
        logger.info(
            "ai_story_optimization_issues_detected types=%s",
            ",".join(i.issue_type for i in all_issues[:5]),
        )

    return StoryOptimizationPlan(
        available=available,
        narrative_score=narrative_score,
        flow_type=flow_type,
        issues=all_issues[:_MAX_ISSUES],
        recommendations=recommendations[:_MAX_RECOMMENDATIONS],
        warnings=warnings,
    )
