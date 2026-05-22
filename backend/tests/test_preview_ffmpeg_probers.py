"""Tests for app.services.preview.ffmpeg_probers (Phase 4H.1).

Verifies:
- All 6 probe helpers are importable from the new module
- Same-object identity: routes.render.X is ffmpeg_probers.X
- No FastAPI routing objects (APIRouter, Request, router) inside ffmpeg_probers
- Subprocess behavior (mocked): command args, timeout, error propagation
- _run_ffmpeg_checked: returns proc on success, raises HTTPException on non-zero exit
- _detect_leading_black_duration: pattern matching, no-black path, leading-black path
- _probe_video_codec: returns stripped codec string, empty string on error
- _probe_preview_profile: parses JSON output, falls back to codec probe on exception
- _is_browser_safe_preview: h264/aac/mp4 → True; vp9 → False; no audio → True
- _ensure_h264_preview: returns src unchanged if already safe; cached out if exists
"""

import inspect
import subprocess
import sys
import types
from pathlib import Path
from unittest import mock

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Import targets
# ---------------------------------------------------------------------------

import app.services.preview.ffmpeg_probers as probers
import app.routes.render as render_mod


# ---------------------------------------------------------------------------
# 1. Module importability
# ---------------------------------------------------------------------------

class TestModuleImports:
    def test_probers_module_importable(self):
        assert probers is not None

    def test_render_module_importable(self):
        assert render_mod is not None

    def test_all_six_symbols_in_probers(self):
        for name in (
            "_probe_video_codec",
            "_probe_preview_profile",
            "_is_browser_safe_preview",
            "_ensure_h264_preview",
            "_run_ffmpeg_checked",
            "_detect_leading_black_duration",
        ):
            assert hasattr(probers, name), f"missing {name} in ffmpeg_probers"

    def test_all_six_symbols_in_render(self):
        for name in (
            "_probe_video_codec",
            "_probe_preview_profile",
            "_is_browser_safe_preview",
            "_ensure_h264_preview",
            "_run_ffmpeg_checked",
            "_detect_leading_black_duration",
        ):
            assert hasattr(render_mod, name), f"missing {name} in routes.render"


# ---------------------------------------------------------------------------
# 2. Same-object identity
# ---------------------------------------------------------------------------

class TestSameObjectIdentity:
    def test_probe_video_codec_same_object(self):
        assert render_mod._probe_video_codec is probers._probe_video_codec

    def test_probe_preview_profile_same_object(self):
        assert render_mod._probe_preview_profile is probers._probe_preview_profile

    def test_is_browser_safe_preview_same_object(self):
        assert render_mod._is_browser_safe_preview is probers._is_browser_safe_preview

    def test_ensure_h264_preview_same_object(self):
        assert render_mod._ensure_h264_preview is probers._ensure_h264_preview

    def test_run_ffmpeg_checked_same_object(self):
        assert render_mod._run_ffmpeg_checked is probers._run_ffmpeg_checked

    def test_detect_leading_black_duration_same_object(self):
        assert render_mod._detect_leading_black_duration is probers._detect_leading_black_duration


# ---------------------------------------------------------------------------
# 3. No FastAPI routing objects inside ffmpeg_probers
# ---------------------------------------------------------------------------

class TestNoFastapiRoutingObjects:
    def _src(self) -> str:
        return inspect.getsource(probers)

    def test_no_apirouter(self):
        assert "APIRouter" not in self._src()

    def test_no_router_variable(self):
        assert "router = " not in self._src()

    def test_no_request_import(self):
        src = self._src()
        assert "from fastapi import" not in src.replace("from fastapi import HTTPException", "")
        # HTTPException is allowed; Request is not
        assert "Request" not in src

    def test_no_route_decorators(self):
        src = self._src()
        assert "@router." not in src

    def test_no_file_response(self):
        assert "FileResponse" not in self._src()

    def test_no_streaming_response(self):
        assert "StreamingResponse" not in self._src()

    def test_no_routes_render_import(self):
        assert "routes.render" not in self._src()


