"""Tests for whisper_timeout.run_with_hard_timeout."""
import threading
import time

import pytest

from app.jobs.cancel import JobCancelledError
from app.jobs.whisper_timeout import run_with_hard_timeout


def test_normal_completion_returns_value():
    out = run_with_hard_timeout(lambda: 42, timeout_sec=120, name="t-ok")
    assert out == 42


def test_timeout_raises_when_fn_takes_too_long():
    def _slow():
        # Loop sleeping until killed — never returns on its own.
        for _ in range(1000):
            time.sleep(0.1)
        return "never"

    t0 = time.perf_counter()
    with pytest.raises(TimeoutError):
        run_with_hard_timeout(_slow, timeout_sec=2, name="t-timeout")
    elapsed = time.perf_counter() - t0
    # Hard timeout 2s, poll cadence 1s — should fire within ~3s.
    assert elapsed < 5.0, f"timeout fired too late: {elapsed:.2f}s"


def test_cancel_event_set_raises_job_cancelled():
    cancel_ev = threading.Event()

    # Schedule the cancel to fire after a short delay
    def _trigger():
        time.sleep(0.5)
        cancel_ev.set()

    threading.Thread(target=_trigger, daemon=True).start()

    def _slow():
        for _ in range(1000):
            time.sleep(0.1)

    with pytest.raises(JobCancelledError):
        run_with_hard_timeout(
            _slow, timeout_sec=120, cancel_event=cancel_ev, name="t-cancel",
        )


def test_fn_exception_propagates():
    class MyErr(RuntimeError):
        pass

    def _boom():
        raise MyErr("explode")

    with pytest.raises(MyErr, match="explode"):
        run_with_hard_timeout(_boom, timeout_sec=120, name="t-exc")


def test_bind_tls_installs_cancel_event_in_daemon_thread():
    # Verify the daemon thread's TLS gets the cancel_event so any
    # ffmpeg_helpers.check_thread_cancel() call inside fn would see it.
    from app.features.render.engine.encoder.ffmpeg_helpers import (
        get_thread_cancel_event,
    )

    cancel_ev = threading.Event()
    captured: dict = {}

    def _fn():
        captured["ev"] = get_thread_cancel_event()
        return "ok"

    out = run_with_hard_timeout(
        _fn, timeout_sec=120, cancel_event=cancel_ev, name="t-tls",
    )
    assert out == "ok"
    assert captured["ev"] is cancel_ev


def test_bind_tls_false_does_not_install():
    from app.features.render.engine.encoder.ffmpeg_helpers import (
        get_thread_cancel_event,
    )

    cancel_ev = threading.Event()
    captured: dict = {}

    def _fn():
        captured["ev"] = get_thread_cancel_event()
        return "ok"

    out = run_with_hard_timeout(
        _fn, timeout_sec=120, cancel_event=cancel_ev, name="t-no-tls", bind_tls=False,
    )
    assert out == "ok"
    # In the daemon thread without bind_tls, TLS slot is empty (None).
    assert captured["ev"] is None
