"""
payoff_analyzer.py — Payoff and outro quality analysis. Phase 20.

Deterministic only. Never raises. Advisory only.
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.story_optimization.story_optimization_schema import StoryOptimizationIssue

logger = logging.getLogger("app.ai.story_optimization")

# Segment types that represent a satisfying payoff
_PAYOFF_TYPES: frozenset[str] = frozenset({"payoff", "outro", "resolution", "conclusion"})

# Retention categories that indicate payoff weakness
_WEAK_PAYOFF_RISK_CATEGORIES: frozenset[str] = frozenset({
    "unclear_payoff", "abrupt_ending", "weak_outro", "pacing_decay",
})


def analyze_payoff_quality(
    story_context: Any = None,
    retention_context: Any = None,
) -> list[StoryOptimizationIssue]:
    """Analyze payoff/outro quality from story + retention metadata.

    Returns a list of StoryOptimizationIssue. Never raises.
    """
    try:
        return _analyze(
            dict(story_context or {}),
            dict(retention_context or {}),
        )
    except Exception as exc:
        logger.debug("analyze_payoff_quality_failed: %s", exc)
        return []


def _analyze(
    story_ctx: dict,
    retention_ctx: dict,
) -> list[StoryOptimizationIssue]:
    issues: list[StoryOptimizationIssue] = []

    segments = story_ctx.get("segments") or []
    payoff_segments = [
        s for s in segments
        if isinstance(s, dict) and s.get("segment_type") in _PAYOFF_TYPES
    ]
    has_payoff = bool(payoff_segments)

    # Bounds of the last payoff segment
    payoff_start: float | None = None
    payoff_end: float | None = None
    if payoff_segments:
        try:
            payoff_start = float(payoff_segments[-1].get("start") or 0.0)
            payoff_end = float(payoff_segments[-1].get("end") or 0.0)
        except (TypeError, ValueError):
            pass

    # Retention risk signals
    risk_regions = retention_ctx.get("risk_regions") or []
    payoff_risks = [
        r for r in risk_regions
        if isinstance(r, dict) and r.get("category") in _WEAK_PAYOFF_RISK_CATEGORIES
    ]

    # Check retention risk on payoff segment itself
    payoff_retention_high = False
    if payoff_segments:
        try:
            retention_risk = float(payoff_segments[-1].get("retention_risk") or 0.0)
            payoff_retention_high = retention_risk > 0.5
        except (TypeError, ValueError):
            pass

    # Issue: missing payoff
    if not has_payoff:
        issues.append(StoryOptimizationIssue(
            start=None,
            end=None,
            issue_type="weak_payoff",
            severity="high",
            reason="No payoff or outro segment detected in story structure",
            suggested_action="Clarify payoff before outro to improve viewer satisfaction",
            confidence=0.80,
            safe_to_auto_apply=False,
        ))
        return issues  # no further payoff analysis possible

    # Issue: unclear payoff from retention risk
    unclear_payoff_risks = [r for r in payoff_risks if r.get("category") == "unclear_payoff"]
    if unclear_payoff_risks:
        label = str(unclear_payoff_risks[0].get("label") or "")
        issues.append(StoryOptimizationIssue(
            start=payoff_start,
            end=payoff_end,
            issue_type="weak_payoff",
            severity="medium",
            reason=f"Payoff segment has unclear payoff risk{': ' + label if label else ''}",
            suggested_action="Clarify payoff before outro to improve viewer satisfaction",
            confidence=_confidence_from_risk(unclear_payoff_risks[0]),
            safe_to_auto_apply=False,
        ))

    # Issue: abrupt outro
    abrupt_risks = [r for r in payoff_risks if r.get("category") in {"abrupt_ending", "weak_outro"}]
    if abrupt_risks:
        issues.append(StoryOptimizationIssue(
            start=payoff_start,
            end=payoff_end,
            issue_type="abrupt_outro",
            severity="medium",
            reason="Outro ends abruptly without clear resolution",
            suggested_action="Add resolution or call-to-action to outro",
            confidence=_confidence_from_risk(abrupt_risks[0]),
            safe_to_auto_apply=False,
        ))

    # Issue: pacing decay in payoff region
    decay_risks = [r for r in payoff_risks if r.get("category") == "pacing_decay"]
    if decay_risks:
        issues.append(StoryOptimizationIssue(
            start=payoff_start,
            end=payoff_end,
            issue_type="weak_payoff",
            severity="low",
            reason="Pacing decays in payoff region, reducing viewer satisfaction",
            suggested_action="Tighten the outro to maintain energy through payoff",
            confidence=_confidence_from_risk(decay_risks[0]),
            safe_to_auto_apply=False,
        ))

    # Issue: high retention risk on payoff segment itself
    if payoff_retention_high and not unclear_payoff_risks:
        issues.append(StoryOptimizationIssue(
            start=payoff_start,
            end=payoff_end,
            issue_type="weak_payoff",
            severity="medium",
            reason="Payoff segment has elevated retention risk",
            suggested_action="Clarify payoff before outro",
            confidence=0.60,
            safe_to_auto_apply=False,
        ))

    return issues


def _confidence_from_risk(risk: dict) -> float:
    try:
        return min(1.0, max(0.0, float(risk.get("severity") or risk.get("score") or 0.6)))
    except (TypeError, ValueError):
        return 0.6
