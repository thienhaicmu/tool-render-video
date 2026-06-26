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
import time
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

# Global job age limit in seconds. Jobs running longer than this are cancelled
# by the watchdog. Default 7200 s (2 h) — covers transcription + LLM + render
# for long-form content.  Set to 0 to disable.
_MAX_JOB_AGE: int = int(os.getenv("MAX_JOB_AGE_SECONDS", "7200"))
_WATCHDOG_INTERVAL: int = 30

# ---------------------------------------------------------------------------
# Internal state  (all mutations must hold _cond/_lock)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_cond = threading.Condition(_lock)          # wait/notify for scheduler

# Min-heap entries: (-priority, seq, job_id, fn, args, kwargs)
# Negated priority → highest int pops first; seq gives FIFO within a tier.
_pending: list[tuple] = []
_pending_job_ids: set[str] = set()         # O(1) mirror of job_ids in _pending
_seq: int = 0                               # monotonic counter, never reset

_active_job_ids: set[str] = set()          # jobs currently executing

# Pha 3.3b — paused ("held") queued jobs: their heap entry is pulled OUT of
# _pending so the scheduler won't dispatch them, but they STAY in
# _pending_job_ids (so dedup / is_running keep working). resume_job pushes
# the entry back. In-memory only — a restart drops holds (jobs become
# 'interrupted' via the normal queued-recovery path). Mutate under _cond.
_held: dict[str, tuple] = {}

_executor: concurrent.futures.ThreadPoolExecutor | None = None
_scheduler_thread: threading.Thread | None = None
_stopping: bool = False

# Watchdog state — tracks when each job was dispatched for age-limit enforcement.
_job_start_times: dict[str, float] = {}
# S4.4 — extra seconds the user has explicitly granted to specific jobs via
# POST /api/jobs/{id}/extend. The watchdog adds this to MAX_JOB_AGE before
# comparing, so a 4 K long-form render can survive past the 2 h default
# without the user having to bump the env var globally. Cleared when the
# job's start-time entry is removed (job finishes / cancelled). In-memory
# only — restart resets to zero overrides, which is the safe default.
_job_age_overrides: dict[str, int] = {}
_job_times_lock = threading.Lock()
_watchdog_thread: threading.Thread | None = None


# ---------------------------------------------------------------------------
# Watchdog — cancels jobs that exceed MAX_JOB_AGE_SECONDS
# ---------------------------------------------------------------------------

def _check_and_cancel_stale_jobs() -> None:
    """Scan active jobs and cancel any that have exceeded _MAX_JOB_AGE.

    Called from the watchdog daemon thread every _WATCHDOG_INTERVAL seconds.
    Exposed at module level so unit tests can invoke it directly without
    sleeping.  _MAX_JOB_AGE == 0 disables the check entirely.

    S4.4 — per-job override in ``_job_age_overrides`` is added to the
    base limit before comparing, so a user-granted extension via
    POST /api/jobs/{id}/extend pushes the deadline out.
    """
    if _MAX_JOB_AGE <= 0:
        return
    now = time.monotonic()
    with _cond:
        active = list(_active_job_ids)
    for job_id in active:
        with _job_times_lock:
            t0 = _job_start_times.get(job_id)
            override = _job_age_overrides.get(job_id, 0)
        effective_limit = _MAX_JOB_AGE + override
        if t0 is not None and (now - t0) > effective_limit:
            logger.warning(
                "watchdog: job %s has run for %.0fs (limit %ds, override %ds) — cancelling",
                job_id, now - t0, _MAX_JOB_AGE, override,
            )
            try:
                from app.jobs.cancel import request_cancel
                request_cancel(job_id)
            except Exception as exc:
                logger.error("watchdog: request_cancel(%s) failed: %s", job_id, exc)


# S4.4 — public surface for the /api/jobs/{id}/extend endpoint.

def extend_job_age(job_id: str, extra_seconds: int = 3600) -> bool:
    """Grant ``extra_seconds`` of additional run-time to an active job.

    Multiple calls accumulate (caller can extend repeatedly). Negative
    values clamp to 0 — extension can't shrink the limit. Returns True
    when the job exists in the active set + has a start time recorded;
    False otherwise (the caller surfaces a 404).

    In-memory only — restart clears all overrides, returning to the base
    MAX_JOB_AGE_SECONDS limit (the safe default).
    """
    extra = max(0, int(extra_seconds))
    with _job_times_lock:
        if job_id not in _job_start_times:
            return False
        _job_age_overrides[job_id] = _job_age_overrides.get(job_id, 0) + extra
        logger.info(
            "watchdog: extended job %s by %ds (cumulative override %ds)",
            job_id, extra, _job_age_overrides[job_id],
        )
    return True


