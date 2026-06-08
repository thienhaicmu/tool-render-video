"""Tests for app.features.render.engine.encoder.clip_ops."""
import subprocess
from unittest.mock import MagicMock, patch, call

import pytest


from app.features.render.engine.encoder.clip_ops import (
    _detect_silence_segments,
    apply_micro_pacing,
    cut_video,
    detect_bad_first_frame,
    detect_silence_trim_offset,
)


# ---------------------------------------------------------------------------
# detect_silence_trim_offset
# ---------------------------------------------------------------------------

def _silence_run_result(stderr_lines: list[str]) -> MagicMock:
    mock = MagicMock()
    mock.returncode = 0
    mock.stderr = "\n".join(stderr_lines)
    return mock


def test_detect_silence_trim_offset_returns_zero_on_no_silence():
    with patch("subprocess.run", return_value=_silence_run_result([])):
        result = detect_silence_trim_offset("/fake.mp4", 0.0, 10.0)
    assert result == 0.0


def test_detect_silence_trim_offset_extracts_silence_end():
    stderr = ["silence_end: 0.50 | silence_duration: 0.50"]
    with patch("subprocess.run", return_value=_silence_run_result(stderr)):
        result = detect_silence_trim_offset("/fake.mp4", 0.0, 10.0)
    assert result == pytest.approx(0.50)


def test_detect_silence_trim_offset_below_min_trim_returns_zero():
    # 0.1 is below min_trim default of 0.2
    stderr = ["silence_end: 0.10 | silence_duration: 0.10"]
    with patch("subprocess.run", return_value=_silence_run_result(stderr)):
        result = detect_silence_trim_offset("/fake.mp4", 0.0, 10.0)
    assert result == 0.0


def test_detect_silence_trim_offset_caps_at_max_trim():
    # 2.0 > max_trim default of 1.5
    stderr = ["silence_end: 2.0 | silence_duration: 2.0"]
    with patch("subprocess.run", return_value=_silence_run_result(stderr)):
        result = detect_silence_trim_offset("/fake.mp4", 0.0, 10.0)
    assert result == pytest.approx(1.5)


def test_detect_silence_trim_offset_returns_zero_on_exception():
    with patch("subprocess.run", side_effect=Exception("ffmpeg error")):
        result = detect_silence_trim_offset("/fake.mp4", 0.0, 10.0)
    assert result == 0.0


# ---------------------------------------------------------------------------
# detect_bad_first_frame
# ---------------------------------------------------------------------------

def _blackdetect_run_result(stderr_lines: list[str]) -> MagicMock:
    mock = MagicMock()
    mock.returncode = 0
    mock.stderr = "\n".join(stderr_lines)
    return mock


def test_detect_bad_first_frame_no_black_returns_zero():
    with patch("subprocess.run", return_value=_blackdetect_run_result([])):
        result = detect_bad_first_frame("/fake.mp4", 0.0, 10.0)
    assert result == 0.0


def test_detect_bad_first_frame_detects_black_at_start():
    stderr = ["[blackdetect @ 0x1] black_start:0.0 black_end:0.5 black_duration:0.5"]
    with patch("subprocess.run", return_value=_blackdetect_run_result(stderr)):
        result = detect_bad_first_frame("/fake.mp4", 0.0, 10.0)
    assert result == pytest.approx(0.5)


def test_detect_bad_first_frame_skips_late_start():
    # black_start is 0.5 (> 0.08 threshold) — should NOT shift
    stderr = ["[blackdetect @ 0x1] black_start:0.5 black_end:1.0 black_duration:0.5"]
    with patch("subprocess.run", return_value=_blackdetect_run_result(stderr)):
        result = detect_bad_first_frame("/fake.mp4", 0.0, 10.0)
    assert result == 0.0


def test_detect_bad_first_frame_returns_zero_on_exception():
    with patch("subprocess.run", side_effect=Exception("error")):
        result = detect_bad_first_frame("/fake.mp4", 0.0, 10.0)
    assert result == 0.0


# ---------------------------------------------------------------------------
# _detect_silence_segments
# ---------------------------------------------------------------------------

def test_detect_silence_segments_returns_empty_on_exception():
    with patch("subprocess.run", side_effect=Exception("error")):
        result = _detect_silence_segments("/fake.mp4")
    assert result == []


def test_detect_silence_segments_parses_start_end_pairs():
    stderr = (
        "silence_start: 1.0\n"
        "silence_end: 2.0 | silence_duration: 1.0\n"
        "silence_start: 5.0\n"
        "silence_end: 6.0 | silence_duration: 1.0\n"
    )
    mock_result = MagicMock()
    mock_result.stderr = stderr
    with patch("subprocess.run", return_value=mock_result):
        segments = _detect_silence_segments("/fake.mp4")
    assert len(segments) == 2
    assert segments[0] == pytest.approx((1.0, 2.0))
    assert segments[1] == pytest.approx((5.0, 6.0))


# ---------------------------------------------------------------------------
# apply_micro_pacing
# ---------------------------------------------------------------------------

def test_apply_micro_pacing_returns_no_op_on_short_clip():
    with patch(
        "app.features.render.engine.encoder.clip_ops._probe_duration",
        return_value=3.0,
    ):
        result = apply_micro_pacing("/fake.mp4", "/out.mp4")
    assert result["applied"] is False
    assert result["segments_trimmed"] == 0


def test_apply_micro_pacing_returns_no_op_when_no_silences():
    with patch(
        "app.features.render.engine.encoder.clip_ops._probe_duration",
        return_value=15.0,
    ), patch(
        "app.features.render.engine.encoder.clip_ops._detect_silence_segments",
        return_value=[],
    ):
        result = apply_micro_pacing("/fake.mp4", "/out.mp4")
    assert result["applied"] is False


def test_apply_micro_pacing_result_shape_on_no_op():
    with patch(
        "app.features.render.engine.encoder.clip_ops._probe_duration",
        return_value=3.0,
    ):
        result = apply_micro_pacing("/fake.mp4", "/out.mp4")
    assert "applied" in result
    assert "segments_trimmed" in result
    assert "total_trim_ms" in result
    assert "method" in result


# ---------------------------------------------------------------------------
# cut_video — only the structure, not the real FFmpeg call
# ---------------------------------------------------------------------------

def test_cut_video_calls_ffmpeg_with_retry():
    with patch(
        "app.features.render.engine.encoder.clip_ops._run_ffmpeg_with_retry"
    ) as mock_retry, patch(
        "app.features.render.engine.encoder.clip_ops._probe_duration",
        return_value=5.0,
    ):
        cut_video("/input.mp4", "/output.mp4", 0.0, 5.0)
    assert mock_retry.called


def test_cut_video_force_accurate_skips_copy():
    """When force_accurate_cut=True, only the re-encode command is tried."""
    with patch(
        "app.features.render.engine.encoder.clip_ops._run_ffmpeg_with_retry"
    ) as mock_retry, patch(
        "app.features.render.engine.encoder.clip_ops._probe_duration",
        return_value=5.0,
    ):
        cut_video("/input.mp4", "/output.mp4", 0.0, 5.0, force_accurate_cut=True)
    assert mock_retry.call_count == 1
    # The fallback (re-encode) command contains "-c:v libx264"
    cmd_used = mock_retry.call_args[0][0]
    assert "libx264" in cmd_used
