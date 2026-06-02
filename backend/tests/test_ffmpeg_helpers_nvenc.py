"""test_ffmpeg_helpers_nvenc.py — Sprint 4.2.

Verifies the NVENC semaphore unification:
- _argv_uses_nvenc() correctly identifies NVENC argv tokens.
- _run_ffmpeg_with_retry acquires the semaphore for NVENC commands when
  nvenc_externally_held=False (closes the gap audit 2026-06-02 P2-B1).
- _run_ffmpeg_with_retry does NOT acquire when nvenc_externally_held=True
  (avoids double-counting at existing external sites).
- _run_ffmpeg_with_retry does NOT acquire for non-NVENC commands.

We don't run a real FFmpeg subprocess here; we patch subprocess.Popen so
the function returns immediately and we assert on semaphore state.
"""
from __future__ import annotations

import subprocess
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.services.render.ffmpeg_helpers import _argv_uses_nvenc


class TestArgvUsesNvenc:
    @pytest.mark.parametrize("token", [
        "h264_nvenc",
        "hevc_nvenc",
        "H264_NVENC",   # case-insensitive
        "av1_nvenc",
    ])
    def test_detects_nvenc_token(self, token):
        assert _argv_uses_nvenc(["ffmpeg", "-c:v", token, "out.mp4"]) is True

    @pytest.mark.parametrize("argv", [
        ["ffmpeg", "-c:v", "libx264"],
        ["ffmpeg", "-c:v", "libx265"],
        ["ffmpeg", "-c:v", "h264", "-i", "in.mp4"],
        ["ffmpeg"],
        [],
    ])
    def test_rejects_non_nvenc(self, argv):
        assert _argv_uses_nvenc(argv) is False

    def test_non_string_tokens_ignored(self):
        # Mixed-type argv (defensive — shouldn't happen in practice)
        assert _argv_uses_nvenc(["ffmpeg", 42, None, "h264_nvenc"]) is True
        assert _argv_uses_nvenc(["ffmpeg", 42, None, "libx264"]) is False


class TestRunFfmpegSemaphoreInteraction:
    """Patch subprocess + semaphore to verify acquire/release logic."""

    def _fake_proc(self):
        """Return a MagicMock that behaves like subprocess.Popen with rc=0."""
        proc = MagicMock()
        proc.communicate.return_value = ("", "")
        proc.returncode = 0
        return proc

    def test_acquires_for_nvenc_when_not_externally_held(self):
        import app.services.render.ffmpeg_helpers as fh
        sem_mock = MagicMock()
        with patch.object(fh, "NVENC_SEMAPHORE", sem_mock), \
             patch.object(fh.subprocess, "Popen", return_value=self._fake_proc()):
            fh._run_ffmpeg_with_retry(["ffmpeg", "-c:v", "h264_nvenc", "out.mp4"])
        sem_mock.acquire.assert_called_once()
        sem_mock.release.assert_called_once()

    def test_does_not_acquire_when_externally_held(self):
        import app.services.render.ffmpeg_helpers as fh
        sem_mock = MagicMock()
        with patch.object(fh, "NVENC_SEMAPHORE", sem_mock), \
             patch.object(fh.subprocess, "Popen", return_value=self._fake_proc()):
            fh._run_ffmpeg_with_retry(
                ["ffmpeg", "-c:v", "h264_nvenc", "out.mp4"],
                nvenc_externally_held=True,
            )
        sem_mock.acquire.assert_not_called()
        sem_mock.release.assert_not_called()

    def test_does_not_acquire_for_non_nvenc(self):
        import app.services.render.ffmpeg_helpers as fh
        sem_mock = MagicMock()
        with patch.object(fh, "NVENC_SEMAPHORE", sem_mock), \
             patch.object(fh.subprocess, "Popen", return_value=self._fake_proc()):
            fh._run_ffmpeg_with_retry(["ffmpeg", "-c:v", "libx264", "out.mp4"])
        sem_mock.acquire.assert_not_called()
        sem_mock.release.assert_not_called()

    def test_releases_on_subprocess_failure(self):
        """If FFmpeg exits non-zero (after retries), the semaphore must still release."""
        import app.services.render.ffmpeg_helpers as fh
        sem_mock = MagicMock()
        proc = MagicMock()
        proc.communicate.return_value = ("", "encode failed")
        proc.returncode = 1
        with patch.object(fh, "NVENC_SEMAPHORE", sem_mock), \
             patch.object(fh.subprocess, "Popen", return_value=proc), \
             patch.object(fh.time, "sleep", lambda *_args, **_kwargs: None):
            with pytest.raises(RuntimeError):
                fh._run_ffmpeg_with_retry(
                    ["ffmpeg", "-c:v", "h264_nvenc", "out.mp4"],
                    retry_count=0,
                )
        # Released exactly once, even though we raised
        sem_mock.acquire.assert_called_once()
        sem_mock.release.assert_called_once()
