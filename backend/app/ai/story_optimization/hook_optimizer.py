"""
hook_optimizer.py — Hook quality analysis. Phase 20.

Deterministic only. Never raises. No text rewriting. Advisory only.
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.story_optimization.story_optimization_schema import StoryOptimizationIssue

logger = logging.getLogger("app.ai.story_optimization")

# Hook segment types that indicate a strong opening
_STRONG_HOOK_TYPES: frozenset[str] = frozenset({"hook", "intro"})

# Retention categories that indicate hook weakness
_WEAK_HOOK_RISK_CATEGORIES: frozenset[str] = frozenset({"weak_hook", "low_retention_start"})


def analyze_hook_quality(
    story_context: Any = None,
    retention_context: Any = None,
    transcript_chunks: Any = None,
) -> list[StoryOptimizationIssue]:
    """Analyze hook quality from story + retention metadata.

    Returns a list of StoryOptimizationIssue. Empty list = strong hook.
    Never raises.
    """
    try:
        return _analyze(
            dict(story_context or {}),
            dict(retention_context or {}),
            list(transcript_chunks or []),
        )
    except Exception as exc:
        logger.debug("analyze_hook_quality_failed: %s", exc)
        return []


def _analyze(
    story_ctx: dict,
    retention_ctx: dict,
    chunks: list,
) -> list[StoryOptimizationIssue]:
    issues: list[StoryOptimizationIssue] = []

    # Check for hook segment in story structure
    segments = story_ctx.get("segments") or []
    hook_segments = [s for s in segments if isinstance(s, dict) and s.get("segment_type") in _STRONG_HOOK_TYPES]
    has_hook_segment = bool(hook_segments)

    # Hook region bounds from story
    hook_start: float | None = None
    hook_end: float | None = None
    if hook_segments:
        try:
            hook_start = float(hook_segments[0].get("start") or 0.0)
            hook_end = float(hook_segments[0].get("end") or 0.0)
        except (TypeError, ValueError):
            pass

    # Check retention risks for weak_hook signals
    risk_regions = retention_ctx.get("risk_regions") or []
    weak_hook_risks = [
        r for r in risk_regions
        if isinstance(r, dict) and r.get("category") in _WEAK_HOOK_RISK_CATEGORIES
    ]
    has_weak_hook_risk = bool(weak_hook_risks)

    # Check hook retention score from story context
    hook_retention = None
    if hook_segments:
        try:
            hook_retention = float(hook_segments[0].get("retention_risk") or 0.0)
        except (TypeError, ValueError):
            pass

    hook_is_weak = (
        not has_hook_segment
        or has_weak_hook_risk
        or (hook_retention is not None and hook_retention > 0.5)
    )

    if hook_is_weak:
        # Determine severity
        if not has_hook_segment:
            severity = "high"
            reason = "No clear hook segment detected in story structure"
            suggested = "Add a strong opening hook to capture immediate attention"
            confidence = 0.80
        elif has_weak_hook_risk:
            severity = "medium"
            risk_label = str(weak_hook_risks[0].get("label") or "")
            reason = f"Hook segment has retention risk{': ' + risk_label if risk_label else ''}"
            suggested = "Strengthen the opening hook to reduce early dropout"
            confidence = _confidence_from_risk(weak_hook_risks[0])
        else:
            severity = "low"
            reason = f"Hook retention risk score elevated ({hook_retention:.2f})"
            suggested = "Consider frontloading more engaging content"
            confidence = 0.55

        issues.append(StoryOptimizationIssue(
            start=hook_start,
            end=hook_end,
            issue_type="weak_hook",
            severity=severity,
            reason=reason,
            suggested_action=suggested,
            confidence=confidence,
            safe_to_auto_apply=False,
        ))
    else:
        # Strong hook — low-severity informational issue only if hook retention is mildly elevated
        if hook_retention is not None and 0.3 < hook_retention <= 0.5:
            issues.append(StoryOptimizationIssue(
                start=hook_start,
                end=hook_end,
                issue_type="weak_hook",
                severity="low",
                reason=f"Hook retention risk mildly elevated ({hook_retention:.2f})",
                suggested_action="Monitor hook engagement; current hook may need minor adjustment",
                confidence=0.45,
                safe_to_auto_apply=False,
            ))

    return issues


def _confidence_from_risk(risk: dict) -> float:
    """Derive confidence from retention risk severity field."""
    try:
        return min(1.0, max(0.0, float(risk.get("severity") or risk.get("score") or 0.6)))
    except (TypeError, ValueError):
        return 0.6
