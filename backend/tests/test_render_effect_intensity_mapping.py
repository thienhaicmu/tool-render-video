"""
test_render_effect_intensity_mapping.py — Phase 5.7 tests for
resolve_effect_preset_with_intensity() in ffmpeg_helpers.py.

Covers:
- None hint returns original preset unchanged
- invalid hint ("ultra") returns original unchanged
- user_effect_is_explicit=True returns original unchanged
- low/medium/high each return a known supported preset
- return value is never a FFmpeg filter string (no "vf=" / "eq=" content)
- never raises on garbage input
- mapping only returns presets known to _effect_filter()
- user explicit wins over any hint
- AI disabled (hint=None) preserves exact existing behavior
"""
from __future__ import annotations

import pytest

from app.services.render.ffmpeg_helpers import (
    resolve_effect_preset_with_intensity,
    _effect_filter,
)

# ---------------------------------------------------------------------------
# Known supported preset names (verified from _effect_filter() source)
# ---------------------------------------------------------------------------

_KNOWN_PRESETS = frozenset({
    "slay_soft_01",
    "slay_pop_01",
    "story_clean_01",
    "social_bright",
    "cinematic_soft",
    "high_contrast",
})

# ---------------------------------------------------------------------------
# Helper: verify a returned value is a known supported preset
# ---------------------------------------------------------------------------

def _is_known_preset(value):
    """Return True if value is in the known preset set."""
    return value in _KNOWN_PRESETS


def _is_ffmpeg_filter_string(value):
    """Return True if value looks like a raw FFmpeg filter string."""
    if value is None:
        return False
    s = str(value)
    # Any of these indicate a raw FFmpeg filter string was returned
    return any(x in s for x in ("eq=", "unsharp=", "hqdn3d=", "scale=", "vf=",
                                  "setpts=", "fps=", "format="))


# ---------------------------------------------------------------------------
# 1. None hint returns original preset unchanged
# ---------------------------------------------------------------------------

def test_none_hint_returns_original_preset():
    """None visual_intensity_hint → returns effect_preset unchanged."""
    result = resolve_effect_preset_with_intensity("slay_pop_01", None)
    assert result == "slay_pop_01"


def test_none_hint_with_default_preset():
    """None hint + default preset → returns slay_soft_01 unchanged."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", None)
    assert result == "slay_soft_01"


def test_none_hint_with_none_preset():
    """None hint + None preset → returns None unchanged."""
    result = resolve_effect_preset_with_intensity(None, None)
    assert result is None


# ---------------------------------------------------------------------------
# 2. Invalid hint returns original unchanged
# ---------------------------------------------------------------------------

def test_invalid_hint_ultra_returns_unchanged():
    """Invalid hint 'ultra' → returns effect_preset unchanged."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "ultra")
    assert result == "slay_soft_01"


def test_invalid_hint_empty_string():
    """Empty string hint → returns effect_preset unchanged."""
    result = resolve_effect_preset_with_intensity("story_clean_01", "")
    assert result == "story_clean_01"


def test_invalid_hint_none_string():
    """'none' string (not None) → returns original unchanged."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "none")
    assert result == "slay_soft_01"


def test_invalid_hint_numeric():
    """Numeric hint → returns original unchanged."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "42")
    assert result == "slay_soft_01"


