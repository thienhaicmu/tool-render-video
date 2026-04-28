"""Unified job event emitter — shared schema for render and skill runner."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger("app.jobs.events")


def emit_job_event(
    job_id: str,
    job_type: str,
    event: str,
    status: str,
    *,
    step: str | None = None,
    step_index: int | None = None,
    total_steps: int | None = None,
    progress: int | None = None,
    message: str = "",
    level: str = "info",
    context: dict | None = None,
) -> dict:
    """
    Emit a structured job event and return it as a dict for storage in result_json.

    Schema:
        job_id, job_type, event, status, step, step_index, total_steps,
        progress, message, level, timestamp, context
    """
    record = {
        "job_id":      job_id,
        "job_type":    job_type,
        "event":       event,
        "status":      status,
        "step":        step,
        "step_index":  step_index,
        "total_steps": total_steps,
        "progress":    progress,
        "message":     message,
        "level":       level,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
        "context":     context or {},
    }
    log_fn = getattr(
        logger,
        level if level in ("debug", "info", "warning", "error") else "info",
    )
    log_fn(
        "job_event job_id=%s type=%s event=%s step=%s status=%s msg=%s",
        job_id, job_type, event, step, status, message,
    )
    return record
