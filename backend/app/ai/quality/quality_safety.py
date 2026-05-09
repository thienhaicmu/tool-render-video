"""
quality_safety.py — Quality evaluation safety gates. Phase 45.

Rules:
- Never raises
- Metadata-only validation
- Clamp all scores 0–100, confidence 0–1
- No file mutation fields allowed
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.quality.safety")

_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "ffmpeg_args",
    "render_command",
    "playback_speed",
    "subtitle_timing",
    "delete_output",
    "overwrite_output",
    "rerender",
    "queue_priority",
    "output_path_mutation",
    "subprocess",
    "executable",
    "python_code",
})

_SCORE_FIELDS: frozenset[str] = frozenset({
    "overall_score",
    "pacing_quality",
    "subtitle_readability",
    "camera_smoothness",
    "hook_strength",
    "retention_quality",
    "creator_consistency",
    "market_fit",
})


def sanitize_quality_input(data: dict) -> dict:
    """Strip forbidden keys and clamp numeric score fields. Never raises."""
    if not isinstance(data, dict):
        return {}
    try:
        result = {}
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                logger.debug("quality_safety_stripped_key key=%s", key)
                continue
            if key in _SCORE_FIELDS:
                result[key] = _clamp_score(value)
            elif key == "confidence":
                result[key] = _clamp_confidence(value)
            elif isinstance(value, dict):
                result[key] = sanitize_quality_input(value)
            else:
                result[key] = value
        return result
    except Exception as exc:
        logger.debug("quality_safety_sanitize_error: %s", exc)
        return {}


def is_quality_evaluation_safe(data: dict) -> bool:
    """Return True if data contains no forbidden keys (recursively). Never raises."""
    if not isinstance(data, dict):
        return True
    try:
        for key, value in data.items():
            if str(key).lower() in _FORBIDDEN_KEYS:
                return False
            if isinstance(value, dict) and not is_quality_evaluation_safe(value):
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
