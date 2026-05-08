"""
story_schema.py — Lightweight story intelligence data structures. Phase 12.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Valid segment types:
    hook, setup, build_up, tension, climax, payoff, outro, unknown
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

VALID_SEGMENT_TYPES: frozenset[str] = frozenset({
    "hook", "setup", "build_up", "tension", "climax", "payoff", "outro", "unknown",
})


@dataclass
class StorySegment:
    """A single classified narrative segment within the video timeline."""
    start: float
    end: float
    segment_type: str
    confidence: float
    emotion: Optional[str] = None
    retention_risk: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "type": self.segment_type,
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "confidence": round(self.confidence, 3),
            "emotion": self.emotion,
            "retention_risk": (
                round(self.retention_risk, 3)
                if self.retention_risk is not None
                else None
            ),
        }


@dataclass
class StoryAnalysis:
    """Full narrative/story intelligence result for a video clip."""
    available: bool = True
    narrative_flow: str = "unknown"
    segments: List[StorySegment] = field(default_factory=list)
    dominant_arc: str = "unknown"
    retention_score: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "narrative_flow": self.narrative_flow,
            "dominant_arc": self.dominant_arc,
            "retention_score": round(self.retention_score, 1),
            "segments": [s.to_dict() for s in self.segments[:12]],
            "warnings": list(self.warnings),
        }
