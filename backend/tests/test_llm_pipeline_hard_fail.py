"""Hard-fail tests for run_llm_pre_render (audit FINDING-TEST03).

llm_pipeline.py is an ORCHESTRATION module — distinct from the AI provider
modules which follow Sacred Contract #3 (return None, never raise). The
orchestrator must raise LLMPipelineError on any precondition failure so
the render-pipeline caller can fail the job and report a structured error.

These tests pin every documented hard-fail site. A regression that turned
any of these into silent None returns would corrupt the FE error-handling
contract (the FE would see a "completed" job with no clips).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from app.features.render.engine.pipeline import llm_pipeline as lp
from app.features.render.engine.pipeline.llm_pipeline import (
    LLMPipelineError,
    run_llm_pre_render,
)


class _CancelRegistry:
    """Stub for the cancel_registry parameter; mirrors the public surface
    that run_llm_pre_render touches.
    """

    class JobCancelledError(Exception):
        pass

    def __init__(self, cancelled: bool = False):
        self._cancelled = cancelled

    def is_cancelled(self, job_id: str) -> bool:
        return self._cancelled


class _Payload:
    """Minimal RenderRequest stand-in.

    Only the attributes touched by run_llm_pre_render are declared; everything
    else returns None via __getattr__ so the real code paths don't blow up.
    """

    def __init__(self, **overrides):
        defaults = {
            "llm_enabled": True,
            "multi_variant": False,
            "ai_provider": "gemini",
            "gemini_api_key": "",
            "openai_api_key": "",
            "claude_api_key": "",
            "ai_cloud_api_key": "",
            "resume_from_last": False,
            "subtitle_transcription_engine": "default",
            "llm_language": None,
            "highlight_per_word": False,
            "llm_min_quality": 0.6,
            "clip_exclude": None,
            "clip_lock": None,
            "min_part_sec": 15,
            "max_part_sec": 60,
            "target_platform": "youtube_shorts",
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            setattr(self, k, v)

    def __getattr__(self, name: str) -> Any:
        # Attribute fall-through: getattr(payload, "unknown", default) works.
        return None


@pytest.fixture
def baseline(monkeypatch, tmp_path):
    """Provide the default-success scaffolding for run_llm_pre_render.

    Each test customises ONE mock to exercise the matching hard-fail site.
    The fixture returns a callable that runs the pipeline with the standard
    kwargs after any further monkey-patches the test wants to apply.
    """
    source_path = tmp_path / "source.mp4"
    source_path.write_bytes(b"\x00" * 4096)

    work_dir = tmp_path / "work"
    work_dir.mkdir()

    # Default mocks: audio stream present, transcription writes a non-empty
    # SRT, LLM returns 2 sane segments.
    monkeypatch.setattr(lp, "has_audio_stream", lambda _src: True)

    def _fake_transcribe(src, dst, *args, **kwargs):
        Path(dst).write_text("1\n00:00:00,000 --> 00:00:05,000\nhello\n", encoding="utf-8")

    monkeypatch.setattr(lp, "transcribe_with_adapter", _fake_transcribe)
    monkeypatch.setattr(lp, "_transcription_cache_get", lambda *a, **kw: None)
    monkeypatch.setattr(lp, "_transcription_cache_put", lambda *a, **kw: None)
    # Silence DB + event side effects so tests don't write to real logs/DB.
    monkeypatch.setattr(lp, "update_job_progress", lambda *a, **kw: None)
    monkeypatch.setattr(lp, "_emit_render_event", lambda **kw: None)
    monkeypatch.setattr(lp, "_job_log", lambda *a, **kw: None)
    monkeypatch.setattr(lp, "_safe_unlink", lambda *a, **kw: None)

    # Give the heartbeat thread something resembling immediate exit.
    # _hb_fn waits on a threading.Event, so the test path returns quickly.
    monkeypatch.setattr(lp.threading, "Thread", _NoopThread)

    # ADR-007 (2026-06-27): run_llm_pre_render now wraps transcribe_with_adapter
    # in run_with_hard_timeout. That helper uses ThreadPoolExecutor internally,
    # which itself spawns threads via threading.Thread — and the above patch
    # turns ALL Thread() calls into no-ops, deadlocking the helper's future.
    # In tests, bypass the helper entirely: call fn() synchronously in the
    # caller's thread (no executor, no daemon). Faithfully exercises the
    # transcribe mock + the exception paths around it; the daemon/timeout
    # behaviour is covered by tests/test_whisper_timeout.py instead.
    def _sync_run(fn, **kwargs):
        return fn()

    monkeypatch.setattr(lp, "run_with_hard_timeout", _sync_run)

    # Provide an API key in the env-side config so the no-key check passes
    # for the default-success test. Individual tests override.
    from app.core import config as _cfg
    monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "test-key-not-used-by-mock", raising=False)
    monkeypatch.setattr(_cfg, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(_cfg, "CLAUDE_API_KEY", "", raising=False)
    monkeypatch.setattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini", raising=False)

    source = {"slug": "src", "duration": 120.0}

    def _run(payload=None, **extra_kwargs):
        kwargs = dict(
            source_path=source_path,
            source=source,
            work_dir=work_dir,
            payload=payload or _Payload(),
            tuned={"whisper_model": "tiny"},
            job_id="job-0001",
            effective_channel="test",
            retry_count=0,
            cancel_registry=_CancelRegistry(),
            set_stage_fn=lambda *a, **kw: None,
        )
        kwargs.update(extra_kwargs)
        return run_llm_pre_render(**kwargs)

    return _run


class _NoopThread:
    """Thread stub that never actually runs — the heartbeat is irrelevant
    for these tests and a real Thread would slow them down.
    """

    def __init__(self, *args, **kwargs):
        # Accept and ignore target / args / kwargs / daemon / name.
        pass

    def start(self):
        return None

    def join(self, timeout=None):
        return None


# ---------------------------------------------------------------------------
# Happy path — baseline succeeds
# ---------------------------------------------------------------------------

def test_happy_path_returns_result(baseline):
    result = baseline()
    assert result.scored == []
    assert result.total_parts == 0
    assert result.full_srt.exists()
    assert result.early_transcription_done is True


# ---------------------------------------------------------------------------
# Hard-fail #1 — no API key on payload AND no API key in env
# ---------------------------------------------------------------------------

def test_no_api_key_raises_llm_pipeline_error(baseline, monkeypatch):
    from app.core import config as _cfg
    monkeypatch.setattr(_cfg, "GEMINI_API_KEY", "", raising=False)
    monkeypatch.setattr(_cfg, "OPENAI_API_KEY", "", raising=False)
    monkeypatch.setattr(_cfg, "CLAUDE_API_KEY", "", raising=False)
    # _resolve_api_key reads os.getenv() directly — clear env vars too
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_API_KEY", raising=False)

    with pytest.raises(LLMPipelineError) as exc_info:
        baseline()
    assert "api key" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Hard-fail #2 — source video has no audio stream
# ---------------------------------------------------------------------------

def test_no_audio_stream_raises(baseline, monkeypatch):
    monkeypatch.setattr(lp, "has_audio_stream", lambda _src: False)
    with pytest.raises(LLMPipelineError) as exc_info:
        baseline()
    assert "audio stream" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Cancel — must surface as JobCancelledError, NOT LLMPipelineError
# ---------------------------------------------------------------------------

def test_cancelled_during_preflight_propagates(baseline):
    """A cancel signal must surface as the registry's JobCancelledError so
    the caller can short-circuit the render. LLMPipelineError would be wrong
    because nothing actually failed.
    """
    with pytest.raises(_CancelRegistry.JobCancelledError):
        baseline(cancel_registry=_CancelRegistry(cancelled=True))


# ---------------------------------------------------------------------------
# Hard-fail #3 — Whisper transcription raises
# ---------------------------------------------------------------------------

def test_whisper_transcribe_failure_raises(baseline, monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("simulated whisper crash")

    monkeypatch.setattr(lp, "transcribe_with_adapter", _boom)
    with pytest.raises(LLMPipelineError) as exc_info:
        baseline()
    msg = str(exc_info.value).lower()
    assert "transcription" in msg or "whisper" in msg


# ---------------------------------------------------------------------------
# Hard-fail #4 — SRT is empty / missing after transcription
# ---------------------------------------------------------------------------

def test_empty_srt_after_transcription_raises(baseline, monkeypatch):
    def _writes_empty(src, dst, *args, **kwargs):
        Path(dst).write_text("", encoding="utf-8")

    monkeypatch.setattr(lp, "transcribe_with_adapter", _writes_empty)
    with pytest.raises(LLMPipelineError) as exc_info:
        baseline()
    assert "srt" in str(exc_info.value).lower()