def get_job_age_override(job_id: str) -> int:
    """Read the cumulative override (seconds) for a job. 0 if untouched
    or job not tracked. Exposed for tests + diagnostic endpoints."""
    with _job_times_lock:
        return int(_job_age_overrides.get(job_id, 0))


def _watchdog_loop() -> None:
    """Daemon loop: sleep, then check for stale jobs. Never raises."""
    while True:
        time.sleep(_WATCHDOG_INTERVAL)
        try:
            _check_and_cancel_stale_jobs()
        except Exception as exc:
            logger.error("watchdog loop error: %s", exc, exc_info=True)


def _ensure_watchdog_running() -> None:
    """Start the watchdog daemon thread if it is not already alive."""
    global _watchdog_thread
    if _MAX_JOB_AGE <= 0:
        return
    with _job_times_lock:
        if _watchdog_thread is not None and _watchdog_thread.is_alive():
            return
        t = threading.Thread(target=_watchdog_loop, daemon=True, name="job-watchdog")
        t.start()
        _watchdog_thread = t
        logger.info("Job watchdog started (MAX_JOB_AGE_SECONDS=%d)", _MAX_JOB_AGE)


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
        from app.db.jobs_repo import update_job_progress
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

        # Record dispatch time for watchdog age-limit enforcement.
        with _job_times_lock:
            _job_start_times[job_id] = time.monotonic()
        _ensure_watchdog_running()

        def _run(jid: str = job_id, f: Callable = fn, a=args, kw=kwargs) -> None:
            try:
                f(*a, **kw)
            except Exception as exc:
                logger.error(
                    "Job %s raised unhandled exception: %s", jid, exc, exc_info=True
                )
            finally:
                with _job_times_lock:
                    _job_start_times.pop(jid, None)
                    # S4.4 — flush any extend-override too; the override
                    # is meaningless once the job has terminated.
                    _job_age_overrides.pop(jid, None)
                with _cond:
                    _active_job_ids.discard(jid)
                    _cond.notify_all()  # a slot just opened — wake the scheduler
                    # Snapshot valid IDs while holding the lock for prune below.
                    # Pha 3.3b — include held jobs so a cancel signal queued for
                    # a paused job isn't pruned before it's resumed + dispatched.
                    _valid_ids = (
                        frozenset(_active_job_ids)
                        | frozenset(e[2] for e in _pending)
                        | frozenset(_held.keys())
                    )
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
        if job_id in _pending_job_ids:
            logger.debug("Job %s already pending — skip duplicate submit", job_id)
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


# ---------------------------------------------------------------------------
# Pha 3 — Queue Workspace surface (read order + move-to-front)
# ---------------------------------------------------------------------------

def pending_order() -> list[str]:
    """Return pending job_ids in dispatch order (highest priority / FIFO first).

    ``sorted(_pending)`` orders by the heap key ``(-priority, seq)`` — both
    ints — so it never compares the callable. Used by the queue UI to show a
    job's position (#N of M) while it waits for a slot. Read-only snapshot.
    """
    with _lock:
        return [entry[2] for entry in sorted(_pending)]


def move_job_to_front(job_id: str) -> bool:
    """Bump a *pending* job to the front of the queue (dispatched next).

    Sets the job's priority to one above the current maximum pending priority
    and re-heapifies in place under ``_cond`` so the change is atomic w.r.t.
    the scheduler, then notifies it. The existing ``seq`` is preserved so FIFO
    ordering within the new priority tier stays stable.

    Returns True if the job was found in the pending heap, False otherwise
    (already running, finished, or unknown — none of which can be reordered).
    """
    with _cond:
        idx = next((i for i, e in enumerate(_pending) if e[2] == job_id), -1)
        if idx < 0:
            return False
        # Highest priority currently waiting (entry[0] is the *negated*
        # priority), then go one above it so this job pops first.
        top_priority = max((-e[0] for e in _pending), default=0) + 1
        e = _pending[idx]
        _pending[idx] = (-top_priority, e[1], e[2], e[3], e[4], e[5])
        heapq.heapify(_pending)
        _cond.notify_all()
        logger.info("Job %s moved to front of queue (priority=%d)", job_id, top_priority)
        return True


