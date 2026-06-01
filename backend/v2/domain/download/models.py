"""
models.py — DownloadRequest và DownloadResult.

Download và Render là 2 domain tách biệt.
Kết quả download (local_path) được truyền vào RenderRequest.source_path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class DownloadRequest(BaseModel):
    url:        str
    output_dir: Path
    filename:   Optional[str]     = None
    quality:    Literal["best", "1080p", "1440p", "720p"] = "1080p"
    cookies_from_browser: Optional[Literal["chrome", "firefox", "edge"]] = None

    @model_validator(mode="after")
    def validate_fields(self) -> "DownloadRequest":
        if not self.url.strip():
            raise ValueError("url không được để trống")
        return self


class DownloadResult(BaseModel):
    """Kết quả download. local_path là input cho RenderRequest.source_path."""
    local_path:   Path
    title:        str
    duration_sec: float
    file_size:    int       # bytes
    url:          str
