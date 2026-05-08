"""
multivariant_safety.py — Safety gates for multi-variant render planning.

Phase 28: extends Phase 27 forbidden set with queue_priority and job_id.
Never mutates originals. Never raises.
"""
from __future__ import annotations

from typing import Any

_ALLOWED_KEYS = frozenset({
    "subtitle_density",
    "subtitle_emphasis",
    "camera_behavior",
    "pacing_style",
    "creator_style",
    "visual_rhythm_mode",
    "ai_mode",
})

_FORBIDDEN_KEYS = frozenset({
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
    # Phase 28 additions
    "queue_priority",
    "job_id",
})


def sanitize_variant_payload_overrides(overrides: Any) -> dict:
    """Strip forbidden + unknown keys. Returns a clean dict. Never raises."""
    if not isinstance(overrides, dict):
        return {}
    result = {}
    for k, v in overrides.items():
        if k in _FORBIDDEN_KEYS:
            continue
        if k not in _ALLOWED_KEYS:
            continue
        if v is None:
            continue
        result[k] = v
    return result


def is_multivariant_plan_safe(overrides: Any) -> bool:
    """Return False if any forbidden key is present. Never raises."""
    if not isinstance(overrides, dict):
        return True
    return not any(k in _FORBIDDEN_KEYS for k in overrides)


def collect_blocked_fields(overrides: Any) -> list:
    """Return list of forbidden keys found in overrides. Never raises."""
    if not isinstance(overrides, dict):
        return []
    return [k for k in overrides if k in _FORBIDDEN_KEYS]
