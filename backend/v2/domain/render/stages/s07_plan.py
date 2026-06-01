"""
s07_plan.py — AI Director local: camera plan, subtitle plan, pacing.

Input:  FilterResult, AnalyzeResult, RenderRequest
Output: PlanResult(per_segment: dict[int, SegmentPlan])

Chỉ chạy khi ai_director_enabled=True. Nếu disabled → default plans.

Platform → mode mapping:
  tiktok           → "viral_tiktok"
  instagram_reels  → "podcast_shorts"
  youtube_shorts   → "storytelling"
  (other)          → "storytelling"

Delegates sang v1 camera_planner + subtitle_planner (lazy import).
Fallback: deterministic rule-based plan nếu v1 không khả dụng.

Local only — không gọi cloud API.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from v2.core.types import PipelineContext, Segment
from v2.domain.render.models import RenderRequest
from v2.domain.render.stages.s04_analyze import AnalyzeResult, SegmentAnalysis
from v2.domain.render.stages.s06_score_filter import FilterResult

logger = logging.getLogger("v2.render.s07_plan")

_PLATFORM_MODE = {
    "tiktok":           "viral_tiktok",
    "instagram_reels":  "podcast_shorts",
    "youtube_shorts":   "storytelling",
}


@dataclass(frozen=True)
class CameraConfig:
    behavior:        str   = "subject_lock"   # "dramatic_push"|"fast_follow"|"slow_reveal"|"subject_lock"|"none"
    zoom_strength:   float = 1.0              # 1.0–1.18
    follow_strength: float = 0.5             # 0.0–0.85


@dataclass(frozen=True)
class SubtitleConfig:
    style_preset:       str       = "viral_bold"   # "viral_bold"|"clean_pro"|"boxed_caption"
    density:            str       = "normal"       # "compact"|"normal"|"relaxed"
    highlight_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PacingConfig:
    pacing_style: str   = "default"   # "fast"|"medium"|"slow"|"default"
    energy_level: str   = "medium"
    cut_style:    str   = "standard"


@dataclass(frozen=True)
class SegmentPlan:
    camera:   CameraConfig
    subtitle: SubtitleConfig
    pacing:   PacingConfig


@dataclass(frozen=True)
class PlanResult:
    per_segment: dict[int, SegmentPlan]   # key = index trong ranked_segments


def run(
    ctx: PipelineContext,
    filter_result: FilterResult,
    analyze_result: AnalyzeResult,
    request: RenderRequest,
) -> PlanResult:
    """Tạo plan cho mỗi segment. Không raise."""
    ctx.check_cancel()
    segments = filter_result.ranked_segments
    logger.info(
        "s07_plan job_id=%s ai_director=%s segments=%d platform=%s",
        ctx.job_id, request.ai_director_enabled, len(segments), request.platform,
    )

    if not segments:
        return PlanResult(per_segment={})

    # Disabled → default plans (luôn an toàn, không cần compute)
    if not request.ai_director_enabled:
        default = _default_plan(request.platform)
        return PlanResult(per_segment={i: default for i in range(len(segments))})

    ctx.emit("plan.start", {"segments": len(segments), "platform": request.platform})

    mode = _PLATFORM_MODE.get(request.platform, "storytelling")
    per_segment: dict[int, SegmentPlan] = {}

    for i, seg in enumerate(segments):
        ctx.check_cancel()
        analysis = analyze_result.per_segment.get(i)
        per_segment[i] = _plan_segment(seg, i, analysis, mode, request)

    ctx.emit("plan.done", {"segments": len(per_segment)})
    logger.info("s07_plan done job_id=%s segments=%d", ctx.job_id, len(per_segment))

    return PlanResult(per_segment=per_segment)


# ── Per-segment planning ──────────────────────────────────────────────────────

def _plan_segment(
    seg: Segment,
    seg_index: int,
    analysis: Optional[SegmentAnalysis],
    mode: str,
    request: RenderRequest,
) -> SegmentPlan:
    """Tạo SegmentPlan cho 1 segment. Không raise."""
    pacing_ctx = _build_pacing_context(analysis)
    transcript_ctx = {"segment_index": seg_index, "source": seg.source}

    camera   = _plan_camera(mode, pacing_ctx, transcript_ctx)
    subtitle = _plan_subtitle(mode, pacing_ctx, transcript_ctx)
    pacing   = _plan_pacing(analysis, mode)

    return SegmentPlan(camera=camera, subtitle=subtitle, pacing=pacing)


def _plan_camera(mode: str, pacing_ctx: dict, transcript_ctx: dict) -> CameraConfig:
    """
    Gọi v1 camera_planner.plan_camera_behavior(). Fallback: rule-based.
    """
    try:
        from app.ai.director.camera_planner import plan_camera_behavior
        result = plan_camera_behavior(
            mode_config={"mode": mode},
            pacing_context=pacing_ctx,
            transcript_context=transcript_ctx,
        )
        return CameraConfig(
            behavior=str(result.behavior or "subject_lock"),
            zoom_strength=float(result.zoom_strength or 1.0),
            follow_strength=float(result.follow_strength or 0.5),
        )
    except Exception as exc:
        logger.debug("s07_plan: camera_planner thất bại, dùng rule-based: %s", exc)
        return _camera_rule_based(mode, pacing_ctx)


def _plan_subtitle(mode: str, pacing_ctx: dict, transcript_ctx: dict) -> SubtitleConfig:
    """
    Gọi v1 subtitle_planner.plan_subtitle_behavior(). Fallback: preset map.
    """
    try:
        from app.ai.director.subtitle_planner import plan_subtitle_behavior
        result = plan_subtitle_behavior(
            mode_config={"mode": mode},
            pacing_context=pacing_ctx,
            transcript_context=transcript_ctx,
        )
        density    = str(result.density or "normal")
        style      = _tone_to_preset(str(result.tone or "default"))
        return SubtitleConfig(style_preset=style, density=density)
    except Exception as exc:
        logger.debug("s07_plan: subtitle_planner thất bại, dùng preset map: %s", exc)
        return _subtitle_preset(mode)


# ── Rule-based fallbacks ──────────────────────────────────────────────────────

def _camera_rule_based(mode: str, pacing_ctx: dict) -> CameraConfig:
    energy = str(pacing_ctx.get("energy_level", "medium"))
    emotion = str(pacing_ctx.get("dominant_emotion", "neutral"))

    if emotion in ("surprise", "urgency", "excitement"):
        return CameraConfig(behavior="dramatic_push", zoom_strength=1.12, follow_strength=0.65)
    if mode == "viral_tiktok" or energy == "high":
        return CameraConfig(behavior="fast_follow",   zoom_strength=1.10, follow_strength=0.75)
    if mode == "podcast_shorts":
        return CameraConfig(behavior="subject_lock",  zoom_strength=1.0,  follow_strength=0.5)
    return CameraConfig(behavior="subject_lock", zoom_strength=1.05, follow_strength=0.5)


def _subtitle_preset(mode: str) -> SubtitleConfig:
    presets = {
        "viral_tiktok":   SubtitleConfig(style_preset="viral_bold",    density="compact"),
        "podcast_shorts": SubtitleConfig(style_preset="clean_pro",     density="normal"),
        "storytelling":   SubtitleConfig(style_preset="clean_pro",     density="normal"),
    }
    return presets.get(mode, SubtitleConfig())


def _plan_pacing(analysis: Optional[SegmentAnalysis], mode: str) -> PacingConfig:
    energy   = analysis.energy_level if analysis else "medium"
    bpm      = analysis.bpm if analysis else None
    wps      = analysis.words_per_sec if analysis else 0.0

    # Pacing style từ words-per-second + mode
    if wps >= 3.0 or (bpm and bpm >= 130) or mode == "viral_tiktok":
        pacing_style = "fast"
        cut_style    = "jump"
    elif wps <= 1.0 or mode == "storytelling":
        pacing_style = "slow"
        cut_style    = "smooth"
    else:
        pacing_style = "medium"
        cut_style    = "standard"

    return PacingConfig(pacing_style=pacing_style, energy_level=energy, cut_style=cut_style)


def _default_plan(platform: str) -> SegmentPlan:
    mode = _PLATFORM_MODE.get(platform, "storytelling")
    return SegmentPlan(
        camera=_camera_rule_based(mode, {}),
        subtitle=_subtitle_preset(mode),
        pacing=PacingConfig(),
    )


# ── Context builders ──────────────────────────────────────────────────────────

def _build_pacing_context(analysis: Optional[SegmentAnalysis]) -> dict:
    if analysis is None:
        return {}
    return {
        "energy_level":      analysis.energy_level,
        "dominant_emotion":  analysis.dominant_emotion,
        "bpm":               analysis.bpm,
        "words_per_sec":     analysis.words_per_sec,
        "beat_available":    analysis.bpm is not None,
    }


def _tone_to_preset(tone: str) -> str:
    mapping = {
        "hype":    "viral_bold",
        "clean":   "clean_pro",
        "story":   "clean_pro",
        "default": "clean_pro",
    }
    return mapping.get(tone, "clean_pro")