# ---------------------------------------------------------------------------
# 4. _probe_video_codec
# ---------------------------------------------------------------------------

class TestProbeVideoCodec:
    def test_returns_codec_string_on_success(self):
        fake_result = mock.MagicMock()
        fake_result.stdout = "h264\n"
        with mock.patch.object(subprocess, "run", return_value=fake_result) as m:
            result = probers._probe_video_codec(Path("/fake/file.mp4"))
        assert result == "h264"
        m.assert_called_once()

    def test_returns_empty_on_exception(self):
        with mock.patch.object(subprocess, "run", side_effect=Exception("ffprobe not found")):
            result = probers._probe_video_codec(Path("/fake/file.mp4"))
        assert result == ""

    def test_strips_and_lowercases_output(self):
        fake_result = mock.MagicMock()
        fake_result.stdout = "  H264  \n"
        with mock.patch.object(subprocess, "run", return_value=fake_result):
            result = probers._probe_video_codec(Path("/fake/file.mp4"))
        assert result == "h264"

    def test_command_uses_ffprobe_bin(self):
        fake_result = mock.MagicMock()
        fake_result.stdout = "h264"
        with mock.patch.object(subprocess, "run", return_value=fake_result) as m, \
             mock.patch.object(probers, "get_ffprobe_bin", return_value="/bin/ffprobe"):
            probers._probe_video_codec(Path("/fake/file.mp4"))
        cmd = m.call_args[0][0]
        assert cmd[0] == "/bin/ffprobe"

    def test_command_selects_video_stream(self):
        fake_result = mock.MagicMock()
        fake_result.stdout = "h264"
        with mock.patch.object(subprocess, "run", return_value=fake_result) as m, \
             mock.patch.object(probers, "get_ffprobe_bin", return_value="/bin/ffprobe"):
            probers._probe_video_codec(Path("/fake/file.mp4"))
        cmd = m.call_args[0][0]
        assert "-select_streams" in cmd
        assert "v:0" in cmd


# ---------------------------------------------------------------------------
# 5. _probe_preview_profile
# ---------------------------------------------------------------------------

class TestProbePreviewProfile:
    def _make_ffprobe_output(self, streams, format_name="mp4"):
        import json
        return json.dumps({
            "format": {"format_name": format_name},
            "streams": streams,
        })

    def test_returns_dict_with_keys(self):
        fake_result = mock.MagicMock()
        fake_result.stdout = self._make_ffprobe_output([
            {"codec_type": "video", "codec_name": "h264", "index": 0},
            {"codec_type": "audio", "codec_name": "aac", "index": 1},
        ])
        with mock.patch.object(subprocess, "run", return_value=fake_result):
            result = probers._probe_preview_profile(Path("/fake/file.mp4"))
        assert result["format_name"] == "mp4"
        assert result["video_codec"] == "h264"
        assert result["audio_codec"] == "aac"

    def test_returns_empty_strings_for_no_streams(self):
        fake_result = mock.MagicMock()
        fake_result.stdout = self._make_ffprobe_output([], format_name="")
        with mock.patch.object(subprocess, "run", return_value=fake_result):
            result = probers._probe_preview_profile(Path("/fake/file.mp4"))
        assert result["video_codec"] == ""
        assert result["audio_codec"] == ""

    def test_fallback_on_exception_calls_probe_video_codec(self):
        with mock.patch.object(subprocess, "run", side_effect=Exception("ffprobe crashed")), \
             mock.patch.object(probers, "_probe_video_codec", return_value="vp9") as mock_codec:
            result = probers._probe_preview_profile(Path("/fake/file.mp4"))
        mock_codec.assert_called_once()
        assert result["video_codec"] == "vp9"
        assert result["audio_codec"] == ""


# ---------------------------------------------------------------------------
# 6. _is_browser_safe_preview
# ---------------------------------------------------------------------------

