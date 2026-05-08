"""
beat_visual_schema.py — Beat-synced visual execution data structures. Phase 18.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


VALID_PULSE_STYLES: frozenset[str] = frozenset({
    "none", "soft_pulse", "punch_pulse", "cinematic_pulse"
})

VALID_TRANSITION_STYLES: frozenset[str] = frozenset({
    "none", "soft_cut", "beat_pulse", "energy_pop", "cinematic_push"
})

_MAX_PULSE_STRENGTH = 0.15   # hard cap — matches Phase 11 beat_execution constraint
_BPM_MIN = 60.0
_BPM_MAX = 190.0
_MIN_BEAT_COUNT = 4
_MAX_PULSE_REGIONS = 12
_MAX_TRANSITION_HINTS = 10


@dataclass
class BeatPulseRegion:
    start: float
    end: float
    pulse_strength: float = 0.0   # clamped to [0.0, 0.15]
    pulse_style: str = "none"
    beat_count: int = 0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "pulse_strength": round(float(self.pulse_strength), 3),
            "pulse_style": self.pulse_style,
            "beat_count": self.beat_count,
            "warnings": list(self.warnings),
        }


@dataclass
class TransitionHint:
    start: float
    end: float
    transition_style: str = "none"
    confidence: float = 0.0
    reason: str = ""
    safe_to_apply: bool = False   # structurally False in Phase 18

    def to_dict(self) -> dict:
        return {
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "transition_style": self.transition_style,
            "confidence": round(float(self.confidence), 3),
            "reason": self.reason,
            "safe_to_apply": False,   # always False — Phase 18 metadata-only
        }


@dataclass
class BeatVisualExecutionPlan:
    available: bool = True
    execution_mode: str = "metadata_only"   # always metadata_only in Phase 18
    bpm: Optional[float] = None
    pulse_regions: List[BeatPulseRegion] = field(default_factory=list)
    transition_hints: List[TransitionHint] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "execution_mode": self.execution_mode,
            "bpm": self.bpm,
            "pulse_regions": [r.to_dict() for r in self.pulse_regions[:_MAX_PULSE_REGIONS]],
            "transition_hints": [h.to_dict() for h in self.transition_hints[:_MAX_TRANSITION_HINTS]],
            "warnings": list(self.warnings),
        }
