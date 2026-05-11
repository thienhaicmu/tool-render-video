"""
camera_preference_safety.py — Safety validation for camera preference data. Phase 50B.

Rules:
- Never raises
- Metadata-only validation
- Deterministic
- No executable/script/render fields allowed
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.creator_camera.safety")

_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "ffmpeg_args",
    "render_command",
    "playback_speed",
    "subtitle_timing",
    "subprocess",
    "executable",
    "python_code",
    "shell",
    "powershell",
    "api_key",
    "auth_token",
    "queue_priority",
    "output_path",
    "rerender",
    "delete_output",
    "crop_coordinates",
    "crop_x", "crop_y", "crop_w", "crop_h",
    "ffmpeg_filter",
    "zoom_curve_points",
    "direct_transform",
})


def sanitize_camera_preference_data(data: dict) -> dict:
    """Strip forbidden keys from camera preference data. Never raises."""
    if not isinstance(data, dict):
        return {}
    try:
        result = {}
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                logger.debug("camera_preference_safety_stripped key=%s", key)
                continue
            if isinstance(value, dict):
                result[key] = sanitize_camera_preference_data(value)
            else:
                result[key] = value
        return result
    except Exception as exc:
        logger.debug("camera_preference_safety_error: %s", exc)
        return {}


def is_camera_preference_safe(data: dict) -> bool:
    """Return True if data contains no forbidden keys (recursively). Never raises."""
    if not isinstance(data, dict):
        return True
    try:
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                return False
            if isinstance(value, dict) and not is_camera_preference_safe(value):
                return False
        return True
    except Exception:
        return False
