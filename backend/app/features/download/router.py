"""Downloader feature router — /api/downloader/* endpoints.

Migrated from routes/platform_downloader.py.
All download execution is delegated to DownloadService (_service).
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.db.download_repo import (
    create_download_job,
    delete_download_job,
    find_active_job_for_url,
    get_download_job,
    list_download_jobs,
    update_download_job,
)
from app.features.download.engine import get_video_info
from app.features.download.engine.platform_detect import detect_platform, is_allowed_url
from app.features.download.service import _service

logger = logging.getLogger("app.downloader")

router = APIRouter(prefix="/api/downloader", tags=["downloader"])


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
    else:
        p = p.resolve()
    try:
        from app.core.config import APP_DATA_DIR
        p.relative_to(Path(APP_DATA_DIR).resolve())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="output_dir must be inside the application data directory",
        )
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot create output folder: {exc}") from exc
    return p


# ── Schemas ───────────────────────────────────────────────────────────────────

class DownloadStartRequest(BaseModel):
    url: str
    output_dir: str
    quality: str = "best"   # best | 1080p | 720p | 480p


class BatchDownloadStartRequest(BaseModel):
    urls: list[str]
    output_dir: str
    quality: str = "best"


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
    existing = find_active_job_for_url(url)
    if existing:
        return {"job_id": existing["id"], "platform": existing.get("platform", ""), "duplicate": True}
    job_id = str(uuid.uuid4())
    platform = detect_platform(url)
    create_download_job(job_id, url, platform, str(output_dir))
    _service.submit(job_id, url, output_dir, quality=req.quality, platform=platform)
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
        existing = find_active_job_for_url(url)
        if existing:
            job_ids.append({"job_id": existing["id"], "url": url, "platform": existing.get("platform", ""), "duplicate": True})
            continue
        job_id = str(uuid.uuid4())
        platform = detect_platform(url)
        create_download_job(job_id, url, platform, str(output_dir))
        _service.submit(job_id, url, output_dir, quality=req.quality, platform=platform)
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
        _service.cancel(job_id)
        update_download_job(job_id, status="cancelled", error_msg="Cancelled by user")
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
            if job.get("status") in ("done", "failed", "cancelled"):
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


@router.post("/refresh-cookies")
def refresh_cookies():
    """Re-extract YouTube cookies from Chrome (auto, read-only SQLite URI).
    Works for Chrome ≤126 (v10/v11 AES-GCM). Returns ok=True if any cookies written.
    Chrome 127+ (v20 App-Bound Encryption) requires manual export via browser extension.
    """
    try:
        from app.core.config import COOKIES_DIR
        from app.features.download.engine.cookie_extractor import extract_youtube_cookies
        output_path = COOKIES_DIR / "youtube_cookies.txt"
        ok = extract_youtube_cookies(output_path)
        if ok:
            logger.info("refresh_cookies: cookies written to %s", output_path)
            return _cookie_status_response()
        else:
            logger.warning("refresh_cookies: no Chrome cookies found")
            return {"ok": False, "present": False,
                    "detail": "No Chrome profile with YouTube cookies found. "
                              "Chrome 127+ uses App-Bound Encryption (v20) — "
                              "use Import File instead."}
    except Exception as exc:
        logger.error("refresh_cookies: failed — %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Cookie extraction failed: {exc}") from exc


class ImportCookiesRequest(BaseModel):
    path: str


@router.post("/import-cookies")
def import_cookies(req: ImportCookiesRequest):
    """Import a manually-exported cookies.txt file (Netscape format).

    Use this for Chrome 127+ where auto-extraction fails due to v20 App-Bound Encryption.
    Steps:
      1. Install 'Get cookies.txt LOCALLY' extension in Chrome
      2. Open youtube.com while logged in
      3. Click the extension → Export cookies for this tab
      4. Browse to the saved file and import here

    The file is copied to data/cookies/youtube_cookies.txt and used for all downloads.
    """
    import shutil as _shutil
    src = Path(req.path).expanduser()
    if not src.is_file():
        raise HTTPException(status_code=400, detail=f"File not found: {req.path}")
    if src.stat().st_size == 0:
        raise HTTPException(status_code=400, detail="File is empty")

    try:
        first_line = src.read_text(encoding="utf-8", errors="ignore").splitlines()[0]
        if "Netscape" not in first_line and "HTTP Cookie" not in first_line:
            raise HTTPException(
                status_code=400,
                detail="File does not appear to be a Netscape cookies.txt. "
                       "Export using 'Get cookies.txt LOCALLY' Chrome extension.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Cannot read file: {exc}") from exc

    try:
        from app.core.config import COOKIES_DIR
        output_path = COOKIES_DIR / "youtube_cookies.txt"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(str(src), str(output_path))
        logger.info("import_cookies: copied %s → %s (%d bytes)", src.name, output_path, src.stat().st_size)
        return _cookie_status_response()
    except Exception as exc:
        logger.error("import_cookies: failed — %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to import: {exc}") from exc


def _cookie_status_response() -> dict:
    """Build the cookie-status response dict from the current cookies file."""
    import time as _time
    try:
        from app.core.config import COOKIES_DIR
        path = COOKIES_DIR / "youtube_cookies.txt"
        if not path.is_file():
            return {"ok": False, "present": False}

        age_seconds = int(_time.time() - path.stat().st_mtime)
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = [l for l in text.splitlines() if l and not l.startswith("#")]
        cookie_count = len(lines)
        has_v20_warning = "v20(no-decrypt)" in text and "v10/v11=0" in text

        return {
            "ok": True,
            "present": True,
            "path": str(path),
            "age_seconds": age_seconds,
            "cookie_count": cookie_count,
            "has_v20_warning": has_v20_warning,
        }
    except Exception:
        return {"ok": False, "present": False}


@router.get("/cookie-status")
def cookie_status():
    """Return current cookie file status: present, age, count, v20 warning."""
    return _cookie_status_response()