class TestIsBrowserSafePreview:
    def _mock_profile(self, format_name, video_codec, audio_codec):
        return mock.patch.object(
            probers,
            "_probe_preview_profile",
            return_value={"format_name": format_name, "video_codec": video_codec, "audio_codec": audio_codec},
        )

    def test_h264_aac_mp4_is_safe(self):
        with self._mock_profile("mp4", "h264", "aac"):
            assert probers._is_browser_safe_preview(Path("/f.mp4")) is True

    def test_vp9_webm_is_not_safe(self):
        with self._mock_profile("webm", "vp9", "opus"):
            assert probers._is_browser_safe_preview(Path("/f.webm")) is False

    def test_hevc_is_not_safe(self):
        with self._mock_profile("mp4", "hevc", "aac"):
            assert probers._is_browser_safe_preview(Path("/f.mp4")) is False

    def test_h264_no_audio_is_safe(self):
        with self._mock_profile("mp4", "h264", ""):
            assert probers._is_browser_safe_preview(Path("/f.mp4")) is True

    def test_mov_h264_aac_is_safe(self):
        with self._mock_profile("mov,mp4,m4a,3gp,3g2,mj2", "h264", "aac"):
            assert probers._is_browser_safe_preview(Path("/f.mov")) is True

    def test_h264_opus_is_not_safe(self):
        with self._mock_profile("mp4", "h264", "opus"):
            assert probers._is_browser_safe_preview(Path("/f.mp4")) is False


# ---------------------------------------------------------------------------
# 7. _run_ffmpeg_checked
# ---------------------------------------------------------------------------

