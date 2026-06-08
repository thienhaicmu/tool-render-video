"""Tests for app.features.render.engine.pipeline.pipeline_segment_selection."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.features.render.engine.pipeline.pipeline_segment_selection import (
    _PLATFORM_PROFILES,
    _safe_output_name,
    _smart_output_stem,
    _select_cover_frame_time,
    _get_effective_playback_speed,
    _build_variant_segments,
)


# ---------------------------------------------------------------------------
# _PLATFORM_PROFILES
# ---------------------------------------------------------------------------

def test_platform_profiles_has_all_three_platforms():
    assert "tiktok" in _PLATFORM_PROFILES
    assert "youtube_shorts" in _PLATFORM_PROFILES
    assert "instagram_reels" in _PLATFORM_PROFILES


@pytest.mark.parametrize("platform", ["tiktok", "youtube_shorts", "instagram_reels"])
def test_platform_profiles_has_required_keys(platform):
    profile = _PLATFORM_PROFILES[platform]
    assert "speed_delta" in profile
    assert "hook_sort_bonus" in profile
    assert "sub_bias" in profile


def test_tiktok_speed_delta_is_positive():
    assert _PLATFORM_PROFILES["tiktok"]["speed_delta"] > 0


def test_instagram_speed_delta_is_negative():
    assert _PLATFORM_PROFILES["instagram_reels"]["speed_delta"] < 0


def test_youtube_shorts_speed_delta_is_zero():
    assert _PLATFORM_PROFILES["youtube_shorts"]["speed_delta"] == 0.0


# ---------------------------------------------------------------------------
# _safe_output_name
# ---------------------------------------------------------------------------

def test_safe_output_name_strips_special_chars():
    result = _safe_output_name('Hello:World*Test?"File|Name')
    assert ":" not in result
    assert "*" not in result
    assert "?" not in result
    assert "|" not in result


def test_safe_output_name_keeps_alphanumeric():
    result = _safe_output_name("Hello World 123")
    assert "Hello" in result
    assert "World" in result
    assert "123" in result


def test_safe_output_name_empty_input_returns_empty():
    assert _safe_output_name("") == ""


def test_safe_output_name_truncates_long_text():
    long_text = "a" * 200
    result = _safe_output_name(long_text)
    assert len(result) <= 80


def test_safe_output_name_strips_leading_trailing_dashes_and_spaces():
    result = _safe_output_name("  -Hello World-  ")
    assert not result.startswith("-")
    assert not result.startswith(" ")
    assert not result.endswith("-")
    assert not result.endswith(" ")


# ---------------------------------------------------------------------------
# _smart_output_stem
# ---------------------------------------------------------------------------

def test_smart_output_stem_uses_hook_text_first():
    result = _smart_output_stem("My Hook Text", "Source Title", "abc12345")
    assert "My Hook Text" in result or "My" in result


def test_smart_output_stem_falls_back_to_source_title():
    result = _smart_output_stem("", "Source Title", "abc12345")
    assert "Source" in result or "Title" in result


def test_smart_output_stem_falls_back_to_job_id():
    result = _smart_output_stem("", "", "abc12345")
    assert result == "render_abc12345"


def test_smart_output_stem_job_id_truncated_to_8():
    result = _smart_output_stem("", "", "1234567890abcdef")
    assert result == "render_12345678"


# ---------------------------------------------------------------------------
# _select_cover_frame_time
# ---------------------------------------------------------------------------

def test_select_cover_frame_time_returns_tuple():
    t, reason = _select_cover_frame_time(
        clip_duration=30.0,
        hook_score=50.0,
        srt_meta={},
        target_platform="tiktok",
        variant_type="balanced",
    )
    assert isinstance(t, float)
    assert isinstance(reason, str)


def test_select_cover_frame_time_within_clip_bounds():
    t, _ = _select_cover_frame_time(
        clip_duration=30.0,
        hook_score=50.0,
        srt_meta={},
        target_platform="youtube_shorts",
        variant_type="balanced",
    )
    assert 0.0 <= t <= 30.0


def test_select_cover_frame_time_very_short_clip():
    # clip_duration is clamped to max(2.0, ...) so 1s clip becomes 2s
    t, _ = _select_cover_frame_time(
        clip_duration=1.0,
        hook_score=0.0,
        srt_meta={},
        target_platform="tiktok",
        variant_type="aggressive",
    )
    assert 0.0 <= t <= 2.0


# ---------------------------------------------------------------------------
# _get_effective_playback_speed
# ---------------------------------------------------------------------------

def test_get_effective_playback_speed_tiktok_gets_delta_added():
    payload = SimpleNamespace(playback_speed=1.07)
    tiktok_delta = _PLATFORM_PROFILES["tiktok"]["speed_delta"]
    result = _get_effective_playback_speed(payload, "tiktok")
    assert result == pytest.approx(1.07 + tiktok_delta)


def test_get_effective_playback_speed_youtube_shorts_no_delta():
    payload = SimpleNamespace(playback_speed=1.07)
    result = _get_effective_playback_speed(payload, "youtube_shorts")
    assert result == pytest.approx(1.07)


def test_get_effective_playback_speed_clamped_to_max_1_5():
    payload = SimpleNamespace(playback_speed=1.5)
    # Even with a positive delta, result should not exceed 1.5
    result = _get_effective_playback_speed(payload, "tiktok")
    assert result <= 1.5


def test_get_effective_playback_speed_clamped_to_min_0_5():
    payload = SimpleNamespace(playback_speed=0.5)
    # Even with negative delta (instagram), result should not go below 0.5
    result = _get_effective_playback_speed(payload, "instagram_reels")
    assert result >= 0.5


def test_get_effective_playback_speed_unknown_platform_no_delta():
    payload = SimpleNamespace(playback_speed=1.0)
    result = _get_effective_playback_speed(payload, "unknown_platform")
    assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _build_variant_segments
# ---------------------------------------------------------------------------

def test_build_variant_segments_empty_scored_returns_empty():
    payload = SimpleNamespace(playback_speed=1.07, subtitle_style="viral")
    result = _build_variant_segments([], payload)
    assert result == []


def test_build_variant_segments_returns_three_variants():
    scored = [
        {"start": 0.0, "viral_score": 70, "hook_score": 80, "motion_score": 60,
         "scene_quality_score": 65, "speech_density_score": 50, "market_score": 55,
         "duration_fit_score": 70, "content_type_hint": "tutorial"},
        {"start": 30.0, "viral_score": 60, "hook_score": 50, "motion_score": 40,
         "scene_quality_score": 75, "speech_density_score": 60, "market_score": 65,
         "duration_fit_score": 60, "content_type_hint": "tutorial"},
        {"start": 60.0, "viral_score": 50, "hook_score": 55, "motion_score": 50,
         "scene_quality_score": 80, "speech_density_score": 70, "market_score": 60,
         "duration_fit_score": 55, "content_type_hint": "tutorial"},
    ]
    payload = SimpleNamespace(playback_speed=1.07, subtitle_style="viral")
    result = _build_variant_segments(scored, payload)
    assert len(result) == 3


def test_build_variant_segments_variant_types_present():
    scored = [
        {"start": 0.0, "viral_score": 70, "hook_score": 80, "motion_score": 60,
         "scene_quality_score": 65, "speech_density_score": 50, "market_score": 55,
         "duration_fit_score": 70, "content_type_hint": "vlog"},
        {"start": 10.0, "viral_score": 55, "hook_score": 45, "motion_score": 45,
         "scene_quality_score": 70, "speech_density_score": 55, "market_score": 60,
         "duration_fit_score": 65, "content_type_hint": "vlog"},
    ]
    payload = SimpleNamespace(playback_speed=1.07, subtitle_style="")
    result = _build_variant_segments(scored, payload)
    variant_types = {v["variant_type"] for v in result}
    assert "aggressive" in variant_types
    assert "balanced" in variant_types
    assert "story_first" in variant_types
