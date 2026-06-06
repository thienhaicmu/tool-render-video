"""Tests for app.features.render.engine.subtitle.processing.styles."""
import pytest

from app.features.render.engine.subtitle.processing.styles import (
    ASSPreset,
    _DEFAULT_PRESET_ID,
    _HL_CLOSE,
    _HL_OPEN,
    _PRESETS,
    _STYLE_ALIASES,
    get_subtitle_preset,
    normalize_subtitle_style_id,
)


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

def test_hl_open_is_non_empty_string():
    assert isinstance(_HL_OPEN, str) and len(_HL_OPEN) >= 1


def test_hl_close_is_non_empty_string():
    assert isinstance(_HL_CLOSE, str) and len(_HL_CLOSE) >= 1


def test_hl_open_close_differ():
    assert _HL_OPEN != _HL_CLOSE


def test_presets_is_dict():
    assert isinstance(_PRESETS, dict)
    assert len(_PRESETS) > 0


def test_default_preset_id_in_presets():
    assert _DEFAULT_PRESET_ID in _PRESETS


def test_style_aliases_is_dict():
    assert isinstance(_STYLE_ALIASES, dict)


# ---------------------------------------------------------------------------
# ASSPreset dataclass structure
# ---------------------------------------------------------------------------

def test_ass_preset_has_required_fields():
    preset = _PRESETS["tiktok_bounce_v1"]
    assert isinstance(preset, ASSPreset)
    assert hasattr(preset, "id")
    assert hasattr(preset, "font_default")
    assert hasattr(preset, "base_font_size")
    assert hasattr(preset, "primary_color")
    assert hasattr(preset, "outline_color")
    assert hasattr(preset, "bold")
    assert hasattr(preset, "bounce_fx")
    assert hasattr(preset, "auto_scale")
    assert hasattr(preset, "heavy_scale")
    assert hasattr(preset, "margin_v_ratio")


def test_ass_preset_is_frozen():
    preset = _PRESETS["tiktok_bounce_v1"]
    with pytest.raises(Exception):
        preset.id = "new_id"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# normalize_subtitle_style_id
# ---------------------------------------------------------------------------

def test_normalize_known_id_unchanged():
    assert normalize_subtitle_style_id("tiktok_bounce_v1") == "tiktok_bounce_v1"


def test_normalize_alias_resolves():
    # "viral_clean_montserrat" is an alias for "tiktok_bounce_v1"
    result = normalize_subtitle_style_id("viral_clean_montserrat")
    assert result == "tiktok_bounce_v1"


def test_normalize_unknown_falls_to_default():
    result = normalize_subtitle_style_id("nonexistent_style")
    assert result == _DEFAULT_PRESET_ID


def test_normalize_uppercase_works():
    result = normalize_subtitle_style_id("TIKTOK_BOUNCE_V1")
    assert result == "tiktok_bounce_v1"


def test_normalize_empty_string_gives_default():
    result = normalize_subtitle_style_id("")
    assert result == _DEFAULT_PRESET_ID


def test_normalize_none_like_gives_default():
    # None should not crash; handled via (style_id or _DEFAULT_PRESET_ID)
    result = normalize_subtitle_style_id(None)  # type: ignore[arg-type]
    assert result == _DEFAULT_PRESET_ID


# ---------------------------------------------------------------------------
# get_subtitle_preset
# ---------------------------------------------------------------------------

def test_get_preset_returns_ass_preset():
    preset = get_subtitle_preset("tiktok_bounce_v1")
    assert isinstance(preset, ASSPreset)
    assert preset.id == "tiktok_bounce_v1"


def test_get_preset_via_alias():
    preset = get_subtitle_preset("slay_soft_01")
    assert preset.id == "slay_soft"


def test_get_preset_unknown_returns_default():
    preset = get_subtitle_preset("completely_unknown_xyz")
    assert preset.id == _DEFAULT_PRESET_ID


def test_get_preset_all_canonical_ids_resolvable():
    """Every key in _PRESETS should be resolvable."""
    for preset_id in _PRESETS:
        p = get_subtitle_preset(preset_id)
        assert p.id == preset_id
