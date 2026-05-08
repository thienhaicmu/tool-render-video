"""
subtitle_execution.py — Dynamic subtitle execution planner. Phase 17.

Combines emphasis/density/emotion intelligence into a SubtitleExecutionPlan.
Deterministic only. Never raises. No timing mutation. No transcript rewrite.
"""
from __future__ import annotations

import logging

from app.ai.subtitles.subtitle_execution_schema import (
    SubtitleExecutionPlan,
    SubtitleExecutionHint,
    SubtitleExecutionRegion,
    VALID_DENSITY_MODES,
    VALID_EMOTION_STYLES,
)
from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
from app.ai.subtitles.subtitle_density import analyze_subtitle_density
from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style

logger = logging.getLogger("app.ai.subtitles")

_MAX_REGIONS = 20


def build_subtitle_execution_plan(
    transcript_chunks=None,
    pacing_context=None,
    emotion_context=None,
    story_context=None,
    retention_context=None,
    creator_style_context=None,
) -> SubtitleExecutionPlan:
    """Build a subtitle execution plan from all available context signals.

    Returns SubtitleExecutionPlan with bounded values, max 20 regions.
    Never raises. No timing mutation. No transcript rewrite.
    """
    try:
        return _build_plan(
            transcript_chunks,
            pacing_context,
            emotion_context,
            story_context,
            retention_context,
            creator_style_context,
        )
    except Exception as exc:
        logger.debug("subtitle_execution_plan_failed: %s", exc)
        return SubtitleExecutionPlan(
            available=False,
            warnings=[f"execution_plan_error:{type(exc).__name__}"],
        )


def _build_plan(
    transcript_chunks,
    pacing_context,
    emotion_context,
    story_context,
    retention_context,
    creator_style_context,
) -> SubtitleExecutionPlan:
    chunks = list(transcript_chunks or [])
    pacing_ctx = dict(pacing_context or {})
    story_ctx = dict(story_context or {})
    retention_ctx = dict(retention_context or {})
    creator_ctx = dict(creator_style_context or {})
    warnings: list[str] = []

    # Merge emotion context with pacing context for combined signal
    combined_emotion_ctx = dict(emotion_context or {})
    combined_emotion_ctx.setdefault("emotion", pacing_ctx.get("emotion", "neutral"))
    combined_emotion_ctx.setdefault("emotion_score", pacing_ctx.get("emotion_score", 0.0))
    combined_emotion_ctx.setdefault("pacing_style", pacing_ctx.get("pacing_style", ""))

    # --- Emphasis analysis ---
    emphasis_result = build_subtitle_emphasis(
        transcript_chunks=chunks,
        pacing_context=pacing_ctx,
        emotion_context=combined_emotion_ctx,
        retention_context=retention_ctx,
    )
    emphasis_strength = _clamp(float(emphasis_result.get("emphasis_strength", 0.0)))
    beat_sync_strength = _clamp(float(emphasis_result.get("beat_sync_strength", 0.0)))
    keyword_focus = list(emphasis_result.get("keyword_focus", []))
    for w in (emphasis_result.get("warnings") or []):
        if w not in warnings:
            warnings.append(w)

    # --- Density analysis ---
    density_result = analyze_subtitle_density(
        transcript_chunks=chunks,
        pacing_context=pacing_ctx,
        story_context=story_ctx,
    )
    density_mode = str(density_result.get("density_mode", "normal"))
    if density_mode not in VALID_DENSITY_MODES:
        density_mode = "normal"
    for w in (density_result.get("warnings") or []):
        if w not in warnings:
            warnings.append(w)

    # --- Emotion style analysis ---
    emotion_result = detect_subtitle_emotion_style(
        emotion_context=combined_emotion_ctx,
        story_context=story_ctx,
        creator_style_context=creator_ctx,
    )
    emotion_style = str(emotion_result.get("emotion_style", "neutral"))
    if emotion_style not in VALID_EMOTION_STYLES:
        emotion_style = "neutral"
    for w in (emotion_result.get("warnings") or []):
        if w not in warnings:
            warnings.append(w)

    # --- Build global hint ---
    global_hint = SubtitleExecutionHint(
        emphasis_strength=emphasis_strength,
        density_mode=density_mode,
        emotion_style=emotion_style,
        beat_sync_strength=beat_sync_strength,
        keyword_focus=keyword_focus[:10],
        warnings=[],
    )

    # --- Build temporal execution regions ---
    regions = _build_regions(
        chunks, pacing_ctx, story_ctx,
        emphasis_strength, emotion_style, beat_sync_strength,
    )

    logger.info(
        "ai_subtitle_execution_generated emphasis=%.3f density=%s emotion=%s "
        "beat_sync=%.3f regions=%d",
        emphasis_strength, density_mode, emotion_style, beat_sync_strength, len(regions),
    )

    return SubtitleExecutionPlan(
        available=True,
        regions=regions[:_MAX_REGIONS],
        global_hint=global_hint,
        warnings=warnings,
    )


def _build_regions(
    chunks: list,
    pacing_ctx: dict,
    story_ctx: dict,
    global_emphasis: float,
    global_emotion: str,
    global_beat_sync: float,
) -> list[SubtitleExecutionRegion]:
    """Build temporal execution regions from transcript chunks. Max 20 regions."""
    if not chunks:
        return []

    # Build a quick lookup of story segment boundaries by type
    story_segments = list(story_ctx.get("segments", []) or [])
    segment_bounds: dict[str, tuple[float, float]] = {}
    for seg in story_segments[:12]:
        if not isinstance(seg, dict):
            continue
        seg_type = str(seg.get("segment_type", "unknown"))
        s_start = float(seg.get("start", 0.0))
        s_end = float(seg.get("end", s_start + 1.0))
        segment_bounds[seg_type] = (s_start, s_end)

    regions: list[SubtitleExecutionRegion] = []

    for chunk in chunks[:_MAX_REGIONS]:
        if not isinstance(chunk, dict):
            continue
        start = float(chunk.get("start", 0.0))
        end = float(chunk.get("end", start + 1.0))
        if end <= start:
            continue

        style = "default"
        emphasis = global_emphasis
        beat_strength = global_beat_sync

        # Score-based emphasis from the chunk itself
        chunk_score = float(chunk.get("score", 0.0))
        if chunk_score > 0.7:
            emphasis = _clamp(emphasis + 0.15)
            style = "hook"
        elif chunk_score > 0.5:
            emphasis = _clamp(emphasis + 0.05)

        # Story segment region matching
        if "hook" in segment_bounds:
            h_start, h_end = segment_bounds["hook"]
            if start >= h_start and start < h_end + 2.0:
                style = "hook"
                emphasis = _clamp(emphasis + 0.12)

        if "climax" in segment_bounds:
            c_start, c_end = segment_bounds["climax"]
            if start >= c_start and start < c_end + 1.0:
                style = "climax"
                emphasis = _clamp(emphasis + 0.1)

        regions.append(SubtitleExecutionRegion(
            start=round(start, 3),
            end=round(end, 3),
            style=style,
            emphasis=_clamp(emphasis),
            emotion=global_emotion,
            beat_strength=_clamp(beat_strength),
            metadata={},
        ))

    return regions


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))
