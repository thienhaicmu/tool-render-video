"""Tiny retry wrapper for cloud LLM provider calls.

Closes audit FINDING-AI05 / BR02: before this module each provider's
``_call_*`` helper made exactly one HTTP request; a single transient
network blip from Claude / OpenAI / Gemini killed an active render job
(the orchestrator above treats ``None`` as hard-fail).

Design constraints:
- Sacred Contract #3 — the public-boundary contract is unchanged: the
  wrapped function still returns ``None`` on exhaustion, never raises.
- Backwards compatible — the wrapper is opt-in per call site; existing
  no-retry behaviour is the default.
- SDK-agnostic — Anthropic, OpenAI and google-genai each ship their own
  exception hierarchies. We catch the broad ``Exception`` (matching the
  pre-existing per-provider try/except) rather than enumerate SDK
  classes that may change between releases.
- Retry-After honour — when the raised exception exposes the header
  value via a common attribute or ``response.headers``, we sleep for
  the requested duration (capped) before the second attempt. Otherwise
  we use a small exponential backoff.

Attempts and sleeps are deliberately conservative: a render job is a
long-running, high-cost operation, so spending up to a few seconds on a
single retry is cheaper than the user re-submitting a 40-minute render.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional, TypeVar

logger = logging.getLogger("app.render.llm.retry")

T = TypeVar("T")

# Conservative defaults — tunable later via env if needed.
DEFAULT_MAX_ATTEMPTS = 2     # = 1 retry after the initial attempt
DEFAULT_BACKOFF_SEC = 2.0    # base sleep for backoff fallback
DEFAULT_RETRY_AFTER_CAP_SEC = 15.0  # never sleep longer than this on Retry-After


_GOOGLE_RETRY_INFO_TYPE = "type.googleapis.com/google.rpc.RetryInfo"


def _parse_protobuf_duration(raw) -> Optional[float]:
    """Parse a Google protobuf Duration string into seconds.

    The serialised form is `"<number>s"` (e.g. `"38s"`, `"38.8s"`,
    `"38.800581929s"`). Returns None for any value that doesn't match.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("s"):
        s = s[:-1]
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _extract_google_retry_info(exc: Exception) -> Optional[float]:
    """Find a RetryInfo entry in a Google-style structured error body.

    Closes audit IM-6-followup (post-smoke-test gap). The Google AI Studio
    `RESOURCE_EXHAUSTED` response carries the retry hint in a structured
    ``details`` list of error messages — NOT in the HTTP `Retry-After`
    header. Example payload observed during the 2026-06-06 smoke run:

        'details': [
            {'@type': 'type.googleapis.com/google.rpc.Help', ...},
            {'@type': 'type.googleapis.com/google.rpc.QuotaFailure', ...},
            {'@type': 'type.googleapis.com/google.rpc.RetryInfo',
             'retryDelay': '38.800581929s'},
        ]

    This helper probes several shapes the google-genai / google.api_core
    SDKs use to expose that list, and parses the protobuf Duration value.
    """
    # The list may be on the exception itself (google.api_core.exceptions)
    # or stringified inside exc.message for google.genai.errors.ClientError.
    candidates = []

    direct = getattr(exc, "details", None)
    if isinstance(direct, list):
        candidates.append(direct)
    elif callable(direct):
        # google.api_core.exceptions.GoogleAPICallError.details() is a callable
        # that returns the list.
        try:
            value = direct()
        except Exception:  # pragma: no cover — defensive
            value = None
        if isinstance(value, list):
            candidates.append(value)

    # Some SDKs expose the structured body inside a wrapping dict.
    for attr in ("response_json", "error_details", "body"):
        v = getattr(exc, attr, None)
        if isinstance(v, dict):
            err = v.get("error") if isinstance(v.get("error"), dict) else None
            inner = (err or v).get("details")
            if isinstance(inner, list):
                candidates.append(inner)

    for details in candidates:
        for entry in details:
            if not isinstance(entry, dict):
                continue
            if entry.get("@type") != _GOOGLE_RETRY_INFO_TYPE:
                continue
            # The field is `retryDelay` in JSON / camelCase, `retry_delay`
            # in protobuf snake_case. Accept either.
            raw = entry.get("retryDelay") or entry.get("retry_delay")
            parsed = _parse_protobuf_duration(raw)
            if parsed is not None:
                return parsed

    return None


