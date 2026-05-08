"""
subtitle_execution_schema.py — Dynamic subtitle execution data structures. Phase 17.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


VALID_DENSITY_MODES: frozenset[str] = frozenset({"compact", "normal", "expressive"})
VALID_EMOTION_STYLES: frozenset[str] = frozenset({
    "neutral", "hype", "dramatic", "calm", "emotional", "punch"
})


@dataclass
class SubtitleExecutionHint:
    emphasis_strength: float = 0.0
    density_mode: str = "normal"
    emotion_style: str = "neutral"
    beat_sync_strength: float = 0.0
    keyword_focus: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "emphasis_strength": round(float(self.emphasis_strength), 3),
            "density_mode": self.density_mode,
            "emotion_style": self.emotion_style,
            "beat_sync_strength": round(float(self.beat_sync_strength), 3),
            "keyword_focus": list(self.keyword_focus[:10]),
            "warnings": list(self.warnings),
        }


@dataclass
class SubtitleExecutionRegion:
    start: float
    end: float
    style: str = "default"
    emphasis: float = 0.0
    emotion: str = "neutral"
    beat_strength: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "style": self.style,
            "emphasis": round(float(self.emphasis), 3),
            "emotion": self.emotion,
            "beat_strength": round(float(self.beat_strength), 3),
            "metadata": dict(self.metadata),
        }


@dataclass
class SubtitleExecutionPlan:
    available: bool = True
    regions: List[SubtitleExecutionRegion] = field(default_factory=list)
    global_hint: Optional[SubtitleExecutionHint] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "regions": [r.to_dict() for r in self.regions[:20]],
            "global_hint": self.global_hint.to_dict() if self.global_hint else None,
            "warnings": list(self.warnings),
        }
