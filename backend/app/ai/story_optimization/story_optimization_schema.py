"""
story_optimization_schema.py — Story optimization plan schema. Phase 20.

Dataclasses only. No Pydantic. No heavy deps. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ── Allowed values ────────────────────────────────────────────────────────────
VALID_ISSUE_TYPES: frozenset[str] = frozenset({
    "weak_hook",
    "missing_setup",
    "long_setup",
    "weak_build_up",
    "missing_climax",
    "weak_payoff",
    "abrupt_outro",
    "unclear_arc",
    "retention_risk",
    "unknown",
})

VALID_SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high"})

VALID_FLOW_TYPES: frozenset[str] = frozenset({
    "hook_to_climax",
    "linear",
    "flat",
    "unknown",
})

# Plan caps
_MAX_ISSUES: int = 10
_MAX_RECOMMENDATIONS: int = 8


@dataclass
class StoryOptimizationIssue:
    start: Optional[float] = None
    end: Optional[float] = None
    issue_type: str = "unknown"
    severity: str = "medium"
    reason: str = ""
    suggested_action: str = ""
    confidence: float = 0.0
    safe_to_auto_apply: bool = False
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        issue_type = self.issue_type if self.issue_type in VALID_ISSUE_TYPES else "unknown"
        severity = self.severity if self.severity in VALID_SEVERITIES else "medium"
        return {
            "start": self.start,
            "end": self.end,
            "issue_type": issue_type,
            "severity": severity,
            "reason": str(self.reason),
            "suggested_action": str(self.suggested_action),
            "confidence": round(float(self.confidence), 4),
            "safe_to_auto_apply": False,  # structurally False in Phase 20
            "metadata": dict(self.metadata),
        }


@dataclass
class StoryOptimizationPlan:
    available: bool = True
    narrative_score: float = 0.0
    flow_type: str = "unknown"
    issues: List[StoryOptimizationIssue] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        flow_type = self.flow_type if self.flow_type in VALID_FLOW_TYPES else "unknown"
        return {
            "available": bool(self.available),
            "narrative_score": round(float(self.narrative_score), 1),
            "flow_type": flow_type,
            "issues": [i.to_dict() for i in self.issues[:_MAX_ISSUES]],
            "recommendations": list(self.recommendations[:_MAX_RECOMMENDATIONS]),
            "warnings": list(self.warnings),
        }
