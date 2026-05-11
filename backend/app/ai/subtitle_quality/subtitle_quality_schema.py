"""
subtitle_quality_schema.py — Subtitle Quality Intelligence v2 data structures. Phase 52A.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Evaluation-only: no subtitle mutation, no timing rewrite, no ASS rewrite,
no render pipeline rewrite, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Scoring weights (must sum to 1.0)
SCORE_WEIGHTS: dict = {
    "mobile_readability":       0.25,
    "subtitle_balance":         0.20,
    "keyword_emphasis_quality": 0.15,
    "safe_zone_fit":            0.20,
    "creator_fit":              0.20,
}

# Risk score penalty factor applied to overall (risk scores reduce it conservatively)
_RISK_PENALTY_FACTOR = 0.08

_MAX_REASONING = 6


@dataclass
class SubtitleQualityV2:
    """Phase 52A subtitle quality evaluation result. Evaluation-only, never mutates."""

    # Positive dimension scores: 0–100, higher is better
    mobile_readability:       int = 0
    subtitle_balance:         int = 0
    keyword_emphasis_quality: int = 0
    safe_zone_fit:            int = 0
    creator_fit:              int = 0

    # Risk scores: 0–100, lower is better
    overload_risk:  int = 0
    fatigue_risk:   int = 0

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
            "mobile_readability":       max(0, min(100, int(self.mobile_readability))),
            "subtitle_balance":         max(0, min(100, int(self.subtitle_balance))),
            "keyword_emphasis_quality": max(0, min(100, int(self.keyword_emphasis_quality))),
            "safe_zone_fit":            max(0, min(100, int(self.safe_zone_fit))),
            "creator_fit":              max(0, min(100, int(self.creator_fit))),
            "overload_risk":            max(0, min(100, int(self.overload_risk))),
            "fatigue_risk":             max(0, min(100, int(self.fatigue_risk))),
            "overall":                  max(0, min(100, int(self.overall))),
            "confidence":               round(max(0.0, min(1.0, float(self.confidence))), 2),
            "reasoning":                list(self.reasoning[:_MAX_REASONING]),
        }


# Canonical fallback (all-zero, no reasoning — matches spec)
_FALLBACK: dict = {
    "mobile_readability":       0,
    "subtitle_balance":         0,
    "keyword_emphasis_quality": 0,
    "safe_zone_fit":            0,
    "creator_fit":              0,
    "overload_risk":            0,
    "fatigue_risk":             0,
    "overall":                  0,
    "confidence":               0.0,
    "reasoning":                [],
}


def fallback_subtitle_quality_v2() -> dict:
    """Return the spec-mandated all-zero fallback dict. Never raises."""
    return dict(_FALLBACK)
