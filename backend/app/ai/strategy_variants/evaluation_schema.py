"""
evaluation_schema.py — Variant evaluation data model. Phase 51B.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
Scores are integers in [0, 100]. Confidence is float in [0.0, 1.0].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

_MAX_REASONING = 3
_MAX_WARNINGS  = 5
_MAX_RANKING   = 3


@dataclass
class VariantScore:
    """Scored evaluation of a single strategy variant. Evaluation-only — not applied."""
    id:          str
    score:       int    # 0-100 composite weighted score
    creator_fit: int    # 0-100
    market_fit:  int    # 0-100
    quality_fit: int    # 0-100
    safety_fit:  int    # 0-100
    confidence:  float  # 0.0-1.0
    reasoning:   List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id":          self.id,
            "score":       max(0, min(100, self.score)),
            "creator_fit": max(0, min(100, self.creator_fit)),
            "market_fit":  max(0, min(100, self.market_fit)),
            "quality_fit": max(0, min(100, self.quality_fit)),
            "safety_fit":  max(0, min(100, self.safety_fit)),
            "confidence":  round(max(0.0, min(1.0, float(self.confidence))), 2),
            "reasoning":   list(self.reasoning[:_MAX_REASONING]),
        }


@dataclass
class VariantEvaluationPack:
    """Ranked evaluation of all Phase 51A strategy variants. Evaluation-only."""
    available:        bool               = False
    best_variant_id:  Optional[str]      = None
    ranking:          List[VariantScore] = field(default_factory=list)
    confidence:       float              = 0.0
    reasoning:        List[str]          = field(default_factory=list)
    evaluation_mode:  str                = "evaluation_only"
    warnings:         List[str]          = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available":       self.available,
            "best_variant_id": self.best_variant_id,
            "ranking":         [v.to_dict() for v in self.ranking[:_MAX_RANKING]],
            "confidence":      round(max(0.0, min(1.0, float(self.confidence))), 2),
            "reasoning":       list(self.reasoning[:_MAX_REASONING]),
            "evaluation_mode": self.evaluation_mode,
            "warnings":        list(self.warnings[:_MAX_WARNINGS]),
        }
