"""
timing_recommender.py — Timing mutation plan builder. Phase 19.

Orchestrates timing analysis and applies safety gates.
Advisory by default (enabled=False). Never raises. No FFmpeg mutation.
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.timing.timing_schema import (
    TimingMutationCandidate,
    TimingMutationPlan,
    _MAX_CANDIDATES,
    _MAX_TRIM_SECONDS,
)
from app.ai.timing.timing_analyzer import analyze_timing_candidates
from app.ai.timing.timing_safety import is_candidate_safe

logger = logging.getLogger("app.ai.timing")


def build_timing_mutation_plan(
    retention_context: Any = None,
    story_context: Any = None,
    pacing_context: Any = None,
    transcript_chunks: Any = None,
    enabled: bool = False,
) -> TimingMutationPlan:
    """Build a timing mutation plan from retention risk metadata.

    When enabled=False (default): mode='advisory', all safe_to_apply=False.
    When enabled=True: safety gate applied; passing candidates get safe_to_apply=True.
    Never raises. No timing or FFmpeg mutation.
    """
    try:
        return _build_plan(
            retention_context,
            story_context,
            pacing_context,
            transcript_chunks,
            enabled,
        )
    except Exception as exc:
        logger.debug("build_timing_mutation_plan_failed: %s", exc)
        return TimingMutationPlan(
            available=False,
            mode="advisory",
            warnings=[f"timing_mutation_error:{type(exc).__name__}"],
        )


def _build_plan(
    retention_context: Any,
    story_context: Any,
    pacing_context: Any,
    transcript_chunks: Any,
    enabled: bool,
) -> TimingMutationPlan:
    warnings: list[str] = []

    candidates = analyze_timing_candidates(
        retention_context=retention_context,
        story_context=story_context,
        pacing_context=pacing_context,
        transcript_chunks=transcript_chunks,
    )

    if not candidates:
        warnings.append("no_timing_candidates")

    if not enabled:
        # Advisory mode: safe_to_apply stays False for all candidates
        for c in candidates:
            c.safe_to_apply = False
        mode = "advisory"
    else:
        # Enabled mode: run safety gate
        mode = "enabled"
        for c in candidates:
            c.safe_to_apply = is_candidate_safe(c)

    # Estimated retention gain: sum of (confidence × max_trim / _MAX_TRIM_SECONDS) for safe candidates
    safe_candidates = [c for c in candidates if c.safe_to_apply]
    gain = 0.0
    for c in safe_candidates:
        try:
            trim_ratio = min(1.0, float(c.max_trim_seconds) / _MAX_TRIM_SECONDS)
            gain += float(c.confidence) * trim_ratio * 0.05  # 5% max gain per candidate
        except Exception:
            pass
    estimated_gain = round(min(1.0, gain), 4)

    available = len(candidates) > 0

    logger.info(
        "ai_timing_mutation_plan_generated available=%s mode=%s "
        "candidates=%d safe=%d estimated_retention_gain=%.4f",
        available,
        mode,
        len(candidates),
        len(safe_candidates),
        estimated_gain,
    )

    return TimingMutationPlan(
        available=available,
        mode=mode,
        candidates=candidates[:_MAX_CANDIDATES],
        estimated_retention_gain=estimated_gain,
        warnings=warnings,
    )
