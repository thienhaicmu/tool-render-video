"""
camera_preference_schema.py — Creator Camera Preference Intelligence schema. Phase 50B.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Metadata-only: no motion_crop rewrite, no tracking rewrite, no FFmpeg mutation.
No executor override. No internet. No cloud AI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ── Allowed values for each dimension ─────────────────────────────────────────

ALLOWED_MOTION_STYLES        = frozenset({"static_center", "smooth_subject", "dynamic_subject", "unknown"})
ALLOWED_AGGRESSIVENESS       = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_STABILITY_PRIORITY   = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_DEADZONE             = frozenset({"narrow", "medium", "wide", "unknown"})
ALLOWED_SUBJECT_HOLD         = frozenset({"short", "medium", "long", "unknown"})
ALLOWED_SCENE_SENSITIVITY    = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_CENTER_BIAS          = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_RISK_TOLERANCE       = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_SMOOTHNESS_PRIORITY  = frozenset({"low", "medium", "high", "unknown"})

# ── Bounded tuning parameter ranges ───────────────────────────────────────────
# All deltas are conservative additive offsets applied to MotionCropConfig defaults.
# Absolute hard limits prevent any parameter from going outside safe operating range.

# dead_zone_ratio default=0.06
DEADZONE_DELTA_MIN:      float = -0.02
DEADZONE_DELTA_MAX:      float = +0.04
DEADZONE_ABS_MIN:        float = 0.02
DEADZONE_ABS_MAX:        float = 0.10

# ema_alpha (slow/normal/fast) defaults=0.08/0.18/0.25
EMA_DELTA_MIN:           float = -0.04
EMA_DELTA_MAX:           float = +0.04
EMA_SLOW_ABS_MIN:        float = 0.04
EMA_SLOW_ABS_MAX:        float = 0.12
EMA_NORMAL_ABS_MIN:      float = 0.14
EMA_NORMAL_ABS_MAX:      float = 0.22
EMA_FAST_ABS_MIN:        float = 0.21
EMA_FAST_ABS_MAX:        float = 0.29

# lost_subject_hold_frames default=45
HOLD_DELTA_MIN:          int = -5
HOLD_DELTA_MAX:          int = +8
HOLD_ABS_MIN:            int = 37
HOLD_ABS_MAX:            int = 53

# scene_cut_threshold default=30.0
SCENE_DELTA_MIN:         float = -2.0
SCENE_DELTA_MAX:         float = +3.0
SCENE_ABS_MIN:           float = 27.0
SCENE_ABS_MAX:           float = 33.0

# temporal_smooth_window default=45
SMOOTH_WINDOW_DELTA_MIN: int = -4
SMOOTH_WINDOW_DELTA_MAX: int = +6
SMOOTH_WINDOW_ABS_MIN:   int = 39
SMOOTH_WINDOW_ABS_MAX:   int = 51

# Soft tier multiplier (medium confidence → scaled-down adjustments)
SOFT_TIER_MULTIPLIER:    float = 0.5


@dataclass
class AICameraPreference:
    """Inferred creator camera preference profile. Phase 50B — metadata only."""

    motion_style:              str = "unknown"
    crop_aggressiveness:       str = "unknown"
    stability_priority:        str = "unknown"
    deadzone_preference:       str = "unknown"
    subject_hold:              str = "unknown"
    scene_sensitivity:         str = "unknown"
    center_bias:               str = "unknown"
    reframing_risk_tolerance:  str = "unknown"
    smoothness_priority:       str = "unknown"
    confidence:                float = 0.0
    signals:                   List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "motion_style":             self.motion_style,
            "crop_aggressiveness":      self.crop_aggressiveness,
            "stability_priority":       self.stability_priority,
            "deadzone_preference":      self.deadzone_preference,
            "subject_hold":             self.subject_hold,
            "scene_sensitivity":        self.scene_sensitivity,
            "center_bias":              self.center_bias,
            "reframing_risk_tolerance": self.reframing_risk_tolerance,
            "smoothness_priority":      self.smoothness_priority,
            "confidence":               round(float(self.confidence), 2),
            "signals":                  list(self.signals),
        }


@dataclass
class AICameraTuningPack:
    """Bounded parameter tuning recommendations for MotionCropConfig. Phase 50B."""

    applied:                   bool = False
    confidence_tier:           str = "low"   # "low", "medium", "high"
    deadzone_delta:            float = 0.0
    ema_alpha_delta:           float = 0.0
    hold_frames_delta:         int = 0
    scene_threshold_delta:     float = 0.0
    smooth_window_delta:       int = 0
    reasoning:                 List[str] = field(default_factory=list)
    warnings:                  List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "applied":               bool(self.applied),
            "confidence_tier":       self.confidence_tier,
            "deadzone_delta":        round(float(self.deadzone_delta), 4),
            "ema_alpha_delta":       round(float(self.ema_alpha_delta), 4),
            "hold_frames_delta":     int(self.hold_frames_delta),
            "scene_threshold_delta": round(float(self.scene_threshold_delta), 4),
            "smooth_window_delta":   int(self.smooth_window_delta),
            "reasoning":             list(self.reasoning)[:5],
            "warnings":              list(self.warnings)[:5],
        }


@dataclass
class AICameraPreferencePack:
    """Phase 50B pack attached to AIEditPlan.creator_camera_preference."""

    available:           bool = False
    inference_mode:      str = "metadata_only"
    camera_preference:   AICameraPreference = field(default_factory=AICameraPreference)
    tuning_pack:         AICameraTuningPack = field(default_factory=AICameraTuningPack)
    warnings:            List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available":         bool(self.available),
            "inference_mode":    self.inference_mode,
            "camera_preference": self.camera_preference.to_dict(),
            "tuning_pack":       self.tuning_pack.to_dict(),
            "warnings":          list(self.warnings),
        }
