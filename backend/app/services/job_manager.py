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
# Negated priority → highest int pops first; seq gives FIFO within a tier.
_pending: list[tuple] = []
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
# DB helper — lazy import avoids circular dependency at module load time
# ---------------------------------------------------------------------------

def _mark_job_running(job_id: str) -> None:
    """Best-effort: transition DB status queued → running before dispatch."""
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
            _active_job_ids.add(job_id)

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
                    _cond.notify_all()  # a slot just opened — wake the scheduler

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
                  (idempotent — safe to call multiple times).
    """
    global _seq

    _ensure_scheduler_running()

    with _cond:
        if _stopping:
            logger.warning("Job %s rejected: scheduler is shutting down", job_id)
            return False

        if job_id in _active_job_ids:
            logger.debug("Job %s already running — skip duplicate submit", job_id)
            return False
        if any(entry[2] == job_id for entry in _pending):
            logger.debug("Job %s already pending — skip duplicate submit", job_id)
            return False

        _seq += 1
        heapq.heappush(_pending, (-priority, _seq, job_id, fn, args, kwargs))
        _cond.notify_all()

    logger.info(
        "Job %s enqueued (priority=%d, queue_depth=%d)",
        job_id, priority, len(_pending),
    )
    return True


def is_running(job_id: str) -> bool:
    """True if the job is currently executing OR waiting in the pending queue."""
    with _lock:
        return job_id in _active_job_ids or any(e[2] == job_id for e in _pending)


def active_count() -> int:
    """Number of jobs currently executing."""
    with _lock:
        return len(_active_job_ids)


def pending_count() -> int:
    """Number of jobs waiting for a concurrency slot."""
    with _lock:
        return len(_pending)


def shutdown(wait: bool = True) -> None:
    global _executor, _stopping
    with _cond:
        _stopping = True
        _cond.notify_all()
    if _executor:
        _executor.shutdown(wait=wait)
        _executor = None


# ---------------------------------------------------------------------------
# Startup recovery
# ---------------------------------------------------------------------------

def recover_pending_render_jobs():
    """
    Called once on server startup.

    Marks any jobs that were left in 'queued' or 'running' state as
    'interrupted' — does NOT auto-restart them.  The user can manually
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
                "Server restarted — click Resume to continue",
                status="interrupted",
            )
            marked += 1
            logger.info("Marked job %s as interrupted (was %s)", job_id, job.get("status"))

        if marked:
            logger.info(
                "Startup: marked %d job(s) as interrupted. User can resume from UI.", marked
            )
    except Exception as exc:
        logger.warning("Job recovery marking failed (non-fatal): %s", exc)
