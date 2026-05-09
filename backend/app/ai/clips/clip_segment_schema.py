"""
clip_segment_schema.py — AI clip segment selection data structures. Phase 36.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Selection-only: no FFmpeg mutation, no segment reorder, no render execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AIClipSegmentPlan:
    """A single selected clip segment plan. Planning-only — no render execution."""
    segment_id: str
    candidate_id: str = ""
    label: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    duration_sec: float = 0.0
    selected: bool = False
    rank: int = 0
    confidence: float = 0.0
    score: float = 0.0
    source_scores: Dict[str, float] = field(default_factory=dict)
    safe: bool = False
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "candidate_id": self.candidate_id,
            "label": self.label,
            "start_sec": round(float(self.start_sec), 3),
            "end_sec": round(float(self.end_sec), 3),
            "duration_sec": round(float(self.duration_sec), 3),
            "selected": bool(self.selected),
            "rank": int(self.rank),
            "confidence": round(float(self.confidence), 4),
            "score": round(float(self.score), 2),
            "source_scores": {k: round(float(v), 2) for k, v in self.source_scores.items()},
            "safe": bool(self.safe),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


@dataclass
class AIClipSegmentSelection:
    """Result of clip segment selection. Always selection_only mode."""
    available: bool = True
    enabled: bool = False
    mode: str = "selection_only"
    selected_segments: List[AIClipSegmentPlan] = field(default_factory=list)
    rejected_candidates: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "mode": str(self.mode),
            "selected_segments": [s.to_dict() for s in self.selected_segments],
            "rejected_candidates": list(self.rejected_candidates),
            "warnings": list(self.warnings),
        }
