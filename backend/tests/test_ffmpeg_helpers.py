"""
Tests for Phase 4E.1: services/render/ffmpeg_helpers.py extraction.

Verifies:
- Import from new module works
- Backward-compat import from render_engine works
- Key moved names are identical objects between modules
- Behavior of pure helpers is unchanged (no real FFmpeg/GPU calls)
"""

import os
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

class TestImportFromNewModule:
    def test_import_ffmpeg_helpers_package(self):
        from app.services.render import ffmpeg_helpers
        assert ffmpeg_helpers is not None

    def test_import_probe_video_metadata(self):
        from app.services.render.ffmpeg_helpers import probe_video_metadata
        assert callable(probe_video_metadata)

    def test_import_set_thread_cancel_event(self):
        from app.services.render.ffmpeg_helpers import set_thread_cancel_event
        assert callable(set_thread_cancel_event)

    def test_import_nvenc_available(self):
        from app.services.render.ffmpeg_helpers import nvenc_available
        assert callable(nvenc_available)

    def test_import_resolve_target_dimensions(self):
        from app.services.render.ffmpeg_helpers import resolve_target_dimensions
        assert callable(resolve_target_dimensions)

    def test_import_resolve_ffmpeg_threads(self):
        from app.services.render.ffmpeg_helpers import resolve_ffmpeg_threads
        assert callable(resolve_ffmpeg_threads)

    def test_import_run_ffmpeg_with_retry(self):
        from app.services.render.ffmpeg_helpers import _run_ffmpeg_with_retry
        assert callable(_run_ffmpeg_with_retry)

    def test_import_constants(self):
        from app.services.render.ffmpeg_helpers import (
            NVENC_SEMAPHORE, _FFMPEG_TIMEOUT_SEC, _FPS_CAP, _tls,
        )
        assert NVENC_SEMAPHORE is not None
        assert isinstance(_FFMPEG_TIMEOUT_SEC, int)
        assert _FPS_CAP == 60


class TestBackwardCompatImport:
    """Existing callers importing from render_engine must still work."""

    def test_probe_video_metadata_via_render_engine(self):
        from app.services.render_engine import probe_video_metadata
        assert callable(probe_video_metadata)

    def test_set_thread_cancel_event_via_render_engine(self):
        from app.services.render_engine import set_thread_cancel_event
        assert callable(set_thread_cancel_event)

    def test_nvenc_available_via_render_engine(self):
        from app.services.render_engine import nvenc_available
        assert callable(nvenc_available)

    def test_resolve_target_dimensions_via_render_engine(self):
        from app.services.render_engine import resolve_target_dimensions
        assert callable(resolve_target_dimensions)

    def test_nvenc_semaphore_via_render_engine(self):
        from app.services.render_engine import NVENC_SEMAPHORE
        assert NVENC_SEMAPHORE is not None

    def test_run_ffmpeg_with_retry_via_render_engine(self):
        from app.services.render_engine import _run_ffmpeg_with_retry
        assert callable(_run_ffmpeg_with_retry)


class TestSameObjects:
    """Names re-exported from render_engine must be the same objects as in ffmpeg_helpers."""

    def test_probe_video_metadata_is_same_object(self):
        import app.services.render.ffmpeg_helpers as fh
        import app.services.render_engine as re_mod
        assert re_mod.probe_video_metadata is fh.probe_video_metadata

    def test_nvenc_semaphore_is_same_object(self):
        import app.services.render.ffmpeg_helpers as fh
        import app.services.render_engine as re_mod
        assert re_mod.NVENC_SEMAPHORE is fh.NVENC_SEMAPHORE

    def test_tls_is_same_object(self):
        import app.services.render.ffmpeg_helpers as fh
        import app.services.render_engine as re_mod
        assert re_mod._tls is fh._tls

    def test_run_ffmpeg_with_retry_is_same_object(self):
        import app.services.render.ffmpeg_helpers as fh
        import app.services.render_engine as re_mod
        assert re_mod._run_ffmpeg_with_retry is fh._run_ffmpeg_with_retry

    def test_resolve_target_dimensions_is_same_object(self):
        import app.services.render.ffmpeg_helpers as fh
        import app.services.render_engine as re_mod
        assert re_mod.resolve_target_dimensions is fh.resolve_target_dimensions


# ---------------------------------------------------------------------------
# _sanitize_speed — clamps to [0.5, 1.5]
# ---------------------------------------------------------------------------

