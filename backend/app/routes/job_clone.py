"""
routes/job_clone.py — Job Clone / Re-render API.

Phase M — Job Clone / Re-render.

POST /api/jobs/{job_id}/clone
    Deserialize the stored payload_json of an existing job, merge optional
    override fields, enqueue a new independent render job with a fresh job_id.

    Body (all optional):
        whisper_model, output_count, llm_model, channel_code, output_dir,
        ai_provider, target_platform, target_duration, hook_strength,
        video_type, ai_clip_min_duration_sec, ai_clip_max_duration_sec

    Response:
        { "job_id": "...", "source_job_id": "...", "status": "queued" }

Design:
  - The source job's payload_json is deserialized into RenderRequest.
  - Override fields are applied via model_copy(update={...}).
  - The original job row is untouched (Sacred Contract #7).
  - No render pipeline files are touched.

Risk: MEDIUM — deserializes stored payload and enqueues via _queue_render_job.
Approved: 2026-06-13 (user approval in conversation).

Blast radius: MEDIUM — new file only. Uses existing _queue_render_job which
is already the standard queue path. No pipeline changes, no schema changes.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db.jobs_repo import get_job
from app.features.render.routers._common import _queue_render_job, _validate_output_dir
from app.models.schemas import RenderRequest

logger = logging.getLogger("app.routes.job_clone")
router = APIRouter(prefix="/api/jobs", tags=["job-clone"])

# Fields the clone endpoint allows to override. Restricted to FE-facing /
# config fields — server-derived plumbing fields (job_id, source_mode, etc.)
# are never overridable to prevent misuse.
_CLONE_OVERRIDE_FIELDS: frozenset[str] = frozenset({
    "whisper_model",
    "output_count",
    "llm_model",
    "channel_code",
    "output_dir",
    "ai_provider",
    "target_platform",
    "target_duration",
    "hook_strength",
    "video_type",
    "ai_clip_min_duration_sec",
    "ai_clip_max_duration_sec",
    "add_subtitle",
    "subtitle_style",
    "llm_enabled",
})


class CloneJobRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    whisper_model: Optional[str] = None
    output_count: Optional[int] = Field(None, ge=1, le=20)
    llm_model: Optional[str] = None
    channel_code: Optional[str] = None
    output_dir: Optional[str] = None
    ai_provider: Optional[str] = None
    target_platform: Optional[str] = None
    target_duration: Optional[int] = Field(None, ge=0)
    hook_strength: Optional[str] = None
    video_type: Optional[str] = None
    ai_clip_min_duration_sec: Optional[float] = Field(None, ge=1.0)
    ai_clip_max_duration_sec: Optional[float] = Field(None, ge=1.0)
    add_subtitle: Optional[bool] = None
    subtitle_style: Optional[str] = None
    llm_enabled: Optional[bool] = None


@router.post("/{job_id}/clone")
def clone_job(job_id: str, body: CloneJobRequest) -> dict:
    """Clone an existing job with optional override fields.

    The source job's stored configuration is used as the base. The body
    fields are merged on top. The original job is never modified.
    """
    source_job = get_job(job_id)
    if source_job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    payload_json_str = source_job.get("payload_json") or "{}"
    try:
        payload_dict = json.loads(payload_json_str)
        if not isinstance(payload_dict, dict):
            payload_dict = {}
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Source job has an invalid payload_json — cannot clone",
        )

    # Apply allowed overrides from the request body
    override_dict = {
        k: v
        for k, v in body.model_dump().items()
        if v is not None and k in _CLONE_OVERRIDE_FIELDS
    }
    payload_dict.update(override_dict)

    try:
        payload = RenderRequest(**payload_dict)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Cloned payload is invalid: {exc}",
        )

    new_job_id = str(uuid.uuid4())
    effective_channel = (payload.channel_code or "manual").strip() or "manual"

    try:
        _queue_render_job(
            new_job_id,
            effective_channel,
            payload,
            resume_mode=False,
            queued_message=f"Cloned from {job_id}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("job_clone: queue failed source=%s new=%s: %s", job_id, new_job_id, exc)
        raise HTTPException(status_code=500, detail=f"Failed to enqueue clone: {exc}")

    logger.info("job_clone: queued new_job_id=%s source=%s", new_job_id, job_id)
    return {
        "job_id":        new_job_id,
        "source_job_id": job_id,
        "status":        "queued",
    }
