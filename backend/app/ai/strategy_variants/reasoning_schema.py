"""
reasoning_schema.py — Best strategy reasoning data model. Phase 51C.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
All text fields are creator-facing; no debug strings, no internal class names.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Allowed recommendation strength values
ALLOWED_STRENGTHS: frozenset = frozenset({"none", "weak", "moderate", "strong"})

_MAX_WHY        = 4
_MAX_TRADEOFFS  = 2
_MAX_WARNINGS   = 5

# Confidence thresholds for recommendation strength
_CONF_WEAK_MAX     = 0.65
_CONF_MODERATE_MAX = 0.82
_SCORE_GAP_STRONG  = 5   # minimum score gap for "strong" when confidence > 0.82


@dataclass
class BestStrategyReasoning:
    """Creator-facing reasoning for why the best variant was selected. Explanation-only."""
    selected_variant_id:    Optional[str]  = None
    selected_label:         str            = ""
    confidence:             float          = 0.0
    summary:                str            = "No confident AI strategy recommendation available."
    why_selected:           List[str]      = field(default_factory=list)
    tradeoffs:              List[str]      = field(default_factory=list)
    recommendation_strength: str           = "none"
    warnings:               List[str]      = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "selected_variant_id":     self.selected_variant_id,
            "selected_label":          self.selected_label,
            "confidence":              round(max(0.0, min(1.0, float(self.confidence))), 2),
            "summary":                 self.summary,
            "why_selected":            list(self.why_selected[:_MAX_WHY]),
            "tradeoffs":               list(self.tradeoffs[:_MAX_TRADEOFFS]),
            "recommendation_strength": self.recommendation_strength,
            "warnings":                list(self.warnings[:_MAX_WARNINGS]),
        }