class TestSanitizeSpeed:
    def test_normal_value_unchanged(self):
        from app.services.render.ffmpeg_helpers import _sanitize_speed
        assert _sanitize_speed(1.15) == pytest.approx(1.15)

    def test_below_min_clamped_to_0_5(self):
        from app.services.render.ffmpeg_helpers import _sanitize_speed
        assert _sanitize_speed(0.1) == pytest.approx(0.5)

    def test_above_max_clamped_to_1_5(self):
        from app.services.render.ffmpeg_helpers import _sanitize_speed
        assert _sanitize_speed(2.0) == pytest.approx(1.5)

    def test_none_defaults_to_1_0(self):
        from app.services.render.ffmpeg_helpers import _sanitize_speed
        assert _sanitize_speed(None) == pytest.approx(1.0)

    def test_string_input_cast_ok(self):
        from app.services.render.ffmpeg_helpers import _sanitize_speed
        assert _sanitize_speed("1.2") == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# _safe_filter_path — comes from encoder_helpers; test via render_engine namespace
# ---------------------------------------------------------------------------

class TestSafeFilterPath:
    def test_importable_via_render_engine(self):
        from app.services.render_engine import _safe_filter_path
        assert callable(_safe_filter_path)


# ---------------------------------------------------------------------------
# _parse_fps_ratio — pure string math
# ---------------------------------------------------------------------------

class TestParseFpsRatio:
    def test_fraction_string(self):
        from app.services.render.ffmpeg_helpers import _parse_fps_ratio
        assert _parse_fps_ratio("60/1") == pytest.approx(60.0)

    def test_ntsc_fraction(self):
        from app.services.render.ffmpeg_helpers import _parse_fps_ratio
        assert _parse_fps_ratio("30000/1001") == pytest.approx(29.97, rel=1e-3)

    def test_plain_float_string(self):
        from app.services.render.ffmpeg_helpers import _parse_fps_ratio
        assert _parse_fps_ratio("25.0") == pytest.approx(25.0)

    def test_zero_denominator_returns_0(self):
        from app.services.render.ffmpeg_helpers import _parse_fps_ratio
        assert _parse_fps_ratio("30/0") == pytest.approx(0.0)

    def test_empty_string_returns_0(self):
        from app.services.render.ffmpeg_helpers import _parse_fps_ratio
        assert _parse_fps_ratio("") == pytest.approx(0.0)

    def test_invalid_string_returns_0(self):
        from app.services.render.ffmpeg_helpers import _parse_fps_ratio
        assert _parse_fps_ratio("not_a_number") == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# resolve_target_dimensions — aspect ratio mapping
# ---------------------------------------------------------------------------

class TestResolveTargetDimensions:
    def test_9_16_portrait(self):
        from app.services.render.ffmpeg_helpers import resolve_target_dimensions
        assert resolve_target_dimensions("9:16") == (1080, 1920)

    def test_16_9_landscape(self):
        from app.services.render.ffmpeg_helpers import resolve_target_dimensions
        assert resolve_target_dimensions("16:9") == (1920, 1080)

    def test_1_1_square(self):
        from app.services.render.ffmpeg_helpers import resolve_target_dimensions
        assert resolve_target_dimensions("1:1") == (1080, 1080)

    def test_3_4_portrait_default(self):
        from app.services.render.ffmpeg_helpers import resolve_target_dimensions
        assert resolve_target_dimensions("3:4") == (1080, 1440)

    def test_unknown_falls_to_portrait_default(self):
        from app.services.render.ffmpeg_helpers import resolve_target_dimensions
        assert resolve_target_dimensions("unknown") == (1080, 1440)

    def test_none_falls_to_portrait_default(self):
        from app.services.render.ffmpeg_helpers import resolve_target_dimensions
        assert resolve_target_dimensions(None) == (1080, 1440)  # type: ignore


# ---------------------------------------------------------------------------
# _resolve_codec — CPU fallback when no GPU
# ---------------------------------------------------------------------------

class TestResolveCodec:
    def test_no_nvenc_returns_libx264(self):
        from app.services.render.ffmpeg_helpers import _resolve_codec
        with patch("app.services.render.ffmpeg_helpers._has_encoder", return_value=False):
            assert _resolve_codec("h264") == "libx264"

    def test_h265_no_nvenc_returns_libx265(self):
        from app.services.render.ffmpeg_helpers import _resolve_codec
        with patch("app.services.render.ffmpeg_helpers._has_encoder", return_value=False):
            assert _resolve_codec("h265") == "libx265"

    def test_nvenc_mode_with_gpu_returns_h264_nvenc(self):
        from app.services.render.ffmpeg_helpers import _resolve_codec
        with patch("app.services.render.ffmpeg_helpers._has_encoder", return_value=True), \
             patch("app.services.render.ffmpeg_helpers._nvenc_runtime_ready", return_value=True):
            assert _resolve_codec("h264", "nvenc") == "h264_nvenc"

    def test_cpu_mode_always_returns_libx264(self):
        from app.services.render.ffmpeg_helpers import _resolve_codec
        with patch("app.services.render.ffmpeg_helpers._has_encoder", return_value=True), \
             patch("app.services.render.ffmpeg_helpers._nvenc_runtime_ready", return_value=True):
            assert _resolve_codec("h264", "cpu") == "libx264"


