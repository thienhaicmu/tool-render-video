"""
downloader.py — Download video về local file.

Chiến lược: wrap app.services.downloader (v1) — không copy logic.
v1 có proxy handling, multi-client retry, wall-clock timeout đã ổn định.
v2 chỉ thêm typed interface và exception mapping.

Public API:
    download_video(request)      -> DownloadResult
    check_url_health(url)        -> HealthResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from v2.core.exceptions import DownloadFailedError, InvalidUrlError
from v2.domain.download.models import DownloadRequest, DownloadResult
from v2.domain.download.validator import detect_source, validate_supported_url

logger = logging.getLogger("v2.download.downloader")


@dataclass
class HealthResult:
    ok:           bool
    source:       str
    title:        str        = ""
    best_height:  int        = 0
    best_fps:     int        = 0
    error:        str        = ""


def download_video(
    request: DownloadRequest,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_event=None,
) -> DownloadResult:
    """
    Download video từ URL về local.

    Raise:
        InvalidUrlError      — URL không hợp lệ hoặc nguồn không hỗ trợ
        DownloadFailedError  — yt-dlp thất bại sau tất cả retry

    progress_callback(pct: int, label: str) — optional, gọi trong quá trình download.
    """
    url = validate_supported_url(request.url)
    source = detect_source(url)

    request.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("download_video source=%s url=%s output_dir=%s", source, url, request.output_dir)

    try:
        raw = _download_by_source(
            source=source,
            url=url,
            output_dir=request.output_dir,
            quality=request.quality,
            cookies_from_browser=request.cookies_from_browser,
            progress_callback=progress_callback,
            cancel_event=cancel_event,
        )
    except RuntimeError as exc:
        raise DownloadFailedError(str(exc)) from exc

    local_path = Path(raw["filepath"])
    if not local_path.exists() or local_path.stat().st_size == 0:
        raise DownloadFailedError(f"File download rỗng hoặc không tồn tại: {local_path}")

    return DownloadResult(
        local_path=local_path,
        title=str(raw.get("title") or local_path.stem),
        duration_sec=float(raw.get("duration") or 0.0),
        file_size=local_path.stat().st_size,
        url=url,
    )


def check_url_health(url: str) -> HealthResult:
    """
    Probe URL mà không download — kiểm tra availability và resolution.
    Không raise — trả về HealthResult với ok=False nếu thất bại.
    """
    try:
        url = validate_supported_url(url)
        source = detect_source(url)
    except InvalidUrlError as exc:
        return HealthResult(ok=False, source="unknown", error=str(exc))

    try:
        from app.services.downloader import check_youtube_download_health
        raw = check_youtube_download_health(url)
        return HealthResult(
            ok=bool(raw.get("ok")),
            source=source,
            title=str(raw.get("title") or ""),
            best_height=int(raw.get("best_height") or 0),
            best_fps=int(raw.get("best_fps") or 0),
            error=str(raw.get("message") or "") if not raw.get("ok") else "",
        )
    except Exception as exc:
        return HealthResult(ok=False, source=source, error=str(exc))


# ── Internal ──────────────────────────────────────────────────────────────────

def _download_by_source(
    source: str,
    url: str,
    output_dir: Path,
    quality: str,
    cookies_from_browser: Optional[str],
    progress_callback: Optional[Callable],
    cancel_event,
) -> dict:
    """Delegate đến v1 downloader theo source. Raise RuntimeError nếu thất bại."""
    if source == "youtube":
        from app.services.downloader import download_youtube
        quality_mode = _map_quality(quality)
        return download_youtube(
            url=url,
            temp_dir=output_dir,
            context="download_v2",
            progress_callback=progress_callback,
            quality_mode=quality_mode,
            cancel_event=cancel_event,
        )

    # facebook, instagram — dùng generic downloader
    from app.services.downloader import download_public_video
    return download_public_video(
        url=url,
        temp_dir=output_dir,
        progress_callback=progress_callback,
    )


def _map_quality(quality: str) -> str:
    """Map quality string từ DownloadRequest sang quality_mode của v1 downloader."""
    mapping = {
        "best":   "best_available",
        "1080p":  "standard_1080",
        "1440p":  "high_1440",
        "720p":   "standard_1080",   # v1 không có 720 riêng, dùng 1080 rồi ffmpeg scale
    }
    return mapping.get(quality.lower(), "standard_1080")
