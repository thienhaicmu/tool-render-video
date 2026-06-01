"""
routes/download.py — Download API endpoints v2.

POST /api/v2/download         — download video từ URL → trả về local_path
GET  /api/v2/download/health  — probe URL không download, kiểm tra availability
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from v2.core.config import TEMP_DIR
from v2.core.exceptions import DownloadFailedError, InvalidUrlError
from v2.domain.download.downloader import HealthResult, check_url_health, download_video
from v2.domain.download.models import DownloadRequest, DownloadResult

router = APIRouter(prefix="/api/v2/download", tags=["download-v2"])
logger = logging.getLogger("v2.api.download")


class DownloadResponse(BaseModel):
    ok:           bool
    local_path:   str
    title:        str
    duration_sec: float
    file_size:    int


class HealthRequest(BaseModel):
    url: str


class HealthResponse(BaseModel):
    ok:          bool
    source:      str
    title:       str        = ""
    best_height: int        = 0
    best_fps:    int        = 0
    error:       str        = ""


@router.post("", response_model=DownloadResponse)
def post_download(body: DownloadRequest) -> DownloadResponse:
    """Download video từ URL về local. Trả về local_path để dùng cho render."""
    try:
        result: DownloadResult = download_video(body)
    except InvalidUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except DownloadFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("download_unexpected_error url=%s", body.url)
        raise HTTPException(status_code=500, detail=str(exc))

    return DownloadResponse(
        ok=True,
        local_path=str(result.local_path),
        title=result.title,
        duration_sec=result.duration_sec,
        file_size=result.file_size,
    )


@router.post("/health", response_model=HealthResponse)
def post_download_health(body: HealthRequest) -> HealthResponse:
    """Probe URL mà không download — kiểm tra khả dụng và max resolution."""
    result: HealthResult = check_url_health(body.url)
    return HealthResponse(
        ok=result.ok,
        source=result.source,
        title=result.title,
        best_height=result.best_height,
        best_fps=result.best_fps,
        error=result.error,
    )
