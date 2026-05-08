"""
policy_schema.py — AI apply policy data structures.

Phase 31: controls HOW MUCH AI influence is allowed during render orchestration.
Policies never bypass hard safety blocks. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AIApplyPolicy:
    policy_name: str = "conservative"
    allow_safe_mutations: bool = True
    allow_multivariant_execution: bool = False
    allow_execution_recommendations: bool = True
    allow_execution_simulation: bool = True
    allow_output_ranking: bool = True
    allow_timing_candidates: bool = False
    allow_creator_style_adaptation: bool = True
    allow_visual_rhythm_guidance: bool = True
    allow_aggressive_behavior: bool = False
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "policy_name": self.policy_name,
            "allow_safe_mutations": bool(self.allow_safe_mutations),
            "allow_multivariant_execution": bool(self.allow_multivariant_execution),
            "allow_execution_recommendations": bool(self.allow_execution_recommendations),
            "allow_execution_simulation": bool(self.allow_execution_simulation),
            "allow_output_ranking": bool(self.allow_output_ranking),
            "allow_timing_candidates": bool(self.allow_timing_candidates),
            "allow_creator_style_adaptation": bool(self.allow_creator_style_adaptation),
            "allow_visual_rhythm_guidance": bool(self.allow_visual_rhythm_guidance),
            "allow_aggressive_behavior": bool(self.allow_aggressive_behavior),
            "warnings": list(self.warnings)[:10],
            "explanation": list(self.explanation)[:10],
        }


@dataclass
class AIPolicyDecision:
    available: bool = True
    selected_policy: str = "conservative"
    effective_policy: dict = field(default_factory=dict)
    blocked_capabilities: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "selected_policy": self.selected_policy,
            "effective_policy": dict(self.effective_policy),
            "blocked_capabilities": list(self.blocked_capabilities)[:30],
            "warnings": list(self.warnings)[:10],
        }
