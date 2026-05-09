"""
clip_batch_safety.py — Safety validation for AI batch render plans. Phase 37.

Never raises. Forbidden override keys are stripped automatically.
No render execution, no job enqueue, no FFmpeg mutation.
"""
from __future__ import annotations

import math
from typing import Any, Optional

_ALLOWED_OVERRIDE_KEYS = frozenset({
    "subtitle_density",
    "subtitle_emphasis",
    "camera_behavior",
    "pacing_style",
    "creator_style",
    "visual_rhythm_mode",
    "ai_mode",
})

_FORBIDDEN_OVERRIDE_KEYS = frozenset({
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
    "queue_priority",
    "job_id",
})

_ALLOWED_RENDER_STRATEGIES = frozenset({
    "safe_default",
    "retention_focused",
    "creator_style_focused",
    "subtitle_clarity",
    "camera_dynamic_safe",
})

_ALLOWED_VARIANT_STRATEGIES = frozenset({
    "single_safe",
    "selected_variant",
    "multivariant_limited",
})


def sanitize_batch_payload_overrides(overrides: Any) -> dict:
    """Return a copy of overrides with all forbidden keys removed. Never raises."""
    try:
        if not isinstance(overrides, dict):
            return {}
        return {
            k: v
            for k, v in overrides.items()
            if k in _ALLOWED_OVERRIDE_KEYS
        }
    except Exception:
        return {}


def sanitize_batch_plan(plan: Any) -> dict:
    """Return a sanitised copy of a raw batch plan dict. Never raises."""
    try:
        if not isinstance(plan, dict):
            return {}
        out = dict(plan)

        try:
            out["start_sec"] = max(0.0, float(out.get("start_sec", 0.0)))
        except Exception:
            out["start_sec"] = 0.0

        try:
            out["end_sec"] = max(0.0, float(out.get("end_sec", 0.0)))
        except Exception:
            out["end_sec"] = 0.0

        try:
            raw_dur = float(out.get("duration_sec", 0.0))
            out["duration_sec"] = max(0.0, raw_dur)
        except Exception:
            out["duration_sec"] = 0.0

        try:
            out["score"] = max(0.0, min(100.0, float(out.get("score", 0.0))))
        except Exception:
            out["score"] = 0.0

        try:
            out["rank"] = max(0, int(out.get("rank", 0)))
        except Exception:
            out["rank"] = 0

        render_strategy = str(out.get("render_strategy", "safe_default"))
        if render_strategy not in _ALLOWED_RENDER_STRATEGIES:
            render_strategy = "safe_default"
        out["render_strategy"] = render_strategy

        variant_strategy = str(out.get("variant_strategy", "single_safe"))
        if variant_strategy not in _ALLOWED_VARIANT_STRATEGIES:
            variant_strategy = "single_safe"
        out["variant_strategy"] = variant_strategy

        out["planned_payload_overrides"] = sanitize_batch_payload_overrides(
            out.get("planned_payload_overrides", {})
        )

        out["warnings"] = list(out.get("warnings") or [])
        out["explanation"] = list(out.get("explanation") or [])
        out["safe"] = bool(out.get("safe", False))

        return out
    except Exception:
        return {}


def is_batch_plan_safe(plan: Any, context: Optional[dict] = None) -> bool:
    """Return True iff the batch plan passes all safety checks. Never raises.

    Raw timing is validated BEFORE sanitizing to prevent clamp-masking bad values.
    """
    try:
        if not isinstance(plan, dict):
            return False

        raw_start = plan.get("start_sec", 0.0)
        raw_end = plan.get("end_sec", 0.0)
        try:
            raw_start = float(raw_start)
            raw_end = float(raw_end)
        except Exception:
            return False

        if not (math.isfinite(raw_start) and math.isfinite(raw_end)):
            return False
        if raw_start < 0.0 or raw_end < 0.0:
            return False
        if raw_end <= raw_start:
            return False

        # Check raw overrides for forbidden keys BEFORE sanitizing strips them.
        raw_overrides = plan.get("planned_payload_overrides", {})
        if isinstance(raw_overrides, dict):
            for k in raw_overrides:
                if k in _FORBIDDEN_OVERRIDE_KEYS:
                    return False

        sanitized = sanitize_batch_plan(plan)
        if not sanitized:
            return False

        duration = sanitized.get("duration_sec", 0.0)
        if duration <= 0.0:
            return False

        if sanitized.get("render_strategy") not in _ALLOWED_RENDER_STRATEGIES:
            return False
        if sanitized.get("variant_strategy") not in _ALLOWED_VARIANT_STRATEGIES:
            return False

        return True
    except Exception:
        return False
