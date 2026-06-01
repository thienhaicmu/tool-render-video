"""test_ui_option_contract.py — Phase 5.10 UI option enum contract tests.

Verifies:
- Subtitle style options match backend enum (_PRESETS keys in styles.py)
- Effect preset options are the 6 documented presets
- Platform options are non-empty strings
- Duration bounds: min < max, both positive
- No documented enum value is invalid against the model
"""
import pytest


# ---------------------------------------------------------------------------
# 1. Subtitle style options
# ---------------------------------------------------------------------------

class TestSubtitleStyleOptions:
    """All documented subtitle_style enum values must be valid backend presets."""

    # The 10 canonical presets documented in UI_BACKEND_CONTRACT.md §6.3
    DOCUMENTED_STYLES = [
        "tiktok_bounce_v1",
        "bold_cap",
        "story_clean_01",
        "viral_bold",
        "clean_pro",
        "boxed_caption",
        "viral",
        "clean",
        "story",
        "gaming",
    ]

    def test_all_documented_styles_in_presets(self):
        """Every documented style ID must exist in _PRESETS."""
        from backend.app.services.subtitles.styles import _PRESETS
        missing = [s for s in self.DOCUMENTED_STYLES if s not in _PRESETS]
        assert not missing, f"Documented styles missing from _PRESETS: {missing}"

    def test_canonical_presets_count(self):
        """_PRESETS must have at least 10 entries (all documented ones)."""
        from backend.app.services.subtitles.styles import _PRESETS
        assert len(_PRESETS) >= 10

    def test_all_documented_styles_are_non_empty_strings(self):
        for style in self.DOCUMENTED_STYLES:
            assert isinstance(style, str) and style, f"Style must be non-empty string: {style!r}"

    def test_normalize_each_documented_style_returns_itself(self):
        """normalize_subtitle_style_id() on a canonical ID should return the same ID."""
        from backend.app.services.subtitles.styles import normalize_subtitle_style_id
        for style in self.DOCUMENTED_STYLES:
            result = normalize_subtitle_style_id(style)
            assert result == style, f"normalize_subtitle_style_id({style!r}) returned {result!r}"

    def test_legacy_aliases_resolve_to_canonical(self):
        """Legacy alias IDs should resolve to a canonical preset, not themselves."""
        from backend.app.services.subtitles.styles import _PRESETS, _STYLE_ALIASES, normalize_subtitle_style_id
        for alias, expected_canonical in _STYLE_ALIASES.items():
            result = normalize_subtitle_style_id(alias)
            assert result == expected_canonical, (
                f"Alias {alias!r} should resolve to {expected_canonical!r}, got {result!r}"
            )
            assert result in _PRESETS, f"Resolved value {result!r} not in _PRESETS"

    def test_unknown_style_falls_back_to_default(self):
        """Unknown style IDs fall back to the default preset."""
        from backend.app.services.subtitles.styles import _DEFAULT_PRESET_ID, normalize_subtitle_style_id
        result = normalize_subtitle_style_id("totally_unknown_style_xyz")
        assert result == _DEFAULT_PRESET_ID

    def test_pro_karaoke_is_alias_or_fallback(self):
        """pro_karaoke is the schema default but is not a canonical preset.

        It must resolve to _DEFAULT_PRESET_ID without raising.
        """
        from backend.app.services.subtitles.styles import _DEFAULT_PRESET_ID, normalize_subtitle_style_id
        result = normalize_subtitle_style_id("pro_karaoke")
        assert result == _DEFAULT_PRESET_ID

    def test_each_preset_has_required_fields(self):
        """Each ASSPreset must have id, font_default, base_font_size."""
        from backend.app.services.subtitles.styles import _PRESETS
        for preset_id, preset in _PRESETS.items():
            assert hasattr(preset, "id"), f"{preset_id} missing 'id'"
            assert hasattr(preset, "font_default"), f"{preset_id} missing 'font_default'"
            assert hasattr(preset, "base_font_size"), f"{preset_id} missing 'base_font_size'"
            assert preset.base_font_size > 0, f"{preset_id} base_font_size must be positive"


# ---------------------------------------------------------------------------
# 2. Effect preset options
# ---------------------------------------------------------------------------

