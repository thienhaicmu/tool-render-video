"""
clip_batch_schema.py — AI multi-clip batch plan data structures. Phase 37.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Planning-only: no FFmpeg mutation, no render execution, no job enqueue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

_ALLOWED_RENDER_STRATEGIES = frozenset({
    "safe_default",
    "retention_focused",
    "creator_style_focused",
    "subtitle_clarity",
    "camera_dynamic_safe",
})

_ALLOWED_VARIANT_STRATEGIES = frozenset({
    "single_safe",
    "selected_variant",
    "multivariant_limited",
})


@dataclass
class AIClipBatchPlan:
    """A single batch render plan entry. Planning-only — no render execution."""
    batch_plan_id: str
    segment_id: str = ""
    candidate_id: str = ""
    label: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    duration_sec: float = 0.0
    rank: int = 0
    score: float = 0.0
    render_strategy: str = "safe_default"
    variant_strategy: str = "single_safe"
    subtitle_strategy: str = "default"
    camera_strategy: str = "default"
    timing_strategy: str = "default"
    creator_style: str = ""
    safe: bool = False
    planned_payload_overrides: Dict[str, object] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "batch_plan_id": self.batch_plan_id,
            "segment_id": self.segment_id,
            "candidate_id": self.candidate_id,
            "label": self.label,
            "start_sec": round(float(self.start_sec), 3),
            "end_sec": round(float(self.end_sec), 3),
            "duration_sec": round(float(self.duration_sec), 3),
            "rank": int(self.rank),
            "score": round(float(self.score), 2),
            "render_strategy": self.render_strategy,
            "variant_strategy": self.variant_strategy,
            "subtitle_strategy": self.subtitle_strategy,
            "camera_strategy": self.camera_strategy,
            "timing_strategy": self.timing_strategy,
            "creator_style": self.creator_style,
            "safe": bool(self.safe),
            "planned_payload_overrides": dict(self.planned_payload_overrides),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation),
        }


@dataclass
class AIClipBatchPlanSet:
    """Result of multi-clip batch planning. Always planning_only mode."""
    available: bool = True
    enabled: bool = False
    mode: str = "planning_only"
    plans: List[AIClipBatchPlan] = field(default_factory=list)
    recommended_plan_ids: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "mode": str(self.mode),
            "plans": [p.to_dict() for p in self.plans],
            "recommended_plan_ids": list(self.recommended_plan_ids),
            "warnings": list(self.warnings),
        }
