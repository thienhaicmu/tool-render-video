"""
edit_plan_schema.py — AI edit plan data structures.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AIClipPlan:
    start: float
    end: float
    score: float
    reason: str = ""
    source: str = "local_ai"


@dataclass
class AISubtitlePlan:
    tone: str = "default"
    highlight_keywords: bool = False
    max_words_per_line: Optional[int] = None


@dataclass
class AICameraPlan:
    mode: str = "default"
    behavior: str = "none"
    subtitle_safe: bool = True


@dataclass
class AIEditPlan:
    enabled: bool
    mode: str
    selected_segments: List[AIClipPlan]
    subtitle: AISubtitlePlan
    camera: AICameraPlan
    warnings: List[str] = field(default_factory=list)
    fallback_used: bool = False
    memory_context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "selected_segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "score": s.score,
                    "reason": s.reason,
                    "source": s.source,
                }
                for s in self.selected_segments
            ],
            "subtitle": {
                "tone": self.subtitle.tone,
                "highlight_keywords": self.subtitle.highlight_keywords,
                "max_words_per_line": self.subtitle.max_words_per_line,
            },
            "camera": {
                "mode": self.camera.mode,
                "behavior": self.camera.behavior,
                "subtitle_safe": self.camera.subtitle_safe,
            },
            "warnings": list(self.warnings),
            "fallback_used": self.fallback_used,
            "memory_context": dict(self.memory_context),
        }
