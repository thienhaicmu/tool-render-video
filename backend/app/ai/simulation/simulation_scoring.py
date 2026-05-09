"""
simulation_scoring.py — Execution simulation scoring. Phase 26.

Scores advisory execution simulations by estimated gain and safety level.

Design rules:
- Deterministic only.
- Never raises.
- Safe simulations preferred.
- Blocked simulations heavily penalized.
- Retention/story gains increase score.

Public API:
    score_simulation(simulation, edit_plan=None) -> dict
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.simulation.scoring")

# Gain weights for overall score computation
_RETENTION_WEIGHT = 0.35
_STORY_WEIGHT = 0.25
_SUBTITLE_WEIGHT = 0.20
_PACING_WEIGHT = 0.20

# Safety level penalties applied to overall score
_SAFETY_PENALTY: dict[str, float] = {
    "safe": 0.0,
    "caution": 15.0,
    "blocked": 50.0,
}


def score_simulation(
    simulation: Any,
    edit_plan: Optional[Any] = None,
) -> dict:
    """Score an advisory execution simulation.

    Returns a compact score dict with overall_score (0–100), confidence,
    reasons, and warnings. Safe simulations with positive gains score
    higher. Blocked simulations are heavily penalized. Never raises.

    Args:
        simulation: AIExecutionSimulation or compatible object.
        edit_plan:  Optional AIEditPlan for additional context (unused in
                    the heuristic model but kept for forward compatibility).

    Returns:
        {"overall_score": float, "confidence": float, "reasons": list, "warnings": list}
    """
    try:
        return _score(simulation, edit_plan)
    except Exception as exc:
        logger.debug("score_simulation_failed: %s", exc)
        return _fallback_score(str(exc))


# ── Internal scorer ───────────────────────────────────────────────────────────

def _score(simulation: Any, edit_plan: Optional[Any]) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []

    retention_gain = float(getattr(simulation, "estimated_retention_gain", 0.0) or 0.0)
    story_gain = float(getattr(simulation, "estimated_story_gain", 0.0) or 0.0)
    subtitle_gain = float(getattr(simulation, "estimated_subtitle_clarity_gain", 0.0) or 0.0)
    pacing_gain = float(getattr(simulation, "estimated_pacing_gain", 0.0) or 0.0)
    confidence = float(getattr(simulation, "confidence", 0.0) or 0.0)
    safety_level = str(getattr(simulation, "safety_level", "safe") or "safe")
    sim_id = str(getattr(simulation, "simulation_id", "") or "")

    # Weighted gain sum (gains in -100..100 space), centred at 0
    weighted_gain = (
        retention_gain * _RETENTION_WEIGHT
        + story_gain * _STORY_WEIGHT
        + subtitle_gain * _SUBTITLE_WEIGHT
        + pacing_gain * _PACING_WEIGHT
    )

    # Baseline of 50 — a no-op simulation scores 50; positive gains push above
    raw_score = 50.0 + weighted_gain

    # Safety penalties
    penalty = _SAFETY_PENALTY.get(safety_level, 0.0)
    if penalty > 0:
        raw_score = max(0.0, raw_score - penalty)
        warnings.append(f"safety_penalty_applied({safety_level})")

    # Confidence dampening: low-confidence sims pulled toward 50
    if confidence < 0.40:
        raw_score = 50.0 + (raw_score - 50.0) * (confidence / 0.40)
        warnings.append("low_confidence_dampened")

    overall = round(max(0.0, min(100.0, raw_score)), 2)

    # Reason lines
    if retention_gain > 0:
        reasons.append(f"retention_gain:{retention_gain:.1f}")
    if story_gain > 0:
        reasons.append(f"story_gain:{story_gain:.1f}")
    if subtitle_gain > 0:
        reasons.append(f"subtitle_clarity_gain:{subtitle_gain:.1f}")
    if pacing_gain > 0:
        reasons.append(f"pacing_gain:{pacing_gain:.1f}")
    if safety_level == "safe":
        reasons.append("safety:safe")
    elif safety_level == "caution":
        reasons.append("safety:caution(penalized)")
    elif safety_level == "blocked":
        reasons.append("safety:blocked(heavy_penalty)")

    logger.debug(
        "score_simulation sim_id=%s score=%.2f confidence=%.4f safety=%s",
        sim_id, overall, confidence, safety_level,
    )

    return {
        "overall_score": overall,
        "confidence": round(min(1.0, max(0.0, confidence)), 4),
        "reasons": reasons[:8],
        "warnings": warnings,
    }


def _fallback_score(reason: str) -> dict:
    return {
        "overall_score": 50.0,
        "confidence": 0.0,
        "reasons": [],
        "warnings": [f"scoring_error:{reason}"],
    }
