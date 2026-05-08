"""
execution_schema.py — AI execution recommendation data structures. Phase 25.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Advisory only. No render execution. No FFmpeg mutation. No payload mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Allowed category values
VALID_CATEGORIES: frozenset[str] = frozenset({
    "subtitle",
    "pacing",
    "camera",
    "creator_style",
    "retention",
    "visual_rhythm",
    "safe_baseline",
})


@dataclass
class AIExecutionRecommendation:
    """Phase 25 — A single advisory execution recommendation.

    Never auto-applied. Never mutates payload. Never triggers rendering.
    advisory_only is always True.
    """
    recommendation_id: str
    label: str = ""
    category: str = ""
    confidence: float = 0.0
    safe_to_apply: bool = False
    advisory_only: bool = True
    recommended_settings: dict = field(default_factory=dict)
    blocked_settings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        category = self.category if self.category in VALID_CATEGORIES else "safe_baseline"
        return {
            "recommendation_id": str(self.recommendation_id),
            "label": str(self.label),
            "category": category,
            "confidence": round(min(1.0, max(0.0, float(self.confidence))), 4),
            "safe_to_apply": bool(self.safe_to_apply),
            "advisory_only": True,          # always True in Phase 25
            "recommended_settings": dict(self.recommended_settings),
            "blocked_settings": list(self.blocked_settings),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation[:5]),
        }


@dataclass
class AIExecutionPack:
    """Phase 25 — Advisory pack of execution recommendations.

    Aggregates all AI execution hints into a single compact structure.
    mode is always "advisory". Never triggers execution.
    """
    available: bool = True
    mode: str = "advisory"
    recommendations: List[AIExecutionRecommendation] = field(default_factory=list)
    recommended_pack_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "mode": "advisory",             # always advisory in Phase 25
            "recommendations": [r.to_dict() for r in self.recommendations[:10]],
            "recommended_pack_id": self.recommended_pack_id,
            "warnings": list(self.warnings),
        }
