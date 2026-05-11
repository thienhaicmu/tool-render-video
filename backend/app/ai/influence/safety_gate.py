"""
safety_gate.py — Conservative safety gate for the influence engine. Phase 48.

Every influence recommendation must pass this gate before being surfaced.
If uncertain: DO NOTHING. Safe fallback always wins.

Confidence thresholds:
  < 0.70            → BLOCKED  — no influence recommendations produced
  0.70 ≤ x ≤ 0.85  → SOFT     — conservative bias only (density, smoothing)
  > 0.85            → STRONG   — stronger safe recommendations (still bounded)

Rules:
- Deterministic
- Conservative-first
- Rollback-safe
- Explainable (every gate decision carries a reason)
- Never raises
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.influence.safety_gate")

# Thresholds
_BLOCK_BELOW = 0.70
_STRONG_ABOVE = 0.85

TIER_BLOCKED = "blocked"
TIER_SOFT = "soft"
TIER_STRONG = "strong"


def evaluate_gate(confidence: float) -> dict:
    """Evaluate the safety gate for a given aggregate confidence score.

    Args:
        confidence: Aggregate confidence from Phase 47 (0.0–1.0).

    Returns:
        {
            "passed": bool,
            "tier": "blocked" | "soft" | "strong",
            "confidence": float,
            "reason": str,
        }
    """
    try:
        return _evaluate(float(confidence))
    except Exception as exc:
        logger.debug("safety_gate_error: %s", exc)
        return _blocked(confidence=0.0, reason=f"gate_error:{type(exc).__name__}")


def _evaluate(confidence: float) -> dict:
    confidence = max(0.0, min(1.0, confidence))

    if confidence < _BLOCK_BELOW:
        return _blocked(
            confidence=confidence,
            reason=f"confidence_too_low ({round(confidence, 3)} < {_BLOCK_BELOW})",
        )
    if confidence > _STRONG_ABOVE:
        return {
            "passed": True,
            "tier": TIER_STRONG,
            "confidence": round(confidence, 4),
            "reason": f"high_confidence ({round(confidence, 3)} > {_STRONG_ABOVE})",
        }
    return {
        "passed": True,
        "tier": TIER_SOFT,
        "confidence": round(confidence, 4),
        "reason": f"medium_confidence ({round(confidence, 3)} in [{_BLOCK_BELOW}, {_STRONG_ABOVE}])",
    }


def _blocked(confidence: float, reason: str) -> dict:
    return {
        "passed": False,
        "tier": TIER_BLOCKED,
        "confidence": round(float(confidence), 4),
        "reason": reason,
    }


def is_soft_or_strong(gate: dict) -> bool:
    """True when gate passed at any tier."""
    return bool(gate.get("passed"))


def is_strong(gate: dict) -> bool:
    """True only when gate passed at STRONG tier."""
    return gate.get("passed") and gate.get("tier") == TIER_STRONG
