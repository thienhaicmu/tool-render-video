"""
Scheduler-backed job queue with priority and concurrency control.

Architecture:
  submit_job() enqueues a callable into a priority min-heap.  A single
  background daemon thread (_scheduler_loop) watches the heap and dispatches
  up to MAX_CONCURRENT_JOBS jobs to a ThreadPoolExecutor at a time.  When a
  slot opens (a job finishes), the scheduler wakes immediately via a
  Condition.notify_all() and picks the next highest-priority job.

Priority ordering:
  Higher integer = dispatched first.  Equal-priority jobs are dispatched in
  submission order (FIFO).  Default priority is 0.

Why not Celery?
  Celery requires Redis/RabbitMQ and a separate worker process, adding
  operational complexity.  For a single-machine desktop platform, a priority
  queue + thread pool with SQLite-backed recovery achieves the same goals:
    - Jobs survive server restart (re-queued on startup from DB).
    - Concurrent job limit (MAX_CONCURRENT_JOBS env var, default cpu//2).
    - Priority ordering with FIFO tie-breaking.
    - Deduplication (job_id can only be active OR pending once at a time).
"""
from __future__ import annotations

import heapq
import logging
import os
import threading
import concurrent.futures
from typing import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_CONCURRENT_JOBS: int = max(1, int(os.getenv(
    "MAX_CONCURRENT_JOBS",
    str(max(1, (os.cpu_count() or 4) // 2)),
)))

# ---------------------------------------------------------------------------
# Internal state  (all mutations must hold _cond/_lock)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_cond = threading.Condition(_lock)          # wait/notify for scheduler

# Min-heap entries: (-priority, seq, job_id, fn, args, kwargs)
# Negated priority â†’ highest int pops first; seq gives FIFO within a tier.
_pending: list[tuple] = []
_pending_job_ids: set[str] = set()         # O(1) mirror of job_ids in _pending
_seq: int = 0                               # monotonic counter, never reset

_active_job_ids: set[str] = set()          # jobs currently executing

_executor: concurrent.futures.ThreadPoolExecutor | None = None
_scheduler_thread: threading.Thread | None = None
_stopping: bool = False


# ---------------------------------------------------------------------------
# Thread pool
# ---------------------------------------------------------------------------

def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _executor
    if _executor is None or _executor._shutdown:
        _executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=MAX_CONCURRENT_JOBS,
            thread_name_prefix="job-worker",
        )
    return _executor


# ---------------------------------------------------------------------------
# DB helper â€” lazy import avoids circular dependency at module load time
# ---------------------------------------------------------------------------

def _mark_job_running(job_id: str) -> None:
    """Best-effort: transition DB status queued â†’ running before dispatch."""
    try:
        from app.services.db import update_job_progress
        update_job_progress(job_id, "starting", 0, "Job starting", status="running")
    except Exception as exc:
        logger.warning("Could not mark job %s as running in DB: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

def _scheduler_loop() -> None:
    """
    Background daemon: dequeue and dispatch jobs while slots are available.

    Sleeps on the Condition until either:
      - A new job is enqueued (submit_job notifies), or
      - A running job finishes (_run wrapper notifies), or
      - The 5-second timeout fires (safety net against missed notifications).
    """
    while True:
        with _cond:
            # Block until there's a pending job AND a free concurrency slot.
            while True:
                if _stopping:
                    return
                if _pending and len(_active_job_ids) < MAX_CONCURRENT_JOBS:
                    break
                _cond.wait(timeout=5.0)

            neg_pri, seq, job_id, fn, args, kwargs = heapq.heappop(_pending)
            _pending_job_ids.discard(job_id)
            _active_job_ids.add(job_id)
            # Sprint 6.C: queue-depth gauges. Sample inside the lock so the
            # snapshot reflects a consistent state of the heap/active set.
            try:
                from app.services.metrics import JOB_QUEUE_ACTIVE, JOB_QUEUE_PENDING
                JOB_QUEUE_PENDING.set(len(_pending))
                JOB_QUEUE_ACTIVE.set(len(_active_job_ids))
            except Exception:
                pass

        # DB write + executor.submit both happen outside the lock so they
        # don't block other threads from enqueuing.
        _mark_job_running(job_id)

        def _run(jid: str = job_id, f: Callable = fn, a=args, kw=kwargs) -> None:
            try:
                f(*a, **kw)
            except Exception as exc:
                logger.error(
                    "Job %s raised unhandled exception: %s", jid, exc, exc_info=True
                )
            finally:
                with _cond:
                    _active_job_ids.discard(jid)
                    _cond.notify_all()  # a slot just opened â€” wake the scheduler
                    # Snapshot valid IDs while holding the lock for prune below
                    _valid_ids = frozenset(_active_job_ids) | frozenset(e[2] for e in _pending)
                    # Sprint 6.C: refresh the active gauge after a slot opens.
                    try:
                        from app.services.metrics import JOB_QUEUE_ACTIVE, JOB_QUEUE_PENDING
                        JOB_QUEUE_PENDING.set(len(_pending))
                        JOB_QUEUE_ACTIVE.set(len(_active_job_ids))
                    except Exception:
                        pass
                # Prune stale _PENDING cancel signals for jobs no longer alive
                try:
                    from app.jobs import cancel as cancel_registry
                    cancel_registry.prune_pending(_valid_ids)
                except Exception:
                    pass

        _get_executor().submit(_run)
        logger.debug(
            "Job %s dispatched (active=%d/%d, pending=%d)",
            job_id, len(_active_job_ids), MAX_CONCURRENT_JOBS, len(_pending),
        )


def _ensure_scheduler_running() -> None:
    """Start the scheduler daemon thread if it is not already alive."""
    global _scheduler_thread
    with _lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return
        t = threading.Thread(target=_scheduler_loop, daemon=True, name="job-scheduler")
        t.start()
        _scheduler_thread = t
        logger.info("Job scheduler started (MAX_CONCURRENT_JOBS=%d)", MAX_CONCURRENT_JOBS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_job(job_id: str, fn: Callable, *args, priority: int = 0, **kwargs) -> bool:
    """
    Enqueue *fn(*args, **kwargs)* under *job_id* with the given *priority*.

    Higher priority values are dispatched before lower ones.  Equal-priority
    jobs are dispatched in FIFO order.

    Returns True  if the job was accepted into the queue.
    Returns False if a job with this job_id is already active or pending
                  (idempotent â€” safe to call multiple times).
    """
    global _seq

    _ensure_scheduler_running()

    with _cond:
        if _stopping:
            logger.warning("Job %s rejected: scheduler is shutting down", job_id)
            return False

        if job_id in _active_job_ids:
            logger.debug("Job %s already running â€” skip duplicate submit", job_id)
            return False
        if job_id in _pending_job_ids:
            logger.debug("Job %s already pending â€” skip duplicate submit", job_id)
            return False

        _seq += 1
        heapq.heappush(_pending, (-priority, _seq, job_id, fn, args, kwargs))
        _pending_job_ids.add(job_id)
        _cond.notify_all()

    logger.info(
        "Job %s enqueued (priority=%d, queue_depth=%d)",
        job_id, priority, len(_pending),
    )
    return True


def is_running(job_id: str) -> bool:
    """True if the job is currently executing OR waiting in the pending queue."""
    with _lock:
        return job_id in _active_job_ids or job_id in _pending_job_ids


def active_count() -> int:
    """Number of jobs currently executing."""
    with _lock:
        return len(_active_job_ids)


def pending_count() -> int:
    """Number of jobs waiting for a concurrency slot."""
    with _lock:
        return len(_pending)


def shutdown(wait: bool = True, timeout: float = 30.0) -> None:
    """Stop the scheduler and drain in-flight workers.

    Sprint 4.1 (audit 2026-06-02 P1-B1): graceful shutdown signals cancel
    to active jobs and waits up to `timeout` seconds for the worker pool to
    drain. If the deadline elapses, the executor is force-shut and workers
    are abandoned (matching the previous wait=False behavior).

    Args:
        wait: if False, force-abandon immediately (backward-compat with the
              previous unbounded-wait=False behavior). Default True.
        timeout: max seconds to wait for graceful drain when wait=True.
                 0 or negative â†’ force-abandon immediately.
    """
    global _executor, _stopping
    with _cond:
        _stopping = True
        _cond.notify_all()

    # Signal cancel to every active job FIRST â€” even when there is no executor
    # (e.g. test fixtures that registered cancel events but never submitted).
    # Long-running loops (ffmpeg_helpers, render_pipeline guards) poll their
    # cancel_event and raise JobCancelledError on set.
    if wait and timeout > 0:
        try:
            from app.jobs import cancel as cancel_registry
            n = cancel_registry.cancel_all_active()
            if n:
                logger.info("Graceful shutdown: signaled cancel to %d active job(s)", n)
        except Exception as exc:
            logger.warning("cancel_all_active() failed during shutdown: %s", exc)

    if _executor is None:
        return

    if not wait or timeout <= 0:
        # Fast-abandon path. Preserves the old wait=False semantics.
        try:
            _executor.shutdown(wait=False)
        finally:
            _executor = None
        return

    # ThreadPoolExecutor.shutdown(wait=True) blocks indefinitely. Bound it by
    # running the drain in a daemon thread and waiting up to `timeout` here.
    finished = threading.Event()

    def _drain():
        try:
            _executor.shutdown(wait=True, cancel_futures=True)
        finally:
            finished.set()

    threading.Thread(target=_drain, daemon=True, name="job-manager-shutdown").start()
    finished.wait(timeout=timeout)
    if not finished.is_set():
        logger.warning(
            "Graceful shutdown timed out after %.1fs â€” abandoning in-flight workers",
            timeout,
        )
        # Belt + suspenders: ensure the executor reference is cleared even if
        # the drain thread is still alive (it's daemon so process exit kills it).
        try:
            _executor.shutdown(wait=False)
        except Exception:
            pass
    _executor = None


# ---------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------

def recover_pending_render_jobs():
    """
    Called once on server startup.

    Marks any jobs that were left in 'queued' or 'running' state as
    'interrupted' â€” does NOT auto-restart them.  The user can manually
    resume from the UI (Resume button) if they want to continue.

    Auto-restarting old jobs on startup is unexpected behaviour: the user
    may have intentionally stopped the server, or the jobs may be days old.
    """
    try:
        from app.services.db import list_jobs, update_job_progress

        jobs = list_jobs()
        marked = 0
        for job in jobs:
            if job.get("kind") not in ("render", "download"):
                continue
            if job.get("status") not in ("queued", "running"):
                continue

            job_id = job["job_id"]
            update_job_progress(
                job_id,
                job.get("stage", "unknown"),
                job.get("progress_percent", 0),
                "Server restarted â€” click Resume to continue",
                status="interrupted",
            )
            marked += 1
            logger.info("Marked job %s as interrupted (was %s)", job_id, job.get("status"))

        if marked:
            logger.info(
                "Startup: marked %d job(s) as interrupted. User can resume from UI.", marked
            )
        else:
            logger.info(
                "Startup: no interrupted jobs â€” queue is clean. "
                "Note: jobs queued in memory at shutdown are not auto-restarted; "
                "only DB-persisted jobs with status 'queued'/'running' are recovered."
            )
    except Exception as exc:
        logger.warning("Job recovery marking failed (non-fatal): %s", exc)

