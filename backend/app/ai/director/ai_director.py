"""
ai_director.py — AI Director Phase 1: safe local AI edit planning.

Orchestrates transcript normalization, clip selection, and plan assembly.
Never raises — returns None on any failure so the existing render pipeline
continues unchanged.

Public API:
    create_ai_edit_plan(request, context) -> AIEditPlan | None
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.ai.director.edit_plan_schema import (
    AIClipPlan, AISubtitlePlan, AICameraPlan, AIEditPlan,
)
from app.ai.config.ai_modes import get_mode_config
from app.ai.analyzers.transcript_analyzer import normalize_transcript_chunks
from app.ai.director.clip_selector import select_ai_segments

logger = logging.getLogger("app.ai.director")


def create_ai_edit_plan(request: Any, context: dict) -> Optional[AIEditPlan]:
    """Create an AI edit plan for the render request.

    Returns None when:
    - ai_director_enabled is False (fast path, no logging)
    - any exception occurs (logged as WARNING, pipeline continues)

    context keys (all optional):
        job_id          str
        transcript_blocks  list[dict|obj]  — already-parsed transcript
        subtitle_blocks    list[dict|obj]  — subtitle blocks (fallback source)
        srt_path        str|Path          — path to full SRT file
        scenes          list[dict]        — scene detection results
        duration        float             — source video duration in seconds
        market          str               — target market (informational)
    """
    if not bool(getattr(request, "ai_director_enabled", False)):
        return None

    mode = str(getattr(request, "ai_mode", "viral_tiktok") or "viral_tiktok")
    job_id = str(context.get("job_id", "unknown"))

    logger.info("ai_director_started job_id=%s mode=%s", job_id, mode)

    try:
        plan = _build_plan(request, context, mode, job_id)
        logger.info(
            "ai_director_plan_created job_id=%s mode=%s segments=%d fallback=%s warnings=%s",
            job_id, mode,
            len(plan.selected_segments),
            plan.fallback_used,
            plan.warnings,
        )
        return plan
    except Exception as exc:
        logger.warning(
            "ai_director_failed_fallback job_id=%s mode=%s error=%s",
            job_id, mode, exc,
        )
        return None


def _build_plan(
    request: Any,
    context: dict,
    mode: str,
    job_id: str,
) -> AIEditPlan:
    warnings: list[str] = []
    fallback_used = False

    mode_config = get_mode_config(mode)

    # --- Transcript resolution ---
    chunks = _resolve_transcript_chunks(context, warnings)
    if not chunks:
        fallback_used = True
        warnings.append("no_transcript_available")
        logger.info("ai_director_no_segments_fallback job_id=%s: no transcript; using scene fallback", job_id)

    # --- Clip selection ---
    scenes: list[dict] = list(context.get("scenes") or [])
    duration = float(context.get("duration") or 0.0)

    raw_target = getattr(request, "ai_target_duration", None)
    target_duration: Optional[float] = float(raw_target) if raw_target else None

    selected_raw = select_ai_segments(
        chunks=chunks,
        scenes=scenes,
        duration=duration,
        mode_config=mode_config,
        target_duration=target_duration,
    )

    selected_segments = [
        AIClipPlan(
            start=float(s["start"]),
            end=float(s["end"]),
            score=float(s.get("score", 50.0)),
            reason=str(s.get("reason", "")),
            source=str(s.get("source", "local_ai")),
        )
        for s in selected_raw
    ]

    if not selected_segments:
        fallback_used = True
        warnings.append("no_segments_selected")

    # --- Subtitle plan ---
    subtitle_plan = AISubtitlePlan(
        tone=mode_config.get("subtitle_tone", "default"),
        highlight_keywords=(mode == "viral_tiktok"),
        max_words_per_line=None,
    )

    # --- Camera plan ---
    camera_plan = AICameraPlan(
        mode="auto",
        behavior=mode_config.get("camera_behavior", "none"),
        subtitle_safe=True,
    )

    return AIEditPlan(
        enabled=True,
        mode=mode,
        selected_segments=selected_segments,
        subtitle=subtitle_plan,
        camera=camera_plan,
        warnings=warnings,
        fallback_used=fallback_used,
    )


def _resolve_transcript_chunks(context: dict, warnings: list[str]) -> list[dict]:
    """Try transcript sources in priority order. Returns [] if none work."""
    # 1. Pre-normalized chunks
    if context.get("transcript_chunks"):
        return list(context["transcript_chunks"])

    # 2. Transcript blocks (list of dicts or objects)
    if context.get("transcript_blocks"):
        chunks = normalize_transcript_chunks(context["transcript_blocks"])
        if chunks:
            return chunks

    # 3. Subtitle blocks as fallback source
    if context.get("subtitle_blocks"):
        chunks = normalize_transcript_chunks(context["subtitle_blocks"])
        if chunks:
            return chunks

    # 4. Full SRT file path
    srt_path = context.get("srt_path")
    if srt_path:
        try:
            srt_text = Path(str(srt_path)).read_text(encoding="utf-8", errors="replace")
            chunks = normalize_transcript_chunks(srt_text)
            if chunks:
                return chunks
        except Exception as exc:
            warnings.append(f"srt_read_failed: {type(exc).__name__}")

    return []