class TestEffectPresetOptions:
    """Effect preset enum documented in UI_BACKEND_CONTRACT.md §6.4."""

    DOCUMENTED_PRESETS = [
        "slay_soft_01",
        "slay_pop_01",
        "story_clean_01",
        "social_bright",
        "cinematic_soft",
        "high_contrast",
    ]

    def test_documented_presets_count(self):
        assert len(self.DOCUMENTED_PRESETS) == 6

    def test_all_documented_presets_are_non_empty_strings(self):
        for preset in self.DOCUMENTED_PRESETS:
            assert isinstance(preset, str) and preset

    def test_default_effect_preset_is_documented(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.effect_preset in self.DOCUMENTED_PRESETS

    def test_visual_intensity_preset_map_values_are_documented(self):
        """AI visual intensity → preset mapping values must all be documented presets."""
        from backend.app.services.render.ffmpeg_helpers import _VISUAL_INTENSITY_PRESET_MAP
        for intensity, preset in _VISUAL_INTENSITY_PRESET_MAP.items():
            assert preset in self.DOCUMENTED_PRESETS, (
                f"AI intensity {intensity!r} maps to undocumented preset {preset!r}"
            )

    def test_visual_intensity_map_covers_low_medium_high(self):
        from backend.app.services.render.ffmpeg_helpers import _VISUAL_INTENSITY_PRESET_MAP
        for required_key in ("low", "medium", "high"):
            assert required_key in _VISUAL_INTENSITY_PRESET_MAP, (
                f"AI intensity key {required_key!r} missing from _VISUAL_INTENSITY_PRESET_MAP"
            )


# ---------------------------------------------------------------------------
# 3. Platform options
# ---------------------------------------------------------------------------

class TestPlatformOptions:
    DOCUMENTED_PLATFORMS = [
        "tiktok",
        "youtube_shorts",
        "instagram_reels",
    ]

    def test_platform_options_are_non_empty_strings(self):
        for platform in self.DOCUMENTED_PLATFORMS:
            assert isinstance(platform, str) and platform

    def test_default_target_platform_is_documented(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.target_platform in self.DOCUMENTED_PLATFORMS

    def test_documented_platforms_count(self):
        assert len(self.DOCUMENTED_PLATFORMS) == 3


# ---------------------------------------------------------------------------
# 4. Duration bounds
# ---------------------------------------------------------------------------

class TestDurationBounds:
    def test_default_min_part_sec_is_positive(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.min_part_sec > 0

    def test_default_max_part_sec_is_positive(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.max_part_sec > 0

    def test_min_less_than_max(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.min_part_sec < req.max_part_sec

    def test_playback_speed_default_in_range(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert 0.5 <= req.playback_speed <= 1.5

    def test_timeline_map_speed_clamp_min(self):
        """TimelineMap clamps speed to [0.5, 1.5]."""
        from backend.app.domain.timeline import TimelineMap
        tm = TimelineMap(source_start=0.0, source_end=10.0, effective_speed=0.1, trim_offset=0.0)
        assert tm.effective_speed == 0.5

    def test_timeline_map_speed_clamp_max(self):
        from backend.app.domain.timeline import TimelineMap
        tm = TimelineMap(source_start=0.0, source_end=10.0, effective_speed=2.5, trim_offset=0.0)
        assert tm.effective_speed == 1.5

    def test_ai_clip_min_duration_validated(self):
        """ai_clip_min_duration_sec must be clamped to [5, 180]."""
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest(ai_clip_min_duration_sec=1)
        assert req.ai_clip_min_duration_sec == 5  # clamped up

    def test_ai_clip_max_duration_validated(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest(ai_clip_max_duration_sec=9999)
        assert req.ai_clip_max_duration_sec == 300  # clamped down


# ---------------------------------------------------------------------------
# 5. Source quality mode options
# ---------------------------------------------------------------------------

class TestSourceQualityModeOptions:
    DOCUMENTED_MODES = [
        "standard_1080",
        "high_1440",
        "best_available",
    ]

    def test_all_documented_modes_are_valid(self):
        from backend.app.models.schemas import RenderRequest
        for mode in self.DOCUMENTED_MODES:
            req = RenderRequest(source_quality_mode=mode)
            assert req.source_quality_mode == mode

    def test_invalid_source_quality_mode_raises(self):
        from pydantic import ValidationError
        from backend.app.models.schemas import RenderRequest
        with pytest.raises(ValidationError):
            RenderRequest(source_quality_mode="8k_hdr")

    def test_default_source_quality_mode_is_documented(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.source_quality_mode in self.DOCUMENTED_MODES


# ---------------------------------------------------------------------------
# 6. Render profile options
# ---------------------------------------------------------------------------

class TestRenderProfileOptions:
    DOCUMENTED_PROFILES = ["fast", "balanced", "quality", "best"]

    def test_all_documented_profiles_are_valid(self):
        from backend.app.models.schemas import RenderRequest
        for profile in self.DOCUMENTED_PROFILES:
            req = RenderRequest(render_profile=profile)
            assert req.render_profile == profile

    def test_invalid_render_profile_raises(self):
        from pydantic import ValidationError
        from backend.app.models.schemas import RenderRequest
        with pytest.raises(ValidationError):
            RenderRequest(render_profile="ultra_hd")

    def test_default_render_profile_is_documented(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.render_profile in self.DOCUMENTED_PROFILES


# AI execution hints class removed in Phase G — validators.py module deleted.
