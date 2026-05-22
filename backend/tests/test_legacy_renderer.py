"""
Tests for Phase 4E.5: services/render/legacy_renderer.py extraction.

Verifies:
- Import from new module works
- Backward-compat import from render_engine works
- Same object identity between modules
- render_part signature unchanged
- render_part_smart signature unchanged
- ass= appears before setpts in vf_chain (legacy invariant)
- fps= is last filter in vf_chain
- setpts present when speed != 1.0
- atempo present when speed != 1.0
- setpts/atempo absent at speed=1.0
- no overlay flag logic inside render_part_smart body
- BGM path uses filter_complex when enabled with valid file
- BGM disabled path uses -vf flag
- loudnorm atempo present when enabled
- text_layers drawtext appears in vf_chain
- title drawtext appears in vf_chain
- NVENC semaphore acquired/released on GPU codec path
- CPU fallback fires when NVENC raises
- render_part_smart motion_crop fallback calls render_part on exception
- render_part_smart non-motion path delegates to render_part
"""

import inspect
import pytest
from unittest.mock import patch, MagicMock

import app.services.render.legacy_renderer as lr_mod


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FAKE_SRC_META = {
    "duration": 30.0, "fps": 29.97, "width": 1920, "height": 1080, "has_audio": True,
}

_SAMPLE_TEXT_LAYER = {
    "id": "layer_1",
    "text": "Hook text",
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
    "start_time": 0.0,
    "end_time": 3.0,
    "order": 1,
}


def _call_render_part(speed: float = 1.15, input_has_audio: bool = True, **overrides):
    """Run render_part with all external I/O mocked. Returns captured cmd list."""
    cmds: list[list] = []

    def _fake_run(cmd, **_kw):
        cmds.append(list(cmd))

    with (
        patch.object(lr_mod, "_run_ffmpeg_with_retry", side_effect=_fake_run),
        patch.object(lr_mod, "probe_video_metadata", return_value=_FAKE_SRC_META),
        patch.object(lr_mod, "_has_audio_stream", return_value=input_has_audio),
        patch.object(lr_mod, "_resolve_codec", return_value="libx264"),
        patch.object(lr_mod, "_resolve_fps", return_value=(60, "capped")),
        patch.object(lr_mod, "_detect_windows_fontfile", return_value=None),
        patch.object(lr_mod, "_get_custom_fonts_dir", return_value=None),
        patch.object(lr_mod, "_detect_windows_fonts_dir", return_value=None),
    ):
        kwargs = dict(
            input_path="/fake/cut.mp4",
            output_path="/fake/out.mp4",
            subtitle_ass=None,
            title_text=None,
            add_subtitle=False,
            add_title_overlay=False,
            motion_aware_crop=False,
            playback_speed=speed,
            encoder_mode="cpu",
            output_fps=60,
        )
        kwargs.update(overrides)
        lr_mod.render_part(**{k: v for k, v in kwargs.items()
                               if k in inspect.signature(lr_mod.render_part).parameters})

    return cmds


def _get_vf(cmds: list) -> str:
    cmd = cmds[0]
    return cmd[cmd.index("-vf") + 1]


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

class TestImportFromNewModule:
    def test_import_legacy_renderer_package(self):
        from app.services.render import legacy_renderer
        assert legacy_renderer is not None

    def test_import_render_part(self):
        from app.services.render.legacy_renderer import render_part
        assert callable(render_part)

    def test_import_render_part_smart(self):
        from app.services.render.legacy_renderer import render_part_smart
        assert callable(render_part_smart)


class TestBackwardCompatImport:
    def test_render_part_via_render_engine(self):
        from app.services.render_engine import render_part
        assert callable(render_part)

    def test_render_part_smart_via_render_engine(self):
        from app.services.render_engine import render_part_smart
        assert callable(render_part_smart)


class TestSameObject:
    def test_render_part_is_same_object(self):
        import app.services.render.legacy_renderer as lr
        import app.services.render_engine as re_mod
        assert re_mod.render_part is lr.render_part

    def test_render_part_smart_is_same_object(self):
        import app.services.render.legacy_renderer as lr
        import app.services.render_engine as re_mod
        assert re_mod.render_part_smart is lr.render_part_smart


