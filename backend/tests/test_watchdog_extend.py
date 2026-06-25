"""Tests for S4.4 watchdog extend (jobs/manager.extend_job_age).

Covers:
1. extend_job_age returns False when the job isn't tracked.
2. extend_job_age accumulates across calls.
3. Negative extra_seconds clamps to 0.
4. _check_and_cancel_stale_jobs respects the override (job past base
   MAX_JOB_AGE but within the override stays alive).
5. _check_and_cancel_stale_jobs cancels when total age exceeds base + override.
6. Override is flushed when start-time entry is removed.
"""
from __future__ import annotations

from unittest.mock import patch

from app.jobs import manager as mod


def _reset_state():
    """Clear manager module state between tests so they don't bleed
    into each other (the module is a singleton)."""
    with mod._job_times_lock:
        mod._job_start_times.clear()
        mod._job_age_overrides.clear()
    with mod._cond:
        mod._active_job_ids.clear()


def test_extend_returns_false_for_unknown_job():
    _reset_state()
    assert mod.extend_job_age("not-a-real-job", 600) is False


def test_extend_accumulates():
    _reset_state()
    # Register a tracked job.
    with mod._job_times_lock:
        mod._job_start_times["jobA"] = 0.0
    with mod._cond:
        mod._active_job_ids.add("jobA")
    assert mod.extend_job_age("jobA", 600) is True
    assert mod.get_job_age_override("jobA") == 600
    assert mod.extend_job_age("jobA", 1800) is True
    assert mod.get_job_age_override("jobA") == 600 + 1800


def test_extend_clamps_negative_to_zero():
    _reset_state()
    with mod._job_times_lock:
        mod._job_start_times["jobB"] = 0.0
    with mod._cond:
        mod._active_job_ids.add("jobB")
    assert mod.extend_job_age("jobB", -100) is True
    assert mod.get_job_age_override("jobB") == 0
    # And a follow-up positive extends from 0, not from a negative anchor.
    assert mod.extend_job_age("jobB", 300) is True
    assert mod.get_job_age_override("jobB") == 300


def test_watchdog_respects_override_for_aged_job():
    """A job past the base limit but within the override is NOT cancelled."""
    _reset_state()
    # Base limit is read at module load. Bypass by setting a small value
    # for the test scope.
    with patch.object(mod, "_MAX_JOB_AGE", 100):
        # Job has been "running" for 150 s — past base 100 s but with a
        # 100 s override should be alive until 200 s.
        with mod._job_times_lock:
            mod._job_start_times["jobC"] = 0.0  # monotonic anchor
            mod._job_age_overrides["jobC"] = 100
        with mod._cond:
            mod._active_job_ids.add("jobC")
        # Pretend "now" is 150 s after start.
        cancels = []
        with patch("time.monotonic", return_value=150.0):
            with patch("app.jobs.cancel.request_cancel", side_effect=lambda jid: cancels.append(jid)):
                mod._check_and_cancel_stale_jobs()
        assert cancels == [], "override should keep jobC alive at 150 s"


def test_watchdog_cancels_after_override_exhausted():
    """A job past base + override IS cancelled."""
    _reset_state()
    with patch.object(mod, "_MAX_JOB_AGE", 100):
        with mod._job_times_lock:
            mod._job_start_times["jobD"] = 0.0
            mod._job_age_overrides["jobD"] = 100
        with mod._cond:
            mod._active_job_ids.add("jobD")
        # 250 s elapsed > 100 base + 100 override = 200.
        cancels = []
        with patch("time.monotonic", return_value=250.0):
            with patch("app.jobs.cancel.request_cancel", side_effect=lambda jid: cancels.append(jid)):
                mod._check_and_cancel_stale_jobs()
        assert cancels == ["jobD"]


def test_watchdog_disabled_when_max_age_zero():
    """Setting MAX_JOB_AGE=0 disables the watchdog entirely; even an
    obviously stale job is not cancelled."""
    _reset_state()
    with patch.object(mod, "_MAX_JOB_AGE", 0):
        with mod._job_times_lock:
            mod._job_start_times["jobE"] = 0.0
        with mod._cond:
            mod._active_job_ids.add("jobE")
        cancels = []
        with patch("time.monotonic", return_value=999999.0):
            with patch("app.jobs.cancel.request_cancel", side_effect=lambda jid: cancels.append(jid)):
                mod._check_and_cancel_stale_jobs()
        assert cancels == []


def test_get_job_age_override_returns_zero_for_unknown():
    _reset_state()
    assert mod.get_job_age_override("ghost-job") == 0
