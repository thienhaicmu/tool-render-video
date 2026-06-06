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


def _extract_retry_after(exc: Exception) -> Optional[float]:
    """Best-effort extraction of Retry-After from an SDK exception.

    Returns a float number of seconds to sleep, or None if no hint found.
    Recognises:
    - ``retry_after`` attribute (Anthropic SDK exposes this on some errors)
    - ``response.headers['retry-after']`` (httpx-based SDKs)
    - ``response.headers['Retry-After']``
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
