"""
camera_apply_safety.py — Safety gates for camera motion apply. Phase 34.

Deterministic only. Never raises. All validation is local/offline.
No direct crop-coordinate rewrite. No FFmpeg mutation. No playback_speed.
"""
from __future__ import annotations

from typing import Any, Optional

from app.ai.camera.camera_apply_schema import (
    _ALLOWED_CAMERA_TYPES,
    _FORBIDDEN_CAMERA_TYPES,
    _ALLOWED_CHANGE_KEYS,
    _FORBIDDEN_CHANGE_KEYS,
    _MIN_CONFIDENCE,
    _MAX_BEAT_PULSE_STRENGTH,
    _MIN_BEAT_PULSE_STRENGTH,
    _MAX_CAMERA_INTENSITY,
    _MIN_CAMERA_INTENSITY,
)


def sanitize_camera_motion_changes(changes: Any) -> dict:
    """Return a sanitized copy of camera motion changes dict. Never raises.

    - Strips all forbidden keys unconditionally
    - Retains only known allowed keys
    - Clamps beat_pulse_strength to [0.0, 0.35]
    - Clamps max_camera_intensity to [0.0, 1.0]
    """
    try:
        if not isinstance(changes, dict):
            return {}
        result: dict = {}
        for k, v in changes.items():
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
            result[k] = v
        return result
    except Exception:
        return {}


def is_camera_motion_apply_safe(candidate: Any, context: Optional[dict] = None) -> bool:
    """Return True only if all safety gates pass. Never raises.

    Gates (all must pass):
    - candidate must be a dict
    - camera_type must be in _ALLOWED_CAMERA_TYPES
    - camera_type must NOT be in _FORBIDDEN_CAMERA_TYPES
    - confidence >= _MIN_CONFIDENCE (0.65)
    - target_scope must be "metadata"
    - changes must not contain any forbidden key
    - changes must be non-empty after sanitization
    """
    try:
        if not isinstance(candidate, dict):
            return False

        cam_type = str(candidate.get("camera_type") or "")

        # Hard reject forbidden types
        if cam_type in _FORBIDDEN_CAMERA_TYPES:
            return False

        # Require known allowed type
        if cam_type not in _ALLOWED_CAMERA_TYPES:
            return False

        # Confidence gate
        confidence = float(candidate.get("confidence") or 0.0)
        if confidence < _MIN_CONFIDENCE:
            return False

        # Scope gate — metadata only, never raw crop/ffmpeg
        scope = str(candidate.get("target_scope") or "metadata").lower()
        if scope not in ("metadata", ""):
            return False

        # Hard reject if any forbidden change key present before sanitization
        raw_changes = candidate.get("changes") or {}
        if isinstance(raw_changes, dict):
            for k in raw_changes:
                if k in _FORBIDDEN_CHANGE_KEYS:
                    return False

        # Changes must survive sanitization (non-empty result)
        sanitized = sanitize_camera_motion_changes(raw_changes)
        if not sanitized:
            return False

        return True
    except Exception:
        return False
