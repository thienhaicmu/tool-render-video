"""
subtitle_apply_safety.py — Safety gates for subtitle text optimization apply. Phase 33.

Deterministic only. Never raises. All validation is local/offline.
No subtitle timestamp rewrite. No FFmpeg. No playback_speed mutation.
"""
from __future__ import annotations

from typing import Any, Optional

from app.ai.subtitles.subtitle_apply_schema import (
    _ALLOWED_OPTIMIZATION_TYPES,
    _FORBIDDEN_OPTIMIZATION_TYPES,
    _ALLOWED_CHANGE_KEYS,
    _FORBIDDEN_CHANGE_KEYS,
    _MIN_CHARS_PER_LINE,
    _MAX_CHARS_PER_LINE,
    _MIN_CONFIDENCE,
)


def sanitize_subtitle_text_changes(changes: Any) -> dict:
    """Return a sanitized copy of subtitle text changes dict. Never raises.

    - Strips all forbidden keys unconditionally
    - Retains only known allowed keys
    - Clamps max_chars_per_line to [_MIN_CHARS_PER_LINE, _MAX_CHARS_PER_LINE]
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
            if k == "max_chars_per_line":
                try:
                    v = max(_MIN_CHARS_PER_LINE, min(_MAX_CHARS_PER_LINE, int(v)))
                except Exception:
                    v = _MAX_CHARS_PER_LINE
            result[k] = v
        return result
    except Exception:
        return {}


def is_subtitle_text_apply_safe(candidate: Any, context: Optional[dict] = None) -> bool:
    """Return True only if all safety gates pass. Never raises.

    Gates (all must pass):
    - candidate must be a dict
    - optimization_type must be in _ALLOWED_OPTIMIZATION_TYPES
    - optimization_type must NOT be in _FORBIDDEN_OPTIMIZATION_TYPES
    - confidence >= _MIN_CONFIDENCE (0.65)
    - target_scope must be "metadata" (never "file" or "ffmpeg")
    - changes dict must not contain any forbidden keys
    - changes must not be empty after sanitization
    """
    try:
        if not isinstance(candidate, dict):
            return False

        opt_type = str(candidate.get("optimization_type") or "")

        # Hard reject forbidden types
        if opt_type in _FORBIDDEN_OPTIMIZATION_TYPES:
            return False

        # Require known allowed type
        if opt_type not in _ALLOWED_OPTIMIZATION_TYPES:
            return False

        # Confidence gate
        confidence = float(candidate.get("confidence") or 0.0)
        if confidence < _MIN_CONFIDENCE:
            return False

        # Scope gate — metadata-only, never file or ffmpeg
        scope = str(candidate.get("target_scope") or "metadata").lower()
        if scope not in ("metadata", ""):
            return False

        # Hard reject if any forbidden change key is present before sanitization
        raw_changes = candidate.get("changes") or {}
        if isinstance(raw_changes, dict):
            for k in raw_changes:
                if k in _FORBIDDEN_CHANGE_KEYS:
                    return False

        # Changes must survive sanitization (non-empty result)
        sanitized = sanitize_subtitle_text_changes(raw_changes)
        if not sanitized:
            return False

        return True
    except Exception:
        return False
