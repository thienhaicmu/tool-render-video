"""
adaptive_schema.py — Adaptive creator intelligence data structures. Phase 42.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Adaptive-only: no FFmpeg mutation, no render execution, no model training.
No internet, no cloud AI, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AICreatorPreferenceProfile:
    """Learned creator preference profile. Local-only, deterministic. Phase 42."""
    profile_id: str = "default"

    # Learned style preferences
    creator_style_preference: str = ""
    preferred_subtitle_style: str = ""
    preferred_pacing_style: str = ""
    preferred_camera_style: str = ""
    preferred_duration_range: str = ""
    preferred_variant_strategy: str = ""

    # Preference confidence scores (0.0–1.0)
    style_confidence: float = 0.0
    subtitle_confidence: float = 0.0
    pacing_confidence: float = 0.0
    camera_confidence: float = 0.0

    # Usage history counters
    selection_history_count: int = 0
    export_history_count: int = 0

    tags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "creator_style_preference": self.creator_style_preference,
            "preferred_subtitle_style": self.preferred_subtitle_style,
            "preferred_pacing_style": self.preferred_pacing_style,
            "preferred_camera_style": self.preferred_camera_style,
            "preferred_duration_range": self.preferred_duration_range,
            "preferred_variant_strategy": self.preferred_variant_strategy,
            "style_confidence": round(float(self.style_confidence), 4),
            "subtitle_confidence": round(float(self.subtitle_confidence), 4),
            "pacing_confidence": round(float(self.pacing_confidence), 4),
            "camera_confidence": round(float(self.camera_confidence), 4),
            "selection_history_count": int(self.selection_history_count),
            "export_history_count": int(self.export_history_count),
            "tags": list(self.tags),
            "warnings": list(self.warnings),
        }


@dataclass
class AIAdaptiveLearningPack:
    """Adaptive creator learning pack. Phase 42.

    Assistive-only: influences ranking/weighting only.
    Never overrides user settings, never mutates FFmpeg.
    """
    available: bool = True
    enabled: bool = False
    learning_mode: str = "assistive_only"

    creator_profile: dict = field(default_factory=dict)
    learned_preferences: dict = field(default_factory=dict)
    adaptive_influences: dict = field(default_factory=dict)

    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "learning_mode": self.learning_mode,
            "creator_profile": dict(self.creator_profile),
            "learned_preferences": dict(self.learned_preferences),
            "adaptive_influences": dict(self.adaptive_influences),
            "warnings": list(self.warnings),
        }
