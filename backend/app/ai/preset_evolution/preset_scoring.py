"""
preset_scoring.py — Creator preset weighted scoring. Phase 46.

Public API:
    score_creator_preset(preset, edit_plan=None, context=None) -> float

Scoring model (weighted blend → 0–100):
    quality_score        35%
    creator_fit_score    25%
    market_fit_score     20%
    feedback_score       10%
    retrieval_score      10%

Rules:
- Deterministic only
- Never raises
- Scores clamped 0–100
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.preset_evolution.preset_safety import _clamp_score, _clamp_confidence

logger = logging.getLogger("app.ai.preset_evolution.scoring")

_WEIGHTS = {
    "quality_score": 0.35,
    "creator_fit_score": 0.25,
    "market_fit_score": 0.20,
    "feedback_score": 0.10,
    "retrieval_score": 0.10,
}


def score_creator_preset(
    preset: Any,
    edit_plan: Any = None,
    context: Optional[dict] = None,
) -> float:
    """Score a creator preset using weighted signals. Never raises.

    Args:
        preset:    AICreatorPreset or dict with quality/fit scores.
        edit_plan: AIEditPlan (or None) with Phase 42–45 signals.
        context:   Optional session context.

    Returns:
        float in [0.0, 100.0]
    """
    try:
        return _score(preset, edit_plan, context)
    except Exception as exc:
        logger.debug("preset_scoring_error: %s", exc)
        return 0.0


def _score(preset: Any, edit_plan: Any, context: Optional[dict]) -> float:
    # Extract base scores from preset
    quality = _get_preset_score(preset, "quality_score")
    creator_fit = _get_preset_score(preset, "creator_fit_score")
    market_fit = _get_preset_score(preset, "market_fit_score")

    # Derive feedback_score from Phase 43 creator feedback intelligence
    feedback = _derive_feedback_score(edit_plan, preset)

    # Derive retrieval_score from Phase 41 creator retrieval intelligence
    retrieval = _derive_retrieval_score(edit_plan, preset)

    # Weighted blend
    overall = (
        quality * _WEIGHTS["quality_score"]
        + creator_fit * _WEIGHTS["creator_fit_score"]
        + market_fit * _WEIGHTS["market_fit_score"]
        + feedback * _WEIGHTS["feedback_score"]
        + retrieval * _WEIGHTS["retrieval_score"]
    )

    return _clamp_score(overall)


def _get_preset_score(preset: Any, attr: str) -> float:
    """Safely extract a score from AICreatorPreset or dict. Never raises."""
    try:
        if isinstance(preset, dict):
            return _clamp_score(float(preset.get(attr) or 0.0))
        return _clamp_score(float(getattr(preset, attr, 0.0) or 0.0))
    except Exception:
        return 0.0


def _derive_feedback_score(edit_plan: Any, preset: Any) -> float:
    """Derive feedback score from Phase 43 signals. Never raises."""
    try:
        if edit_plan is None:
            return 0.0
        cfi = _get_dict(edit_plan, "creator_feedback_intelligence")
        if not cfi.get("enabled"):
            return 0.0

        patterns = cfi.get("learned_feedback_patterns") or {}
        total_exports = int(patterns.get("total_exports") or 0)
        total_signals = int(patterns.get("total_signals") or 0)

        # Score rises with exports (signals of satisfaction), capped
        export_score = min(total_exports * 5.0, 50.0)
        signal_score = min(total_signals * 2.0, 20.0)

        # Style match bonus: if preset creator_style matches dominant feedback style
        preset_style = _get_preset_str(preset, "creator_style")
        dominant = str(patterns.get("dominant_creator_style") or "")
        style_bonus = 20.0 if (preset_style and dominant and preset_style == dominant) else 0.0

        return _clamp_score(export_score + signal_score + style_bonus)
    except Exception:
        return 0.0


def _derive_retrieval_score(edit_plan: Any, preset: Any) -> float:
    """Derive retrieval alignment score from Phase 41 signals. Never raises."""
    try:
        if edit_plan is None:
            return 0.0
        cr = _get_dict(edit_plan, "creator_retrieval")
        if not cr.get("enabled"):
            return 0.0

        matches = cr.get("matches") or []
        if not isinstance(matches, list):
            return 0.0

        preset_style = _get_preset_str(preset, "creator_style")
        match_count = len(matches)
        base = min(match_count * 8.0, 60.0)

        # Style alignment bonus
        style_match = sum(
            1 for m in matches
            if isinstance(m, dict) and m.get("creator_style") == preset_style
        )
        style_bonus = min(style_match * 10.0, 30.0)

        return _clamp_score(base + style_bonus)
    except Exception:
        return 0.0


def _get_dict(edit_plan: Any, attr: str) -> dict:
    """Safely retrieve a dict attribute from edit_plan. Never raises."""
    try:
        if edit_plan is None:
            return {}
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _get_preset_str(preset: Any, attr: str) -> str:
    """Safely extract a string field from AICreatorPreset or dict. Never raises."""
    try:
        if isinstance(preset, dict):
            return str(preset.get(attr) or "")
        return str(getattr(preset, attr, "") or "")
    except Exception:
        return ""
