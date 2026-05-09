"""
style_adapter.py — Advisory creator style adaptation hints. Phase 23.

Maps a detected creator style into compact, advisory metadata hints for
subtitle density, pacing, camera, hook density, visual rhythm, and presets.

Advisory only. Never mutates render payload. Never triggers rendering.
Deterministic. Never raises.

Public API:
    build_style_adaptation(style_profile, edit_plan=None, context=None) -> dict
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.styles.adapter")

# ── Per-style advisory adaptation hints ──────────────────────────────────────
# All values are metadata strings — never applied directly to render pipeline.
_STYLE_ADAPTATION_HINTS: dict[str, dict] = {
    "viral_tiktok": {
        "subtitle_density": "high",
        "subtitle_style": "punch",
        "pacing_hint": "fast",
        "camera_hint": "fast_follow",
        "hook_density_hint": "high",
        "visual_rhythm_hint": "beat_synced",
        "preset_hint": "viral_short",
    },
    "cinematic": {
        "subtitle_density": "low",
        "subtitle_style": "minimal",
        "pacing_hint": "slow_build",
        "camera_hint": "slow_reveal",
        "hook_density_hint": "low",
        "visual_rhythm_hint": "smooth_cuts",
        "preset_hint": "cinematic_wide",
    },
    "educational": {
        "subtitle_density": "high",
        "subtitle_style": "bold",
        "pacing_hint": "medium",
        "camera_hint": "static",
        "hook_density_hint": "medium",
        "visual_rhythm_hint": "steady",
        "preset_hint": "educational_clear",
    },
    "podcast": {
        "subtitle_density": "medium",
        "subtitle_style": "clean",
        "pacing_hint": "medium",
        "camera_hint": "static",
        "hook_density_hint": "low",
        "visual_rhythm_hint": "steady",
        "preset_hint": "podcast_clean",
    },
    "product_demo": {
        "subtitle_density": "medium",
        "subtitle_style": "overlay",
        "pacing_hint": "medium",
        "camera_hint": "static",
        "hook_density_hint": "medium",
        "visual_rhythm_hint": "steady",
        "preset_hint": "product_demo",
    },
    "storytelling": {
        "subtitle_density": "low",
        "subtitle_style": "minimal",
        "pacing_hint": "slow_build",
        "camera_hint": "pan",
        "hook_density_hint": "medium",
        "visual_rhythm_hint": "smooth_cuts",
        "preset_hint": "storytelling_cinematic",
    },
    "commentary": {
        "subtitle_density": "high",
        "subtitle_style": "bold",
        "pacing_hint": "fast",
        "camera_hint": "reaction",
        "hook_density_hint": "high",
        "visual_rhythm_hint": "dynamic",
        "preset_hint": "commentary_punchy",
    },
    "interview": {
        "subtitle_density": "medium",
        "subtitle_style": "clean",
        "pacing_hint": "slow",
        "camera_hint": "static",
        "hook_density_hint": "low",
        "visual_rhythm_hint": "steady",
        "preset_hint": "interview_clean",
    },
    "safe_generic": {
        "subtitle_density": "medium",
        "subtitle_style": "default",
        "pacing_hint": "default",
        "camera_hint": "auto",
        "hook_density_hint": "medium",
        "visual_rhythm_hint": "default",
        "preset_hint": "auto",
    },
}

# Allowed advisory hint keys — never includes payload-mutation keys
_SAFE_HINT_KEYS: frozenset[str] = frozenset({
    "subtitle_density",
    "subtitle_style",
    "pacing_hint",
    "camera_hint",
    "hook_density_hint",
    "visual_rhythm_hint",
    "preset_hint",
})

# Blocked keys — must never appear in adaptation output
_FORBIDDEN_HINT_KEYS: frozenset[str] = frozenset({
    "playback_speed",
    "segment_start",
    "segment_end",
    "subtitle_timing",
    "ffmpeg_args",
    "codec",
    "crf",
    "bitrate",
    "output_path",
    "validation_rules",
})


def build_style_adaptation(
    style_profile: Any,
    edit_plan: Any = None,
    context: Optional[dict] = None,
) -> dict:
    """Build advisory adaptation hints for a detected creator style.

    Returns a compact dict of advisory metadata hints. Never mutates payload.
    Never raises.

    Args:
        style_profile: DetectedStyleProfile or dict with 'style_id' key.
        edit_plan:     AIEditPlan (or None) — for context-aware adjustments.
        context:       Optional extra context dict.

    Returns:
        {
            "style_id": str,
            "adaptation": {advisory hint keys},
            "confidence": float,
            "reasons": list[str],
            "warnings": list[str],
        }
    """
    try:
        return _adapt(style_profile, edit_plan, context or {})
    except Exception as exc:
        logger.debug("build_style_adaptation_failed: %s", exc)
        return _safe_fallback(str(exc))


def _adapt(style_profile: Any, edit_plan: Any, context: dict) -> dict:
    # Resolve style_id from profile
    style_id = _resolve_style_id(style_profile)

    # Get canonical hints, falling back to safe_generic
    raw_hints = dict(_STYLE_ADAPTATION_HINTS.get(style_id, _STYLE_ADAPTATION_HINTS["safe_generic"]))

    # Apply context adjustments (conservative)
    reasons: list[str] = []
    warnings: list[str] = []
    raw_hints, reasons = _apply_context_adjustments(style_id, raw_hints, edit_plan, reasons)

    # Safety gate — strip any forbidden keys
    adaptation = {
        k: v for k, v in raw_hints.items()
        if k in _SAFE_HINT_KEYS and k not in _FORBIDDEN_HINT_KEYS
    }

    # Resolve confidence
    confidence = 0.0
    try:
        confidence = float(getattr(style_profile, "confidence", 0.0) or 0.0)
        if not (0.0 <= confidence <= 1.0):
            confidence = min(1.0, max(0.0, confidence))
    except Exception:
        pass

    logger.info(
        "ai_creator_style_adaptation_applied style=%s confidence=%.4f hints=%d",
        style_id, confidence, len(adaptation),
    )

    return {
        "style_id": style_id,
        "adaptation": adaptation,
        "confidence": round(confidence, 4),
        "reasons": reasons[:5],
        "warnings": warnings,
    }


def _apply_context_adjustments(
    style_id: str,
    hints: dict,
    edit_plan: Any,
    reasons: list[str],
) -> tuple[dict, list[str]]:
    """Apply conservative context-aware adjustments to hint values."""
    try:
        if edit_plan is None:
            return hints, reasons

        # Retention-driven adjustment: if low retention score → increase hook density
        retention = getattr(edit_plan, "retention", {}) or {}
        if isinstance(retention, dict) and retention.get("available"):
            ret_score = float(retention.get("overall_retention_score") or 50)
            if ret_score < 55 and hints.get("hook_density_hint") == "low":
                hints = dict(hints)
                hints["hook_density_hint"] = "medium"
                reasons.append("hook_density_raised_for_low_retention")

        # Subtitle execution context: if dense subtitle execution → prefer compact
        se = getattr(edit_plan, "subtitle_execution", {}) or {}
        if isinstance(se, dict) and se.get("available"):
            density_mode = str((se.get("global_hint") or {}).get("density_mode") or "")
            if density_mode == "compact" and hints.get("subtitle_density") == "high":
                hints = dict(hints)
                hints["subtitle_density"] = "medium"
                reasons.append("subtitle_density_adjusted_for_compact_execution")

    except Exception:
        pass

    return hints, reasons


def _resolve_style_id(style_profile: Any) -> str:
    """Extract a valid Phase 23 style_id from a style_profile of any type."""
    from app.ai.styles.style_schema import VALID_P23_STYLES
    try:
        if isinstance(style_profile, dict):
            raw = str(style_profile.get("style_id") or "")
        else:
            raw = str(getattr(style_profile, "style_id", "") or "")
        return raw if raw in VALID_P23_STYLES else "safe_generic"
    except Exception:
        return "safe_generic"


def _safe_fallback(reason: str) -> dict:
    hints = dict(_STYLE_ADAPTATION_HINTS["safe_generic"])
    adaptation = {k: v for k, v in hints.items() if k in _SAFE_HINT_KEYS}
    return {
        "style_id": "safe_generic",
        "adaptation": adaptation,
        "confidence": 0.0,
        "reasons": [],
        "warnings": [f"adaptation_error:{reason}"],
    }
