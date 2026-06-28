import threading
import time
from collections import deque
from typing import Optional

_EVENTS: dict[str, threading.Event] = {}
_PENDING: set[str] = set()
_LOCK = threading.Lock()

# Recently-cancelled jobs ledger — used by _find_active_duplicate_source to
# block fresh submits within a grace window after cancel. Bounded deque so
# memory stays flat under sustained cancel rate. Each entry is a tuple of
# (source_path, channel_code, job_id, timestamp_sec).
#
# ADR-007 (2026-06-27): when a user cancels a Whisper-heavy job and
# immediately resubmits the same source, the cancelled job's subprocess
# may still be running for several seconds while the new job tries to
# start. Both Whispers running on the same source saturates CPU/RAM.
# The grace window blocks the resubmit so the user re-tries after the
# original is fully gone (FE polls /cancel-status to know when).
_RECENT_CANCELS: "deque[tuple[str, str, str, float]]" = deque(maxlen=200)
_RECENT_CANCELS_WINDOW_SEC = 30.0


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


def note_cancel(source_path: str, channel_code: str, job_id: str) -> None:
    """Record that a job has just been cancelled, for the recently-cancelled ledger.

    Called from the cancel HTTP handler right after ``request_cancel``.
    ``_find_active_duplicate_source`` consults this ledger so a fresh
    submit for the same (source, channel) within the grace window is
    rejected with 409 (giving the previous job's subprocess time to
    fully exit).

    No-op if source_path is empty — only "real" sources need dedup
    protection. Resume/retry paths use the same job_id (no resubmit
    race possible).
    """
    src = (source_path or "").strip()
    if not src:
        return
    ts = time.time()
    with _LOCK:
        _RECENT_CANCELS.append((src, channel_code, job_id, ts))


def is_cancelling_recently(
    source_path: str,
    channel_code: str,
    *,
    window_sec: Optional[float] = None,
) -> Optional[str]:
    """Return job_id of a job for (source_path, channel) that was cancelled within
    ``window_sec`` (default :data:`_RECENT_CANCELS_WINDOW_SEC`), or None.

    Used by ``_find_active_duplicate_source`` to extend dedup beyond just
    'running'/'queued' jobs into the cancel-cleanup grace window.
    """
    src = (source_path or "").strip()
    if not src:
        return None
    win = float(window_sec) if window_sec is not None else _RECENT_CANCELS_WINDOW_SEC
    now = time.time()
    with _LOCK:
        # Walk newest-first so we surface the most recent matching cancel.
        for entry_src, entry_ch, entry_job, entry_ts in reversed(_RECENT_CANCELS):
            if (now - entry_ts) > win:
                # Entries are appended in time order — once we're past the
                # window we can stop scanning.
                break
            if entry_src == src and entry_ch == channel_code:
                return entry_job
    return None


def _reset_recent_cancels_for_tests() -> None:
    """Test-only helper to clear the recent-cancels ledger between cases."""
    with _LOCK:
        _RECENT_CANCELS.clear()


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