# ---------------------------------------------------------------------------
# Pha 3.2 — full reorder (move-to-back + up/down one step)
# ---------------------------------------------------------------------------

def _apply_pending_order(ids: list[str]) -> None:
    """Reassign priorities so the heap dispatches in *ids* order (front-first).

    Caller MUST hold ``_cond``. Each entry's ``seq`` + payload are preserved;
    only the priority key is rewritten (descending) so the dispatch order
    matches ``ids`` exactly. O(n) — fine for the small desktop queue.
    """
    entry_by_id = {e[2]: e for e in _pending}
    n = len(ids)
    new: list[tuple] = []
    for rank, jid in enumerate(ids):
        e = entry_by_id[jid]
        new.append((-(n - rank), e[1], e[2], e[3], e[4], e[5]))
    _pending[:] = new
    heapq.heapify(_pending)


def move_job_to_back(job_id: str) -> bool:
    """Send a *pending* job to the back of the queue (dispatched last).

    Returns True if found in the pending heap, False otherwise.
    """
    with _cond:
        ids = [e[2] for e in sorted(_pending)]
        if job_id not in ids:
            return False
        ids.append(ids.pop(ids.index(job_id)))
        _apply_pending_order(ids)
        _cond.notify_all()
        logger.info("Job %s moved to back of queue", job_id)
        return True


def move_job(job_id: str, delta: int) -> bool:
    """Nudge a *pending* job one position up (delta<0) or down (delta>0).

    Moves a single step in the sign direction regardless of magnitude. A move
    past either edge is a no-op that still returns True (the job is simply
    already at the boundary). Returns False only when the job isn't pending.
    """
    step = 1 if delta > 0 else -1 if delta < 0 else 0
    with _cond:
        ids = [e[2] for e in sorted(_pending)]
        if job_id not in ids:
            return False
        pos = ids.index(job_id)
        target = pos + step
        if step == 0 or target < 0 or target >= len(ids):
            return True  # at an edge / no movement — nothing to do
        ids.insert(target, ids.pop(pos))
        _apply_pending_order(ids)
        _cond.notify_all()
        logger.info("Job %s moved %s one step", job_id, "down" if step > 0 else "up")
        return True


# ---------------------------------------------------------------------------
# Pha 3.3b — pause / resume (hold) a queued job
# ---------------------------------------------------------------------------

def hold_job(job_id: str) -> bool:
    """Pause a *pending* job: pull its entry out of the dispatch heap.

    The job stays in ``_pending_job_ids`` (dedup / is_running still report it),
    so a paused job can't be re-submitted and still appears 'queued' in the DB.
    Returns True if the job was pending (and is now held), False otherwise
    (running, unknown, or already held).
    """
    with _cond:
        idx = next((i for i, e in enumerate(_pending) if e[2] == job_id), -1)
        if idx < 0:
            return False
        entry = _pending.pop(idx)
        heapq.heapify(_pending)
        _held[job_id] = entry
        logger.info("Job %s held (paused)", job_id)
        return True


def resume_job(job_id: str) -> bool:
    """Resume a held job: push its entry back into the dispatch heap.

    Returns True if the job was held (and is now pending again), False
    otherwise (never held / unknown).
    """
    with _cond:
        entry = _held.pop(job_id, None)
        if entry is None:
            return False
        heapq.heappush(_pending, entry)
        _cond.notify_all()
        logger.info("Job %s resumed", job_id)
        return True


def is_held(job_id: str) -> bool:
    """True if the job is currently paused (held out of the dispatch heap)."""
    with _lock:
        return job_id in _held


