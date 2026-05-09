"""
preset_safety.py — Creator preset safety validation. Phase 46.

Rules:
- Never raises
- Metadata-only validation
- Clamp all scores 0–100, confidence 0–1
- No render mutation fields allowed
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.preset_evolution.safety")

_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "ffmpeg_args",
    "render_command",
    "playback_speed",
    "subtitle_timing",
    "rerender",
    "delete_output",
    "subprocess",
    "executable",
    "python_code",
    "queue_priority",
    "output_path",
})

_SCORE_FIELDS: frozenset[str] = frozenset({
    "quality_score",
    "creator_fit_score",
    "market_fit_score",
})


def sanitize_preset(data: dict) -> dict:
    """Strip forbidden keys and clamp numeric fields. Never raises."""
    if not isinstance(data, dict):
        return {}
    try:
        result = {}
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                logger.debug("preset_safety_stripped_key key=%s", key)
                continue
            if key in _SCORE_FIELDS:
                result[key] = _clamp_score(value)
            elif key == "confidence":
                result[key] = _clamp_confidence(value)
            elif isinstance(value, dict):
                result[key] = sanitize_preset(value)
            else:
                result[key] = value
        return result
    except Exception as exc:
        logger.debug("preset_safety_sanitize_error: %s", exc)
        return {}


def is_preset_safe(data: dict) -> bool:
    """Return True if data contains no forbidden keys (recursively). Never raises."""
    if not isinstance(data, dict):
        return True
    try:
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                return False
            if isinstance(value, dict) and not is_preset_safe(value):
                return False
        return True
    except Exception:
        return False


def _clamp_score(value) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except Exception:
        return 0.0


def _clamp_confidence(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0
