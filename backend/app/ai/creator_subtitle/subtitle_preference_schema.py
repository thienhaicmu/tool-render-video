"""
subtitle_preference_schema.py — Deep Subtitle Preference Intelligence schema. Phase 50A.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Metadata-only: no FFmpeg mutation, no render execution, no timing rewrite.
No internet, no cloud AI, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# Allowed values for each dimension — deterministic normalization contract.
ALLOWED_STYLES      = frozenset({"viral_bold", "clean_pro", "boxed_caption", "unknown"})
ALLOWED_DENSITIES   = frozenset({"light", "medium", "dense", "unknown"})
ALLOWED_UPPERCASE   = frozenset({"uppercase", "mixed", "lowercase", "unknown"})
ALLOWED_EMPHASIS    = frozenset({"none", "subtle", "moderate", "strong", "unknown"})
ALLOWED_MOTION      = frozenset({"clean", "bounce", "karaoke", "unknown"})
ALLOWED_CAPTION_BOX = frozenset({"none", "minimal", "boxed", "unknown"})
ALLOWED_READABILITY = frozenset({"low", "medium", "high", "unknown"})


@dataclass
class AISubtitlePreference:
    """Inferred creator subtitle preference profile. Phase 50A — metadata only."""

    style: str = "unknown"
    density: str = "unknown"
    line_count: int = 2
    uppercase: str = "unknown"
    keyword_emphasis: str = "unknown"
    motion_style: str = "unknown"
    caption_box: str = "unknown"
    readability_priority: str = "unknown"
    mobile_safe: bool = True
    confidence: float = 0.0
    signals: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "style": self.style,
            "density": self.density,
            "line_count": int(self.line_count),
            "uppercase": self.uppercase,
            "keyword_emphasis": self.keyword_emphasis,
            "motion_style": self.motion_style,
            "caption_box": self.caption_box,
            "readability_priority": self.readability_priority,
            "mobile_safe": bool(self.mobile_safe),
            "confidence": round(float(self.confidence), 2),
            "signals": list(self.signals),
        }


@dataclass
class AISubtitlePreferencePack:
    """Phase 50A pack attached to AIEditPlan.creator_subtitle_preference."""

    available: bool = False
    inference_mode: str = "metadata_only"
    subtitle_preference: AISubtitlePreference = field(default_factory=AISubtitlePreference)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "inference_mode": self.inference_mode,
            "subtitle_preference": self.subtitle_preference.to_dict(),
            "warnings": list(self.warnings),
        }
