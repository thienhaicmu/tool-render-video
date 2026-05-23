"""
validators.py — AI execution hints validation layer for Phase 5.3.

Validates and clamps raw AI hint dicts into safe RenderExecutionHints.
Never raises — always returns AIValidationResult.

Public API:
    validate_execution_hints(raw_hints: dict) -> AIValidationResult
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.contracts import AIValidationResult, RenderExecutionHints

logger = logging.getLogger(__name__)

# ── Validation constants ──────────────────────────────────────────────────────

_SPEED_MIN: float = 0.5
_SPEED_MAX: float = 1.5

_CUT_MIN: float = 1.0
_CUT_MAX: float = 12.0

_SUBTITLE_STYLES = frozenset({"subtle", "medium", "strong", "word_only"})
_VISUAL_INTENSITIES = frozenset({"low", "medium", "high"})


# ── Public API ────────────────────────────────────────────────────────────────

def validate_execution_hints(raw_hints: dict) -> AIValidationResult:
    """Validate and clamp a raw execution hints dict.

    Rules (NEVER raise — always return AIValidationResult):
    1. playback_speed_hint: clamp to [0.5, 1.5]; non-numeric → None
    2. cut_interval_min: float in [1.0, 12.0]; invalid → None
    3. cut_interval_max: float in [1.0, 12.0]; invalid → None;
       if min > max → swap; add fixup
    4. subtitle_emphasis_style: allowed "subtle"/"medium"/"strong"/"word_only"; unknown → None
    5. hook_overlay_enabled: must be bool; invalid → None
    6. visual_intensity: allowed "low"/"medium"/"high"; unknown → None
    7. source_knowledge_ids / validation_notes: pass through as-is
    """
    fixups: list[dict] = []
    warnings: list[str] = []

    try:
        raw = dict(raw_hints) if raw_hints else {}
    except Exception:
        raw = {}
        warnings.append("raw_hints was not a dict — using empty defaults")

    # ── 1. playback_speed_hint ────────────────────────────────────────────────
    speed = _parse_float(raw.get("playback_speed_hint"))
    if speed is None and raw.get("playback_speed_hint") is not None:
        fixups.append({
            "field": "playback_speed_hint",
            "original": raw.get("playback_speed_hint"),
            "action": "non_numeric_cleared",
            "result": None,
        })
    elif speed is not None:
        clamped = _clamp(speed, _SPEED_MIN, _SPEED_MAX)
        if clamped != speed:
            fixups.append({
                "field": "playback_speed_hint",
                "original": speed,
                "action": "clamped",
                "result": clamped,
            })
        speed = clamped

    # ── 2. cut_interval_min ───────────────────────────────────────────────────
    cut_min = _parse_float(raw.get("cut_interval_min"))
    if cut_min is None and raw.get("cut_interval_min") is not None:
        fixups.append({
            "field": "cut_interval_min",
            "original": raw.get("cut_interval_min"),
            "action": "invalid_cleared",
            "result": None,
        })
    elif cut_min is not None:
        clamped_min = _clamp(cut_min, _CUT_MIN, _CUT_MAX)
        if clamped_min != cut_min:
            fixups.append({
                "field": "cut_interval_min",
                "original": cut_min,
                "action": "clamped",
                "result": clamped_min,
            })
        cut_min = clamped_min

    # ── 3. cut_interval_max ───────────────────────────────────────────────────
    cut_max = _parse_float(raw.get("cut_interval_max"))
    if cut_max is None and raw.get("cut_interval_max") is not None:
        fixups.append({
            "field": "cut_interval_max",
            "original": raw.get("cut_interval_max"),
            "action": "invalid_cleared",
            "result": None,
        })
    elif cut_max is not None:
        clamped_max = _clamp(cut_max, _CUT_MIN, _CUT_MAX)
        if clamped_max != cut_max:
            fixups.append({
                "field": "cut_interval_max",
                "original": cut_max,
                "action": "clamped",
                "result": clamped_max,
            })
        cut_max = clamped_max

    # If both are valid and min > max → swap
    if cut_min is not None and cut_max is not None and cut_min > cut_max:
        fixups.append({
            "field": "cut_interval_min/max",
            "original": {"min": cut_min, "max": cut_max},
            "action": "swapped_inverted_range",
            "result": {"min": cut_max, "max": cut_min},
        })
        cut_min, cut_max = cut_max, cut_min

    # ── 4. subtitle_emphasis_style ────────────────────────────────────────────
    sub_style = _parse_str(raw.get("subtitle_emphasis_style"))
    if sub_style is not None and sub_style not in _SUBTITLE_STYLES:
        fixups.append({
            "field": "subtitle_emphasis_style",
            "original": sub_style,
            "action": "unknown_style_cleared",
            "result": None,
        })
        sub_style = None

    # ── 5. hook_overlay_enabled ───────────────────────────────────────────────
    hook_raw = raw.get("hook_overlay_enabled")
    hook_enabled = _parse_bool(hook_raw)
    if hook_enabled is None and hook_raw is not None:
        fixups.append({
            "field": "hook_overlay_enabled",
            "original": hook_raw,
            "action": "non_bool_cleared",
            "result": None,
        })

    # ── 6. visual_intensity ───────────────────────────────────────────────────
    vis_raw = _parse_str(raw.get("visual_intensity"))
    vis_intensity = vis_raw if vis_raw in _VISUAL_INTENSITIES else None
    if vis_raw is not None and vis_raw not in _VISUAL_INTENSITIES:
        fixups.append({
            "field": "visual_intensity",
            "original": vis_raw,
            "action": "unknown_intensity_cleared",
            "result": None,
        })

    # ── 7. pass-through fields ────────────────────────────────────────────────
    source_ids = _parse_str_list(raw.get("source_knowledge_ids"))
    val_notes = _parse_str_list(raw.get("validation_notes"))

    hints = RenderExecutionHints(
        cut_interval_min=cut_min,
        cut_interval_max=cut_max,
        playback_speed_hint=speed,
        subtitle_emphasis_style=sub_style,
        hook_overlay_enabled=hook_enabled,
        visual_intensity=vis_intensity,
        source_knowledge_ids=source_ids,
        validation_notes=val_notes,
    )

    return AIValidationResult(ok=True, hints=hints, fixups=fixups, warnings=warnings)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_float(value: Any) -> float | None:
    """Return float or None. Never raises."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is a subclass of int — treat as non-numeric
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to [lo, hi]."""
    return max(lo, min(hi, value))


def _parse_str(value: Any) -> str | None:
    """Return stripped non-empty str or None."""
    if value is None:
        return None
    try:
        s = str(value).strip()
        return s if s else None
    except Exception:
        return None


def _parse_bool(value: Any) -> bool | None:
    """Return bool or None. Strict: only accepts actual bool values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    # Reject int, str, etc. — strict bool only
    return None


def _parse_str_list(value: Any) -> list[str]:
    """Return list of strings or empty list. Never raises."""
    if value is None:
        return []
    if isinstance(value, list):
        try:
            return [str(v) for v in value if v is not None]
        except Exception:
            return []
    return []
