"""Downloader feature router — /api/downloader/* endpoints.

Migrated from routes/platform_downloader.py.
Handles: start download, batch download, job status, cancel, WebSocket progress.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.db.download_repo import (
    create_download_job,
    delete_download_job,
    get_download_job,
    list_download_jobs,
    update_download_job,
)
from app.services.platform_downloader import download_video, get_video_info
from app.services.platform_downloader.platform_detect import detect_platform, is_allowed_url

logger = logging.getLogger("app.downloader")

router = APIRouter(prefix="/api/downloader", tags=["downloader"])

_EXECUTOR = ThreadPoolExecutor(max_workers=3, thread_name_prefix="platform-dl")


# ── Security helpers ──────────────────────────────────────────────────────────

def _validate_download_url(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL format")
    host = (parsed.hostname or "").lower()
    try:
        ipaddress.ip_address(host)
        raise HTTPException(status_code=400, detail="Direct IP addresses are not permitted")
    except ValueError:
        pass
    if not is_allowed_url(url):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Domain '{host}' is not supported. "
                "Supported: YouTube, TikTok, Instagram, Facebook, X, Bilibili, Reddit, Vimeo, Dailymotion."
            ),
        )
    return url


def _validate_output_dir(raw: str) -> Path:
    raw = str(raw or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="output_dir is required")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot create output folder: {exc}") from exc
    return p


def _friendly_error(exc: Exception) -> str:
    text = str(exc or "").lower()
    if "unsupported" in text or "invalid url" in text:
        return "Unsupported link"
    if "private" in text or "unavailable" in text or "not available" in text:
        return "Private or unavailable video"
    if "login" in text or "sign in" in text or "cookies" in text:
        return "Login required — video is age-restricted or private"
    if "copyright" in text or "blocked" in text:
        return "Video is not available in your region"
    if "network" in text or "connection" in text or "timeout" in text:
        return "Network error — check your connection and try again"
    if "no video formats" in text or "format" in text:
        return "No downloadable format found for this video"
    return "Download failed — please try again"


# ── Schemas ───────────────────────────────────────────────────────────────────

class DownloadStartRequest(BaseModel):
    url: str
    output_dir: str
    quality: str = "best"   # best | 1080p | 720p | 480p


class BatchDownloadStartRequest(BaseModel):
    urls: list[str]
    output_dir: str
    quality: str = "best"


# ── Background worker ─────────────────────────────────────────────────────────

def _run_download(job_id: str, url: str, output_dir: Path) -> None:
    try:
        update_download_job(job_id, status="downloading", progress=1)

        def _on_progress(pct: int, speed: str, eta: str):
            update_download_job(job_id, progress=pct, speed_str=speed, eta_str=eta)

        result = download_video(job_id, url, output_dir, on_progress=_on_progress)

        update_download_job(
            job_id,
            status="done",
            progress=100,
            speed_str="",
            eta_str="",
            title=result["title"],
            output_path=result["output_path"],
            filename=result["filename"],
            height=result["height"],
            fps=result["fps"],
            duration=result["duration"],
            filesize=result["filesize"],
        )
        logger.info("download.done job_id=%s file=%s", job_id, result["filename"])
    except Exception as exc:
        msg = _friendly_error(exc)
        update_download_job(job_id, status="failed", error_msg=msg, progress=0)
        logger.error(
            "download.failed  job_id=%s  url=%s  friendly=%r  raw=%s",
            job_id, url, msg, exc,
            exc_info=True,
        )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/info")
def get_info(url: str):
    """Preview video metadata before downloading (no download)."""
    url = _validate_download_url(url)
    return get_video_info(url)


@router.post("/start")
def start_download(req: DownloadStartRequest):
    url = _validate_download_url(req.url)
    output_dir = _validate_output_dir(req.output_dir)
    job_id = str(uuid.uuid4())
    platform = detect_platform(url)
    create_download_job(job_id, url, platform, str(output_dir))
    _EXECUTOR.submit(_run_download, job_id, url, output_dir)
    return {"job_id": job_id, "platform": platform}


@router.post("/batch")
def start_batch(req: BatchDownloadStartRequest):
    urls = list({u.strip() for u in req.urls if u.strip()})
    if not urls:
        raise HTTPException(status_code=400, detail="No valid URLs provided")
    output_dir = _validate_output_dir(req.output_dir)
    job_ids = []
    for url in urls:
        try:
            url = _validate_download_url(url)
        except HTTPException:
            continue
        job_id = str(uuid.uuid4())
        platform = detect_platform(url)
        create_download_job(job_id, url, platform, str(output_dir))
        _EXECUTOR.submit(_run_download, job_id, url, output_dir)
        job_ids.append({"job_id": job_id, "url": url, "platform": platform})
    return {"jobs": job_ids}


@router.get("/jobs")
def list_jobs(limit: int = 100):
    return list_download_jobs(limit=min(limit, 200))


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = get_download_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return job


@router.delete("/jobs/{job_id}")
def cancel_job(job_id: str):
    job = get_download_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    if job.get("status") in ("queued", "downloading"):
        update_download_job(job_id, status="failed", error_msg="Cancelled by user")
    delete_download_job(job_id)
    return {"ok": True}


@router.websocket("/jobs/{job_id}/ws")
async def job_progress_ws(websocket: WebSocket, job_id: str):
    await websocket.accept()
    try:
        while True:
            job = get_download_job(job_id)
            if not job:
                await websocket.send_json({"error": "not_found"})
                break
            await websocket.send_json(job)
            if job.get("status") in ("done", "failed"):
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("downloader ws closed: %s", exc)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
