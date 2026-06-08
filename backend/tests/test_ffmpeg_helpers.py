"""Tests for app.features.render.engine.encoder.ffmpeg_helpers."""
import threading
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Module import
# ---------------------------------------------------------------------------

from app.features.render.engine.encoder.ffmpeg_helpers import (
    NVENC_SEMAPHORE,
    _argv_uses_nvenc,
    _effect_filter,
    _sanitize_speed,
    content_type_crf_delta,
    has_audio_stream,
    _has_audio_stream,
    nvenc_available,
    resolve_ffmpeg_threads,
    resolve_target_dimensions,
)


# ---------------------------------------------------------------------------
# NVENC_SEMAPHORE
# ---------------------------------------------------------------------------

def test_nvenc_semaphore_is_semaphore():
    assert isinstance(NVENC_SEMAPHORE, type(threading.Semaphore()))


# ---------------------------------------------------------------------------
# _argv_uses_nvenc
# ---------------------------------------------------------------------------

def test_argv_uses_nvenc_detects_h264_nvenc():
    assert _argv_uses_nvenc(["ffmpeg", "-c:v", "h264_nvenc"]) is True


def test_argv_uses_nvenc_detects_hevc_nvenc():
    assert _argv_uses_nvenc(["ffmpeg", "-c:v", "hevc_nvenc"]) is True


def test_argv_uses_nvenc_false_for_libx264():
    assert _argv_uses_nvenc(["ffmpeg", "-c:v", "libx264"]) is False


def test_argv_uses_nvenc_empty_list():
    assert _argv_uses_nvenc([]) is False


def test_argv_uses_nvenc_case_sensitive_match_only():
    # Batch 3 (audit FINDING-R01) tightened the detector to exact-set
    # membership. FFmpeg's codec names are always lowercase
    # (h264_nvenc / hevc_nvenc / av1_nvenc), so an upper-case spelling
    # is treated as a non-NVENC string and does NOT trigger the lock.
    # This rejects the prior substring-match false-positive class.
    assert _argv_uses_nvenc(["H264_NVENC"]) is False
    assert _argv_uses_nvenc(["h264_nvenc"]) is True


# ---------------------------------------------------------------------------
# _effect_filter
# ---------------------------------------------------------------------------

def test_effect_filter_slay_pop_01():
    result = _effect_filter("slay_pop_01")
    assert "eq=" in result
    assert "unsharp" in result


def test_effect_filter_story_clean_01():
    result = _effect_filter("story_clean_01")
    assert "eq=" in result


def test_effect_filter_default_returns_string():
    result = _effect_filter("unknown_preset")
    assert isinstance(result, str)
    assert len(result) > 0


def test_effect_filter_high_contrast():
    result = _effect_filter("high_contrast")
    assert "1.15" in result or "contrast=1.15" in result


# ---------------------------------------------------------------------------
# _sanitize_speed
# ---------------------------------------------------------------------------

def test_sanitize_speed_clamps_below_min():
    assert _sanitize_speed(0.1) == 0.5


def test_sanitize_speed_clamps_above_max():
    assert _sanitize_speed(2.0) == 1.5


def test_sanitize_speed_normal_value():
    assert _sanitize_speed(1.0) == pytest.approx(1.0)


def test_sanitize_speed_none_defaults_to_one():
    assert _sanitize_speed(None) == pytest.approx(1.0)


def test_sanitize_speed_string_input():
    assert _sanitize_speed("1.2") == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# content_type_crf_delta
# ---------------------------------------------------------------------------

def test_crf_delta_tutorial():
    assert content_type_crf_delta("tutorial") == -2


def test_crf_delta_interview():
    assert content_type_crf_delta("interview") == -2


def test_crf_delta_montage():
    assert content_type_crf_delta("montage") == 1


def test_crf_delta_vlog_zero():
    assert content_type_crf_delta("vlog") == 0


def test_crf_delta_unknown_zero():
    assert content_type_crf_delta("unknown") == 0


def test_crf_delta_empty_string():
    assert content_type_crf_delta("") == 0


# ---------------------------------------------------------------------------
# resolve_ffmpeg_threads
# ---------------------------------------------------------------------------

def test_resolve_ffmpeg_threads_returns_int():
    result = resolve_ffmpeg_threads(2)
    assert isinstance(result, int)
    assert result >= 1


def test_resolve_ffmpeg_threads_bounded():
    result = resolve_ffmpeg_threads(1)
    assert 1 <= result <= 8


def test_resolve_ffmpeg_threads_none_default():
    result = resolve_ffmpeg_threads(None)
    assert result >= 1


# ---------------------------------------------------------------------------
# has_audio_stream / _has_audio_stream (via probe_video_metadata mock)
# ---------------------------------------------------------------------------

def test_has_audio_stream_delegates_to_probe():
    with patch(
        "app.features.render.engine.encoder.ffmpeg_helpers.probe_video_metadata",
        return_value={"has_audio": True, "has_video": True, "fps": 30.0,
                      "duration": 5.0, "width": 1080, "height": 1920},
    ) as mock_probe:
        result = has_audio_stream("/fake/video.mp4")
    assert result is True
    mock_probe.assert_called_once_with("/fake/video.mp4")


def test_has_audio_stream_false_when_probe_returns_false():
    with patch(
        "app.features.render.engine.encoder.ffmpeg_helpers.probe_video_metadata",
        return_value={"has_audio": False, "has_video": True, "fps": 30.0,
                      "duration": 5.0, "width": 1080, "height": 1920},
    ):
        assert has_audio_stream("/fake/video.mp4") is False


# ---------------------------------------------------------------------------
# resolve_target_dimensions
# ---------------------------------------------------------------------------

def test_resolve_target_dimensions_9_16():
    assert resolve_target_dimensions("9:16") == (1080, 1920)


def test_resolve_target_dimensions_16_9():
    assert resolve_target_dimensions("16:9") == (1920, 1080)


def test_resolve_target_dimensions_1_1():
    assert resolve_target_dimensions("1:1") == (1080, 1080)


def test_resolve_target_dimensions_default():
    # unknown falls through to portrait default
    w, h = resolve_target_dimensions("3:4")
    assert w == 1080 and h == 1440


# ---------------------------------------------------------------------------
# nvenc_available (patched so no real GPU probe runs in CI)
# ---------------------------------------------------------------------------

def test_nvenc_available_returns_bool():
    # We just verify the return type; GPU probe itself is mocked.
    with patch(
        "app.features.render.engine.encoder.ffmpeg_helpers._has_encoder",
        return_value=False,
    ):
        # Clear LRU cache before calling so mock takes effect
        nvenc_available.cache_clear()
        result = nvenc_available()
        assert isinstance(result, bool)
