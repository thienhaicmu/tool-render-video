"""
feedback_safety.py — Creator feedback safety validation. Phase 43.

Rules:
- Never raises
- Metadata-only validation
- Deterministic
- Local-only persistence
- No personal/private sensitive data
- No executable/script fields
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.feedback.safety")

_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "password",
    "token",
    "api_key",
    "auth",
    "subprocess",
    "executable",
    "ffmpeg_args",
    "render_command",
    "playback_speed",
    "subtitle_timing",
    "queue_priority",
    "output_path",
})


def sanitize_feedback(data: dict) -> dict:
    """Strip forbidden keys from feedback data recursively. Never raises."""
    if not isinstance(data, dict):
        return {}
    try:
        result = {}
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                logger.debug("feedback_safety_stripped_key key=%s", key)
                continue
            if isinstance(value, dict):
                result[key] = sanitize_feedback(value)
            else:
                result[key] = value
        return result
    except Exception as exc:
        logger.debug("feedback_safety_sanitize_error: %s", exc)
        return {}


def is_feedback_safe(data: dict) -> bool:
    """Return True if data contains no forbidden keys (recursively). Never raises."""
    if not isinstance(data, dict):
        return True
    try:
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                return False
            if isinstance(value, dict) and not is_feedback_safe(value):
                return False
        return True
    except Exception:
        return False
