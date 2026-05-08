"""
variant_scoring.py — Deterministic scoring for AI variant plans. Phase 21–22.

Deterministic only. Never raises. No payload mutation.
Phase 22 additions: score normalization, stronger safety penalty, baseline stabilizer.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.variants.variant_schema import AIVariantPlan
from app.ai.variants.variant_safety import is_variant_safe

logger = logging.getLogger("app.ai.variants")

# Base scores per purpose
_BASE_SCORES: dict[str, float] = {
    "safe_baseline":  60.0,
    "retention":      72.0,
    "hook":           70.0,
    "subtitle":       65.0,
    "pacing":         68.0,
    "story":          71.0,
    "creator_style":  67.0,
}

# Risk penalties — Phase 22: high penalty increased for stronger selection pressure
_RISK_PENALTIES: dict[str, float] = {
    "low":    0.0,
    "medium": 8.0,
    "high":   40.0,  # Phase 22: raised from 30 → 40 for selector clarity
}

# Phase 22: safe_baseline stabilizer — guarantees a floor score for selection
_BASELINE_FLOOR: float = 58.0


def score_variant(
    variant: AIVariantPlan,
    edit_plan: Any = None,
    context: Optional[dict] = None,
) -> dict:
    """Score a variant plan deterministically.

    Returns:
        {
            "score": 0-100,
            "expected_gain": 0-100,
            "reasons": list[str],
            "warnings": list[str],
        }
    Never raises.
    """
    try:
        return _score(variant, edit_plan, context or {})
    except Exception as exc:
        logger.debug("score_variant_failed: %s", exc)
        return {"score": 0.0, "expected_gain": 0.0, "reasons": [], "warnings": [f"scoring_error:{type(exc).__name__}"]}


def _score(variant: AIVariantPlan, edit_plan: Any, context: dict) -> dict:
    reasons: list[str] = []
    warnings: list[str] = []

    purpose = variant.purpose if variant.purpose in _BASE_SCORES else "safe_baseline"
    base = _BASE_SCORES[purpose]

    # Risk penalty
    risk = str(variant.risk) if variant.risk in _RISK_PENALTIES else "low"
    penalty = _RISK_PENALTIES[risk]
    if penalty > 0:
        reasons.append(f"risk_penalty_{risk}:{penalty:.0f}pts")

    # Confidence boost (up to +15)
    confidence_boost = 0.0
    try:
        conf = float(variant.confidence)
        confidence_boost = conf * 15.0
        if confidence_boost > 1.0:
            reasons.append(f"confidence_boost:{confidence_boost:.1f}pts")
    except (TypeError, ValueError):
        pass

    # Safety gate bonus/penalty
    safe = is_variant_safe(variant, context)
    safety_modifier = 0.0
    if safe:
        safety_modifier = 5.0
        reasons.append("safety_gate_passed")
    else:
        safety_modifier = -20.0
        reasons.append("safety_gate_failed")
        warnings.append("variant_not_safe_to_render")

    # Context modifiers from edit_plan metadata
    context_boost = 0.0
    if edit_plan is not None:
        context_boost = _context_boost(purpose, edit_plan, reasons)

    raw_score = base + confidence_boost + safety_modifier + context_boost - penalty

    # Phase 22: safe_baseline floor — guarantees selector always has a stable fallback
    if purpose == "safe_baseline":
        raw_score = max(raw_score, _BASELINE_FLOOR)

    score = round(max(0.0, min(100.0, raw_score)), 2)

    # Phase 22: normalized selection score in [0, 1] for selector use
    normalized = round(score / 100.0, 4)

    # Expected gain: proportional to score above baseline floor
    expected_gain = round(max(0.0, min(100.0, (score - _BASELINE_FLOOR) * 2.0)), 2)

    return {
        "score": score,
        "normalized_score": normalized,
        "expected_gain": expected_gain,
        "reasons": reasons,
        "warnings": warnings,
    }


def _context_boost(purpose: str, edit_plan: Any, reasons: list[str]) -> float:
    """Apply small context-dependent boosts based on edit plan metadata."""
    boost = 0.0
    try:
        if purpose == "retention":
            retention = getattr(edit_plan, "retention", {}) or {}
            score = retention.get("overall_retention_score") if isinstance(retention, dict) else None
            if score is not None and float(score) < 70:
                boost += 5.0
                reasons.append("retention_score_low:boost+5")

        elif purpose == "hook":
            so = getattr(edit_plan, "story_optimization", {}) or {}
            if isinstance(so, dict):
                issues = so.get("issues") or []
                if any(
                    isinstance(i, dict) and i.get("issue_type") == "weak_hook"
                    for i in issues
                ):
                    boost += 6.0
                    reasons.append("weak_hook_detected:boost+6")

        elif purpose == "subtitle":
            se = getattr(edit_plan, "subtitle_execution", {}) or {}
            if isinstance(se, dict) and se.get("available"):
                boost += 3.0
                reasons.append("subtitle_execution_available:boost+3")

        elif purpose == "pacing":
            pacing = getattr(edit_plan, "pacing", None)
            if pacing is not None:
                energy = getattr(pacing, "energy_level", None)
                if energy is not None and float(energy) > 0.6:
                    boost += 4.0
                    reasons.append("high_pacing_energy:boost+4")

        elif purpose == "story":
            so = getattr(edit_plan, "story_optimization", {}) or {}
            if isinstance(so, dict):
                score_val = so.get("narrative_score")
                if score_val is not None and float(score_val) < 60:
                    boost += 5.0
                    reasons.append("low_narrative_score:boost+5")

        elif purpose == "creator_style":
            cs = getattr(edit_plan, "creator_style", {}) or {}
            if isinstance(cs, dict) and cs.get("dominant_style") not in (None, "unknown", ""):
                boost += 3.0
                reasons.append("creator_style_matched:boost+3")

    except Exception:
        pass
    return boost
