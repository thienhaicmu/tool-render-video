"""
quality_schema.py — AI render quality evaluation data structures. Phase 45.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Evaluation-only: no file mutation, no render execution, no output deletion.
No internet, no cloud AI, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AIRenderQualityScore:
    """Quality score for a single render output. Metadata-only. Phase 45."""
    score_id: str = "unknown"
    output_id: str = ""
    output_path: str = ""

    # Per-dimension scores (0.0–100.0)
    overall_score: float = 0.0
    pacing_quality: float = 0.0
    subtitle_readability: float = 0.0
    camera_smoothness: float = 0.0
    hook_strength: float = 0.0
    retention_quality: float = 0.0
    creator_consistency: float = 0.0
    market_fit: float = 0.0

    # Evaluation confidence (0.0–1.0)
    confidence: float = 0.0

    quality_flags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score_id": self.score_id,
            "output_id": self.output_id,
            "output_path": self.output_path,
            "overall_score": round(float(self.overall_score), 2),
            "pacing_quality": round(float(self.pacing_quality), 2),
            "subtitle_readability": round(float(self.subtitle_readability), 2),
            "camera_smoothness": round(float(self.camera_smoothness), 2),
            "hook_strength": round(float(self.hook_strength), 2),
            "retention_quality": round(float(self.retention_quality), 2),
            "creator_consistency": round(float(self.creator_consistency), 2),
            "market_fit": round(float(self.market_fit), 2),
            "confidence": round(float(self.confidence), 4),
            "quality_flags": list(self.quality_flags),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation),
        }


@dataclass
class AIRenderQualityEvaluation:
    """Evaluation result across all render outputs. Phase 45.

    Evaluation-only: never mutates files, never triggers rerender,
    never deletes outputs, never overrides executor.
    """
    available: bool = True
    enabled: bool = False
    evaluation_mode: str = "evaluation_only"

    output_scores: List[AIRenderQualityScore] = field(default_factory=list)
    best_quality_output_id: str = ""

    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "evaluation_mode": self.evaluation_mode,
            "output_scores": [s.to_dict() for s in self.output_scores],
            "best_quality_output_id": self.best_quality_output_id,
            "warnings": list(self.warnings),
        }