def _extract_retry_after(exc: Exception) -> Optional[float]:
    """Best-effort extraction of Retry-After from an SDK exception.

    Returns a float number of seconds to sleep, or None if no hint found.
    Recognises:
    - ``retry_after`` attribute (Anthropic SDK exposes this on some errors)
    - ``response.headers['retry-after']`` (httpx-based SDKs)
    - ``response.headers['Retry-After']``
    - Google `RetryInfo` inside a structured error ``details`` list
      (closes audit IM-6-followup discovered during the 2026-06-06 smoke run).
    """
    # 1. Direct attribute
    val = getattr(exc, "retry_after", None)
    if val is not None:
        try:
            return float(val)
        except (TypeError, ValueError):
            pass

    # 2. response.headers — common httpx pattern (OpenAI, Anthropic, google-genai)
    response = getattr(exc, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None) or {}
        # httpx Headers is case-insensitive, but a plain dict may not be.
        for key in ("retry-after", "Retry-After"):
            raw = headers.get(key) if hasattr(headers, "get") else None
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    pass

    # 3. Google-style structured error body (RetryInfo entry in details list).
    google_hint = _extract_google_retry_info(exc)
    if google_hint is not None:
        return google_hint

    return None


def call_with_retry(
    fn: Callable[[], T],
    *,
    label: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_backoff_sec: float = DEFAULT_BACKOFF_SEC,
    retry_after_cap_sec: float = DEFAULT_RETRY_AFTER_CAP_SEC,
) -> Optional[T]:
    """Run ``fn`` up to ``max_attempts`` times, honouring Retry-After.

    Returns the first successful (non-None) result. If every attempt
    raises OR returns None, returns None and logs at WARNING. Never
    propagates the exception.

    ``label`` is the provider name used in log lines, e.g. ``"claude"``.
    """
    assert max_attempts >= 1
    last_exc: Optional[BaseException] = None

    for attempt in range(1, max_attempts + 1):
        try:
            result = fn()
        except BaseException as exc:  # noqa: BLE001 — broad on purpose
            last_exc = exc
            if attempt >= max_attempts:
                # Match the pre-existing pattern: swallow and return None.
                logger.warning(
                    "%s_client: API call failed after %d attempt(s) — %s",
                    label, attempt, exc,
                )
                return None

            # Decide how long to wait before the next attempt.
            retry_after = _extract_retry_after(exc)
            if retry_after is not None and retry_after > 0:
                sleep_sec = min(retry_after, retry_after_cap_sec)
                logger.info(
                    "%s_client: attempt %d/%d raised %s — honouring Retry-After=%.2fs (capped at %.1fs)",
                    label, attempt, max_attempts, type(exc).__name__,
                    retry_after, retry_after_cap_sec,
                )
            else:
                # Exponential backoff: 2s, 4s, 8s, ... (capped indirectly by max_attempts).
                sleep_sec = base_backoff_sec * (2 ** (attempt - 1))
                logger.info(
                    "%s_client: attempt %d/%d raised %s — backing off %.1fs",
                    label, attempt, max_attempts, type(exc).__name__, sleep_sec,
                )
            time.sleep(sleep_sec)
            continue

        # Successful (or None) — return as-is. A None result is a logical
        # failure (e.g. empty completion) and the orchestrator handles it.
        if result is not None:
            return result
        # If the underlying fn returned None *without* raising, do not
        # retry: that path means the SDK responded but the response was
        # empty/unparseable, which is unlikely to change on a re-try and
        # we don't want to double the cost.
        return None

    # Unreachable in practice (loop returns above); satisfies the type checker.
    if last_exc is not None:
        logger.debug("%s_client: retry loop exited with last_exc=%r", label, last_exc)
    return None
