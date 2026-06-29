"""Shared helpers used by multiple render sub-routers.

Extracted from the original ``features/render/router.py`` monolith
during the audit FINDING-A03 router split (2026-06-06).

The helpers live here (not in any one sub-router file) because they are
called from more than one bucket:

- ``_emit_request_event`` — Type 1 (request validation) error logger.
  Used by lifecycle.py at the /process boundary; reserved for any other
  endpoint that wants to log a 4xx into request.log.
- ``_UUID_RE`` — UUID format regex. Used by prepare.py for client-supplied
  session_ids; available to any handler that needs the same shape.
- ``_validate_output_dir`` / ``_coerce_legacy_channel_payload`` /
  ``_validate_render_source`` — shared validation chain used by both
  ``/process`` and the resume/retry endpoints.
- ``process_render`` — the in-thread render-job entry point invoked by
  ``submit_job`` from the queue. Used by every lifecycle endpoint that
  enqueues work.
- ``_queue_render_job`` — DB insert + queue submit. Used by /process,
  /resume and /retry.

Error classification (Sacred Contract #6 events vs request.log):

Type 1 · Request / validation errors — HTTPException raised BEFORE
        process_render. Logged as WARNING into request.log via
        ``_emit_request_event``. NOT written to error.log (pipeline
        never starts).
Type 2 · Render pipeline errors — exception INSIDE process_render.
        Logged as ERROR via ``_emit_render_event`` into:
          data/logs/error.log
          channels/{code}/logs/{job_id}.log
          data/logs/app.log
Type 3 · Unexpected / system errors — unhandled exception in the route
        function itself. Logged by FastAPI default handler to
        desktop-backend.log. NOT written to error.log.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from app.core.config import REQUEST_LOG
from app.core.stage import JobStage
from app.features.render.engine.pipeline.render_pipeline import (
    _append_json_line,
    run_render_pipeline,
)
from app.features.render.engine.preview.session_service import (
    _cleanup_preview_session,
    _load_session,
)
from app.jobs.manager import is_running, submit_job
from app.models.schemas import RenderRequest
from app.db.connection import close_thread_conn
from app.db.jobs_repo import get_job, update_job_progress, upsert_job
logger = logging.getLogger("app.render")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _emit_request_event(
    *,
    route: str,
    status_code: int,
    detail: str,
    channel_code: str = "",
):
    """Write Type 1 (request/validation) errors to request.log as JSON-lines."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "WARNING",
        "event": "render.request.rejected",
        "module": "render",
        "message": detail,
        "route": route,
        "status_code": status_code,
        "channel_code": channel_code,
    }
    _append_json_line(REQUEST_LOG, entry)


def _validate_output_dir(payload: RenderRequest):
    """Require output_dir, auto-populating from saved setting when empty."""
    if not (payload.output_dir or "").strip():
        saved: "str | None" = None
        try:
            from app.db.creator_repo import get_default_output_dir
            saved = get_default_output_dir()
        except Exception:
            pass
        if saved:
            payload.output_dir = saved
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    "output_dir is required. Go to Settings → Output Directory "
                    "to set a default and avoid sending it with every request."
                ),
            )
    # Reject the case where the path exists but is a file — the pipeline cannot
    # mkdir over an existing file. Non-existent paths are fine (pipeline creates them).
    resolved = Path(payload.output_dir).expanduser()
    if not resolved.is_absolute():
        resolved = (Path.cwd() / resolved).resolve()
    if resolved.exists() and not resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"output_dir exists but is not a directory: {payload.output_dir}",
        )
    # Bug N6 (audit 2026-06-15): probe write access on the nearest existing
    # ancestor so the pipeline doesn't fail 60 s into a render with a
    # cryptic OSError. Walks up the tree until we find a directory that
    # exists (output_dir may not be created yet — that's fine, the pipeline
    # will mkdir it). We only need to confirm the parent is writable.
    import os as _os_n6
    probe = resolved if resolved.exists() else resolved.parent
    while probe and not probe.exists():
        nxt = probe.parent
        if nxt == probe:
            break
        probe = nxt
    if probe.exists() and not _os_n6.access(str(probe), _os_n6.W_OK):
        raise HTTPException(
            status_code=400,
            detail=(
                f"output_dir is not writable: {payload.output_dir} "
                f"(no write permission on {probe}). "
                "Pick a different folder or fix the permissions."
            ),
        )
    # N8 (audit 2026-06-15): probe free disk space on the output partition so
    # a render that would fill the disk halfway through gets rejected at
    # submit time with a clear message instead of failing 20 minutes in with
    # an OSError. The thresholds below are conservative — we don't know the
    # exact source size yet, but anything < 256 MB free is guaranteed to
    # break, and < 2 GB will run the cache pruner constantly. Both numbers
    # are env-overridable for unusual deployments (test fixtures on small
    # tmpfs, etc.).
    import shutil as _shutil_n8
    _min_free_mb_hard = int(os.getenv("RENDER_MIN_FREE_DISK_MB", "256"))
    _min_free_mb_warn = int(os.getenv("RENDER_WARN_FREE_DISK_MB", "2048"))
    try:
        _usage = _shutil_n8.disk_usage(str(probe))
        _free_mb = _usage.free // (1024 * 1024)
        if _free_mb < _min_free_mb_hard:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"output_dir partition has only {_free_mb} MB free. "
                    f"Render requires at least {_min_free_mb_hard} MB. "
                    "Free up space on the drive or pick a different folder."
                ),
            )
        if _free_mb < _min_free_mb_warn:
            logger.warning(
                "output_dir partition low on space: only %s MB free (< %s MB warn). "
                "Render may exhaust disk mid-pipeline.",
                _free_mb, _min_free_mb_warn,
            )
    except HTTPException:
        raise
    except Exception as _disk_exc:
        # disk_usage can fail on network shares or permission-restricted paths.
        # Don't block the render — log and let the pipeline discover the
        # OSError naturally if disk really is full.
        logger.warning("disk space probe failed for %s: %s", probe, _disk_exc)


