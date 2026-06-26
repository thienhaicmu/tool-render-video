"""Tests for app.jobs.manager."""
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

import app.jobs.manager as manager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_manager():
    """Reset shared module state between tests to prevent cross-test pollution."""
    with manager._cond:
        manager._pending.clear()
        manager._pending_job_ids.clear()
        manager._active_job_ids.clear()
        manager._stopping = False
    if manager._executor is not None:
        try:
            manager._executor.shutdown(wait=False)
        except Exception:
            pass
        manager._executor = None


@pytest.fixture(autouse=True)
def isolate_manager():
    """Reset manager state before and after each test."""
    _reset_manager()
    yield
    _reset_manager()


# ---------------------------------------------------------------------------
# Module-level state variables
# ---------------------------------------------------------------------------

def test_lock_is_lock():
    assert isinstance(manager._lock, type(threading.Lock()))


def test_cond_is_condition():
    assert isinstance(manager._cond, type(threading.Condition()))


def test_active_job_ids_is_set():
    assert isinstance(manager._active_job_ids, set)


# ---------------------------------------------------------------------------
# active_count / pending_count
# ---------------------------------------------------------------------------

def test_active_count_initially_zero():
    assert manager.active_count() == 0


def test_pending_count_initially_zero():
    assert manager.pending_count() == 0


# ---------------------------------------------------------------------------
# is_running
# ---------------------------------------------------------------------------

def test_is_running_false_for_unknown_job():
    assert manager.is_running("nonexistent-job-id") is False


def test_is_running_true_when_in_active_set():
    with manager._cond:
        manager._active_job_ids.add("test-job-active")
    assert manager.is_running("test-job-active") is True


def test_is_running_true_when_in_pending_set():
    with manager._cond:
        manager._pending_job_ids.add("test-job-pending")
    assert manager.is_running("test-job-pending") is True


# ---------------------------------------------------------------------------
# submit_job
# ---------------------------------------------------------------------------

def test_submit_job_returns_true_for_new_job():
    fn = MagicMock()
    with patch("app.jobs.manager._mark_job_running"):
        result = manager.submit_job("new-job-1", fn)
    assert result is True


def test_submit_job_returns_false_for_duplicate_active():
    fn = MagicMock()
    with manager._cond:
        manager._active_job_ids.add("dupe-job")
    result = manager.submit_job("dupe-job", fn)
    assert result is False


def test_submit_job_returns_false_for_duplicate_pending():
    fn = MagicMock()
    with manager._cond:
        manager._pending_job_ids.add("dupe-job-2")
    result = manager.submit_job("dupe-job-2", fn)
    assert result is False


def test_submit_job_increments_pending_count():
    """The previous version of this test was flaky in isolation. ``patch``
    on ``_mark_job_running`` did NOT prevent the scheduler thread from
    popping the job out of ``_pending`` — the pop happens BEFORE
    ``_mark_job_running`` is called, so when the scheduler woke fast
    enough the assertion observed ``pending_count() == 0``.

    Deterministic fix: pre-fill ``_active_job_ids`` to ``MAX_CONCURRENT_JOBS``
    so the scheduler sees no free slot and never pops. The autouse
    ``isolate_manager`` fixture clears these markers after the test.
    """
    fn = MagicMock()
    with manager._cond:
        for i in range(manager.MAX_CONCURRENT_JOBS):
            manager._active_job_ids.add(f"slot-filler-{i}")
    manager.submit_job("pending-job-count", fn)
    assert manager.pending_count() >= 1


def test_submit_job_rejected_when_stopping():
    fn = MagicMock()
    with manager._cond:
        manager._stopping = True
    result = manager.submit_job("stopped-job", fn)
    assert result is False


# ---------------------------------------------------------------------------
# submit_job + job execution
# ---------------------------------------------------------------------------

def test_submitted_job_eventually_executes():
    done_event = threading.Event()
    fn = MagicMock(side_effect=lambda: done_event.set())

    with patch("app.jobs.manager._mark_job_running"):
        manager.submit_job("exec-job", fn)

    done_event.wait(timeout=5.0)
    assert done_event.is_set(), "Job function was not called within timeout"
    fn.assert_called_once()


