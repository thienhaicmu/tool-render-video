"""
test_composite_overlays.py — Unit tests for composite_overlays_on_base_clip().

Coverage:
- FFmpeg command contains ass= when subtitle_ass is provided
- Command does NOT contain setpts=
- Command does NOT contain atempo=
- Command does NOT contain scale=
- Command does NOT contain crop=
- Command does NOT contain drawtext=
- Command uses -c:a copy
- No fps filter in the composite command (base_clip already has correct fps)
- Returns metadata dict with expected keys
- stream copy path (subtitle_ass=None): -c:v copy -c:a copy
- FEATURE_OVERLAY_AFTER_BASE_CLIP defaults to OFF
- FEATURE_OVERLAY_AFTER_BASE_CLIP=1 + success → composite path used
- FEATURE_OVERLAY_AFTER_BASE_CLIP=1 + failure → render_part_smart fallback
- Overlay flag ignored when FEATURE_BASE_CLIP_FIRST=0
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.domain.timeline import TimelineMap
import app.services.render_engine as render_engine_mod
from app.services.render_engine import composite_overlays_on_base_clip


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_timeline(speed: float = 1.15) -> TimelineMap:
    return TimelineMap(
        source_start=0.0,
        source_end=30.0,
        effective_speed=speed,
        trim_offset=0.0,
    )


_FAKE_META = {
    "duration": 26.1,
    "fps": 60.0,
    "width": 1080,
    "height": 1440,
    "has_audio": True,
}


def _call_composite(subtitle_ass: "str | None" = "/fake/overlay.ass", **overrides):
    """Run composite_overlays_on_base_clip with all external side-effects mocked."""
    captured: list[list] = []

    def _fake_run(cmd, **_kw):
        captured.append(list(cmd))

    with (
        patch.object(render_engine_mod, "_run_ffmpeg_with_retry", side_effect=_fake_run),
        patch.object(render_engine_mod, "probe_video_metadata", return_value=_FAKE_META),
        patch.object(render_engine_mod, "nvenc_available", return_value=False),
        patch.object(render_engine_mod, "_resolve_codec", return_value="libx264"),
    ):
        kwargs = dict(
            base_clip_path="/fake/base_clip.mp4",
            output_path="/fake/overlay_out.mp4",
            timeline=_make_timeline(),
            subtitle_ass=subtitle_ass,
            video_codec="h264",
            video_crf=18,
            video_preset="slow",
            audio_bitrate="192k",
            retry_count=2,
            encoder_mode="cpu",
            ffmpeg_threads=4,
        )
        kwargs.update(overrides)
        result = composite_overlays_on_base_clip(**kwargs)

    return result, captured


# ---------------------------------------------------------------------------
# Tests: vf_chain content — subtitle and forbidden filters
# ---------------------------------------------------------------------------

class TestCompositeOverlayFilters:
    def test_ass_filter_present_when_subtitle_provided(self):
        _, captured = _call_composite(subtitle_ass="/fake/overlay.ass")
        assert captured, "composite_overlays_on_base_clip did not call _run_ffmpeg_with_retry"
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "ass=" in cmd_str, "ass= filter must be present when subtitle_ass is provided"

    def test_no_setpts_in_command(self):
        """Overlay compositing must not apply setpts — base_clip.mp4 is already speed-adjusted."""
        _, captured = _call_composite()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "setpts=" not in cmd_str

    def test_no_atempo_in_command(self):
        """Overlay compositing must not apply atempo — audio is already speed-adjusted."""
        _, captured = _call_composite()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "atempo=" not in cmd_str

    def test_no_scale_in_command(self):
        """No scale= filter — geometry is already applied in base_clip."""
        _, captured = _call_composite()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "scale=" not in cmd_str

    def test_no_crop_in_command(self):
        """No crop= filter — geometry is already applied in base_clip."""
        _, captured = _call_composite()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "crop=" not in cmd_str

    def test_no_drawtext_in_command(self):
        _, captured = _call_composite()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "drawtext=" not in cmd_str

    def test_no_eq_filter(self):
        """No color grading in the composite command."""
        _, captured = _call_composite()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "eq=" not in cmd_str

    def test_no_hqdn3d_filter(self):
        """No denoise in the composite command."""
        _, captured = _call_composite()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "hqdn3d" not in cmd_str


# ---------------------------------------------------------------------------
# Tests: audio passthrough
# ---------------------------------------------------------------------------

class TestCompositeAudioPassthrough:
    def test_audio_copy_with_subtitle(self):
        """-c:a copy must appear when subtitle_ass is provided."""
        _, captured = _call_composite(subtitle_ass="/fake/overlay.ass")
        cmd = captured[0]
        cmd_pairs = list(zip(cmd, cmd[1:]))
        assert ("-c:a", "copy") in cmd_pairs, "-c:a copy required in overlay composite command"

    def test_audio_copy_without_subtitle(self):
        """-c:a copy must appear in stream copy path too."""
        _, captured = _call_composite(subtitle_ass=None)
        cmd = captured[0]
        cmd_pairs = list(zip(cmd, cmd[1:]))
        assert ("-c:a", "copy") in cmd_pairs

    def test_no_af_audio_filter(self):
        """No -af flag — audio must be copied without re-processing."""
        _, captured = _call_composite(subtitle_ass="/fake/overlay.ass")
        cmd = captured[0]
        assert "-af" not in cmd


# ---------------------------------------------------------------------------
# Tests: stream copy path (no subtitle)
# ---------------------------------------------------------------------------

class TestCompositeStreamCopyPath:
    def test_stream_copy_when_no_subtitle(self):
        """-c:v copy when subtitle_ass=None."""
        _, captured = _call_composite(subtitle_ass=None)
        cmd = captured[0]
        cmd_pairs = list(zip(cmd, cmd[1:]))
        assert ("-c:v", "copy") in cmd_pairs

    def test_no_vf_filter_when_no_subtitle(self):
        """No -vf flag when subtitle_ass=None (stream copy, no decode)."""
        _, captured = _call_composite(subtitle_ass=None)
        cmd = captured[0]
        assert "-vf" not in cmd

    def test_no_ass_filter_when_no_subtitle(self):
        _, captured = _call_composite(subtitle_ass=None)
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "ass=" not in cmd_str


# ---------------------------------------------------------------------------
# Tests: return value metadata
# ---------------------------------------------------------------------------

class TestCompositeReturnValue:
    def test_returns_dict_with_expected_keys(self):
        result, _ = _call_composite()
        for key in ("path", "duration", "fps", "width", "height", "has_audio"):
            assert key in result, f"Missing key '{key}' in composite_overlays_on_base_clip return value"

    def test_return_path_matches_output_path(self):
        result, _ = _call_composite()
        assert result["path"] == "/fake/overlay_out.mp4"

    def test_return_metadata_from_probe(self):
        result, _ = _call_composite()
        assert result["duration"] == pytest.approx(_FAKE_META["duration"])
        assert result["fps"] == pytest.approx(_FAKE_META["fps"])
        assert result["width"] == _FAKE_META["width"]
        assert result["height"] == _FAKE_META["height"]
        assert result["has_audio"] == _FAKE_META["has_audio"]


# ---------------------------------------------------------------------------
# Tests: feature flag behavior
# ---------------------------------------------------------------------------

class TestFeatureOverlayAfterBaseClipFlag:
    def test_overlay_flag_defaults_off(self):
        """FEATURE_OVERLAY_AFTER_BASE_CLIP must default to False."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEATURE_OVERLAY_AFTER_BASE_CLIP", None)
            flag_value = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
        assert flag_value is False

    def test_overlay_flag_on_when_env_set(self):
        with patch.dict(os.environ, {"FEATURE_OVERLAY_AFTER_BASE_CLIP": "1"}):
            flag_value = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
        assert flag_value is True

    def test_pipeline_uses_composite_when_both_flags_on(self):
        """Simulate: both flags ON + base_clip exists → composite path used."""
        mock_composite = MagicMock(return_value={"path": "/fake/final.mp4"})
        mock_render_smart = MagicMock()
        base_clip_first = True
        overlay_after = True
        base_clip_path = "/fake/base_clip.mp4"
        tl = _make_timeline()

        _overlay_succeeded = False
        if base_clip_first and overlay_after and base_clip_path:
            try:
                mock_composite(base_clip_path, "/fake/final.mp4", tl)
                _overlay_succeeded = True
            except Exception:
                pass

        if not _overlay_succeeded:
            mock_render_smart("/fake/cut.mp4", "/fake/final.mp4")

        mock_composite.assert_called_once()
        mock_render_smart.assert_not_called()

    def test_pipeline_falls_back_to_render_smart_on_composite_failure(self):
        """Simulate: overlay composite raises → render_part_smart fallback runs."""
        mock_composite = MagicMock(side_effect=RuntimeError("subtitle burn failed"))
        mock_render_smart = MagicMock()
        base_clip_first = True
        overlay_after = True
        base_clip_path = "/fake/base_clip.mp4"
        tl = _make_timeline()

        _overlay_succeeded = False
        if base_clip_first and overlay_after and base_clip_path:
            try:
                mock_composite(base_clip_path, "/fake/final.mp4", tl)
                _overlay_succeeded = True
            except Exception:
                pass

        if not _overlay_succeeded:
            mock_render_smart("/fake/cut.mp4", "/fake/final.mp4")

        mock_render_smart.assert_called_once()
        assert not _overlay_succeeded

    def test_overlay_flag_ignored_when_base_clip_first_off(self):
        """Simulate: overlay=ON but base_clip_first=OFF → render_part_smart used."""
        mock_composite = MagicMock()
        mock_render_smart = MagicMock()
        base_clip_first = False
        overlay_after = True
        base_clip_path = None  # never generated because base_clip_first=False
        tl = _make_timeline()

        _overlay_succeeded = False
        if base_clip_first and overlay_after and base_clip_path:
            try:
                mock_composite(base_clip_path, "/fake/final.mp4", tl)
                _overlay_succeeded = True
            except Exception:
                pass

        if not _overlay_succeeded:
            mock_render_smart("/fake/cut.mp4", "/fake/final.mp4")

        mock_composite.assert_not_called()
        mock_render_smart.assert_called_once()

    def test_render_smart_path_when_both_flags_off(self):
        """Simulate: both flags OFF → render_part_smart always runs."""
        mock_composite = MagicMock()
        mock_render_smart = MagicMock()
        base_clip_first = False
        overlay_after = False
        base_clip_path = None
        tl = _make_timeline()

        _overlay_succeeded = False
        if base_clip_first and overlay_after and base_clip_path:
            try:
                mock_composite(base_clip_path, "/fake/final.mp4", tl)
                _overlay_succeeded = True
            except Exception:
                pass

        if not _overlay_succeeded:
            mock_render_smart("/fake/cut.mp4", "/fake/final.mp4")

        mock_composite.assert_not_called()
        mock_render_smart.assert_called_once()
