"""
feature_enhancement_schema.py — AI feature enhancement data structures. Phase 38.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Assistive-only: AI enhances existing features; never replaces render engine authority.
No FFmpeg mutation, no render execution, no autonomous editing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AIFeatureEnhancement:
    """Enhancement summary for a single existing render feature. Assistive-only."""
    feature_name: str
    enabled: bool = False
    enhancement_level: str = "safe"
    confidence: float = 0.0
    improvements: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feature_name": self.feature_name,
            "enabled": bool(self.enabled),
            "enhancement_level": str(self.enhancement_level),
            "confidence": round(float(self.confidence), 4),
            "improvements": list(self.improvements),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation),
        }


@dataclass
class AIFeatureEnhancementPack:
    """Unified AI feature enhancement pack. Always assistive_only mode."""
    available: bool = True
    mode: str = "assistive_only"
    subtitle_enhancement: dict = field(default_factory=dict)
    camera_enhancement: dict = field(default_factory=dict)
    timing_enhancement: dict = field(default_factory=dict)
    clip_selection_enhancement: dict = field(default_factory=dict)
    creator_style_enhancement: dict = field(default_factory=dict)
    variant_enhancement: dict = field(default_factory=dict)
    output_ranking_enhancement: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "mode": str(self.mode),
            "subtitle_enhancement": dict(self.subtitle_enhancement),
            "camera_enhancement": dict(self.camera_enhancement),
            "timing_enhancement": dict(self.timing_enhancement),
            "clip_selection_enhancement": dict(self.clip_selection_enhancement),
            "creator_style_enhancement": dict(self.creator_style_enhancement),
            "variant_enhancement": dict(self.variant_enhancement),
            "output_ranking_enhancement": dict(self.output_ranking_enhancement),
            "warnings": list(self.warnings),
        }