def test_job_no_longer_active_after_completion():
    done_event = threading.Event()

    def _fn():
        pass

    done_event_after = threading.Event()

    def _fn_with_wait():
        _fn()

    with patch("app.jobs.manager._mark_job_running"):
        manager.submit_job("cleanup-job", _fn_with_wait)

    # Wait for the manager scheduler to clean up
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not manager.is_running("cleanup-job"):
            break
        time.sleep(0.05)

    assert not manager.is_running("cleanup-job")


# ---------------------------------------------------------------------------
# shutdown
# ---------------------------------------------------------------------------

def test_shutdown_sets_stopping_flag():
    manager.shutdown(wait=False)
    with manager._lock:
        assert manager._stopping is True


# ---------------------------------------------------------------------------
# Pha 3 — pending_order / move_job_to_front
#
# Deterministic pattern (same as test_submit_job_increments_pending_count):
# pre-fill _active_job_ids to MAX_CONCURRENT_JOBS so the scheduler never pops,
# keeping the submitted jobs in the pending heap for inspection/reorder.
# ---------------------------------------------------------------------------

def _fill_slots():
    with manager._cond:
        for i in range(manager.MAX_CONCURRENT_JOBS):
            manager._active_job_ids.add(f"slot-filler-{i}")


def test_pending_order_reflects_fifo_within_same_priority():
    fn = MagicMock()
    _fill_slots()
    with patch("app.jobs.manager._mark_job_running"):
        manager.submit_job("job-a", fn)
        manager.submit_job("job-b", fn)
        manager.submit_job("job-c", fn)
    assert manager.pending_order() == ["job-a", "job-b", "job-c"]


def test_move_job_to_front_reorders_pending():
    fn = MagicMock()
    _fill_slots()
    with patch("app.jobs.manager._mark_job_running"):
        manager.submit_job("job-a", fn)
        manager.submit_job("job-b", fn)
        manager.submit_job("job-c", fn)
    assert manager.move_job_to_front("job-c") is True
    # c jumps to front; a and b keep their relative order behind it.
    assert manager.pending_order() == ["job-c", "job-a", "job-b"]


def test_move_job_to_front_unknown_returns_false():
    assert manager.move_job_to_front("does-not-exist") is False


def test_move_job_to_front_twice_keeps_newest_first():
    fn = MagicMock()
    _fill_slots()
    with patch("app.jobs.manager._mark_job_running"):
        manager.submit_job("job-a", fn)
        manager.submit_job("job-b", fn)
        manager.submit_job("job-c", fn)
    manager.move_job_to_front("job-b")
    manager.move_job_to_front("job-c")  # last bump wins the front slot
    assert manager.pending_order()[0] == "job-c"


def test_pending_order_empty_when_no_pending():
    assert manager.pending_order() == []


# ---------------------------------------------------------------------------
# Pha 3.2 — move_job_to_back / move_job(delta)
# ---------------------------------------------------------------------------

def _submit_abc():
    fn = MagicMock()
    _fill_slots()
    with patch("app.jobs.manager._mark_job_running"):
        manager.submit_job("job-a", fn)
        manager.submit_job("job-b", fn)
        manager.submit_job("job-c", fn)


def test_move_job_to_back_sends_to_end():
    _submit_abc()
    assert manager.move_job_to_back("job-a") is True
    assert manager.pending_order() == ["job-b", "job-c", "job-a"]


def test_move_job_to_back_unknown_returns_false():
    assert manager.move_job_to_back("nope") is False


def test_move_job_up_one_step():
    _submit_abc()
    assert manager.move_job("job-c", -1) is True
    assert manager.pending_order() == ["job-a", "job-c", "job-b"]


def test_move_job_down_one_step():
    _submit_abc()
    assert manager.move_job("job-a", 1) is True
    assert manager.pending_order() == ["job-b", "job-a", "job-c"]


def test_move_job_past_edge_is_noop_success():
    _submit_abc()
    # job-a already first → moving up is a no-op but still True.
    assert manager.move_job("job-a", -1) is True
    assert manager.pending_order() == ["job-a", "job-b", "job-c"]


def test_move_job_unknown_returns_false():
    _submit_abc()
    assert manager.move_job("nope", 1) is False
