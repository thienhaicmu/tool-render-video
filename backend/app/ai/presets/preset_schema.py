"""
preset_schema.py — Lightweight preset evolution data structures. Phase 13.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class PresetPerformanceSample:
    """One render memory entry parsed for preset performance analysis."""
    preset: Optional[str] = None
    ai_mode: Optional[str] = None
    market: Optional[str] = None
    score: Optional[float] = None
    duration: Optional[float] = None
    subtitle_tone: Optional[str] = None
    camera_behavior: Optional[str] = None
    pacing_style: Optional[str] = None
    story_arc: Optional[str] = None
    status: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "preset": self.preset,
            "ai_mode": self.ai_mode,
            "market": self.market,
            "score": self.score,
            "duration": self.duration,
            "subtitle_tone": self.subtitle_tone,
            "camera_behavior": self.camera_behavior,
            "pacing_style": self.pacing_style,
            "story_arc": self.story_arc,
            "status": self.status,
        }


@dataclass
class PresetRecommendation:
    """Advisory preset recommendation derived from historical render analysis."""
    recommended_preset: Optional[str] = None
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    suggested_adjustments: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "recommended_preset": self.recommended_preset,
            "confidence": round(self.confidence, 1),
            "reasons": list(self.reasons[:5]),
            "suggested_adjustments": dict(self.suggested_adjustments),
            "warnings": list(self.warnings),
        }


@dataclass
class PresetEvolutionReport:
    """Full preset performance analysis and advisory recommendation."""
    available: bool = True
    market: Optional[str] = None
    ai_mode: Optional[str] = None
    best_samples: List[dict] = field(default_factory=list)
    recommendation: Optional[PresetRecommendation] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "market": self.market,
            "ai_mode": self.ai_mode,
            "best_samples": list(self.best_samples[:5]),
            "recommendation": self.recommendation.to_dict() if self.recommendation else None,
            "warnings": list(self.warnings),
        }
