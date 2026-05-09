"""
retrieval_safety.py — Creator intelligence retrieval safety validation. Phase 41.

Validates and sanitizes retrieval match data.
Never raises. Metadata-only. No render execution.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai.retrieval.retrieval_safety")

_FORBIDDEN_MATCH_KEYS = frozenset({
    "ffmpeg_args",
    "render_command",
    "playback_speed",
    "subtitle_timing",
    "queue_priority",
    "output_path",
    "subprocess",
    "executable",
    "python_code",
    "shell",
    "powershell",
    "direct_crop_coordinates",
})

_VALID_PATTERN_TYPES = frozenset({
    "hook", "subtitle", "pacing", "camera", "retention", "creator",
})

_MAX_CONFIDENCE = 1.0
_MIN_CONFIDENCE = 0.0
_MAX_RETRIEVAL_SCORE = 100.0
_MIN_RETRIEVAL_SCORE = 0.0


def sanitize_retrieval_match(data: Any) -> dict:
    """Strip forbidden keys, clamp numeric values, return safe dict. Never raises."""
    try:
        if not isinstance(data, dict):
            return {}
        result = {k: v for k, v in data.items() if k not in _FORBIDDEN_MATCH_KEYS}

        # Clamp confidence
        if "confidence" in result:
            try:
                result["confidence"] = max(
                    _MIN_CONFIDENCE, min(_MAX_CONFIDENCE, float(result["confidence"]))
                )
            except (TypeError, ValueError):
                result["confidence"] = 0.0

        # Clamp retrieval_score
        if "retrieval_score" in result:
            try:
                result["retrieval_score"] = max(
                    _MIN_RETRIEVAL_SCORE,
                    min(_MAX_RETRIEVAL_SCORE, float(result["retrieval_score"])),
                )
            except (TypeError, ValueError):
                result["retrieval_score"] = 0.0

        # Validate pattern_type
        if "pattern_type" in result:
            if result["pattern_type"] not in _VALID_PATTERN_TYPES:
                result["pattern_type"] = ""

        # Sanitize nested influence dicts
        for influence_key in (
            "subtitle_influence", "pacing_influence", "camera_influence",
            "retention_influence", "hook_influence",
        ):
            if influence_key in result:
                influence = result[influence_key]
                if isinstance(influence, dict):
                    result[influence_key] = {
                        k: v for k, v in influence.items()
                        if k not in _FORBIDDEN_MATCH_KEYS
                    }
                else:
                    result[influence_key] = {}

        return result

    except Exception as exc:
        logger.debug("sanitize_retrieval_match_error: %s", exc)
        return {}


def is_retrieval_match_safe(data: Any) -> bool:
    """Validate a retrieval match dict. Returns False on any safety violation. Never raises."""
    try:
        if not isinstance(data, dict):
            return False

        # Check top-level forbidden keys (raw — before sanitize strips them)
        for k in data:
            if k in _FORBIDDEN_MATCH_KEYS:
                return False

        # match_id must be present and non-empty string
        match_id = data.get("match_id", "")
        if not isinstance(match_id, str) or not match_id.strip():
            return False

        # confidence must be in valid range
        confidence = data.get("confidence", 0.0)
        try:
            conf_val = float(confidence)
        except (TypeError, ValueError):
            return False
        if not (_MIN_CONFIDENCE <= conf_val <= _MAX_CONFIDENCE):
            return False

        # retrieval_score must be in valid range
        retrieval_score = data.get("retrieval_score", 0.0)
        try:
            score_val = float(retrieval_score)
        except (TypeError, ValueError):
            return False
        if not (_MIN_RETRIEVAL_SCORE <= score_val <= _MAX_RETRIEVAL_SCORE):
            return False

        # Check nested influence dicts for forbidden keys
        for influence_key in (
            "subtitle_influence", "pacing_influence", "camera_influence",
            "retention_influence", "hook_influence",
        ):
            influence = data.get(influence_key, {})
            if isinstance(influence, dict):
                for k in influence:
                    if k in _FORBIDDEN_MATCH_KEYS:
                        return False

        return True

    except Exception as exc:
        logger.debug("is_retrieval_match_safe_error: %s", exc)
        return False
