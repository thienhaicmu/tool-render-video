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
import re
import time
import uuid
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
