"""
preview_schema.py — AI render decision preview data structures. Phase 24.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Advisory only. No render execution. No FFmpeg mutation. No payload mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Allowed safety_status values
VALID_SAFETY_STATUSES: frozenset[str] = frozenset({
    "safe",
    "caution",
    "blocked",
    "unavailable",
})


@dataclass
class AIRenderDecisionPreview:
    """Phase 24 — Compact advisory summary of all AI render decisions.

    Intended for developer/creator review before any render execution.
    Never auto-applied. Never mutates payload. Never triggers rendering.
    mode is always "advisory".
    """
    available: bool = True
    mode: str = "advisory"
    selected_variant_id: Optional[str] = None
    creator_style: str = ""
    decision_summary: str = ""
    recommended_actions: List[str] = field(default_factory=list)
    blocked_actions: List[str] = field(default_factory=list)
    safety_status: str = "safe"
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        status = self.safety_status if self.safety_status in VALID_SAFETY_STATUSES else "safe"
        return {
            "available": bool(self.available),
            "mode": "advisory",           # always advisory in Phase 24
            "selected_variant_id": self.selected_variant_id,
            "creator_style": str(self.creator_style),
            "decision_summary": str(self.decision_summary),
            "recommended_actions": list(self.recommended_actions[:10]),
            "blocked_actions": list(self.blocked_actions[:10]),
            "safety_status": status,
            "confidence": round(min(1.0, max(0.0, float(self.confidence))), 4),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation[:8]),
        }


@dataclass
class AIPreviewSafetyReport:
    """Phase 24 — Safety gate report for a render decision preview.

    safe_to_execute is always False in Phase 24 — advisory only.
    advisory_only is always True.
    """
    safe_to_preview: bool = True
    safe_to_execute: bool = False      # hardcoded — preview never triggers execution
    blocked_reasons: List[str] = field(default_factory=list)
    advisory_only: bool = True         # hardcoded
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "safe_to_preview": bool(self.safe_to_preview),
            "safe_to_execute": False,   # never True in Phase 24
            "blocked_reasons": list(self.blocked_reasons),
            "advisory_only": True,      # never False in Phase 24
            "warnings": list(self.warnings),
        }
