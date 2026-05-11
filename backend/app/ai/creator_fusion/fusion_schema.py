"""
fusion_schema.py — Creator Preference Fusion schema. Phase 50D.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Metadata-only: no render engine rewrite, no subtitle timing rewrite,
no motion_crop rewrite, no FFmpeg mutation, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ── Allowed values ─────────────────────────────────────────────────────────────

ALLOWED_SUBTITLE_STYLES   = frozenset({"viral_bold", "clean_pro", "boxed_caption", "unknown"})
ALLOWED_DENSITIES         = frozenset({"light", "medium", "dense", "unknown"})
ALLOWED_EMPHASIS          = frozenset({"none", "subtle", "moderate", "strong", "unknown"})
ALLOWED_READABILITY       = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_CAMERA_MOTION     = frozenset({"static_center", "smooth_subject", "dynamic_subject", "unknown"})
ALLOWED_AGGRESSIVENESS    = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_PRIORITY          = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_CONTENT_STYLES    = frozenset({"podcast", "educational", "viral", "unknown"})
ALLOWED_RANKING_PREFS     = frozenset({"engagement", "retention", "reach", "unknown"})
ALLOWED_MARKET_FIT        = frozenset({"low", "medium", "high", "unknown"})


@dataclass
class SubtitleFusionProfile:
    """Fused subtitle preference — creator-first, market-aware."""

    style:                str = "unknown"
    density:              str = "unknown"
    keyword_emphasis:     str = "unknown"
    readability_priority: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "style":                self.style,
            "density":              self.density,
            "keyword_emphasis":     self.keyword_emphasis,
            "readability_priority": self.readability_priority,
        }


@dataclass
class CameraFusionProfile:
    """Fused camera preference — creator-first, market-aware."""

    motion_style:       str = "unknown"
    crop_aggressiveness: str = "unknown"
    stability_priority: str = "unknown"
    smoothness_priority: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "motion_style":        self.motion_style,
            "crop_aggressiveness": self.crop_aggressiveness,
            "stability_priority":  self.stability_priority,
            "smoothness_priority": self.smoothness_priority,
        }


@dataclass
class ClipFusionProfile:
    """Fused clip / content preference derived from feedback + market signals."""

    content_style:       str = "unknown"
    ranking_preference:  str = "unknown"

    def to_dict(self) -> dict:
        return {
            "content_style":      self.content_style,
            "ranking_preference": self.ranking_preference,
        }


@dataclass
class MarketAlignmentFusion:
    """Creator–market alignment summary."""

    target_market: str = "unknown"
    market_fit:    str = "unknown"

    def to_dict(self) -> dict:
        return {
            "target_market": self.target_market,
            "market_fit":    self.market_fit,
        }


@dataclass
class QualityAlignmentFusion:
    """Fused quality priority signals from render evaluation + creator preference."""

    readability_priority: str = "unknown"
    smoothness_priority:  str = "unknown"

    def to_dict(self) -> dict:
        return {
            "readability_priority": self.readability_priority,
            "smoothness_priority":  self.smoothness_priority,
        }


@dataclass
class CreatorPreferenceProfile:
    """Phase 50D — unified, deterministic creator preference profile.

    Fuses Phase 50A subtitle, Phase 50B camera, Phase 50C influence,
    creator feedback, market intelligence, and quality evaluation into
    one coherent creator model.  Advisory metadata only — no execution.
    """

    available:         bool = False
    subtitle:          SubtitleFusionProfile   = field(default_factory=SubtitleFusionProfile)
    camera:            CameraFusionProfile     = field(default_factory=CameraFusionProfile)
    clip:              ClipFusionProfile       = field(default_factory=ClipFusionProfile)
    market_alignment:  MarketAlignmentFusion   = field(default_factory=MarketAlignmentFusion)
    quality_alignment: QualityAlignmentFusion  = field(default_factory=QualityAlignmentFusion)
    confidence:        float                   = 0.0
    reasoning:         List[str]               = field(default_factory=list)
    conflicts_resolved: List[str]              = field(default_factory=list)
    warnings:          List[str]               = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available":          bool(self.available),
            "subtitle":           self.subtitle.to_dict(),
            "camera":             self.camera.to_dict(),
            "clip":               self.clip.to_dict(),
            "market_alignment":   self.market_alignment.to_dict(),
            "quality_alignment":  self.quality_alignment.to_dict(),
            "confidence":         round(float(self.confidence), 2),
            "reasoning":          list(self.reasoning)[:5],
            "conflicts_resolved": list(self.conflicts_resolved)[:5],
            "warnings":           list(self.warnings)[:5],
        }
