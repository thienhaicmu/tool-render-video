"""
s06_score_filter.py — Scoring + platform filter + story arc reorder.

Input:  GroqSelectResult, AnalyzeResult, SceneResult, ValidateResult, RenderRequest
Output: FilterResult(ranked_segments: list[Segment], used_local_scorer: bool)

Hai path:
  Path A (from_groq=True):  Groq đã chọn segments → refine score bằng content
                             analysis + platform bias → story arc reorder.
  Path B (from_groq=False): Groq skip/fail → local viral scorer tạo candidates
                             từ scene cuts → score → chọn top N.

Platform bias:
  TikTok     → hook bonus +0.06, ưu tiên high-energy + hooks trước
  Instagram  → penalize hook-free, prefer polished/clean energy
  YouTube    → neutral, prefer longer/narrative segments

Story arc reorder (áp dụng cả hai path):
  1. Hook segment (has_hook=True, highest hook score) → vị trí 1
  2. Remaining → sort by score desc

Local only — không gọi cloud API.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from v2.core.types import PipelineContext, Segment
from v2.domain.render.models import RenderRequest
from v2.domain.render.stages.s01_validate import ValidateResult
from v2.domain.render.stages.s03_groq_select import GroqSelectResult
from v2.domain.render.stages.s04_analyze import AnalyzeResult, SegmentAnalysis
from v2.domain.render.stages.s05_scene_detect import SceneResult

logger = logging.getLogger("v2.render.s06_score_filter")

# Platform hook bonus (added to normalized score 0–1)
_PLATFORM_HOOK_BONUS = {"tiktok": 0.06, "instagram_reels": 0.0, "youtube_shorts": 0.0}
_PLATFORM_ENERGY_BIAS = {"tiktok": "high", "instagram_reels": "medium", "youtube_shorts": "medium"}


@dataclass(frozen=True)
class FilterResult:
    ranked_segments:  list[Segment]
    used_local_scorer: bool   # True = Groq disabled/failed, dùng local scorer


def run(
    ctx: PipelineContext,
    groq_result: GroqSelectResult,
    analyze_result: AnalyzeResult,
    scene_result: SceneResult,
    validate_result: ValidateResult,
    request: RenderRequest,
) -> FilterResult:
    """Filter, score, reorder segments. Không raise — luôn trả về FilterResult."""
    ctx.check_cancel()
    logger.info(
        "s06_score_filter job_id=%s from_groq=%s segments=%d platform=%s",
        ctx.job_id, groq_result.from_groq, len(groq_result.segments), request.platform,
    )

    ctx.emit("score_filter.start", {
        "from_groq": groq_result.from_groq,
        "platform": request.platform,
        "input_segments": len(groq_result.segments),
    })

    if groq_result.from_groq and groq_result.segments:
        ranked = _path_a_refine(groq_result.segments, analyze_result, request)
        used_local = False
    else:
        ranked = _path_b_local_scorer(validate_result, scene_result, analyze_result, request)
        used_local = True

    # Cap at output_count
    ranked = ranked[: request.output_count]

    ctx.emit("score_filter.done", {
        "ranked": len(ranked),
        "used_local_scorer": used_local,
        "scores": [round(s.score, 3) for s in ranked],
    })
    logger.info(
        "s06_score_filter done job_id=%s ranked=%d used_local=%s",
        ctx.job_id, len(ranked), used_local,
    )

    return FilterResult(ranked_segments=ranked, used_local_scorer=used_local)


# ── Path A — refine Groq segments ────────────────────────────────────────────

def _path_a_refine(
    segments: list[Segment],
    analyze_result: AnalyzeResult,
    request: RenderRequest,
) -> list[Segment]:
    """
    Điều chỉnh score Groq bằng content analysis + platform bias,
    sau đó story-arc reorder.
    """
    hook_bonus   = _PLATFORM_HOOK_BONUS.get(request.platform, 0.0)
    energy_pref  = _PLATFORM_ENERGY_BIAS.get(request.platform, "medium")

    adjusted: list[tuple[float, bool, Segment]] = []  # (adj_score, has_hook, seg)
    for i, seg in enumerate(segments):
        analysis = analyze_result.per_segment.get(i)
        adj_score = _adjust_score(seg.score, analysis, hook_bonus, energy_pref)
        has_hook  = bool(analysis and analysis.has_hook)
        adjusted.append((adj_score, has_hook, seg))

    return _story_arc_sort(adjusted)


def _adjust_score(
    base_score: float,
    analysis: Optional[SegmentAnalysis],
    hook_bonus: float,
    energy_pref: str,
) -> float:
    score = base_score
    if analysis is None:
        return score

    if analysis.has_hook:
        score += hook_bonus

    # Energy alignment bonus/penalty (small, ±0.03)
    if energy_pref == "high" and analysis.energy_level == "high":
        score += 0.03
    elif energy_pref == "medium" and analysis.energy_level == "medium":
        score += 0.015
    elif analysis.energy_level != energy_pref:
        score -= 0.02

    return min(1.0, max(0.0, score))


def _story_arc_sort(
    adjusted: list[tuple[float, bool, Segment]],
) -> list[Segment]:
    """
    Story arc: hook segment đầu tiên, rồi phần còn lại sort score giảm dần.
    Nếu có nhiều hook → lấy hook có score cao nhất lên đầu.
    """
    hooks    = [(sc, seg) for sc, hk, seg in adjusted if hk]
    non_hook = [(sc, seg) for sc, hk, seg in adjusted if not hk]

    hooks.sort(key=lambda x: x[0], reverse=True)
    non_hook.sort(key=lambda x: x[0], reverse=True)

    result = []
    if hooks:
        result.append(hooks[0][1])
        result.extend(seg for _, seg in hooks[1:])
    result.extend(seg for _, seg in non_hook)
    return result


# ── Path B — local viral scorer ───────────────────────────────────────────────

def _path_b_local_scorer(
    validate_result: ValidateResult,
    scene_result: SceneResult,
    analyze_result: AnalyzeResult,
    request: RenderRequest,
) -> list[Segment]:
    """
    Khi Groq disabled/fail: tự xây candidate segments từ scene cuts,
    chạy v1 score_segments(), convert → list[Segment].
    Fallback: uniform time split.
    """
    candidates = _build_candidates(
        duration=validate_result.source.duration,
        all_cuts=scene_result.all_cuts,
        min_sec=request.min_part_sec,
        max_sec=request.max_part_sec,
        output_count=request.output_count,
    )

    if not candidates:
        logger.warning("s06_score_filter: không tạo được candidate segments")
        return []

    # Thử v1 score_segments
    scored = _try_v1_score_segments(
        candidates=candidates,
        all_cuts=scene_result.all_cuts,
        analyze_result=analyze_result,
    )

    if scored is None:
        # Fallback: dùng candidates với score đồng đều theo position
        logger.info("s06_score_filter: dùng position-based fallback scorer")
        scored = _position_score(candidates, validate_result.source.duration)

    # Sắp theo score giảm dần, lấy output_count
    scored.sort(key=lambda s: s.score, reverse=True)

    # Apply story arc reorder nếu có analyze data
    if analyze_result.per_segment:
        # Re-map analyze result về candidates (rough mapping by index)
        adjusted = []
        for i, seg in enumerate(scored):
            analysis = analyze_result.per_segment.get(i)
            has_hook = bool(analysis and analysis.has_hook)
            adjusted.append((seg.score, has_hook, seg))
        scored = _story_arc_sort(adjusted)

    return scored[: request.output_count]


def _build_candidates(
    duration: float,
    all_cuts: list[dict],
    min_sec: float,
    max_sec: float,
    output_count: int,
) -> list[Segment]:
    """
    Xây candidate segments từ scene cuts (natural boundaries) + sliding window.
    """
    candidates: list[Segment] = []

    # 1. Scene-cut-based: ghép các cuts liên tiếp để tạo window
    cut_times = sorted({0.0} | {c["start"] for c in all_cuts} | {duration})
    i = 0
    while i < len(cut_times) - 1:
        seg_start = cut_times[i]
        seg_end   = seg_start
        j = i + 1
        while j < len(cut_times) and (cut_times[j] - seg_start) < min_sec:
            j += 1
        if j < len(cut_times):
            seg_end = min(cut_times[j], seg_start + max_sec)
            dur = seg_end - seg_start
            if min_sec <= dur <= max_sec:
                candidates.append(Segment(start=seg_start, end=seg_end, score=0.5))
        i = j if j > i else i + 1

    # 2. Sliding window fallback nếu candidates quá ít
    if len(candidates) < output_count * 2:
        stride = max_sec * 0.5
        t = 0.0
        while t + min_sec <= duration:
            end = min(t + max_sec, duration)
            if end - t >= min_sec:
                candidates.append(Segment(start=t, end=end, score=0.5))
            t += stride

    # Deduplicate (overlap > 80%)
    return _dedup_candidates(candidates)


def _dedup_candidates(candidates: list[Segment]) -> list[Segment]:
    """Loại bỏ candidates overlap quá nhiều (> 80% overlap)."""
    result: list[Segment] = []
    for cand in candidates:
        overlap = False
        for kept in result:
            inter = min(cand.end, kept.end) - max(cand.start, kept.start)
            min_dur = min(cand.duration, kept.duration)
            if min_dur > 0 and inter / min_dur > 0.8:
                overlap = True
                break
        if not overlap:
            result.append(cand)
    return result


def _try_v1_score_segments(
    candidates: list[Segment],
    all_cuts: list[dict],
    analyze_result: AnalyzeResult,
) -> Optional[list[Segment]]:
    """
    Gọi v1 score_segments(). Trả về list[Segment] đã có score, hoặc None nếu lỗi.
    """
    try:
        from app.services.viral_scorer import score_segments
    except ImportError:
        logger.debug("s06_score_filter: viral_scorer không khả dụng")
        return None

    # Convert Segment → dict cho v1
    seg_dicts = [{"start": s.start, "end": s.end} for s in candidates]

    # Lấy ContentAnalysisResult nếu có (analyzer result object từ s04 không giữ object này,
    # nhưng viral_scorer vẫn chạy được khi content_analysis=None)
    try:
        scored_dicts = score_segments(
            segments=seg_dicts,
            scenes=all_cuts,
            content_analysis=None,
        )
    except Exception as exc:
        logger.warning("s06_score_filter: score_segments thất bại: %s", exc)
        return None

    result: list[Segment] = []
    for d in scored_dicts:
        raw_score = float(d.get("viral_score", 50)) / 100.0
        result.append(Segment(
            start=float(d["start"]),
            end=float(d["end"]),
            score=min(1.0, max(0.0, raw_score)),
            source="local_scorer",
        ))
    return result


def _position_score(candidates: list[Segment], total_duration: float) -> list[Segment]:
    """
    Simple fallback: score dựa trên vị trí trong video.
    Segment ở 20–60% vào video nhận score cao nhất (hook + content zone).
    """
    result = []
    for seg in candidates:
        mid = (seg.start + seg.end) / 2.0
        pos = mid / total_duration if total_duration > 0 else 0.5
        # Peak at 20–60% into video
        if 0.2 <= pos <= 0.6:
            score = 0.7 + 0.3 * (1.0 - abs(pos - 0.4) / 0.4)
        else:
            score = 0.4 * (1.0 - abs(pos - 0.4))
        result.append(Segment(start=seg.start, end=seg.end, score=round(score, 3), source="position"))
    return result
