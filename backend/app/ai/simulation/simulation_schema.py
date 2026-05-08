"""
simulation_schema.py — AI execution simulation data structures. Phase 26.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Simulation only. No render execution. No FFmpeg mutation. No payload mutation.
advisory_only is always True.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Allowed safety_level values
VALID_SAFETY_LEVELS: frozenset[str] = frozenset({"safe", "caution", "blocked"})


@dataclass
class AIExecutionSimulation:
    """Phase 26 — A single advisory execution simulation result.

    Estimates the likely impact of applying an execution recommendation.
    Never auto-applied. Never mutates payload. Never triggers rendering.
    advisory_only is always True. mode is always simulation_only.
    """
    simulation_id: str
    recommendation_id: str = ""
    label: str = ""
    estimated_retention_gain: float = 0.0
    estimated_story_gain: float = 0.0
    estimated_subtitle_clarity_gain: float = 0.0
    estimated_pacing_gain: float = 0.0
    confidence: float = 0.0
    safety_level: str = "safe"
    advisory_only: bool = True
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        safety = self.safety_level if self.safety_level in VALID_SAFETY_LEVELS else "safe"
        return {
            "simulation_id": str(self.simulation_id),
            "recommendation_id": str(self.recommendation_id),
            "label": str(self.label),
            "estimated_retention_gain": round(
                max(-100.0, min(100.0, float(self.estimated_retention_gain))), 4
            ),
            "estimated_story_gain": round(
                max(-100.0, min(100.0, float(self.estimated_story_gain))), 4
            ),
            "estimated_subtitle_clarity_gain": round(
                max(-100.0, min(100.0, float(self.estimated_subtitle_clarity_gain))), 4
            ),
            "estimated_pacing_gain": round(
                max(-100.0, min(100.0, float(self.estimated_pacing_gain))), 4
            ),
            "confidence": round(min(1.0, max(0.0, float(self.confidence))), 4),
            "safety_level": safety,
            "advisory_only": True,          # always True in Phase 26
            "warnings": list(self.warnings),
            "explanation": list(self.explanation[:5]),
        }


@dataclass
class AISimulationPack:
    """Phase 26 — Advisory pack of execution simulation results.

    Aggregates all AI execution simulations into a single compact structure.
    mode is always "simulation_only". Never triggers execution.
    """
    available: bool = True
    mode: str = "simulation_only"
    simulations: List[AIExecutionSimulation] = field(default_factory=list)
    recommended_simulation_id: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "mode": "simulation_only",      # always simulation_only in Phase 26
            "simulations": [s.to_dict() for s in self.simulations[:10]],
            "recommended_simulation_id": self.recommended_simulation_id,
            "warnings": list(self.warnings),
        }
