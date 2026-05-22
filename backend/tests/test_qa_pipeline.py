"""
test_qa_pipeline.py — Unit tests for Phase 4C extraction.

Coverage:
- Import from new module location works
- Backward-compat import from render_pipeline works (same object)
- _duration_tolerance behavior unchanged
- _stall_deadline behavior unchanged
- _failed_part_progress behavior unchanged
- _render_part_failure_detail behavior unchanged
- _resume_output_valid handles missing file / positive-duration ffprobe output
- _validate_render_output handles missing file, zero-size, duration mismatch, valid output
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Section 1: Import correctness
# ---------------------------------------------------------------------------

class TestImportFromNewModule:
    def test_import_qa_pipeline(self):
        from app.orchestration.qa_pipeline import (
            _assess_output_quality,
            _duration_tolerance,
            _failed_part_progress,
            _render_part_failure_detail,
            _resume_output_valid,
            _stall_deadline,
            _validate_render_output,
        )
        assert callable(_duration_tolerance)
        assert callable(_stall_deadline)
        assert callable(_failed_part_progress)
        assert callable(_validate_render_output)
        assert callable(_assess_output_quality)
        assert callable(_render_part_failure_detail)
        assert callable(_resume_output_valid)


class TestBackwardCompatImport:
    def test_qa_functions_re_exported_from_render_pipeline(self):
        from app.orchestration.qa_pipeline import (
            _assess_output_quality,
            _duration_tolerance,
            _failed_part_progress,
            _render_part_failure_detail,
            _resume_output_valid,
            _stall_deadline,
            _validate_render_output,
        )
        from app.orchestration.render_pipeline import (
            _assess_output_quality as rp_assess,
            _duration_tolerance as rp_dt,
            _failed_part_progress as rp_fp,
            _render_part_failure_detail as rp_rpfd,
            _resume_output_valid as rp_rov,
            _stall_deadline as rp_sd,
            _validate_render_output as rp_vro,
        )
        assert rp_dt is _duration_tolerance
        assert rp_sd is _stall_deadline
        assert rp_fp is _failed_part_progress
        assert rp_vro is _validate_render_output
        assert rp_assess is _assess_output_quality
        assert rp_rpfd is _render_part_failure_detail
        assert rp_rov is _resume_output_valid


# ---------------------------------------------------------------------------
# Section 2: _duration_tolerance
# ---------------------------------------------------------------------------

class TestDurationTolerance:
    def test_short_clip_minimum(self):
        from app.orchestration.qa_pipeline import _duration_tolerance
        assert _duration_tolerance(1.0) == 0.5

    def test_medium_clip_proportional(self):
        from app.orchestration.qa_pipeline import _duration_tolerance
        result = _duration_tolerance(10.0)
        assert result == pytest_approx(1.5, abs=0.01)

    def test_long_clip_capped_at_3(self):
        from app.orchestration.qa_pipeline import _duration_tolerance
        assert _duration_tolerance(100.0) == 3.0

    def test_zero_duration_fallback(self):
        from app.orchestration.qa_pipeline import _duration_tolerance
        assert _duration_tolerance(0.0) == 1.0

    def test_negative_duration_fallback(self):
        from app.orchestration.qa_pipeline import _duration_tolerance
        assert _duration_tolerance(-5.0) == 1.0


def pytest_approx(val, abs=None):
    import math
    class _Approx:
        def __init__(self, v, a): self.v = v; self.a = a
        def __eq__(self, other): return math.isclose(other, self.v, abs_tol=self.a)
        def __repr__(self): return f"~{self.v}"
    return _Approx(val, abs or 1e-6)


# ---------------------------------------------------------------------------
# Section 3: _stall_deadline
# ---------------------------------------------------------------------------

class TestStallDeadline:
    def test_minimum_120s(self):
        from app.orchestration.qa_pipeline import _stall_deadline
        result = _stall_deadline(0.0, 0.0)
        assert result >= 120.0

    def test_expected_duration_multiplied(self):
        from app.orchestration.qa_pipeline import _stall_deadline
        result = _stall_deadline(0.0, 60.0)
        assert result == 600.0

    def test_encode_start_offset(self):
        from app.orchestration.qa_pipeline import _stall_deadline
        result = _stall_deadline(100.0, 60.0)
        assert result == 700.0

    def test_zero_expected_uses_fallback(self):
        from app.orchestration.qa_pipeline import _stall_deadline
        result = _stall_deadline(0.0, 0.0)
        assert result == 600.0  # max(120, 60*10)


# ---------------------------------------------------------------------------
# Section 4: _failed_part_progress
# ---------------------------------------------------------------------------

class TestFailedPartProgress:
    def test_returns_fallback_on_empty_parts(self):
        from app.orchestration.qa_pipeline import _failed_part_progress
        with patch("app.orchestration.qa_pipeline.list_job_parts", return_value=[]):
            result = _failed_part_progress("job1", 1, fallback=95)
        assert result == 95

    def test_returns_current_progress_for_matching_part(self):
        from app.orchestration.qa_pipeline import _failed_part_progress
        parts = [{"part_no": 1, "progress_percent": 72}]
        with patch("app.orchestration.qa_pipeline.list_job_parts", return_value=parts):
            result = _failed_part_progress("job1", 1)
        assert result == 72

    def test_caps_at_99_when_current_is_100(self):
        from app.orchestration.qa_pipeline import _failed_part_progress
        parts = [{"part_no": 1, "progress_percent": 100}]
        with patch("app.orchestration.qa_pipeline.list_job_parts", return_value=parts):
            result = _failed_part_progress("job1", 1, fallback=95)
        assert result == 95

    def test_ignores_non_matching_parts(self):
        from app.orchestration.qa_pipeline import _failed_part_progress
        parts = [{"part_no": 2, "progress_percent": 50}]
        with patch("app.orchestration.qa_pipeline.list_job_parts", return_value=parts):
            result = _failed_part_progress("job1", 1, fallback=80)
        assert result == 80

    def test_handles_exception_gracefully(self):
        from app.orchestration.qa_pipeline import _failed_part_progress
        with patch("app.orchestration.qa_pipeline.list_job_parts", side_effect=RuntimeError("db down")):
            result = _failed_part_progress("job1", 1, fallback=60)
        assert result == 60


# ---------------------------------------------------------------------------
# Section 5: _render_part_failure_detail
# ---------------------------------------------------------------------------

class TestRenderPartFailureDetail:
    def test_validation_error_code(self):
        from app.orchestration.qa_pipeline import _render_part_failure_detail
        result = _render_part_failure_detail(1, "output_validation_failed: too small")
        assert result["code"] == "RN001"
        assert result["phase"] == "validation"

    def test_duration_mismatch_error_code(self):
        from app.orchestration.qa_pipeline import _render_part_failure_detail
        result = _render_part_failure_detail(2, "duration mismatch: 10.0s vs 12.0s")
        assert result["code"] == "RN001"
        assert result["phase"] == "validation"

    def test_non_validation_error_code(self):
        from app.orchestration.qa_pipeline import _render_part_failure_detail
        result = _render_part_failure_detail(3, "ffmpeg crashed")
        assert result["code"] == "RN004"
        assert result["phase"] == "render"

    def test_part_no_preserved(self):
        from app.orchestration.qa_pipeline import _render_part_failure_detail
        result = _render_part_failure_detail(7, "some error")
        assert result["part_no"] == 7

    def test_error_message_preserved(self):
        from app.orchestration.qa_pipeline import _render_part_failure_detail
        exc = ValueError("bad input")
        result = _render_part_failure_detail(1, exc)
        assert "bad input" in result["error"]


# ---------------------------------------------------------------------------
# Section 6: _resume_output_valid
# ---------------------------------------------------------------------------

class TestResumeOutputValid:
    def test_returns_false_for_missing_file(self, tmp_path):
        from app.orchestration.qa_pipeline import _resume_output_valid
        result = _resume_output_valid(tmp_path / "nonexistent.mp4")
        assert result is False

    def test_returns_true_for_positive_duration(self, tmp_path):
        from app.orchestration.qa_pipeline import _resume_output_valid
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"fake")
        mock_proc = MagicMock()
        mock_proc.stdout = "12.345\n"
        with patch("app.orchestration.qa_pipeline.subprocess.run", return_value=mock_proc):
            result = _resume_output_valid(f)
        assert result is True

    def test_returns_false_for_zero_duration(self, tmp_path):
        from app.orchestration.qa_pipeline import _resume_output_valid
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"fake")
        mock_proc = MagicMock()
        mock_proc.stdout = "0.000\n"
        with patch("app.orchestration.qa_pipeline.subprocess.run", return_value=mock_proc):
            result = _resume_output_valid(f)
        assert result is False

    def test_returns_false_on_probe_exception(self, tmp_path):
        from app.orchestration.qa_pipeline import _resume_output_valid
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"fake")
        with patch("app.orchestration.qa_pipeline.subprocess.run", side_effect=Exception("probe failed")):
            result = _resume_output_valid(f)
        assert result is False


# ---------------------------------------------------------------------------
# Section 7: _validate_render_output
# ---------------------------------------------------------------------------

def _make_probe_output(duration: float = 30.0, has_video: bool = True, has_audio: bool = True) -> str:
    streams = []
    if has_video:
        streams.append({"codec_type": "video", "codec_name": "h264"})
    if has_audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return json.dumps({
        "format": {"duration": str(duration)},
        "streams": streams,
    })


class TestValidateRenderOutput:
    def test_missing_file_not_ok(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        result = _validate_render_output(tmp_path / "missing.mp4")
        assert result["ok"] is False
        assert "does not exist" in result["error"]

    def test_zero_size_file_not_ok(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        f = tmp_path / "empty.mp4"
        f.write_bytes(b"")
        result = _validate_render_output(f)
        assert result["ok"] is False
        assert "too small" in result["error"]

    def test_small_file_not_ok(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        f = tmp_path / "tiny.mp4"
        f.write_bytes(b"x" * 100)
        result = _validate_render_output(f)
        assert result["ok"] is False
        assert "too small" in result["error"]

    def test_valid_output_ok(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"x" * 20_000)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_probe_output(duration=30.0)
        with patch("app.orchestration.qa_pipeline.subprocess.run", return_value=mock_proc):
            result = _validate_render_output(f)
        assert result["ok"] is True
        assert result["metadata"]["duration"] == 30.0
        assert result["metadata"]["has_video"] is True

    def test_duration_mismatch_not_ok(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"x" * 20_000)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_probe_output(duration=10.0)
        with patch("app.orchestration.qa_pipeline.subprocess.run", return_value=mock_proc):
            result = _validate_render_output(f, expected_duration=30.0)
        assert result["ok"] is False
        assert "duration mismatch" in result["error"]

    def test_duration_within_tolerance_ok(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"x" * 20_000)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_probe_output(duration=30.2)
        with patch("app.orchestration.qa_pipeline.subprocess.run", return_value=mock_proc):
            result = _validate_render_output(f, expected_duration=30.0)
        assert result["ok"] is True

    def test_no_video_stream_not_ok(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"x" * 20_000)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_probe_output(duration=30.0, has_video=False)
        with patch("app.orchestration.qa_pipeline.subprocess.run", return_value=mock_proc):
            result = _validate_render_output(f)
        assert result["ok"] is False
        assert "no video stream" in result["error"]

    def test_ffprobe_failure_not_ok(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"x" * 20_000)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Invalid data found"
        with patch("app.orchestration.qa_pipeline.subprocess.run", return_value=mock_proc):
            result = _validate_render_output(f)
        assert result["ok"] is False
        assert "ffprobe could not read" in result["error"]

    def test_audio_warning_when_expected(self, tmp_path):
        from app.orchestration.qa_pipeline import _validate_render_output
        f = tmp_path / "clip.mp4"
        f.write_bytes(b"x" * 20_000)
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = _make_probe_output(duration=30.0, has_audio=False)
        with patch("app.orchestration.qa_pipeline.subprocess.run", return_value=mock_proc):
            result = _validate_render_output(f, expect_audio=True)
        assert result["ok"] is True
        assert any("audio" in w for w in result["warnings"])
