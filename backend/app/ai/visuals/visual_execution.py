"""
visual_execution.py — Beat-synced visual execution planner. Phase 18.

Combines beat pulse regions + transition hints into a BeatVisualExecutionPlan.
Deterministic only. Never raises. No timing mutation. No FFmpeg mutation.
"""
from __future__ import annotations

import logging

from app.ai.visuals.beat_visual_schema import (
    BeatVisualExecutionPlan,
    _BPM_MIN,
    _BPM_MAX,
    _MIN_BEAT_COUNT,
)
from app.ai.visuals.beat_pulse import build_beat_pulse_regions
from app.ai.visuals.transition_planner import build_transition_hints

logger = logging.getLogger("app.ai.visuals")


def build_beat_visual_execution_plan(
    pacing_context=None,
    beat_execution_context=None,
    story_context=None,
    retention_context=None,
    creator_style_context=None,
) -> BeatVisualExecutionPlan:
    """Build a beat visual execution plan from existing AI metadata.

    Returns BeatVisualExecutionPlan with execution_mode='metadata_only'.
    Never raises. No timing mutation. No FFmpeg mutation.
    """
    try:
        return _build_plan(
            pacing_context,
            beat_execution_context,
            story_context,
            retention_context,
            creator_style_context,
        )
    except Exception as exc:
        logger.debug("build_beat_visual_execution_plan_failed: %s", exc)
        return BeatVisualExecutionPlan(
            available=False,
            warnings=[f"beat_visual_execution_error:{type(exc).__name__}"],
        )


def _build_plan(
    pacing_context,
    beat_execution_context,
    story_context,
    retention_context,
    creator_style_context,
) -> BeatVisualExecutionPlan:
    pacing_ctx = dict(pacing_context or {})
    beat_ctx = dict(beat_execution_context or {})
    warnings: list[str] = []

    # Resolve BPM for plan-level storage
    bpm: float | None = None
    raw_bpm = pacing_ctx.get("bpm") or beat_ctx.get("bpm")
    if raw_bpm is not None:
        try:
            bpm = float(raw_bpm)
        except (TypeError, ValueError):
            bpm = None

    # --- Beat pulse regions ---
    pulse_regions = build_beat_pulse_regions(
        pacing_context=pacing_ctx,
        beat_execution_context=beat_ctx,
        story_context=dict(story_context or {}),
        retention_context=dict(retention_context or {}),
    )

    # --- Transition hints ---
    transition_hints = build_transition_hints(
        pacing_context=pacing_ctx,
        story_context=dict(story_context or {}),
        retention_context=dict(retention_context or {}),
        creator_style_context=dict(creator_style_context or {}),
    )

    # Availability: requires valid beat metadata
    beat_available = bool(pacing_ctx.get("beat_available") or beat_ctx.get("beat_available"))
    raw_beat_count = pacing_ctx.get("beat_count") or beat_ctx.get("beat_count") or 0
    beat_count = int(raw_beat_count)

    if not beat_available:
        warnings.append("beat_data_unavailable")
    bpm_in_range = bpm is not None and _BPM_MIN <= bpm <= _BPM_MAX
    if bpm is not None and not bpm_in_range:
        warnings.append(f"bpm_out_of_range:{bpm:.1f}")
    if beat_count < _MIN_BEAT_COUNT and beat_available:
        warnings.append(f"beat_count_insufficient:{beat_count}")

    available = beat_available and bpm_in_range and beat_count >= _MIN_BEAT_COUNT

    logger.info(
        "ai_beat_visual_execution_generated available=%s bpm=%s "
        "pulse_regions=%d transition_hints=%d",
        available,
        f"{bpm:.1f}" if bpm is not None else "none",
        len(pulse_regions),
        len(transition_hints),
    )

    return BeatVisualExecutionPlan(
        available=available,
        execution_mode="metadata_only",
        bpm=bpm,
        pulse_regions=pulse_regions,
        transition_hints=transition_hints,
        warnings=warnings,
    )