# ---------------------------------------------------------------------------
# _should_fallback_to_cpu — tested via _run_ffmpeg_with_retry importability
# ---------------------------------------------------------------------------

class TestRunFfmpegWithRetryImportable:
    def test_importable_and_patchable(self):
        from app.services.render.ffmpeg_helpers import _run_ffmpeg_with_retry
        # Verify it can be patched at its canonical location
        with patch("app.services.render.ffmpeg_helpers._run_ffmpeg_with_retry") as m:
            m.return_value = MagicMock()
            from app.services.render.ffmpeg_helpers import _run_ffmpeg_with_retry as fn
            # Patching replaced the module-level name; verify patch took effect
            assert m is fn


# ---------------------------------------------------------------------------
# _build_audio_filter — speed/loudnorm filter string construction
# ---------------------------------------------------------------------------

class TestBuildAudioFilter:
    def test_no_processing_returns_none(self):
        from app.services.render.ffmpeg_helpers import _build_audio_filter
        result = _build_audio_filter(loudnorm_enabled=False, reup_mode=False, speed=1.0)
        assert result is None

    def test_speed_ne_1_adds_atempo(self):
        from app.services.render.ffmpeg_helpers import _build_audio_filter
        result = _build_audio_filter(loudnorm_enabled=False, reup_mode=False, speed=1.15)
        assert result is not None
        assert "atempo=1.1500" in result

    def test_loudnorm_enabled_adds_normalization(self):
        from app.services.render.ffmpeg_helpers import _build_audio_filter
        result = _build_audio_filter(loudnorm_enabled=True, reup_mode=False, speed=1.0)
        assert result is not None
        assert "loudnorm" in result
        assert "highpass" in result

    def test_loudnorm_skipped_in_reup_mode(self):
        from app.services.render.ffmpeg_helpers import _build_audio_filter
        result = _build_audio_filter(loudnorm_enabled=True, reup_mode=True, speed=1.0)
        # reup_mode suppresses loudnorm, adds reup_audio_filter instead
        assert result is None or "loudnorm" not in (result or "")


# ---------------------------------------------------------------------------
# _build_audio_mix_filter — BGM ducking / plain amix
# ---------------------------------------------------------------------------

class TestBuildAudioMixFilter:
    def test_ducking_enabled_produces_sidechaincompress(self):
        from app.services.render.ffmpeg_helpers import _build_audio_mix_filter
        with patch.dict(os.environ, {"BGM_DUCKING_ENABLED": "1"}):
            result = _build_audio_mix_filter("a0", "a1", "aout")
        assert "sidechaincompress" in result
        assert "amix" in result

    def test_ducking_disabled_produces_plain_amix(self):
        from app.services.render.ffmpeg_helpers import _build_audio_mix_filter
        with patch.dict(os.environ, {"BGM_DUCKING_ENABLED": "0"}):
            result = _build_audio_mix_filter("a0", "a1", "aout")
        assert "sidechaincompress" not in result
        assert "amix" in result


# ---------------------------------------------------------------------------
# content_type_crf_delta — pure lookup
# ---------------------------------------------------------------------------

class TestContentTypeCrfDelta:
    def test_tutorial_returns_minus_2(self):
        from app.services.render.ffmpeg_helpers import content_type_crf_delta
        assert content_type_crf_delta("tutorial") == -2

    def test_interview_returns_minus_2(self):
        from app.services.render.ffmpeg_helpers import content_type_crf_delta
        assert content_type_crf_delta("interview") == -2

    def test_montage_returns_plus_1(self):
        from app.services.render.ffmpeg_helpers import content_type_crf_delta
        assert content_type_crf_delta("montage") == 1

    def test_vlog_returns_0(self):
        from app.services.render.ffmpeg_helpers import content_type_crf_delta
        assert content_type_crf_delta("vlog") == 0

    def test_unknown_returns_0(self):
        from app.services.render.ffmpeg_helpers import content_type_crf_delta
        assert content_type_crf_delta("") == 0
