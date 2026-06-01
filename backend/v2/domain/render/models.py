"""
models.py — RenderRequest và RenderResult cho domain render v2.

Quy tắc:
- source_path bắt buộc, chỉ nhận local file — không có youtube_url
- Mọi field optional default về disabled (False / "" / None)
- Không có business logic trong model
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from v2.core.constants import (
    DEFAULT_OUTPUT_COUNT,
    GROQ_DEFAULT_MODEL,
    MAX_OUTPUT_COUNT,
    MAX_PART_DURATION_SEC,
    MIN_PART_DURATION_SEC,
    PLATFORM_TIKTOK,
    SUPPORTED_PLATFORMS,
    DEFAULT_VIDEO_CODEC,
)


class RenderRequest(BaseModel):
    # ── Source — local only ───────────────────────────────────────────────────
    source_path:  Path              # bắt buộc — path đến file video local
    output_dir:   Path              # bắt buộc — thư mục chứa kết quả

    # ── Segment config ────────────────────────────────────────────────────────
    output_count:     int   = Field(DEFAULT_OUTPUT_COUNT, ge=1, le=MAX_OUTPUT_COUNT)
    min_part_sec:     float = Field(MIN_PART_DURATION_SEC, ge=5.0)
    max_part_sec:     float = Field(MAX_PART_DURATION_SEC, le=300.0)

    # ── Groq — disabled by default ────────────────────────────────────────────
    groq_enabled:     bool  = False
    groq_api_key:     str   = ""          # override GROQ_API_KEY env var
    groq_model:       str   = GROQ_DEFAULT_MODEL
    groq_language:    str   = "auto"
    groq_min_score:   float = Field(0.6, ge=0.0, le=1.0)

    # ── AI local — disabled by default ───────────────────────────────────────
    ai_director_enabled: bool = False     # camera/subtitle/pacing planning
    subtitle_enabled:    bool = True
    voice_enabled:       bool = False     # TTS narration

    # ── Output ────────────────────────────────────────────────────────────────
    platform:     str = PLATFORM_TIKTOK
    video_codec:  str = DEFAULT_VIDEO_CODEC
    aspect_ratio: str = "9:16"

    @model_validator(mode="after")
    def validate_fields(self) -> "RenderRequest":
        if not self.source_path.exists():
            raise ValueError(f"source_path không tồn tại: {self.source_path}")
        if self.min_part_sec >= self.max_part_sec:
            raise ValueError("min_part_sec phải nhỏ hơn max_part_sec")
        if self.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"platform phải là một trong: {SUPPORTED_PLATFORMS}")
        return self

    def resolve_groq_api_key(self) -> str:
        """Trả về API key: request field trước, env var sau."""
        if self.groq_api_key:
            return self.groq_api_key
        from v2.core.config import GROQ_API_KEY
        return GROQ_API_KEY


class RenderResult(BaseModel):
    """Kết quả tổng hợp sau khi pipeline chạy xong."""
    job_id:          str
    status:          str            # "completed" | "completed_with_errors" | "failed"
    total_parts:     int
    success_parts:   int
    failed_parts:    int
    best_output:     Optional[Path] = None
    output_rank_score: float        = 0.0
    is_best_output:  bool           = False
    is_best_clip:    bool           = False
    outputs:         list[dict]     = Field(default_factory=list)
    warnings:        list[str]      = Field(default_factory=list)
