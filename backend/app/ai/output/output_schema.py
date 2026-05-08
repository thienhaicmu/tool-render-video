"""
output_schema.py — AI output ranking and best export recommendation data structures.

Phase 30: recommendation_only. No auto-upload, no auto-publish, no file deletion.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AIOutputScore:
    output_id: str
    path: str = ""
    variant_id: str = ""
    score: float = 0.0
    confidence: float = 0.0
    rank: int = 0
    recommended: bool = False
    quality_flags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "output_id": self.output_id,
            "path": self.path,
            "variant_id": self.variant_id,
            "score": round(float(max(0.0, min(100.0, self.score))), 2),
            "confidence": round(float(max(0.0, min(1.0, self.confidence))), 4),
            "rank": int(self.rank),
            "recommended": bool(self.recommended),
            "quality_flags": list(self.quality_flags)[:10],
            "warnings": list(self.warnings)[:10],
            "explanation": list(self.explanation)[:10],
        }


@dataclass
class AIOutputRanking:
    available: bool = True
    mode: str = "recommendation_only"
    outputs: List[AIOutputScore] = field(default_factory=list)
    best_output_id: Optional[str] = None
    best_output_path: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "mode": "recommendation_only",  # always hardcoded
            "outputs": [o.to_dict() for o in self.outputs[:20]],
            "best_output_id": self.best_output_id,
            "best_output_path": self.best_output_path,
            "warnings": list(self.warnings)[:10],
        }
