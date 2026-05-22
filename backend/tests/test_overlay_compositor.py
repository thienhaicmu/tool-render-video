"""
Tests for Phase 4E.4: services/render/overlay_compositor.py extraction.

Verifies:
- Import from new module works
- Backward-compat import from render_engine works
- Same object identity between modules
- Subtitle-only path contains ass= in vf_chain
- Title-only path contains drawtext= in vf_chain
- Text-layers path contains drawtext= with layer timing
- All-overlays vf_chain order: ass → title drawtext → layers → fps
- fps= is last video filter
- Forbidden filters absent: setpts, atempo, crop, scale, eq, hqdn3d, loudnorm
- No BGM inputs (-stream_loop absent, -filter_complex absent)
- Audio always -c:a copy; no -af flag
- Stream copy path when all overlay sources absent
- NVENC semaphore acquired/released on GPU codec path
- CPU fallback fires when NVENC raises
- Return metadata dict has required keys and correct types
"""

import pytest
from unittest.mock import patch, MagicMock

from app.domain.timeline import TimelineMap
import app.services.render.overlay_compositor as oc_mod


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


_FAKE_META = {
    "duration": 26.1,
    "fps": 60.0,
    "width": 1080,
    "height": 1440,
    "has_audio": True,
}

_SAMPLE_TEXT_LAYER = {
    "id": "layer_1",
    "text": "Overlay text",
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


def _call_oc(subtitle_ass: "str | None" = "/fake/overlay.ass", codec: str = "libx264", **overrides):
    """Run composite_overlays_on_base_clip with all external I/O mocked. Returns (result, cmds)."""
    cmds: list[list] = []

    def _fake_run(cmd, **_kw):
        cmds.append(list(cmd))

    with (
        patch.object(oc_mod, "_run_ffmpeg_with_retry", side_effect=_fake_run),
        patch.object(oc_mod, "probe_video_metadata", return_value=_FAKE_META),
        patch.object(oc_mod, "_resolve_codec", return_value=codec),
        patch.object(oc_mod, "_detect_windows_fontfile", return_value=None),
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
        result = oc_mod.composite_overlays_on_base_clip(**kwargs)

    return result, cmds


def _get_vf(cmds: list) -> str:
    cmd = cmds[0]
    return cmd[cmd.index("-vf") + 1]


# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------

class TestImportFromNewModule:
    def test_import_overlay_compositor_package(self):
        from app.services.render import overlay_compositor
        assert overlay_compositor is not None

    def test_import_composite_overlays_on_base_clip(self):
        from app.services.render.overlay_compositor import composite_overlays_on_base_clip
        assert callable(composite_overlays_on_base_clip)


class TestBackwardCompatImport:
    def test_composite_via_render_engine(self):
        from app.services.render_engine import composite_overlays_on_base_clip
        assert callable(composite_overlays_on_base_clip)


class TestSameObject:
    def test_composite_is_same_object(self):
        import app.services.render.overlay_compositor as oc
        import app.services.render_engine as re_mod
        assert re_mod.composite_overlays_on_base_clip is oc.composite_overlays_on_base_clip


# ---------------------------------------------------------------------------
# vf_chain content — overlay filters
# ---------------------------------------------------------------------------

class TestOverlayCompositorFilters:
    def test_ass_filter_present_when_subtitle_provided(self):
        _, cmds = _call_oc(subtitle_ass="/fake/overlay.ass")
        assert cmds
        assert "ass=" in " ".join(cmds[0])

    def test_drawtext_present_when_title_provided(self):
        _, cmds = _call_oc(subtitle_ass=None, title_text="My Title")
        assert "drawtext=" in _get_vf(cmds)

    def test_title_enable_expression_is_lt_3(self):
        _, cmds = _call_oc(subtitle_ass=None, title_text="My Title")
        vf = _get_vf(cmds)
        assert "lt(t" in vf and "3" in vf

    def test_drawtext_present_when_text_layers_provided(self):
        _, cmds = _call_oc(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        assert "drawtext=" in _get_vf(cmds)

    def test_text_layer_uses_start_end_times(self):
        _, cmds = _call_oc(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        vf = _get_vf(cmds)
        assert "1.500" in vf
        assert "5.000" in vf

    def test_drawtext_absent_when_title_none(self):
        _, cmds = _call_oc(subtitle_ass="/fake/overlay.ass", title_text=None, text_layers=None)
        vf = _get_vf(cmds)
        assert "drawtext=" not in vf

    def test_drawtext_absent_when_text_layers_none(self):
        _, cmds = _call_oc(subtitle_ass="/fake/overlay.ass", title_text=None, text_layers=None)
        vf = _get_vf(cmds)
        assert "drawtext=" not in vf


# ---------------------------------------------------------------------------
# vf_chain filter order: ass → title → layers → fps
# ---------------------------------------------------------------------------

class TestOverlayCompositorFilterOrder:
    def test_fps_is_last_filter_subtitle_only(self):
        _, cmds = _call_oc(subtitle_ass="/fake/overlay.ass")
        last = _get_vf(cmds).rsplit(",", 1)[-1]
        assert last.startswith("fps=")

    def test_fps_is_last_filter_title_only(self):
        _, cmds = _call_oc(subtitle_ass=None, title_text="Title")
        last = _get_vf(cmds).rsplit(",", 1)[-1]
        assert last.startswith("fps=")

    def test_fps_is_last_filter_text_layers_only(self):
        _, cmds = _call_oc(subtitle_ass=None, text_layers=[_SAMPLE_TEXT_LAYER])
        last = _get_vf(cmds).rsplit(",", 1)[-1]
        assert last.startswith("fps=")

    def test_fps_is_last_filter_all_overlays(self):
        _, cmds = _call_oc(
            subtitle_ass="/fake/overlay.ass",
            title_text="Title",
            text_layers=[_SAMPLE_TEXT_LAYER],
        )
        last = _get_vf(cmds).rsplit(",", 1)[-1]
        assert last.startswith("fps=")

    def test_ass_before_drawtext_in_vf_chain(self):
        _, cmds = _call_oc(subtitle_ass="/fake/overlay.ass", title_text="Title")
        vf = _get_vf(cmds)
        assert vf.index("ass=") < vf.index("drawtext=")


# ---------------------------------------------------------------------------
# Forbidden filters
# ---------------------------------------------------------------------------

class TestOverlayCompositorForbiddenFilters:
    def test_no_setpts(self):
        _, cmds = _call_oc()
        assert "setpts=" not in " ".join(cmds[0])

    def test_no_atempo(self):
        _, cmds = _call_oc()
        assert "atempo=" not in " ".join(cmds[0])

    def test_no_crop(self):
        _, cmds = _call_oc()
        assert "crop=" not in " ".join(cmds[0])

    def test_no_scale(self):
        _, cmds = _call_oc()
        assert "scale=" not in " ".join(cmds[0])

    def test_no_eq(self):
        _, cmds = _call_oc()
        assert "eq=" not in " ".join(cmds[0])

    def test_no_hqdn3d(self):
        _, cmds = _call_oc()
        assert "hqdn3d" not in " ".join(cmds[0])

    def test_no_loudnorm(self):
        _, cmds = _call_oc()
        assert "loudnorm" not in " ".join(cmds[0])

    def test_no_stream_loop_bgm(self):
        _, cmds = _call_oc()
        assert "-stream_loop" not in cmds[0]

    def test_no_filter_complex(self):
        _, cmds = _call_oc()
        assert "-filter_complex" not in cmds[0]

    def test_no_amix(self):
        _, cmds = _call_oc()
        assert "amix" not in " ".join(cmds[0])


# ---------------------------------------------------------------------------
# Audio: always -c:a copy, never -af
# ---------------------------------------------------------------------------

class TestOverlayCompositorAudio:
    def test_audio_copy_with_subtitle(self):
        _, cmds = _call_oc(subtitle_ass="/fake/overlay.ass")
        pairs = list(zip(cmds[0], cmds[0][1:]))
        assert ("-c:a", "copy") in pairs

    def test_audio_copy_no_overlay(self):
        _, cmds = _call_oc(subtitle_ass=None)
        pairs = list(zip(cmds[0], cmds[0][1:]))
        assert ("-c:a", "copy") in pairs

    def test_audio_copy_all_overlays(self):
        _, cmds = _call_oc(
            subtitle_ass="/fake/overlay.ass",
            title_text="Title",
            text_layers=[_SAMPLE_TEXT_LAYER],
        )
        pairs = list(zip(cmds[0], cmds[0][1:]))
        assert ("-c:a", "copy") in pairs

    def test_no_af_flag(self):
        _, cmds = _call_oc(subtitle_ass="/fake/overlay.ass")
        assert "-af" not in cmds[0]


# ---------------------------------------------------------------------------
# Stream copy path
# ---------------------------------------------------------------------------

class TestOverlayCompositorStreamCopy:
    def test_stream_copy_when_no_overlays(self):
        _, cmds = _call_oc(subtitle_ass=None, title_text=None, text_layers=None)
        pairs = list(zip(cmds[0], cmds[0][1:]))
        assert ("-c:v", "copy") in pairs

    def test_no_vf_when_no_overlays(self):
        _, cmds = _call_oc(subtitle_ass=None, title_text=None, text_layers=None)
        assert "-vf" not in cmds[0]

    def test_encode_when_subtitle_only(self):
        _, cmds = _call_oc(subtitle_ass="/fake/overlay.ass", title_text=None, text_layers=None)
        pairs = list(zip(cmds[0], cmds[0][1:]))
        assert ("-c:v", "copy") not in pairs
        assert "-vf" in cmds[0]

    def test_encode_when_title_only(self):
        _, cmds = _call_oc(subtitle_ass=None, title_text="Title Only", text_layers=None)
        assert "-vf" in cmds[0]

    def test_encode_when_text_layers_only(self):
        _, cmds = _call_oc(subtitle_ass=None, title_text=None, text_layers=[_SAMPLE_TEXT_LAYER])
        assert "-vf" in cmds[0]


# ---------------------------------------------------------------------------
# NVENC semaphore + CPU fallback
# ---------------------------------------------------------------------------

class TestOverlayCompositorNvenc:
    def test_nvenc_semaphore_acquired_for_gpu_codec(self):
        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(oc_mod, "_resolve_codec", return_value="h264_nvenc"), \
             patch.object(oc_mod, "_run_ffmpeg_with_retry"), \
             patch.object(oc_mod, "probe_video_metadata", return_value=_FAKE_META), \
             patch.object(oc_mod, "_detect_windows_fontfile", return_value=None), \
             patch.object(oc_mod, "NVENC_SEMAPHORE", sem_mock):
            oc_mod.composite_overlays_on_base_clip(
                base_clip_path="/fake/base_clip.mp4",
                output_path="/fake/out.mp4",
                timeline=_make_timeline(),
                subtitle_ass="/fake/overlay.ass",
            )
        sem_mock.__enter__.assert_called_once()
        sem_mock.__exit__.assert_called_once()

    def test_cpu_fallback_on_nvenc_failure(self):
        call_count = {"n": 0}

        def _side_effect(cmd, **_kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("NVENC out of memory")

        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(oc_mod, "_resolve_codec", return_value="h264_nvenc"), \
             patch.object(oc_mod, "_run_ffmpeg_with_retry", side_effect=_side_effect), \
             patch.object(oc_mod, "probe_video_metadata", return_value=_FAKE_META), \
             patch.object(oc_mod, "_detect_windows_fontfile", return_value=None), \
             patch.object(oc_mod, "NVENC_SEMAPHORE", sem_mock):
            oc_mod.composite_overlays_on_base_clip(
                base_clip_path="/fake/base_clip.mp4",
                output_path="/fake/out.mp4",
                timeline=_make_timeline(),
                subtitle_ass="/fake/overlay.ass",
            )
        assert call_count["n"] == 2, "Expected two FFmpeg calls: GPU attempt + CPU fallback"

    def test_cpu_only_no_semaphore(self):
        sem_mock = MagicMock()
        sem_mock.__enter__ = MagicMock(return_value=None)
        sem_mock.__exit__ = MagicMock(return_value=False)

        with patch.object(oc_mod, "_resolve_codec", return_value="libx264"), \
             patch.object(oc_mod, "_run_ffmpeg_with_retry"), \
             patch.object(oc_mod, "probe_video_metadata", return_value=_FAKE_META), \
             patch.object(oc_mod, "_detect_windows_fontfile", return_value=None), \
             patch.object(oc_mod, "NVENC_SEMAPHORE", sem_mock):
            oc_mod.composite_overlays_on_base_clip(
                base_clip_path="/fake/base_clip.mp4",
                output_path="/fake/out.mp4",
                timeline=_make_timeline(),
                subtitle_ass="/fake/overlay.ass",
            )
        sem_mock.__enter__.assert_not_called()


# ---------------------------------------------------------------------------
# Return value
# ---------------------------------------------------------------------------

class TestOverlayCompositorReturnValue:
    def test_returns_dict_with_all_keys(self):
        result, _ = _call_oc()
        for key in ("path", "duration", "fps", "width", "height", "has_audio"):
            assert key in result, f"Missing key '{key}'"

    def test_path_matches_output_path(self):
        result, _ = _call_oc()
        assert result["path"] == "/fake/overlay_out.mp4"

    def test_has_audio_is_bool(self):
        result, _ = _call_oc()
        assert isinstance(result["has_audio"], bool)

    def test_metadata_sourced_from_probe(self):
        result, _ = _call_oc()
        assert result["duration"] == pytest.approx(_FAKE_META["duration"])
        assert result["fps"] == pytest.approx(_FAKE_META["fps"])
        assert result["width"] == _FAKE_META["width"]
        assert result["height"] == _FAKE_META["height"]
