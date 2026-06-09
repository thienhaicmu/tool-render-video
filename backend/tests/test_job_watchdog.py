"""Tests for the render thread watchdog — Sprint C-2.

Exercises _check_and_cancel_stale_jobs() directly (no sleeping required).
The watchdog daemon thread is not started in these tests.
"""
import time
import pytest


def _register_job(job_id: str, start_offset: float) -> None:
    """Add job_id to active set and _job_start_times with start = now - start_offset."""
    import app.jobs.manager as mgr
    with mgr._job_times_lock:
        mgr._job_start_times[job_id] = time.monotonic() - start_offset
    with mgr._cond:
        mgr._active_job_ids.add(job_id)


def _deregister_job(job_id: str) -> None:
    """Remove job_id from active set and _job_start_times."""
    import app.jobs.manager as mgr
    with mgr._job_times_lock:
        mgr._job_start_times.pop(job_id, None)
    with mgr._cond:
        mgr._active_job_ids.discard(job_id)


# ---------------------------------------------------------------------------
# 1. Job within age limit — not cancelled
# ---------------------------------------------------------------------------

def test_watchdog_within_age_limit_not_cancelled(monkeypatch):
    """A freshly-dispatched job (age << _MAX_JOB_AGE) must NOT be cancelled."""
    import app.jobs.manager as mgr
    job_id = "watchdog-test-fresh"
    _register_job(job_id, start_offset=1.0)  # 1 second old — well within limit
    cancel_calls: list[str] = []
    monkeypatch.setattr("app.jobs.cancel.request_cancel", lambda jid: cancel_calls.append(jid))
    try:
        mgr._check_and_cancel_stale_jobs()
    finally:
        _deregister_job(job_id)
    assert job_id not in cancel_calls, (
        f"Fresh job {job_id} was unexpectedly cancelled after 1s (limit {mgr._MAX_JOB_AGE}s)"
    )


# ---------------------------------------------------------------------------
# 2. Job exceeding MAX_JOB_AGE_SECONDS — request_cancel called
# ---------------------------------------------------------------------------

def test_watchdog_exceeds_max_job_age_cancels(monkeypatch):
    """A job older than _MAX_JOB_AGE must have request_cancel() called on it."""
    import app.jobs.manager as mgr
    job_id = "watchdog-test-stale"
    _register_job(job_id, start_offset=mgr._MAX_JOB_AGE + 10)
    cancel_calls: list[str] = []
    monkeypatch.setattr("app.jobs.cancel.request_cancel", lambda jid: cancel_calls.append(jid))
    try:
        mgr._check_and_cancel_stale_jobs()
    finally:
        _deregister_job(job_id)
    assert job_id in cancel_calls, (
        f"Stale job {job_id} was NOT cancelled (age > {mgr._MAX_JOB_AGE}s)"
    )


# ---------------------------------------------------------------------------
# 3. request_cancel raises — watchdog swallows exception and does not propagate
# ---------------------------------------------------------------------------

def test_watchdog_survives_cancel_failure(monkeypatch):
    """If request_cancel() raises, _check_and_cancel_stale_jobs must not propagate the error."""
    import app.jobs.manager as mgr
    job_id = "watchdog-test-cancel-fail"
    _register_job(job_id, start_offset=mgr._MAX_JOB_AGE + 10)

    def _raise(jid: str) -> None:
        raise RuntimeError("cancel boom")

    monkeypatch.setattr("app.jobs.cancel.request_cancel", _raise)
    try:
        mgr._check_and_cancel_stale_jobs()  # must not raise
    finally:
        _deregister_job(job_id)
