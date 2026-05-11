"""
unified_quality_evaluator.py — Unified Quality Score v2 evaluator. Phase 52D.

Fuses subtitle_quality_v2, camera_quality_v2, hook_quality_v2, creator fit,
market fit, and strategy fit into a single deterministic render_quality_v2 result.

Public API:
    evaluate_unified_quality_v2(edit_plan) -> dict

Safety contract:
    ❌ No render mutation
    ❌ No hook rewriting
    ❌ No subtitle mutation
    ❌ No motion_crop rewrite
    ❌ No FFmpeg mutation
    ❌ No render pipeline rewrite
    ❌ No executor override
    ❌ No autonomous execution
    ✅ Evaluation-only — enriches unified quality metadata, never mutates
    ✅ Deterministic — same inputs always produce same output
    ✅ Never raises
    ✅ Fallback-safe — returns all-zero dict on any error
"""
from __future__ import annotations

import logging
from typing import Any, List

from app.ai.unified_quality.unified_quality_schema import (
    UnifiedQualityV2,
    SCORE_WEIGHTS,
    fallback_render_quality_v2,
)
from app.ai.unified_quality.unified_quality_scorer import (
    score_subtitle,
    score_camera,
    score_hook,
    score_creator_fit,
    score_market_fit,
    score_strategy_fit,
    compute_confidence,
)

logger = logging.getLogger("app.ai.unified_quality.evaluator")


def evaluate_unified_quality_v2(edit_plan: Any) -> dict:
    """Fuse all quality intelligence into one unified score. Never raises.

    Args:
        edit_plan: AIEditPlan with Phase 52A/B/C results + strategy/creator/market signals.

    Returns:
        dict with key "render_quality_v2" matching the unified quality schema spec.
        Falls back to all-zero dict on any failure.
    """
    try:
        return _evaluate(edit_plan)
    except Exception as exc:
        logger.debug("unified_quality_v2_error: %s", exc)
        return {"render_quality_v2": fallback_render_quality_v2()}


def _evaluate(edit_plan: Any) -> dict:
    if edit_plan is None:
        return {"render_quality_v2": fallback_render_quality_v2()}

    # Score all dimensions
    subtitle  = score_subtitle(edit_plan)
    camera    = score_camera(edit_plan)
    hook      = score_hook(edit_plan)
    creator   = score_creator_fit(edit_plan)
    market    = score_market_fit(edit_plan)
    strategy  = score_strategy_fit(edit_plan)
    confidence = compute_confidence(edit_plan)

    # Weighted overall
    raw_overall = (
        subtitle  * SCORE_WEIGHTS["subtitle_score"]
        + camera  * SCORE_WEIGHTS["camera_score"]
        + hook    * SCORE_WEIGHTS["hook_score"]
        + creator * SCORE_WEIGHTS["creator_fit"]
        + market  * SCORE_WEIGHTS["market_fit"]
        + strategy * SCORE_WEIGHTS["strategy_fit"]
    )

    overall = max(0, min(100, round(raw_overall)))

    reasoning = _build_reasoning(
        subtitle, camera, hook, creator, market, strategy, edit_plan,
    )

    result = UnifiedQualityV2(
        subtitle_score=subtitle,
        camera_score=camera,
        hook_score=hook,
        creator_fit=creator,
        market_fit=market,
        strategy_fit=strategy,
        overall=overall,
        confidence=confidence,
        reasoning=reasoning,
    )

    logger.debug(
        "unified_quality_v2_done overall=%d confidence=%.2f "
        "subtitle=%d camera=%d hook=%d creator=%d market=%d strategy=%d",
        overall, confidence, subtitle, camera, hook, creator, market, strategy,
    )

    return {"render_quality_v2": result.to_dict()}


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    subtitle: int,
    camera: int,
    hook: int,
    creator: int,
    market: int,
    strategy: int,
    edit_plan: Any,
) -> List[str]:
    lines: List[str] = []

    # Lead with the balance of the three subsystems
    scores = [s for s in (subtitle, camera, hook) if s > 0]
    if scores:
        avg = sum(scores) / len(scores)
        if avg >= 75:
            lines.append(
                "Subtitle readability, camera stability, and hook strength are well balanced"
            )
        elif avg >= 55:
            lines.append("Subtitle, camera, and hook quality are moderately balanced")
        else:
            lines.append("Quality signals across subtitle, camera, and hook are limited")

    # Creator fit comment
    if creator >= 75:
        lines.append("Creator preference alignment is strong")
    elif creator >= 55:
        lines.append("Creator preference alignment is moderate")

    # Market fit comment
    if market >= 70:
        lines.append("Hook strength supports retention for the selected market")
    elif market >= 50:
        lines.append("Market fit is within acceptable range")

    # Strategy fit comment
    if strategy >= 60:
        lines.append(
            "Quality-focused strategy supports retention without unsafe execution changes"
        )

    # Individual quality highlights
    if subtitle >= 80 and camera >= 80:
        lines.append("Subtitle and camera quality are both strong")
    elif hook >= 80:
        lines.append("Hook opening strength is a key quality contributor")

    return lines
