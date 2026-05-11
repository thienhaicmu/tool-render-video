"""
hook_quality_schema.py — Hook Quality Intelligence v2 data structures. Phase 52C.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Evaluation-only: no hook rewriting, no clip rewrite, no render mutation,
no FFmpeg mutation, no render pipeline rewrite, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Positive-dimension scoring weights (sum = 1.00)
SCORE_WEIGHTS: dict = {
    "first_3s_strength":   0.25,
    "first_5s_retention":  0.20,
    "curiosity_strength":  0.15,
    "open_loop_quality":   0.10,
    "market_fit":          0.15,
    "creator_fit":         0.15,
}

# Risk penalty: each 10-pt hook_fatigue_risk reduces overall by this many pts.
_RISK_PENALTY_PER_10: float = 1.5

_MAX_REASONING: int = 6


@dataclass
class HookQualityV2:
    """Phase 52C hook quality evaluation result. Evaluation-only, never mutates."""

    # Positive dimension scores: 0–100, higher is better
    first_3s_strength:  int = 0
    first_5s_retention: int = 0
    curiosity_strength: int = 0
    open_loop_quality:  int = 0
    market_fit:         int = 0
    creator_fit:        int = 0

    # Risk score: 0–100, lower is better
    hook_fatigue_risk: int = 0

    # Overall weighted score (0–100)
    overall: int = 0

    # Evaluation confidence (0–1)
    confidence: float = 0.0

    # Creator-facing reasoning (no debug text, no stack traces, no internal symbols)
    reasoning: List[str] = field(default_factory=list)

    # Internal diagnostic (never user-facing)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "first_3s_strength":  max(0, min(100, int(self.first_3s_strength))),
            "first_5s_retention": max(0, min(100, int(self.first_5s_retention))),
            "curiosity_strength": max(0, min(100, int(self.curiosity_strength))),
            "open_loop_quality":  max(0, min(100, int(self.open_loop_quality))),
            "hook_fatigue_risk":  max(0, min(100, int(self.hook_fatigue_risk))),
            "market_fit":         max(0, min(100, int(self.market_fit))),
            "creator_fit":        max(0, min(100, int(self.creator_fit))),
            "overall":            max(0, min(100, int(self.overall))),
            "confidence":         round(max(0.0, min(1.0, float(self.confidence))), 2),
            "reasoning":          list(self.reasoning[:_MAX_REASONING]),
        }


# Canonical fallback (all-zero, no reasoning — matches spec)
_FALLBACK: dict = {
    "first_3s_strength":  0,
    "first_5s_retention": 0,
    "curiosity_strength": 0,
    "open_loop_quality":  0,
    "hook_fatigue_risk":  0,
    "market_fit":         0,
    "creator_fit":        0,
    "overall":            0,
    "confidence":         0.0,
    "reasoning":          [],
}


def fallback_hook_quality_v2() -> dict:
    """Return the spec-mandated all-zero fallback dict. Never raises."""
    return dict(_FALLBACK)
