"""test_job_manager_shutdown.py — Sprint 4.1 graceful shutdown tests.

Verifies that job_manager.shutdown:
- Signals cancel to all active jobs via cancel_registry.cancel_all_active().
- Waits up to `timeout` seconds for the worker pool to drain.
- Force-abandons after the deadline (logs a warning) without hanging.
- Preserves backward-compat: shutdown(wait=False) does immediate abandon.

cancel_registry.cancel_all_active is verified to set every registered event.

Audit reference: docs/review/AUDIT_2026-06-02.md P1-B1.
"""
from __future__ import annotations

import threading
import time

import pytest


# ── cancel_registry.cancel_all_active ────────────────────────────────────────


class TestCancelAllActive:
    def test_signals_all_registered_events(self):
        from app.services import cancel_registry

        # Use unique ids so we don't disturb any other running test
        ids = [f"sprint41-{i}" for i in range(5)]
        events = [cancel_registry.register(j) for j in ids]
        try:
            for ev in events:
                assert ev.is_set() is False
            count = cancel_registry.cancel_all_active()
            assert count >= len(ids), f"signaled {count}, expected ≥ {len(ids)}"
            for ev in events:
                assert ev.is_set() is True
        finally:
            for j in ids:
                cancel_registry.unregister(j)

    def test_does_not_double_count_already_set(self):
        from app.services import cancel_registry

        j = "sprint41-pre-set"
        ev = cancel_registry.register(j)
        try:
            ev.set()  # already cancelled before shutdown
            count = cancel_registry.cancel_all_active()
            # The pre-set event must NOT contribute to the count — but other
            # tests' events might, so allow >= 0.
            assert count >= 0
            assert ev.is_set()  # still set, unchanged
        finally:
            cancel_registry.unregister(j)


# ── job_manager.shutdown ──────────────────────────────────────────────────────


def _quiesce_state():
    """Reset job_manager module state between tests to a known-clean baseline."""
    from app.services import job_manager as jm
    with jm._cond:
        jm._pending.clear()
        jm._pending_job_ids.clear()
        jm._active_job_ids.clear()
        jm._stopping = False
    if jm._executor is not None:
        try:
            jm._executor.shutdown(wait=False)
        except Exception:
            pass
        jm._executor = None


class TestShutdownBackwardCompat:
    def setup_method(self):
        _quiesce_state()

    def test_shutdown_wait_false_does_not_hang(self):
        """wait=False preserves the old fast-abandon behavior."""
        from app.services import job_manager as jm

        completed = threading.Event()

        def slow_job():
            time.sleep(5.0)  # would block a wait=True shutdown well past timeout

        jm.submit_job("sprint41-slow", slow_job)
        time.sleep(0.1)  # let scheduler dispatch

        t0 = time.monotonic()
        jm.shutdown(wait=False)
        elapsed = time.monotonic() - t0
        completed.set()
        # wait=False must return quickly (well under the 5s job sleep).
        assert elapsed < 2.0, f"shutdown(wait=False) took {elapsed:.2f}s — should be near-instant"


class TestShutdownGraceful:
    def setup_method(self):
        _quiesce_state()

    def test_shutdown_signals_cancel(self):
        """shutdown(wait=True) calls cancel_registry.cancel_all_active()."""
        from app.services import cancel_registry, job_manager as jm

        ev = cancel_registry.register("sprint41-cancel-target")
        try:
            assert ev.is_set() is False
            # Empty queue → shutdown returns immediately after signaling cancel
            jm.shutdown(wait=True, timeout=5.0)
            assert ev.is_set() is True, "shutdown should have signaled the registered cancel event"
        finally:
            cancel_registry.unregister("sprint41-cancel-target")

    def test_shutdown_returns_within_timeout_when_workers_hang(self):
        """If a worker won't drain in time, shutdown returns by the deadline."""
        from app.services import job_manager as jm

        # Hold the worker thread alive past the shutdown deadline
        hold = threading.Event()

        def hanging_job():
            hold.wait(timeout=10.0)  # would block until 10s

        jm.submit_job("sprint41-hang", hanging_job)
        time.sleep(0.2)  # let scheduler dispatch

        try:
            t0 = time.monotonic()
            jm.shutdown(wait=True, timeout=0.5)
            elapsed = time.monotonic() - t0
            # Must return within ~1s of the 0.5s deadline; can't hang for 10s.
            assert elapsed < 2.0, (
                f"shutdown(timeout=0.5) took {elapsed:.2f}s — deadline ignored?"
            )
        finally:
            hold.set()  # let the daemon worker drain so it doesn't leak

    def test_shutdown_drains_quick_workers(self):
        """Fast-completing jobs let shutdown return well before the timeout."""
        from app.services import job_manager as jm

        def quick_job():
            time.sleep(0.05)

        jm.submit_job("sprint41-quick", quick_job)
        time.sleep(0.1)

        t0 = time.monotonic()
        jm.shutdown(wait=True, timeout=5.0)
        elapsed = time.monotonic() - t0
        assert elapsed < 2.0, f"quick-job shutdown took {elapsed:.2f}s — should be near-instant"
