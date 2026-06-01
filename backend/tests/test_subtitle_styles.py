"""Tests for Phase 4G.1 — subtitle styles extraction.

Verifies:
- app.services.subtitles.styles imports cleanly
- app.services.subtitle_engine still exposes all moved symbols
- Same-object identity for mutable constants (dicts)
- Scalar equality for immutable constants
- PUA sentinel constants exactly unchanged
- Preset keys and fields unchanged
- ASSPreset is a frozen dataclass
- No behavior function was moved in this phase
- Backward-compat import path still works
"""
import importlib
import pytest

# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestStylesModuleImports:
    def test_subtitles_styles_imports_cleanly(self):
        import app.services.subtitles.styles

    def test_subtitle_engine_imports_cleanly(self):
        import app.services.subtitle_engine

    def test_subtitles_package_imports_cleanly(self):
        import app.services.subtitles


# ---------------------------------------------------------------------------
# PUA sentinel constant tests
# ---------------------------------------------------------------------------

class TestPUASentinelConstants:
    def test_hl_open_exact_value(self):
        from app.services.subtitles.styles import _HL_OPEN
        assert _HL_OPEN == ""
        assert len(_HL_OPEN) == 1

    def test_hl_close_exact_value(self):
        from app.services.subtitles.styles import _HL_CLOSE
        assert _HL_CLOSE == ""
        assert len(_HL_CLOSE) == 1

    def test_hl_open_distinct_from_close(self):
        from app.services.subtitles.styles import _HL_OPEN, _HL_CLOSE
        assert _HL_OPEN != _HL_CLOSE

    def test_hl_open_engine_compat(self):
        from app.services.subtitle_engine import _HL_OPEN
        assert _HL_OPEN == ""

    def test_hl_close_engine_compat(self):
        from app.services.subtitle_engine import _HL_CLOSE
        assert _HL_CLOSE == ""

    def test_hl_open_same_object(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        # After import, subtitle_engine._HL_OPEN is the styles._HL_OPEN object
        assert s._HL_OPEN is e._HL_OPEN

    def test_hl_close_same_object(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        assert s._HL_CLOSE is e._HL_CLOSE


# ---------------------------------------------------------------------------
# Preset constant tests
# ---------------------------------------------------------------------------

EXPECTED_PRESET_IDS = {
    "tiktok_bounce_v1", "bold_cap", "story_clean_01", "viral_bold",
    "clean_pro", "boxed_caption", "viral", "clean", "story", "gaming",
    # Presets added after initial extraction:
    "bold_stroke", "color_pop", "dark_card", "fire_bold", "neon_glow", "slay_soft",
}

class TestPresetConstants:
    def test_presets_keys_unchanged(self):
        from app.services.subtitles.styles import _PRESETS
        assert set(_PRESETS.keys()) == EXPECTED_PRESET_IDS

    def test_default_preset_id(self):
        from app.services.subtitles.styles import _DEFAULT_PRESET_ID
        assert _DEFAULT_PRESET_ID == "tiktok_bounce_v1"

    def test_bounce_fx_value(self):
        from app.services.subtitles.styles import BOUNCE_FX
        assert BOUNCE_FX == r"{\fscx122\fscy122\t(0,200,\fscx100\fscy100)}"

    def test_style_aliases_keys_present(self):
        from app.services.subtitles.styles import _STYLE_ALIASES
        expected_aliases = {
            "viral_clean_montserrat", "viral_soft_poppins",
            "viral_pop_anton", "viral_compact_barlow", "clean_bold_01",
            # Aliases added after initial extraction:
            "boxed", "pro_karaoke", "slay_soft_01",
        }
        assert set(_STYLE_ALIASES.keys()) == expected_aliases

    def test_style_aliases_values(self):
        from app.services.subtitles.styles import _STYLE_ALIASES
        assert _STYLE_ALIASES["viral_clean_montserrat"] == "tiktok_bounce_v1"
        assert _STYLE_ALIASES["clean_bold_01"] == "clean_pro"

    def test_tiktok_bounce_v1_fields(self):
        from app.services.subtitles.styles import _PRESETS
        p = _PRESETS["tiktok_bounce_v1"]
        assert p.font_default == "Bungee"
        assert p.primary_color == "&H00FFFFFF"
        assert p.bounce_fx is True
        assert p.auto_scale is True
        assert p.spacing == pytest.approx(0.3)

    def test_viral_preset_fields(self):
        from app.services.subtitles.styles import _PRESETS
        p = _PRESETS["viral"]
        assert p.font_default == "Anton"
        assert p.base_font_size == 50
        assert p.heavy_scale is True
        assert p.margin_v_ratio == pytest.approx(0.22)

    def test_gaming_preset_border_style(self):
        from app.services.subtitles.styles import _PRESETS
        assert _PRESETS["gaming"].border_style == 3

    def test_clean_preset_no_bounce(self):
        from app.services.subtitles.styles import _PRESETS
        assert _PRESETS["clean"].bounce_fx is False


# ---------------------------------------------------------------------------
# ASSPreset dataclass tests
# ---------------------------------------------------------------------------

class TestASSPresetDataclass:
    def test_asspreset_is_frozen(self):
        from app.services.subtitles.styles import ASSPreset
        import dataclasses
        assert dataclasses.is_dataclass(ASSPreset)
        fields = dataclasses.fields(ASSPreset)
        # frozen=True means the class has __delattr__ and __setattr__ that raise
        instance = ASSPreset(
            id="test", font_default="Bungee", base_font_size=38,
            primary_color="&H00FFFFFF", secondary_color="&H0000FFFF",
            outline_color="&H00000000", back_color="&H90000000",
            bold=0, border_style=1, outline_default=4, shadow_default=2,
            alignment=2, margin_l=30, margin_r=30, wrap_max_em=16.0,
            bounce_fx=True, auto_scale=False, heavy_scale=False, margin_v_ratio=0.0,
        )
        with pytest.raises((AttributeError, TypeError)):
            instance.id = "mutated"

    def test_asspreset_field_count(self):
        import dataclasses
        from app.services.subtitles.styles import ASSPreset
        fields = dataclasses.fields(ASSPreset)
        assert len(fields) == 20  # 19 required + 1 default (spacing)

    def test_asspreset_spacing_default(self):
        from app.services.subtitles.styles import ASSPreset
        p = ASSPreset(
            id="x", font_default="F", base_font_size=12,
            primary_color="&H00FFFFFF", secondary_color="&H0000FFFF",
            outline_color="&H00000000", back_color="&H00000000",
            bold=0, border_style=1, outline_default=2, shadow_default=1,
            alignment=2, margin_l=10, margin_r=10, wrap_max_em=16.0,
            bounce_fx=False, auto_scale=False, heavy_scale=False, margin_v_ratio=0.0,
        )
        assert p.spacing == 0.0


# ---------------------------------------------------------------------------
# Same-object identity tests
# ---------------------------------------------------------------------------

class TestSameObjectIdentity:
    def test_presets_dict_identity(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        assert s._PRESETS is e._PRESETS

    def test_style_aliases_identity(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        assert s._STYLE_ALIASES is e._STYLE_ALIASES

    def test_preset_motion_fx_identity(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        assert s._PRESET_MOTION_FX is e._PRESET_MOTION_FX

    def test_asspreset_class_identity(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        assert s.ASSPreset is e.ASSPreset

    def test_normalize_function_identity(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        assert s.normalize_subtitle_style_id is e.normalize_subtitle_style_id

    def test_get_subtitle_preset_identity(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        assert s.get_subtitle_preset is e.get_subtitle_preset

    def test_build_ass_style_line_identity(self):
        import app.services.subtitles.styles as s
        import app.services.subtitle_engine as e
        assert s.build_ass_style_line is e.build_ass_style_line


# ---------------------------------------------------------------------------
# Backward-compat: engine still exposes all style symbols
# ---------------------------------------------------------------------------

class TestEngineBackwardCompat:
    def test_engine_exposes_presets(self):
        from app.services.subtitle_engine import _PRESETS
        assert "tiktok_bounce_v1" in _PRESETS

    def test_engine_exposes_bounce_fx(self):
        from app.services.subtitle_engine import BOUNCE_FX
        assert "fscx" in BOUNCE_FX

    def test_engine_exposes_asspresets(self):
        from app.services.subtitle_engine import ASSPreset
        assert ASSPreset is not None

    def test_engine_exposes_normalize(self):
        from app.services.subtitle_engine import normalize_subtitle_style_id
        result = normalize_subtitle_style_id("viral_clean_montserrat")
        assert result == "tiktok_bounce_v1"

    def test_engine_exposes_get_preset(self):
        from app.services.subtitle_engine import get_subtitle_preset
        p = get_subtitle_preset("viral")
        assert p.id == "viral"


# ---------------------------------------------------------------------------
# Verify NO behavior functions were moved to styles.py
# ---------------------------------------------------------------------------

class TestNoLogicMovedToStyles:
    def test_parse_srt_blocks_not_in_styles(self):
        import app.services.subtitles.styles as s
        assert not hasattr(s, "parse_srt_blocks")

    def test_srt_to_ass_bounce_not_in_styles(self):
        import app.services.subtitles.styles as s
        assert not hasattr(s, "srt_to_ass_bounce")

    def test_transcribe_to_srt_not_in_styles(self):
        import app.services.subtitles.styles as s
        assert not hasattr(s, "transcribe_to_srt")

    def test_resegment_not_in_styles(self):
        import app.services.subtitles.styles as s
        assert not hasattr(s, "resegment_srt_for_readability")

    def test_has_audio_stream_not_in_styles(self):
        import app.services.subtitles.styles as s
        assert not hasattr(s, "has_audio_stream")
