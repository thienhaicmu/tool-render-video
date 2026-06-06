import threading

_EVENTS: dict[str, threading.Event] = {}
_PENDING: set[str] = set()
_LOCK = threading.Lock()


class JobCancelledError(RuntimeError):
    """Raised inside a render pipeline when a cancel signal has been received."""


def register(job_id: str) -> threading.Event:
    """Create a cancel event for job_id. If cancel was requested while queued, the event is pre-set."""
    ev = threading.Event()
    with _LOCK:
        _EVENTS[job_id] = ev
        if job_id in _PENDING:
            ev.set()
            _PENDING.discard(job_id)
    return ev


def get_event(job_id: str):
    """Return the live threading.Event for job_id, or None if not registered."""
    with _LOCK:
        return _EVENTS.get(job_id)


def request_cancel(job_id: str) -> bool:
    """Signal cancel for job_id. Returns True if job was actively running, False if queued/unknown."""
    with _LOCK:
        ev = _EVENTS.get(job_id)
        if ev is not None:
            ev.set()
            return True
        # Job not yet in process_render â€” queue the cancel so register() picks it up
        _PENDING.add(job_id)
        return False


def is_cancelled(job_id: str) -> bool:
    with _LOCK:
        ev = _EVENTS.get(job_id)
        if ev is not None:
            return ev.is_set()
        return job_id in _PENDING


def unregister(job_id: str) -> None:
    with _LOCK:
        _EVENTS.pop(job_id, None)
        _PENDING.discard(job_id)


def prune_pending(active_job_ids: "frozenset[str]") -> int:
    """Remove _PENDING entries whose job_id is not in active_job_ids.

    Call with the current set of queued+running job IDs so stale pending cancel
    signals (e.g. for jobs that were removed from the queue without ever running)
    are discarded.  Returns the count of pruned entries.
    """
    with _LOCK:
        stale = _PENDING - active_job_ids
        _PENDING.difference_update(stale)
        return len(stale)


def cancel_all_active() -> int:
    """Signal cancel to every currently registered job event.

    Sprint 4.1 graceful shutdown helper (audit 2026-06-02 P1-B1): job_manager
    calls this on shutdown so in-flight render workers exit promptly instead
    of being abandoned with no signal. Worker code polls its cancel event in
    long-running loops (e.g. ffmpeg_helpers._run_ffmpeg_with_retry) and
    raises JobCancelledError when set.

    Returns the number of events that were signaled.
    """
    with _LOCK:
        count = 0
        for ev in _EVENTS.values():
            if not ev.is_set():
                ev.set()
                count += 1
        return count

