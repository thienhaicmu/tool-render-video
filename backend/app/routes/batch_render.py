"""
routes/batch_render.py — Batch Render from Asset Library.

Phase K — Batch Render.

POST /api/render/batch
    Enqueue one render job per asset_id in the request body, optionally
    applying a shared preset. Each job is fully independent — failure
    or skipping of one does not affect the others.

    Request body fields:
        asset_ids   — list of 1–20 asset UUIDs from the Asset Library.
        preset_id   — optional preset to apply to every job.
        output_dir  — shared output directory. Falls back to the saved
                      default from creator_prefs when omitted.
        channel_code — shared channel code. Defaults to "manual".

    Response:
        {total, queued, skipped, jobs: [{asset_id, job_id, status, error?}]}

    Assets that are not found in the DB or whose file_path does not exist
    on disk are reported as status="skipped" in the jobs list.

Blast radius: LOW — new file. Imports from _common.py without modifying it.
No render pipeline changes. No DB schema changes.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db.assets_repo import get_asset
from app.db.presets_repo import get_preset
from app.domain.render_preset import PRESET_ALLOWED_PARAMS
from app.features.render.routers._common import _queue_render_job, _validate_output_dir
from app.models.schemas import RenderRequest

logger = logging.getLogger("app.routes.batch_render")
router = APIRouter(prefix="/api/render", tags=["batch-render"])

_MAX_BATCH_SIZE = 20


class BatchRenderRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    asset_ids: list[str] = Field(..., min_length=1, max_length=_MAX_BATCH_SIZE)
    preset_id: Optional[str] = None
    output_dir: Optional[str] = None
    channel_code: str = "manual"


class BatchRenderJobResult(BaseModel):
    asset_id: str
    job_id: str
    status: str          # "queued" | "skipped"
    error: Optional[str] = None


class BatchRenderResponse(BaseModel):
    total: int
    queued: int
    skipped: int
    jobs: list[BatchRenderJobResult]


@router.post("/batch", response_model=BatchRenderResponse)
def create_batch_render(body: BatchRenderRequest) -> BatchRenderResponse:
    """Enqueue one render job per asset. Returns a result for each asset_id."""
    if not body.asset_ids:
        raise HTTPException(status_code=422, detail="asset_ids must not be empty")

    # Resolve preset params once (shared across all jobs).
    preset_params: dict = {}
    if body.preset_id:
        preset = get_preset(body.preset_id.strip())
        if preset is None:
            raise HTTPException(status_code=404, detail=f"Preset not found: {body.preset_id}")
        preset_params = {k: v for k, v in (preset.params or {}).items() if k in PRESET_ALLOWED_PARAMS}

    # Resolve shared output_dir — fall back to saved default when omitted.
    shared_output_dir = (body.output_dir or "").strip()
    if not shared_output_dir:
        try:
            from app.db.creator_repo import get_default_output_dir
            shared_output_dir = get_default_output_dir() or ""
        except Exception:
            pass
    if not shared_output_dir:
        raise HTTPException(
            status_code=400,
            detail=(
                "output_dir is required for batch render. Provide it in the request body "
                "or set a default in Settings → Output Directory."
            ),
        )

    channel = (body.channel_code or "manual").strip() or "manual"
    jobs: list[BatchRenderJobResult] = []
    queued = 0
    skipped = 0

    for asset_id in body.asset_ids:
        asset_id = asset_id.strip()
        job_id = str(uuid.uuid4())

        # Look up the asset.
        asset = get_asset(asset_id) if asset_id else None
        if asset is None:
            logger.warning("batch_render: asset not found asset_id=%s — skipping", asset_id)
            jobs.append(BatchRenderJobResult(
                asset_id=asset_id, job_id=job_id,
                status="skipped", error="asset_not_found",
            ))
            skipped += 1
            continue

        # Verify the source file is still on disk.
        if not asset.file_path or not Path(asset.file_path).is_file():
            logger.warning(
                "batch_render: source file missing asset_id=%s path=%s — skipping",
                asset_id, asset.file_path,
            )
            jobs.append(BatchRenderJobResult(
                asset_id=asset_id, job_id=job_id,
                status="skipped", error="source_file_missing",
            ))
            skipped += 1
            continue

        # Build the RenderRequest — preset params first, then fixed fields.
        render_kwargs: dict = {
            "source_mode": "local",
            "source_video_path": asset.file_path,
            "output_dir": shared_output_dir,
            "channel_code": channel,
            "asset_id": asset_id,
        }
        render_kwargs.update(preset_params)
        payload = RenderRequest(**render_kwargs)

        try:
            _queue_render_job(
                job_id, channel, payload,
                resume_mode=False,
                queued_message="Batch render queued",
            )
        except HTTPException as exc:
            logger.warning(
                "batch_render: queue failed asset_id=%s job_id=%s: %s",
                asset_id, job_id, exc.detail,
            )
            jobs.append(BatchRenderJobResult(
                asset_id=asset_id, job_id=job_id,
                status="skipped", error=str(exc.detail),
            ))
            skipped += 1
            continue

        jobs.append(BatchRenderJobResult(
            asset_id=asset_id, job_id=job_id, status="queued",
        ))
        queued += 1

    return BatchRenderResponse(
        total=len(body.asset_ids),
        queued=queued,
        skipped=skipped,
        jobs=jobs,
    )
