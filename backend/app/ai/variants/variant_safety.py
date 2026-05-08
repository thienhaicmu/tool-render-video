"""
variant_safety.py — Safety gates for AI variant plans. Phase 21.

Deterministic only. Never raises. No payload mutation.
"""
from __future__ import annotations

from typing import Any, Optional

from app.ai.variants.variant_schema import AIVariantPlan, VALID_RISKS

# ── Allowed suggested_changes keys ───────────────────────────────────────────
ALLOWED_CHANGE_KEYS: frozenset[str] = frozenset({
    "subtitle_density",
    "subtitle_emphasis",
    "camera_behavior",
    "pacing_style",
    "target_duration_hint",
    "creator_style",
    "ai_mode",
})

# ── Forbidden keys that must never appear in suggested_changes ────────────────
FORBIDDEN_CHANGE_KEYS: frozenset[str] = frozenset({
    "playback_speed",
    "segment_start",
    "segment_end",
    "subtitle_timing",
    "ffmpeg_args",
    "codec",
    "crf",
    "bitrate",
    "validation_rules",
    "output_path",
})


def sanitize_variant_changes(changes: dict) -> dict:
    """Strip forbidden keys from suggested_changes; keep only allowed keys.

    Never raises. Returns empty dict on any error.
    """
    try:
        return {
            k: v for k, v in changes.items()
            if k in ALLOWED_CHANGE_KEYS and k not in FORBIDDEN_CHANGE_KEYS
        }
    except Exception:
        return {}


def is_variant_safe(
    variant: AIVariantPlan,
    context: Optional[dict] = None,
) -> bool:
    """Return True only when all safety gates pass.

    Gates:
    - risk must not be "high"
    - suggested_changes must contain no forbidden keys
    - variant_id must be a non-empty string
    Never raises.
    """
    try:
        if str(variant.risk) == "high":
            return False
        changes = variant.suggested_changes or {}
        if any(k in FORBIDDEN_CHANGE_KEYS for k in changes):
            return False
        if not str(variant.variant_id).strip():
            return False
        return True
    except Exception:
        return False
