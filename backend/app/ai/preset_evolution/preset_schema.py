"""
preset_schema.py — Creator preset evolution data structures. Phase 46.

Plain dataclasses — no Pydantic, no heavy deps.

Assistive-only: no file mutation, no render execution, no FFmpeg args,
no playback_speed, no subtitle timing rewrite, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AICreatorPreset:
    """A single creator preset (base or evolved). Phase 46."""
    preset_id: str = "unknown"
    preset_name: str = ""
    creator_style: str = ""
    market_type: str = ""

    subtitle_style: str = ""
    pacing_style: str = ""
    camera_style: str = ""
    hook_style: str = ""

    quality_score: float = 0.0
    creator_fit_score: float = 0.0
    market_fit_score: float = 0.0

    evolution_generation: int = 1
    confidence: float = 0.0

    tags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "preset_id": self.preset_id,
            "preset_name": self.preset_name,
            "creator_style": self.creator_style,
            "market_type": self.market_type,
            "subtitle_style": self.subtitle_style,
            "pacing_style": self.pacing_style,
            "camera_style": self.camera_style,
            "hook_style": self.hook_style,
            "quality_score": round(float(self.quality_score), 2),
            "creator_fit_score": round(float(self.creator_fit_score), 2),
            "market_fit_score": round(float(self.market_fit_score), 2),
            "evolution_generation": int(self.evolution_generation),
            "confidence": round(float(self.confidence), 4),
            "tags": list(self.tags),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AICreatorPreset":
        if not isinstance(data, dict):
            return cls()
        return cls(
            preset_id=str(data.get("preset_id") or "unknown"),
            preset_name=str(data.get("preset_name") or ""),
            creator_style=str(data.get("creator_style") or ""),
            market_type=str(data.get("market_type") or ""),
            subtitle_style=str(data.get("subtitle_style") or ""),
            pacing_style=str(data.get("pacing_style") or ""),
            camera_style=str(data.get("camera_style") or ""),
            hook_style=str(data.get("hook_style") or ""),
            quality_score=float(data.get("quality_score") or 0.0),
            creator_fit_score=float(data.get("creator_fit_score") or 0.0),
            market_fit_score=float(data.get("market_fit_score") or 0.0),
            evolution_generation=int(data.get("evolution_generation") or 1),
            confidence=float(data.get("confidence") or 0.0),
            tags=list(data.get("tags") or []),
            warnings=list(data.get("warnings") or []),
            explanation=list(data.get("explanation") or []),
        )


@dataclass
class AIPresetEvolutionPack:
    """Evolution result containing recommended and evolved presets. Phase 46.

    Assistive-only: never mutates render, never triggers rerender,
    never overrides executor.
    """
    available: bool = True
    enabled: bool = False
    evolution_mode: str = "assistive_only"

    recommended_presets: List[dict] = field(default_factory=list)
    evolved_presets: List[dict] = field(default_factory=list)
    best_preset_id: str = ""

    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "evolution_mode": self.evolution_mode,
            "recommended_presets": list(self.recommended_presets),
            "evolved_presets": list(self.evolved_presets),
            "best_preset_id": self.best_preset_id,
            "warnings": list(self.warnings),
        }