def held_ids() -> list[str]:
    """Snapshot of currently-held (paused) job_ids."""
    with _lock:
        return list(_held.keys())


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
                 0 or negative → force-abandon immediately.
    """
    global _executor, _stopping
    with _cond:
        _stopping = True
        _cond.notify_all()

    # Signal cancel to every active job FIRST — even when there is no executor
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
            "Graceful shutdown timed out after %.1fs — abandoning in-flight workers",
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

def reconcile_orphaned_render_jobs(stale_seconds: int = 120) -> int:
    """Mark phantom render jobs as 'interrupted'.

    A *phantom* is a job whose DB status is still 'running' or 'queued' but
    which the scheduler is NOT tracking (not in _active_job_ids / _pending).
    This happens when a worker dies without writing a terminal status — e.g.
    an exception during the render pipeline's setup phase (before its own
    try/except) that propagated past process_render. The phantom then shows
    as a perpetually-active job, which makes the UI's active-job reattach and
    the queue's source-dedup block every NEW render until the user manually
    kills it.

    Conservative gates to avoid racing a freshly-submitted job:
      - only jobs untouched for ``stale_seconds`` (default 120 s), and
      - only jobs the scheduler is not currently tracking.

    Returns the number of jobs reconciled. Never raises.
    """
    try:
        from app.db.connection import db_conn
        from app.db.jobs_repo import update_job_progress
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT job_id, stage, progress_percent FROM jobs "
                "WHERE kind = 'render' AND status IN ('running', 'queued') "
                "AND updated_at < datetime('now', ?)",
                (f"-{int(stale_seconds)} seconds",),
            ).fetchall()
        reconciled = 0
        for r in rows:
            jid = r[0] if isinstance(r, tuple) else r["job_id"]
            stage = (r[1] if isinstance(r, tuple) else r["stage"]) or "unknown"
            pct = int((r[2] if isinstance(r, tuple) else r["progress_percent"]) or 0)
            with _lock:
                tracked = jid in _active_job_ids or jid in _pending_job_ids
            if tracked:
                continue
            update_job_progress(
                jid, stage, pct,
                "Worker ended without finishing — click Resume to continue",
                status="interrupted",
            )
            reconciled += 1
            logger.info("Reconciled orphaned render job %s (was stuck, untracked)", jid)
        return reconciled
    except Exception as exc:
        logger.warning("reconcile_orphaned_render_jobs failed (non-fatal): %s", exc)
        return 0


def recover_pending_render_jobs():
    """
    Called once on server startup.

    Marks any jobs that were left in 'queued' or 'running' state as
    'interrupted' — does NOT auto-restart them.  The user can manually
    resume from the UI (Resume button) if they want to continue.

    Strategic-6 — Audit 2026-06-08 closure (Batch A V9-F5). Jobs left
    in the transient 'cancelling' state are FINALISED to 'cancelled'
    on restart. Pre-Strategic-6 the in-process cancel event lived in
    ``cancel_registry`` (jobs/cancel.py) which evaporates at process
    death; the DB status sat at 'cancelling' forever because the
    recovery loop only handled queued/running. Adding the
    cancelling → cancelled transition preserves the operator's
    cancel intent across server restarts.

    Auto-restarting old jobs on startup is unexpected behaviour: the user
    may have intentionally stopped the server, or the jobs may be days old.
    """
    try:
        from app.db.jobs_repo import list_jobs, update_job_progress
        jobs = list_jobs()
        marked = 0
        cancelled_finalised = 0
        for job in jobs:
            if job.get("kind") not in ("render", "download"):
                continue
            status = job.get("status")
            job_id = job["job_id"]

            if status in ("queued", "running"):
                update_job_progress(
                    job_id,
                    job.get("stage", "unknown"),
                    job.get("progress_percent", 0),
                    "Server restarted — click Resume to continue",
                    status="interrupted",
                )
                marked += 1
                logger.info("Marked job %s as interrupted (was %s)", job_id, status)
            elif status == "cancelling":
                # Strategic-6 — finalise the operator's cancel intent
                # to the terminal CANCELLED state. The in-process
                # cancel event is gone (process died); the DB row
                # carries forward the user's last-known intent.
                update_job_progress(
                    job_id,
                    "cancelled",
                    job.get("progress_percent", 0),
                    "Server restarted — finalising cancel from prior session",
                    status="cancelled",
                )
                cancelled_finalised += 1
                logger.info(
                    "Finalised job %s cancelling -> cancelled "
                    "(Strategic-6 — V9-F5 closure)", job_id,
                )

        total = marked + cancelled_finalised
        if total:
            logger.info(
                "Startup: marked %d job(s) as interrupted, finalised %d "
                "cancelling -> cancelled. User can resume any interrupted "
                "job from the UI.",
                marked, cancelled_finalised,
            )
        else:
            logger.info(
                "Startup: no interrupted jobs — queue is clean. "
                "Note: jobs queued in memory at shutdown are not auto-restarted; "
                "only DB-persisted jobs with status 'queued'/'running' are recovered."
            )
    except Exception as exc:
        logger.warning("Job recovery marking failed (non-fatal): %s", exc)

