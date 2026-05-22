"""
Tests for Phase 4E.3: services/render/base_clip_renderer.py extraction.

Verifies:
- Import from new module works
- Backward-compat import from render_engine works
- Same object identity between modules
- Base clip invariants: no ass=, no drawtext=, no text_layers
- Uses TimelineMap.effective_speed for setpts/atempo
- BGM enabled path uses filter_complex
- BGM disabled path uses -vf
- NVENC semaphore is acquired/released on GPU path
- CPU fallback fires when NVENC raises
- Return metadata dict has required keys and correct types
"""

import time
import pytest
from unittest.mock import patch, MagicMock, call

from app.domain.timeline import TimelineMap
import app.services.render.base_clip_renderer as bcr_mod


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_timeline(speed: float = 1.15) -> TimelineMap:
    return TimelineMap(
        source_start=0.0,
        source_end=30.0,
        effective_speed=speed,
        trim_offset=0.0,
    )


_FAKE_SRC_META = {
    "duration": 30.0, "fps": 29.97, "width": 1920, "height": 1080, "has_audio": True,
}
_FAKE_OUT_META = {
    "duration": 26.1, "fps": 60.0, "width": 1080, "height": 1440, "has_audio": True,
}


def _call_bcr(
    timeline=None,
    speed: float = 1.15,
    input_has_audio: bool = True,
    codec: str = "libx264",
    **overrides,
):
    """Run render_base_clip with all external I/O mocked. Returns (result, cmds)."""
    if timeline is None:
        timeline = _make_timeline(speed)
    cmds: list[list] = []

    def _fake_run(cmd, **_kw):
        cmds.append(list(cmd))

    def _probe(path, **_kw):
        return _FAKE_OUT_META if "base_clip" in str(path) else _FAKE_SRC_META

    with (
        patch.object(bcr_mod, "_run_ffmpeg_with_retry", side_effect=_fake_run),
        patch.object(bcr_mod, "probe_video_metadata", side_effect=_probe),
        patch.object(bcr_mod, "_has_audio_stream", return_value=input_has_audio),
        patch.object(bcr_mod, "_resolve_codec", return_value=codec),
    ):
        kwargs = dict(
            input_path="/fake/cut.mp4",
            output_path="/fake/base_clip.mp4",
            timeline=timeline,
            motion_aware_crop=False,
            video_codec="h264",
            encoder_mode="cpu",
            output_fps=60,
        )
        kwargs.update(overrides)
        result = bcr_mod.render_base_clip(**kwargs)

    return result, cmds


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

class TestImportFromNewModule:
    def test_import_base_clip_renderer_package(self):
        from app.services.render import base_clip_renderer
        assert base_clip_renderer is not None

    def test_import_render_base_clip(self):
        from app.services.render.base_clip_renderer import render_base_clip
        assert callable(render_base_clip)


class TestBackwardCompatImport:
    def test_render_base_clip_via_render_engine(self):
        from app.services.render_engine import render_base_clip
        assert callable(render_base_clip)


class TestSameObject:
    def test_render_base_clip_is_same_object(self):
        import app.services.render.base_clip_renderer as bcr
        import app.services.render_engine as re_mod
        assert re_mod.render_base_clip is bcr.render_base_clip


# ---------------------------------------------------------------------------
# Base clip invariants — no overlay filters
# ---------------------------------------------------------------------------

class TestBaseClipNoOverlayFilters:
    def test_no_ass_filter(self):
        _, cmds = _call_bcr()
        assert cmds, "render_base_clip did not call _run_ffmpeg_with_retry"
        cmd_str = " ".join(str(a) for a in cmds[0])
        assert "ass=" not in cmd_str

    def test_no_drawtext_filter(self):
        _, cmds = _call_bcr()
        cmd_str = " ".join(str(a) for a in cmds[0])
        assert "drawtext=" not in cmd_str

    def test_no_text_layers(self):
        _, cmds = _call_bcr()
        cmd_str = " ".join(str(a) for a in cmds[0])
        assert "drawtext" not in cmd_str

    def test_subtitle_file_none_passed_to_motion_crop(self):
        """motion_aware_crop path: subtitle_file=None enforced."""
        with patch.object(bcr_mod, "render_motion_aware_crop") as mock_mac, \
             patch.object(bcr_mod, "probe_video_metadata", return_value=_FAKE_OUT_META), \
             patch.object(bcr_mod, "_resolve_codec", return_value="libx264"):
            bcr_mod.render_base_clip(
                input_path="/fake/cut.mp4",
                output_path="/fake/base_clip.mp4",
                timeline=_make_timeline(),
                motion_aware_crop=True,
            )
        call_kwargs = mock_mac.call_args[1]
        assert call_kwargs.get("subtitle_file") is None
        assert call_kwargs.get("title_text") is None
        assert call_kwargs.get("text_layers") is None


