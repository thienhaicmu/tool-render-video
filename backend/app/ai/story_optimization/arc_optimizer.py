"""
arc_optimizer.py — Story arc analysis and narrative scoring. Phase 20.

Deterministic only. Never raises. No segment reorder. Advisory only.
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.story_optimization.story_optimization_schema import (
    StoryOptimizationIssue,
    VALID_FLOW_TYPES,
)

logger = logging.getLogger("app.ai.story_optimization")

# Segment types in preferred narrative order
_ARC_SEGMENTS: tuple[str, ...] = ("hook", "setup", "build_up", "climax", "payoff", "outro")

# Segments needed for a full hook-to-climax arc
_HOOK_TO_CLIMAX_REQUIRED: frozenset[str] = frozenset({"hook", "climax"})
_FULL_ARC_BONUS_TYPES: frozenset[str] = frozenset({"setup", "build_up", "payoff"})

# Score weights per segment type presence
_SEGMENT_SCORE_WEIGHTS: dict[str, float] = {
    "hook":     20.0,
    "setup":    10.0,
    "build_up": 15.0,
    "climax":   25.0,
    "payoff":   15.0,
    "outro":     5.0,
}

# Issue types mapped to arc gaps
_MISSING_ISSUE_MAP: dict[str, str] = {
    "build_up": "weak_build_up",
    "climax":   "missing_climax",
    "setup":    "missing_setup",
}


def analyze_story_arc(
    story_context: Any = None,
    pacing_context: Any = None,
    retention_context: Any = None,
) -> dict:
    """Analyze story arc and return a compact arc result dict.

    Returns:
        {
            "flow_type": "hook_to_climax" | "linear" | "flat" | "unknown",
            "narrative_score": 0–100,
            "issues": [StoryOptimizationIssue ...],
            "warnings": [],
        }
    Never raises.
    """
    try:
        return _analyze(
            dict(story_context or {}),
            dict(pacing_context or {}),
            dict(retention_context or {}),
        )
    except Exception as exc:
        logger.debug("analyze_story_arc_failed: %s", exc)
        return {
            "flow_type": "unknown",
            "narrative_score": 0.0,
            "issues": [],
            "warnings": [f"arc_analysis_error:{type(exc).__name__}"],
        }


def _analyze(
    story_ctx: dict,
    pacing_ctx: dict,
    retention_ctx: dict,
) -> dict:
    warnings: list[str] = []
    issues: list[StoryOptimizationIssue] = []

    segments = story_ctx.get("segments") or []
    segment_types: set[str] = set()
    for s in segments:
        if isinstance(s, dict):
            t = s.get("segment_type")
            if t:
                segment_types.add(str(t))

    # Dominant arc string from story analysis
    dominant_arc = str(story_ctx.get("dominant_arc") or "")
    narrative_flow = str(story_ctx.get("narrative_flow") or "")

    # --- Base score from segment presence ---
    base_score = 0.0
    for seg_type, weight in _SEGMENT_SCORE_WEIGHTS.items():
        if seg_type in segment_types:
            base_score += weight

    # --- Flow type classification ---
    has_hook = "hook" in segment_types
    has_climax = "climax" in segment_types
    has_build_up = "build_up" in segment_types
    has_payoff = "payoff" in segment_types or "outro" in segment_types

    if has_hook and has_climax:
        flow_type = "hook_to_climax"
        base_score += 10.0  # bonus for complete arc
        if has_build_up:
            base_score += 5.0
        if has_payoff:
            base_score += 5.0
    elif len(segment_types) >= 3 and narrative_flow in ("linear", "front_loaded"):
        flow_type = "linear"
    elif len(segment_types) <= 1 or dominant_arc in ("flat", "unclear"):
        flow_type = "flat"
        base_score = min(base_score, 30.0)  # cap flat arcs
    else:
        flow_type = "unknown"

    # --- Pacing modifier ---
    energy = None
    try:
        energy = float(pacing_ctx.get("energy_level") or 0.5)
    except (TypeError, ValueError):
        pass
    if energy is not None:
        if energy >= 0.7:
            base_score += 5.0
        elif energy < 0.3:
            base_score -= 5.0

    # --- Retention modifier ---
    risk_regions = retention_ctx.get("risk_regions") or []
    n_risks = len([r for r in risk_regions if isinstance(r, dict)])
    base_score -= n_risks * 2.0

    # Story retention_score override if present
    story_score = story_ctx.get("retention_score")
    if story_score is not None:
        try:
            story_score_f = float(story_score)
            # Blend: 60% arc calculation + 40% story retention score
            base_score = base_score * 0.6 + story_score_f * 0.4
        except (TypeError, ValueError):
            pass

    narrative_score = max(0.0, min(100.0, base_score))

    # --- Issue generation for arc gaps ---
    if not has_hook and "intro" not in segment_types:
        issues.append(StoryOptimizationIssue(
            issue_type="weak_hook",
            severity="high",
            reason="Story arc has no hook or intro segment",
            suggested_action="Add a strong opening hook",
            confidence=0.80,
        ))

    if not has_climax and len(segment_types) >= 2:
        issues.append(StoryOptimizationIssue(
            issue_type="missing_climax",
            severity="medium",
            reason="Story arc has no climax segment — peak moment unclear",
            suggested_action="Identify and emphasize the climax moment",
            confidence=0.70,
        ))

    if has_hook and has_climax and not has_build_up:
        issues.append(StoryOptimizationIssue(
            issue_type="weak_build_up",
            severity="low",
            reason="Story jumps from hook to climax without a build-up section",
            suggested_action="Keep high-energy section closer to hook for better build-up",
            confidence=0.60,
        ))

    if flow_type == "flat":
        issues.append(StoryOptimizationIssue(
            issue_type="unclear_arc",
            severity="medium",
            reason="Story arc is flat or unclear — no clear narrative progression detected",
            suggested_action="Restructure to include hook → setup → climax → payoff flow",
            confidence=0.65,
        ))

    # Long setup: setup segment exists but is longer than build_up + climax combined
    setup_segs = [s for s in segments if isinstance(s, dict) and s.get("segment_type") == "setup"]
    non_setup_segs = [
        s for s in segments
        if isinstance(s, dict) and s.get("segment_type") in {"build_up", "climax"}
    ]
    if setup_segs and non_setup_segs:
        try:
            setup_dur = sum(
                float(s.get("end", 0)) - float(s.get("start", 0)) for s in setup_segs
            )
            climax_dur = sum(
                float(s.get("end", 0)) - float(s.get("start", 0)) for s in non_setup_segs
            )
            if setup_dur > climax_dur * 1.5 and setup_dur > 5.0:
                issues.append(StoryOptimizationIssue(
                    start=float(setup_segs[0].get("start") or 0.0),
                    end=float(setup_segs[-1].get("end") or 0.0),
                    issue_type="long_setup",
                    severity="medium",
                    reason=f"Setup is longer than ideal before climax ({setup_dur:.1f}s setup vs {climax_dur:.1f}s climax/build)",
                    suggested_action="Tighten setup before climax",
                    confidence=0.70,
                ))
        except (TypeError, ValueError):
            pass

    logger.info(
        "ai_story_arc_analyzed flow_type=%s narrative_score=%.1f issues=%d segments=%d",
        flow_type, narrative_score, len(issues), len(segment_types),
    )

    return {
        "flow_type": flow_type,
        "narrative_score": round(narrative_score, 1),
        "issues": issues,
        "warnings": warnings,
    }
