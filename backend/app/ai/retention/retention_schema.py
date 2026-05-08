"""
retention_schema.py — Retention intelligence data structures. Phase 16.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


VALID_CATEGORIES: frozenset[str] = frozenset({
    "weak_hook",
    "long_setup",
    "low_energy",
    "silence_gap",
    "subtitle_overload",
    "story_drop",
    "unclear_payoff",
    "pacing_decay",
    "unknown",
})

VALID_SEVERITIES: frozenset[str] = frozenset({"low", "medium", "high"})


@dataclass
class RetentionRiskRegion:
    start: float
    end: float
    risk: float
    reason: str = ""
    category: str = "unknown"
    severity: str = "medium"
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "risk": round(float(self.risk), 3),
            "reason": self.reason,
            "category": self.category,
            "severity": self.severity,
            "suggestions": list(self.suggestions[:3]),
        }


@dataclass
class RetentionAnalysis:
    available: bool = True
    overall_retention_score: float = 0.0
    risk_regions: List[RetentionRiskRegion] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "overall_retention_score": round(self.overall_retention_score),
            "risk_regions": [r.to_dict() for r in self.risk_regions[:10]],
            "strengths": list(self.strengths[:6]),
            "warnings": list(self.warnings),
        }


@dataclass
class RetentionRecommendation:
    priority: str = "medium"
    recommended_action: str = ""
    reason: str = ""
    safe_to_auto_apply: bool = False
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "priority": self.priority,
            "recommended_action": self.recommended_action,
            "reason": self.reason,
            "safe_to_auto_apply": False,  # structurally locked False in Phase 16
            "metadata": dict(self.metadata),
        }
