"""YouTube download adapter — wraps services/downloader.py (yt-dlp)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from .base import DownloadAdapter

_YOUTUBE_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
)


class YouTubeAdapter(DownloadAdapter):
    """yt-dlp based YouTube adapter."""

    @property
    def platform_name(self) -> str:
        return "youtube"

    def supports(self, url: str) -> bool:
        lower = url.lower()
        return any(d in lower for d in _YOUTUBE_DOMAINS)

    def download(
        self,
        url: str,
        output_dir: Path,
        *,
        quality: str = "best",
        cancel_event: Optional[threading.Event] = None,
        context: str = "download",
    ) -> dict:
        from app.services.downloader import download_youtube
        result = download_youtube(url, output_dir, context=context, cancel_event=cancel_event)
        return {**result, "platform": "youtube", "url": url}
