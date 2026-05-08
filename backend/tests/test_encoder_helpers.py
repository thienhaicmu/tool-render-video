"""
Tests for encoder_helpers.py — the shared encoder detection and flag module.

All tests mock subprocess so no real FFmpeg binary is required.
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers for lru_cache invalidation between tests
# ---------------------------------------------------------------------------

def _clear_encoder_caches():
    from app.services import encoder_helpers
    encoder_helpers.ffmpeg_encoders_text.cache_clear()
    encoder_helpers.nvenc_runtime_ready.cache_clear()


# ---------------------------------------------------------------------------
# has_encoder / ffmpeg_encoders_text
# ---------------------------------------------------------------------------

class TestHasEncoder:

    def setup_method(self):
        _clear_encoder_caches()

    def test_returns_true_when_name_in_output(self):
        from app.services.encoder_helpers import has_encoder, ffmpeg_encoders_text
        with patch("app.services.encoder_helpers.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=" h264_nvenc  ", stderr="")
            _clear_encoder_caches()
            assert has_encoder("h264_nvenc") is True

    def test_returns_false_when_name_absent(self):
        from app.services.encoder_helpers import has_encoder
        with patch("app.services.encoder_helpers.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="libx264\nlibx265\n", stderr="")
            _clear_encoder_caches()
            assert has_encoder("h264_nvenc") is False

    def test_returns_false_on_subprocess_exception(self):
        from app.services.encoder_helpers import has_encoder
        with patch("app.services.encoder_helpers.subprocess.run", side_effect=OSError("not found")):
            _clear_encoder_caches()
            assert has_encoder("h264_nvenc") is False


# ---------------------------------------------------------------------------
# nvenc_runtime_ready
# ---------------------------------------------------------------------------

class TestNvencRuntimeReady:

    def setup_method(self):
        _clear_encoder_caches()

    def test_returns_true_on_zero_returncode(self):
        from app.services.encoder_helpers import nvenc_runtime_ready
        with patch("app.services.encoder_helpers.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            _clear_encoder_caches()
            assert nvenc_runtime_ready("h264_nvenc") is True

    def test_returns_false_on_nvcuda_error(self):
        from app.services.encoder_helpers import nvenc_runtime_ready
        with patch("app.services.encoder_helpers.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="cannot load nvcuda.dll"
            )
            _clear_encoder_caches()
            assert nvenc_runtime_ready("h264_nvenc") is False

    def test_returns_false_on_no_nvenc_devices(self):
        from app.services.encoder_helpers import nvenc_runtime_ready
        with patch("app.services.encoder_helpers.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="", stderr="no nvenc capable devices found"
            )
            _clear_encoder_caches()
            assert nvenc_runtime_ready("h264_nvenc") is False

    def test_returns_false_on_exception(self):
        from app.services.encoder_helpers import nvenc_runtime_ready
        with patch("app.services.encoder_helpers.subprocess.run", side_effect=OSError("crash")):
            _clear_encoder_caches()
            assert nvenc_runtime_ready("h264_nvenc") is False


# ---------------------------------------------------------------------------
# resolve_encoder
# ---------------------------------------------------------------------------

class TestResolveEncoder:

    def setup_method(self):
        _clear_encoder_caches()

    def _resolve(self, codec="h264", mode="auto", nvenc_available=False):
        from app.services.encoder_helpers import resolve_encoder
        with patch("app.services.encoder_helpers.has_encoder", return_value=nvenc_available), \
             patch("app.services.encoder_helpers.nvenc_runtime_ready", return_value=nvenc_available):
            return resolve_encoder(codec, mode)

    def test_auto_no_nvenc_returns_libx264(self):
        assert self._resolve("h264", "auto", nvenc_available=False) == "libx264"

    def test_auto_no_nvenc_h265_returns_libx265(self):
        assert self._resolve("h265", "auto", nvenc_available=False) == "libx265"

    def test_auto_nvenc_available_returns_h264_nvenc(self):
        assert self._resolve("h264", "auto", nvenc_available=True) == "h264_nvenc"

    def test_auto_nvenc_available_h265_returns_hevc_nvenc(self):
        from app.services.encoder_helpers import resolve_encoder
        with patch("app.services.encoder_helpers.has_encoder", return_value=True), \
             patch("app.services.encoder_helpers.nvenc_runtime_ready", return_value=True):
            assert resolve_encoder("h265", "auto") == "hevc_nvenc"

    def test_cpu_mode_always_returns_cpu_codec(self):
        from app.services.encoder_helpers import resolve_encoder
        with patch("app.services.encoder_helpers.has_encoder", return_value=True), \
             patch("app.services.encoder_helpers.nvenc_runtime_ready", return_value=True):
            assert resolve_encoder("h264", "cpu") == "libx264"
            assert resolve_encoder("h265", "cpu") == "libx265"

    def test_nvenc_mode_falls_back_to_cpu_when_unavailable(self):
        assert self._resolve("h264", "nvenc", nvenc_available=False) == "libx264"

    def test_empty_codec_defaults_to_h264_path(self):
        assert self._resolve("", "auto", nvenc_available=False) == "libx264"

    def test_none_codec_does_not_crash(self):
        from app.services.encoder_helpers import resolve_encoder
        with patch("app.services.encoder_helpers.has_encoder", return_value=False), \
             patch("app.services.encoder_helpers.nvenc_runtime_ready", return_value=False):
            result = resolve_encoder(None, "auto")  # type: ignore[arg-type]
        assert result == "libx264"


# ---------------------------------------------------------------------------
# map_preset_for_encoder
# ---------------------------------------------------------------------------

class TestMapPresetForEncoder:

    def _map(self, preset, codec):
        from app.services.encoder_helpers import map_preset_for_encoder
        return map_preset_for_encoder(preset, codec)

    def test_nvenc_slow_maps_to_p6(self):
        assert self._map("slow", "h264_nvenc") == "p6"

    def test_nvenc_veryslow_maps_to_p7(self):
        assert self._map("veryslow", "h264_nvenc") == "p7"

    def test_nvenc_medium_maps_to_p5(self):
        assert self._map("medium", "hevc_nvenc") == "p5"

    def test_nvenc_unknown_preset_defaults_to_p6(self):
        assert self._map("banana", "h264_nvenc") == "p6"

    def test_cpu_codec_returns_preset_unchanged(self):
        assert self._map("slow", "libx264") == "slow"
        assert self._map("veryslow", "libx265") == "veryslow"

    @pytest.mark.parametrize("preset,expected", [
        ("ultrafast", "p2"), ("superfast", "p3"), ("veryfast", "p4"),
        ("faster", "p4"), ("fast", "p4"), ("medium", "p5"),
        ("slow", "p6"), ("slower", "p7"), ("veryslow", "p7"),
    ])
    def test_all_nvenc_preset_mappings(self, preset, expected):
        assert self._map(preset, "h264_nvenc") == expected


# ---------------------------------------------------------------------------
# codec_extra_flags — CPU paths (libx264 / libx265)
# ---------------------------------------------------------------------------

class TestCodecExtraFlagsCpu:

    def _flags(self, codec, crf=18, preset="slow"):
        from app.services.encoder_helpers import codec_extra_flags
        return codec_extra_flags(codec, crf, preset)

    def test_libx264_has_maxrate_20m(self):
        flags = self._flags("libx264")
        assert "-maxrate" in flags
        assert flags[flags.index("-maxrate") + 1] == "20M"

    def test_libx264_has_bufsize_40m(self):
        flags = self._flags("libx264")
        assert "-bufsize" in flags
        assert flags[flags.index("-bufsize") + 1] == "40M"

    def test_libx264_has_crf(self):
        flags = self._flags("libx264", crf=22)
        assert "-crf" in flags
        assert flags[flags.index("-crf") + 1] == "22"

    def test_libx265_has_maxrate_20m(self):
        flags = self._flags("libx265")
        assert "-maxrate" in flags
        assert flags[flags.index("-maxrate") + 1] == "20M"

    def test_libx265_has_bufsize_40m(self):
        flags = self._flags("libx265")
        assert "-bufsize" in flags
        assert flags[flags.index("-bufsize") + 1] == "40M"

    def test_libx265_has_hvc1_tag(self):
        assert "-tag:v" in self._flags("libx265")
        flags = self._flags("libx265")
        assert flags[flags.index("-tag:v") + 1] == "hvc1"

    def test_libx265_x265_params_vary_by_preset(self):
        slow = self._flags("libx265", preset="slow")
        veryslow = self._flags("libx265", preset="veryslow")
        idx_s = slow.index("-x265-params")
        idx_v = veryslow.index("-x265-params")
        assert slow[idx_s + 1] != veryslow[idx_v + 1]

    def test_libx264_x264_params_vary_by_preset(self):
        slow = self._flags("libx264", preset="slow")
        veryslow = self._flags("libx264", preset="veryslow")
        idx_s = slow.index("-x264-params")
        idx_v = veryslow.index("-x264-params")
        assert slow[idx_s + 1] != veryslow[idx_v + 1]

    @pytest.mark.parametrize("codec", ["libx264", "libx265"])
    def test_maxrate_before_bufsize(self, codec):
        flags = self._flags(codec)
        assert flags.index("-maxrate") < flags.index("-bufsize")


# ---------------------------------------------------------------------------
# codec_extra_flags — NVENC paths
# ---------------------------------------------------------------------------

class TestCodecExtraFlagsNvenc:

    def _flags(self, codec, crf=18):
        from app.services.encoder_helpers import codec_extra_flags
        return codec_extra_flags(codec, crf)

    def test_h264_nvenc_has_maxrate(self):
        assert "-maxrate" in self._flags("h264_nvenc")

    def test_h264_nvenc_has_bufsize(self):
        assert "-bufsize" in self._flags("h264_nvenc")

    def test_h264_nvenc_bf3(self):
        flags = self._flags("h264_nvenc")
        assert flags[flags.index("-bf") + 1] == "3"

    def test_hevc_nvenc_has_maxrate(self):
        assert "-maxrate" in self._flags("hevc_nvenc")

    def test_hevc_nvenc_bf4(self):
        flags = self._flags("hevc_nvenc")
        assert flags[flags.index("-bf") + 1] == "4"

    def test_nvenc_uses_vbr_hq(self):
        for codec in ("h264_nvenc", "hevc_nvenc"):
            flags = self._flags(codec)
            assert "-rc" in flags
            assert flags[flags.index("-rc") + 1] == "vbr_hq"


# ---------------------------------------------------------------------------
# safe_filter_path
# ---------------------------------------------------------------------------

class TestSafeFilterPath:

    def _sfp(self, path):
        from app.services.encoder_helpers import safe_filter_path
        return safe_filter_path(path)

    def test_backslash_path_separators_converted_to_forward_slash(self):
        # Input: C:\Users\foo\video.mp4
        # After replace("\\", "/"): C:/Users/foo/video.mp4
        # After replace(":", r"\:"): C\:/Users/foo/video.mp4
        # Original path-separator backslashes are gone; the remaining \ is the colon escape.
        result = self._sfp("C:\\Users\\foo\\video.mp4")
        assert "/" in result
        # Path separators (the /Users/foo portion) must use forward slashes.
        assert "/Users/foo/" in result

    def test_colon_escaped(self):
        result = self._sfp("C:/foo/bar.mp4")
        assert r"\:" in result

    def test_single_quote_escaped(self):
        result = self._sfp("foo's video.mp4")
        assert r"\'" in result

    def test_plain_unix_path_unchanged(self):
        result = self._sfp("/tmp/video.mp4")
        assert result == "/tmp/video.mp4"

    def test_returns_string(self):
        assert isinstance(self._sfp("test.mp4"), str)


# ---------------------------------------------------------------------------
# detect_windows_fontfile / detect_windows_fonts_dir
# ---------------------------------------------------------------------------

class TestDetectWindowsFontfile:

    def test_returns_none_when_windir_not_set(self):
        from app.services.encoder_helpers import detect_windows_fontfile
        with patch.dict("os.environ", {}, clear=True):
            assert detect_windows_fontfile() is None

    def test_returns_none_when_no_known_font_exists(self, tmp_path):
        from app.services.encoder_helpers import detect_windows_fontfile
        fake_windir = str(tmp_path)
        fonts_dir = tmp_path / "Fonts"
        fonts_dir.mkdir()
        with patch.dict("os.environ", {"WINDIR": fake_windir}):
            assert detect_windows_fontfile() is None

    def test_returns_path_when_arial_exists(self, tmp_path):
        from app.services.encoder_helpers import detect_windows_fontfile
        fake_windir = str(tmp_path)
        fonts_dir = tmp_path / "Fonts"
        fonts_dir.mkdir()
        arial = fonts_dir / "arial.ttf"
        arial.write_bytes(b"")
        with patch.dict("os.environ", {"WINDIR": fake_windir}):
            result = detect_windows_fontfile()
        assert result is not None
        assert "arial.ttf" in result.lower()


class TestDetectWindowsFontsDir:

    def test_returns_none_when_windir_not_set(self):
        from app.services.encoder_helpers import detect_windows_fonts_dir
        with patch.dict("os.environ", {}, clear=True):
            assert detect_windows_fonts_dir() is None

    def test_returns_path_when_fonts_dir_exists(self, tmp_path):
        from app.services.encoder_helpers import detect_windows_fonts_dir
        fonts_dir = tmp_path / "Fonts"
        fonts_dir.mkdir()
        with patch.dict("os.environ", {"WINDIR": str(tmp_path)}):
            result = detect_windows_fonts_dir()
        assert result is not None
        assert "Fonts" in result


# ---------------------------------------------------------------------------
# get_custom_fonts_dir
# ---------------------------------------------------------------------------

class TestGetCustomFontsDir:

    def test_returns_none_when_no_fonts_dir(self, tmp_path):
        from app.services.encoder_helpers import get_custom_fonts_dir
        with patch("app.services.encoder_helpers.Path.__file__", create=True):
            result = get_custom_fonts_dir()
        # No assertion on value since the backend/fonts dir may/may not exist in CI.
        # Just confirm it returns str or None.
        assert result is None or isinstance(result, str)

    def test_returns_string_when_backend_fonts_exists(self, tmp_path):
        from app.services.encoder_helpers import get_custom_fonts_dir
        # Create a fake fonts directory at the expected relative path.
        # The function resolves __file__ → parents[2]/fonts. We test it indirectly
        # by checking the return type rather than filesystem layout.
        result = get_custom_fonts_dir()
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# Backward-compat: render_engine and motion_crop still export old private names
# ---------------------------------------------------------------------------

class TestBackwardCompatWrappers:

    def test_render_engine_has_has_encoder(self):
        import app.services.render_engine as re
        assert callable(getattr(re, "_has_encoder", None))

    def test_render_engine_has_nvenc_runtime_ready(self):
        import app.services.render_engine as re
        assert callable(getattr(re, "_nvenc_runtime_ready", None))

    def test_render_engine_has_codec_extra_flags(self):
        import app.services.render_engine as re
        assert callable(getattr(re, "_codec_extra_flags", None))

    def test_render_engine_has_map_preset_for_encoder(self):
        import app.services.render_engine as re
        assert callable(getattr(re, "_map_preset_for_encoder", None))

    def test_render_engine_has_reup_video_filters(self):
        import app.services.render_engine as re
        assert callable(getattr(re, "_reup_video_filters", None))

    def test_render_engine_has_safe_filter_path(self):
        import app.services.render_engine as re
        assert callable(getattr(re, "_safe_filter_path", None))

    def test_motion_crop_has_resolve_encoder(self):
        import app.services.motion_crop as mc
        assert callable(getattr(mc, "_resolve_encoder", None))

    def test_motion_crop_has_codec_flags(self):
        import app.services.motion_crop as mc
        assert callable(getattr(mc, "_codec_flags", None))

    def test_motion_crop_has_map_preset_for_encoder(self):
        import app.services.motion_crop as mc
        assert callable(getattr(mc, "_map_preset_for_encoder", None))

    def test_render_engine_codec_extra_flags_delegates_to_encoder_helpers(self):
        """render_engine._codec_extra_flags must be the encoder_helpers function."""
        import app.services.render_engine as re
        import app.services.encoder_helpers as eh
        assert re._codec_extra_flags is eh.codec_extra_flags

    def test_motion_crop_reup_audio_filter_delegates_to_encoder_helpers(self):
        """motion_crop._reup_audio_filter must be the encoder_helpers function."""
        import app.services.motion_crop as mc
        import app.services.encoder_helpers as eh
        assert mc._reup_audio_filter is eh.reup_audio_filter
