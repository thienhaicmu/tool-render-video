"""
s01_validate.py — Validate local source file.

Input:  source_path: Path
Output: ValidateResult(source: VideoSource)

Kiểm tra:
- File tồn tại và readable
- Có video stream
- Có audio stream
- Duration > 0
- Width/height > 0
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from v2.core.exceptions import ValidateError
from v2.core.types import PipelineContext, VideoSource
from v2.services.ffmpeg import probe_video

logger = logging.getLogger("v2.render.s01_validate")

MIN_DURATION_SEC = 1.0   # video ngắn hơn 1 giây không thể render


@dataclass(frozen=True)
class ValidateResult:
    source: VideoSource


def run(ctx: PipelineContext, source_path: Path) -> ValidateResult:
    """
    Validate source file. Raise ValidateError nếu file không hợp lệ.

    Không raise ngoài ValidateError — mọi lỗi khác được wrap vào ValidateError.
    """
    ctx.check_cancel()
    logger.info("s01_validate job_id=%s path=%s", ctx.job_id, source_path)

    # Kiểm tra file tồn tại
    if not source_path.exists():
        raise ValidateError(f"File không tồn tại: {source_path}")
    if not source_path.is_file():
        raise ValidateError(f"Không phải file: {source_path}")
    if source_path.stat().st_size == 0:
        raise ValidateError(f"File rỗng (0 bytes): {source_path}")

    # Probe với ffprobe
    try:
        probe = probe_video(source_path)
    except Exception as exc:
        raise ValidateError(f"ffprobe thất bại: {exc}") from exc

    # Validate video stream
    if not probe.has_video:
        raise ValidateError(f"Không có video stream: {source_path}")
    if probe.video.width <= 0 or probe.video.height <= 0:
        raise ValidateError(
            f"Kích thước video không hợp lệ: {probe.video.width}x{probe.video.height}"
        )

    # Validate audio stream
    if not probe.has_audio:
        raise ValidateError(f"Không có audio stream: {source_path}")

    # Validate duration
    if probe.duration < MIN_DURATION_SEC:
        raise ValidateError(
            f"Video quá ngắn: {probe.duration:.2f}s (tối thiểu {MIN_DURATION_SEC}s)"
        )

    source = VideoSource(
        path=source_path,
        duration=probe.duration,
        has_audio=probe.has_audio,
        width=probe.video.width,
        height=probe.video.height,
        fps=probe.video.fps,
    )

    logger.info(
        "s01_validate ok job_id=%s duration=%.1fs resolution=%dx%d fps=%.2f",
        ctx.job_id, source.duration, source.width, source.height, source.fps,
    )
    ctx.emit("validate.ok", {
        "duration_sec": source.duration,
        "resolution": f"{source.width}x{source.height}",
        "fps": source.fps,
    })

    return ValidateResult(source=source)
