"""
render_preset.py — RenderPreset domain dataclass.

Phase E — Smart Render Presets. Pure data object: no I/O, no DB.
`params` holds a subset of RenderRequest fields that the preset
overrides. The FE merges params into the render form before submitting.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional


# Fields that are valid inside a preset's params dict.
# Only FE-facing, user-configurable fields — no server-derived plumbing.
PRESET_ALLOWED_PARAMS: frozenset[str] = frozenset({
    "output_count",
    "target_platform",
    "target_duration",
    "video_type",
    "hook_strength",
    "add_subtitle",
    "subtitle_style",
    "llm_enabled",
    "ai_provider",
    "ai_clip_min_duration_sec",
    "ai_clip_max_duration_sec",
})


@dataclass
class RenderPreset:
    preset_id: str = ""
    name: str = ""
    description: str = ""
    channel_code: str = ""
    platform: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    is_builtin: bool = False
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "preset_id": self.preset_id,
            "name": self.name,
            "description": self.description,
            "channel_code": self.channel_code,
            "platform": self.platform,
            "params": self.params,
            "is_builtin": self.is_builtin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: dict) -> "RenderPreset":
        """Build from a sqlite3.Row dict. Never raises."""
        if not isinstance(row, dict):
            return cls()
        params: dict = {}
        raw_params = row.get("params_json") or "{}"
        try:
            parsed = json.loads(raw_params)
            if isinstance(parsed, dict):
                params = {k: v for k, v in parsed.items() if k in PRESET_ALLOWED_PARAMS}
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return cls(
            preset_id=str(row.get("preset_id") or ""),
            name=str(row.get("name") or ""),
            description=str(row.get("description") or ""),
            channel_code=str(row.get("channel_code") or ""),
            platform=str(row.get("platform") or ""),
            params=params,
            is_builtin=bool(row.get("is_builtin") or False),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
        )