# ---------------------------------------------------------------------------
# Signature checks
# ---------------------------------------------------------------------------

class TestSignatures:
    def test_render_part_has_subtitle_ass_param(self):
        sig = inspect.signature(lr_mod.render_part)
        assert "subtitle_ass" in sig.parameters

    def test_render_part_has_playback_speed_param(self):
        sig = inspect.signature(lr_mod.render_part)
        assert "playback_speed" in sig.parameters

    def test_render_part_has_text_layers_param(self):
        sig = inspect.signature(lr_mod.render_part)
        assert "text_layers" in sig.parameters

    def test_render_part_has_loudnorm_param(self):
        sig = inspect.signature(lr_mod.render_part)
        assert "loudnorm_enabled" in sig.parameters

    def test_render_part_has_reup_bgm_params(self):
        sig = inspect.signature(lr_mod.render_part)
        assert "reup_bgm_enable" in sig.parameters
        assert "reup_bgm_path" in sig.parameters
        assert "reup_bgm_gain" in sig.parameters

    def test_render_part_smart_has_motion_aware_crop_param(self):
        sig = inspect.signature(lr_mod.render_part_smart)
        assert "motion_aware_crop" in sig.parameters

    def test_render_part_smart_has_crop_cfg_override_param(self):
        sig = inspect.signature(lr_mod.render_part_smart)
        assert "crop_cfg_override" in sig.parameters

    def test_render_part_smart_has_fallback_flag_param(self):
        sig = inspect.signature(lr_mod.render_part_smart)
        assert "_fallback_flag" in sig.parameters


# ---------------------------------------------------------------------------
# vf_chain invariants: ass-before-setpts, fps last, speed filters
# ---------------------------------------------------------------------------

class TestRenderPartVfChain:
    def test_setpts_present_when_speed_ne_1(self):
        cmds = _call_render_part(speed=1.15)
        vf = _get_vf(cmds)
        assert "setpts=PTS/1.1500" in vf

    def test_setpts_absent_at_1x_speed(self):
        cmds = _call_render_part(speed=1.0)
        vf = _get_vf(cmds)
        assert "setpts=PTS/" not in vf

    def test_fps_is_last_filter(self):
        cmds = _call_render_part(speed=1.15)
        last = _get_vf(cmds).rsplit(",", 1)[-1]
        assert last.startswith("fps=")

    def test_fps_is_last_at_1x_speed(self):
        cmds = _call_render_part(speed=1.0)
        last = _get_vf(cmds).rsplit(",", 1)[-1]
        assert last.startswith("fps=")

    def test_ass_before_setpts(self):
        cmds = _call_render_part(
            speed=1.15,
            subtitle_ass="/fake/part.ass",
            add_subtitle=True,
        )
        vf = _get_vf(cmds)
        assert "ass=" in vf and "setpts=" in vf
        assert vf.index("ass=") < vf.index("setpts=")

    def test_ass_before_fps(self):
        cmds = _call_render_part(
            subtitle_ass="/fake/part.ass",
            add_subtitle=True,
        )
        vf = _get_vf(cmds)
        assert vf.index("ass=") < vf.rindex("fps=")

    def test_drawtext_present_when_title_provided(self):
        cmds = _call_render_part(
            title_text="My Title",
            add_title_overlay=True,
        )
        cmd_str = " ".join(cmds[0])
        assert "drawtext=" in cmd_str

    def test_drawtext_present_when_text_layers_provided(self):
        cmds = _call_render_part(text_layers=[_SAMPLE_TEXT_LAYER])
        cmd_str = " ".join(cmds[0])
        assert "drawtext=" in cmd_str

    def test_contains_scale_and_crop(self):
        cmds = _call_render_part()
        vf = _get_vf(cmds)
        assert "scale=" in vf
        assert "crop=" in vf


# ---------------------------------------------------------------------------
# Audio: atempo and loudnorm
# ---------------------------------------------------------------------------

