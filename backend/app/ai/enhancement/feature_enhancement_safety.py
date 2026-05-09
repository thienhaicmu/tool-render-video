"""
feature_enhancement_safety.py — Safety validation for AI feature enhancements. Phase 38.

Never raises. Forbidden execution fields stripped automatically.
Assistive-only: no FFmpeg mutation, no playback_speed, no render execution.
"""
from __future__ import annotations

from typing import Any, Optional

_FORBIDDEN_KEYS = frozenset({
    "ffmpeg_args",
    "render_command",
    "playback_speed",
    "subtitle_timing",
    "output_path",
    "queue_priority",
    "job_id",
    "segment_order",
    "direct_crop_coordinates",
})

_ALLOWED_ENHANCEMENT_LEVELS = frozenset({
    "safe",
    "moderate",
    "enhanced",
})


def sanitize_feature_enhancement(data: Any) -> dict:
    """Return a sanitised copy of a raw feature enhancement dict. Never raises."""
    try:
        if not isinstance(data, dict):
            return {}
        out = dict(data)
        for key in _FORBIDDEN_KEYS:
            out.pop(key, None)

        try:
            out["confidence"] = max(0.0, min(1.0, float(out.get("confidence", 0.0))))
        except Exception:
            out["confidence"] = 0.0

        level = str(out.get("enhancement_level", "safe"))
        if level not in _ALLOWED_ENHANCEMENT_LEVELS:
            out["enhancement_level"] = "safe"

        out["improvements"] = list(out.get("improvements") or [])
        out["warnings"] = list(out.get("warnings") or [])
        out["explanation"] = list(out.get("explanation") or [])
        out["enabled"] = bool(out.get("enabled", False))

        return out
    except Exception:
        return {}


def is_feature_enhancement_safe(data: Any, context: Optional[dict] = None) -> bool:
    """Return True iff the feature enhancement dict passes all safety checks. Never raises."""
    try:
        if not isinstance(data, dict):
            return False
        for key in _FORBIDDEN_KEYS:
            if key in data:
                return False
        level = str(data.get("enhancement_level", "safe"))
        if level not in _ALLOWED_ENHANCEMENT_LEVELS:
            return False
        try:
            confidence = float(data.get("confidence", 0.0))
            if not (0.0 <= confidence <= 1.0):
                return False
        except Exception:
            return False
        return True
    except Exception:
        return False
