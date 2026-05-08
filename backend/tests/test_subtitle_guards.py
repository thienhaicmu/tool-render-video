"""
Guard tests for subtitle_engine._run_with_retry — covers:
  1. Raises RuntimeError with stderr content after exhausting retries
  2. Retries before final failure (does not raise on first attempt)
  3. Empty stderr does not crash the error path
  4. Non-CalledProcessError exceptions re-raise after retries
"""

import subprocess
import pytest
from unittest.mock import patch, MagicMock, call


def _import_run_with_retry():
    from app.services.subtitle_engine import _run_with_retry
    return _run_with_retry


class TestRunWithRetry:

    def test_raises_runtime_error_on_final_failure(self):
        """After exhausting retries a RuntimeError must be raised (not CalledProcessError)."""
        _run_with_retry = _import_run_with_retry()
        exc = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="encoder error XYZ")

        with patch("subprocess.run", side_effect=exc), \
             patch("time.sleep"):
            with pytest.raises(RuntimeError):
                _run_with_retry(["ffmpeg", "-i", "x.mp4"], retries=2, wait_sec=0.0)

    def test_stderr_content_in_runtime_error_message(self):
        """RuntimeError message must contain the stderr text from the failed process."""
        _run_with_retry = _import_run_with_retry()
        exc = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="encoder error XYZ")

        with patch("subprocess.run", side_effect=exc), \
             patch("time.sleep"):
            with pytest.raises(RuntimeError) as exc_info:
                _run_with_retry(["ffmpeg", "-i", "x.mp4"], retries=2, wait_sec=0.0)

        assert "encoder error XYZ" in str(exc_info.value)

    def test_retries_before_final_failure(self):
        """subprocess.run must be called retries+1 times before the error propagates."""
        _run_with_retry = _import_run_with_retry()
        exc = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="fail")

        with patch("subprocess.run", side_effect=exc) as mock_run, \
             patch("time.sleep"):
            with pytest.raises(RuntimeError):
                _run_with_retry(["ffmpeg"], retries=2, wait_sec=0.0)

        assert mock_run.call_count == 3  # 1 initial + 2 retries

    def test_no_raise_on_first_attempt_when_second_succeeds(self):
        """If the command succeeds on retry, no exception must be raised."""
        _run_with_retry = _import_run_with_retry()
        fail_exc = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="transient")
        ok_result = MagicMock()
        ok_result.returncode = 0

        with patch("subprocess.run", side_effect=[fail_exc, ok_result]), \
             patch("time.sleep"):
            result = _run_with_retry(["ffmpeg"], retries=2, wait_sec=0.0)

        assert result is ok_result

    def test_empty_stderr_raises_without_crash(self):
        """An empty stderr string must not cause a crash — RuntimeError still raised."""
        _run_with_retry = _import_run_with_retry()
        exc = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="")

        with patch("subprocess.run", side_effect=exc), \
             patch("time.sleep"):
            with pytest.raises(RuntimeError) as exc_info:
                _run_with_retry(["ffmpeg"], retries=1, wait_sec=0.0)

        # Message must at least mention the exit code
        assert "exit=1" in str(exc_info.value) or "FFmpeg failed" in str(exc_info.value)

    def test_none_stderr_raises_without_crash(self):
        """stderr=None (some OS edge cases) must not cause an AttributeError."""
        _run_with_retry = _import_run_with_retry()
        exc = subprocess.CalledProcessError(1, ["ffmpeg"])
        exc.stderr = None

        with patch("subprocess.run", side_effect=exc), \
             patch("time.sleep"):
            with pytest.raises(RuntimeError):
                _run_with_retry(["ffmpeg"], retries=1, wait_sec=0.0)

    def test_non_calledprocesserror_reraises_after_retries(self):
        """A plain OSError (e.g. ffmpeg binary not found) must also be retried
        and re-raised after exhausting retries."""
        _run_with_retry = _import_run_with_retry()

        with patch("subprocess.run", side_effect=OSError("no such file")), \
             patch("time.sleep") as mock_sleep:
            with pytest.raises(OSError):
                _run_with_retry(["ffmpeg"], retries=2, wait_sec=0.0)

        # sleep must have been called once per retry (not on the final attempt)
        assert mock_sleep.call_count == 2

    def test_retries_1_means_two_total_attempts(self):
        """retries=1 means one initial attempt + one retry = two total calls."""
        _run_with_retry = _import_run_with_retry()
        exc = subprocess.CalledProcessError(1, ["ffmpeg"], stderr="err")

        with patch("subprocess.run", side_effect=exc) as mock_run, \
             patch("time.sleep"):
            with pytest.raises(RuntimeError):
                _run_with_retry(["ffmpeg"], retries=1, wait_sec=0.0)

        assert mock_run.call_count == 2