# ---------------------------------------------------------------------------
# Speed — uses TimelineMap.effective_speed
# ---------------------------------------------------------------------------

class TestBaseClipSpeed:
    def test_setpts_uses_timeline_speed(self):
        speed = 1.15
        _, cmds = _call_bcr(speed=speed)
        cmd_str = " ".join(str(a) for a in cmds[0])
        assert f"setpts=PTS/{speed:.4f}" in cmd_str

    def test_atempo_uses_timeline_speed(self):
        speed = 1.15
        _, cmds = _call_bcr(speed=speed, input_has_audio=True)
        cmd_str = " ".join(str(a) for a in cmds[0])
        assert f"atempo={speed:.4f}" in cmd_str

    def test_no_setpts_at_1x_speed(self):
        _, cmds = _call_bcr(speed=1.0)
        cmd_str = " ".join(str(a) for a in cmds[0])
        assert "setpts=PTS/" not in cmd_str

    def test_no_atempo_at_1x_speed(self):
        _, cmds = _call_bcr(speed=1.0, input_has_audio=True)
        cmd_str = " ".join(str(a) for a in cmds[0])
        assert "atempo=" not in cmd_str

    def test_timeline_speed_clamped(self):
        tl = TimelineMap(source_start=0.0, source_end=30.0, effective_speed=2.5, trim_offset=0.0)
        assert tl.effective_speed == pytest.approx(1.5)
        _, cmds = _call_bcr(timeline=tl)
        cmd_str = " ".join(str(a) for a in cmds[0])
        assert "setpts=PTS/1.5000" in cmd_str


# ---------------------------------------------------------------------------
# fps= is the last video filter
# ---------------------------------------------------------------------------

class TestBaseClipFpsLast:
    def test_fps_is_last_video_filter(self):
        _, cmds = _call_bcr()
        cmd = cmds[0]
        vf_idx = next((i + 1 for i, a in enumerate(cmd) if a == "-vf"), None)
        assert vf_idx is not None, "No -vf flag in command"
        vf_chain = cmd[vf_idx]
        last_filter = vf_chain.split(",")[-1]
        assert last_filter.startswith("fps="), f"Last filter must be fps=, got: {last_filter!r}"


# ---------------------------------------------------------------------------
# BGM paths
# ---------------------------------------------------------------------------

class TestBaseClipBgm:
    def test_bgm_disabled_uses_vf_flag(self):
        _, cmds = _call_bcr(reup_bgm_enable=False)
        cmd = cmds[0]
        assert "-vf" in cmd
        assert "-filter_complex" not in cmd

    def test_bgm_invalid_path_no_stream_loop(self):
        _, cmds = _call_bcr(reup_bgm_enable=True, reup_bgm_path="/nonexistent/bgm.mp3")
        assert "-stream_loop" not in cmds[0]

    def test_bgm_enabled_uses_filter_complex(self, tmp_path):
        bgm = tmp_path / "bgm.mp3"
        bgm.write_bytes(b"fake")
        _, cmds = _call_bcr(reup_bgm_enable=True, reup_bgm_path=str(bgm))
        cmd = cmds[0]
        assert "-filter_complex" in cmd
        assert "-vf" not in cmd

    def test_bgm_filter_complex_contains_amix(self, tmp_path):
        bgm = tmp_path / "bgm.mp3"
        bgm.write_bytes(b"fake")
        _, cmds = _call_bcr(reup_bgm_enable=True, reup_bgm_path=str(bgm))
        cmd = cmds[0]
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert "amix" in fc or "sidechaincompress" in fc

    def test_bgm_atempo_in_filter_complex_when_speed_ne_1(self, tmp_path):
        bgm = tmp_path / "bgm.mp3"
        bgm.write_bytes(b"fake")
        speed = 1.15
        _, cmds = _call_bcr(speed=speed, reup_bgm_enable=True, reup_bgm_path=str(bgm))
        cmd = cmds[0]
        fc = cmd[cmd.index("-filter_complex") + 1]
        assert f"atempo={speed:.4f}" in fc


