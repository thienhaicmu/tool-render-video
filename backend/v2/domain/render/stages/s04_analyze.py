"""
s04_analyze.py — Content analysis CHỈ trên segments đã được chọn.

Input:  GroqSelectResult (segments), ValidateResult (source path), TranscribeResult (srt_path)
Output: AnalyzeResult(per_segment: dict[int, SegmentAnalysis], from_analyzer: bool)

Khác với app cũ: KHÔNG phân tích toàn bộ video.
Chạy ContentAnalyzer 1 lần trên toàn video, sau đó map kết quả về từng segment
dựa trên time window — tiết kiệm hơn chạy N lần riêng lẻ.

Fallback: SRT-based local analysis nếu ContentAnalyzer không khả dụng.

Local only — không gọi cloud API.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from v2.core.types import PipelineContext, Segment
from v2.domain.render.stages.s01_validate import ValidateResult
from v2.domain.render.stages.s02_transcribe import TranscribeResult
from v2.domain.render.stages.s03_groq_select import GroqSelectResult

logger = logging.getLogger("v2.render.s04_analyze")

# Hook indicator keywords (language-agnostic enough for vi/en)
_HOOK_KEYWORDS = re.compile(
    r"\b(bí\s*quyết|sự\s*thật|tại\s*sao|làm\s*sao|cách|hướng\s*dẫn"
    r"|secret|truth|why|how|tip|trick|reveal|you\s*need|must\s*see"
    r"|amazing|incredible|finally|never|always|biggest|best|worst)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SegmentAnalysis:
    """Kết quả phân tích nội dung của 1 segment."""
    dominant_emotion: str        = "neutral"
    emotion_score:    float      = 0.0
    has_hook:         bool       = False
    hook_type:        str        = "none"    # "question" | "keyword" | "position" | "none"
    energy_level:     str        = "medium"  # "low" | "medium" | "high"
    bpm:              Optional[float] = None
    word_count:       int        = 0
    words_per_sec:    float      = 0.0


@dataclass(frozen=True)
class AnalyzeResult:
    per_segment:   dict[int, SegmentAnalysis]
    from_analyzer: bool = False   # True = v1 ContentAnalyzer ran successfully


def run(
    ctx: PipelineContext,
    groq_result: GroqSelectResult,
    validate_result: ValidateResult,
    transcribe_result: TranscribeResult,
) -> AnalyzeResult:
    """
    Phân tích nội dung từng segment. Không raise — trả về local fallback nếu thất bại.
    """
    ctx.check_cancel()
    segments = groq_result.segments
    logger.info("s04_analyze job_id=%s segments=%d", ctx.job_id, len(segments))

    if not segments:
        return AnalyzeResult(per_segment={})

    ctx.emit("analyze.start", {"segments": len(segments)})

    # Thử v1 ContentAnalyzer (có emotion/beat/hook detection đầy đủ)
    full_analysis = _try_content_analyzer(
        source_path=validate_result.source.path,
        srt_path=transcribe_result.srt_path,
        duration=validate_result.source.duration,
    )

    # Đọc SRT blocks để dùng cho cả 2 path
    srt_blocks = _read_srt_blocks(transcribe_result.srt_path)

    per_segment: dict[int, SegmentAnalysis] = {}
    for i, seg in enumerate(segments):
        ctx.check_cancel()
        if full_analysis is not None:
            per_segment[i] = _map_from_full_analysis(seg, i, full_analysis, srt_blocks)
        else:
            per_segment[i] = _local_analyze(seg, srt_blocks)

    from_analyzer = full_analysis is not None
    ctx.emit("analyze.done", {
        "segments": len(segments),
        "from_analyzer": from_analyzer,
        "hooks_found": sum(1 for a in per_segment.values() if a.has_hook),
    })
    logger.info(
        "s04_analyze done job_id=%s from_analyzer=%s hooks=%d",
        ctx.job_id, from_analyzer,
        sum(1 for a in per_segment.values() if a.has_hook),
    )

    return AnalyzeResult(per_segment=per_segment, from_analyzer=from_analyzer)


# ── v1 ContentAnalyzer wrapper ────────────────────────────────────────────────

def _try_content_analyzer(source_path: Path, srt_path: Path, duration: float):
    """
    Chạy v1 ContentAnalyzer.analyze(). Trả về result object hoặc None nếu lỗi.
    Import lazy để không crash nếu module không có.
    """
    try:
        from app.ai.content.content_analyzer import ContentAnalyzer
    except ImportError:
        logger.debug("s04_analyze: ContentAnalyzer không khả dụng — dùng local fallback")
        return None

    try:
        result = ContentAnalyzer.analyze(
            source_path=str(source_path),
            srt_path=str(srt_path),
            source_duration=duration,
        )
        if not getattr(result, "available", False):
            logger.debug("s04_analyze: ContentAnalyzer returned available=False")
            return None
        return result
    except Exception as exc:
        logger.warning("s04_analyze: ContentAnalyzer.analyze thất bại: %s", exc)
        return None


def _map_from_full_analysis(
    seg: Segment,
    seg_index: int,
    analysis,
    srt_blocks: list[dict],
) -> SegmentAnalysis:
    """Map kết quả ContentAnalyzer toàn video → SegmentAnalysis của 1 segment."""

    # Emotion: tìm emotion_arc window gần nhất với midpoint của segment
    mid = (seg.start + seg.end) / 2.0
    dominant_emotion = "neutral"
    emotion_score = 0.0
    emotion_arc = getattr(analysis, "emotion_arc", None) or []
    if emotion_arc:
        # emotion_arc item thường có "time" hoặc "start"/"end" và "emotion"/"score"
        best = min(
            emotion_arc,
            key=lambda w: abs(_arc_midpoint(w) - mid),
            default=None,
        )
        if best:
            dominant_emotion = str(best.get("emotion", "neutral"))
            emotion_score    = float(best.get("score", 0.0))

    # Hook: kiểm tra xem có hook_position nào nằm trong segment không
    hook_positions = getattr(analysis, "hook_positions", None) or []
    has_hook = False
    hook_type = "none"
    for hp in hook_positions:
        hp_time = float(hp.get("time", hp.get("timestamp", -1)))
        if seg.start <= hp_time <= seg.end:
            has_hook = True
            hook_type = str(hp.get("type", "position"))
            break

    # Energy / BPM
    energy_level = str(getattr(analysis, "energy_level", "medium") or "medium")
    bpm_val = getattr(analysis, "bpm", None)
    bpm = float(bpm_val) if bpm_val else None

    # Word count từ SRT
    seg_blocks = [b for b in srt_blocks if b["start"] < seg.end and b["end"] > seg.start]
    words = sum(len(b["text"].split()) for b in seg_blocks)
    dur = seg.duration or 1.0
    wps = words / dur

    return SegmentAnalysis(
        dominant_emotion=dominant_emotion,
        emotion_score=min(1.0, max(0.0, emotion_score)),
        has_hook=has_hook,
        hook_type=hook_type,
        energy_level=_normalize_energy(energy_level, wps),
        bpm=bpm,
        word_count=words,
        words_per_sec=round(wps, 2),
    )


def _arc_midpoint(window: dict) -> float:
    """Lấy midpoint của 1 emotion_arc window dict."""
    if "time" in window:
        return float(window["time"])
    start = float(window.get("start", 0))
    end   = float(window.get("end", start))
    return (start + end) / 2.0


# ── Local fallback (SRT-only) ─────────────────────────────────────────────────

def _local_analyze(seg: Segment, srt_blocks: list[dict]) -> SegmentAnalysis:
    """
    Phân tích cơ bản chỉ dựa vào SRT — không cần ContentAnalyzer.
    Dùng khi v1 module không khả dụng.
    """
    seg_blocks = [b for b in srt_blocks if b["start"] < seg.end and b["end"] > seg.start]
    if not seg_blocks:
        return SegmentAnalysis()

    text = " ".join(b["text"] for b in seg_blocks)
    words = text.split()
    dur = seg.duration or 1.0
    wps = len(words) / dur

    # Hook detection bằng regex keyword
    has_hook = False
    hook_type = "none"
    if _HOOK_KEYWORDS.search(text):
        has_hook = True
        hook_type = "keyword"
    elif "?" in text:
        has_hook = True
        hook_type = "question"
    elif seg.start <= 5.0:   # 5 giây đầu video = natural hook position
        has_hook = True
        hook_type = "position"

    return SegmentAnalysis(
        dominant_emotion="neutral",
        emotion_score=0.0,
        has_hook=has_hook,
        hook_type=hook_type,
        energy_level=_normalize_energy("medium", wps),
        bpm=None,
        word_count=len(words),
        words_per_sec=round(wps, 2),
    )


def _normalize_energy(base: str, wps: float) -> str:
    """
    Kết hợp energy_level từ ContentAnalyzer và words-per-second từ SRT
    để ra energy level cuối cùng.
    """
    if wps >= 3.5:
        return "high"
    if wps <= 1.0:
        return "low"
    # Giữ nguyên base nếu wps ở mức trung bình
    if base in ("high", "low", "medium"):
        return base
    return "medium"


# ── SRT reader ────────────────────────────────────────────────────────────────

def _read_srt_blocks(srt_path: Path) -> list[dict]:
    """
    Đọc SRT → list[{start, end, text}]. Thử v1 parser trước, tự parse nếu lỗi.
    Trả về [] nếu cả 2 đều thất bại.
    """
    try:
        from app.services.subtitles.srt_core import parse_srt_blocks
        return parse_srt_blocks(str(srt_path))
    except Exception:
        pass

    # Minimal local SRT parser
    try:
        content = srt_path.read_text(encoding="utf-8", errors="replace")
        return _parse_srt_minimal(content)
    except Exception as exc:
        logger.warning("s04_analyze: không đọc được SRT: %s", exc)
        return []


_TS_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def _parse_srt_minimal(content: str) -> list[dict]:
    blocks = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = block.strip().splitlines()
        ts_line = next((l for l in lines if "-->" in l), None)
        if not ts_line:
            continue
        m = _TS_RE.search(ts_line)
        if not m:
            continue
        g = m.groups()
        start = int(g[0]) * 3600 + int(g[1]) * 60 + int(g[2]) + int(g[3]) / 1000
        end   = int(g[4]) * 3600 + int(g[5]) * 60 + int(g[6]) + int(g[7]) / 1000
        text_lines = [l for l in lines if "-->" not in l and not l.strip().isdigit()]
        text = " ".join(text_lines).strip()
        if text:
            blocks.append({"start": start, "end": end, "text": text})
    return blocks
