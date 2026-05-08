"""
retention.py — Deterministic retention risk estimation. Phase 12.

No ML models, no external APIs. Pure heuristic scoring from StorySegment
metadata (segment_type, confidence, emotion, retention_risk).

Public API:
    estimate_retention(segment, context=None) -> dict

Return shape:
    {
        "score":    int,         # 0-100  (higher = better retention)
        "risk":     float,       # 0-1    (higher = more dropout risk)
        "reasons":  list[str],
        "warnings": list[str],
    }
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.story.retention")

# Per segment-type baseline adjustments (score_delta, risk_delta, reason)
_TYPE_MAP: dict[str, tuple[int, float, Optional[str]]] = {
    "hook":     ( 20, -0.20, "Opening hook drives initial retention"),
    "setup":    ( -5,  0.05, "Setup phase has moderate dropout risk"),
    "build_up": ( 10, -0.15, "Rising pacing increases engagement"),
    "tension":  ( 15, -0.18, "Tension peak keeps viewers watching"),
    "climax":   ( 22, -0.22, "Climax moment anchors viewer attention"),
    "payoff":   (  8, -0.10, "Payoff resolution rewards viewers"),
    "outro":    (-20,  0.25, "Outro section has elevated dropout risk"),
    "unknown":  (  0,  0.00, None),
}

# Emotions that increase retention
_HIGH_RETENTION_EMOTIONS: frozenset[str] = frozenset({
    "urgency", "surprise", "curiosity", "excitement",
})

# Emotions that decrease retention
_LOW_RETENTION_EMOTIONS: frozenset[str] = frozenset({
    "sadness", "boredom", "calm",
})

_SCORE_BASE = 65
_RISK_BASE = 0.35


def estimate_retention(segment: Any, context: Optional[dict] = None) -> dict:
    """Estimate viewer retention for a single story segment.

    Args:
        segment: StorySegment (or any object with segment_type, confidence,
                 emotion, retention_risk attributes).
        context: Optional metadata dict (reserved for future use).

    Returns:
        dict with keys: score (int 0-100), risk (float 0-1),
        reasons (list[str]), warnings (list[str]).
    """
    score: float = _SCORE_BASE
    risk: float = _RISK_BASE
    reasons: list[str] = []
    warnings: list[str] = []

    try:
        seg_type = str(getattr(segment, "segment_type", "unknown") or "unknown").lower()
        confidence = float(getattr(segment, "confidence", 0.5) or 0.5)
        emotion = str(getattr(segment, "emotion", "") or "").lower()

        # ── Segment-type baseline ─────────────────────────────────────────────
        s_adj, r_adj, reason_text = _TYPE_MAP.get(seg_type, (0, 0.0, None))
        score += s_adj
        risk += r_adj
        if reason_text:
            reasons.append(reason_text)

        # ── Confidence modifier ───────────────────────────────────────────────
        if confidence < 0.30:
            score -= 10
            risk += 0.10
            reasons.append("Low classification confidence increases uncertainty")
        elif confidence >= 0.70:
            score += 5
            risk -= 0.05

        # ── Emotion modifier ──────────────────────────────────────────────────
        if emotion in _HIGH_RETENTION_EMOTIONS:
            score += 8
            risk -= 0.08
            reasons.append(f"Strong {emotion} signal boosts retention")
        elif emotion in _LOW_RETENTION_EMOTIONS:
            score -= 8
            risk += 0.10
            reasons.append(f"Low-energy {emotion} signal increases dropout risk")

        # ── Incorporate existing segment retention_risk estimate ──────────────
        seg_risk = getattr(segment, "retention_risk", None)
        if seg_risk is not None:
            try:
                seg_risk_f = float(seg_risk)
                risk = (risk + seg_risk_f) / 2.0
            except (TypeError, ValueError):
                pass

    except Exception as exc:
        warnings.append(f"retention_estimate_error:{type(exc).__name__}")
        logger.debug("estimate_retention_failed: %s", exc)

    score_int = max(0, min(100, round(score)))
    risk_clamped = round(max(0.0, min(1.0, risk)), 3)

    return {
        "score": score_int,
        "risk": risk_clamped,
        "reasons": reasons,
        "warnings": warnings,
    }
