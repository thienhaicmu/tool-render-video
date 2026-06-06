"""TikTok download adapter — uses yt-dlp via generic fallback."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from .base import DownloadAdapter

_TIKTOK_DOMAINS = ("tiktok.com", "www.tiktok.com", "vm.tiktok.com", "vt.tiktok.com")


class TikTokAdapter(DownloadAdapter):
    @property
    def platform_name(self) -> str:
        return "tiktok"

    def supports(self, url: str) -> bool:
        lower = url.lower()
        return any(d in lower for d in _TIKTOK_DOMAINS)

    def download(
        self,
        url: str,
        output_dir: Path,
        *,
        quality: str = "best",
        cancel_event: Optional[threading.Event] = None,
        context: str = "download",
    ) -> dict:
        from app.features.download.engine.downloader import download_youtube
        result = download_youtube(url, output_dir, context=context, cancel_event=cancel_event)
        return {**result, "platform": "tiktok", "url": url}
