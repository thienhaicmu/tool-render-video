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
        # Job not yet in process_render — queue the cancel so register() picks it up
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
