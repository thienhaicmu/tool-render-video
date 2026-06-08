"""Tests for app.features.render.engine.pipeline.qa_pipeline."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.features.render.engine.pipeline.qa_pipeline import (
    _duration_tolerance,
    _stall_deadline,
    _resume_output_valid,
    _validate_render_output,
)


# ---------------------------------------------------------------------------
# _duration_tolerance
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("duration,expected", [
    (5.0,   0.75),   # 5 * 0.15 = 0.75, inside [0.5, 3.0]
    (3.0,   0.5),    # 3 * 0.15 = 0.45 < 0.5 → floor is 0.5
    (100.0, 3.0),    # 100 * 0.15 = 15.0 > 3.0 → cap is 3.0
    (20.0,  3.0),    # 20 * 0.15 = 3.0 → exactly at cap
    (10.0,  1.5),    # 10 * 0.15 = 1.5
])
def test_duration_tolerance_parametrize(duration, expected):
    assert _duration_tolerance(duration) == pytest.approx(expected)


def test_duration_tolerance_zero_returns_fallback():
    assert _duration_tolerance(0) == pytest.approx(1.0)


def test_duration_tolerance_negative_returns_fallback():
    assert _duration_tolerance(-5.0) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _stall_deadline
# ---------------------------------------------------------------------------

def test_stall_deadline_basic_math():
    # 50s clip → max(120, 50*10) = max(120, 500) = 500 → start + 500
    result = _stall_deadline(1000.0, 50.0)
    assert result == pytest.approx(1500.0)


def test_stall_deadline_minimum_floor():
    # 5s clip → max(120, 5*10) = max(120, 50) = 120 → floor applied
    result = _stall_deadline(0.0, 5.0)
    assert result == pytest.approx(120.0)


def test_stall_deadline_zero_duration_uses_default():
    # expected_duration=0 → uses 60.0 fallback → max(120, 600) = 600
    result = _stall_deadline(0.0, 0.0)
    assert result == pytest.approx(600.0)


# ---------------------------------------------------------------------------
# _resume_output_valid
# ---------------------------------------------------------------------------

def test_resume_output_valid_missing_file_returns_false():
    # Path.exists() is not called by this function — it calls ffprobe
    # If ffprobe raises FileNotFoundError the except branch returns False
    with patch("subprocess.run", side_effect=FileNotFoundError("ffprobe not found")):
        result = _resume_output_valid(Path("/nonexistent/file.mp4"))
    assert result is False


def test_resume_output_valid_ffprobe_exception_returns_false():
    with patch("subprocess.run", side_effect=RuntimeError("ffprobe crashed")):
        result = _resume_output_valid(Path("/some/file.mp4"))
    assert result is False


def test_resume_output_valid_zero_duration_returns_false():
    mock_proc = MagicMock()
    mock_proc.stdout = "0.000000\n"
    mock_proc.returncode = 0
    with patch("subprocess.run", return_value=mock_proc):
        result = _resume_output_valid(Path("/some/file.mp4"))
    assert result is False


def test_resume_output_valid_empty_stdout_returns_false():
    mock_proc = MagicMock()
    mock_proc.stdout = ""
    mock_proc.returncode = 0
    with patch("subprocess.run", return_value=mock_proc):
        result = _resume_output_valid(Path("/some/file.mp4"))
    assert result is False


def test_resume_output_valid_positive_duration_returns_true():
    mock_proc = MagicMock()
    mock_proc.stdout = "12.345678\n"
    mock_proc.returncode = 0
    with patch("subprocess.run", return_value=mock_proc):
        result = _resume_output_valid(Path("/some/file.mp4"))
    assert result is True


# ---------------------------------------------------------------------------
# _validate_render_output
# ---------------------------------------------------------------------------

def test_validate_render_output_nonexistent_file():
    path = Path("/does/not/exist.mp4")
    result = _validate_render_output(path)
    assert result["ok"] is False
    assert "does not exist" in result["error"]


def test_validate_render_output_file_too_small(tmp_path):
    small_file = tmp_path / "tiny.mp4"
    small_file.write_bytes(b"x" * 100)  # 100 bytes < 10 240 minimum
    result = _validate_render_output(small_file)
    assert result["ok"] is False
    assert "too small" in result["error"]


def test_validate_render_output_no_video_stream(tmp_path):
    output = tmp_path / "audio_only.mp4"
    output.write_bytes(b"x" * 20_000)  # large enough to pass size check

    probe_data = {
        "streams": [{"codec_type": "audio"}],
        "format": {"duration": "10.0"},
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(probe_data)

    with patch("subprocess.run", return_value=mock_proc):
        result = _validate_render_output(output)

    assert result["ok"] is False
    assert "no video stream" in result["error"]


def test_validate_render_output_zero_duration(tmp_path):
    output = tmp_path / "zero_dur.mp4"
    output.write_bytes(b"x" * 20_000)

    probe_data = {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"duration": "0"},
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(probe_data)

    with patch("subprocess.run", return_value=mock_proc):
        result = _validate_render_output(output)

    assert result["ok"] is False
    assert "zero" in result["error"]


def test_validate_render_output_happy_path_video_and_audio(tmp_path):
    output = tmp_path / "good.mp4"
    output.write_bytes(b"x" * 50_000)

    probe_data = {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"duration": "30.0"},
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(probe_data)

    with patch("subprocess.run", return_value=mock_proc):
        result = _validate_render_output(output, expected_duration=30.0, expect_audio=True)

    assert result["ok"] is True
    assert result["error"] is None
    assert result["metadata"]["has_video"] is True
    assert result["metadata"]["has_audio"] is True
    assert result["warnings"] == []


def test_validate_render_output_duration_mismatch_beyond_tolerance(tmp_path):
    output = tmp_path / "mismatch.mp4"
    output.write_bytes(b"x" * 50_000)

    # expected=30s, actual=10s → diff=20s >> tolerance=max(0.5, min(4.5,3.0))=3.0
    probe_data = {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"duration": "10.0"},
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(probe_data)

    with patch("subprocess.run", return_value=mock_proc):
        result = _validate_render_output(output, expected_duration=30.0)

    assert result["ok"] is False
    assert "duration mismatch" in result["error"]


def test_validate_render_output_missing_audio_produces_warning(tmp_path):
    output = tmp_path / "no_audio.mp4"
    output.write_bytes(b"x" * 50_000)

    probe_data = {
        "streams": [{"codec_type": "video"}],
        "format": {"duration": "15.0"},
    }
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(probe_data)

    with patch("subprocess.run", return_value=mock_proc):
        result = _validate_render_output(output)

    assert result["ok"] is True  # warning, not hard failure
    assert len(result["warnings"]) == 1
