"""
ai_director.py — AI Director: safe local AI edit planning.

Orchestrates transcript normalization, clip selection, emotion/pacing analysis,
and plan assembly. Never raises — returns None on any failure so the existing
render pipeline continues unchanged.

Public API:
    create_ai_edit_plan(request, context) -> AIEditPlan | None
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.ai.director.edit_plan_schema import (
    AIClipPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan, AIEditPlan,
)
from app.ai.director.camera_planner import plan_camera_behavior
from app.ai.director.subtitle_planner import plan_subtitle_behavior
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
        job_id             str
        transcript_blocks  list[dict|obj]  — already-parsed transcript
        subtitle_blocks    list[dict|obj]  — subtitle blocks (fallback source)
        srt_path           str|Path        — path to full SRT file
        scenes             list[dict]      — scene detection results
        duration           float           — source video duration in seconds
        market             str             — target market (informational)
        source_path        str|Path        — source video/audio path (for beat analysis)
        audio_path         str|Path        — explicit audio path (takes priority)
        memory_store       LocalMemoryStore — Phase 3 persistent store
    """
    if not bool(getattr(request, "ai_director_enabled", False)):
        return None

    mode = str(getattr(request, "ai_mode", "viral_tiktok") or "viral_tiktok")
    job_id = str(context.get("job_id", "unknown"))

    logger.info("ai_director_started job_id=%s mode=%s", job_id, mode)

    try:
        plan = _build_plan(request, context, mode, job_id)
        logger.info(
            "ai_director_plan_created job_id=%s mode=%s segments=%d fallback=%s pacing=%s warnings=%s",
            job_id, mode,
            len(plan.selected_segments),
            plan.fallback_used,
            plan.pacing.suggested_cut_style,
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

    # --- RAG memory context ---
    memory_ctx: dict = {}
    if bool(getattr(request, "ai_use_rag_memory", False)):
        try:
            from app.ai.rag.retriever import retrieve_ai_context
            query = _build_rag_query(mode, chunks, context)
            memory_store = context.get("memory_store")
            memory_ctx = retrieve_ai_context(query, memory_store=memory_store, top_k=5)
            if memory_ctx.get("warnings"):
                for w in memory_ctx["warnings"]:
                    warnings.append(f"rag:{w}")
        except Exception as exc:
            warnings.append(f"rag_error:{type(exc).__name__}")
            logger.debug("ai_director_rag_failed job_id=%s: %s", job_id, exc)

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
        memory_context=memory_ctx or None,
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

    # --- Phase 4: Pacing plan (needed by Phase 5 planners) ---
    pacing_plan = _build_pacing_plan(chunks, context, mode_config, warnings)

    # --- Phase 5: Camera + Subtitle planning ---
    pacing_ctx = {
        "pacing_style": pacing_plan.pacing_style,
        "energy_level": pacing_plan.energy_level,
        "emotion": pacing_plan.emotion,
        "emotion_score": pacing_plan.emotion_score,
        "beat_available": pacing_plan.beat_available,
        "bpm": pacing_plan.bpm,
    }
    transcript_ctx = {
        "text": " ".join(c.get("text", "") for c in chunks[:10]),
        "chunk_count": len(chunks),
    }
    # Inject mode name so planners can apply mode-specific rules.
    mode_config_with_name = dict(mode_config)
    mode_config_with_name["mode_name"] = mode

    camera_plan = _safe_camera_plan(mode_config_with_name, pacing_ctx, memory_ctx, transcript_ctx, warnings)
    subtitle_plan = _safe_subtitle_plan(mode_config_with_name, pacing_ctx, memory_ctx, transcript_ctx, warnings)

    plan = AIEditPlan(
        enabled=True,
        mode=mode,
        selected_segments=selected_segments,
        subtitle=subtitle_plan,
        camera=camera_plan,
        warnings=warnings,
        fallback_used=fallback_used,
        memory_context=memory_ctx,
        pacing=pacing_plan,
    )

    # --- Phase 6: Explainability ---
    try:
        _attach_explainability(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"explainability_error:{type(exc).__name__}")
        logger.debug("ai_director_explainability_failed job_id=%s: %s", job_id, exc)

    return plan


# ---------------------------------------------------------------------------
# Phase 4 — pacing builder
# ---------------------------------------------------------------------------

def _build_pacing_plan(
    chunks: list[dict],
    context: dict,
    mode_config: dict,
    warnings: list[str],
) -> AIPacingPlan:
    """Build a pacing plan from beat analysis + emotion analysis. Never raises."""
    pacing_style = str(mode_config.get("pacing_style", "default"))
    pacing_warnings: list[str] = []

    # --- Emotion analysis ---
    emotion = "neutral"
    emotion_score = 0.0
    try:
        from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion
        emotion_result = analyze_pacing_emotion(chunks)
        emotion = str(emotion_result.get("dominant", "neutral"))
        emotion_score = float(emotion_result.get("score", 0.0))
        if emotion_result.get("warnings"):
            pacing_warnings.extend(emotion_result["warnings"])
    except Exception as exc:
        pacing_warnings.append(f"emotion_error:{type(exc).__name__}")
        logger.debug("ai_director_emotion_failed: %s", exc)

    # --- Beat analysis ---
    beat_available = False
    bpm: Optional[float] = None
    beat_count = 0
    energy_level: Optional[float] = None

    audio_path = _resolve_audio_path(context)
    if audio_path is not None:
        try:
            from app.ai.analyzers.beat_analyzer import analyze_beats
            beat_result = analyze_beats(audio_path)
            if beat_result.get("available"):
                beat_available = True
                bpm = beat_result.get("bpm")
                beat_count = len(beat_result.get("beats") or [])
                energy = beat_result.get("energy") or {}
                energy_level = energy.get("mean")
            if beat_result.get("warnings"):
                pacing_warnings.extend(beat_result["warnings"])
        except Exception as exc:
            pacing_warnings.append(f"beat_error:{type(exc).__name__}")
            logger.debug("ai_director_beat_failed: %s", exc)
    else:
        pacing_warnings.append("beat_analysis_unavailable")

    suggested_cut_style = _suggest_cut_style(bpm, pacing_style)

    return AIPacingPlan(
        beat_available=beat_available,
        bpm=bpm,
        beat_count=beat_count,
        energy_level=energy_level,
        pacing_style=pacing_style,
        emotion=emotion,
        emotion_score=emotion_score,
        suggested_cut_style=suggested_cut_style,
        warnings=pacing_warnings,
    )


def _safe_camera_plan(
    mode_config: dict,
    pacing_ctx: dict,
    memory_ctx: dict,
    transcript_ctx: dict,
    warnings: list[str],
) -> AICameraPlan:
    """Call camera_planner with a fallback to a bare AICameraPlan on failure."""
    try:
        return plan_camera_behavior(
            mode_config,
            pacing_context=pacing_ctx,
            memory_context=memory_ctx,
            transcript_context=transcript_ctx,
        )
    except Exception as exc:
        warnings.append(f"camera_planner_error:{type(exc).__name__}")
        logger.debug("ai_director_camera_planner_failed: %s", exc)
        return AICameraPlan(
            mode="auto",
            behavior=str(mode_config.get("camera_behavior") or "none"),
            subtitle_safe=True,
        )


def _safe_subtitle_plan(
    mode_config: dict,
    pacing_ctx: dict,
    memory_ctx: dict,
    transcript_ctx: dict,
    warnings: list[str],
) -> AISubtitlePlan:
    """Call subtitle_planner with a fallback to a bare AISubtitlePlan on failure."""
    try:
        return plan_subtitle_behavior(
            mode_config,
            pacing_context=pacing_ctx,
            memory_context=memory_ctx,
            transcript_context=transcript_ctx,
        )
    except Exception as exc:
        warnings.append(f"subtitle_planner_error:{type(exc).__name__}")
        logger.debug("ai_director_subtitle_planner_failed: %s", exc)
        return AISubtitlePlan(
            tone=str(mode_config.get("subtitle_tone") or "default"),
            highlight_keywords=False,
        )


def _resolve_audio_path(context: dict) -> Optional[str]:
    """Return the best available audio/video path for beat analysis."""
    for key in ("audio_path", "source_path", "video_path"):
        val = context.get(key)
        if val and str(val).strip():
            return str(val)
    return None


def _suggest_cut_style(bpm: Optional[float], pacing_style: str) -> str:
    """Map BPM or pacing_style to a cut style label."""
    if bpm is not None:
        if bpm >= 140:
            return "fast_cut"
        if bpm >= 100:
            return "medium_cut"
        return "slow_cut"
    # Fall back to mode pacing_style
    if pacing_style in ("fast",):
        return "fast_cut"
    if pacing_style in ("slow_build",):
        return "slow_cut"
    if pacing_style in ("medium",):
        return "medium_cut"
    return "standard"


# ---------------------------------------------------------------------------
# Phase 6 — Explainability attachment
# ---------------------------------------------------------------------------

def _attach_explainability(plan: "AIEditPlan", job_id: str) -> None:
    """Build and attach explainability + confidence to the plan. Never raises."""
    try:
        from app.ai.explainability.reason_builder import (
            build_clip_reasons,
            build_camera_reasons,
            build_subtitle_reasons,
            build_pacing_reasons,
        )
        from app.ai.explainability.confidence import calculate_ai_confidence
        from app.ai.explainability.summary import build_ai_summary

        clip_reasons = build_clip_reasons(plan.selected_segments, plan.memory_context)
        camera_reasons = build_camera_reasons(plan.camera, plan.pacing)
        subtitle_reasons = build_subtitle_reasons(plan.subtitle, plan.pacing)
        pacing_reasons = build_pacing_reasons(plan.pacing)

        confidence = calculate_ai_confidence(plan)
        plan.confidence = confidence

        summary = build_ai_summary(plan, confidence)
        plan.explainability = {
            "clip_reasons": clip_reasons,
            "camera_reasons": camera_reasons,
            "subtitle_reasons": subtitle_reasons,
            "pacing_reasons": pacing_reasons,
            "summary": summary,
        }

        logger.info(
            "ai_explainability_generated job_id=%s clip_reasons=%d camera_reasons=%d",
            job_id, len(clip_reasons), len(camera_reasons),
        )
        logger.info(
            "ai_confidence_generated job_id=%s overall=%s semantic=%s memory=%s pacing=%s",
            job_id,
            confidence.get("overall"),
            confidence.get("semantic"),
            confidence.get("memory"),
            confidence.get("pacing"),
        )
    except Exception as exc:
        plan.warnings.append(f"explainability_error:{type(exc).__name__}")
        logger.debug("ai_director_explainability_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Helpers (Phase 1–3)
# ---------------------------------------------------------------------------

def _build_rag_query(mode: str, chunks: list[dict], context: dict) -> str:
    """Build a short search query for the RAG retriever."""
    market = str(context.get("market") or "")
    duration = context.get("duration") or 0
    first_text = chunks[0].get("text", "") if chunks else ""
    parts = [f"mode:{mode}"]
    if market:
        parts.append(f"market:{market}")
    if duration:
        parts.append(f"duration:{int(duration)}s")
    if first_text:
        parts.append(first_text[:80])
    return " ".join(parts)


def _resolve_transcript_chunks(context: dict, warnings: list[str]) -> list[dict]:
    """Try transcript sources in priority order. Returns [] if none work."""
    if context.get("transcript_chunks"):
        return list(context["transcript_chunks"])

    if context.get("transcript_blocks"):
        chunks = normalize_transcript_chunks(context["transcript_blocks"])
        if chunks:
            return chunks

    if context.get("subtitle_blocks"):
        chunks = normalize_transcript_chunks(context["subtitle_blocks"])
        if chunks:
            return chunks

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