class TestRunFfmpegChecked:
    def test_returns_proc_on_success(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 0
        fake_proc.stderr = ""
        fake_proc.stdout = "done"
        with mock.patch.object(subprocess, "run", return_value=fake_proc):
            result = probers._run_ffmpeg_checked(["ffmpeg", "-v", "quiet"], "test")
        assert result is fake_proc

    def test_raises_http_exception_on_nonzero(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 1
        fake_proc.stderr = "Error: codec not found"
        fake_proc.stdout = ""
        with mock.patch.object(subprocess, "run", return_value=fake_proc):
            with pytest.raises(HTTPException) as exc_info:
                probers._run_ffmpeg_checked(["ffmpeg", "-bad"], "encode failed")
        assert exc_info.value.status_code == 500
        assert "encode failed" in exc_info.value.detail

    def test_detail_truncated_to_1200_chars(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 1
        fake_proc.stderr = "x" * 2000
        fake_proc.stdout = ""
        with mock.patch.object(subprocess, "run", return_value=fake_proc):
            with pytest.raises(HTTPException) as exc_info:
                probers._run_ffmpeg_checked(["ffmpeg"], "msg")
        assert len(exc_info.value.detail) <= 1200 + len("msg: ")

    def test_unknown_error_fallback_message(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 1
        fake_proc.stderr = ""
        fake_proc.stdout = ""
        with mock.patch.object(subprocess, "run", return_value=fake_proc):
            with pytest.raises(HTTPException) as exc_info:
                probers._run_ffmpeg_checked(["ffmpeg"], "my_op")
        assert "unknown ffmpeg error" in exc_info.value.detail


# ---------------------------------------------------------------------------
# 8. _detect_leading_black_duration
# ---------------------------------------------------------------------------

class TestDetectLeadingBlackDuration:
    def _make_ffmpeg_output(self, black_start, black_end, black_duration):
        return (
            f"blackdetect @ ... black_start:{black_start} "
            f"black_end:{black_end} black_duration:{black_duration}"
        )

    def test_returns_zero_when_no_black(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 0
        fake_proc.stderr = "no black detected"
        fake_proc.stdout = ""
        with mock.patch.object(subprocess, "run", return_value=fake_proc):
            result = probers._detect_leading_black_duration(
                Path("/fake/file.mp4"), min_duration=0.5, threshold=0.98
            )
        assert result == 0.0

    def test_returns_black_end_when_leading_black(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 0
        fake_proc.stderr = self._make_ffmpeg_output(0.0, 1.5, 1.5)
        fake_proc.stdout = ""
        with mock.patch.object(subprocess, "run", return_value=fake_proc):
            result = probers._detect_leading_black_duration(
                Path("/fake/file.mp4"), min_duration=0.5, threshold=0.98
            )
        assert result == pytest.approx(1.5)

    def test_ignores_black_that_starts_mid_video(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 0
        # start at 5.0s — not leading
        fake_proc.stderr = self._make_ffmpeg_output(5.0, 6.5, 1.5)
        fake_proc.stdout = ""
        with mock.patch.object(subprocess, "run", return_value=fake_proc):
            result = probers._detect_leading_black_duration(
                Path("/fake/file.mp4"), min_duration=0.5, threshold=0.98
            )
        assert result == 0.0

    def test_ignores_black_shorter_than_min_duration(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 0
        # duration 0.1s < min_duration 0.5s
        fake_proc.stderr = self._make_ffmpeg_output(0.0, 0.1, 0.1)
        fake_proc.stdout = ""
        with mock.patch.object(subprocess, "run", return_value=fake_proc):
            result = probers._detect_leading_black_duration(
                Path("/fake/file.mp4"), min_duration=0.5, threshold=0.98
            )
        assert result == 0.0

    def test_blackdetect_filter_in_command(self):
        fake_proc = mock.MagicMock()
        fake_proc.returncode = 0
        fake_proc.stderr = ""
        fake_proc.stdout = ""
        with mock.patch.object(subprocess, "run", return_value=fake_proc) as m, \
             mock.patch.object(probers, "get_ffmpeg_bin", return_value="/bin/ffmpeg"):
            probers._detect_leading_black_duration(
                Path("/fake/file.mp4"), min_duration=0.5, threshold=0.98
            )
        cmd = m.call_args[0][0]
        vf_idx = cmd.index("-vf")
        assert "blackdetect" in cmd[vf_idx + 1]


# ---------------------------------------------------------------------------
# 9. _ensure_h264_preview
# ---------------------------------------------------------------------------

class TestEnsureH264Preview:
    def test_returns_existing_output_without_probe(self, tmp_path):
        out = tmp_path / "preview_h264.mp4"
        out.write_bytes(b"fake video data")
        with mock.patch.object(probers, "_is_browser_safe_preview") as m_safe:
            result = probers._ensure_h264_preview(tmp_path / "source.mp4", tmp_path)
        m_safe.assert_not_called()
        assert result == out

    def test_returns_src_when_already_safe(self, tmp_path):
        src = tmp_path / "source.mp4"
        src.write_bytes(b"safe video")
        with mock.patch.object(probers, "_is_browser_safe_preview", return_value=True) as m_safe:
            result = probers._ensure_h264_preview(src, tmp_path)
        m_safe.assert_called_once_with(src)
        assert result == src

    def test_returns_src_on_transcode_failure(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_bytes(b"hevc video")
        fake_profile = {"format_name": "matroska", "video_codec": "hevc", "audio_codec": "aac"}
        with mock.patch.object(probers, "_is_browser_safe_preview", return_value=False), \
             mock.patch.object(probers, "_probe_preview_profile", return_value=fake_profile), \
             mock.patch.object(subprocess, "run", side_effect=Exception("ffmpeg crashed")):
            result = probers._ensure_h264_preview(src, tmp_path)
        assert result == src

    def test_returns_src_on_timeout(self, tmp_path):
        src = tmp_path / "source.mkv"
        src.write_bytes(b"hevc video")
        fake_profile = {"format_name": "matroska", "video_codec": "hevc", "audio_codec": "aac"}
        with mock.patch.object(probers, "_is_browser_safe_preview", return_value=False), \
             mock.patch.object(probers, "_probe_preview_profile", return_value=fake_profile), \
             mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("ffmpeg", 120)):
            result = probers._ensure_h264_preview(src, tmp_path)
        assert result == src
