"""service.py — DownloadService: executor, cancel registry, job lifecycle.

Routes from router.py call _service.submit() / _service.cancel().
Heavy lifting (adapter dispatch, normalisation) lives in engine/acquire.py.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger("app.downloader")


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
    if "timed out" in text or "timeout" in text or "network" in text or "connection" in text:
        return "Network error — check your connection and try again"
    if "no video formats" in text or "format" in text:
        return "No downloadable format found for this video"
    if "cancelled" in text or "cancel" in text:
        return "Cancelled by user"
    return "Download failed — please try again"


class _ThrottledWriter:
    """Rate-limits progress DB writes to at most 1 per min_interval seconds."""

    def __init__(self, job_id: str, min_interval: float = 1.0):
        self._job_id = job_id
        self._min_interval = min_interval
        self._last_write = 0.0
        self._lock = threading.Lock()

    def update(self, pct: int, speed: str, eta: str) -> None:
        from app.db.download_repo import update_download_job
        now = time.monotonic()
        with self._lock:
            if now - self._last_write < self._min_interval:
                return
            self._last_write = now
        update_download_job(self._job_id, progress=pct, speed_str=speed, eta_str=eta)


class DownloadService:
    """Manages the download executor, cancel registry, and job lifecycle."""

    def __init__(self, max_workers: int = 3):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="platform-dl"
        )
        self._cancel_events: dict[str, threading.Event] = {}
        self._cancel_lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def submit(
        self,
        job_id: str,
        url: str,
        output_dir: Path,
        quality: str = "best",
        platform: str = "",
    ) -> threading.Event:
        """Enqueue a download job. Returns the cancel event for this job."""
        cancel_event = self._register(job_id)
        self._executor.submit(
            self._run_job, job_id, url, output_dir, quality, platform, cancel_event
        )
        return cancel_event

    def cancel(self, job_id: str) -> bool:
        """Signal the cancel event for job_id. Returns True if event was found."""
        with self._cancel_lock:
            ev = self._cancel_events.get(job_id)
        if ev:
            ev.set()
            return True
        return False

    # ── Internal ──────────────────────────────────────────────────────────────

    def _register(self, job_id: str) -> threading.Event:
        ev = threading.Event()
        with self._cancel_lock:
            self._cancel_events[job_id] = ev
        return ev

    def _unregister(self, job_id: str) -> None:
        with self._cancel_lock:
            self._cancel_events.pop(job_id, None)

    def _run_job(
        self,
        job_id: str,
        url: str,
        output_dir: Path,
        quality: str,
        platform: str,
        cancel_event: threading.Event,
    ) -> None:
        from app.core.tracing import dl_job_start, dl_job_done, dl_job_fail
        from app.db.download_repo import update_download_job, complete_download_job
        from app.features.download.engine.acquire import acquire
        import os as _os

        _t_start = time.monotonic()
        _platform = platform or "unknown"

        # Detect cookie source for tracing
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

        _cs = None          # CatalogService handle — set only if registration succeeds
        _asset_id: str | None = None

        try:
            update_download_job(job_id, status="downloading", progress=1)

            # Non-fatal catalog registration
            try:
                from app.features.download.catalog.service import _catalog_service
                _cs = _catalog_service
                _ast = _cs.register_or_get(url, platform=_platform, quality=quality)
                _asset_id = _ast["asset_id"]
                _cs.link_download_job(_asset_id, job_id)
                _cs.transition(_asset_id, "downloading")
            except Exception as _cat_exc:
                logger.debug("catalog.register skipped job=%s: %s", job_id, _cat_exc)

            _writer = _ThrottledWriter(job_id)

            def _on_progress(pct: int, speed: str, eta: str) -> None:
                _writer.update(pct, speed, eta)

            result = acquire(
                job_id, url, output_dir,
                quality=quality,
                platform=_platform,
                cancel_event=cancel_event,
                progress_callback=_on_progress,
            )

            _elapsed_ms = int((time.monotonic() - _t_start) * 1000)
            complete_download_job(
                job_id,
                title=result["title"],
                output_path=result["output_path"],
                filename=result["filename"],
                height=result["height"],
                fps=result["fps"],
                duration=result["duration"],
                filesize=result["filesize"],
            )
            update_download_job(job_id, progress=100, speed_str="", eta_str="")

            # Non-fatal catalog mark_ready
            try:
                if _cs and _asset_id:
                    from app.db.catalog_repo import update_asset as _upd
                    _cs.transition(_asset_id, "ready")
                    _upd(
                        _asset_id,
                        storage_path=result["output_path"],
                        filename=result["filename"],
                        filesize=result["filesize"],
                        storage_tier="raw",
                        title=result["title"],
                        duration=result["duration"],
                        height=result["height"],
                        fps=result["fps"],
                    )
            except Exception:
                pass

            logger.info(
                "download.done  job_id=%s  platform=%s  file=%s  size_bytes=%s  elapsed_ms=%d",
                job_id, _platform, result["filename"], result["filesize"], _elapsed_ms,
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

            # Non-fatal catalog failure transition
            try:
                if _cs and _asset_id:
                    _cs.transition(_asset_id, "failed")
            except Exception:
                pass

        finally:
            self._unregister(job_id)


# Module-level singleton — router.py imports this
_service = DownloadService()


# ── Backward-compat helpers (used by router.py /info endpoint) ────────────────

def detect_platform(url: str) -> str:
    """Return the platform name for a URL without downloading."""
    from app.features.download.engine.acquire import get_adapter
    return get_adapter(url).platform_name


# Backward-compat re-export — tests and older callers may import get_adapter from service
from app.features.download.engine.acquire import get_adapter  # noqa: E402, F401
