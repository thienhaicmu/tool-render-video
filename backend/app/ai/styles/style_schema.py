"""
style_schema.py — Lightweight creator style intelligence data structures. Phase 14.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CreatorStyleProfile:
    """Archetype profile defining editing tendencies. Not tied to any real creator."""
    style_id: str
    display_name: str
    pacing_style: str
    subtitle_style: str
    camera_behavior: str
    hook_style: str
    story_arc_style: str
    energy_level: str
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "style_id": self.style_id,
            "display_name": self.display_name,
            "pacing_style": self.pacing_style,
            "subtitle_style": self.subtitle_style,
            "camera_behavior": self.camera_behavior,
            "hook_style": self.hook_style,
            "story_arc_style": self.story_arc_style,
            "energy_level": self.energy_level,
        }


@dataclass
class StyleClassification:
    """Result of classifying editing signals against known style archetypes."""
    available: bool = True
    dominant_style: str = "unknown"
    confidence: float = 0.0
    secondary_styles: List[str] = field(default_factory=list)
    matched_traits: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "dominant_style": self.dominant_style,
            "confidence": round(self.confidence, 1),
            "secondary_styles": list(self.secondary_styles[:3]),
            "matched_traits": list(self.matched_traits[:6]),
            "warnings": list(self.warnings),
        }


@dataclass
class StyleRecommendation:
    """Advisory style-based suggestions. Never auto-applied."""
    recommended_style: Optional[str] = None
    confidence: float = 0.0
    suggested_adjustments: dict = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "recommended_style": self.recommended_style,
            "confidence": round(self.confidence, 1),
            "suggested_adjustments": dict(self.suggested_adjustments),
            "reasons": list(self.reasons[:5]),
            "warnings": list(self.warnings),
        }