class TestRenderPartAudio:
    def test_atempo_present_when_speed_ne_1(self):
        cmds = _call_render_part(speed=1.15, input_has_audio=True)
        cmd_str = " ".join(cmds[0])
        assert "atempo=1.1500" in cmd_str

    def test_atempo_absent_at_1x_speed(self):
        cmds = _call_render_part(speed=1.0, input_has_audio=True)
        cmd_str = " ".join(cmds[0])
        assert "atempo=" not in cmd_str

    def test_loudnorm_in_af_when_enabled(self):
        cmds = _call_render_part(loudnorm_enabled=True, input_has_audio=True)
        cmd_str = " ".join(cmds[0])
        assert "loudnorm" in cmd_str

    def test_no_af_when_no_audio(self):
        cmds = _call_render_part(input_has_audio=False)
        assert "-af" not in cmds[0]


# ---------------------------------------------------------------------------
# BGM paths
# ---------------------------------------------------------------------------

class TestRenderPartBgm:
    def test_bgm_disabled_uses_vf(self):
        cmds = _call_render_part(reup_bgm_enable=False)
        assert "-vf" in cmds[0]
        assert "-filter_complex" not in cmds[0]

    def test_bgm_invalid_path_no_stream_loop(self):
        cmds = _call_render_part(
            reup_bgm_enable=True,
            reup_bgm_path="/nonexistent/bgm.mp3",
        )
        assert "-stream_loop" not in cmds[0]

    def test_bgm_enabled_uses_filter_complex(self, tmp_path):
        bgm = tmp_path / "bgm.mp3"
        bgm.write_bytes(b"fake")
        cmds = _call_render_part(
            reup_bgm_enable=True,
            reup_bgm_path=str(bgm),
        )
        assert "-filter_complex" in cmds[0]
        assert "-vf" not in cmds[0]

    def test_bgm_filter_complex_contains_amix(self, tmp_path):
        bgm = tmp_path / "bgm.mp3"
        bgm.write_bytes(b"fake")
        cmds = _call_render_part(
            reup_bgm_enable=True,
            reup_bgm_path=str(bgm),
        )
        fc = cmds[0][cmds[0].index("-filter_complex") + 1]
        assert "amix" in fc or "sidechaincompress" in fc


# ---------------------------------------------------------------------------
# NVENC semaphore + CPU fallback (render_part)
# ---------------------------------------------------------------------------

