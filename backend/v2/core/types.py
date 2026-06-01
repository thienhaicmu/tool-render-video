"""
types.py — Shared dataclasses dùng toàn bộ v2.

Quy tắc:
- Chỉ chứa types được dùng ở ít nhất 2 module khác nhau
- Stage-specific results định nghĩa trong stage module của nó
- Segment là immutable (frozen=True) — không mutate sau khi tạo
- Không import từ domain/ hoặc services/ để tránh circular imports
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# ── Core data types ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Segment:
    """Một đoạn video đã được chọn. Immutable.

    Là đơn vị dữ liệu trung tâm — được tạo ở s03_groq_select và đi qua
    toàn bộ pipeline còn lại.
    """
    start:  float            # giây, tính từ đầu video gốc
    end:    float            # giây
    score:  float            # 0.0–1.0 (Groq confidence)
    title:  str   = ""       # tên clip do Groq đặt
    reason: str   = ""       # lý do Groq chọn
    source: str   = "groq"   # "groq" | "local"

    @property
    def duration(self) -> float:
        return self.end - self.start

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError(f"Segment.start phải >= 0, got {self.start}")
        if self.end <= self.start:
            raise ValueError(f"Segment.end ({self.end}) phải > start ({self.start})")
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(f"Segment.score phải trong [0.0, 1.0], got {self.score}")


@dataclass(frozen=True)
class VideoSource:
    """Thông tin về file video nguồn đã được validate."""
    path:      Path
    duration:  float   # giây
    has_audio: bool
    width:     int
    height:    int
    fps:       float


# ── Pipeline context ──────────────────────────────────────────────────────────

@dataclass
class PipelineContext:
    """Metadata job được truyền vào mọi stage. Không chứa data của stage.

    Mỗi stage nhận context + result của stage trước → trả về result của nó.
    Context không thay đổi trong suốt pipeline.
    """
    job_id:       str
    work_dir:     Path
    cancel_event: threading.Event
    emit_fn:      Callable[[str, dict], None]   # gọi để emit WebSocket event

    def check_cancel(self) -> None:
        """Raise CancelledError nếu user đã cancel job."""
        from v2.core.exceptions import CancelledError
        if self.cancel_event.is_set():
            raise CancelledError(f"Job {self.job_id} was cancelled")

    def emit(self, stage: str, data: dict) -> None:
        """Emit WebSocket event. Không raise nếu emit thất bại."""
        try:
            self.emit_fn(stage, {"job_id": self.job_id, **data})
        except Exception:
            pass


# ── Part result (dùng ở s08 và s09) ──────────────────────────────────────────

@dataclass
class PartResult:
    """Kết quả render của 1 part. Dùng ở s08_render_parts và s09_qa_rank."""
    part_index:  int
    segment:     Segment
    output_path: Optional[Path]
    is_success:  bool
    error:       Optional[str]      = None
    duration:    Optional[float]    = None    # giây — duration thực của output
    file_size:   Optional[int]      = None    # bytes
    thumbnail:   Optional[Path]     = None
