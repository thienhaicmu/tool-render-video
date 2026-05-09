"""
multivariant_execution_schema.py — Safe multi-variant render execution data structures.

Phase 29: FIRST phase where AI-prepared variant plans may become actual render jobs.
Execution is opt-in only. Every execution preserves audit metadata. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AIMultiVariantExecution:
    execution_id: str
    plan_id: str = ""
    variant_id: str = ""
    enabled: bool = False
    safe: bool = False
    advisory_origin: bool = True
    payload_overrides: dict = field(default_factory=dict)
    blocked_fields: list = field(default_factory=list)
    render_job_created: bool = False
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "plan_id": self.plan_id,
            "variant_id": self.variant_id,
            "enabled": bool(self.enabled),
            "safe": bool(self.safe),
            "advisory_origin": True,  # always hardcoded
            "payload_overrides": dict(self.payload_overrides),
            "blocked_fields": list(self.blocked_fields)[:20],
            "render_job_created": bool(self.render_job_created),
            "warnings": list(self.warnings)[:10],
            "explanation": list(self.explanation)[:10],
        }


@dataclass
class AIMultiVariantExecutionSet:
    available: bool = True
    execution_enabled: bool = False
    executions: List[AIMultiVariantExecution] = field(default_factory=list)
    executed_plan_ids: List[str] = field(default_factory=list)
    blocked_plan_ids: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "execution_enabled": bool(self.execution_enabled),
            "executions": [e.to_dict() for e in self.executions[:3]],
            "executed_plan_ids": list(self.executed_plan_ids)[:20],
            "blocked_plan_ids": list(self.blocked_plan_ids)[:20],
            "warnings": list(self.warnings)[:10],
        }