class TestRenderPartNvenc:
    def test_nvenc_semaphore_acquired_for_gpu_codec(self):
        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(lr_mod, "_resolve_codec", return_value="h264_nvenc"), \
             patch.object(lr_mod, "_run_ffmpeg_with_retry"), \
             patch.object(lr_mod, "probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch.object(lr_mod, "_has_audio_stream", return_value=True), \
             patch.object(lr_mod, "_resolve_fps", return_value=(60, "capped")), \
             patch.object(lr_mod, "_detect_windows_fontfile", return_value=None), \
             patch.object(lr_mod, "_get_custom_fonts_dir", return_value=None), \
             patch.object(lr_mod, "_detect_windows_fonts_dir", return_value=None), \
             patch.object(lr_mod, "NVENC_SEMAPHORE", sem_mock):
            lr_mod.render_part(
                input_path="/fake/cut.mp4",
                output_path="/fake/out.mp4",
                subtitle_ass=None,
                title_text=None,
            )
        sem_mock.__enter__.assert_called_once()
        sem_mock.__exit__.assert_called_once()

    def test_cpu_fallback_on_nvenc_failure(self):
        call_count = {"n": 0}

        def _side(cmd, **_kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("NVENC out of memory")

        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(lr_mod, "_resolve_codec", return_value="h264_nvenc"), \
             patch.object(lr_mod, "_run_ffmpeg_with_retry", side_effect=_side), \
             patch.object(lr_mod, "probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch.object(lr_mod, "_has_audio_stream", return_value=True), \
             patch.object(lr_mod, "_resolve_fps", return_value=(60, "capped")), \
             patch.object(lr_mod, "_detect_windows_fontfile", return_value=None), \
             patch.object(lr_mod, "_get_custom_fonts_dir", return_value=None), \
             patch.object(lr_mod, "_detect_windows_fonts_dir", return_value=None), \
             patch.object(lr_mod, "NVENC_SEMAPHORE", sem_mock):
            lr_mod.render_part(
                input_path="/fake/cut.mp4",
                output_path="/fake/out.mp4",
                subtitle_ass=None,
                title_text=None,
            )
        assert call_count["n"] == 2

    def test_cpu_only_no_semaphore(self):
        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(lr_mod, "_resolve_codec", return_value="libx264"), \
             patch.object(lr_mod, "_run_ffmpeg_with_retry"), \
             patch.object(lr_mod, "probe_video_metadata", return_value=_FAKE_SRC_META), \
             patch.object(lr_mod, "_has_audio_stream", return_value=True), \
             patch.object(lr_mod, "_resolve_fps", return_value=(60, "capped")), \
             patch.object(lr_mod, "_detect_windows_fontfile", return_value=None), \
             patch.object(lr_mod, "_get_custom_fonts_dir", return_value=None), \
             patch.object(lr_mod, "_detect_windows_fonts_dir", return_value=None), \
             patch.object(lr_mod, "NVENC_SEMAPHORE", sem_mock):
            lr_mod.render_part(
                input_path="/fake/cut.mp4",
                output_path="/fake/out.mp4",
                subtitle_ass=None,
                title_text=None,
            )
        sem_mock.__enter__.assert_not_called()


# ---------------------------------------------------------------------------
# render_part_smart: no overlay flag logic, motion-crop fallback
# ---------------------------------------------------------------------------

class TestRenderPartSmart:
    def test_no_feature_overlay_logic(self):
        """render_part_smart must not contain FEATURE_OVERLAY_AFTER_BASE_CLIP logic."""
        import inspect as _inspect
        src = _inspect.getsource(lr_mod.render_part_smart)
        assert "FEATURE_OVERLAY_AFTER_BASE_CLIP" not in src
        assert "FEATURE_BASE_CLIP_FIRST" not in src

    def test_non_motion_path_delegates_to_render_part(self):
        """motion_aware_crop=False → render_part called directly."""
        mock_rp = MagicMock()
        with patch.object(lr_mod, "render_part", mock_rp):
            lr_mod.render_part_smart(
                input_path="/fake/cut.mp4",
                output_path="/fake/out.mp4",
                subtitle_ass="",
                title_text="",
                motion_aware_crop=False,
            )
        mock_rp.assert_called_once()

    def test_motion_crop_failure_falls_back_to_render_part(self):
        """render_motion_aware_crop raises → render_part called as fallback."""
        mock_rp = MagicMock()
        with patch.object(lr_mod, "render_motion_aware_crop",
                          side_effect=RuntimeError("CV2 error")), \
             patch.object(lr_mod, "_resolve_codec", return_value="libx264"), \
             patch.object(lr_mod, "render_part", mock_rp):
            lr_mod.render_part_smart(
                input_path="/fake/cut.mp4",
                output_path="/fake/out.mp4",
                subtitle_ass="",
                title_text="",
                motion_aware_crop=True,
            )
        mock_rp.assert_called_once()

    def test_fallback_flag_populated_on_motion_crop_failure(self):
        flag: list = []
        with patch.object(lr_mod, "render_motion_aware_crop",
                          side_effect=RuntimeError("CV2 error")), \
             patch.object(lr_mod, "_resolve_codec", return_value="libx264"), \
             patch.object(lr_mod, "render_part"):
            lr_mod.render_part_smart(
                input_path="/fake/cut.mp4",
                output_path="/fake/out.mp4",
                subtitle_ass="",
                title_text="",
                motion_aware_crop=True,
                _fallback_flag=flag,
            )
        assert len(flag) == 1
        assert "CV2 error" in flag[0]

    def test_nvenc_semaphore_acquired_for_motion_crop_gpu(self):
        """NVENC_SEMAPHORE is acquired before render_motion_aware_crop when codec is GPU."""
        sem_mock = MagicMock()
        mock_mac = MagicMock(return_value=None)

        with patch.object(lr_mod, "_resolve_codec", return_value="h264_nvenc"), \
             patch.object(lr_mod, "render_motion_aware_crop", mock_mac), \
             patch.object(lr_mod, "NVENC_SEMAPHORE", sem_mock):
            lr_mod.render_part_smart(
                input_path="/fake/cut.mp4",
                output_path="/fake/out.mp4",
                subtitle_ass="",
                title_text="",
                motion_aware_crop=True,
            )
        sem_mock.acquire.assert_called_once()
        sem_mock.release.assert_called_once()
