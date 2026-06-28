"""whisper_timeout.py — hard-timeout + cancel-aware wrapper for Whisper.

Closes ADR-007 root cause: the job-level call to ``transcribe_with_adapter``
used to be a plain blocking call with no timeout. When Whisper got stuck
(VAD loop, corrupted audio, CUDA hang, resource contention from a
zombie cancelled-but-still-running peer), the worker thread would block
indefinitely while heartbeat logs spammed "elapsed=1700s progress=99%".

This wrapper:
  - runs ``fn`` in a daemon thread (named for log grep'ability);
  - polls ``cancel_event`` every 1 s so cancel signals propagate within
    that bound;
  - applies a hard ``timeout_sec`` deadline;
  - on timeout / cancel, raises the appropriate exception immediately
    rather than waiting for ``fn`` to notice — the daemon thread is
    left running (will die with the process) since Python has no safe
    way to kill a thread mid-blocking-call. Callers using
    ``set_thread_cancel_event`` inside ``fn`` get fast subprocess
    teardown for free (FFmpeg subprocess poll = ~50 ms exit).

Sacred Contract #3 spirit: failures are explicit (TimeoutError /
JobCancelledError) rather than silent hangs.

No new pip dependencies — pure stdlib (``concurrent.futures``,
``threading``, ``time``).
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as _FutTimeout
from typing import Callable, Optional, TypeVar

from app.jobs.cancel import JobCancelledError

logger = logging.getLogger("app.jobs.whisper_timeout")

T = TypeVar("T")

# How often the main thread checks cancel_event while waiting on fn().
# 1.0 s is small enough that cancel feels instant to the user but large
# enough that polling overhead is negligible vs Whisper's typical multi-
# minute runtime.
_POLL_INTERVAL_SEC = 1.0


def run_with_hard_timeout(
    fn: Callable[[], T],
    *,
    timeout_sec: float,
    cancel_event: Optional[threading.Event] = None,
    name: str = "whisper",
    bind_tls: bool = True,
) -> T:
    """Run ``fn()`` in a daemon thread with a hard deadline.

    Args:
        fn: zero-arg callable to execute. If ``bind_tls`` is True the
            wrapper will install ``cancel_event`` in the daemon thread's
            TLS slot via ``ffmpeg_helpers.set_thread_cancel_event`` so
            FFmpeg subprocesses spawned inside ``fn`` exit promptly when
            the event fires.
        timeout_sec: hard deadline in seconds. Callers (see
            ``llm_pipeline.run_llm_pre_render``) are expected to apply
            their own sane floor (e.g. ``max(120, 8 * video_dur)``).
        cancel_event: optional ``threading.Event``. When set during the
            wait, the wrapper raises :class:`JobCancelledError`
            immediately. ``None`` disables cancel polling.
        name: thread name (for log grep). Truncated to a sane length by
            the runtime.
        bind_tls: when True (default), wrap ``fn`` so the daemon thread
            gets its own ``set_thread_cancel_event(cancel_event)`` call
            before invoking ``fn``. Necessary because the caller's TLS
            does NOT propagate to the daemon thread.

    Returns: ``fn()``'s return value.

    Raises:
        JobCancelledError: ``cancel_event`` was set during the wait.
        TimeoutError: deadline reached before ``fn()`` returned.
        Exception: anything ``fn()`` raised internally.
    """
    deadline = float(timeout_sec)
    poll = _POLL_INTERVAL_SEC

    def _wrapped() -> T:
        # Daemon thread starts fresh — its TLS is empty. Rebind the
        # cancel_event so ffmpeg_helpers and adapter cancel polls see it.
        if bind_tls and cancel_event is not None:
            try:
                from app.features.render.engine.encoder.ffmpeg_helpers import (
                    set_thread_cancel_event,
                )
                set_thread_cancel_event(cancel_event)
            except Exception as exc:  # pragma: no cover — defensive
                logger.debug("whisper_timeout: TLS bind failed: %s", exc)
        return fn()

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=name)
    try:
        fut: Future[T] = pool.submit(_wrapped)
        elapsed = 0.0
        while True:
            try:
                return fut.result(timeout=poll)
            except _FutTimeout:
                elapsed += poll
                if cancel_event is not None and cancel_event.is_set():
                    logger.warning(
                        "whisper_timeout: cancel signal received after %.1fs (name=%s)",
                        elapsed, name,
                    )
                    raise JobCancelledError(
                        f"{name}: cancelled by user after {elapsed:.1f}s"
                    )
                if elapsed >= deadline:
                    logger.warning(
                        "whisper_timeout: hard deadline %.1fs exceeded (name=%s)",
                        deadline, name,
                    )
                    raise TimeoutError(
                        f"{name}: exceeded hard timeout of {deadline:.0f}s"
                    )
                # Continue polling — fn is still running.
    finally:
        # Don't block on shutdown — the daemon thread will be reaped by
        # the executor on its own (or by process exit). cancel_futures=True
        # marks any queued (not-yet-running) future for non-execution.
        pool.shutdown(wait=False, cancel_futures=True)
