"""
market_safety.py — Market profile safety validation. Phase 44.

Rules:
- Never raises
- Metadata-only validation
- Deterministic
- No executable/script fields
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.market.safety")

_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "ffmpeg_args",
    "render_command",
    "playback_speed",
    "subtitle_timing",
    "subprocess",
    "executable",
    "python_code",
    "queue_priority",
    "output_path",
})


def sanitize_market_profile(data: dict) -> dict:
    """Strip forbidden keys from market profile data recursively. Never raises."""
    if not isinstance(data, dict):
        return {}
    try:
        result = {}
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                logger.debug("market_safety_stripped_key key=%s", key)
                continue
            if isinstance(value, dict):
                result[key] = sanitize_market_profile(value)
            else:
                result[key] = value
        return result
    except Exception as exc:
        logger.debug("market_safety_sanitize_error: %s", exc)
        return {}


def is_market_profile_safe(data: dict) -> bool:
    """Return True if data contains no forbidden keys (recursively). Never raises."""
    if not isinstance(data, dict):
        return True
    try:
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                return False
            if isinstance(value, dict) and not is_market_profile_safe(value):
                return False
        return True
    except Exception:
        return False
