"""
retention_recommender.py — Advisory retention recommendations. Phase 16.

Maps detected risk regions to human-readable advisory suggestions.
Advisory only — safe_to_auto_apply is structurally locked to False.
No timing mutations, no render command changes, no automatic edits.

Public API:
    build_retention_recommendations(analysis: RetentionAnalysis) -> list[RetentionRecommendation]
"""
from __future__ import annotations

import logging
from typing import List

from app.ai.retention.retention_schema import RetentionAnalysis, RetentionRecommendation

logger = logging.getLogger("app.ai.retention.recommender")

_MAX_RECOMMENDATIONS = 6

# Severity ordering for sorting (higher → appears first)
_SEVERITY_ORDER: dict[str, int] = {"high": 3, "medium": 2, "low": 1}

# Per-category advisory recommendation data: (priority, action, reason)
_CATEGORY_RECOMMENDATIONS: dict[str, tuple[str, str, str]] = {
    "weak_hook": (
        "high",
        "Strengthen the first 3 seconds with a clearer hook",
        "Early dropout risk is highest in the first few seconds",
    ),
    "long_setup": (
        "high",
        "Tighten the setup before the payoff",
        "Extended setup reduces viewer patience before the climax",
    ),
    "unclear_payoff": (
        "high",
        "Ensure the edit has a clear resolution or climax",
        "Viewers need a reward for watching through to the end",
    ),
    "pacing_decay": (
        "medium",
        "Avoid long calm gaps after high-energy moments",
        "Energy drops in the middle section trigger viewer dropout",
    ),
    "silence_gap": (
        "medium",
        "Fill or tighten silence gaps between segments",
        "Unintended pauses interrupt viewer flow and attention",
    ),
    "story_drop": (
        "medium",
        "Clarify the narrative arc to maintain engagement",
        "Unclear story structure disorients viewers mid-content",
    ),
    "subtitle_overload": (
        "low",
        "Reduce subtitle density in high-energy sections",
        "Dense subtitles compete with visual content for viewer attention",
    ),
    "low_energy": (
        "medium",
        "Add higher-energy content in the middle section",
        "Low energy sections increase dropout risk",
    ),
    "unknown": (
        "low",
        "Review this section for narrative clarity",
        "Unclassified content may weaken viewer engagement",
    ),
}


def build_retention_recommendations(
    analysis: RetentionAnalysis,
) -> List[RetentionRecommendation]:
    """Build advisory recommendations from a RetentionAnalysis. Never raises.

    All recommendations have safe_to_auto_apply=False.
    Returns at most 6 recommendations, ordered by severity.
    """
    try:
        return _build(analysis)
    except Exception as exc:
        logger.debug("build_retention_recommendations_failed: %s", exc)
        return []


def _build(analysis: RetentionAnalysis) -> List[RetentionRecommendation]:
    if not analysis.available or not analysis.risk_regions:
        return []

    # Sort risk regions: highest severity and risk first
    sorted_risks = sorted(
        analysis.risk_regions,
        key=lambda r: (_SEVERITY_ORDER.get(r.severity, 1), r.risk),
        reverse=True,
    )

    seen_categories: set[str] = set()
    recommendations: List[RetentionRecommendation] = []

    for region in sorted_risks:
        if len(recommendations) >= _MAX_RECOMMENDATIONS:
            break

        cat = region.category
        if cat in seen_categories:
            continue
        seen_categories.add(cat)

        rec_data = _CATEGORY_RECOMMENDATIONS.get(cat)
        if rec_data is None:
            continue

        priority, action, reason = rec_data
        recommendations.append(RetentionRecommendation(
            priority=priority,
            recommended_action=action,
            reason=reason,
            safe_to_auto_apply=False,
        ))

    logger.debug(
        "retention_recommendations_built count=%d categories=%s",
        len(recommendations),
        ",".join(seen_categories),
    )

    return recommendations
