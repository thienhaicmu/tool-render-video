"""
subtitle_influence_schema.py — Creator Subtitle Safe Influence schema. Phase 50C.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Metadata-only: no subtitle engine rewrite, no ASS generation rewrite,
no subtitle timing rewrite, no segmentation rewrite, no FFmpeg mutation.
No executor override. No internet. No cloud AI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ── Allowed values ─────────────────────────────────────────────────────────────

ALLOWED_PRESET_BIAS       = frozenset({"viral_bold", "clean_pro", "boxed_caption", "none", "unknown"})
ALLOWED_DENSITY_NUDGE     = frozenset({"reduce", "none"})
ALLOWED_MOTION_STYLE_BIAS = frozenset({"clean", "bounce", "karaoke", "none", "unknown"})
ALLOWED_CONFIDENCE_TIERS  = frozenset({"low", "medium", "high"})

# ── Bounded tuning parameter ranges ───────────────────────────────────────────
# All values are conservative additive offsets. Absolute limits prevent any
# parameter from escaping safe operating range.

# Keyword emphasis delta — applied to emphasis intensity signal [0.0, 1.0]
EMPHASIS_DELTA_MIN: float  = -0.30
EMPHASIS_DELTA_MAX: float  = +0.30

# Preset bias strength — how strongly to bias toward the preferred preset
PRESET_BIAS_MIN:   float   = 0.0
PRESET_BIAS_MAX:   float   = 1.0

# Mobile readability nudge — font scale / safe-margin boost fraction
MOBILE_NUDGE_MIN:  float   = 0.0
MOBILE_NUDGE_MAX:  float   = 0.20

# Line count bias range
LINE_COUNT_BIAS_MIN: int   = -1
LINE_COUNT_BIAS_MAX: int   = +1

# Soft tier multiplier (medium confidence → scaled-down adjustments)
SOFT_TIER_MULTIPLIER: float = 0.5


@dataclass
class AISubtitleInfluencePack:
    """Phase 50C — creator-aware subtitle influence recommendations.

    All fields are bounded metadata signals.  The subtitle system may
    consume these to improve output quality; it may also ignore them.
    Nothing here executes, rewrites, or overrides the subtitle pipeline.
    """

    available: bool = False
    confidence_tier: str = "low"   # "low", "medium", "high"

    # A. Preset bias — which subtitle style preset to favour
    preset_bias: str = "unknown"         # ALLOWED_PRESET_BIAS value
    preset_bias_strength: float = 0.0   # [0.0, 1.0]

    # B. Density nudge — only reduction allowed; never forced increase
    density_nudge: str = "none"          # "reduce" | "none"

    # C. Keyword emphasis delta — signed adjustment to emphasis intensity
    emphasis_delta: float = 0.0         # [EMPHASIS_DELTA_MIN, EMPHASIS_DELTA_MAX]

    # D. Line count bias — directional preference (-1 fewer / 0 unchanged / +1 more)
    line_count_bias: int = 0             # {-1, 0, +1}

    # E. Motion style bias — subtitle animation style preference
    motion_style_bias: str = "unknown"   # ALLOWED_MOTION_STYLE_BIAS value

    # F. Mobile readability nudge — font-scale / margin-boost fraction
    mobile_readability_nudge: float = 0.0  # [MOBILE_NUDGE_MIN, MOBILE_NUDGE_MAX]

    reasoning: List[str] = field(default_factory=list)
    warnings:  List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available":                bool(self.available),
            "confidence_tier":          self.confidence_tier,
            "preset_bias":              self.preset_bias,
            "preset_bias_strength":     round(float(self.preset_bias_strength), 4),
            "density_nudge":            self.density_nudge,
            "emphasis_delta":           round(float(self.emphasis_delta), 4),
            "line_count_bias":          int(self.line_count_bias),
            "motion_style_bias":        self.motion_style_bias,
            "mobile_readability_nudge": round(float(self.mobile_readability_nudge), 4),
            "reasoning":                list(self.reasoning)[:5],
            "warnings":                 list(self.warnings)[:5],
        }
