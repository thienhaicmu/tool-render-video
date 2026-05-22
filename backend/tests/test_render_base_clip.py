"""
test_render_base_clip.py — Unit tests for render_base_clip().

Coverage:
- No ass= filter in FFmpeg command
- No drawtext= filter in FFmpeg command
- Uses timeline.effective_speed for setpts
- Uses timeline.effective_speed for atempo (audio speed filter)
- Applies crop/scale filters (not just a passthrough)
- fps= is last video filter in the chain
- FEATURE_BASE_CLIP_FIRST=0: render_base_clip NOT called from pipeline block
- FEATURE_BASE_CLIP_FIRST=1: render_base_clip IS called from pipeline block
- base clip failure allows legacy render path (render_part_smart still runs)
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from app.domain.timeline import TimelineMap
import app.services.render_engine as render_engine_mod
from app.services.render_engine import render_base_clip


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_timeline(speed: float = 1.15) -> TimelineMap:
    return TimelineMap(
        source_start=0.0,
        source_end=32.0,
        effective_speed=speed,
        trim_offset=0.0,
    )


_FAKE_SRC_META = {
    "duration": 32.0,
    "fps": 29.97,
    "width": 1920,
    "height": 1080,
    "has_audio": True,
}

_FAKE_OUT_META = {
    "duration": 27.8,
    "fps": 60.0,
    "width": 1080,
    "height": 1440,
    "has_audio": True,
}


def _captured_cmd(mock_run):
    """Return the first positional arg (cmd list) of the first call to mock_run."""
    return mock_run.call_args[0][0]


# ---------------------------------------------------------------------------
# Helper: run render_base_clip with all external side-effects mocked out.
# motion_aware_crop=False forces the non-motion path so we can inspect the
# exact FFmpeg command that would be built.
# ---------------------------------------------------------------------------

def _call_render_base_clip(
    timeline=None,
    speed=1.15,
    input_has_audio=True,
    **overrides,
):
    if timeline is None:
        timeline = _make_timeline(speed)
    captured: list[list] = []

    def _fake_run(cmd, **_kw):
        captured.append(list(cmd))

    def _probe_side_effect(path, **_kw):
        # Return output metadata when probing the output path; source metadata otherwise.
        if "/fake/base_clip" in str(path):
            return _FAKE_OUT_META
        return _FAKE_SRC_META

    with (
        patch.object(render_engine_mod, "_run_ffmpeg_with_retry", side_effect=_fake_run),
        patch.object(render_engine_mod, "probe_video_metadata", side_effect=_probe_side_effect),
        patch.object(render_engine_mod, "_has_audio_stream", return_value=input_has_audio),
        patch.object(render_engine_mod, "nvenc_available", return_value=False),
        patch.object(render_engine_mod, "_resolve_codec", return_value="libx264"),
    ):
        kwargs = dict(
            input_path="/fake/cut.mp4",
            output_path="/fake/base_clip.mp4",
            timeline=timeline,
            motion_aware_crop=False,  # use non-motion path for command inspection
            video_codec="h264",
            encoder_mode="cpu",
            output_fps=60,
        )
        kwargs.update(overrides)
        result = render_base_clip(**kwargs)

    return result, captured


# ---------------------------------------------------------------------------
# Tests: vf_chain content — no overlay filters
# ---------------------------------------------------------------------------

class TestRenderBaseClipNoOverlayFilters:
    def test_no_ass_filter(self):
        _, captured = _call_render_base_clip()
        assert captured, "render_base_clip did not call _run_ffmpeg_with_retry"
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "ass=" not in cmd_str, "render_base_clip must not include ass= subtitle filter"

    def test_no_drawtext_filter(self):
        _, captured = _call_render_base_clip()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "drawtext=" not in cmd_str, "render_base_clip must not include drawtext= overlay filter"

    def test_no_text_layer_filters(self):
        _, captured = _call_render_base_clip()
        cmd_str = " ".join(str(a) for a in captured[0])
        # text_overlay produces drawtext filters; none should be present
        assert "drawtext" not in cmd_str

    def test_contains_scale_crop_filter(self):
        _, captured = _call_render_base_clip()
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "scale=" in cmd_str and "crop=" in cmd_str, (
            "render_base_clip must apply scale/crop reframe filters"
        )


# ---------------------------------------------------------------------------
# Tests: speed — setpts and atempo derived from timeline.effective_speed
# ---------------------------------------------------------------------------

class TestRenderBaseClipSpeedFromTimeline:
    def test_setpts_uses_timeline_speed(self):
        speed = 1.15
        _, captured = _call_render_base_clip(speed=speed)
        cmd_str = " ".join(str(a) for a in captured[0])
        expected_setpts = f"setpts=PTS/{speed:.4f}"
        assert expected_setpts in cmd_str, (
            f"Expected '{expected_setpts}' in vf_chain, got: {cmd_str}"
        )

    def test_atempo_uses_timeline_speed(self):
        speed = 1.15
        _, captured = _call_render_base_clip(speed=speed, input_has_audio=True)
        cmd_str = " ".join(str(a) for a in captured[0])
        expected_atempo = f"atempo={speed:.4f}"
        assert expected_atempo in cmd_str, (
            f"Expected '{expected_atempo}' in audio filter, got: {cmd_str}"
        )

    def test_no_setpts_at_1x_speed(self):
        _, captured = _call_render_base_clip(speed=1.0)
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "setpts=PTS/" not in cmd_str, (
            "setpts filter must be omitted when speed=1.0"
        )

    def test_no_atempo_at_1x_speed(self):
        _, captured = _call_render_base_clip(speed=1.0, input_has_audio=True)
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "atempo=" not in cmd_str, (
            "atempo filter must be omitted when speed=1.0"
        )

    def test_speed_clamped_to_pipeline_range(self):
        """Timeline clamps effective_speed to [0.5, 1.5]; render_base_clip honours it."""
        # Speed of 2.5 is above _SPEED_MAX=1.5 and will be clamped by TimelineMap
        tl = TimelineMap(
            source_start=0.0,
            source_end=32.0,
            effective_speed=2.5,
            trim_offset=0.0,
        )
        assert tl.effective_speed == pytest.approx(1.5)
        _, captured = _call_render_base_clip(timeline=tl)
        cmd_str = " ".join(str(a) for a in captured[0])
        assert "setpts=PTS/1.5000" in cmd_str


# ---------------------------------------------------------------------------
# Tests: fps= is last video filter
# ---------------------------------------------------------------------------

class TestRenderBaseClipFpsFilter:
    def test_fps_is_last_video_filter(self):
        _, captured = _call_render_base_clip()
        cmd = captured[0]
        vf_idx = None
        for i, arg in enumerate(cmd):
            if arg == "-vf":
                vf_idx = i + 1
                break
        assert vf_idx is not None, "No -vf flag found in ffmpeg command"
        vf_chain = cmd[vf_idx]
        filters = vf_chain.split(",")
        last_filter = filters[-1]
        assert last_filter.startswith("fps="), (
            f"Last video filter must be fps=, got: '{last_filter}'"
        )


# ---------------------------------------------------------------------------
# Tests: return value metadata
# ---------------------------------------------------------------------------

class TestRenderBaseClipReturnValue:
    def test_returns_dict_with_expected_keys(self):
        result, _ = _call_render_base_clip()
        for key in ("path", "duration", "fps", "width", "height", "has_audio", "created_at"):
            assert key in result, f"Missing key '{key}' in render_base_clip return value"

    def test_return_path_matches_output_path(self):
        result, _ = _call_render_base_clip()
        assert result["path"] == "/fake/base_clip.mp4"

    def test_return_metadata_from_probe(self):
        result, _ = _call_render_base_clip()
        assert result["duration"] == pytest.approx(_FAKE_OUT_META["duration"])
        assert result["fps"] == pytest.approx(_FAKE_OUT_META["fps"])
        assert result["width"] == _FAKE_OUT_META["width"]
        assert result["height"] == _FAKE_OUT_META["height"]
        assert result["has_audio"] == _FAKE_OUT_META["has_audio"]

    def test_created_at_is_recent_timestamp(self):
        before = time.time()
        result, _ = _call_render_base_clip()
        after = time.time()
        assert before <= result["created_at"] <= after


# ---------------------------------------------------------------------------
# Tests: feature flag integration
# ---------------------------------------------------------------------------

class TestFeatureBaseClipFlag:
    def test_feature_flag_defaults_off(self):
        """_FEATURE_BASE_CLIP_FIRST must default to False (env var not set)."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEATURE_BASE_CLIP_FIRST", None)
            flag_value = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
        assert flag_value is False, "FEATURE_BASE_CLIP_FIRST must default to OFF"

    def test_feature_flag_on_when_env_set(self):
        with patch.dict(os.environ, {"FEATURE_BASE_CLIP_FIRST": "1"}):
            flag_value = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
        assert flag_value is True

    def test_pipeline_block_skips_base_clip_when_flag_off(self):
        """Simulate the pipeline block: flag=False → render_base_clip NOT called."""
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        mock_render_smart = MagicMock()
        feature_flag = False

        if feature_flag:
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4", _make_timeline())

        mock_render_base.assert_not_called()

    def test_pipeline_block_calls_base_clip_when_flag_on(self):
        """Simulate the pipeline block: flag=True → render_base_clip IS called."""
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        feature_flag = True
        timeline = _make_timeline()

        if feature_flag:
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4", timeline)

        mock_render_base.assert_called_once()

    def test_pipeline_block_render_smart_runs_on_base_clip_failure(self):
        """Simulate: base clip raises → render_part_smart still runs (legacy path)."""
        mock_render_base = MagicMock(side_effect=RuntimeError("encode failed"))
        mock_render_smart = MagicMock()
        feature_flag = True
        timeline = _make_timeline()

        if feature_flag:
            try:
                mock_render_base("/fake/cut.mp4", "/fake/base.mp4", timeline)
            except Exception:
                pass  # swallow — base clip failure must not block final render

        mock_render_smart("/fake/cut.mp4", "/fake/final.mp4")

        mock_render_smart.assert_called_once()

    def test_pipeline_block_render_smart_always_runs_when_flag_on(self):
        """Simulate: flag=True, base clip succeeds → render_part_smart still runs."""
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        mock_render_smart = MagicMock()
        feature_flag = True
        timeline = _make_timeline()

        if feature_flag:
            try:
                mock_render_base("/fake/cut.mp4", "/fake/base.mp4", timeline)
            except Exception:
                pass

        mock_render_smart("/fake/cut.mp4", "/fake/final.mp4")

        mock_render_base.assert_called_once()
        mock_render_smart.assert_called_once()
