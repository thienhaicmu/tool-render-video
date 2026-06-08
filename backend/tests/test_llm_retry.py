"""Tests for the LLM call retry wrapper (audit FINDING-AI05 / BR02)."""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.features.render.ai.llm.retry import (
    DEFAULT_MAX_ATTEMPTS,
    call_with_retry,
    _extract_google_retry_info,
    _extract_retry_after,
    _parse_protobuf_duration,
)


# ---------------------------------------------------------------------------
# _parse_protobuf_duration — Google serialises Duration as "<number>s"
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("38s", 38.0),
        ("38.8s", 38.8),
        ("38.800581929s", 38.800581929),
        ("0s", 0.0),
        ("0.5s", 0.5),
        (38, 38.0),
        (38.8, 38.8),
        ("", None),
        (None, None),
        ("not-a-number", None),
        ("38xs", None),
    ],
)
def test_parse_protobuf_duration(raw, want):
    got = _parse_protobuf_duration(raw)
    if want is None:
        assert got is None
    else:
        assert got == pytest.approx(want)


# ---------------------------------------------------------------------------
# _extract_google_retry_info — three places google-genai / google.api_core
# expose the structured error body
# ---------------------------------------------------------------------------

_RETRY_INFO_ENTRY = {
    "@type": "type.googleapis.com/google.rpc.RetryInfo",
    "retryDelay": "38.8s",
}
_HELP_ENTRY = {
    "@type": "type.googleapis.com/google.rpc.Help",
    "links": [{"description": "x", "url": "y"}],
}
_QUOTA_ENTRY = {
    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
    "violations": [],
}


def test_google_retry_info_from_details_list_attr():
    """google.api_core ResourceExhausted carries the list as an attribute."""
    exc = RuntimeError("quota")
    exc.details = [_HELP_ENTRY, _QUOTA_ENTRY, _RETRY_INFO_ENTRY]  # type: ignore[attr-defined]
    assert _extract_google_retry_info(exc) == pytest.approx(38.8)


def test_google_retry_info_from_details_callable():
    """google.api_core.exceptions.GoogleAPICallError.details() is a method."""
    exc = RuntimeError("quota")
    exc.details = lambda: [_RETRY_INFO_ENTRY]  # type: ignore[attr-defined]
    assert _extract_google_retry_info(exc) == pytest.approx(38.8)


def test_google_retry_info_from_body_dict():
    """google-genai ClientError sometimes stores the response body as a dict."""
    exc = RuntimeError("quota")
    exc.body = {  # type: ignore[attr-defined]
        "error": {
            "code": 429,
            "message": "Quota exceeded",
            "status": "RESOURCE_EXHAUSTED",
            "details": [_HELP_ENTRY, _RETRY_INFO_ENTRY],
        }
    }
    assert _extract_google_retry_info(exc) == pytest.approx(38.8)


def test_google_retry_info_accepts_snake_case():
    """The protobuf snake_case `retry_delay` form is also valid."""
    exc = RuntimeError("quota")
    exc.details = [{  # type: ignore[attr-defined]
        "@type": "type.googleapis.com/google.rpc.RetryInfo",
        "retry_delay": "5s",
    }]
    assert _extract_google_retry_info(exc) == pytest.approx(5.0)


def test_google_retry_info_returns_none_when_absent():
    exc = RuntimeError("no RetryInfo here")
    exc.details = [_HELP_ENTRY, _QUOTA_ENTRY]  # type: ignore[attr-defined]
    assert _extract_google_retry_info(exc) is None


def test_google_retry_info_returns_none_when_details_not_list():
    exc = RuntimeError("no details")
    assert _extract_google_retry_info(exc) is None


# ---------------------------------------------------------------------------
# _extract_retry_after — preserves prior precedence; Google fallback last
# ---------------------------------------------------------------------------

def test_retry_after_prefers_attribute_over_google_details():
    """When BOTH an explicit retry_after attribute AND a Google RetryInfo
    are present, the attribute wins (it's the more direct signal).
    """
    exc = RuntimeError("both")
    exc.retry_after = 4  # type: ignore[attr-defined]
    exc.details = [_RETRY_INFO_ENTRY]  # type: ignore[attr-defined]
    # _RETRY_INFO_ENTRY says 38.8s, but the explicit attribute wins at 4.
    assert _extract_retry_after(exc) == 4.0


def test_retry_after_falls_back_to_google_details():
    """When no header / attribute is present, the Google RetryInfo is used."""
    exc = RuntimeError("google-only")
    exc.details = [_RETRY_INFO_ENTRY]  # type: ignore[attr-defined]
    assert _extract_retry_after(exc) == pytest.approx(38.8)


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
