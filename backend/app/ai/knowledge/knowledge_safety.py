"""
knowledge_safety.py — Safety validation for creator knowledge items. Phase 39.

Never raises. Forbidden execution/scraping fields stripped automatically.
Local JSON only: no internet, no subprocess, no command execution.
"""
from __future__ import annotations

from typing import Any

_FORBIDDEN_KEYS = frozenset({
    "script",
    "executable",
    "command",
    "subprocess",
    "ffmpeg_args",
    "render_command",
    "shell",
    "powershell",
    "batch_script",
    "python_code",
    "live_scrape_url",
    "auth_token",
    "api_key",
})

_MAX_STRING_LEN = 2000
_MAX_LIST_LEN = 100
_MAX_DICT_KEYS = 50

_ALLOWED_SOURCE_TYPES = frozenset({
    "local_json",
    "manual_note",
    "trend_summary",
    "style_pattern",
    "hook_pattern",
    "subtitle_pattern",
    "pacing_pattern",
    "market_pattern",
    "creator_pattern",
})


def sanitize_knowledge(data: Any) -> dict:
    """Return a sanitised copy of a raw knowledge dict. Never raises.

    Strips forbidden keys, truncates oversized strings/lists, preserves structure.
    """
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
                out[k] = _sanitize_list(v)
            elif isinstance(v, dict):
                out[k] = _sanitize_nested_dict(v)
            elif isinstance(v, (int, float, bool)) and not isinstance(v, complex):
                out[k] = v
            else:
                # Drop unknown/exotic types silently
                pass
        return out
    except Exception:
        return {}


def is_knowledge_safe(data: Any) -> bool:
    """Return True iff the knowledge item passes all safety checks. Never raises."""
    try:
        if not isinstance(data, dict):
            return False
        for key in _FORBIDDEN_KEYS:
            if key in data:
                return False
        knowledge_id = data.get("knowledge_id", "")
        if not knowledge_id or not isinstance(knowledge_id, str):
            return False
        source_type = str(data.get("source_type", "local_json"))
        if source_type not in _ALLOWED_SOURCE_TYPES:
            return False
        for field_name in ("title", "description", "category", "creator_style"):
            val = data.get(field_name, "")
            if isinstance(val, str) and len(val) > _MAX_STRING_LEN:
                return False
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            return False
        if len(tags) > _MAX_LIST_LEN:
            return False
        hook_patterns = data.get("hook_patterns", [])
        if not isinstance(hook_patterns, list):
            return False
        if len(hook_patterns) > _MAX_LIST_LEN:
            return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sanitize_list(lst: list) -> list:
    out = []
    for item in lst[:_MAX_LIST_LEN]:
        if isinstance(item, str):
            out.append(item[:_MAX_STRING_LEN])
        elif isinstance(item, (int, float, bool)) and not isinstance(item, complex):
            out.append(item)
        elif isinstance(item, dict):
            out.append(_sanitize_nested_dict(item))
        # drop other types silently
    return out


def _sanitize_nested_dict(d: dict) -> dict:
    out: dict = {}
    for k, v in list(d.items())[:_MAX_DICT_KEYS]:
        if k in _FORBIDDEN_KEYS:
            continue
        if isinstance(v, str):
            out[k] = v[:_MAX_STRING_LEN]
        elif isinstance(v, (int, float, bool)) and not isinstance(v, complex):
            out[k] = v
        elif isinstance(v, list):
            out[k] = [i[:_MAX_STRING_LEN] if isinstance(i, str) else i for i in v[:_MAX_LIST_LEN]]
        elif isinstance(v, dict):
            out[k] = {kk: vv for kk, vv in list(v.items())[:_MAX_DICT_KEYS]
                      if kk not in _FORBIDDEN_KEYS}
        # drop exotic types silently
    return out
