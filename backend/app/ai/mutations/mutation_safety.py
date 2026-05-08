"""
mutation_safety.py — Safe render mutation safety gates. Phase 27.

Sanitizes and validates bounded AI render mutations.

Design rules:
- Never raises.
- Forbidden keys stripped automatically.
- Mutations deterministic only.
- Payload copy always used — original never mutated in-place.

Public API:
    sanitize_mutation_changes(changes: dict) -> dict
    is_mutation_safe(changes: dict) -> bool
    apply_safe_mutation(payload: dict, changes: dict) -> dict
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai.mutations.safety")

# Keys that AI mutations are allowed to set
_ALLOWED_KEYS: frozenset[str] = frozenset({
    "subtitle_density",
    "subtitle_emphasis",
    "camera_behavior",
    "pacing_style",
    "creator_style",
    "visual_rhythm_mode",
    "ai_mode",
})

# Keys that are never allowed — stripped and flagged if detected
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
    "render_segments",
    "segment_order",
})


def sanitize_mutation_changes(changes: Any) -> dict:
    """Return a sanitized copy of changes with all forbidden keys stripped.

    Only keys in _ALLOWED_KEYS are retained. Forbidden and unknown keys are
    dropped silently. None values are also dropped. Non-dict input returns
    empty dict. Never raises.
    """
    if not isinstance(changes, dict):
        return {}
    try:
        result = {}
        for k, v in changes.items():
            key = str(k)
            if key in _FORBIDDEN_KEYS:
                logger.debug("mutation_forbidden_key_stripped key=%s", key)
                continue
            if key in _ALLOWED_KEYS and v is not None:
                result[key] = v
        return result
    except Exception as exc:
        logger.debug("sanitize_mutation_changes_failed: %s", exc)
        return {}


def is_mutation_safe(changes: Any) -> bool:
    """Return True if changes contain no forbidden keys.

    Returns False if any forbidden key is present or input is invalid.
    An empty changes dict is considered safe (no-op). Never raises.
    """
    try:
        if not isinstance(changes, dict):
            return False
        for key in changes:
            if str(key) in _FORBIDDEN_KEYS:
                logger.debug("mutation_unsafe_forbidden_key=%s", key)
                return False
        return True
    except Exception as exc:
        logger.debug("is_mutation_safe_failed: %s", exc)
        return False


def apply_safe_mutation(payload: Any, changes: Any) -> dict:
    """Apply sanitized mutation changes to a copy of the payload dict.

    Creates a shallow copy of payload, then applies only allowed keys from
    changes. The original payload is never mutated. Forbidden keys in changes
    are silently ignored. Never raises.

    Args:
        payload:  Dict-like payload or object with __dict__. Never mutated.
        changes:  Dict of proposed changes. Sanitized before applying.

    Returns:
        Modified copy of the payload as a plain dict.
    """
    try:
        # Produce a plain dict copy of the payload
        if isinstance(payload, dict):
            payload_copy = dict(payload)
        elif hasattr(payload, "__dict__"):
            payload_copy = dict(vars(payload))
        else:
            payload_copy = {}

        # Apply only sanitized (allowed) changes to the copy
        safe_changes = sanitize_mutation_changes(changes)
        payload_copy.update(safe_changes)
        return payload_copy
    except Exception as exc:
        logger.debug("apply_safe_mutation_failed: %s", exc)
        # Return a clean copy without changes rather than raise
        try:
            if isinstance(payload, dict):
                return dict(payload)
            elif hasattr(payload, "__dict__"):
                return dict(vars(payload))
        except Exception:
            pass
        return {}
