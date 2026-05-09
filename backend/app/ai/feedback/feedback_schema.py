"""
feedback_schema.py — Creator feedback intelligence data structures. Phase 43.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Feedback-only: no FFmpeg mutation, no render execution, no model training.
No internet, no cloud AI, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AICreatorFeedbackSignal:
    """A single creator feedback signal. Local-only, deterministic. Phase 43."""
    feedback_id: str = "unknown"

    # Creator behavior captured
    creator_style: str = ""
    selected_variant: str = ""
    selected_output_rank: int = 0
    subtitle_style: str = ""
    pacing_style: str = ""
    camera_style: str = ""
    duration_bucket: str = ""

    # Action flags
    exported: bool = False
    selected: bool = False
    ignored: bool = False

    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "creator_style": self.creator_style,
            "selected_variant": self.selected_variant,
            "selected_output_rank": int(self.selected_output_rank),
            "subtitle_style": self.subtitle_style,
            "pacing_style": self.pacing_style,
            "camera_style": self.camera_style,
            "duration_bucket": self.duration_bucket,
            "exported": bool(self.exported),
            "selected": bool(self.selected),
            "ignored": bool(self.ignored),
            "confidence": round(float(self.confidence), 4),
            "tags": list(self.tags),
            "warnings": list(self.warnings),
        }


@dataclass
class AIFeedbackLearningPack:
    """Creator feedback learning pack. Phase 43.

    Assistive-only: influences ranking and weighting only.
    Never overrides user settings, never mutates FFmpeg.
    """
    available: bool = True
    enabled: bool = False
    feedback_mode: str = "assistive_only"

    feedback_signals: List[dict] = field(default_factory=list)
    learned_feedback_patterns: dict = field(default_factory=dict)
    ranking_biases: dict = field(default_factory=dict)

    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "feedback_mode": self.feedback_mode,
            "feedback_signals": list(self.feedback_signals),
            "learned_feedback_patterns": dict(self.learned_feedback_patterns),
            "ranking_biases": dict(self.ranking_biases),
            "warnings": list(self.warnings),
        }