def test_invalid_hint_too_many_levels():
    """'ultra_high' not in allowed set → returns original unchanged."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "ultra_high")
    assert result == "slay_soft_01"


# ---------------------------------------------------------------------------
# 3. user_effect_is_explicit=True returns original unchanged
# ---------------------------------------------------------------------------

def test_user_explicit_wins_over_low():
    """user_effect_is_explicit=True + 'low' hint → returns effect_preset unchanged."""
    result = resolve_effect_preset_with_intensity("slay_pop_01", "low", user_effect_is_explicit=True)
    assert result == "slay_pop_01"


def test_user_explicit_wins_over_medium():
    """user_effect_is_explicit=True + 'medium' hint → returns effect_preset unchanged."""
    result = resolve_effect_preset_with_intensity("high_contrast", "medium", user_effect_is_explicit=True)
    assert result == "high_contrast"


def test_user_explicit_wins_over_high():
    """user_effect_is_explicit=True + 'high' hint → returns effect_preset unchanged."""
    result = resolve_effect_preset_with_intensity("cinematic_soft", "high", user_effect_is_explicit=True)
    assert result == "cinematic_soft"


def test_user_explicit_false_allows_hint():
    """user_effect_is_explicit=False → hint is applied (default behavior)."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "high", user_effect_is_explicit=False)
    # Should map to slay_pop_01 (energetic high)
    assert result == "slay_pop_01"


# ---------------------------------------------------------------------------
# 4. low/medium/high each return a known supported preset
# ---------------------------------------------------------------------------

def test_low_hint_returns_known_preset():
    """'low' hint → returns a known supported preset."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "low")
    assert result is not None
    assert _is_known_preset(result), f"'low' mapped to unknown preset: {result!r}"


def test_medium_hint_returns_known_preset():
    """'medium' hint → returns a known supported preset."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "medium")
    assert result is not None
    assert _is_known_preset(result), f"'medium' mapped to unknown preset: {result!r}"


def test_high_hint_returns_known_preset():
    """'high' hint → returns a known supported preset."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "high")
    assert result is not None
    assert _is_known_preset(result), f"'high' mapped to unknown preset: {result!r}"


def test_low_maps_to_story_clean_01():
    """'low' hint maps to 'story_clean_01' (subtle processing)."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "low")
    assert result == "story_clean_01"


def test_medium_maps_to_slay_soft_01():
    """'medium' hint maps to 'slay_soft_01' (natural default)."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "medium")
    assert result == "slay_soft_01"


def test_high_maps_to_slay_pop_01():
    """'high' hint maps to 'slay_pop_01' (energetic pop)."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "high")
    assert result == "slay_pop_01"


# ---------------------------------------------------------------------------
# 5. Return value is never a FFmpeg filter string
# ---------------------------------------------------------------------------

def test_low_does_not_return_ffmpeg_filter():
    """'low' return value must not contain FFmpeg filter syntax."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "low")
    assert not _is_ffmpeg_filter_string(result), (
        f"'low' returned FFmpeg filter string: {result!r}"
    )


def test_medium_does_not_return_ffmpeg_filter():
    """'medium' return value must not contain FFmpeg filter syntax."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "medium")
    assert not _is_ffmpeg_filter_string(result), (
        f"'medium' returned FFmpeg filter string: {result!r}"
    )


def test_high_does_not_return_ffmpeg_filter():
    """'high' return value must not contain FFmpeg filter syntax."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "high")
    assert not _is_ffmpeg_filter_string(result), (
        f"'high' returned FFmpeg filter string: {result!r}"
    )


def test_all_intensities_no_vf_prefix():
    """No intensity hint returns a value starting with 'vf='."""
    for hint in ("low", "medium", "high", None, "ultra"):
        result = resolve_effect_preset_with_intensity("slay_soft_01", hint)
        if result is not None:
            assert not str(result).startswith("vf="), (
                f"hint={hint!r} returned value starts with 'vf=': {result!r}"
            )


# ---------------------------------------------------------------------------
# 6. Never raises on garbage input
# ---------------------------------------------------------------------------

def test_no_raise_none_none():
    """resolve_effect_preset_with_intensity(None, None) does not raise."""
    result = resolve_effect_preset_with_intensity(None, None)
    assert result is None


def test_no_raise_garbage_preset():
    """Garbage effect_preset does not raise."""
    result = resolve_effect_preset_with_intensity("not_a_real_preset", "high")
    # Should return mapped preset (hint applies when preset is non-default)
    assert isinstance(result, str) or result is None


def test_no_raise_garbage_hint():
    """Garbage hint (list, int, etc.) handled gracefully."""
    for bad_hint in [[], {}, 42, object(), b"bytes"]:
        try:
            result = resolve_effect_preset_with_intensity("slay_soft_01", bad_hint)
            # Should return original unchanged (invalid hint)
            assert result == "slay_soft_01" or result is None
        except Exception as exc:
            pytest.fail(f"Raised on bad_hint={bad_hint!r}: {exc}")


def test_no_raise_all_none():
    """All None parameters does not raise."""
    result = resolve_effect_preset_with_intensity(None, None, False)
    assert result is None


def test_no_raise_extreme_strings():
    """Extreme string values don't raise."""
    for s in ["", " ", "\x00", "a" * 1000, "vf=eq=scale=", "hqdn3d=1.5:1.5"]:
        result = resolve_effect_preset_with_intensity("slay_soft_01", s)
        assert result == "slay_soft_01"  # invalid hint → unchanged


