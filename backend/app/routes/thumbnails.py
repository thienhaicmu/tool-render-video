"""
routes/thumbnails.py — Output clip thumbnail endpoint.

GET /api/jobs/{job_id}/outputs/{part_no}/thumbnail?width=320
    Extract a JPEG frame at 10 % of the clip's duration from the
    rendered output file and return it as image/jpeg.

    Results are cached under APP_DATA_DIR/cache/thumbnails/ keyed by
    md5(output_file|mtime) with a 24-hour TTL. Subsequent requests for
    the same unmodified file are served from disk without an FFmpeg call.
    The cache directory is pruned automatically by the existing
    maintenance walker (subdir-agnostic, 72-hour default TTL applies;
    thumbnails use a shorter 24-hour in-memory TTL check).

Blast radius: LOW — new file, no existing routes or pipeline files modified.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.core.config import APP_DATA_DIR
from app.db.jobs_repo import get_job, list_job_parts
from app.features.render.engine.encoder.ffmpeg_helpers import (
    extract_thumbnail_frame,
    probe_video_metadata,
)

router = APIRouter(prefix="/api/jobs", tags=["thumbnails"])

_THUMBNAIL_CACHE_TTL_SEC = 24 * 3600   # 24 h
_THUMBNAIL_DIR = APP_DATA_DIR / "cache" / "thumbnails"


def _cache_key(output_file: str, mtime: float) -> str:
    raw = f"{output_file}|{mtime}"
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> bytes | None:
    """Return cached JPEG bytes if present and within TTL, else None."""
    try:
        p = _THUMBNAIL_DIR / f"{key}.jpg"
        if not p.exists():
            return None
        if time.time() - p.stat().st_mtime > _THUMBNAIL_CACHE_TTL_SEC:
            p.unlink(missing_ok=True)
            return None
        return p.read_bytes()
    except Exception:
        return None


def _cache_put(key: str, data: bytes) -> None:
    """Write JPEG bytes to cache atomically. Silent on any error."""
    try:
        _THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _THUMBNAIL_DIR / f"{key}.jpg.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, _THUMBNAIL_DIR / f"{key}.jpg")
    except Exception:
        pass


@router.get("/{job_id}/outputs/{part_no}/thumbnail")
def get_output_thumbnail(
    job_id: str,
    part_no: int,
    width: int = Query(320, ge=64, le=1280, description="Output JPEG width in pixels"),
) -> Response:
    """Return a JPEG thumbnail frame for the given render output part.

    The frame is extracted at 10 % of the clip's duration (minimum 0.5 s).
    Results are cached by (output_file, mtime) — repeated calls for the
    same unmodified file are served instantly from disk.
    """
    _job = get_job(job_id)
    if not _job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    # Recap: serve the assembled EPISODE thumbnail (per-scene parts are internal
    # intermediates in a cleaned-up temp dir). Clips fall through to job_parts.
    from app.routes.outputs import recap_output_file_for_part
    output_file = (recap_output_file_for_part(_job, part_no) or "").strip()
    if not output_file:
        parts = list_job_parts(job_id)
        part = next((p for p in parts if int(p.get("part_no") or -1) == part_no), None)
        if part is None:
            raise HTTPException(status_code=404, detail=f"Part {part_no} not found for job {job_id}")
        output_file = str(part.get("output_file") or "").strip()
    if not output_file:
        raise HTTPException(status_code=404, detail="Part has no output file")

    if not Path(output_file).is_file():
        raise HTTPException(status_code=404, detail="Output file no longer exists on disk")

    # Prefer a designed poster sibling ({stem}.thumb.jpg) when present — Story Mode writes
    # a procedural SVG cover there at finalize. Scaled to `width` + cached; on any failure
    # we fall through to the video frame grab below (unchanged for clips/recap/content).
    poster = Path(output_file).with_name(Path(output_file).stem + ".thumb.jpg")
    if poster.is_file() and poster.stat().st_size > 0:
        try:
            pkey = _cache_key(str(poster), poster.stat().st_mtime) + f"|w{width}"
            pcached = _cache_get(pkey)
            if pcached:
                return Response(content=pcached, media_type="image/jpeg",
                                headers={"Cache-Control": "max-age=3600"})
            from app.services.bin_paths import get_ffmpeg_bin
            r = subprocess.run(
                [get_ffmpeg_bin(), "-y", "-i", str(poster), "-vf", f"scale={width}:-2",
                 "-frames:v", "1", "-q:v", "4", "-f", "mjpeg", "pipe:1"],
                capture_output=True, timeout=30,
            )
            if r.returncode == 0 and r.stdout:
                _cache_put(pkey, r.stdout)
                return Response(content=r.stdout, media_type="image/jpeg",
                                headers={"Cache-Control": "max-age=3600"})
        except Exception:
            pass   # fall through to the frame grab

    # Cache lookup — keyed by path + mtime so a re-render invalidates the entry.
    try:
        mtime = Path(output_file).stat().st_mtime
    except OSError:
        raise HTTPException(status_code=404, detail="Output file no longer exists on disk")

    key = _cache_key(output_file, mtime)
    cached = _cache_get(key)
    if cached:
        return Response(
            content=cached,
            media_type="image/jpeg",
            headers={"Cache-Control": "max-age=3600"},
        )

    # Probe duration to compute a meaningful offset (10 % into the clip).
    duration: float | None = probe_video_metadata(output_file).get("duration")
    if duration and duration > 0:
        offset_sec = max(0.5, duration * 0.1)
    else:
        offset_sec = 0.5

    jpeg_bytes = extract_thumbnail_frame(output_file, offset_sec=offset_sec, width=width)
    if not jpeg_bytes:
        raise HTTPException(status_code=503, detail="Thumbnail extraction failed")

    _cache_put(key, jpeg_bytes)

    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"},
    )
