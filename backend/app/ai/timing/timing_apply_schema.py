"""
timing_apply_schema.py — Safe timing mutation apply schema. Phase 32.

Dataclasses only. No Pydantic. No heavy deps. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ── Allowed mutation types ────────────────────────────────────────────────────
_ALLOWED_MUTATION_TYPES: frozenset[str] = frozenset({
    "trim_silence_gap",
    "tighten_setup",
    "shorten_outro",
    "reduce_dead_air",
})

# ── Forbidden mutation types (NEVER applied) ──────────────────────────────────
_FORBIDDEN_MUTATION_TYPES: frozenset[str] = frozenset({
    "playback_speed",
    "segment_reorder",
    "subtitle_timing_rewrite",
    "arbitrary_cut",
    "ffmpeg_command_change",
})

# ── Safety bounds ─────────────────────────────────────────────────────────────
_MAX_SINGLE_DELTA_SEC: float = 1.5
_MAX_TOTAL_DELTA_SEC: float = 4.0
_MIN_CONFIDENCE: float = 0.65


@dataclass
class AITimingMutationApply:
    mutation_id: str
    mutation_type: str = ""
    source_candidate_id: str = ""
    confidence: float = 0.0
    applied: bool = False
    safe: bool = False
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None
    delta_sec: float = 0.0
    reason: str = ""
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        mutation_type = (
            self.mutation_type
            if self.mutation_type in _ALLOWED_MUTATION_TYPES
            else "unknown"
        )
        delta_sec = max(0.0, min(_MAX_SINGLE_DELTA_SEC, float(self.delta_sec)))
        return {
            "mutation_id": str(self.mutation_id),
            "mutation_type": mutation_type,
            "source_candidate_id": str(self.source_candidate_id),
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 4),
            "applied": bool(self.applied),
            "safe": bool(self.safe),
            "start_sec": float(self.start_sec) if self.start_sec is not None else None,
            "end_sec": float(self.end_sec) if self.end_sec is not None else None,
            "delta_sec": round(delta_sec, 3),
            "reason": str(self.reason)[:200],
            "warnings": list(self.warnings)[:10],
            "explanation": list(self.explanation)[:10],
        }


@dataclass
class AITimingApplyPack:
    available: bool = True
    enabled: bool = False
    mode: str = "disabled"
    applied_mutations: List[AITimingMutationApply] = field(default_factory=list)
    blocked_mutations: List[AITimingMutationApply] = field(default_factory=list)
    total_delta_sec: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        total_delta = max(0.0, min(_MAX_TOTAL_DELTA_SEC, float(self.total_delta_sec)))
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "mode": str(self.mode),
            "applied_mutations": [m.to_dict() for m in self.applied_mutations[:20]],
            "blocked_mutations": [m.to_dict() for m in self.blocked_mutations[:20]],
            "total_delta_sec": round(total_delta, 3),
            "warnings": list(self.warnings)[:10],
        }
