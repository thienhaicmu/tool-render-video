"""Downloader feature router — /api/downloader/* endpoints.

Migrated from routes/platform_downloader.py.
Handles: start download, batch download, job status, cancel, WebSocket progress.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import threading
import time
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
from app.features.download.engine import download_video, get_video_info
from app.features.download.engine.platform_detect import detect_platform, is_allowed_url

logger = logging.getLogger("app.downloader")

router = APIRouter(prefix="/api/downloader", tags=["downloader"])

# Perf-opt Phase 10 (D6) — expose executor sizing via env vars so users
# on bigger machines can raise the ceiling without a code edit.
# Defaults match the historical hardcoded values (3 + 2).
def _exec_size(env_name: str, default: int, min_: int = 1, max_: int = 16) -> int:
    try:
        raw = (os.getenv(env_name) or "").strip()
        if not raw:
            return default
        return max(min_, min(max_, int(raw)))
    except Exception:
        return default

_DOWNLOAD_EXECUTOR = ThreadPoolExecutor(
    max_workers=_exec_size("DOWNLOAD_MAX_WORKERS", 3),
    thread_name_prefix="dl-main",
)
_ENRICH_EXECUTOR = ThreadPoolExecutor(
    max_workers=_exec_size("DOWNLOAD_ENRICH_WORKERS", 2),
    thread_name_prefix="dl-enrich",
)

# In-flight dedup: prevents duplicate downloads when the same URL is submitted
# twice before the first job finishes. url → job_id, cleared in _run_download finally.
_INFLIGHT_URLS: dict[str, str] = {}
_INFLIGHT_LOCK = threading.Lock()

# Per-job cancellation: job_id → Event. Set by cancel_job so the worker's
# yt-dlp progress hook aborts the in-flight download. Created in _run_download,
# cleared in its finally. Guarded by _INFLIGHT_LOCK.
_CANCEL_EVENTS: dict[str, threading.Event] = {}


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

def _run_download(job_id: str, url: str, output_dir: Path, platform: str = "", quality: str = "best") -> None:
    from app.core.tracing import dl_job_start, dl_job_done, dl_job_fail

    _t_start = time.monotonic()
    _platform = platform or "unknown"

    # Register a cancel event so DELETE /jobs/{id} can abort this download.
    _cancel = threading.Event()
    with _INFLIGHT_LOCK:
        _CANCEL_EVENTS[job_id] = _cancel

    # Detect cookie source for trace
    import os as _os
    from pathlib import Path as _Path
    _cookie_src = "none"
    if (_os.getenv("YTDLP_COOKIEFILE") or "").strip():
        _cookie_src = "file"
    else:
        try:
            from app.core.config import COOKIES_DIR as _CD
            if (_CD / "youtube_cookies.txt").is_file():
                _cookie_src = "auto"
        except Exception:
            pass
        if _cookie_src == "none" and (_os.getenv("YTDLP_COOKIES_FROM_BROWSER") or "").strip():
            _cookie_src = "browser"

    dl_job_start(job_id, url=url, platform=_platform, quality=quality, cookies=_cookie_src)

    try:
        update_download_job(job_id, status="downloading", progress=1)

        def _on_progress(pct: int, speed: str, eta: str):
            update_download_job(job_id, progress=pct, speed_str=speed, eta_str=eta)

        result = download_video(
            job_id, url, output_dir,
            on_progress=_on_progress,
            quality=quality,
            cancel_event=_cancel,
        )

        _elapsed_ms = int((time.monotonic() - _t_start) * 1000)
        # Phase C — register file in asset library (never blocks, never raises).
        _asset_id: str | None = None
        try:
            from app.db.assets_repo import upsert_asset, update_asset_status
            from app.features.download.engine.enrichment import enrich_asset
            _output_path = result.get("output_path") or ""
            if _output_path:
                _asset_id = upsert_asset(
                    asset_id=str(uuid.uuid4()),
                    file_path=_output_path,
                    original_url=url,
                    title=result.get("title") or "",
                )
                update_asset_status(_asset_id, "enriching")
                _ENRICH_EXECUTOR.submit(enrich_asset, _asset_id, _output_path)
        except Exception:
            logger.warning("download: asset registration failed job_id=%s", job_id, exc_info=True)

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
            asset_id=_asset_id,
        )
        logger.info(
            "download.done  job_id=%s  platform=%s  file=%s  size_bytes=%s  elapsed_ms=%d  asset_id=%s",
            job_id, _platform, result["filename"], result["filesize"], _elapsed_ms, _asset_id,
        )
        dl_job_done(job_id, filename=result["filename"], filesize=result["filesize"], platform=_platform)
    except Exception as exc:
        _elapsed_ms = int((time.monotonic() - _t_start) * 1000)
        msg = _friendly_error(exc)
        update_download_job(job_id, status="failed", error_msg=msg, progress=0)
        logger.error(
            "download.failed  job_id=%s  platform=%s  url=%s  elapsed_ms=%d  friendly=%r  raw=%s",
            job_id, _platform, url, _elapsed_ms, msg, exc,
            exc_info=True,
        )
        dl_job_fail(job_id, error=msg, platform=_platform)
    finally:
        with _INFLIGHT_LOCK:
            # Only clear the dedup marker if it still points at THIS job — a
            # later job for the same URL may have reserved it.
            if _INFLIGHT_URLS.get(url) == job_id:
                _INFLIGHT_URLS.pop(url, None)
            _CANCEL_EVENTS.pop(job_id, None)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/info")
def get_info(url: str):
    """Preview video metadata before downloading (no download)."""
    url = _validate_download_url(url)
    return get_video_info(url)


def _reserve_inflight(url: str) -> tuple[str, bool]:
    """Atomically reserve the in-flight slot for ``url``.

    Returns (job_id, is_new). When the URL is already in flight, returns the
    existing job_id with is_new=False so the caller can dedup.
    """
    with _INFLIGHT_LOCK:
        existing = _INFLIGHT_URLS.get(url)
        if existing:
            return existing, False
        job_id = str(uuid.uuid4())
        _INFLIGHT_URLS[url] = job_id
        return job_id, True


def _release_inflight(url: str, job_id: str) -> None:
    with _INFLIGHT_LOCK:
        if _INFLIGHT_URLS.get(url) == job_id:
            _INFLIGHT_URLS.pop(url, None)


@router.post("/start")
def start_download(req: DownloadStartRequest):
    url = _validate_download_url(req.url)
    # Filesystem + platform work is done OUTSIDE the dedup lock so concurrent
    # /start calls don't serialise behind mkdir / DB I/O.
    output_dir = _validate_output_dir(req.output_dir)
    platform = detect_platform(url)

    job_id, is_new = _reserve_inflight(url)
    if not is_new:
        logger.info("download: dedup hit url=%s existing_job=%s", url, job_id)
        return {"job_id": job_id, "platform": platform, "dedup": True}

    try:
        create_download_job(job_id, url, platform, str(output_dir))
        _DOWNLOAD_EXECUTOR.submit(_run_download, job_id, url, output_dir, platform, req.quality)
    except Exception:
        _release_inflight(url, job_id)
        raise
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
        platform = detect_platform(url)
        # Same in-flight dedup as /start so the same URL across batch+single (or
        # two batch calls) never spawns duplicate downloads.
        job_id, is_new = _reserve_inflight(url)
        if not is_new:
            logger.info("download: batch dedup hit url=%s existing_job=%s", url, job_id)
            job_ids.append({"job_id": job_id, "url": url, "platform": platform, "dedup": True})
            continue
        try:
            create_download_job(job_id, url, platform, str(output_dir))
            _DOWNLOAD_EXECUTOR.submit(_run_download, job_id, url, output_dir, platform, req.quality)
        except Exception:
            _release_inflight(url, job_id)
            continue
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
        # Signal the worker to abort the in-flight yt-dlp download (the progress
        # hook raises on the next callback), then mark + remove the job.
        with _INFLIGHT_LOCK:
            _ev = _CANCEL_EVENTS.get(job_id)
        if _ev is not None:
            _ev.set()
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
            # Perf-opt Phase 10 (D7) — 2 s poll interval (was 1 s). Halves
            # DB queries against `download_jobs` without a perceptible
            # progress-bar lag (download progress is dominated by network
            # latency, not the poll cadence).
            await asyncio.sleep(2.0)
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

    # Validate Netscape format
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
