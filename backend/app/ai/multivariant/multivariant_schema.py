"""
multivariant_schema.py — Safe multi-variant render planning data structures.

Phase 28: planning_only. No render execution, no enqueueing, no job creation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AIMultiVariantRenderPlan:
    plan_id: str
    variant_id: str
    label: str
    renderable: bool
    safe_to_enqueue: bool
    advisory_only: bool
    mutation_ids: List[str]
    planned_payload_overrides: dict
    blocked_fields: List[str]
    warnings: List[str]
    explanation: str

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "variant_id": self.variant_id,
            "label": self.label,
            "renderable": bool(self.renderable),
            "safe_to_enqueue": bool(self.safe_to_enqueue),
            "advisory_only": True,  # always hardcoded
            "mutation_ids": list(self.mutation_ids)[:20],
            "planned_payload_overrides": dict(self.planned_payload_overrides),
            "blocked_fields": list(self.blocked_fields)[:20],
            "warnings": list(self.warnings)[:10],
            "explanation": str(self.explanation)[:300],
        }


@dataclass
class AIMultiVariantRenderSet:
    available: bool
    mode: str
    plans: List[AIMultiVariantRenderPlan]
    recommended_plan_id: Optional[str]
    warnings: List[str]

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "mode": "planning_only",  # always hardcoded
            "plans": [p.to_dict() for p in self.plans[:5]],
            "recommended_plan_id": self.recommended_plan_id,
            "warnings": list(self.warnings)[:10],
        }
