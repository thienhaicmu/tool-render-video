"""
camera_apply_schema.py — Safe camera motion apply schema. Phase 34.

Dataclasses only. No Pydantic. No heavy deps. Never raises.
No direct crop-coordinate rewrite. No FFmpeg mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# ── Allowed camera guidance types ─────────────────────────────────────────────
_ALLOWED_CAMERA_TYPES: frozenset[str] = frozenset({
    "dynamic_safe",
    "subtitle_safe_framing",
    "beat_aware_pulse",
    "creator_style_camera",
    "subject_lock_preference",
    "motion_smoothing_hint",
})

# ── Forbidden camera types (NEVER applied) ────────────────────────────────────
_FORBIDDEN_CAMERA_TYPES: frozenset[str] = frozenset({
    "direct_crop_coordinate_rewrite",
    "ffmpeg_filter_rewrite",
    "arbitrary_zoom_curve",
    "unsafe_subject_jump",
    "scene_reorder_camera",
})

# ── Allowed change keys (metadata guidance only) ──────────────────────────────
_ALLOWED_CHANGE_KEYS: frozenset[str] = frozenset({
    "camera_behavior",
    "subtitle_safe_framing",
    "beat_pulse_strength",
    "creator_style_camera",
    "subject_lock_preference",
    "motion_smoothing",
    "max_camera_intensity",
    "visual_rhythm_mode",
})

# ── Forbidden change keys (NEVER written) ─────────────────────────────────────
_FORBIDDEN_CHANGE_KEYS: frozenset[str] = frozenset({
    "crop_x",
    "crop_y",
    "crop_w",
    "crop_h",
    "crop_coordinates",
    "ffmpeg_filter",
    "ffmpeg_args",
    "zoom_curve_points",
    "direct_transform",
    "playback_speed",
    "segment_start",
    "segment_end",
    "segment_order",
    "output_path",
})

# ── Safety bounds ─────────────────────────────────────────────────────────────
_MIN_CONFIDENCE: float = 0.65
_MAX_BEAT_PULSE_STRENGTH: float = 0.35
_MIN_BEAT_PULSE_STRENGTH: float = 0.0
_MAX_CAMERA_INTENSITY: float = 1.0
_MIN_CAMERA_INTENSITY: float = 0.0


@dataclass
class AICameraMotionApply:
    apply_id: str
    camera_type: str = ""
    source_candidate_id: str = ""
    confidence: float = 0.0
    applied: bool = False
    safe: bool = False
    target_scope: str = "metadata"
    changes: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        cam_type = (
            self.camera_type
            if self.camera_type in _ALLOWED_CAMERA_TYPES
            else "unknown"
        )
        # Sanitize changes in-line for serialization safety
        safe_changes: dict = {}
        for k, v in (self.changes or {}).items():
            if k in _FORBIDDEN_CHANGE_KEYS:
                continue
            if k not in _ALLOWED_CHANGE_KEYS:
                continue
            if k == "beat_pulse_strength":
                try:
                    v = max(_MIN_BEAT_PULSE_STRENGTH, min(_MAX_BEAT_PULSE_STRENGTH, float(v)))
                except Exception:
                    v = 0.0
            elif k == "max_camera_intensity":
                try:
                    v = max(_MIN_CAMERA_INTENSITY, min(_MAX_CAMERA_INTENSITY, float(v)))
                except Exception:
                    v = 0.0
            safe_changes[k] = v

        return {
            "apply_id": str(self.apply_id),
            "camera_type": cam_type,
            "source_candidate_id": str(self.source_candidate_id),
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 4),
            "applied": bool(self.applied),
            "safe": bool(self.safe),
            "target_scope": str(self.target_scope),
            "changes": safe_changes,
            "warnings": list(self.warnings)[:10],
            "explanation": list(self.explanation)[:10],
        }


@dataclass
class AICameraMotionApplyPack:
    available: bool = True
    enabled: bool = False
    mode: str = "disabled"
    applied: List[AICameraMotionApply] = field(default_factory=list)
    blocked: List[AICameraMotionApply] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "mode": str(self.mode),
            "applied": [a.to_dict() for a in self.applied[:20]],
            "blocked": [b.to_dict() for b in self.blocked[:20]],
            "warnings": list(self.warnings)[:10],
        }
