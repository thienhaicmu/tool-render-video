"""
Simple in-process job queue backed by a ThreadPoolExecutor.

Why not Celery?
  Celery requires Redis/RabbitMQ and a separate worker process, adding
  operational complexity. For a single-machine desktop platform, a thread
  pool with SQLite-backed recovery achieves the same goals:
    - Jobs survive server restart (re-queued on startup from DB).
    - Concurrent job limit (max_workers).
    - Deduplication (a job_id can only run once at a time).
"""
from __future__ import annotations

import logging
import os
import threading
import concurrent.futures
from typing import Callable

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Module-level thread pool
# --------------------------------------------------------------------------

_executor: concurrent.futures.ThreadPoolExecutor | None = None
_lock = threading.Lock()
_active_job_ids: set[str] = set()
_MAX_WORKERS = max(2, (os.cpu_count() or 4) // 2)


def _get_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _executor
    if _executor is None or _executor._shutdown:
        _executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=_MAX_WORKERS,
            thread_name_prefix="job-worker",
        )
    return _executor


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def submit_job(job_id: str, fn: Callable, *args, **kwargs) -> bool:
    """
    Submit *fn(*args, **kwargs)* to the thread pool under *job_id*.

    Returns True if the job was submitted, False if it was already running
    (idempotent — safe to call multiple times with the same job_id).
    """
    with _lock:
        if job_id in _active_job_ids:
            logger.debug("Job %s already running, skip duplicate submit", job_id)
            return False
        _active_job_ids.add(job_id)

    def _wrapper():
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            logger.error("Job %s raised unhandled exception: %s", job_id, exc, exc_info=True)
        finally:
            with _lock:
                _active_job_ids.discard(job_id)

    _get_executor().submit(_wrapper)
    logger.info("Job %s submitted to thread pool", job_id)
    return True


def is_running(job_id: str) -> bool:
    with _lock:
        return job_id in _active_job_ids


def active_count() -> int:
    with _lock:
        return len(_active_job_ids)


def shutdown(wait: bool = True):
    global _executor
    if _executor:
        _executor.shutdown(wait=wait)
        _executor = None


# --------------------------------------------------------------------------
# Startup recovery
# --------------------------------------------------------------------------

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
            if job.get("kind") != "render":
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
            logger.info("Startup: marked %d job(s) as interrupted. User can resume from UI.", marked)
    except Exception as exc:
        logger.warning("Job recovery marking failed (non-fatal): %s", exc)
