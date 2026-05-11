"""
camera_quality_schema.py — Camera Quality Intelligence v2 data structures. Phase 52B.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Evaluation-only: no motion_crop rewrite, no tracking rewrite, no FFmpeg mutation,
no render pipeline rewrite, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Positive-dimension scoring weights (sum = 0.90; risk_penalty provides the remaining 0.10)
SCORE_WEIGHTS: dict = {
    "crop_smoothness":   0.25,
    "subject_stability": 0.25,
    "scene_continuity":  0.20,
    "creator_fit":       0.20,
}

# Risk penalty weight: avg(micro_jitter_risk, whip_pan_risk) × RISK_WEIGHT reduces overall
RISK_WEIGHT: float = 0.10

_MAX_REASONING = 6


@dataclass
class CameraQualityV2:
    """Phase 52B camera quality evaluation result. Evaluation-only, never mutates."""

    # Risk scores: 0–100, lower is better
    micro_jitter_risk: int = 0
    whip_pan_risk:     int = 0

    # Positive dimension scores: 0–100, higher is better
    crop_smoothness:   int = 0
    subject_stability: int = 0
    scene_continuity:  int = 0
    creator_fit:       int = 0

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
            "micro_jitter_risk": max(0, min(100, int(self.micro_jitter_risk))),
            "whip_pan_risk":     max(0, min(100, int(self.whip_pan_risk))),
            "crop_smoothness":   max(0, min(100, int(self.crop_smoothness))),
            "subject_stability": max(0, min(100, int(self.subject_stability))),
            "scene_continuity":  max(0, min(100, int(self.scene_continuity))),
            "creator_fit":       max(0, min(100, int(self.creator_fit))),
            "overall":           max(0, min(100, int(self.overall))),
            "confidence":        round(max(0.0, min(1.0, float(self.confidence))), 2),
            "reasoning":         list(self.reasoning[:_MAX_REASONING]),
        }


# Canonical fallback (all-zero, no reasoning — matches spec)
_FALLBACK: dict = {
    "micro_jitter_risk": 0,
    "whip_pan_risk":     0,
    "crop_smoothness":   0,
    "subject_stability": 0,
    "scene_continuity":  0,
    "creator_fit":       0,
    "overall":           0,
    "confidence":        0.0,
    "reasoning":         [],
}


def fallback_camera_quality_v2() -> dict:
    """Return the spec-mandated all-zero fallback dict. Never raises."""
    return dict(_FALLBACK)
