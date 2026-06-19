"""
routes/snapshot.py — Job Snapshot Endpoint.

GET /api/jobs/{job_id}/snapshot
    Return a single JSON blob with the shape of a WebSocket progress event:
        { "job": {...}, "parts": [...], "summary": {...} }

    Used by the frontend when a WebSocket reconnects — instead of polling
    three separate endpoints and recomputing the summary client-side, one
    call provides a fully-consistent snapshot of the current job state.

    The response shape is frozen (Sacred Contract #6 spirit):
    the three top-level keys "job", "parts", and "summary" are always present,
    even when the job has no parts yet.

Blast radius: LOW — new file, no existing routes or pipeline files modified.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.jobs_repo import get_job, list_job_parts
from app.routes.jobs import _compute_progress_summary

router = APIRouter(prefix="/api/jobs", tags=["snapshot"])


@router.get("/{job_id}/snapshot")
def get_job_snapshot(job_id: str) -> dict:
    """Return a WebSocket-shaped snapshot of the current job state.

    Response shape mirrors the frozen WebSocket event (Sacred Contract #6):
        { "job": {...}, "parts": [...], "summary": {...} }

    Frontend can use this on WS reconnect to immediately re-sync progress
    without waiting for the next pipeline event emission.
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    parts = list_job_parts(job_id)
    summary = _compute_progress_summary(parts)

    return {
        "job":     job,
        "parts":   parts,
        "summary": summary,
    }
