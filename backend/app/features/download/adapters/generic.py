"""Generic yt-dlp adapter — fallback for any platform not matched by a specific adapter."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from .base import DownloadAdapter


class GenericAdapter(DownloadAdapter):
    """yt-dlp fallback: handles any URL yt-dlp supports (Twitter/X, Vimeo, Twitch, etc.)."""

    @property
    def platform_name(self) -> str:
        return "generic"

    def supports(self, url: str) -> bool:
        return True  # always matches — must be last in the adapter chain

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
        return {**result, "platform": "generic", "url": url}
