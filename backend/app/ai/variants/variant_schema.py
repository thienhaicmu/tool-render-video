"""
variant_schema.py — AI variant plan schema. Phase 21.

Dataclasses only. No Pydantic. No heavy deps. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ── Allowed values ────────────────────────────────────────────────────────────
VALID_PURPOSES: frozenset[str] = frozenset({
    "safe_baseline",
    "retention",
    "hook",
    "subtitle",
    "pacing",
    "story",
    "creator_style",
})

VALID_RISKS: frozenset[str] = frozenset({"low", "medium", "high"})

# Clamp bounds for ai_variant_count
_VARIANT_COUNT_MIN: int = 1
_VARIANT_COUNT_MAX: int = 5


def clamp_variant_count(value: int) -> int:
    """Clamp requested variant count to [1, 5]."""
    try:
        return max(_VARIANT_COUNT_MIN, min(_VARIANT_COUNT_MAX, int(value)))
    except Exception:
        return _VARIANT_COUNT_MIN


@dataclass
class AIVariantPlan:
    variant_id: str
    label: str = ""
    purpose: str = "safe_baseline"
    confidence: float = 0.0
    risk: str = "low"
    suggested_changes: dict = field(default_factory=dict)
    expected_gain: float = 0.0
    safe_to_render: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        purpose = self.purpose if self.purpose in VALID_PURPOSES else "safe_baseline"
        risk = self.risk if self.risk in VALID_RISKS else "low"
        return {
            "variant_id": str(self.variant_id),
            "label": str(self.label),
            "purpose": purpose,
            "confidence": round(float(self.confidence), 4),
            "risk": risk,
            "suggested_changes": dict(self.suggested_changes),
            "expected_gain": round(float(self.expected_gain), 4),
            "safe_to_render": bool(self.safe_to_render),
            "warnings": list(self.warnings),
        }


@dataclass
class AIVariantSet:
    available: bool = True
    mode: str = "advisory"
    variants: List[AIVariantPlan] = field(default_factory=list)
    recommended_variant_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "mode": str(self.mode),
            "variants": [v.to_dict() for v in self.variants[:_VARIANT_COUNT_MAX]],
            "recommended_variant_id": self.recommended_variant_id,
            "warnings": list(self.warnings),
        }
