"""
execution_safety.py — Execution recommendation safety gates. Phase 25.

Sanitizes advisory recommendation settings and validates safety boundaries.

Design rules:
- Never raises.
- Forbidden keys stripped automatically.
- advisory_only always True.
- safe_to_apply set False if forbidden settings detected.

Public API:
    sanitize_execution_settings(settings: dict) -> dict
    is_execution_recommendation_safe(recommendation, context=None) -> bool
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.execution.safety")

# Allowed keys in recommended_settings
_ALLOWED_KEYS: frozenset[str] = frozenset({
    "subtitle_density",
    "subtitle_emphasis",
    "camera_behavior",
    "pacing_style",
    "creator_style",
    "visual_rhythm_mode",
    "hook_density",
    "target_duration_hint",
    "ai_mode",
})

# Keys that are never allowed — stripped and flagged
_FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "playback_speed",
    "segment_start",
    "segment_end",
    "subtitle_timing",
    "ffmpeg_args",
    "codec",
    "bitrate",
    "crf",
    "validation_rules",
    "output_path",
    "render_command",
})


def sanitize_execution_settings(settings: Any) -> dict:
    """Return a sanitized copy of settings with forbidden keys stripped.

    Only keys in _ALLOWED_KEYS are retained. Forbidden keys are dropped
    silently. Non-dict input returns empty dict. Never raises.
    """
    if not isinstance(settings, dict):
        return {}
    try:
        result = {}
        for k, v in settings.items():
            key = str(k)
            if key in _FORBIDDEN_KEYS:
                logger.debug("execution_settings_forbidden_key_stripped key=%s", key)
                continue
            if key in _ALLOWED_KEYS:
                result[key] = v
        return result
    except Exception as exc:
        logger.debug("sanitize_execution_settings_failed: %s", exc)
        return {}


def is_execution_recommendation_safe(
    recommendation: Any,
    context: Optional[dict] = None,
) -> bool:
    """Return True if the recommendation contains no forbidden settings.

    Checks recommended_settings for any forbidden key. Returns False if
    any forbidden key is present or if the recommendation is invalid.
    Never raises.
    """
    try:
        if recommendation is None:
            return False
        settings = getattr(recommendation, "recommended_settings", None)
        if not isinstance(settings, dict):
            return True
        for key in settings:
            if str(key) in _FORBIDDEN_KEYS:
                logger.debug(
                    "execution_recommendation_unsafe forbidden_key=%s", key
                )
                return False
        return True
    except Exception as exc:
        logger.debug("is_execution_recommendation_safe_failed: %s", exc)
        return False
