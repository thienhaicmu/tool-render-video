"""
unified_quality_schema.py — Unified Quality Score v2 data structures. Phase 52D.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Evaluation-only: no render mutation, no executor override, no hook rewriting,
no subtitle mutation, no FFmpeg mutation, no render pipeline rewrite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Dimension weights (sum = 1.00)
SCORE_WEIGHTS: dict = {
    "subtitle_score": 0.25,
    "camera_score":   0.25,
    "hook_score":     0.20,
    "creator_fit":    0.15,
    "market_fit":     0.10,
    "strategy_fit":   0.05,
}

_MAX_REASONING: int = 5


@dataclass
class UnifiedQualityV2:
    """Phase 52D unified render quality evaluation result. Evaluation-only, never mutates."""

    # Subsystem scores (drawn from Phase 52A/B/C)
    subtitle_score: int = 0
    camera_score:   int = 0
    hook_score:     int = 0

    # Aggregate dimension scores
    creator_fit:  int = 0
    market_fit:   int = 0
    strategy_fit: int = 0

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
            "subtitle_score": max(0, min(100, int(self.subtitle_score))),
            "camera_score":   max(0, min(100, int(self.camera_score))),
            "hook_score":     max(0, min(100, int(self.hook_score))),
            "creator_fit":    max(0, min(100, int(self.creator_fit))),
            "market_fit":     max(0, min(100, int(self.market_fit))),
            "strategy_fit":   max(0, min(100, int(self.strategy_fit))),
            "overall":        max(0, min(100, int(self.overall))),
            "confidence":     round(max(0.0, min(1.0, float(self.confidence))), 2),
            "reasoning":      list(self.reasoning[:_MAX_REASONING]),
        }


# Canonical fallback (all-zero, no reasoning — matches spec)
_FALLBACK: dict = {
    "subtitle_score": 0,
    "camera_score":   0,
    "hook_score":     0,
    "creator_fit":    0,
    "market_fit":     0,
    "strategy_fit":   0,
    "overall":        0,
    "confidence":     0.0,
    "reasoning":      [],
}


def fallback_render_quality_v2() -> dict:
    """Return the spec-mandated all-zero fallback dict. Never raises."""
    return dict(_FALLBACK)