def _validate_render_source(payload: RenderRequest):
    # When an editor session is provided, the pipeline uses the session's video_path;
    # skip source-path validation entirely.
    if (getattr(payload, "edit_session_id", None) or "").strip():
        _validate_output_dir(payload)
        return

    mode = (payload.source_mode or "local").lower().strip()
    local = (payload.source_video_path or "").strip()

    # Render pipeline only accepts local files. Use the standalone Downloader
    # feature first to fetch a remote source as a local file, then submit here.
    if mode != "local":
        raise HTTPException(
            status_code=400,
            detail=(
                f"source_mode='{mode}' is not supported by /api/render/process. "
                "Use the standalone Downloader to fetch remote sources as local files."
            ),
        )

    if not local:
        raise HTTPException(status_code=400, detail="source_video_path is required when source_mode='local'")
    if not Path(local).exists():
        raise HTTPException(status_code=400, detail=f"Source file not found on disk: {local}")
    _validate_output_dir(payload)


def process_render(job_id: str, payload: RenderRequest, resume_mode: bool = False):
    """In-thread render-job entry point invoked by ``submit_job`` from the queue.

    Wraps ``run_render_pipeline`` with cancel-registry housekeeping and
    Prometheus terminal-status / duration instrumentation.
    """
    from app.jobs import cancel as cancel_registry
    from app.services.metrics import RENDER_JOB_DURATION, RENDER_JOBS_TOTAL

    # Phase C — Asset Library: persist asset_id on the job row if provided.
    # Never raises — asset linkage must not block or fail a render.
    _asset_id = (getattr(payload, "asset_id", None) or "").strip()
    if _asset_id:
        try:
            from app.db.jobs_repo import update_job_asset_id
            update_job_asset_id(job_id, _asset_id)
        except Exception:
            pass

    ev = cancel_registry.register(job_id)
    # Sprint 6.C: instrument terminal status + wallclock per job. `final_status`
    # starts as "succeeded" because the happy path falls through the try block
    # without setting it. Cancellation + failure paths overwrite it.
    start_monotonic = time.monotonic()
    final_status = "succeeded"
    try:
        # A cancel requested while the job was still queued pre-sets the event.
        if ev.is_set():
            raise cancel_registry.JobCancelledError()
        # render_format="recap" routes to a FULLY SEPARATE orchestrator so the
        # clips path (run_render_pipeline) is never touched. Both share this
        # wrapper's cancel / failure / metrics / close_thread_conn housekeeping.
        if str(getattr(payload, "render_format", "clips") or "clips").strip().lower() == "recap":
            from app.features.render.engine.pipeline.recap_pipeline import run_recap
            run_recap(
                job_id=job_id,
                payload=payload,
                resume_mode=resume_mode,
                load_session_fn=_load_session,
                cleanup_session_fn=_cleanup_preview_session,
            )
        else:
            run_render_pipeline(
                job_id=job_id,
                payload=payload,
                resume_mode=resume_mode,
                load_session_fn=_load_session,
                cleanup_session_fn=_cleanup_preview_session,
            )
    except cancel_registry.JobCancelledError:
        # P3-B1: use the JobStage enum constant instead of the raw string so a
        # future enum-only validation refactor doesn't silently break cancellation.
        update_job_progress(
            job_id, JobStage.CANCELLED, 0,
            "Job cancelled by user",
            status=JobStage.CANCELLED,
        )
        final_status = "cancelled"
    except Exception:
        final_status = "failed"
        # Belt-and-suspenders: run_render_pipeline runs setup (setup_render_pipeline,
        # prepare_output_dir, …) BEFORE its own try/except, and JobCancelledError
        # aside, any exception from that setup phase propagates here WITHOUT a
        # terminal DB write. The job would then sit at status='running' forever —
        # a phantom "active" job that makes the queue dedup + the UI's
        # active-job reattach block every NEW render (the user has to manually
        # kill it). Force the row terminal so a dead worker never blocks the queue.
        try:
            _cur = get_job(job_id)
            if (_cur or {}).get("status") in (None, "running", "queued"):
                update_job_progress(
                    job_id, JobStage.FAILED, 0,
                    "Render failed before completion",
                    status="failed",
                )
        except Exception:
            pass
        raise
    finally:
        # Audit FINDING-BR10 closure (Batch 10A ST-14): belt-and-suspenders
        # cleanup of the worker thread's cached SQLite connection.
        # ``run_render_pipeline`` already closes it in its own outer finally
        # for the normal path. But if the pipeline dies BEFORE reaching its
        # try block (e.g., setup_render_pipeline / prepare_output_dir raises),
        # the cleanup there never runs and the thread-local connection lives
        # until the worker thread is GC'd — a cumulative leak on a long-lived
        # process. Calling it here is idempotent: the second close sees
        # ``_tls.conn is None`` from the first and no-ops.
        try:
            close_thread_conn()
        except Exception:
            pass
        duration = time.monotonic() - start_monotonic
        try:
            RENDER_JOBS_TOTAL.labels(status=final_status).inc()
            RENDER_JOB_DURATION.labels(status=final_status).observe(duration)
        except Exception:
            # Metrics must NEVER fail a render. The no-op shim covers the
            # missing-prometheus path; this except catches anything else.
            pass
        cancel_registry.unregister(job_id)


