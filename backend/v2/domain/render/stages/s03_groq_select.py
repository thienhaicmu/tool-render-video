"""
s03_groq_select.py — Groq phân tích full SRT → chọn N segments tốt nhất.

ĐÂY LÀ NƠI DUY NHẤT GỌI GROQ API TRONG TOÀN BỘ PIPELINE.
Mọi stage sau (s04–s09) nhận list[Segment] — không gọi Groq nữa.

Flow:
  1. Đọc full SRT từ s02
  2. Build prompt (truncate tới GROQ_MAX_SRT_CHARS)
  3. Gọi GroqProvider._call_api() — 1 HTTP request duy nhất
  4. Parse JSON response → list[GroqSegment]
  5. Convert → list[Segment] (v2 type)
  6. Apply min_score filter
  7. Trả về GroqSelectResult

Nếu Groq disabled hoặc thất bại → trả về from_groq=False, segments=[].
Pipeline tiếp tục với local scorer ở s06.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from v2.core.constants import GROQ_MAX_SRT_CHARS, GROQ_DEFAULT_MODEL
from v2.core.exceptions import GroqSelectError
from v2.core.types import PipelineContext, Segment
from v2.domain.render.models import RenderRequest
from v2.domain.render.stages.s02_transcribe import TranscribeResult

logger = logging.getLogger("v2.render.s03_groq_select")


@dataclass(frozen=True)
class GroqSelectResult:
    segments:   list[Segment]
    model_used: str
    from_groq:  bool          # False = Groq skip / fail → s06 dùng local scorer
    warnings:   list[str]     = field(default_factory=list)


def run(
    ctx: PipelineContext,
    prev: TranscribeResult,
    request: RenderRequest,
) -> GroqSelectResult:
    """
    Gọi Groq để chọn segments. Không raise ra ngoài —
    trả về from_groq=False nếu Groq disabled hoặc thất bại.
    """
    ctx.check_cancel()
    logger.info("s03_groq_select job_id=%s groq_enabled=%s", ctx.job_id, request.groq_enabled)

    # ── Guard: Groq disabled ──────────────────────────────────────────────────
    if not request.groq_enabled:
        logger.info("s03_groq_select: groq disabled — s06 sẽ dùng local scorer")
        return GroqSelectResult(segments=[], model_used="", from_groq=False)

    api_key = request.resolve_groq_api_key()
    if not api_key:
        logger.warning("s03_groq_select: groq_enabled=True nhưng không có API key")
        return GroqSelectResult(
            segments=[], model_used="", from_groq=False,
            warnings=["groq_no_api_key"],
        )

    # ── Đọc SRT ───────────────────────────────────────────────────────────────
    srt_content = _read_srt(prev.srt_path)
    if not srt_content:
        logger.warning("s03_groq_select: SRT rỗng — không thể gọi Groq")
        return GroqSelectResult(
            segments=[], model_used="", from_groq=False,
            warnings=["empty_srt"],
        )

    model = request.groq_model or GROQ_DEFAULT_MODEL

    # ── Gọi Groq API — 1 lần duy nhất ────────────────────────────────────────
    ctx.emit("groq_select.start", {
        "model": model,
        "output_count": request.output_count,
        "srt_chars": len(srt_content),
    })

    raw_response = _call_groq_once(
        srt_content=srt_content,
        output_count=request.output_count,
        min_sec=request.min_part_sec,
        max_sec=request.max_part_sec,
        video_duration=prev.duration_sec,
        api_key=api_key,
        model=model,
        language=request.groq_language,
    )

    if raw_response is None:
        logger.warning("s03_groq_select: Groq trả về None — fallback local scorer")
        return GroqSelectResult(
            segments=[], model_used=model, from_groq=False,
            warnings=["groq_empty_response"],
        )

    # ── Parse response ────────────────────────────────────────────────────────
    groq_segments = _parse_response(
        raw=raw_response,
        output_count=request.output_count,
        min_sec=request.min_part_sec,
        max_sec=request.max_part_sec,
        video_duration=prev.duration_sec,
    )

    if not groq_segments:
        logger.warning("s03_groq_select: parse thất bại hoặc không có segment hợp lệ")
        return GroqSelectResult(
            segments=[], model_used=model, from_groq=False,
            warnings=["groq_parse_failed"],
        )

    # ── Apply min_score filter ────────────────────────────────────────────────
    before_filter = len(groq_segments)
    groq_segments = [s for s in groq_segments if s.score >= request.groq_min_score]
    if len(groq_segments) < before_filter:
        logger.info(
            "s03_groq_select: %d/%d segments bị loại do score < %.2f",
            before_filter - len(groq_segments), before_filter, request.groq_min_score,
        )

    if not groq_segments:
        logger.warning("s03_groq_select: tất cả segments dưới min_score=%.2f", request.groq_min_score)
        return GroqSelectResult(
            segments=[], model_used=model, from_groq=False,
            warnings=["all_below_min_score"],
        )

    # ── Convert → v2 Segment ─────────────────────────────────────────────────
    segments = [
        Segment(
            start=gs.start,
            end=gs.end,
            score=gs.score,
            title=gs.title or gs.clip_name,
            reason=gs.reason,
            source="groq",
        )
        for gs in groq_segments
    ]

    logger.info(
        "s03_groq_select ok job_id=%s model=%s segments=%d",
        ctx.job_id, model, len(segments),
    )
    ctx.emit("groq_select.done", {
        "model": model,
        "segments": len(segments),
        "scores": [round(s.score, 3) for s in segments],
    })

    return GroqSelectResult(segments=segments, model_used=model, from_groq=True)


# ── Internal ──────────────────────────────────────────────────────────────────

def _read_srt(srt_path: Path) -> str:
    """Đọc SRT, truncate tới GROQ_MAX_SRT_CHARS. Trả về '' nếu lỗi."""
    try:
        content = srt_path.read_text(encoding="utf-8", errors="replace")
        if len(content) > GROQ_MAX_SRT_CHARS:
            content = content[:GROQ_MAX_SRT_CHARS] + "\n... [transcript truncated]"
        return content.strip()
    except Exception as exc:
        logger.warning("s03_groq_select: không đọc được SRT: %s", exc)
        return ""


def _call_groq_once(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str,
    model: str,
    language: str,
) -> Optional[str]:
    """
    Gọi Groq API đúng 1 lần. Trả về raw string response hoặc None nếu thất bại.
    Reuse GroqProvider + prompts từ v1 — không duplicate.
    """
    try:
        from app.ai.analysis.groq.prompts import build_segment_prompt
        from app.ai.analysis.cloud.groq_provider import GroqProvider
    except ImportError as exc:
        logger.warning("s03_groq_select: không import được v1 Groq modules: %s", exc)
        return None

    try:
        system_prompt, user_prompt = build_segment_prompt(
            srt_content=srt_content,
            output_count=output_count,
            min_sec=min_sec,
            max_sec=max_sec,
            language=language,
        )
        # GroqProvider._call_api() nhận combined prompt string
        full_prompt = f"[INSTRUCTION]\n{system_prompt}\n\n[TASK]\n{user_prompt}"
        provider = GroqProvider(api_key=api_key, model=model)
        return provider._call_api(full_prompt)
    except Exception as exc:
        logger.warning("s03_groq_select: Groq API call thất bại: %s", exc)
        return None


def _parse_response(
    raw: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
) -> list:
    """
    Parse Groq response → list[GroqSegment]. Trả về [] nếu parse thất bại.

    Khác v1: chấp nhận partial result (ít hơn output_count) thay vì trả None.
    Lý do: Groq không phải lúc nào cũng trả đủ số segment yêu cầu, nhưng
    các segment nó trả vẫn có giá trị — không nên bỏ hoàn toàn.
    """
    try:
        from app.ai.analysis.groq.parser import _extract_json_array, _parse_item
    except ImportError:
        logger.warning("s03_groq_select: không import được v1 parser")
        return []

    try:
        data = _extract_json_array(raw)
        if not isinstance(data, list):
            return []

        segments = []
        for item in data:
            seg = _parse_item(item, min_sec, max_sec, video_duration)
            if seg is not None:
                segments.append(seg)

        # Sắp theo score giảm dần, lấy tối đa output_count
        segments.sort(key=lambda s: s.score, reverse=True)
        return segments[:output_count]

    except Exception as exc:
        logger.warning("s03_groq_select: parse error: %s", exc)
        return []
