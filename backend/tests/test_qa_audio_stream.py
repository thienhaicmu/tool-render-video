"""
test_qa_audio_stream.py — Tests for audio stream presence check in output QA.

Phase 5.1 — Task 3

Coverage:
- Video with audio passes QA with no audio warning
- Video without audio produces a warning (non-fatal — ok=True)
- expect_audio=True with no audio produces the "expected but missing" warning
- expect_audio=False with no audio still warns (new behaviour)
- Probe failure is handled safely (does not crash)
- _validate_render_output structure unchanged (ok, warnings, error, metadata keys)
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_probe_output(
    has_video: bool = True,
    has_audio: bool = True,
    duration: float = 10.0,
) -> str:
    """Return fake ffprobe JSON output."""
    streams = []
    if has_video:
        streams.append({"codec_type": "video", "codec_name": "h264"})
    if has_audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return json.dumps({
        "streams": streams,
        "format": {"duration": str(duration)},
    })


def _patch_ffprobe(returncode=0, stdout="", stderr=""):
    """Context manager: patch subprocess.run to simulate ffprobe output."""
    mock_result = MagicMock()
    mock_result.returncode = returncode
    mock_result.stdout = stdout
    mock_result.stderr = stderr
    return patch("subprocess.run", return_value=mock_result)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

class TestImport:
    def test_validate_render_output_importable(self):
        from app.orchestration.qa_pipeline import _validate_render_output
        assert callable(_validate_render_output)


# ---------------------------------------------------------------------------
# Audio stream present — should pass cleanly
# ---------------------------------------------------------------------------

class TestVideoWithAudio:
    def test_video_with_audio_passes(self, tmp_path):
        """Video with both video and audio streams must pass QA without audio warning."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)  # > 10 KB minimum

        probe_json = _make_probe_output(has_video=True, has_audio=True, duration=10.0)

        with _patch_ffprobe(returncode=0, stdout=probe_json):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output, expected_duration=10.0)

        assert result["ok"] is True
        # No audio-related warning
        audio_warnings = [w for w in result["warnings"] if "audio" in w.lower()]
        assert len(audio_warnings) == 0, f"Unexpected audio warnings: {audio_warnings}"

    def test_metadata_has_audio_true(self, tmp_path):
        """metadata.has_audio must be True when audio stream present."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        probe_json = _make_probe_output(has_video=True, has_audio=True, duration=5.0)
        with _patch_ffprobe(returncode=0, stdout=probe_json):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output)

        assert result["metadata"]["has_audio"] is True


# ---------------------------------------------------------------------------
# Audio stream missing — should warn (non-fatal)
# ---------------------------------------------------------------------------

class TestVideoWithoutAudio:
    def test_video_without_audio_warns(self, tmp_path):
        """Video without audio must produce a warning (non-fatal)."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        probe_json = _make_probe_output(has_video=True, has_audio=False, duration=10.0)

        with _patch_ffprobe(returncode=0, stdout=probe_json):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output, expected_duration=10.0)

        assert result["ok"] is True, (
            "Video without audio must not be a hard failure (ok must still be True)"
        )
        audio_warnings = [w for w in result["warnings"] if "audio" in w.lower()]
        assert len(audio_warnings) > 0, (
            "Video without audio must produce at least one audio warning"
        )

    def test_metadata_has_audio_false(self, tmp_path):
        """metadata.has_audio must be False when audio stream absent."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        probe_json = _make_probe_output(has_video=True, has_audio=False, duration=5.0)
        with _patch_ffprobe(returncode=0, stdout=probe_json):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output)

        assert result["metadata"]["has_audio"] is False

    def test_result_ok_not_changed_by_audio_warning(self, tmp_path):
        """Audio warning must not flip ok=False — render should complete."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        probe_json = _make_probe_output(has_video=True, has_audio=False, duration=5.0)
        with _patch_ffprobe(returncode=0, stdout=probe_json):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output)

        assert result["ok"] is True, (
            "Audio missing must be a warning, not a hard failure"
        )
        assert result["error"] is None


# ---------------------------------------------------------------------------
# expect_audio=True — "expected but missing" warning
# ---------------------------------------------------------------------------

class TestExpectAudioTrue:
    def test_expect_audio_true_no_audio_warns(self, tmp_path):
        """expect_audio=True with no audio stream must produce the legacy warning."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        probe_json = _make_probe_output(has_video=True, has_audio=False, duration=5.0)
        with _patch_ffprobe(returncode=0, stdout=probe_json):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output, expect_audio=True)

        warnings_text = " ".join(result["warnings"]).lower()
        assert "audio" in warnings_text
        assert "expected" in warnings_text or "missing" in warnings_text

    def test_expect_audio_true_with_audio_no_warning(self, tmp_path):
        """expect_audio=True and audio present must produce no audio warning."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        probe_json = _make_probe_output(has_video=True, has_audio=True, duration=5.0)
        with _patch_ffprobe(returncode=0, stdout=probe_json):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output, expect_audio=True)

        audio_warnings = [w for w in result["warnings"] if "audio" in w.lower()]
        assert len(audio_warnings) == 0


# ---------------------------------------------------------------------------
# Probe failure safety
# ---------------------------------------------------------------------------

class TestProbeFailureSafety:
    def test_ffprobe_failure_returns_error_not_crash(self, tmp_path):
        """ffprobe failure (non-zero returncode) must return ok=False, not crash."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        with _patch_ffprobe(returncode=1, stdout="", stderr="ffprobe error"):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output)

        assert result["ok"] is False
        assert result["error"] is not None

    def test_missing_file_returns_error_not_crash(self, tmp_path):
        """Missing output file must return ok=False with error message."""
        output = tmp_path / "nonexistent.mp4"

        from app.orchestration.qa_pipeline import _validate_render_output
        result = _validate_render_output(output)

        assert result["ok"] is False
        assert "does not exist" in (result["error"] or "").lower() or result["code"] == "RN001"

    def test_result_always_has_required_keys(self, tmp_path):
        """Result dict must always have ok, warnings, error, metadata keys."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        probe_json = _make_probe_output(has_video=True, has_audio=True)
        with _patch_ffprobe(returncode=0, stdout=probe_json):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output)

        for key in ("ok", "warnings", "error", "metadata"):
            assert key in result, f"Result missing key: {key}"

    def test_metadata_has_audio_key_always_present(self, tmp_path):
        """metadata.has_audio must always be present (even on probe failure)."""
        output = tmp_path / "output.mp4"
        output.write_bytes(b"x" * 20_000)

        with _patch_ffprobe(returncode=1, stdout="", stderr="error"):
            from app.orchestration.qa_pipeline import _validate_render_output
            result = _validate_render_output(output)

        assert "has_audio" in result["metadata"]
