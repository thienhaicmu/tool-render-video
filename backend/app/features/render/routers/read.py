"""Read-only per-job media endpoints (audit FINDING-A03 read bucket).

Covers the 4 GET endpoints that serve job metadata or rendered artifacts:
- /jobs/{job_id} (duplicate of /api/jobs/{job_id}; see audit FINDING-API03)
- /jobs/{job_id}/parts/{part_no}/media (HTTP Range streaming)
- /jobs/{job_id}/parts/{part_no}/thumbnail
- /subtitle-preview (style preview, FE not wired today per Phase 6)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from app.features.render.engine.preview.media_streaming import (
    _iter_file_bytes,
    _parse_range_header,
)
from app.db.jobs_repo import list_job_parts
router = APIRouter(tags=["render"])


# Audit FINDING-API03 closure (2026-06-06): the GET /api/render/jobs/{job_id}
# endpoint that used to live here was a byte-for-byte duplicate of
# GET /api/jobs/{job_id} (routes/jobs.py:api_get_job). The FE only ever
# called the /api/jobs/... path; the duplicate just bloated the contract
# surface. The /api/render/jobs/{job_id}/parts/{part_no}/{media,thumbnail}
# endpoints below are NOT duplicates — they expose render-specific
# artefacts (streaming bytes, JPEG thumbnails) that /api/jobs/... doesn't.


# ── Rendered clip media streaming ───────────────────────────────────────────
@router.get("/jobs/{job_id}/parts/{part_no}/media")
def stream_render_part_media(job_id: str, part_no: int, request: Request):
    """Stream a rendered clip output file with proper HTTP Range request support.

    Chrome's <video> element sends a Range probe on every load; without a real
    206 Partial Content response the element stalls until the full file is
    buffered, making clips appear broken. This endpoint handles Range correctly
    so playback starts immediately.

    Security: the file path is looked up from the job_parts DB record, never
    taken from user input, so there is no path-traversal risk.
    """
    parts = list_job_parts(job_id)
    part = next((p for p in parts if int(p.get("part_no", -1)) == part_no), None)
    if not part or not part.get("output_file"):
        raise HTTPException(status_code=404, detail="Part not found")

    path = Path(part["output_file"])
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found on disk")

    file_size = path.stat().st_size
    if file_size == 0:
        raise HTTPException(status_code=404, detail="Output file is empty")

    range_header = request.headers.get("range", "").strip()

    if range_header:
        byte1, byte2 = _parse_range_header(range_header, file_size)
        length = byte2 - byte1 + 1
        return StreamingResponse(
            _iter_file_bytes(path, byte1, byte2),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range":   f"bytes {byte1}-{byte2}/{file_size}",
                "Accept-Ranges":   "bytes",
                "Content-Length":  str(length),
                "Cache-Control":   "no-store",
            },
        )

    # No Range header — send the full file (still streaming, never buffered in-process).
    return StreamingResponse(
        _iter_file_bytes(path, 0, file_size - 1),
        status_code=200,
        media_type="video/mp4",
        headers={
            "Accept-Ranges":  "bytes",
            "Content-Length": str(file_size),
            "Cache-Control":  "no-store",
        },
    )


@router.get("/jobs/{job_id}/parts/{part_no}/thumbnail")
def get_render_part_thumbnail(job_id: str, part_no: int, t: float = 0.5, w: int = 320):
    """Return a JPEG thumbnail frame extracted from the rendered clip at offset t seconds.

    Cached by the browser for 24 hours (Cache-Control: public, max-age=86400).
    Security: file path is resolved from DB, never from user input.
    """
    from app.features.render.engine.encoder.ffmpeg_helpers import extract_thumbnail_frame
    parts = list_job_parts(job_id)
    part = next((p for p in parts if int(p.get("part_no", -1)) == part_no), None)
    if not part or not part.get("output_file"):
        raise HTTPException(status_code=404, detail="Part not found")
    path = Path(part["output_file"])
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found on disk")
    jpeg = extract_thumbnail_frame(str(path), offset_sec=max(0.0, t), width=max(32, min(640, w)))
    if not jpeg:
        raise HTTPException(status_code=500, detail="Thumbnail extraction failed")
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control":  "public, max-age=86400",
            "Content-Length": str(len(jpeg)),
        },
    )


@router.get("/subtitle-preview")
def api_subtitle_preview(
    style: str = "tiktok_bounce_v1",
    aspect_ratio: str = "9:16",
    font_size: int = 0,
    text: str = "This is a preview subtitle",
):
    """Return a PNG frame with the subtitle style rendered by libass.

    Uses the same ASSPreset pipeline as real renders so the preview matches
    actual output exactly. Cached by the browser for 1 hour.
    """
    from app.features.render.engine.subtitle.generator.ass import render_subtitle_preview

    safe_ratio = aspect_ratio if aspect_ratio in ("9:16", "3:4", "4:5", "1:1", "16:9") else "9:16"
    safe_size  = max(0, min(200, int(font_size)))
    safe_text  = (text or "Preview subtitle")[:200].replace("\n", " ").strip()

    try:
        png = render_subtitle_preview(
            subtitle_style=style,
            font_size=safe_size,
            aspect_ratio=safe_ratio,
            sample_text=safe_text,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Subtitle preview failed: {exc}")

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control":  "public, max-age=3600",
            "Content-Length": str(len(png)),
        },
    )
