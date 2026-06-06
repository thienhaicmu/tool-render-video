"""Tests for the NVENC argv-detector and centralized semaphore (audit R01/BR04).

The contract: any FFmpeg invocation whose argv uses an NVENC encoder
codec MUST acquire NVENC_SEMAPHORE before running. The centralization
lives in _run_ffmpeg_with_retry, gated by _argv_uses_nvenc.

These tests pin two properties:
1. _argv_uses_nvenc correctly detects every codec in the curated
   NVENC_CODECS set and rejects unrelated tokens (no false positives).
2. The acquire/release flow is balanced — _run_ffmpeg_with_retry must
   not leak a semaphore slot when the underlying subprocess fails or
   succeeds, and must NOT acquire when nvenc_externally_held=True.
"""
from __future__ import annotations

import subprocess

import pytest

from app.features.render.engine.encoder.ffmpeg_helpers import (
    NVENC_CODECS,
    NVENC_SEMAPHORE,
    _argv_uses_nvenc,
)

# Pre-import the metrics module so the prometheus_client platform_collector
# completes its own (subprocess-backed) initialization BEFORE the tests
# monkey-patch subprocess.Popen. Without this, the lazy import inside
# _run_ffmpeg_with_retry triggers prometheus's startup `Popen` call under
# the patched class and fails with "not a context manager".
from app.services import metrics as _metrics_preload  # noqa: F401


# ---------------------------------------------------------------------------
# _argv_uses_nvenc
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("codec", sorted(NVENC_CODECS))
def test_argv_uses_nvenc_detects_each_codec(codec: str):
    argv = ["ffmpeg", "-i", "in.mp4", "-c:v", codec, "out.mp4"]
    assert _argv_uses_nvenc(argv) is True


@pytest.mark.parametrize(
    "argv",
    [
        ["ffmpeg", "-i", "in.mp4", "-c:v", "libx264", "out.mp4"],
        ["ffmpeg", "-i", "in.mp4", "-c:v", "libx265", "out.mp4"],
        ["ffmpeg", "-i", "in.mp4", "-c", "copy", "out.mp4"],
        ["ffmpeg", "-i", "in.mp4", "out.mp4"],
        [],
    ],
)
def test_argv_uses_nvenc_negative_cases(argv: list[str]):
    assert _argv_uses_nvenc(argv) is False


def test_argv_uses_nvenc_no_false_positive_on_filename():
    """A path/filename that contains the substring '_nvenc' must not
    trigger NVENC semaphore acquisition.

    Pre-Batch-3 the detector did `"_nvenc" in token.lower()` and would
    incorrectly fire on benign paths like /tmp/render_nvenc.mp4 — wasting
    the GPU semaphore on a libx264 encode.
    """
    argv = [
        "ffmpeg",
        "-i", "/tmp/source_my_nvenc_backup.mp4",
        "-c:v", "libx264",
        "/output/segment_nvenc_capable.mp4",
    ]
    assert _argv_uses_nvenc(argv) is False


def test_argv_uses_nvenc_tolerates_nonstring_tokens():
    """Mixed-type argvs (numbers, paths, None) must not raise."""
    argv = ["ffmpeg", 123, None, "-c:v", "libx264"]
    assert _argv_uses_nvenc(argv) is False


def test_argv_uses_nvenc_detects_codec_among_many_tokens():
    """The codec token may appear deep in a long argv."""
    argv = (
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", "in.mp4"]
        + ["-filter_complex", "[0:v]scale=1080:1920[v]", "-map", "[v]", "-map", "0:a"]
        + ["-c:a", "aac", "-b:a", "192k", "-c:v", "h264_nvenc", "-preset", "p4"]
        + ["out.mp4"]
    )
    assert _argv_uses_nvenc(argv) is True


# ---------------------------------------------------------------------------
# Semaphore balance under _run_ffmpeg_with_retry
# ---------------------------------------------------------------------------

def _semaphore_count() -> int:
    """Return the number of permits currently available on NVENC_SEMAPHORE.

    Implementation note: threading.Semaphore._value is private but stable
    across CPython releases; we read it for diagnostic balance checks
    and never mutate it.
    """
    return NVENC_SEMAPHORE._value  # type: ignore[attr-defined]


def _make_dummy_completed_process(returncode: int = 0):
    return subprocess.CompletedProcess(args=["dummy"], returncode=returncode)


def test_nvenc_balance_under_success(monkeypatch):
    """On a successful FFmpeg call with NVENC argv, the semaphore must
    end with exactly the same available count as it started.
    """
    from app.features.render.engine.encoder import ffmpeg_helpers as fh

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            self.returncode = 0

        def communicate(self):
            return ("stdout", "")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(fh.subprocess, "Popen", _FakePopen)

    before = _semaphore_count()
    fh._run_ffmpeg_with_retry(["ffmpeg", "-c:v", "h264_nvenc", "out.mp4"])
    after = _semaphore_count()
    assert before == after


def test_nvenc_balance_under_failure(monkeypatch):
    """On a failing FFmpeg call (non-zero exit, all retries exhausted),
    the semaphore must still be released. A leak here would slowly
    starve all subsequent NVENC renders.
    """
    from app.features.render.engine.encoder import ffmpeg_helpers as fh

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            self.returncode = 1

        def communicate(self):
            return ("", "boom")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(fh.subprocess, "Popen", _FakePopen)

    before = _semaphore_count()
    with pytest.raises(RuntimeError):
        fh._run_ffmpeg_with_retry(
            ["ffmpeg", "-c:v", "h264_nvenc", "out.mp4"],
            retry_count=0,
            wait_sec=0,
        )
    after = _semaphore_count()
    assert before == after


def test_nvenc_skip_acquire_when_externally_held(monkeypatch):
    """nvenc_externally_held=True must skip the internal acquire path —
    the caller is responsible for the semaphore. We verify by asserting
    the available count never dips during the call.
    """
    from app.features.render.engine.encoder import ffmpeg_helpers as fh

    observed_counts: list[int] = []

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            observed_counts.append(_semaphore_count())

        def communicate(self):
            return ("", "")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(fh.subprocess, "Popen", _FakePopen)

    before = _semaphore_count()
    fh._run_ffmpeg_with_retry(
        ["ffmpeg", "-c:v", "h264_nvenc", "out.mp4"],
        nvenc_externally_held=True,
    )
    after = _semaphore_count()
    assert before == after
    # During the run, the count must equal the starting count — the
    # helper did NOT acquire.
    assert all(c == before for c in observed_counts)


def test_no_acquire_when_argv_has_no_nvenc(monkeypatch):
    """A libx264 (or unspecified codec) call must not touch the semaphore."""
    from app.features.render.engine.encoder import ffmpeg_helpers as fh

    observed_counts: list[int] = []

    class _FakePopen:
        def __init__(self, *args, **kwargs):
            self.returncode = 0
            observed_counts.append(_semaphore_count())

        def communicate(self):
            return ("", "")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(fh.subprocess, "Popen", _FakePopen)

    before = _semaphore_count()
    fh._run_ffmpeg_with_retry(["ffmpeg", "-c:v", "libx264", "out.mp4"])
    after = _semaphore_count()
    assert before == after
    assert all(c == before for c in observed_counts)
