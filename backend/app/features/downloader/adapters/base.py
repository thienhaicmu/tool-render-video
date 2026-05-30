"""Abstract base class for platform download adapters."""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class DownloadAdapter(ABC):
    """Platform-specific download adapter.

    Each adapter wraps yt-dlp (or a native SDK) for one platform family.
    Contract:
      - download() returns a dict on success
      - download() raises RuntimeError on failure (never returns None)
      - supports() is fast and stateless (URL pattern match only)
    """

    @abstractmethod
    def supports(self, url: str) -> bool:
        """Return True if this adapter can handle the given URL."""
        ...

    @abstractmethod
    def download(
        self,
        url: str,
        output_dir: Path,
        *,
        quality: str = "best",
        cancel_event: Optional[threading.Event] = None,
        context: str = "download",
    ) -> dict:
        """Download video from the platform URL to output_dir.

        Returns dict with keys:
            filepath  str  — absolute path to downloaded file
            title     str  — video title
            duration  int  — duration in seconds
            platform  str  — platform name ("youtube", "tiktok", ...)
            url       str  — original URL

        Raises:
            RuntimeError: download failed
        """
        ...

    @property
    def platform_name(self) -> str:
        return self.__class__.__name__.replace("Adapter", "").lower()