# ---------------------------------------------------------------------------
# 7. Return value passes _effect_filter without error
# ---------------------------------------------------------------------------

def test_low_preset_accepted_by_effect_filter():
    """Preset returned for 'low' is accepted by _effect_filter()."""
    preset = resolve_effect_preset_with_intensity("slay_soft_01", "low")
    assert preset is not None
    filter_str = _effect_filter(preset)
    # _effect_filter returns a raw FFmpeg string (that's its job)
    assert isinstance(filter_str, str)
    assert len(filter_str) > 0


def test_medium_preset_accepted_by_effect_filter():
    """Preset returned for 'medium' is accepted by _effect_filter()."""
    preset = resolve_effect_preset_with_intensity("slay_soft_01", "medium")
    assert preset is not None
    filter_str = _effect_filter(preset)
    assert isinstance(filter_str, str)
    assert len(filter_str) > 0


def test_high_preset_accepted_by_effect_filter():
    """Preset returned for 'high' is accepted by _effect_filter()."""
    preset = resolve_effect_preset_with_intensity("slay_soft_01", "high")
    assert preset is not None
    filter_str = _effect_filter(preset)
    assert isinstance(filter_str, str)
    assert len(filter_str) > 0


# ---------------------------------------------------------------------------
# 8. Mapping table completeness — all known intensities covered
# ---------------------------------------------------------------------------

def test_all_valid_intensities_map_to_known_preset():
    """All allowed intensity values map to a known preset."""
    for hint in ("low", "medium", "high"):
        result = resolve_effect_preset_with_intensity("slay_soft_01", hint)
        assert _is_known_preset(result), (
            f"Intensity '{hint}' mapped to unknown or unsupported preset: {result!r}"
        )


def test_case_insensitive_high():
    """Uppercase 'HIGH' is normalized and maps correctly."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "HIGH")
    assert result == "slay_pop_01"


def test_case_insensitive_low():
    """Uppercase 'LOW' is normalized and maps correctly."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "LOW")
    assert result == "story_clean_01"


def test_case_insensitive_medium():
    """Mixed case 'Medium' is normalized and maps correctly."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "Medium")
    assert result == "slay_soft_01"


# ---------------------------------------------------------------------------
# 9. User explicit detection edge cases
# ---------------------------------------------------------------------------

def test_user_explicit_true_overrides_any_hint():
    """user_effect_is_explicit=True always returns original, regardless of hint."""
    original = "social_bright"
    for hint in ("low", "medium", "high", None, "ultra"):
        result = resolve_effect_preset_with_intensity(original, hint, user_effect_is_explicit=True)
        assert result == original, (
            f"user_explicit=True should return original for hint={hint!r}, got {result!r}"
        )


def test_user_explicit_false_default_preset_allows_high():
    """user_explicit=False with default preset allows 'high' to map."""
    result = resolve_effect_preset_with_intensity("slay_soft_01", "high", user_effect_is_explicit=False)
    assert result == "slay_pop_01"
