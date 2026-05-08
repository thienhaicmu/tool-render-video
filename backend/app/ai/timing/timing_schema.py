"""
timing_schema.py — Timing mutation plan schema. Phase 19.

Dataclasses only. No Pydantic. No heavy deps. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# ── Allowed action values ─────────────────────────────────────────────────────
VALID_ACTIONS: frozenset[str] = frozenset({
    "tighten_setup",
    "trim_silence",
    "shorten_outro",
    "hold_hook",
    "no_change",
    "none",
})

# Hard cap: no AI-proposed trim may exceed this
_MAX_TRIM_SECONDS: float = 1.5

# Safety gate: candidates below this confidence are never safe
_MIN_CONFIDENCE: float = 0.70

# Minimum region duration for a trim candidate to be considered
_MIN_REGION_DURATION: float = 3.0

# Maximum candidates returned from the plan
_MAX_CANDIDATES: int = 10


@dataclass
class TimingMutationCandidate:
    start: float
    end: float
    action: str = "none"
    confidence: float = 0.0
    reason: str = ""
    risk_category: str = "unknown"
    max_trim_seconds: float = 0.0   # clamped to [0.0, _MAX_TRIM_SECONDS]
    safe_to_apply: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        action = self.action if self.action in VALID_ACTIONS else "none"
        trim = max(0.0, min(_MAX_TRIM_SECONDS, float(self.max_trim_seconds)))
        return {
            "start": self.start,
            "end": self.end,
            "action": action,
            "confidence": round(float(self.confidence), 4),
            "reason": str(self.reason),
            "risk_category": str(self.risk_category),
            "max_trim_seconds": round(trim, 3),
            "safe_to_apply": bool(self.safe_to_apply),
            "warnings": list(self.warnings),
        }


@dataclass
class TimingMutationPlan:
    available: bool = True
    mode: str = "advisory"
    candidates: List[TimingMutationCandidate] = field(default_factory=list)
    estimated_retention_gain: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "mode": str(self.mode),
            "candidates": [c.to_dict() for c in self.candidates[:_MAX_CANDIDATES]],
            "estimated_retention_gain": round(float(self.estimated_retention_gain), 4),
            "warnings": list(self.warnings),
        }
