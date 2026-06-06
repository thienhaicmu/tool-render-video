"""Tests for the LLM call retry wrapper (audit FINDING-AI05 / BR02)."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.features.render.ai.llm.retry import (
    DEFAULT_MAX_ATTEMPTS,
    call_with_retry,
    _extract_retry_after,
)


# ---------------------------------------------------------------------------
# _extract_retry_after
# ---------------------------------------------------------------------------

def test_retry_after_from_attribute():
    exc = RuntimeError("503")
    exc.retry_after = 4  # type: ignore[attr-defined]
    assert _extract_retry_after(exc) == 4.0


def test_retry_after_from_response_headers_lowercase():
    exc = RuntimeError("503")
    exc.response = SimpleNamespace(headers={"retry-after": "7"})  # type: ignore[attr-defined]
    assert _extract_retry_after(exc) == 7.0


def test_retry_after_from_response_headers_titlecase():
    exc = RuntimeError("503")
    exc.response = SimpleNamespace(headers={"Retry-After": "9.5"})  # type: ignore[attr-defined]
    assert _extract_retry_after(exc) == 9.5


def test_retry_after_returns_none_when_absent():
    exc = RuntimeError("no headers, no attr")
    assert _extract_retry_after(exc) is None


def test_retry_after_returns_none_on_garbage_value():
    exc = RuntimeError("bad")
    exc.retry_after = "soon-ish"  # type: ignore[attr-defined]
    assert _extract_retry_after(exc) is None


# ---------------------------------------------------------------------------
# call_with_retry — success paths
# ---------------------------------------------------------------------------

def test_first_attempt_success_no_retry():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    result = call_with_retry(fn, label="test")
    assert result == "ok"
    assert calls["n"] == 1


def test_first_attempt_returns_none_no_retry():
    """An explicit None from the SDK is a logical 'empty response'.
    Retrying would double the cost and is unlikely to change the answer.
    """
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return None

    result = call_with_retry(fn, label="test")
    assert result is None
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# call_with_retry — retry paths
# ---------------------------------------------------------------------------

def test_retries_once_on_exception_then_succeeds(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)  # skip real sleep

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient blip")
        return "rescued"

    result = call_with_retry(fn, label="test")
    assert result == "rescued"
    assert calls["n"] == 2


def test_returns_none_after_all_attempts_raise(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise RuntimeError("always-broken")

    result = call_with_retry(fn, label="test")
    assert result is None
    assert calls["n"] == DEFAULT_MAX_ATTEMPTS


def test_honours_retry_after(monkeypatch):
    """When the exception exposes Retry-After, sleep at least that long."""
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            exc = RuntimeError("503 from server")
            exc.retry_after = 3  # type: ignore[attr-defined]
            raise exc
        return "ok"

    result = call_with_retry(fn, label="test", retry_after_cap_sec=10.0)
    assert result == "ok"
    assert slept == [3.0]


def test_retry_after_is_capped(monkeypatch):
    """Retry-After must be capped so a hostile server cannot stall the loop."""
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            exc = RuntimeError("too-long")
            exc.retry_after = 999_999  # type: ignore[attr-defined]
            raise exc
        return "ok"

    result = call_with_retry(fn, label="test", retry_after_cap_sec=5.0)
    assert result == "ok"
    assert slept == [5.0]


def test_backoff_fallback_when_no_retry_after(monkeypatch):
    """No Retry-After → exponential backoff (base * 2^(attempt-1))."""
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("no Retry-After")
        return "ok"

    result = call_with_retry(fn, label="test", base_backoff_sec=2.0)
    assert result == "ok"
    # First (and only) retry uses base * 2^0 = 2.0.
    assert slept == [2.0]


def test_custom_max_attempts(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise RuntimeError("nope")

    result = call_with_retry(fn, label="test", max_attempts=4)
    assert result is None
    assert calls["n"] == 4