def _find_active_duplicate_source(channel_code: str, source_path: str) -> str | None:
    """Return job_id of an active (running/queued/cancelling/recently-cancelled)
    job with the same source, or None.

    Defense against accidental double-submit + cancel-resubmit race:
      * Layer A — DB scan for jobs whose status is still 'running',
        'queued', or 'cancelling' (the cancelling state didn't block
        resubmit before ADR-007 — root cause of the duplicate-Whisper
        bug reported 2026-06-27).
      * Layer B — in-memory ledger of jobs cancelled within the last
        30 s, populated by cancel.note_cancel(). Gives the previous
        job's subprocess time to fully exit before letting the same
        source re-enter the pipeline.

    Resume/retry paths bypass this (they reuse an existing job_id and
    shouldn't be dedup'd against themselves) — see _queue_render_job's
    `resume_mode` guard.
    """
    src = (source_path or "").strip()
    if not src:
        return None
    from app.db.jobs_repo import list_jobs_page
    # Layer A: DB scan. 30 most recent jobs covers the active queue
    # (bounded by MAX_CONCURRENT_JOBS) + any in-flight cancelling.
    _BLOCK_STATUSES = ("running", "queued", "cancelling")
    for j in list_jobs_page(30, 0):
        if (j.get("status") or "") not in _BLOCK_STATUSES:
            continue
        if (j.get("channel_code") or "") != channel_code:
            continue
        try:
            stored = json.loads(j.get("payload_json") or "{}")
        except Exception:
            continue
        if (stored.get("source_video_path") or "").strip() == src:
            return j.get("job_id")
    # Layer B: recently-cancelled ledger (ADR-007 grace window).
    from app.jobs import cancel as cancel_registry
    recent = cancel_registry.is_cancelling_recently(src, channel_code)
    if recent:
        return recent
    return None


def _queue_render_job(
    job_id: str,
    effective_channel: str,
    payload: RenderRequest,
    *,
    resume_mode: bool,
    queued_message: str,
):
    """Insert the job row and submit to the queue.

    If ``submit_job`` reports the job is already running, restore the previous
    DB row exactly (so the in-memory state matches stored history) and raise 409.
    """
    if is_running(job_id):
        raise HTTPException(status_code=409, detail="Render job is already running")

    # Source-path dedup (Layer 2 defense — fresh /process only, not resume/retry).
    # When the FE submits the same source twice with different UUIDs (e.g. user
    # double-clicks the Start-Render button across a slow network), the
    # queue-level job_id dedup misses it because the IDs differ. Catch it here
    # by comparing source_video_path + channel against recently-active jobs.
    if not resume_mode:
        dup_job = _find_active_duplicate_source(
            effective_channel, payload.source_video_path or ""
        )
        if dup_job and dup_job != job_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    "A render job for this source is already in progress "
                    f"(job_id={dup_job}). Wait for it to finish or cancel it first."
                ),
            )
    previous = get_job(job_id)
    upsert_job(
        job_id,
        "render",
        effective_channel,
        "queued",
        payload.model_dump(),
        {},
        stage=JobStage.QUEUED,
        progress_percent=0,
        message=queued_message,
    )
    submitted = submit_job(job_id, process_render, job_id, payload, resume_mode)
    if submitted:
        return

    if previous:
        try:
            previous_payload = json.loads(previous.get("payload_json") or "{}")
        except Exception:
            previous_payload = {}
        try:
            previous_result = json.loads(previous.get("result_json") or "{}")
        except Exception:
            previous_result = {}
        upsert_job(
            job_id,
            previous.get("kind") or "render",
            previous.get("channel_code") or effective_channel,
            previous.get("status") or "queued",
            previous_payload,
            previous_result,
            stage=previous.get("stage") or JobStage.QUEUED,
            progress_percent=int(previous.get("progress_percent") or 0),
            message=previous.get("message") or "",
        )
    raise HTTPException(status_code=409, detail="Render job is already running")
