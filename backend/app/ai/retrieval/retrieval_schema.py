"""
retrieval_schema.py — Creator intelligence retrieval data structures. Phase 41.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Retrieval-only: no FFmpeg mutation, no render execution, no model training.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AICreatorRetrievalMatch:
    """A single retrieved creator intelligence match. Metadata-only."""
    match_id: str
    creator_style: str = ""
    pattern_type: str = ""
    confidence: float = 0.0
    retrieval_score: float = 0.0
    matched_tags: List[str] = field(default_factory=list)

    subtitle_influence: dict = field(default_factory=dict)
    pacing_influence: dict = field(default_factory=dict)
    camera_influence: dict = field(default_factory=dict)
    retention_influence: dict = field(default_factory=dict)
    hook_influence: dict = field(default_factory=dict)

    safe: bool = False
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "match_id": self.match_id,
            "creator_style": self.creator_style,
            "pattern_type": self.pattern_type,
            "confidence": round(float(self.confidence), 4),
            "retrieval_score": round(float(self.retrieval_score), 4),
            "matched_tags": list(self.matched_tags),
            "subtitle_influence": dict(self.subtitle_influence),
            "pacing_influence": dict(self.pacing_influence),
            "camera_influence": dict(self.camera_influence),
            "retention_influence": dict(self.retention_influence),
            "hook_influence": dict(self.hook_influence),
            "safe": bool(self.safe),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation),
        }


@dataclass
class AICreatorRetrievalPack:
    """Pack of retrieved creator intelligence matches. Phase 41."""
    available: bool = True
    enabled: bool = False
    retrieval_mode: str = "assistive_only"
    matches: List[AICreatorRetrievalMatch] = field(default_factory=list)
    recommended_creator_style: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "retrieval_mode": self.retrieval_mode,
            "matches": [m.to_dict() for m in self.matches],
            "recommended_creator_style": self.recommended_creator_style,
            "warnings": list(self.warnings),
        }
