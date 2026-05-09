"""
clip_candidate_schema.py — AI clip candidate data structures. Phase 35.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Discovery-only: no FFmpeg mutation, no segment reorder, no playback_speed changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AIClipCandidate:
    """A single discovered clip candidate window. Advisory-only."""
    candidate_id: str
    label: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    duration_sec: float = 0.0
    confidence: float = 0.0
    retention_score: float = 0.0
    story_score: float = 0.0
    hook_score: float = 0.0
    pacing_score: float = 0.0
    creator_style_score: float = 0.0
    safe: bool = False
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "label": self.label,
            "start_sec": round(float(self.start_sec), 3),
            "end_sec": round(float(self.end_sec), 3),
            "duration_sec": round(float(self.duration_sec), 3),
            "confidence": round(float(self.confidence), 4),
            "retention_score": round(float(self.retention_score), 2),
            "story_score": round(float(self.story_score), 2),
            "hook_score": round(float(self.hook_score), 2),
            "pacing_score": round(float(self.pacing_score), 2),
            "creator_style_score": round(float(self.creator_style_score), 2),
            "safe": bool(self.safe),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


@dataclass
class AIClipCandidatePack:
    """Collection of discovered clip candidates. Always discovery_only mode."""
    available: bool = True
    enabled: bool = False
    mode: str = "discovery_only"
    candidates: List[AIClipCandidate] = field(default_factory=list)
    recommended_candidate_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "mode": str(self.mode),
            "candidates": [c.to_dict() for c in self.candidates],
            "recommended_candidate_id": self.recommended_candidate_id,
            "warnings": list(self.warnings),
        }
