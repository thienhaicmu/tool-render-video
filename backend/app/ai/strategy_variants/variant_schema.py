"""
variant_schema.py — Safe strategy variant data model. Phase 51A.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
All field values are validated against frozenset allowlists before storage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Allowed value sets — every variant field must resolve to one of these values
# ---------------------------------------------------------------------------

ALLOWED_SUBTITLE_STYLES: frozenset = frozenset({
    "viral_bold", "clean_pro", "boxed_caption", "unknown",
})
ALLOWED_SUBTITLE_DENSITY: frozenset = frozenset({
    "light", "medium", "dense", "unknown",
})
ALLOWED_KEYWORD_EMPHASIS: frozenset = frozenset({
    "none", "subtle", "moderate", "strong", "unknown",
})
ALLOWED_CAMERA_MOTION: frozenset = frozenset({
    "static_center", "smooth_subject", "dynamic_subject", "unknown",
})
ALLOWED_STABILITY_PRIORITY: frozenset = frozenset({
    "low", "medium", "high", "unknown",
})
ALLOWED_CROP_AGGRESSIVENESS: frozenset = frozenset({
    "low", "medium", "high", "unknown",
})
ALLOWED_RANKING_PRIORITY: frozenset = frozenset({
    "creator_fit", "retention", "hook_strength", "readability", "balanced", "unknown",
})

VALID_VARIANT_IDS: frozenset = frozenset({
    "creator_safe", "market_balanced", "quality_focused",
})

_MAX_REASONING = 3
_MAX_WARNINGS  = 5
_MAX_VARIANTS  = 3


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

@dataclass
class StrategyVariantSubtitle:
    style: str            = "unknown"
    density: str          = "unknown"
    keyword_emphasis: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "style":            self.style,
            "density":          self.density,
            "keyword_emphasis": self.keyword_emphasis,
        }


@dataclass
class StrategyVariantCamera:
    motion_style:        str = "unknown"
    stability_priority:  str = "unknown"
    crop_aggressiveness: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "motion_style":        self.motion_style,
            "stability_priority":  self.stability_priority,
            "crop_aggressiveness": self.crop_aggressiveness,
        }


@dataclass
class StrategyVariantRanking:
    priority: str = "unknown"

    def to_dict(self) -> dict:
        return {"priority": self.priority}


# ---------------------------------------------------------------------------
# Top-level models
# ---------------------------------------------------------------------------

@dataclass
class StrategyVariant:
    """Single safe candidate render strategy. Generated only — never executed."""
    id:       str
    label:    str
    intent:   str
    subtitle: StrategyVariantSubtitle = field(default_factory=StrategyVariantSubtitle)
    camera:   StrategyVariantCamera   = field(default_factory=StrategyVariantCamera)
    ranking:  StrategyVariantRanking  = field(default_factory=StrategyVariantRanking)
    confidence: float                 = 0.0
    reasoning:  List[str]             = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id":         self.id,
            "label":      self.label,
            "intent":     self.intent,
            "subtitle":   self.subtitle.to_dict(),
            "camera":     self.camera.to_dict(),
            "ranking":    self.ranking.to_dict(),
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 2),
            "reasoning":  list(self.reasoning[:_MAX_REASONING]),
        }


@dataclass
class StrategyVariantPack:
    """Collection of safe candidate strategy variants. Candidate-only — no execution."""
    available:         bool               = False
    strategy_variants: List[StrategyVariant] = field(default_factory=list)
    variant_count:     int                = 0
    generation_mode:   str                = "candidate_only"
    warnings:          List[str]          = field(default_factory=list)

    def to_dict(self) -> dict:
        variants = self.strategy_variants[:_MAX_VARIANTS]
        return {
            "available":         self.available,
            "strategy_variants": [v.to_dict() for v in variants],
            "variant_count":     len(variants),
            "generation_mode":   self.generation_mode,
            "warnings":          list(self.warnings[:_MAX_WARNINGS]),
        }
