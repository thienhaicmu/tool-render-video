"""Instagram download adapter — uses yt-dlp."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from .base import DownloadAdapter

_INSTAGRAM_DOMAINS = ("instagram.com", "www.instagram.com", "instagr.am")


class InstagramAdapter(DownloadAdapter):
    @property
    def platform_name(self) -> str:
        return "instagram"

    def supports(self, url: str) -> bool:
        lower = url.lower()
        return any(d in lower for d in _INSTAGRAM_DOMAINS)

    def download(
        self,
        url: str,
        output_dir: Path,
        *,
        quality: str = "best",
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, str, str], None]] = None,
        context: str = "download",
    ) -> dict:
        from app.features.download.engine.downloader import download_youtube
        result = download_youtube(
            url, output_dir,
            context=context,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )
        return {**result, "platform": "instagram", "url": url}