# ---------------------------------------------------------------------------
# NVENC semaphore + CPU fallback
# ---------------------------------------------------------------------------

class TestBaseClipNvenc:
    def test_nvenc_semaphore_acquired_for_gpu_codec(self):
        """When codec resolves to h264_nvenc, NVENC_SEMAPHORE is used."""
        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(bcr_mod, "_resolve_codec", return_value="h264_nvenc"), \
             patch.object(bcr_mod, "_run_ffmpeg_with_retry"), \
             patch.object(bcr_mod, "probe_video_metadata", return_value=_FAKE_OUT_META), \
             patch.object(bcr_mod, "_has_audio_stream", return_value=True), \
             patch.object(bcr_mod, "NVENC_SEMAPHORE", sem_mock):
            bcr_mod.render_base_clip(
                input_path="/fake/cut.mp4",
                output_path="/fake/base_clip.mp4",
                timeline=_make_timeline(),
                motion_aware_crop=False,
            )
        sem_mock.__enter__.assert_called_once()
        sem_mock.__exit__.assert_called_once()

    def test_cpu_fallback_on_nvenc_failure(self):
        """NVENC raises → second _run_ffmpeg_with_retry call with libx264."""
        call_count = {"n": 0}

        def _side_effect(cmd, **_kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("NVENC out of memory")

        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(bcr_mod, "_resolve_codec", return_value="h264_nvenc"), \
             patch.object(bcr_mod, "_run_ffmpeg_with_retry", side_effect=_side_effect), \
             patch.object(bcr_mod, "probe_video_metadata", return_value=_FAKE_OUT_META), \
             patch.object(bcr_mod, "_has_audio_stream", return_value=True), \
             patch.object(bcr_mod, "NVENC_SEMAPHORE", sem_mock):
            bcr_mod.render_base_clip(
                input_path="/fake/cut.mp4",
                output_path="/fake/base_clip.mp4",
                timeline=_make_timeline(),
                motion_aware_crop=False,
            )
        assert call_count["n"] == 2, "Expected two FFmpeg calls: GPU attempt + CPU fallback"

    def test_cpu_only_no_semaphore(self):
        """CPU codec → NVENC_SEMAPHORE is never entered."""
        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(bcr_mod, "_resolve_codec", return_value="libx264"), \
             patch.object(bcr_mod, "_run_ffmpeg_with_retry"), \
             patch.object(bcr_mod, "probe_video_metadata", return_value=_FAKE_OUT_META), \
             patch.object(bcr_mod, "_has_audio_stream", return_value=True), \
             patch.object(bcr_mod, "NVENC_SEMAPHORE", sem_mock):
            bcr_mod.render_base_clip(
                input_path="/fake/cut.mp4",
                output_path="/fake/base_clip.mp4",
                timeline=_make_timeline(),
                motion_aware_crop=False,
            )
        sem_mock.__enter__.assert_not_called()


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------

class TestBaseClipReturnValue:
    def test_returns_dict_with_all_keys(self):
        result, _ = _call_bcr()
        for key in ("path", "duration", "fps", "width", "height", "has_audio", "created_at"):
            assert key in result, f"Missing key '{key}'"

    def test_path_matches_output_path(self):
        result, _ = _call_bcr()
        assert result["path"] == "/fake/base_clip.mp4"

    def test_duration_is_float(self):
        result, _ = _call_bcr()
        assert isinstance(result["duration"], float)

    def test_has_audio_is_bool(self):
        result, _ = _call_bcr()
        assert isinstance(result["has_audio"], bool)

    def test_created_at_is_recent(self):
        before = time.time()
        result, _ = _call_bcr()
        after = time.time()
        assert before <= result["created_at"] <= after

    def test_metadata_sourced_from_output_probe(self):
        result, _ = _call_bcr()
        assert result["duration"] == pytest.approx(_FAKE_OUT_META["duration"])
        assert result["fps"] == pytest.approx(_FAKE_OUT_META["fps"])
        assert result["width"] == _FAKE_OUT_META["width"]
        assert result["height"] == _FAKE_OUT_META["height"]
