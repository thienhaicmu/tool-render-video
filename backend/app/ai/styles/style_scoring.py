"""
style_scoring.py — Deterministic creator style-fit scoring. Phase 23.

Scores how well a variant's purpose aligns with a detected creator style.
Used by the variant selector to apply a style-fit bonus to ranking.

Deterministic only. Never raises. No ML models. No external APIs.
safe_generic always receives a stable moderate score.

Public API:
    score_style_fit(style_profile, variant=None, edit_plan=None) -> dict
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.styles.scoring")

# ── Style × variant-purpose fit scores (0-100) ───────────────────────────────
# Maps (style_id, variant_purpose) → base fit score.
# Higher = better fit. safe_generic always returns 60 for any purpose.
_STYLE_PURPOSE_FIT: dict[str, dict[str, float]] = {
    "viral_tiktok": {
        "retention":    85.0,
        "hook":         80.0,
        "creator_style": 75.0,
        "subtitle":     65.0,
        "pacing":       60.0,
        "story":        55.0,
        "safe_baseline": 50.0,
    },
    "cinematic": {
        "story":        85.0,
        "retention":    75.0,
        "creator_style": 72.0,
        "pacing":       65.0,
        "hook":         60.0,
        "subtitle":     55.0,
        "safe_baseline": 55.0,
    },
    "educational": {
        "subtitle":     82.0,
        "story":        75.0,
        "retention":    70.0,
        "creator_style": 65.0,
        "pacing":       65.0,
        "hook":         55.0,
        "safe_baseline": 55.0,
    },
    "podcast": {
        "retention":    75.0,
        "pacing":       72.0,
        "creator_style": 65.0,
        "story":        65.0,
        "subtitle":     60.0,
        "hook":         55.0,
        "safe_baseline": 55.0,
    },
    "product_demo": {
        "subtitle":     78.0,
        "retention":    72.0,
        "creator_style": 68.0,
        "hook":         65.0,
        "pacing":       65.0,
        "story":        55.0,
        "safe_baseline": 55.0,
    },
    "storytelling": {
        "story":        85.0,
        "retention":    78.0,
        "hook":         72.0,
        "creator_style": 70.0,
        "pacing":       65.0,
        "subtitle":     55.0,
        "safe_baseline": 55.0,
    },
    "commentary": {
        "hook":         85.0,
        "retention":    80.0,
        "creator_style": 72.0,
        "subtitle":     65.0,
        "pacing":       65.0,
        "story":        55.0,
        "safe_baseline": 50.0,
    },
    "interview": {
        "pacing":       78.0,
        "subtitle":     75.0,
        "creator_style": 68.0,
        "story":        65.0,
        "retention":    60.0,
        "hook":         50.0,
        "safe_baseline": 55.0,
    },
    "safe_generic": {
        "safe_baseline": 65.0,
        "retention":    60.0,
        "story":        60.0,
        "subtitle":     60.0,
        "pacing":       60.0,
        "hook":         60.0,
        "creator_style": 60.0,
    },
}

# Confidence threshold below which we treat the style as unreliable
_MIN_STYLE_CONFIDENCE: float = 0.30


def score_style_fit(
    style_profile: Any,
    variant: Any = None,
    edit_plan: Any = None,
) -> dict:
    """Score how well a variant's purpose fits a detected creator style.

    Returns:
        {
            "style_fit_score": float (0-100),
            "confidence":      float (0-1),
            "reasons":         list[str],
            "warnings":        list[str],
        }
    Never raises. Deterministic.
    """
    try:
        return _score(style_profile, variant, edit_plan)
    except Exception as exc:
        logger.debug("score_style_fit_failed: %s", exc)
        return {
            "style_fit_score": 60.0,
            "confidence": 0.0,
            "reasons": [],
            "warnings": [f"style_fit_scoring_error:{type(exc).__name__}"],
        }


def _score(style_profile: Any, variant: Any, edit_plan: Any) -> dict:
    from app.ai.styles.style_schema import VALID_P23_STYLES

    reasons: list[str] = []
    warnings: list[str] = []

    # Resolve style_id
    style_id = _resolve_str(style_profile, "style_id", "safe_generic")
    if style_id not in VALID_P23_STYLES:
        style_id = "safe_generic"
        warnings.append(f"unknown_style_id_fallback_to_safe_generic")

    # Resolve confidence
    raw_conf = _resolve_float(style_profile, "confidence", 0.5)
    confidence = round(min(1.0, max(0.0, raw_conf)), 4)

    # Resolve variant purpose
    purpose = _resolve_str(variant, "purpose", "safe_baseline")
    if not purpose:
        purpose = "safe_baseline"

    # Look up base fit score
    purpose_map = _STYLE_PURPOSE_FIT.get(style_id, _STYLE_PURPOSE_FIT["safe_generic"])
    base_fit = float(purpose_map.get(purpose, 60.0))

    # Confidence modifier: low confidence → pull score toward neutral (60)
    if confidence < _MIN_STYLE_CONFIDENCE:
        base_fit = 60.0 + (base_fit - 60.0) * (confidence / _MIN_STYLE_CONFIDENCE)
        warnings.append("low_style_confidence:score_dampened")
    else:
        reasons.append(f"style_fit:{style_id}×{purpose}:{base_fit:.0f}")

    # safe_generic stability: always returns moderate score
    if style_id == "safe_generic":
        base_fit = max(58.0, min(65.0, base_fit))
        reasons.append("safe_generic_stable_score")

    fit_score = round(max(0.0, min(100.0, base_fit)), 2)
    normalized_confidence = round(confidence, 4)

    return {
        "style_fit_score": fit_score,
        "confidence": normalized_confidence,
        "reasons": reasons,
        "warnings": warnings,
    }


# ── Utility ───────────────────────────────────────────────────────────────────

def _resolve_str(obj: Any, attr: str, default: str) -> str:
    try:
        if isinstance(obj, dict):
            return str(obj.get(attr) or default)
        return str(getattr(obj, attr, default) or default)
    except Exception:
        return default


def _resolve_float(obj: Any, attr: str, default: float) -> float:
    try:
        if isinstance(obj, dict):
            return float(obj.get(attr) or default)
        return float(getattr(obj, attr, default) or default)
    except Exception:
        return default
