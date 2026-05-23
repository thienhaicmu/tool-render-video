"""
test_ai_validators.py — Tests for validate_execution_hints().

Verifies all clamping, invalid-value clearing, and fixup recording rules.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate(raw: dict):
    from app.ai.validators import validate_execution_hints
    return validate_execution_hints(raw)


def _fixup_fields(result) -> list[str]:
    return [f["field"] for f in result.fixups]


# ---------------------------------------------------------------------------
# 1. playback_speed_hint
# ---------------------------------------------------------------------------

def test_speed_clamped_high():
    r = _validate({"playback_speed_hint": 3.0})
    assert r.ok is True
    assert r.hints.playback_speed_hint == 1.5
    assert "playback_speed_hint" in _fixup_fields(r)
    fixup = next(f for f in r.fixups if f["field"] == "playback_speed_hint")
    assert fixup["original"] == 3.0
    assert fixup["result"] == 1.5


def test_speed_clamped_low():
    r = _validate({"playback_speed_hint": 0.1})
    assert r.hints.playback_speed_hint == 0.5
    assert "playback_speed_hint" in _fixup_fields(r)
    fixup = next(f for f in r.fixups if f["field"] == "playback_speed_hint")
    assert fixup["original"] == 0.1
    assert fixup["result"] == 0.5


def test_speed_valid_passes():
    r = _validate({"playback_speed_hint": 1.2})
    assert r.hints.playback_speed_hint == 1.2
    assert not any(f["field"] == "playback_speed_hint" for f in r.fixups)


def test_speed_at_boundary_min():
    r = _validate({"playback_speed_hint": 0.5})
    assert r.hints.playback_speed_hint == 0.5
    assert not any(f["field"] == "playback_speed_hint" for f in r.fixups)


def test_speed_at_boundary_max():
    r = _validate({"playback_speed_hint": 1.5})
    assert r.hints.playback_speed_hint == 1.5


def test_speed_invalid_string():
    r = _validate({"playback_speed_hint": "fast"})
    assert r.hints.playback_speed_hint is None
    assert "playback_speed_hint" in _fixup_fields(r)


def test_speed_invalid_none():
    r = _validate({"playback_speed_hint": None})
    assert r.hints.playback_speed_hint is None
    # None means "not provided" — no fixup needed
    assert not any(f["field"] == "playback_speed_hint" for f in r.fixups)


def test_speed_invalid_bool():
    """Bool is not a valid float — should be cleared."""
    r = _validate({"playback_speed_hint": True})
    assert r.hints.playback_speed_hint is None


# ---------------------------------------------------------------------------
# 2 & 3. cut_interval_min / cut_interval_max
# ---------------------------------------------------------------------------

def test_cut_interval_valid():
    r = _validate({"cut_interval_min": 3.0, "cut_interval_max": 6.0})
    assert r.hints.cut_interval_min == 3.0
    assert r.hints.cut_interval_max == 6.0
    assert not _fixup_fields(r)


def test_cut_interval_reversed_swapped():
    """min > max → swap."""
    r = _validate({"cut_interval_min": 8.0, "cut_interval_max": 3.0})
    assert r.hints.cut_interval_min == 3.0
    assert r.hints.cut_interval_max == 8.0
    assert any("min/max" in f["field"] or "swapped" in f["action"] for f in r.fixups)


def test_cut_interval_invalid_min():
    r = _validate({"cut_interval_min": "fast"})
    assert r.hints.cut_interval_min is None
    assert "cut_interval_min" in _fixup_fields(r)


def test_cut_interval_invalid_max():
    r = _validate({"cut_interval_max": "slow"})
    assert r.hints.cut_interval_max is None
    assert "cut_interval_max" in _fixup_fields(r)


def test_cut_interval_clamped_below_min():
    r = _validate({"cut_interval_min": 0.0, "cut_interval_max": 0.5})
    # Both get clamped to 1.0 → then min==max → no swap needed
    assert r.hints.cut_interval_min == 1.0
    assert r.hints.cut_interval_max == 1.0


def test_cut_interval_clamped_above_max():
    r = _validate({"cut_interval_min": 15.0, "cut_interval_max": 20.0})
    assert r.hints.cut_interval_min == 12.0
    assert r.hints.cut_interval_max == 12.0


def test_cut_interval_only_min():
    r = _validate({"cut_interval_min": 4.0})
    assert r.hints.cut_interval_min == 4.0
    assert r.hints.cut_interval_max is None


def test_cut_interval_only_max():
    r = _validate({"cut_interval_max": 7.0})
    assert r.hints.cut_interval_min is None
    assert r.hints.cut_interval_max == 7.0


# ---------------------------------------------------------------------------
# 4. subtitle_emphasis_style
# ---------------------------------------------------------------------------

def test_subtitle_style_valid_subtle():
    r = _validate({"subtitle_emphasis_style": "subtle"})
    assert r.hints.subtitle_emphasis_style == "subtle"
    assert not any(f["field"] == "subtitle_emphasis_style" for f in r.fixups)


def test_subtitle_style_valid_medium():
    r = _validate({"subtitle_emphasis_style": "medium"})
    assert r.hints.subtitle_emphasis_style == "medium"


def test_subtitle_style_valid_strong():
    r = _validate({"subtitle_emphasis_style": "strong"})
    assert r.hints.subtitle_emphasis_style == "strong"


def test_subtitle_style_valid_word_only():
    r = _validate({"subtitle_emphasis_style": "word_only"})
    assert r.hints.subtitle_emphasis_style == "word_only"


def test_subtitle_style_invalid_cleared():
    r = _validate({"subtitle_emphasis_style": "aggressive"})
    assert r.hints.subtitle_emphasis_style is None
    assert "subtitle_emphasis_style" in _fixup_fields(r)


def test_subtitle_style_unknown_cleared():
    r = _validate({"subtitle_emphasis_style": "bouncy"})
    assert r.hints.subtitle_emphasis_style is None


def test_subtitle_style_none_safe():
    r = _validate({"subtitle_emphasis_style": None})
    assert r.hints.subtitle_emphasis_style is None


# ---------------------------------------------------------------------------
# 5. hook_overlay_enabled
# ---------------------------------------------------------------------------

def test_hook_bool_true_passes():
    r = _validate({"hook_overlay_enabled": True})
    assert r.hints.hook_overlay_enabled is True
    assert not any(f["field"] == "hook_overlay_enabled" for f in r.fixups)


def test_hook_bool_false_passes():
    r = _validate({"hook_overlay_enabled": False})
    assert r.hints.hook_overlay_enabled is False


def test_hook_invalid_int_cleared():
    r = _validate({"hook_overlay_enabled": 1})
    assert r.hints.hook_overlay_enabled is None
    assert "hook_overlay_enabled" in _fixup_fields(r)


def test_hook_invalid_string_cleared():
    r = _validate({"hook_overlay_enabled": "yes"})
    assert r.hints.hook_overlay_enabled is None


def test_hook_none_safe():
    r = _validate({"hook_overlay_enabled": None})
    assert r.hints.hook_overlay_enabled is None


# ---------------------------------------------------------------------------
# 6. visual_intensity
# ---------------------------------------------------------------------------

def test_visual_intensity_valid_low():
    r = _validate({"visual_intensity": "low"})
    assert r.hints.visual_intensity == "low"


def test_visual_intensity_valid_medium():
    r = _validate({"visual_intensity": "medium"})
    assert r.hints.visual_intensity == "medium"


def test_visual_intensity_valid_high():
    r = _validate({"visual_intensity": "high"})
    assert r.hints.visual_intensity == "high"


def test_visual_intensity_invalid_cleared():
    r = _validate({"visual_intensity": "extreme"})
    assert r.hints.visual_intensity is None
    assert "visual_intensity" in _fixup_fields(r)


# ---------------------------------------------------------------------------
# 7. Pass-through: source_knowledge_ids, validation_notes
# ---------------------------------------------------------------------------

def test_source_knowledge_ids_pass_through():
    ids = ["item_a", "item_b"]
    r = _validate({"source_knowledge_ids": ids})
    assert r.hints.source_knowledge_ids == ids


def test_validation_notes_pass_through():
    notes = ["note_1", "note_2"]
    r = _validate({"validation_notes": notes})
    assert r.hints.validation_notes == notes


# ---------------------------------------------------------------------------
# 8. Garbage input — never raises
# ---------------------------------------------------------------------------

def test_garbage_input_dict_safe():
    r = _validate({
        "playback_speed_hint": [1, 2, 3],
        "cut_interval_min": {"nested": True},
        "subtitle_emphasis_style": 42,
        "hook_overlay_enabled": "maybe",
        "visual_intensity": None,
        "source_knowledge_ids": "not_a_list",
        "validation_notes": 999,
    })
    assert r.ok is True
    assert r.hints is not None


def test_empty_dict_safe():
    r = _validate({})
    assert r.ok is True
    assert r.hints.playback_speed_hint is None
    assert r.hints.cut_interval_min is None


def test_none_input_safe():
    from app.ai.validators import validate_execution_hints
    r = validate_execution_hints(None)
    assert r.ok is True
