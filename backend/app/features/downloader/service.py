"""Downloader service — selects the right adapter and orchestrates the download."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from .adapters.youtube import YouTubeAdapter
from .adapters.tiktok import TikTokAdapter
from .adapters.instagram import InstagramAdapter
from .adapters.facebook import FacebookAdapter
from .adapters.douyin import DouyinAdapter
from .adapters.generic import GenericAdapter
from .adapters.base import DownloadAdapter

logger = logging.getLogger("app.downloader")

# Adapter chain — order matters, GenericAdapter must be last (supports any URL).
_ADAPTER_CHAIN: list[DownloadAdapter] = [
    YouTubeAdapter(),
    TikTokAdapter(),
    InstagramAdapter(),
    FacebookAdapter(),
    DouyinAdapter(),
    GenericAdapter(),
]


def get_adapter(url: str) -> DownloadAdapter:
    """Return the first adapter that supports the given URL."""
    for adapter in _ADAPTER_CHAIN:
        if adapter.supports(url):
            logger.debug("download_adapter_selected platform=%s url=%s", adapter.platform_name, url[:80])
            return adapter
    return _ADAPTER_CHAIN[-1]  # GenericAdapter always matches


def download_video(
    url: str,
    output_dir: Path,
    *,
    quality: str = "best",
    cancel_event: Optional[threading.Event] = None,
    context: str = "download",
) -> dict:
    """Download a video from any supported platform URL.

    Automatically selects the correct adapter based on the URL domain.

    Returns:
        dict with keys: filepath, title, duration, platform, url

    Raises:
        RuntimeError: download failed (propagated from adapter)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = get_adapter(url)
    logger.info(
        "download_start platform=%s url=%s context=%s",
        adapter.platform_name, url[:80], context,
    )
    result = adapter.download(
        url, output_dir,
        quality=quality,
        cancel_event=cancel_event,
        context=context,
    )
    logger.info(
        "download_done platform=%s title=%s duration=%ss filepath=%s",
        result.get("platform", "?"),
        result.get("title", "")[:60],
        result.get("duration", "?"),
        result.get("filepath", ""),
    )
    return result


def detect_platform(url: str) -> str:
    """Return the platform name for a URL without downloading."""
    return get_adapter(url).platform_name
