"""
Editing routes — trim, re-render selection, export clip.

POST /api/jobs/{job_id}/parts/{part_no}/trim
POST /api/jobs/{job_id}/parts/{part_no}/rerender
POST /api/jobs/{job_id}/parts/{part_no}/export

Security:
  - Accepts only job_id (path param) and part_no (path param).
  - Source media resolved from DB — never from client-supplied paths.
  - Export destination validated: absolute path, within safe roots.
  - AI does NOT control these operations.
"""
import logging
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.features.render.editing.editing_service import (
    apply_trim,
    rerender_selection,
    export_clip,
)

logger = logging.getLogger("app.routes.editing")
router = APIRouter(prefix="/api/jobs", tags=["editing"])

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _validate_job_id(job_id: str) -> None:
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")


# ── Schemas ───────────────────────────────────────────────────────────────────

class TrimRequest(BaseModel):
    start_sec: float = Field(..., ge=0.0, description="Trim start in seconds")
    end_sec: float = Field(..., gt=0.0, description="Trim end in seconds")
    output_mode: str = Field(default="new_job", description="'new_job' (default) or 'replace'")


class RerenderRequest(BaseModel):
    start_sec: float = Field(..., ge=0.0)
    end_sec: float = Field(..., gt=0.0)
    effect_preset: str | None = Field(default=None)
    subtitle_style: str | None = Field(default=None)


class ExportRequest(BaseModel):
    destination_dir: str = Field(..., min_length=1, description="Absolute path to destination directory")
    # Publish v1 (additive, conservative defaults — Sacred Contract #2 spirit):
    platform_preset: str | None = Field(
        default=None, description="tiktok | youtube_shorts | instagram_reels — adds platform subfolder + filename tag")
    write_metadata: bool = Field(
        default=False, description="Write a .txt sidecar with AI title/reason + platform hashtags")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/{job_id}/parts/{part_no}/trim")
def api_trim_part(job_id: str, part_no: int, req: TrimRequest):
    """
    Trim a rendered clip to [start_sec, end_sec].

    Default output_mode is 'new_job' — writes a new file, never overwrites original.
    Returns the output file path and actual duration.
    """
    _validate_job_id(job_id)
    if part_no <= 0:
        raise HTTPException(status_code=400, detail="part_no must be a positive integer")

    try:
        result = apply_trim(
            job_id=job_id,
            part_no=part_no,
            start_sec=req.start_sec,
            end_sec=req.end_sec,
            output_mode=req.output_mode,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("trim error job_id=%s part_no=%d: %s", job_id, part_no, exc)
        raise HTTPException(status_code=500, detail="Trim operation failed")


@router.post("/{job_id}/parts/{part_no}/rerender")
def api_rerender_part(job_id: str, part_no: int, req: RerenderRequest):
    """
    Create a new render job for a selected segment of a completed part.

    Returns immediately with the new job_id. Check /api/jobs/{new_job_id} for status.
    """
    _validate_job_id(job_id)
    if part_no <= 0:
        raise HTTPException(status_code=400, detail="part_no must be a positive integer")

    try:
        result = rerender_selection(
            job_id=job_id,
            part_no=part_no,
            start_sec=req.start_sec,
            end_sec=req.end_sec,
            effect_preset=req.effect_preset,
            subtitle_style=req.subtitle_style,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("rerender error job_id=%s part_no=%d: %s", job_id, part_no, exc)
        raise HTTPException(status_code=500, detail="Re-render operation failed")


@router.post("/{job_id}/parts/{part_no}/export")
def api_export_part(job_id: str, part_no: int, req: ExportRequest):
    """
    Export a rendered clip to a user-specified directory.

    destination_dir must be an absolute path within allowed safe roots.
    """
    _validate_job_id(job_id)
    if part_no <= 0:
        raise HTTPException(status_code=400, detail="part_no must be a positive integer")

    try:
        result = export_clip(
            job_id=job_id,
            part_no=part_no,
            destination_dir=req.destination_dir,
            platform_preset=req.platform_preset,
            write_metadata=req.write_metadata,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("export error job_id=%s part_no=%d: %s", job_id, part_no, exc)
        raise HTTPException(status_code=500, detail="Export operation failed")
