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

    # --- Phase 12: Story Intelligence ---
    try:
        _attach_story_intelligence(plan, chunks, pacing_ctx, memory_ctx, job_id)
    except Exception as exc:
        plan.warnings.append(f"story_error:{type(exc).__name__}")
        logger.debug("ai_director_story_failed job_id=%s: %s", job_id, exc)

    # --- Phase 13: Smart Preset Evolution ---
    try:
        _attach_preset_evolution(plan, memory_ctx, mode, context, job_id)
    except Exception as exc:
        plan.warnings.append(f"preset_evolution_error:{type(exc).__name__}")
        logger.debug("ai_director_preset_evolution_failed job_id=%s: %s", job_id, exc)

    # --- Phase 14: Creator Style Intelligence ---
    try:
        _attach_creator_style(plan, chunks, pacing_ctx, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_style_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_style_failed job_id=%s: %s", job_id, exc)

    # --- Phase 15: External Knowledge ---
    try:
        _attach_external_knowledge(plan, chunks, pacing_ctx, context, mode, job_id)
    except Exception as exc:
        plan.warnings.append(f"external_knowledge_error:{type(exc).__name__}")
        logger.debug("ai_director_external_knowledge_failed job_id=%s: %s", job_id, exc)

    # --- Phase 16: Retention Intelligence ---
    try:
        _attach_retention_intelligence(plan, chunks, pacing_ctx, job_id)
    except Exception as exc:
        plan.warnings.append(f"retention_error:{type(exc).__name__}")
        logger.debug("ai_director_retention_failed job_id=%s: %s", job_id, exc)

    # --- Phase 17: Dynamic Subtitle Execution ---
    try:
        _attach_subtitle_execution(plan, chunks, pacing_ctx, job_id)
    except Exception as exc:
        plan.warnings.append(f"subtitle_execution_error:{type(exc).__name__}")
        logger.debug("ai_director_subtitle_execution_failed job_id=%s: %s", job_id, exc)

    # --- Phase 18: Beat-synced Visual Execution ---
    try:
        _attach_beat_visual_execution(plan, pacing_ctx, job_id)
    except Exception as exc:
        plan.warnings.append(f"beat_visual_execution_error:{type(exc).__name__}")
        logger.debug("ai_director_beat_visual_execution_failed job_id=%s: %s", job_id, exc)

    # --- Phase 19: Retention-driven Timing Mutation ---
    try:
        timing_enabled = bool(getattr(request, "ai_timing_mutation_enabled", False))
        _attach_timing_mutation(plan, chunks, pacing_ctx, timing_enabled, job_id)
    except Exception as exc:
        plan.warnings.append(f"timing_mutation_error:{type(exc).__name__}")
        logger.debug("ai_director_timing_mutation_failed job_id=%s: %s", job_id, exc)

    # --- Phase 20: Story-driven Edit Optimization ---
    try:
        _attach_story_optimization(plan, chunks, pacing_ctx, job_id)
    except Exception as exc:
        plan.warnings.append(f"story_optimization_error:{type(exc).__name__}")
        logger.debug("ai_director_story_optimization_failed job_id=%s: %s", job_id, exc)

    # --- Phase 21: Safe Autonomous Variant Rendering ---
    try:
        variant_enabled = bool(getattr(request, "ai_variant_planning_enabled", False))
        if variant_enabled:
            raw_count = getattr(request, "ai_variant_count", 3)
            _attach_variant_plans(plan, raw_count, job_id)
    except Exception as exc:
        plan.warnings.append(f"variant_planning_error:{type(exc).__name__}")
        logger.debug("ai_director_variant_planning_failed job_id=%s: %s", job_id, exc)

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
# Phase 12 — Story intelligence attachment
# ---------------------------------------------------------------------------

def _attach_story_intelligence(
    plan: "AIEditPlan",
    chunks: list[dict],
    pacing_ctx: dict,
    memory_ctx: dict,
    job_id: str,
) -> None:
    """Run story structure analysis and attach results to the plan. Never raises."""
    try:
        from app.ai.story.story_analyzer import analyze_story_structure

        story = analyze_story_structure(
            transcript_chunks=chunks,
            pacing_context=pacing_ctx,
            emotion_context=None,
            memory_context=memory_ctx or None,
        )
        plan.story = story.to_dict()

        logger.info(
            "ai_story_analysis_generated job_id=%s flow=%s arc=%s retention=%.1f segments=%d",
            job_id,
            story.narrative_flow,
            story.dominant_arc,
            story.retention_score,
            len(story.segments),
        )

        # Attach compact explainability notes when summary exists
        _append_story_explainability(plan, story)

    except Exception as exc:
        plan.warnings.append(f"story_error:{type(exc).__name__}")
        logger.debug("ai_director_story_failed job_id=%s: %s", job_id, exc)


def _append_story_explainability(plan: "AIEditPlan", story: Any) -> None:
    """Append compact story insight lines to plan.explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        types = {s.segment_type for s in story.segments}

        if "hook" in types:
            lines.append("Strong opening hook detected")
        if "climax" in types:
            lines.append("Narrative climax identified")
        elif "tension" in types:
            lines.append("Narrative tension peak identified")
        if "build_up" in types and "climax" not in types:
            lines.append("Narrative build-up identified")
        outro_segs = [s for s in story.segments if s.segment_type == "outro"]
        if any((s.retention_risk or 0) > 0.5 for s in outro_segs):
            lines.append("Retention pacing weakened near ending")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 13 — Smart Preset Evolution attachment
# ---------------------------------------------------------------------------

def _attach_preset_evolution(
    plan: "AIEditPlan",
    memory_ctx: dict,
    mode: str,
    context: dict,
    job_id: str,
) -> None:
    """Run preset performance analysis and attach results to the plan. Never raises."""
    try:
        from app.ai.presets.preset_analyzer import analyze_preset_performance
        from app.ai.presets.preset_recommender import recommend_preset

        market = str(context.get("market") or "").strip() or None
        memories = memory_ctx.get("results", []) if isinstance(memory_ctx, dict) else []

        if not memories:
            plan.preset_evolution = {
                "available": False,
                "warnings": ["no_memory_available_for_preset_analysis"],
            }
            logger.debug("ai_preset_evolution_skipped job_id=%s (no memories)", job_id)
            return

        preset_context = {"market": market, "mode": mode}
        report = analyze_preset_performance(memories, context=preset_context)

        if report.available:
            rec = recommend_preset(report, current_context=preset_context)
            report.recommendation = rec

        plan.preset_evolution = report.to_dict()

        logger.info(
            "ai_preset_evolution_generated job_id=%s market=%s mode=%s available=%s confidence=%s",
            job_id,
            market or "none",
            mode,
            report.available,
            report.recommendation.confidence if report.recommendation else 0,
        )

        _append_preset_explainability(plan, report)

    except Exception as exc:
        plan.preset_evolution = {
            "available": False,
            "warnings": [f"preset_evolution_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_preset_evolution_failed job_id=%s: %s", job_id, exc)


def _append_preset_explainability(plan: "AIEditPlan", report: Any) -> None:
    """Append compact preset insight lines to plan.explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        rec = report.recommendation
        if rec is None or not report.available:
            return

        if rec.confidence >= 30.0:
            if not any("Preset recommendation" in str(l) for l in lines):
                lines.append("Preset recommendation based on similar successful renders")
            if rec.suggested_adjustments.get("subtitle_tone"):
                if not any("Subtitle tone" in str(l) for l in lines):
                    lines.append("Subtitle tone suggestion learned from prior high-score outputs")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 14 — Creator Style Intelligence attachment
# ---------------------------------------------------------------------------

def _attach_creator_style(
    plan: "AIEditPlan",
    chunks: list[dict],
    pacing_ctx: dict,
    job_id: str,
) -> None:
    """Classify creator style and attach result + recommendation to plan. Never raises."""
    try:
        from app.ai.styles.style_classifier import classify_creator_style
        from app.ai.styles.style_recommender import recommend_style_adjustments

        # Build transcript context from chunks
        transcript_ctx = {
            "text": " ".join(c.get("text", "") for c in chunks[:15] if isinstance(c, dict)),
            "chunk_count": len(chunks),
        }

        # Story context from plan.story (may be empty dict if story analysis not run)
        story_ctx = dict(plan.story) if isinstance(plan.story, dict) else {}

        classification = classify_creator_style(
            transcript_context=transcript_ctx,
            pacing_context=pacing_ctx,
            story_context=story_ctx,
        )

        recommendation = recommend_style_adjustments(
            classification,
            current_context={"mode": plan.mode},
        )

        plan.creator_style = {
            **classification.to_dict(),
            "recommendation": recommendation.to_dict(),
        }

        logger.info(
            "ai_creator_style_classified job_id=%s style=%s confidence=%.1f",
            job_id,
            classification.dominant_style,
            classification.confidence,
        )

        _append_style_explainability(plan, classification)

    except Exception as exc:
        plan.creator_style = {
            "available": False,
            "warnings": [f"creator_style_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_style_failed job_id=%s: %s", job_id, exc)


def _append_style_explainability(plan: "AIEditPlan", classification: Any) -> None:
    """Append compact creator style insight lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        style = getattr(classification, "dominant_style", "unknown")
        if style == "unknown" or not getattr(classification, "available", False):
            return

        _STYLE_LINES: dict[str, str] = {
            "podcast_viral": "Podcast-style pacing identified",
            "high_energy_reaction": "High-energy reaction editing archetype detected",
            "storytelling_cinematic": "Cinematic storytelling structure recognized",
            "documentary_clean": "Documentary clean style identified",
            "educational_focus": "Educational focus editing style detected",
            "anime_edit": "High-energy anime edit style identified",
            "gameplay_highlight": "Gameplay highlight editing style detected",
            "motivation_short": "Motivation short-form style identified",
            "interview_clip": "Interview clip editing style recognized",
            "calm_minimal": "Calm minimal editing style identified",
        }

        line = _STYLE_LINES.get(style)
        if line and not any(line in str(l) for l in lines):
            lines.append(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 16 — Retention Intelligence attachment
# ---------------------------------------------------------------------------

def _attach_retention_intelligence(
    plan: "AIEditPlan",
    chunks: list[dict],
    pacing_ctx: dict,
    job_id: str,
) -> None:
    """Run retention analysis and attach compact summary to plan. Never raises."""
    try:
        from app.ai.retention.retention_analyzer import analyze_retention
        from app.ai.retention.retention_recommender import build_retention_recommendations

        # Build subtitle context from plan.subtitle (safe attribute access)
        subtitle_ctx = {
            "density": getattr(plan.subtitle, "density", "normal"),
            "max_words_per_line": getattr(plan.subtitle, "max_words_per_line", None),
            "tone": getattr(plan.subtitle, "tone", "default"),
        }

        # Build beat context from plan.pacing
        beat_ctx = {
            "beat_available": getattr(plan.pacing, "beat_available", False),
            "bpm": getattr(plan.pacing, "bpm", None),
            "energy_level": getattr(plan.pacing, "energy_level", None),
        }

        # Story context from Phase 12 (may be empty dict)
        story_ctx = dict(plan.story) if isinstance(plan.story, dict) else {}

        # Memory context from Phase 3
        memory_ctx = dict(plan.memory_context) if isinstance(plan.memory_context, dict) else {}

        analysis = analyze_retention(
            transcript_chunks=chunks,
            pacing_context=pacing_ctx,
            story_context=story_ctx,
            subtitle_context=subtitle_ctx,
            beat_context=beat_ctx,
            memory_context=memory_ctx,
        )

        recommendations = build_retention_recommendations(analysis)

        plan.retention = {
            "available": analysis.available,
            "overall_retention_score": round(analysis.overall_retention_score),
            "risk_regions": [r.to_dict() for r in analysis.risk_regions[:10]],
            "strengths": list(analysis.strengths[:6]),
            "recommendations": [r.to_dict() for r in recommendations[:6]],
            "warnings": list(analysis.warnings),
        }

        logger.info(
            "ai_retention_analysis_generated job_id=%s score=%d risks=%d strengths=%d",
            job_id,
            round(analysis.overall_retention_score),
            len(analysis.risk_regions),
            len(analysis.strengths),
        )

        if analysis.risk_regions:
            logger.info(
                "ai_retention_risks_detected job_id=%s categories=%s",
                job_id,
                ",".join(r.category for r in analysis.risk_regions[:5]),
            )

        _append_retention_explainability(plan, analysis)

    except Exception as exc:
        plan.retention = {
            "available": False,
            "warnings": [f"retention_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_retention_failed job_id=%s: %s", job_id, exc)


def _append_retention_explainability(plan: "AIEditPlan", analysis: Any) -> None:
    """Append compact retention insight lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        _RISK_LINES: dict[str, str] = {
            "weak_hook": "Weak opening hook may increase early dropout",
            "long_setup": "Retention risk detected in long setup",
            "pacing_decay": "Pacing decay may reduce viewer retention",
            "silence_gap": "Silence gaps may interrupt viewer flow",
            "subtitle_overload": "Subtitle density may weaken retention",
            "story_drop": "Unclear narrative may reduce engagement",
            "unclear_payoff": "Unclear payoff may reduce viewer satisfaction",
        }

        # Risk-based lines — up to 2 most severe
        seen: set[str] = set()
        risk_regions = getattr(analysis, "risk_regions", [])
        for region in risk_regions[:3]:
            cat = getattr(region, "category", "")
            if cat in seen:
                continue
            seen.add(cat)
            line = _RISK_LINES.get(cat)
            if line and not any(line in str(l) for l in lines):
                lines.append(line)

        # Strength-based lines
        strengths = getattr(analysis, "strengths", [])
        if "strong opening hook" in strengths:
            line = "Strong hook supports early retention"
            if not any(line in str(l) for l in lines):
                lines.append(line)
        if "high pacing energy" in strengths:
            line = "High pacing energy supports viewer engagement"
            if not any(line in str(l) for l in lines):
                lines.append(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 15 — External Knowledge attachment
# ---------------------------------------------------------------------------

def _attach_external_knowledge(
    plan: "AIEditPlan",
    chunks: list[dict],
    pacing_ctx: dict,
    context: dict,
    mode: str,
    job_id: str,
) -> None:
    """Retrieve external curated knowledge and attach compact summary. Never raises."""
    try:
        context = context or {}
        knowledge_store = context.get("knowledge_store")

        if knowledge_store is None:
            plan.external_knowledge = {
                "available": False,
                "warnings": ["no_knowledge_store"],
            }
            logger.debug("ai_external_knowledge_skipped job_id=%s (no store)", job_id)
            return

        from app.ai.knowledge.knowledge_retriever import retrieve_external_knowledge

        market = str(context.get("market") or "").strip() or None

        # Style hint from Phase 14 creator style (may be empty dict)
        style_hint: Optional[str] = None
        if isinstance(plan.creator_style, dict):
            raw_style = plan.creator_style.get("dominant_style")
            if raw_style and str(raw_style) not in ("unknown", ""):
                style_hint = str(raw_style)

        # Build free-text query from mode + market + transcript excerpt
        query_parts: list[str] = [mode]
        if market:
            query_parts.append(market)
        text_excerpt = " ".join(
            c.get("text", "") for c in chunks[:5] if isinstance(c, dict)
        ).strip()
        if text_excerpt:
            query_parts.append(text_excerpt[:200])
        query = " ".join(query_parts)

        retrieve_ctx = {
            "knowledge_store": knowledge_store,
            "market": market,
            "style": style_hint,
        }

        result = retrieve_external_knowledge(query, context=retrieve_ctx, top_k=5)
        plan.external_knowledge = _build_knowledge_summary(result)

        if result.get("available") and result.get("results"):
            logger.info(
                "ai_external_knowledge_matched job_id=%s matched=%d",
                job_id,
                len(result.get("results", [])),
            )
            _append_knowledge_explainability(plan, result)
        else:
            logger.debug(
                "ai_external_knowledge_skipped job_id=%s (no matches)", job_id
            )

    except Exception as exc:
        plan.external_knowledge = {
            "available": False,
            "warnings": [f"external_knowledge_error:{type(exc).__name__}"],
        }
        logger.debug(
            "ai_director_external_knowledge_failed job_id=%s: %s", job_id, exc
        )


def _build_knowledge_summary(result: dict) -> dict:
    """Convert retriever result dict to compact external_knowledge payload."""
    if not result.get("available"):
        return {
            "available": False,
            "warnings": list(result.get("warnings", [])),
        }

    raw_results = result.get("results", [])
    top_matches = []
    for r in raw_results[:5]:
        if not isinstance(r, dict):
            continue
        meta = r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {}
        top_matches.append({
            "source_type": str(meta.get("source_type", "unknown")),
            "market": meta.get("market"),
            "style": meta.get("style"),
            "score": round(float(r.get("score", 0.0)), 4),
            "text": str(r.get("text", ""))[:300],
        })

    return {
        "available": True,
        "matched_items": len(raw_results),
        "top_matches": top_matches,
    }


def _append_knowledge_explainability(plan: "AIEditPlan", result: dict) -> None:
    """Append compact knowledge insight lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        main_line = "External curated knowledge matched this edit style"
        if not any(main_line in str(l) for l in lines):
            lines.append(main_line)

        # Append market-specific hook note when a hook_pattern result is present
        for r in result.get("results", [])[:3]:
            if not isinstance(r, dict):
                continue
            meta = r.get("metadata", {}) if isinstance(r.get("metadata"), dict) else {}
            if meta.get("source_type") == "hook_pattern":
                hook_line = "Market-specific hook guidance identified"
                if not any(hook_line in str(l) for l in lines):
                    lines.append(hook_line)
                break
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 17 — Dynamic Subtitle Execution attachment
# ---------------------------------------------------------------------------

def _attach_subtitle_execution(
    plan: "AIEditPlan",
    chunks: list[dict],
    pacing_ctx: dict,
    job_id: str,
) -> None:
    """Build subtitle execution plan and attach compact summary to plan. Never raises."""
    try:
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan

        # Build context dicts from prior phase results
        story_ctx = dict(plan.story) if isinstance(plan.story, dict) else {}
        retention_ctx = dict(plan.retention) if isinstance(plan.retention, dict) else {}
        creator_ctx = dict(plan.creator_style) if isinstance(plan.creator_style, dict) else {}

        execution_plan = build_subtitle_execution_plan(
            transcript_chunks=chunks,
            pacing_context=pacing_ctx,
            emotion_context=None,
            story_context=story_ctx,
            retention_context=retention_ctx,
            creator_style_context=creator_ctx,
        )

        plan.subtitle_execution = execution_plan.to_dict()

        logger.info(
            "ai_subtitle_execution_generated job_id=%s available=%s regions=%d "
            "density=%s emotion=%s emphasis=%.3f",
            job_id,
            execution_plan.available,
            len(execution_plan.regions),
            execution_plan.global_hint.density_mode if execution_plan.global_hint else "none",
            execution_plan.global_hint.emotion_style if execution_plan.global_hint else "none",
            execution_plan.global_hint.emphasis_strength if execution_plan.global_hint else 0.0,
        )

        _append_subtitle_execution_explainability(plan, execution_plan)

    except Exception as exc:
        plan.subtitle_execution = {
            "available": False,
            "warnings": [f"subtitle_execution_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_subtitle_execution_failed job_id=%s: %s", job_id, exc)


def _append_subtitle_execution_explainability(plan: "AIEditPlan", execution_plan: Any) -> None:
    """Append compact subtitle execution insight lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        if not getattr(execution_plan, "available", False):
            return

        hint = getattr(execution_plan, "global_hint", None)
        if hint is None:
            return

        emphasis = getattr(hint, "emphasis_strength", 0.0)
        density = getattr(hint, "density_mode", "normal")
        emotion = getattr(hint, "emotion_style", "neutral")
        beat_sync = getattr(hint, "beat_sync_strength", 0.0)

        if emphasis > 0.3:
            line = "Dynamic subtitle emphasis enabled"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if emotion not in ("neutral", ""):
            line = "Emotion-aware subtitle execution detected"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if density == "compact":
            line = "Compact subtitle density recommended"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if beat_sync > 0.3:
            line = "Beat-aware subtitle emphasis enabled"
            if not any(line in str(l) for l in lines):
                lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 18 — Beat-synced Visual Execution attachment
# ---------------------------------------------------------------------------

def _attach_beat_visual_execution(
    plan: "AIEditPlan",
    pacing_ctx: dict,
    job_id: str,
) -> None:
    """Build beat visual execution plan and attach to plan. Never raises."""
    try:
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan

        # Pull context from prior phases
        beat_ctx = dict(plan.beat_execution) if isinstance(plan.beat_execution, dict) else {}
        story_ctx = dict(plan.story) if isinstance(plan.story, dict) else {}
        retention_ctx = dict(plan.retention) if isinstance(plan.retention, dict) else {}
        creator_ctx = dict(plan.creator_style) if isinstance(plan.creator_style, dict) else {}

        visual_plan = build_beat_visual_execution_plan(
            pacing_context=pacing_ctx,
            beat_execution_context=beat_ctx,
            story_context=story_ctx,
            retention_context=retention_ctx,
            creator_style_context=creator_ctx,
        )

        plan.beat_visual_execution = visual_plan.to_dict()

        logger.info(
            "ai_beat_visual_execution_generated job_id=%s available=%s "
            "bpm=%s pulse_regions=%d transition_hints=%d",
            job_id,
            visual_plan.available,
            f"{visual_plan.bpm:.1f}" if visual_plan.bpm is not None else "none",
            len(visual_plan.pulse_regions),
            len(visual_plan.transition_hints),
        )

        _append_beat_visual_explainability(plan, visual_plan)

    except Exception as exc:
        plan.beat_visual_execution = {
            "available": False,
            "warnings": [f"beat_visual_execution_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_beat_visual_execution_failed job_id=%s: %s", job_id, exc)


def _append_beat_visual_explainability(plan: "AIEditPlan", visual_plan: Any) -> None:
    """Append compact beat visual execution lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        if not getattr(visual_plan, "available", False):
            return

        pulse_regions = getattr(visual_plan, "pulse_regions", [])
        transition_hints = getattr(visual_plan, "transition_hints", [])

        # Beat pulse line
        has_punch = any(
            getattr(r, "pulse_style", "") == "punch_pulse" for r in pulse_regions
        )
        has_cinematic = any(
            getattr(r, "pulse_style", "") == "cinematic_pulse" for r in pulse_regions
        )

        if has_punch:
            line = "Beat pulse visual rhythm planned"
            if not any(line in str(l) for l in lines):
                lines.append(line)
        elif has_cinematic:
            line = "Cinematic visual rhythm planned"
            if not any(line in str(l) for l in lines):
                lines.append(line)
        elif pulse_regions:
            line = "Beat pulse visual rhythm planned"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        # Transition hints line
        high_energy_transitions = {
            r.transition_style for r in transition_hints
            if getattr(r, "transition_style", "") in ("energy_pop", "cinematic_push", "beat_pulse")
        }
        if high_energy_transitions:
            line = "High-energy visual transition hints detected"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        # Metadata-only reminder
        line = "Visual beat execution remains metadata-only"
        if not any("metadata-only" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 21 — Safe Autonomous Variant Rendering attachment
# ---------------------------------------------------------------------------

def _attach_variant_plans(
    plan: "AIEditPlan",
    count: int,
    job_id: str,
) -> None:
    """Generate advisory variant plans and attach to plan. Never raises."""
    try:
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.variants.variant_schema import clamp_variant_count

        clamped = clamp_variant_count(count)
        variant_set = generate_variant_plans(plan, context={"job_id": job_id}, count=clamped)
        plan.variants = variant_set.to_dict()

        safe_count = sum(1 for v in variant_set.variants if v.safe_to_render)
        logger.info(
            "ai_variant_plans_attached job_id=%s count=%d safe=%d recommended=%s",
            job_id,
            len(variant_set.variants),
            safe_count,
            variant_set.recommended_variant_id,
        )

        _append_variant_explainability(plan, variant_set)

    except Exception as exc:
        plan.variants = {
            "available": False,
            "warnings": [f"variant_planning_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_variant_planning_failed job_id=%s: %s", job_id, exc)


def _append_variant_explainability(plan: "AIEditPlan", variant_set: Any) -> None:
    """Append compact variant planning insight lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        if not getattr(variant_set, "available", False):
            return

        variants = getattr(variant_set, "variants", [])
        purposes = {getattr(v, "purpose", "") for v in variants}

        line = "AI variant planning prepared safe A/B options"
        if not any(line in str(l) for l in lines):
            lines.append(line)

        if "retention" in purposes:
            line = "Retention-focused variant suggested"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if "subtitle" in purposes:
            line = "Compact subtitle variant available"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if "hook" in purposes:
            line = "Hook-strengthening variant prepared"
            if not any(line in str(l) for l in lines):
                lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 20 — Story-driven Edit Optimization attachment
# ---------------------------------------------------------------------------

def _attach_story_optimization(
    plan: "AIEditPlan",
    chunks: list[dict],
    pacing_ctx: dict,
    job_id: str,
) -> None:
    """Build story optimization plan and attach compact summary to plan. Never raises."""
    try:
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan

        story_ctx = dict(plan.story) if isinstance(plan.story, dict) else {}
        retention_ctx = dict(plan.retention) if isinstance(plan.retention, dict) else {}

        opt_plan = build_story_optimization_plan(
            story_context=story_ctx,
            retention_context=retention_ctx,
            pacing_context=pacing_ctx,
            transcript_chunks=chunks,
        )

        plan.story_optimization = opt_plan.to_dict()

        logger.info(
            "ai_story_optimization_generated job_id=%s available=%s flow=%s "
            "score=%.1f issues=%d recommendations=%d",
            job_id,
            opt_plan.available,
            opt_plan.flow_type,
            opt_plan.narrative_score,
            len(opt_plan.issues),
            len(opt_plan.recommendations),
        )

        _append_story_optimization_explainability(plan, opt_plan)

    except Exception as exc:
        plan.story_optimization = {
            "available": False,
            "warnings": [f"story_optimization_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_story_optimization_failed job_id=%s: %s", job_id, exc)


def _append_story_optimization_explainability(plan: "AIEditPlan", opt_plan: Any) -> None:
    """Append compact story optimization insight lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        if not getattr(opt_plan, "available", False):
            return

        flow_type = getattr(opt_plan, "flow_type", "unknown")
        issues = getattr(opt_plan, "issues", [])
        issue_types = {getattr(i, "issue_type", "") for i in issues}

        # Positive flow line
        if flow_type == "hook_to_climax":
            line = "Strong hook-to-climax flow detected"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        # Issue-driven lines
        if "long_setup" in issue_types or "weak_build_up" in issue_types:
            line = "Story arc can be tightened"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if "weak_payoff" in issue_types or "abrupt_outro" in issue_types:
            line = "Payoff clarity may improve retention"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if "weak_hook" in issue_types:
            line = "Opening hook may need strengthening"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if "unclear_arc" in issue_types or "missing_climax" in issue_types:
            line = "Narrative arc needs clearer structure"
            if not any(line in str(l) for l in lines):
                lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 19 — Retention-driven Timing Mutation attachment
# ---------------------------------------------------------------------------

def _attach_timing_mutation(
    plan: "AIEditPlan",
    chunks: list[dict],
    pacing_ctx: dict,
    enabled: bool,
    job_id: str,
) -> None:
    """Build timing mutation plan and attach compact summary to plan. Never raises."""
    try:
        from app.ai.timing.timing_recommender import build_timing_mutation_plan

        retention_ctx = dict(plan.retention) if isinstance(plan.retention, dict) else {}
        story_ctx = dict(plan.story) if isinstance(plan.story, dict) else {}

        timing_plan = build_timing_mutation_plan(
            retention_context=retention_ctx,
            story_context=story_ctx,
            pacing_context=pacing_ctx,
            transcript_chunks=chunks,
            enabled=enabled,
        )

        plan.timing_mutation = timing_plan.to_dict()

        from app.ai.timing.timing_schema import _MAX_CANDIDATES
        safe_count = sum(
            1 for c in timing_plan.candidates if c.safe_to_apply
        )

        logger.info(
            "ai_timing_mutation_generated job_id=%s available=%s mode=%s "
            "candidates=%d safe=%d retention_gain=%.4f",
            job_id,
            timing_plan.available,
            timing_plan.mode,
            len(timing_plan.candidates),
            safe_count,
            timing_plan.estimated_retention_gain,
        )

        _append_timing_mutation_explainability(plan, timing_plan)

    except Exception as exc:
        plan.timing_mutation = {
            "available": False,
            "warnings": [f"timing_mutation_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_timing_mutation_failed job_id=%s: %s", job_id, exc)


def _append_timing_mutation_explainability(plan: "AIEditPlan", timing_plan: Any) -> None:
    """Append compact timing mutation insight lines to explainability. Never raises."""
    try:
        explainability = getattr(plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        if not getattr(timing_plan, "available", False):
            return

        candidates = getattr(timing_plan, "candidates", [])
        mode = getattr(timing_plan, "mode", "advisory")
        safe_candidates = [c for c in candidates if getattr(c, "safe_to_apply", False)]

        # Summarize risk categories found
        actions = {getattr(c, "action", "") for c in candidates if getattr(c, "action", "") not in ("none", "no_change")}
        if "tighten_setup" in actions:
            line = "Retention risk: setup pacing candidate identified"
            if not any(line in str(l) for l in lines):
                lines.append(line)
        if "trim_silence" in actions:
            line = "Retention risk: silence gap trim candidate identified"
            if not any(line in str(l) for l in lines):
                lines.append(line)
        if "shorten_outro" in actions:
            line = "Retention risk: outro pacing decay candidate identified"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        if mode == "advisory":
            line = "Timing mutation plan advisory-only (no segments changed)"
            if not any("advisory-only" in str(l) for l in lines):
                lines.append(line)
        elif safe_candidates:
            gain = getattr(timing_plan, "estimated_retention_gain", 0.0)
            line = f"Timing mutation plan ready ({len(safe_candidates)} safe candidate(s), est. gain={gain:.1%})"
            if not any("Timing mutation plan ready" in str(l) for l in lines):
                lines.append(line)

    except Exception:
        pass


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
