"""
style_recommender.py — Advisory creator style recommender. Phase 14.

Derives suggested adjustments from a StyleClassification result.
Advisory only — never mutates payload, never auto-applies styles.

Allowed suggestions:
    subtitle_style, pacing_style, camera_behavior, hook_style,
    target_duration_hint

NEVER suggests:
    playback_speed, timing mutations, FFmpeg changes, copyrighted imitation.

Public API:
    recommend_style_adjustments(classification, current_context=None) -> StyleRecommendation
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.styles.style_schema import StyleClassification, StyleRecommendation

logger = logging.getLogger("app.ai.styles.recommender")

# Safe fields only — any key not in this set is blocked
_SAFE_ADJUSTMENT_FIELDS: frozenset[str] = frozenset({
    "subtitle_style",
    "pacing_style",
    "camera_behavior",
    "hook_style",
    "target_duration_hint",
})

# Explicitly blocked fields
_UNSAFE_FIELDS: frozenset[str] = frozenset({
    "playback_speed", "segment_start", "segment_end", "timing",
    "codec", "bitrate", "fps", "resolution", "ffmpeg", "output_format",
})


def recommend_style_adjustments(
    classification: Any,
    current_context: Optional[dict] = None,
) -> StyleRecommendation:
    """Build an advisory StyleRecommendation from a StyleClassification.

    Args:
        classification:  StyleClassification from style_classifier.
        current_context: Optional dict with current render context.

    Returns:
        StyleRecommendation — never raises; returns empty recommendation on error.
    """
    try:
        return _recommend(classification, current_context or {})
    except Exception as exc:
        logger.debug("recommend_style_adjustments_failed: %s", exc)
        return StyleRecommendation(
            warnings=[f"style_recommend_error:{type(exc).__name__}"],
        )


# ── Internal recommender ──────────────────────────────────────────────────────

def _recommend(
    classification: Any,
    context: dict,
) -> StyleRecommendation:
    available = bool(getattr(classification, "available", False))
    if not available:
        return StyleRecommendation(
            confidence=0.0,
            warnings=["classification_unavailable"],
        )

    dominant = str(getattr(classification, "dominant_style", "unknown") or "unknown")
    if dominant == "unknown":
        return StyleRecommendation(
            confidence=0.0,
            warnings=["no_dominant_style"],
        )

    confidence = float(getattr(classification, "confidence", 0.0))
    matched_traits = list(getattr(classification, "matched_traits", []) or [])

    # Load profile for suggested values
    from app.ai.styles.style_profiles import get_profile, STYLE_DURATION_HINTS
    profile = get_profile(dominant)

    if profile is None:
        return StyleRecommendation(
            confidence=0.0,
            warnings=[f"unknown_style_profile:{dominant}"],
        )

    # Build safe adjustments from profile
    raw_adjustments: dict = {
        "subtitle_style": profile.subtitle_style,
        "pacing_style": profile.pacing_style,
        "camera_behavior": profile.camera_behavior,
        "hook_style": profile.hook_style,
    }

    # Advisory duration hint
    if dominant in STYLE_DURATION_HINTS:
        raw_adjustments["target_duration_hint"] = STYLE_DURATION_HINTS[dominant]

    # Safety gate: keep only allowed fields, strip any unsafe keys
    adjustments = {
        k: v for k, v in raw_adjustments.items()
        if k in _SAFE_ADJUSTMENT_FIELDS and k not in _UNSAFE_FIELDS
    }

    # Build reasons (max 5)
    reasons: list[str] = []
    reasons.append(f"{profile.display_name} editing archetype detected")
    reasons.append(f"{profile.pacing_style.replace('_', ' ').title()} pacing identified")
    if profile.energy_level in ("high", "very_high"):
        reasons.append("High-energy editing style matched")
    elif profile.energy_level in ("very_low", "low"):
        reasons.append("Calm low-energy editing style matched")
    if matched_traits:
        reasons.append(f"Matched signals: {', '.join(matched_traits[:2])}")
    if confidence >= 60.0:
        reasons.append("High-confidence archetype match")

    logger.info(
        "ai_creator_style_recommended style=%s confidence=%.1f adjustments=%d",
        dominant, confidence, len(adjustments),
    )

    return StyleRecommendation(
        recommended_style=dominant,
        confidence=confidence,
        suggested_adjustments=adjustments,
        reasons=reasons[:5],
    )
