"""
pattern_safety.py — Safety validation for creator patterns. Phase 40.

Never raises. Forbidden execution fields stripped automatically.
No FFmpeg, no subprocess, no remote execution, no model training.
"""
from __future__ import annotations

from typing import Any

_FORBIDDEN_KEYS = frozenset({
    "ffmpeg_args",
    "render_command",
    "shell",
    "powershell",
    "subprocess",
    "executable",
    "python_code",
    "api_key",
    "auth_token",
    "remote_script",
    "playback_speed",
    "subtitle_timing",
})

_ALLOWED_PATTERN_TYPES = frozenset({
    "hook",
    "subtitle",
    "pacing",
    "camera",
    "retention",
    "creator",
})

_MAX_STRING_LEN = 1000
_MAX_LIST_LEN = 50
_MAX_DICT_KEYS = 30


def sanitize_pattern(data: Any) -> dict:
    """Return a sanitised copy of a raw pattern dict. Never raises."""
    try:
        if not isinstance(data, dict):
            return {}
        out: dict = {}
        for k, v in data.items():
            if k in _FORBIDDEN_KEYS:
                continue
            if isinstance(v, str):
                out[k] = v[:_MAX_STRING_LEN]
            elif isinstance(v, list):
                out[k] = [
                    (i[:_MAX_STRING_LEN] if isinstance(i, str) else i)
                    for i in v[:_MAX_LIST_LEN]
                    if isinstance(i, (str, int, float, bool))
                ]
            elif isinstance(v, dict):
                out[k] = {
                    kk: (vv[:_MAX_STRING_LEN] if isinstance(vv, str) else vv)
                    for kk, vv in list(v.items())[:_MAX_DICT_KEYS]
                    if kk not in _FORBIDDEN_KEYS
                    and isinstance(vv, (str, int, float, bool))
                }
            elif isinstance(v, (int, float, bool)) and not isinstance(v, complex):
                out[k] = v

        try:
            out["confidence"] = max(0.0, min(1.0, float(out.get("confidence", 0.0))))
        except Exception:
            out["confidence"] = 0.0

        pattern_type = str(out.get("pattern_type", ""))
        if pattern_type not in _ALLOWED_PATTERN_TYPES:
            out["pattern_type"] = ""

        out.setdefault("tags", [])
        out.setdefault("hook_patterns", [])
        out.setdefault("subtitle_patterns", {})
        out.setdefault("pacing_patterns", {})
        out.setdefault("camera_patterns", {})
        out.setdefault("retention_patterns", {})
        out.setdefault("warnings", [])
        out.setdefault("explanation", [])
        out.setdefault("safe", False)

        return out
    except Exception:
        return {}


def is_pattern_safe(data: Any) -> bool:
    """Return True iff the pattern passes all safety checks. Never raises."""
    try:
        if not isinstance(data, dict):
            return False
        for key in _FORBIDDEN_KEYS:
            if key in data:
                return False
        pattern_id = data.get("pattern_id", "")
        if not pattern_id or not isinstance(pattern_id, str):
            return False
        try:
            conf = float(data.get("confidence", 0.0))
            if not (0.0 <= conf <= 1.0):
                return False
        except Exception:
            return False
        return True
    except Exception:
        return False
