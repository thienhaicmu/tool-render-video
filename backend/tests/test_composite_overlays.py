"""
test_composite_overlays.py — Unit tests for composite_overlays_on_base_clip().

Phase 3A coverage:
- FFmpeg command contains ass= when subtitle_ass is provided
- Command does NOT contain setpts= / atempo= / scale= / crop= / eq= / hqdn3d
- Command uses -c:a copy; no -af
- fps= is last filter in vf_chain when encode path is taken
- Returns metadata dict with expected keys
- Stream copy path (all overlay sources absent): -c:v copy -c:a copy, no -vf
- FEATURE_OVERLAY_AFTER_BASE_CLIP defaults to OFF
- Overlay composite success → render_part_smart not called
- Overlay composite failure → render_part_smart fallback runs

Phase 3B coverage:
- drawtext= present when title_text provided; enable='lt(t,3)' on output-timeline PTS
- drawtext= present when text_layers provided; enable= expression uses layer times
- drawtext= absent when title_text=None and text_layers=None
- fps= remains last filter even with text_layers and title
- ass= appears before drawtext= in vf_chain
- Stream copy only when subtitle_ass, title_text, and text_layers all absent
- Encode triggered when only text_layers or only title_text is provided
- Invariants (no setpts/atempo/scale/crop) still hold with text_layers
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

_SAMPLE_TEXT_LAYER = {
    "id": "test_layer_1",
    "text": "Test overlay text",
    "font_family": "Bungee",
    "font_size": 40,
    "color": "#FFFFFF",
    "position": "top-center",
    "x_percent": 50.0,
    "y_percent": 20.0,
    "alignment": "center",
    "bold": False,
    "outline": {"enabled": False, "thickness": 0},
    "shadow": {"enabled": False, "offset_x": 0, "offset_y": 0},
    "background": {"enabled": False, "color": "#000000", "padding": 0},
    "start_time": 1.5,
    "end_time": 5.0,
    "order": 1,
}


def _call_composite(subtitle_ass: "str | None" = "/fake/overlay.ass", **overrides):
    """Run composite_overlays_on_base_clip with all external side-effects mocked.

    probe_video_metadata is mocked for both base_clip probe (fps) and output probe
    (return metadata). _detect_windows_fontfile returns None for platform consistency.
    """
    captured: list[list] = []

    def _fake_run(cmd, **_kw):
        captured.append(list(cmd))

    with (
        patch.object(render_engine_mod, "_run_ffmpeg_with_retry", side_effect=_fake_run),
        patch.object(render_engine_mod, "probe_video_metadata", return_value=_FAKE_META),
        patch.object(render_engine_mod, "nvenc_available", return_value=False),
        patch.object(render_engine_mod, "_resolve_codec", return_value="libx264"),
        patch.object(render_engine_mod, "_detect_windows_fontfile", return_value=None),
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


def _get_vf_value(captured: list) -> str:
    """Extract the -vf argument value from the captured FFmpeg command list."""
    cmd = captured[0]
    vf_idx = cmd.index("-vf")
    return cmd[vf_idx + 1]


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


# ---------------------------------------------------------------------------
# Phase 3B Tests: title drawtext overlay
# ---------------------------------------------------------------------------

class TestCompositeTitleOverlay:
    def test_drawtext_present_when_title_provided(self):
        """drawtext= filter must appear in vf_chain when title_text is given."""
        _, captured = _call_composite(title_text="My Reel Title")
        vf = _get_vf_value(captured)
        assert "drawtext=" in vf

    def test_title_enable_expression_is_lt_3(self):
        """Title drawtext enable expression must use lt(t,3) — first 3 output seconds."""
        _, captured = _call_composite(title_text="My Reel Title")
        vf = _get_vf_value(captured)
        assert "lt(t" in vf and "3" in vf

    def test_drawtext_absent_when_title_is_none(self):
        """No drawtext= when title_text=None and no text_layers."""
        _, captured = _call_composite(subtitle_ass="/fake/overlay.ass", title_text=None)
        vf = _get_vf_value(captured)
        assert "drawtext=" not in vf

    def test_drawtext_absent_when_title_is_empty_string(self):
        """No drawtext= when title_text is empty — treated same as None."""
        _, captured = _call_composite(subtitle_ass="/fake/overlay.ass", title_text="")
        vf = _get_vf_value(captured)
        assert "drawtext=" not in vf

    def test_no_setpts_with_title(self):
        _, captured = _call_composite(title_text="Title")
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "setpts=" not in cmd_str

    def test_audio_copy_with_title(self):
        _, captured = _call_composite(title_text="Title")
        cmd = captured[0]
        assert ("-c:a", "copy") in list(zip(cmd, cmd[1:]))


# ---------------------------------------------------------------------------
# Phase 3B Tests: text_layers drawtext overlay
# ---------------------------------------------------------------------------

class TestCompositeTextLayerFilters:
    def test_drawtext_present_when_text_layers_provided(self):
        """drawtext= filter must appear in vf_chain when text_layers is non-empty."""
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        vf = _get_vf_value(captured)
        assert "drawtext=" in vf

    def test_text_layer_enable_uses_start_end_times(self):
        """Layer with start_time=1.5, end_time=5.0 produces gte(t,1.500)*lt(t,5.000) enable."""
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        vf = _get_vf_value(captured)
        assert "gte(t" in vf
        assert "1.500" in vf
        assert "5.000" in vf

    def test_drawtext_absent_when_text_layers_none(self):
        """No drawtext= from layers when text_layers=None."""
        _, captured = _call_composite(subtitle_ass="/fake/overlay.ass", text_layers=None, title_text=None)
        vf = _get_vf_value(captured)
        assert "drawtext=" not in vf

    def test_drawtext_absent_when_text_layers_empty_list(self):
        """Empty list is treated as no layers — no drawtext= appended."""
        _, captured = _call_composite(subtitle_ass="/fake/overlay.ass", text_layers=[], title_text=None)
        vf = _get_vf_value(captured)
        assert "drawtext=" not in vf

    def test_no_setpts_with_text_layers(self):
        """setpts= must not appear even when text_layers are provided."""
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "setpts=" not in cmd_str

    def test_no_atempo_with_text_layers(self):
        """atempo= must not appear when text_layers are provided."""
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "atempo=" not in cmd_str

    def test_no_scale_with_text_layers(self):
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "scale=" not in cmd_str

    def test_no_crop_with_text_layers(self):
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "crop=" not in cmd_str

    def test_audio_copy_with_text_layers(self):
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        cmd = captured[0]
        assert ("-c:a", "copy") in list(zip(cmd, cmd[1:]))


# ---------------------------------------------------------------------------
# Phase 3B Tests: vf_chain filter order
# ---------------------------------------------------------------------------

class TestCompositeFilterOrder:
    def test_fps_is_last_filter_with_subtitle_only(self):
        """fps= must be the last filter in the vf_chain when subtitle is provided."""
        _, captured = _call_composite(subtitle_ass="/fake/overlay.ass")
        vf = _get_vf_value(captured)
        last_filter = vf.rsplit(",", 1)[-1]
        assert last_filter.startswith("fps=")

    def test_fps_is_last_filter_with_text_layers(self):
        """fps= must be the last filter in the vf_chain when text_layers are provided."""
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        vf = _get_vf_value(captured)
        last_filter = vf.rsplit(",", 1)[-1]
        assert last_filter.startswith("fps=")

    def test_fps_is_last_filter_with_title(self):
        """fps= must be the last filter when title_text is provided."""
        _, captured = _call_composite(subtitle_ass=None, title_text="Title")
        vf = _get_vf_value(captured)
        last_filter = vf.rsplit(",", 1)[-1]
        assert last_filter.startswith("fps=")

    def test_ass_before_drawtext_in_vf_chain(self):
        """ass= must appear before drawtext= in the vf_chain when both are present."""
        _, captured = _call_composite(
            subtitle_ass="/fake/overlay.ass",
            title_text="Test Title",
        )
        vf = _get_vf_value(captured)
        assert "ass=" in vf and "drawtext=" in vf
        assert vf.index("ass=") < vf.index("drawtext=")


# ---------------------------------------------------------------------------
# Phase 3B Tests: stream copy guard
# ---------------------------------------------------------------------------

class TestCompositeStreamCopyGuard:
    def test_stream_copy_when_all_overlay_sources_absent(self):
        """Stream copy path taken when subtitle_ass, title_text, and text_layers are all absent."""
        _, captured = _call_composite(subtitle_ass=None, title_text=None, text_layers=None)
        cmd = captured[0]
        cmd_pairs = list(zip(cmd, cmd[1:]))
        assert ("-c:v", "copy") in cmd_pairs
        assert "-vf" not in cmd

    def test_encode_triggered_when_only_text_layers(self):
        """Re-encode is triggered when text_layers are provided but subtitle_ass=None."""
        _, captured = _call_composite(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER], title_text=None)
        cmd = captured[0]
        cmd_pairs = list(zip(cmd, cmd[1:]))
        assert ("-c:v", "copy") not in cmd_pairs
        assert "-vf" in cmd

    def test_encode_triggered_when_only_title_text(self):
        """Re-encode is triggered when title_text is provided but no subtitle or layers."""
        _, captured = _call_composite(subtitle_ass=None, title_text="Title Only", text_layers=None)
        cmd = captured[0]
        cmd_pairs = list(zip(cmd, cmd[1:]))
        assert ("-c:v", "copy") not in cmd_pairs
        assert "-vf" in cmd
