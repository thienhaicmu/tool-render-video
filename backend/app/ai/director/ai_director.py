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

    # --- Phase 31: AI Apply Policy ---
    # Runs first so downstream phases can reference the effective policy.
    try:
        _attach_ai_apply_policy(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"ai_apply_policy_error:{type(exc).__name__}")
        logger.debug("ai_director_apply_policy_failed job_id=%s: %s", job_id, exc)

    # --- Phase 32: Safe Timing Mutation Apply ---
    # Runs after policy (Phase 31) so effective policy is available.
    try:
        _attach_timing_apply(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"timing_apply_error:{type(exc).__name__}")
        logger.debug("ai_director_timing_apply_failed job_id=%s: %s", job_id, exc)

    # --- Phase 33: Subtitle Text Optimization Apply ---
    # Runs after Phase 32 (timing apply) with full policy context.
    try:
        _attach_subtitle_text_apply(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"subtitle_text_apply_error:{type(exc).__name__}")
        logger.debug("ai_director_subtitle_text_apply_failed job_id=%s: %s", job_id, exc)

    # --- Phase 34: Safe Camera Motion Apply ---
    # Runs after Phase 33 (subtitle apply) so subtitle safety metadata is available.
    try:
        _attach_camera_motion_apply(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"camera_motion_apply_error:{type(exc).__name__}")
        logger.debug("ai_director_camera_motion_apply_failed job_id=%s: %s", job_id, exc)

    # --- Phase 35: AI Clip Candidate Discovery ---
    # Runs after all prior phases so story/retention/timing/style metadata is available.
    # Discovery-only: never executes cuts, never mutates render payload or FFmpeg.
    try:
        _attach_clip_candidate_discovery(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"clip_candidate_discovery_error:{type(exc).__name__}")
        logger.debug("ai_director_clip_candidate_discovery_failed job_id=%s: %s", job_id, exc)

    # --- Phase 36: AI Clip Segment Selection ---
    # Runs after Phase 35 so candidate discovery metadata is available.
    # Selection-only: never executes renders, never mutates payload or FFmpeg.
    try:
        _attach_clip_segment_selection(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"clip_segment_selection_error:{type(exc).__name__}")
        logger.debug("ai_director_clip_segment_selection_failed job_id=%s: %s", job_id, exc)

    # --- Phase 37: AI Multi-Clip Batch Planning ---
    # Runs after Phase 36 so selected segment metadata is available.
    # Planning-only: never executes batch renders, never enqueues jobs, never mutates FFmpeg.
    try:
        _attach_clip_batch_planning(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"clip_batch_planning_error:{type(exc).__name__}")
        logger.debug("ai_director_clip_batch_planning_failed job_id=%s: %s", job_id, exc)

    # --- Phase 38: AI Feature Enhancement Integration ---
    # Runs after all other phases so all AI metadata is available for enhancement.
    # Assistive-only: enhances existing features, never replaces render engine authority.
    try:
        _attach_feature_enhancement(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"feature_enhancement_error:{type(exc).__name__}")
        logger.debug("ai_director_feature_enhancement_failed job_id=%s: %s", job_id, exc)

    # --- Phase 39: External Creator Knowledge Ingestion ---
    # Loads local-first creator knowledge registry. No internet, no scraping.
    # Knowledge-only: never mutates render payload, never overrides executor.
    try:
        _attach_creator_knowledge(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_knowledge_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_knowledge_failed job_id=%s: %s", job_id, exc)

    # --- Phase 40: Creator Pattern Extraction ---
    # Extracts structured creator intelligence patterns from ingested knowledge.
    # Extraction-only: no internet, no model training, no executor override.
    try:
        _attach_creator_patterns(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_patterns_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_patterns_failed job_id=%s: %s", job_id, exc)

    # --- Phase 41: Retrieval-Based Creator Intelligence ---
    # Retrieves creator intelligence patterns from Phase 39/40 registry.
    # Retrieval-only: assistive metadata only, no internet, no executor override.
    try:
        _attach_creator_retrieval(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_retrieval_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_retrieval_failed job_id=%s: %s", job_id, exc)

    # --- Phase 42: Adaptive Creator Intelligence ---
    # Learns creator preferences over time from edit plan signals.
    # Assistive-only: no FFmpeg, no playback_speed, no subtitle timing, no executor override.
    try:
        _attach_adaptive_creator_intelligence(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"adaptive_creator_intelligence_error:{type(exc).__name__}")
        logger.debug("ai_director_adaptive_creator_intelligence_failed job_id=%s: %s", job_id, exc)

    # --- Phase 43: Creator Feedback Loop Intelligence ---
    # Learns from creator feedback behavior (exports, selections, ignores).
    # Assistive-only: no FFmpeg, no playback_speed, no subtitle timing, no executor override.
    try:
        _attach_creator_feedback_intelligence(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_feedback_intelligence_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_feedback_intelligence_failed job_id=%s: %s", job_id, exc)

    # --- Phase 44: Market-Aware Optimization Intelligence ---
    # Optimizes rendering metadata for target platform/market.
    # Assistive-only: no FFmpeg, no playback_speed, no subtitle timing, no executor override.
    try:
        _attach_market_optimization_intelligence(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"market_optimization_intelligence_error:{type(exc).__name__}")
        logger.debug("ai_director_market_optimization_intelligence_failed job_id=%s: %s", job_id, exc)

    # --- Phase 45: AI Render Quality Evaluation (pre-render placeholder) ---
    # Actual scoring is post-render (in render_pipeline.py after outputs are ready).
    # Director only initializes the field so the schema slot is present in plan.to_dict().
    plan.render_quality_evaluation = {
        "available": True,
        "enabled": False,
        "evaluation_mode": "evaluation_only",
        "output_scores": [],
        "best_quality_output_id": "",
        "warnings": ["quality_evaluation_pending_post_render"],
    }

    # --- Phase 46: Creator Preset Evolution Intelligence ---
    # Combines creator behavior + market + feedback + quality signals.
    # Assistive-only: no FFmpeg, no playback_speed, no subtitle timing, no executor override.
    try:
        _attach_creator_preset_evolution(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_preset_evolution_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_preset_evolution_failed job_id=%s: %s", job_id, exc)

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

    # --- Phase 23: Creator Style Adaptation ---
    try:
        _attach_creator_style_adaptation(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_style_adaptation_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_style_adaptation_failed job_id=%s: %s", job_id, exc)

    # --- Phase 21: Safe Autonomous Variant Rendering ---
    try:
        variant_enabled = bool(getattr(request, "ai_variant_planning_enabled", False))
        if variant_enabled:
            raw_count = getattr(request, "ai_variant_count", 3)
            _attach_variant_plans(plan, raw_count, job_id)
    except Exception as exc:
        plan.warnings.append(f"variant_planning_error:{type(exc).__name__}")
        logger.debug("ai_director_variant_planning_failed job_id=%s: %s", job_id, exc)

    # --- Phase 22: AI Best Variant Selector ---
    try:
        variant_enabled = bool(getattr(request, "ai_variant_planning_enabled", False))
        if variant_enabled and plan.variants.get("available"):
            _attach_variant_selection(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"variant_selection_error:{type(exc).__name__}")
        logger.debug("ai_director_variant_selection_failed job_id=%s: %s", job_id, exc)

    # --- Phase 24: AI Render Decision Preview ---
    try:
        _attach_render_decision_preview(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"render_decision_preview_error:{type(exc).__name__}")
        logger.debug("ai_director_render_decision_preview_failed job_id=%s: %s", job_id, exc)

    # --- Phase 25: Safe Execution Recommendation Layer ---
    try:
        _attach_execution_recommendations(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"execution_recommendations_error:{type(exc).__name__}")
        logger.debug("ai_director_execution_recommendations_failed job_id=%s: %s", job_id, exc)

    # --- Phase 26: Execution Simulation Layer ---
    try:
        _attach_execution_simulation(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"execution_simulation_error:{type(exc).__name__}")
        logger.debug("ai_director_execution_simulation_failed job_id=%s: %s", job_id, exc)

    # --- Phase 27: Safe AI-Assisted Render Mutations ---
    try:
        _attach_safe_render_mutations(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"safe_render_mutations_error:{type(exc).__name__}")
        logger.debug("ai_director_safe_render_mutations_failed job_id=%s: %s", job_id, exc)

    # --- Phase 28: Safe Multi-Variant Render Planning ---
    try:
        _attach_multivariant_render_plans(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"multivariant_render_plans_error:{type(exc).__name__}")
        logger.debug("ai_director_multivariant_plans_failed job_id=%s: %s", job_id, exc)

    # --- Phase 29: Safe Multi-Variant Render Execution ---
    try:
        _attach_multivariant_execution(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"multivariant_execution_error:{type(exc).__name__}")
        logger.debug("ai_director_multivariant_execution_failed job_id=%s: %s", job_id, exc)

    # --- Phase 30: AI Output Ranking placeholder ---
    # Actual ranking occurs post-render in render_pipeline.py when outputs exist.
    # This block attaches an empty placeholder so the field is always present.
    try:
        plan.output_ranking = {
            "available": False,
            "mode": "recommendation_only",
            "outputs": [],
            "best_output_id": None,
            "best_output_path": "",
            "warnings": ["ranking_deferred_until_render_completion"],
        }
    except Exception as exc:
        plan.warnings.append(f"output_ranking_placeholder_error:{type(exc).__name__}")
        logger.debug("ai_director_output_ranking_placeholder_failed job_id=%s: %s", job_id, exc)

    # --- Phase 47: Multi-Signal AI Render Orchestrator ---
    # Runs last: all Phase 41–46 signals and Phase 23 style adaptation are populated.
    # Reasoning-only: no render mutation, no executor override, no FFmpeg.
    try:
        _attach_multi_signal_orchestration(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"multi_signal_orchestration_error:{type(exc).__name__}")
        logger.debug("ai_director_multi_signal_orchestration_failed job_id=%s: %s", job_id, exc)

    # --- Phase 48: Safe Controlled Influence Engine ---
    # Runs after Phase 47: consumes multi_signal_orchestration output.
    # Safe influence only: no render mutation, no executor override, no FFmpeg.
    try:
        _attach_safe_influence_pack(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"safe_influence_pack_error:{type(exc).__name__}")
        logger.debug("ai_director_safe_influence_pack_failed job_id=%s: %s", job_id, exc)

    # --- Phase 50A: Deep Subtitle Preference Intelligence ---
    # Runs after Phase 48: all subtitle/influence/orchestration signals are populated.
    # Inference-only: no render mutation, no subtitle engine rewrite, no executor override.
    try:
        _attach_creator_subtitle_preference(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_subtitle_preference_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_subtitle_preference_failed job_id=%s: %s", job_id, exc)

    # --- Phase 50B: Creator Camera Preference Intelligence ---
    # Runs after Phase 50A: all camera/influence/orchestration signals are populated.
    # Inference-only metadata: no motion_crop rewrite, no tracking rewrite, no FFmpeg mutation.
    try:
        _attach_creator_camera_preference(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_camera_preference_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_camera_preference_failed job_id=%s: %s", job_id, exc)

    # --- Phase 50C: Subtitle Preference Safe Influence ---
    # Runs after Phase 50A: uses creator_subtitle_preference as input.
    # Produces bounded subtitle tuning recommendations — no subtitle engine rewrite,
    # no ASS generation rewrite, no timing rewrite, no FFmpeg mutation.
    try:
        _attach_creator_subtitle_influence(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_subtitle_influence_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_subtitle_influence_failed job_id=%s: %s", job_id, exc)

    # --- Phase 50D: Creator Preference Fusion ---
    # Runs after Phase 50A/B/C: fuses all creator intelligence into one unified profile.
    # Advisory metadata only — no render mutation, no executor override.
    try:
        _attach_creator_preference_profile(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"creator_preference_profile_error:{type(exc).__name__}")
        logger.debug("ai_director_creator_preference_profile_failed job_id=%s: %s", job_id, exc)

    # --- Phase 51A: Safe Strategy Variant Generator ---
    # Runs after Phase 50D: generates candidate strategy variants from the unified
    # creator preference profile, market intelligence, and quality evaluation.
    # Candidate-only — no evaluation, no selection, no execution applied.
    try:
        _attach_strategy_variants(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"strategy_variants_error:{type(exc).__name__}")
        logger.debug("ai_director_strategy_variants_failed job_id=%s: %s", job_id, exc)

    # --- Phase 51B: Variant Evaluation Engine ---
    # Runs after Phase 51A: scores and ranks the generated strategy variants.
    # Evaluation-only — best_variant_id is metadata advisory, never applied to render.
    try:
        _attach_variant_evaluation(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"variant_evaluation_error:{type(exc).__name__}")
        logger.debug("ai_director_variant_evaluation_failed job_id=%s: %s", job_id, exc)

    # --- Phase 51C: Best Strategy Reasoning ---
    # Runs after Phase 51B: explains why the best evaluated variant was selected.
    # Reasoning-only — never applied to render, no executor override.
    try:
        _attach_best_strategy_reasoning(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"best_strategy_reasoning_error:{type(exc).__name__}")
        logger.debug("ai_director_best_strategy_reasoning_failed job_id=%s: %s", job_id, exc)

    # --- Phase 52A: Subtitle Quality Intelligence v2 ---
    # Runs after Phase 51C: all subtitle, creator preference, and market signals are available.
    # Evaluation-only — no subtitle mutation, no timing rewrite, no ASS rewrite,
    # no FFmpeg mutation, no render pipeline rewrite, no executor override.
    try:
        _attach_subtitle_quality_v2(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"subtitle_quality_v2_error:{type(exc).__name__}")
        logger.debug("ai_director_subtitle_quality_v2_failed job_id=%s: %s", job_id, exc)

    # --- Phase 52B: Camera Quality Intelligence v2 ---
    # Runs after Phase 52A: all camera, creator preference, and market signals are available.
    # Evaluation-only — no motion_crop rewrite, no tracking rewrite, no scene detection
    # mutation, no FFmpeg mutation, no render pipeline rewrite, no executor override.
    try:
        _attach_camera_quality_v2(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"camera_quality_v2_error:{type(exc).__name__}")
        logger.debug("ai_director_camera_quality_v2_failed job_id=%s: %s", job_id, exc)

    # --- Phase 52C: Hook Quality Intelligence v2 ---
    # Runs after Phase 52B: all story, retention, pacing, market, and creator signals available.
    # Evaluation-only — no hook rewriting, no clip rewrite, no render mutation,
    # no FFmpeg mutation, no render pipeline rewrite, no executor override.
    try:
        _attach_hook_quality_v2(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"hook_quality_v2_error:{type(exc).__name__}")
        logger.debug("ai_director_hook_quality_v2_failed job_id=%s: %s", job_id, exc)

    # --- Phase 52D: Unified Quality Score v2 ---
    # Runs last in the 52-series: fuses subtitle_quality_v2, camera_quality_v2,
    # hook_quality_v2, creator/market/strategy signals into one render_quality_v2 score.
    # Evaluation-only — no render mutation, no executor override, no autonomous execution.
    try:
        _attach_unified_quality_v2(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"render_quality_v2_error:{type(exc).__name__}")
        logger.debug("ai_director_unified_quality_v2_failed job_id=%s: %s", job_id, exc)

    # --- Phase 53A: Knowledge Injection Foundation ---
    # Runs after Phase 52D: builds knowledge context from active quality signals.
    # Advisory only — no render mutation, no executor override, no autonomous execution.
    try:
        _attach_knowledge_injection(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"knowledge_injection_error:{type(exc).__name__}")
        logger.debug("ai_director_knowledge_injection_failed job_id=%s: %s", job_id, exc)

    # --- Phase 53E: Knowledge-Aware Render Reasoning ---
    # Runs after Phase 53A: routes subtitle/camera/hook knowledge retrievers from quality
    # signals and assembles a cross-domain advisory reasoning context.
    # Advisory only — no render mutation, no executor override, no autonomous execution.
    try:
        _attach_knowledge_reasoning_context(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"knowledge_reasoning_context_error:{type(exc).__name__}")
        logger.debug("ai_director_knowledge_reasoning_context_failed job_id=%s: %s", job_id, exc)

    # --- Phase 54: Knowledge-Aware Influence Upgrade ---
    # Runs after Phase 53E: reads knowledge_reasoning_context, builds per-domain influence
    # support context with bounded confidence deltas, and enriches existing influence
    # reasoning for subtitle, camera, and ranking domains.
    # Advisory only — confidence_delta is metadata only, never fed to safety gate.
    # Safety gates are NEVER lowered or bypassed by knowledge.
    try:
        _attach_knowledge_influence_context(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"knowledge_influence_context_error:{type(exc).__name__}")
        logger.debug("ai_director_knowledge_influence_context_failed job_id=%s: %s", job_id, exc)

    # --- Phase 55A: Platform Knowledge Foundation ---
    # Runs after Phase 54: reads platform/creator_type from request, retrieves
    # matching platform knowledge packs, and attaches advisory platform_context.
    # Foundation only — no influence mutation, no render execution change.
    # Advisory only — platform_context is metadata, never alters render parameters.
    try:
        _attach_platform_context(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"platform_context_error:{type(exc).__name__}")
        logger.debug("ai_director_platform_context_failed job_id=%s: %s", job_id, exc)

    # --- Phase 55B: Platform Subtitle Intelligence ---
    # Runs after Phase 55A: retrieves subtitle-specific platform knowledge and
    # attaches advisory platform_subtitle_context to the plan.
    # Advisory only — no subtitle timing rewrite, no ASS rewrite, no segmentation.
    try:
        _attach_platform_subtitle_context(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"platform_subtitle_context_error:{type(exc).__name__}")
        logger.debug("ai_director_platform_subtitle_context_failed job_id=%s: %s", job_id, exc)

    # --- Phase 55C: Platform Camera Intelligence ---
    # Runs after Phase 55B: retrieves camera-specific platform knowledge and
    # attaches advisory platform_camera_context to the plan.
    # Advisory only — no motion_crop rewrite, no tracking config change, no FFmpeg mutation.
    try:
        _attach_platform_camera_context(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"platform_camera_context_error:{type(exc).__name__}")
        logger.debug("ai_director_platform_camera_context_failed job_id=%s: %s", job_id, exc)

    # --- Phase 55D: Platform Hook & Retention Intelligence ---
    # Runs after Phase 55C: retrieves hook/retention-specific platform knowledge and
    # attaches advisory platform_hook_context to the plan.
    # Advisory only — no transcript rewrite, no hook text rewrite, no clip boundary change.
    try:
        _attach_platform_hook_context(plan, request, job_id)
    except Exception as exc:
        plan.warnings.append(f"platform_hook_context_error:{type(exc).__name__}")
        logger.debug("ai_director_platform_hook_context_failed job_id=%s: %s", job_id, exc)

    # --- Phase 55E: Platform-Aware Render Strategy ---
    # Runs after Phase 55D: fuses platform subtitle, camera, and hook intelligence
    # into one deterministic advisory platform render strategy.
    # Advisory only — no render execution, no executor override, no pipeline mutation.
    try:
        _attach_platform_render_strategy(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"platform_render_strategy_error:{type(exc).__name__}")
        logger.debug("ai_director_platform_render_strategy_failed job_id=%s: %s", job_id, exc)

    # --- Phase 56: Platform-Aware Strategy Influence ---
    # Runs after Phase 55E: reads platform_render_strategy, builds per-domain
    # influence support (subtitle, camera, ranking) with bounded confidence deltas,
    # and enriches existing influence reasoning (additive only).
    # Advisory only — confidence_delta is metadata only, NEVER fed to safety gate.
    # Safety gates are NEVER lowered or bypassed. No render mutation.
    try:
        _attach_platform_strategy_influence(plan, job_id)
    except Exception as exc:
        plan.warnings.append(f"platform_strategy_influence_error:{type(exc).__name__}")
        logger.debug("ai_director_platform_strategy_influence_failed job_id=%s: %s", job_id, exc)

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
# Phase 22 — AI Best Variant Selector attachment
# ---------------------------------------------------------------------------

def _attach_variant_selection(plan: "AIEditPlan", job_id: str) -> None:
    """Run best variant selector and attach compact result to plan. Never raises."""
    try:
        from app.ai.variants.variant_selector import select_best_variant

        selection = select_best_variant(plan.variants, edit_plan=plan, context={"job_id": job_id})

        # Store only the compact fields — never store full variant content again
        plan.variant_selection = {
            "selected_variant_id": selection.get("selected_variant_id"),
            "selection_confidence": selection.get("selection_confidence", 0.0),
            "selection_reasons": list(selection.get("selection_reasons") or []),
            "fallback_used": bool(selection.get("fallback_used", False)),
            "rejected_count": len(selection.get("rejected_variants") or []),
        }

        logger.info(
            "ai_variant_selection_attached job_id=%s selected=%s confidence=%.4f fallback=%s",
            job_id,
            selection.get("selected_variant_id"),
            selection.get("selection_confidence", 0.0),
            selection.get("fallback_used", False),
        )

        _append_variant_selection_explainability(plan, selection)

    except Exception as exc:
        plan.variant_selection = {
            "available": False,
            "warnings": [f"variant_selection_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_variant_selection_failed job_id=%s: %s", job_id, exc)


def _append_variant_selection_explainability(plan: "AIEditPlan", selection: dict) -> None:
    """Append compact variant selection insight lines to explainability. Never raises."""
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

        fallback = selection.get("fallback_used", False)
        reasons = selection.get("selection_reasons") or []

        if fallback:
            line = "Safe baseline retained due to low confidence"
            if not any(line in str(l) for l in lines):
                lines.append(line)
            return

        if "retention_focused_variant_highest_score" in reasons:
            line = "AI selected retention-focused variant"
        elif "hook_strengthening_variant_highest_score" in reasons:
            line = "AI selected hook-strengthening variant"
        elif "creator_style_match_variant_highest_score" in reasons:
            line = "Creator-style variant scored highest"
        elif "story_coherence_variant_highest_score" in reasons:
            line = "Story coherence variant selected"
        elif "subtitle_optimization_variant_highest_score" in reasons:
            line = "Compact subtitle variant selected"
        else:
            line = "AI variant selection complete"

        if not any(line in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 24 — AI Render Decision Preview attachment
# ---------------------------------------------------------------------------

def _attach_render_decision_preview(plan: "AIEditPlan", job_id: str) -> None:
    """Build and attach a compact advisory render decision preview to the plan.

    Runs after all prior phases (Phases 21-23) so the preview can aggregate
    the full set of AI metadata. Never raises. Never mutates render payload.
    Advisory metadata only.
    """
    if plan is None:
        return
    try:
        from app.ai.preview.decision_preview import build_render_decision_preview

        preview_dict = build_render_decision_preview(plan, context={"job_id": job_id})
        plan.render_decision_preview = preview_dict

        safety = preview_dict.get("safety_report", {})
        logger.info(
            "ai_render_decision_preview_created job_id=%s status=%s confidence=%.4f "
            "actions=%d blocked=%d",
            job_id,
            preview_dict.get("safety_status", "unknown"),
            float(preview_dict.get("confidence", 0.0)),
            len(preview_dict.get("recommended_actions", [])),
            len(preview_dict.get("blocked_actions", [])),
        )

        _append_render_decision_preview_explainability(plan, preview_dict)

    except Exception as exc:
        plan.render_decision_preview = {
            "available": False,
            "mode": "advisory",
            "safety_status": "unavailable",
            "warnings": [f"render_decision_preview_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_render_decision_preview_failed job_id=%s: %s", job_id, exc)


def _append_render_decision_preview_explainability(
    plan: "AIEditPlan",
    preview_dict: dict,
) -> None:
    """Append compact preview insight lines to explainability. Never raises."""
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

        if not any("AI render decision preview" in str(l) for l in lines):
            lines.append("AI render decision preview prepared")

        selected = preview_dict.get("selected_variant_id")
        if selected:
            purpose = ""
            for v in (plan.variants.get("variants") or []):
                if isinstance(v, dict) and str(v.get("variant_id")) == str(selected):
                    purpose = str(v.get("purpose") or "")
                    break
            if purpose:
                line = f"Selected advisory variant summarized ({purpose.replace('_', ' ')})"
            else:
                line = "Selected advisory variant summarized"
            if not any("advisory variant summarized" in str(l) for l in lines):
                lines.append(line)

        if not any("Autonomous render actions remain blocked" in str(l) for l in lines):
            lines.append("Autonomous render actions remain blocked")

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 27 — Safe AI-Assisted Render Mutations attachment
# ---------------------------------------------------------------------------

def _attach_safe_render_mutations(plan: "AIEditPlan", job_id: str) -> None:
    """Build and attach bounded safe render mutation pack to the plan.

    Runs after Phase 26 (execution simulation) so mutations have full AI
    context. Applies only bounded AI guidance metadata changes. Never
    mutates FFmpeg commands, render timings, segment structure, or subtitle
    timestamps. Never raises. Never blocks render.
    """
    if plan is None:
        return
    try:
        from app.ai.mutations.mutation_engine import build_safe_mutations

        pack = build_safe_mutations(plan, payload=None, context={"job_id": job_id})
        pack_dict = pack.to_dict()
        plan.safe_render_mutations = pack_dict

        applied = pack_dict.get("applied_mutation_ids") or []
        blocked = pack_dict.get("blocked_mutations") or []
        logger.info(
            "ai_safe_render_mutations_built job_id=%s applied=%d blocked=%d advisory=%s",
            job_id,
            len(applied),
            len(blocked),
            pack_dict.get("advisory_mode", True),
        )

        _append_safe_render_mutations_explainability(plan, pack_dict)

    except Exception as exc:
        plan.safe_render_mutations = {
            "available": False,
            "advisory_mode": True,
            "warnings": [f"safe_render_mutations_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_safe_render_mutations_failed job_id=%s: %s", job_id, exc)


def _append_safe_render_mutations_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact mutation insight lines to explainability. Never raises."""
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

        mutations = pack_dict.get("mutations") or []
        applied_ids = set(pack_dict.get("applied_mutation_ids") or [])

        for mut in mutations:
            if not isinstance(mut, dict) or not mut.get("applied"):
                continue
            mid = str(mut.get("mutation_id") or "")
            cat = str(mut.get("category") or "")
            if cat == "subtitle" and not any("subtitle density mutation" in str(l) for l in lines):
                lines.append("Safe subtitle density mutation applied")
            elif cat == "visual_rhythm" and not any("Visual rhythm guidance" in str(l) for l in lines):
                lines.append("Visual rhythm guidance safely adjusted")
            elif cat == "creator_style" and not any("Creator style mutation" in str(l) for l in lines):
                lines.append("Creator style mutation applied safely")
            elif cat == "pacing" and mid != "m_safe_baseline" and not any("pacing mutation" in str(l) for l in lines):
                lines.append("Safe pacing mutation applied")

        if not any("Dangerous timing mutations remain blocked" in str(l) for l in lines):
            lines.append("Dangerous timing mutations remain blocked")

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 31 — AI Apply Policy attachment
# ---------------------------------------------------------------------------

def _attach_ai_apply_policy(plan: "AIEditPlan", request: Any, job_id: str) -> None:
    """Build and attach AI apply policy decision to the plan.

    Runs early (before Phase 6 explainability) so downstream AI phases can
    reference the effective policy. Never raises. Never mutates dangerous fields.
    Hard safety blocks are never bypassed regardless of policy.
    """
    if plan is None:
        return
    try:
        from app.ai.policy.policy_engine import build_policy_decision

        raw_policy = str(getattr(request, "ai_apply_policy", "conservative") or "conservative")
        context = {"ai_apply_policy": raw_policy, "job_id": job_id}

        decision = build_policy_decision(plan, payload=request, context=context)
        decision_dict = decision.to_dict()
        plan.ai_apply_policy = decision_dict

        logger.info(
            "ai_apply_policy_selected job_id=%s policy=%s blocked=%d",
            job_id,
            decision_dict.get("selected_policy", "conservative"),
            len(decision_dict.get("blocked_capabilities") or []),
        )

        _append_ai_apply_policy_explainability(plan, decision_dict)

    except Exception as exc:
        plan.ai_apply_policy = {
            "available": False,
            "selected_policy": "conservative",
            "effective_policy": {},
            "blocked_capabilities": [],
            "warnings": [f"ai_apply_policy_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_apply_policy_failed job_id=%s: %s", job_id, exc)


def _append_ai_apply_policy_explainability(
    plan: "AIEditPlan",
    decision_dict: dict,
) -> None:
    """Append compact policy insight lines to explainability. Never raises."""
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

        policy = decision_dict.get("selected_policy") or "conservative"
        policy_label = policy.capitalize()

        line = f"{policy_label} AI apply policy enabled"
        if not any(line in str(l) for l in lines):
            lines.append(line)

        if policy in ("aggressive", "experimental"):
            line = "Aggressive orchestration remains safety-gated"
            if not any("safety-gated" in str(l) for l in lines):
                lines.append(line)

        line = "Dangerous timing mutations remain blocked"
        if not any("Dangerous timing mutations remain blocked" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 29 — Safe Multi-Variant Render Execution attachment
# ---------------------------------------------------------------------------

def _attach_multivariant_execution(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build and attach multi-variant execution set to the plan.

    Runs after Phase 28 (multi-variant planning) so execution has full
    plan metadata. Execution is opt-in only — disabled by default.
    Never raises. Never overrides executor authority.
    """
    if plan is None:
        return
    try:
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set

        execution_enabled = bool(
            getattr(request, "ai_multivariant_execution_enabled", False)
        )
        raw_limit = int(getattr(request, "ai_multivariant_execution_limit", 2) or 2)

        context = {
            "job_id": job_id,
            "ai_multivariant_execution_enabled": execution_enabled,
            "ai_multivariant_execution_limit": raw_limit,
        }

        execution_set = build_multivariant_execution_set(
            plan, payload=None, context=context
        )
        exec_dict = execution_set.to_dict()
        plan.multivariant_execution = exec_dict

        executed = exec_dict.get("executed_plan_ids") or []
        blocked = exec_dict.get("blocked_plan_ids") or []

        logger.info(
            "ai_multivariant_execution_built job_id=%s enabled=%s "
            "executed=%d blocked=%d",
            job_id, execution_enabled, len(executed), len(blocked),
        )

        _append_multivariant_execution_explainability(plan, exec_dict)

    except Exception as exc:
        plan.multivariant_execution = {
            "available": False,
            "execution_enabled": False,
            "warnings": [f"multivariant_execution_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_multivariant_execution_failed job_id=%s: %s", job_id, exc)


def _append_multivariant_execution_explainability(
    plan: "AIEditPlan",
    exec_dict: dict,
) -> None:
    """Append compact execution insight lines to explainability. Never raises."""
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

        execution_enabled = exec_dict.get("execution_enabled", False)
        executed_ids = exec_dict.get("executed_plan_ids") or []

        if execution_enabled and executed_ids:
            line = "Safe multi-variant execution enabled"
            if not any(line in str(l) for l in lines):
                lines.append(line)
            line = "Bounded render variants prepared"
            if not any("Bounded render variants" in str(l) for l in lines):
                lines.append(line)
        else:
            line = "Multi-variant execution disabled (opt-in required)"
            if not any("Multi-variant execution disabled" in str(l) for l in lines):
                lines.append(line)

        line = "Dangerous execution overrides remain blocked"
        if not any("Dangerous execution overrides" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 28 — Safe Multi-Variant Render Planning attachment
# ---------------------------------------------------------------------------

def _attach_multivariant_render_plans(plan: "AIEditPlan", job_id: str) -> None:
    """Build and attach multi-variant render planning set to the plan.

    Runs after Phase 27 (safe mutations) so plans have full mutation context.
    Mode is always planning_only. Never enqueues. Never executes. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans

        render_set = build_multivariant_render_plans(plan, payload=None, context={"job_id": job_id})
        render_set_dict = render_set.to_dict()
        plan.multivariant_render_plans = render_set_dict

        plans = render_set_dict.get("plans") or []
        safe_count = sum(1 for p in plans if p.get("safe_to_enqueue"))

        logger.info(
            "ai_multivariant_plans_built job_id=%s available=%s plans=%d "
            "safe_to_enqueue=%d recommended=%s mode=%s",
            job_id,
            render_set_dict.get("available", False),
            len(plans),
            safe_count,
            render_set_dict.get("recommended_plan_id") or "none",
            render_set_dict.get("mode", "planning_only"),
        )

        _append_multivariant_plans_explainability(plan, render_set_dict)

    except Exception as exc:
        plan.multivariant_render_plans = {
            "available": False,
            "mode": "planning_only",
            "warnings": [f"multivariant_render_plans_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_multivariant_plans_failed job_id=%s: %s", job_id, exc)


def _append_multivariant_plans_explainability(
    plan: "AIEditPlan",
    render_set_dict: dict,
) -> None:
    """Append compact multi-variant planning insight lines to explainability. Never raises."""
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

        plans = render_set_dict.get("plans") or []
        safe_plans = [p for p in plans if p.get("safe_to_enqueue")]
        recommended_id = render_set_dict.get("recommended_plan_id") or ""

        line = "Multi-variant render plans prepared"
        if not any(line in str(l) for l in lines):
            lines.append(line)

        if safe_plans and recommended_id and recommended_id != "mvplan_baseline":
            line = "Recommended variant render plan is safe to enqueue later"
            if not any("safe to enqueue" in str(l) for l in lines):
                lines.append(line)

        line = "Automatic variant rendering remains blocked"
        if not any("Automatic variant rendering" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 26 — Execution Simulation Layer attachment
# ---------------------------------------------------------------------------

def _attach_execution_simulation(plan: "AIEditPlan", job_id: str) -> None:
    """Build and attach advisory execution simulation pack to the plan.

    Runs after Phase 25 (execution recommendations) so simulation has full
    recommendation context available. Never raises. Never mutates render
    payload. Simulation metadata only.
    """
    if plan is None:
        return
    try:
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations

        pack = simulate_execution_recommendations(plan, context={"job_id": job_id})
        pack_dict = pack.to_dict()
        plan.execution_simulation = pack_dict

        logger.info(
            "ai_execution_simulation_created job_id=%s available=%s "
            "count=%d recommended=%s",
            job_id,
            pack_dict.get("available", False),
            len(pack_dict.get("simulations", [])),
            pack_dict.get("recommended_simulation_id") or "none",
        )

        _append_execution_simulation_explainability(plan, pack_dict)

    except Exception as exc:
        plan.execution_simulation = {
            "available": False,
            "mode": "simulation_only",
            "warnings": [f"execution_simulation_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_execution_simulation_failed job_id=%s: %s", job_id, exc)


def _append_execution_simulation_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact simulation insight lines to explainability. Never raises."""
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

        sims = pack_dict.get("simulations") or []
        recommended_id = pack_dict.get("recommended_simulation_id") or ""

        # Identify highest-gain simulation
        max_ret_gain = max(
            (float(s.get("estimated_retention_gain") or 0) for s in sims if isinstance(s, dict)),
            default=0.0,
        )
        max_subtitle_gain = max(
            (float(s.get("estimated_subtitle_clarity_gain") or 0) for s in sims if isinstance(s, dict)),
            default=0.0,
        )

        if not any("Execution simulation" in str(l) for l in lines):
            if max_ret_gain > 5:
                lines.append(
                    f"Execution simulation estimated retention improvement (+{max_ret_gain:.1f})"
                )
            else:
                lines.append("Execution simulation prepared (advisory metadata only)")

        if max_subtitle_gain > 0 and not any("Subtitle clarity simulation" in str(l) for l in lines):
            lines.append("Subtitle clarity simulation available")

        if not any("Simulation remains advisory" in str(l) for l in lines):
            lines.append("Simulation remains advisory-only")

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 25 — Safe Execution Recommendation Layer attachment
# ---------------------------------------------------------------------------

def _attach_execution_recommendations(plan: "AIEditPlan", job_id: str) -> None:
    """Build and attach advisory execution recommendation pack to the plan.

    Runs after Phase 24 so all prior AI metadata is available for aggregation.
    Never raises. Never mutates render payload. Advisory metadata only.
    """
    if plan is None:
        return
    try:
        from app.ai.execution.execution_recommendation import build_execution_recommendations

        pack = build_execution_recommendations(plan, context={"job_id": job_id})
        pack_dict = pack.to_dict()
        plan.execution_recommendations = pack_dict

        logger.info(
            "ai_execution_recommendations_created job_id=%s available=%s "
            "count=%d recommended=%s",
            job_id,
            pack_dict.get("available", False),
            len(pack_dict.get("recommendations", [])),
            pack_dict.get("recommended_pack_id") or "none",
        )

        _append_execution_recommendations_explainability(plan, pack_dict)

    except Exception as exc:
        plan.execution_recommendations = {
            "available": False,
            "mode": "advisory",
            "warnings": [f"execution_recommendations_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_execution_recommendations_failed job_id=%s: %s", job_id, exc)


def _append_execution_recommendations_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact execution recommendation lines to explainability. Never raises."""
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

        if not any("AI execution recommendation" in str(l) for l in lines):
            lines.append("AI execution recommendation pack prepared")

        recommended_id = pack_dict.get("recommended_pack_id") or ""
        if recommended_id and recommended_id != "safe_baseline":
            if "retention" in recommended_id:
                hint = "Retention-oriented pacing recommendation available"
            elif "creator_style" in recommended_id:
                hint = "Creator-style execution recommendation available"
            elif "story" in recommended_id:
                hint = "Story-driven pacing recommendation available"
            else:
                hint = f"Execution recommendation available ({recommended_id})"
            if not any(hint in str(l) for l in lines):
                lines.append(hint)

        if not any("Autonomous execution remains blocked" in str(l) for l in lines):
            lines.append("Autonomous execution remains blocked")

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 23 — Creator Style Adaptation attachment
# ---------------------------------------------------------------------------

def _attach_creator_style_adaptation(plan: "AIEditPlan", job_id: str) -> None:
    """Detect Phase 23 creator style and build advisory adaptation hints.

    Runs after Phase 14 (creator_style) and Phase 16/20 (retention/story)
    so all prior metadata is available. Result stored in plan.creator_style_adaptation.
    Never raises. Never mutates render payload. Advisory metadata only.
    """
    try:
        from app.ai.styles.style_classifier import detect_creator_styles
        from app.ai.styles.style_adapter import build_style_adaptation

        style_set = detect_creator_styles(edit_plan=plan, context={"job_id": job_id})

        # Build adaptation for primary style
        primary_profile = style_set.styles[0] if style_set.styles else None
        adaptation_result: dict = {}
        if primary_profile is not None:
            adaptation_result = build_style_adaptation(
                primary_profile, edit_plan=plan, context={"job_id": job_id}
            )

        plan.creator_style_adaptation = {
            "detected": style_set.detected,
            "primary_style": style_set.primary_style,
            "confidence": round(float(primary_profile.confidence if primary_profile else 0.0), 4),
            "adaptation": adaptation_result.get("adaptation", {}),
            "fallback_used": style_set.fallback_used,
            "warnings": list(style_set.warnings),
        }

        logger.info(
            "ai_creator_style_detected job_id=%s primary=%s confidence=%.4f fallback=%s styles=%d",
            job_id,
            style_set.primary_style,
            plan.creator_style_adaptation["confidence"],
            style_set.fallback_used,
            len(style_set.styles),
        )

        if style_set.fallback_used:
            logger.info("ai_creator_style_fallback job_id=%s reason=low_confidence_or_unknown", job_id)

        _append_creator_style_adaptation_explainability(plan, style_set, adaptation_result)

    except Exception as exc:
        plan.creator_style_adaptation = {
            "detected": False,
            "primary_style": "safe_generic",
            "confidence": 0.0,
            "adaptation": {},
            "fallback_used": True,
            "warnings": [f"creator_style_adaptation_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_style_adaptation_failed job_id=%s: %s", job_id, exc)


def _append_creator_style_adaptation_explainability(
    plan: "AIEditPlan",
    style_set: Any,
    adaptation_result: dict,
) -> None:
    """Append compact creator-style adaptation lines to explainability. Never raises."""
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

        primary = style_set.primary_style
        fallback = style_set.fallback_used
        adaptation = adaptation_result.get("adaptation", {})

        if fallback:
            line = "Creator style: safe generic fallback used"
        else:
            _STYLE_LABELS: dict[str, str] = {
                "viral_tiktok": "viral TikTok",
                "cinematic": "cinematic",
                "educational": "educational",
                "podcast": "podcast",
                "product_demo": "product demo",
                "storytelling": "storytelling",
                "commentary": "commentary",
                "interview": "interview",
            }
            label = _STYLE_LABELS.get(primary, primary)
            line = f"Creator style classified as {label}"

        if not any("Creator style" in str(l) for l in lines):
            lines.append(line)

        # Pacing hint line
        pacing_hint = adaptation.get("pacing_hint", "")
        if pacing_hint and pacing_hint not in ("default", ""):
            hint_line = f"{pacing_hint.replace('_', ' ').title()} pacing adaptation suggested"
            if not any("pacing adaptation" in str(l) for l in lines):
                lines.append(hint_line)

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


# ---------------------------------------------------------------------------
# Phase 32 — Safe Timing Mutation Apply attachment
# ---------------------------------------------------------------------------

def _attach_timing_apply(plan: "AIEditPlan", request: Any, job_id: str) -> None:
    """Build and attach safe timing apply pack to the plan.

    Runs after Phase 31 (apply policy) so effective policy is available.
    Only applies mutations when policy is aggressive or experimental.
    Hard safety bounds enforced. Never raises. Never mutates FFmpeg.
    Never rewrites subtitle timing. Never reorders segments.
    """
    if plan is None:
        return
    try:
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack

        raw_policy = str(
            getattr(request, "ai_apply_policy", "conservative") or "conservative"
        )
        context = {"ai_apply_policy": raw_policy, "job_id": job_id}

        pack = build_timing_apply_pack(plan, payload=request, context=context)
        pack_dict = pack.to_dict()
        plan.timing_apply = pack_dict

        applied_count = len(pack_dict.get("applied_mutations") or [])
        blocked_count = len(pack_dict.get("blocked_mutations") or [])

        logger.info(
            "ai_timing_apply_generated job_id=%s enabled=%s mode=%s "
            "applied=%d blocked=%d total_delta=%.2f",
            job_id,
            pack_dict.get("enabled", False),
            pack_dict.get("mode", "disabled"),
            applied_count,
            blocked_count,
            pack_dict.get("total_delta_sec", 0.0),
        )

        _append_timing_apply_explainability(plan, pack_dict)

    except Exception as exc:
        plan.timing_apply = {
            "available": False,
            "enabled": False,
            "mode": "disabled",
            "applied_mutations": [],
            "blocked_mutations": [],
            "total_delta_sec": 0.0,
            "warnings": [f"timing_apply_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_timing_apply_failed job_id=%s: %s", job_id, exc)


def _append_timing_apply_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact timing apply lines to explainability. Never raises."""
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

        enabled = pack_dict.get("enabled", False)
        mode = pack_dict.get("mode", "disabled")

        if not enabled or mode == "disabled":
            line = "Safe timing apply disabled by conservative policy"
            if not any("timing apply" in str(l).lower() for l in lines):
                lines.append(line)
            return

        applied = pack_dict.get("applied_mutations") or []
        blocked = pack_dict.get("blocked_mutations") or []

        for mut in applied:
            if not isinstance(mut, dict):
                continue
            mut_type = str(mut.get("mutation_type") or "")
            if mut_type == "trim_silence_gap":
                line = "Safe silence-gap trim applied"
            elif mut_type == "tighten_setup":
                line = "Safe setup tighten applied"
            elif mut_type == "shorten_outro":
                line = "Safe outro shorten applied"
            elif mut_type == "reduce_dead_air":
                line = "Safe dead-air reduction applied"
            else:
                line = "Safe timing mutation applied"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        for mut in blocked:
            if not isinstance(mut, dict):
                continue
            warnings = mut.get("warnings") or []
            reason = warnings[0] if warnings else "safety_gate_failed"
            line = f"Unsafe timing mutation blocked ({reason})"
            if not any("Unsafe timing mutation blocked" in str(l) for l in lines):
                lines.append(line)
                break  # one blocked line is enough

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 33 — Subtitle Text Optimization Apply attachment
# ---------------------------------------------------------------------------

def _attach_subtitle_text_apply(plan: "AIEditPlan", request: Any, job_id: str) -> None:
    """Build and attach subtitle text optimization pack to the plan.

    Runs after Phase 32 (timing apply). Policy-gated: balanced/aggressive/experimental.
    Text and style metadata only. Never rewrites subtitle timestamps.
    Never mutates FFmpeg. Never raises. Never overrides executor authority.
    """
    if plan is None:
        return
    try:
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack

        raw_policy = str(
            getattr(request, "ai_apply_policy", "conservative") or "conservative"
        )
        context = {"ai_apply_policy": raw_policy, "job_id": job_id}

        pack = build_subtitle_text_apply_pack(plan, payload=request, context=context)
        pack_dict = pack.to_dict()
        plan.subtitle_text_apply = pack_dict

        applied_count = len(pack_dict.get("applied") or [])
        blocked_count = len(pack_dict.get("blocked") or [])

        logger.info(
            "ai_subtitle_text_apply_generated job_id=%s enabled=%s mode=%s "
            "applied=%d blocked=%d",
            job_id,
            pack_dict.get("enabled", False),
            pack_dict.get("mode", "disabled"),
            applied_count,
            blocked_count,
        )

        _append_subtitle_text_apply_explainability(plan, pack_dict)

    except Exception as exc:
        plan.subtitle_text_apply = {
            "available": False,
            "enabled": False,
            "mode": "disabled",
            "applied": [],
            "blocked": [],
            "warnings": [f"subtitle_text_apply_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_subtitle_text_apply_failed job_id=%s: %s", job_id, exc)


def _append_subtitle_text_apply_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact subtitle text apply lines to explainability. Never raises."""
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

        enabled = pack_dict.get("enabled", False)
        mode = pack_dict.get("mode", "disabled")

        if not enabled or mode == "disabled":
            line = "Subtitle text optimization disabled by conservative policy"
            if not any("subtitle text optimization" in str(l).lower() for l in lines):
                lines.append(line)
            line = "Subtitle timestamp rewrite remains blocked"
            if not any("timestamp rewrite" in str(l).lower() for l in lines):
                lines.append(line)
            return

        applied = pack_dict.get("applied") or []
        blocked = pack_dict.get("blocked") or []

        _OPT_LABELS: dict = {
            "compact_overload": "Compact subtitle overload optimization applied",
            "keyword_emphasis": "Keyword emphasis optimization applied",
            "safer_line_breaks": "Safer subtitle line-break optimization applied",
            "density_reduce": "Subtitle density reduce optimization applied",
            "creator_style_tone": "Creator style subtitle tone optimization applied",
            "hook_emphasis": "Hook emphasis subtitle optimization applied",
        }

        for opt in applied:
            if not isinstance(opt, dict):
                continue
            opt_type = str(opt.get("optimization_type") or "")
            line = _OPT_LABELS.get(opt_type, f"Subtitle text optimization applied ({opt_type})")
            if not any(line in str(l) for l in lines):
                lines.append(line)

        for opt in blocked:
            if not isinstance(opt, dict):
                continue
            warns = opt.get("warnings") or []
            reason = warns[0] if warns else "safety_gate_failed"
            line = f"Subtitle optimization blocked ({reason})"
            if not any("Subtitle optimization blocked" in str(l) for l in lines):
                lines.append(line)
                break

        line = "Subtitle timestamp rewrite remains blocked"
        if not any("timestamp rewrite" in str(l).lower() for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 34 — Safe Camera Motion Apply attachment
# ---------------------------------------------------------------------------

def _attach_camera_motion_apply(plan: "AIEditPlan", request: Any, job_id: str) -> None:
    """Build and attach safe camera motion apply pack to the plan.

    Runs after Phase 33 (subtitle apply). Policy-gated: balanced/aggressive/experimental.
    Camera guidance metadata only. Never rewrites crop coordinates.
    Never mutates motion_crop.py. Never mutates FFmpeg. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack

        raw_policy = str(
            getattr(request, "ai_apply_policy", "conservative") or "conservative"
        )
        context = {"ai_apply_policy": raw_policy, "job_id": job_id}

        pack = build_camera_motion_apply_pack(plan, payload=request, context=context)
        pack_dict = pack.to_dict()
        plan.camera_motion_apply = pack_dict

        applied_count = len(pack_dict.get("applied") or [])
        blocked_count = len(pack_dict.get("blocked") or [])

        logger.info(
            "ai_camera_motion_apply_generated job_id=%s enabled=%s mode=%s "
            "applied=%d blocked=%d",
            job_id,
            pack_dict.get("enabled", False),
            pack_dict.get("mode", "disabled"),
            applied_count,
            blocked_count,
        )

        _append_camera_motion_apply_explainability(plan, pack_dict)

    except Exception as exc:
        plan.camera_motion_apply = {
            "available": False,
            "enabled": False,
            "mode": "disabled",
            "applied": [],
            "blocked": [],
            "warnings": [f"camera_motion_apply_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_camera_motion_apply_failed job_id=%s: %s", job_id, exc)


def _append_camera_motion_apply_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact camera motion apply lines to explainability. Never raises."""
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

        enabled = pack_dict.get("enabled", False)
        mode = pack_dict.get("mode", "disabled")

        if not enabled or mode == "disabled":
            line = "Camera motion apply disabled by conservative policy"
            if not any("camera motion apply" in str(l).lower() for l in lines):
                lines.append(line)
            line = "Direct crop coordinate rewrite remains blocked"
            if not any("crop coordinate" in str(l).lower() for l in lines):
                lines.append(line)
            return

        applied = pack_dict.get("applied") or []
        blocked = pack_dict.get("blocked") or []

        _CAM_LABELS: dict = {
            "dynamic_safe": "Dynamic safe camera guidance applied",
            "subtitle_safe_framing": "Subtitle-safe framing guidance applied",
            "beat_aware_pulse": "Beat-aware camera pulse guidance applied",
            "creator_style_camera": "Creator style camera guidance applied",
            "subject_lock_preference": "Subject-lock preference guidance applied",
            "motion_smoothing_hint": "Motion smoothing hint applied",
        }

        for cam in applied:
            if not isinstance(cam, dict):
                continue
            cam_type = str(cam.get("camera_type") or "")
            line = _CAM_LABELS.get(cam_type, f"Camera motion guidance applied ({cam_type})")
            if not any(line in str(l) for l in lines):
                lines.append(line)

        for cam in blocked:
            if not isinstance(cam, dict):
                continue
            warns = cam.get("warnings") or []
            reason = warns[0] if warns else "safety_gate_failed"
            line = f"Camera motion guidance blocked ({reason})"
            if not any("Camera motion guidance blocked" in str(l) for l in lines):
                lines.append(line)
                break

        line = "Direct crop coordinate rewrite remains blocked"
        if not any("crop coordinate" in str(l).lower() for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 35 — AI Clip Candidate Discovery attachment
# ---------------------------------------------------------------------------

def _attach_clip_candidate_discovery(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Discover and rank clip candidates from all available AI metadata.

    Discovery-only: never executes actual cuts, never mutates render payload,
    never modifies FFmpeg, never rewrites subtitle timing, never reorders
    segments. No external API calls. No GPU. No internet. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates

        pack = discover_clip_candidates(plan, payload=request, context={"job_id": job_id})
        pack_dict = pack.to_dict()
        plan.clip_candidate_discovery = pack_dict

        enabled = pack_dict.get("enabled", False)
        candidates = pack_dict.get("candidates") or []
        recommended = pack_dict.get("recommended_candidate_id")

        if enabled:
            logger.info(
                "ai_clip_candidate_discovery_enabled job_id=%s candidates=%d recommended=%s",
                job_id, len(candidates), recommended or "none",
            )
            if candidates:
                logger.info(
                    "ai_clip_candidate_created job_id=%s count=%d",
                    job_id, len(candidates),
                )
            if recommended:
                logger.info(
                    "ai_clip_candidate_recommended job_id=%s candidate_id=%s",
                    job_id, recommended,
                )
        else:
            logger.debug(
                "ai_clip_candidate_discovery_skipped job_id=%s (disabled)", job_id
            )

        _append_clip_candidate_explainability(plan, pack_dict)

    except Exception as exc:
        plan.clip_candidate_discovery = {
            "available": False,
            "enabled": False,
            "mode": "discovery_only",
            "candidates": [],
            "recommended_candidate_id": None,
            "warnings": [f"clip_candidate_discovery_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_clip_candidate_discovery_failed job_id=%s: %s", job_id, exc)


def _append_clip_candidate_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact clip discovery lines to explainability. Never raises."""
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

        if not pack_dict.get("enabled", False):
            return

        if not any("AI clip candidate discovery" in str(l) for l in lines):
            lines.append("AI clip candidate discovery enabled")

        candidates = pack_dict.get("candidates") or []
        if candidates:
            best_retention = max(
                (float(c.get("retention_score", 0.0)) for c in candidates if isinstance(c, dict)),
                default=0.0,
            )
            if best_retention > 70.0:
                line = "High-retention candidate window identified"
                if not any(line in str(l) for l in lines):
                    lines.append(line)

        line = "Candidate discovery remains advisory-only"
        if not any(line in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 36 — AI Clip Segment Selection attachment
# ---------------------------------------------------------------------------

def _attach_clip_segment_selection(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Select and rank clip segment plans from Phase 35 candidates.

    Selection-only: never executes actual cuts, never mutates render payload,
    never modifies FFmpeg, never rewrites subtitle timing, never reorders
    source media. No external API calls. No GPU. No internet. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.clips.clip_segment_selector import select_clip_segments

        selection = select_clip_segments(plan, payload=request, context={"job_id": job_id})
        sel_dict  = selection.to_dict()
        plan.clip_segment_selection = sel_dict

        enabled   = sel_dict.get("enabled", False)
        selected  = sel_dict.get("selected_segments") or []
        rejected  = sel_dict.get("rejected_candidates") or []

        if enabled:
            logger.info(
                "ai_clip_segment_selection_enabled job_id=%s selected=%d rejected=%d",
                job_id, len(selected), len(rejected),
            )
            for seg in selected:
                if isinstance(seg, dict):
                    logger.info(
                        "ai_clip_segment_selected job_id=%s segment_id=%s "
                        "start=%.2f end=%.2f score=%.2f",
                        job_id,
                        seg.get("segment_id", ""),
                        float(seg.get("start_sec", 0.0)),
                        float(seg.get("end_sec", 0.0)),
                        float(seg.get("score", 0.0)),
                    )
            if rejected:
                logger.info(
                    "ai_clip_segment_rejected job_id=%s count=%d",
                    job_id, len(rejected),
                )
        else:
            logger.debug(
                "ai_clip_segment_selection_skipped job_id=%s (disabled)", job_id
            )

        _append_clip_segment_explainability(plan, sel_dict)

    except Exception as exc:
        plan.clip_segment_selection = {
            "available": False,
            "enabled": False,
            "mode": "selection_only",
            "selected_segments": [],
            "rejected_candidates": [],
            "warnings": [f"clip_segment_selection_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_clip_segment_selection_failed job_id=%s: %s", job_id, exc)


def _append_clip_segment_explainability(
    plan: "AIEditPlan",
    sel_dict: dict,
) -> None:
    """Append compact segment selection lines to explainability. Never raises."""
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

        if not sel_dict.get("enabled", False):
            return

        selected = sel_dict.get("selected_segments") or []

        if not any("AI selected clip segments" in str(l) for l in lines):
            lines.append("AI selected clip segments from discovered candidates")

        if selected:
            line = "Selected segments respect configured duration bounds"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        line = "Segment selection remains planning-only"
        if not any(line in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 37 — AI Multi-Clip Batch Planning attachment
# ---------------------------------------------------------------------------

def _attach_clip_batch_planning(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Convert selected clip segments into safe batch render plans.

    Planning-only: never executes batch renders, never enqueues jobs,
    never modifies FFmpeg, never rewrites subtitle timing, never reorders
    source media. No external API calls. No GPU. No internet. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans

        plan_set = build_clip_batch_plans(plan, payload=request, context={"job_id": job_id})
        plan_set_dict = plan_set.to_dict()
        plan.clip_batch_planning = plan_set_dict

        enabled = plan_set_dict.get("enabled", False)
        plans = plan_set_dict.get("plans") or []
        recommended = plan_set_dict.get("recommended_plan_ids") or []

        if enabled:
            logger.info(
                "ai_clip_batch_planning_enabled job_id=%s plans=%d recommended=%d",
                job_id, len(plans), len(recommended),
            )
            for p in plans:
                if isinstance(p, dict):
                    logger.info(
                        "ai_clip_batch_plan_created job_id=%s batch_plan_id=%s strategy=%s",
                        job_id,
                        p.get("batch_plan_id", ""),
                        p.get("render_strategy", ""),
                    )
            if recommended:
                logger.info(
                    "ai_clip_batch_plan_recommended job_id=%s ids=%s",
                    job_id, ",".join(recommended),
                )
        else:
            logger.debug(
                "ai_clip_batch_planning_skipped job_id=%s (disabled)", job_id
            )

        _append_clip_batch_explainability(plan, plan_set_dict)

    except Exception as exc:
        plan.clip_batch_planning = {
            "available": False,
            "enabled": False,
            "mode": "planning_only",
            "plans": [],
            "recommended_plan_ids": [],
            "warnings": [f"clip_batch_planning_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_clip_batch_planning_failed job_id=%s: %s", job_id, exc)


def _append_clip_batch_explainability(
    plan: "AIEditPlan",
    plan_set_dict: dict,
) -> None:
    """Append compact batch planning lines to explainability. Never raises."""
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

        if not plan_set_dict.get("enabled", False):
            return

        plans = plan_set_dict.get("plans") or []

        if not any("AI multi-clip batch plans" in str(l) for l in lines):
            lines.append("AI multi-clip batch plans prepared")

        if plans:
            line = "Selected segments converted into planning-only render plans"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        line = "Batch rendering remains disabled until execution phase"
        if not any(line in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 38 — AI Feature Enhancement Integration attachment
# ---------------------------------------------------------------------------

def _attach_feature_enhancement(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build unified AI feature enhancement pack from all available AI metadata.

    Assistive-only: enhances existing features, never replaces render engine authority.
    Never executes renders, never mutates FFmpeg, never rewrites subtitle timing.
    Never enqueues jobs, never overrides executor. No external API. No GPU. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack

        pack = build_feature_enhancement_pack(plan, payload=request, context={"job_id": job_id})
        pack_dict = pack.to_dict()
        plan.feature_enhancement = pack_dict

        subtitle_enh = pack_dict.get("subtitle_enhancement", {})
        camera_enh = pack_dict.get("camera_enhancement", {})
        timing_enh = pack_dict.get("timing_enhancement", {})
        clip_enh = pack_dict.get("clip_selection_enhancement", {})

        enabled_categories = [
            name for name, enh in (
                ("subtitle", subtitle_enh),
                ("camera", camera_enh),
                ("timing", timing_enh),
                ("clip_selection", clip_enh),
                ("creator_style", pack_dict.get("creator_style_enhancement", {})),
                ("variant", pack_dict.get("variant_enhancement", {})),
                ("output_ranking", pack_dict.get("output_ranking_enhancement", {})),
            )
            if isinstance(enh, dict) and enh.get("enabled", False)
        ]

        if enabled_categories:
            logger.info(
                "ai_feature_enhancement_applied job_id=%s categories=%s",
                job_id, ",".join(enabled_categories),
            )
            logger.info(
                "ai_feature_enhancement_assistive_only job_id=%s mode=assistive_only",
                job_id,
            )
        else:
            logger.debug(
                "ai_feature_enhancement_skipped job_id=%s (no_categories_active)", job_id
            )

        _append_feature_enhancement_explainability(plan, pack_dict)

    except Exception as exc:
        plan.feature_enhancement = {
            "available": False,
            "mode": "assistive_only",
            "subtitle_enhancement": {},
            "camera_enhancement": {},
            "timing_enhancement": {},
            "clip_selection_enhancement": {},
            "creator_style_enhancement": {},
            "variant_enhancement": {},
            "output_ranking_enhancement": {},
            "warnings": [f"feature_enhancement_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_feature_enhancement_failed job_id=%s: %s", job_id, exc)


def _append_feature_enhancement_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact feature enhancement lines to explainability. Never raises."""
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

        subtitle_enh = pack_dict.get("subtitle_enhancement", {})
        if isinstance(subtitle_enh, dict) and subtitle_enh.get("enabled", False):
            line = "AI subtitle enhancement improved readability"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        timing_enh = pack_dict.get("timing_enhancement", {})
        if isinstance(timing_enh, dict) and timing_enh.get("enabled", False):
            improvements = timing_enh.get("improvements") or []
            if any("dead_air" in str(i) for i in improvements):
                line = "AI timing enhancement reduced dead-air"
                if not any(line in str(l) for l in lines):
                    lines.append(line)

        camera_enh = pack_dict.get("camera_enhancement", {})
        if isinstance(camera_enh, dict) and camera_enh.get("enabled", False):
            line = "AI camera enhancement improved framing guidance"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        line = "AI feature enhancement remains assistive-only"
        if not any(line in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 39 — External Creator Knowledge Ingestion attachment
# ---------------------------------------------------------------------------

def _attach_creator_knowledge(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Load local creator knowledge registry and attach compact summary.

    Local-first: reads only from the knowledge/ directory on the local filesystem.
    No internet, no scraping, no subprocess, no cloud dependency.
    Never mutates FFmpeg, never overrides executor. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.knowledge.knowledge_registry import load_knowledge_registry

        registry = load_knowledge_registry()
        registry_dict = registry.to_dict()
        plan.creator_knowledge = registry_dict

        loaded = registry_dict.get("loaded_count", 0)
        categories = registry_dict.get("categories") or []
        styles = registry_dict.get("creator_styles") or []

        if loaded > 0:
            logger.info(
                "ai_creator_knowledge_loaded job_id=%s count=%d categories=%s",
                job_id, loaded, categories,
            )
            logger.info(
                "ai_creator_knowledge_registry_ready job_id=%s styles=%s",
                job_id, styles,
            )
        else:
            logger.debug(
                "ai_creator_knowledge_skipped job_id=%s (no_knowledge_files_found)", job_id
            )

        _append_creator_knowledge_explainability(plan, registry_dict)

    except Exception as exc:
        plan.creator_knowledge = {
            "available": False,
            "loaded_count": 0,
            "categories": [],
            "creator_styles": [],
            "warnings": [f"creator_knowledge_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_knowledge_failed job_id=%s: %s", job_id, exc)


def _append_creator_knowledge_explainability(
    plan: "AIEditPlan",
    registry_dict: dict,
) -> None:
    """Append compact creator knowledge lines to explainability. Never raises."""
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

        loaded = registry_dict.get("loaded_count", 0)
        if loaded > 0:
            line = "External creator knowledge registry loaded"
            if not any(line in str(l) for l in lines):
                lines.append(line)
            line = "Local creator intelligence available"
            if not any(line in str(l) for l in lines):
                lines.append(line)

        line = "Knowledge ingestion remains local-first"
        if not any(line in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 40 — Creator Pattern Extraction attachment
# ---------------------------------------------------------------------------

def _attach_creator_patterns(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Extract creator intelligence patterns from knowledge registry.

    Local-only: reads from knowledge/patterns/. No internet, no model training.
    Never mutates FFmpeg, never overrides executor. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.knowledge.pattern_registry import load_pattern_registry

        registry = load_pattern_registry()
        registry_dict = registry.to_dict()
        plan.creator_patterns = registry_dict

        loaded = registry_dict.get("loaded_patterns", 0)
        pattern_types = registry_dict.get("pattern_types") or []
        styles = registry_dict.get("creator_styles") or []

        if loaded > 0:
            logger.info(
                "ai_creator_pattern_loaded job_id=%s count=%d types=%s",
                job_id, loaded, pattern_types,
            )
            logger.info(
                "ai_creator_pattern_registry_ready job_id=%s styles=%s",
                job_id, styles,
            )
        else:
            logger.debug(
                "ai_creator_pattern_skipped job_id=%s (no_patterns_found)", job_id
            )

        _append_creator_patterns_explainability(plan, registry_dict)

    except Exception as exc:
        plan.creator_patterns = {
            "available": False,
            "loaded_patterns": 0,
            "pattern_types": [],
            "creator_styles": [],
            "warnings": [f"creator_patterns_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_patterns_failed job_id=%s: %s", job_id, exc)


def _append_creator_patterns_explainability(
    plan: "AIEditPlan",
    registry_dict: dict,
) -> None:
    """Append compact creator pattern lines to explainability. Never raises."""
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

        pattern_types = registry_dict.get("pattern_types") or []
        loaded = registry_dict.get("loaded_patterns", 0)

        if loaded > 0:
            if "hook" in pattern_types:
                line = "Creator hook patterns extracted"
                if not any(line in str(l) for l in lines):
                    lines.append(line)
            if "subtitle" in pattern_types:
                line = "Subtitle style patterns available"
                if not any(line in str(l) for l in lines):
                    lines.append(line)
            if "pacing" in pattern_types:
                line = "Creator pacing patterns loaded"
                if not any(line in str(l) for l in lines):
                    lines.append(line)

    except Exception:
        pass


# Phase 41 — Retrieval-Based Creator Intelligence attachment


def _attach_creator_retrieval(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Retrieve creator intelligence patterns from Phase 40 registry.

    Retrieval-only: assistive metadata, no internet, no model training.
    Never mutates FFmpeg, never overrides executor. Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence

        logger.debug("ai_creator_retrieval_started job_id=%s", job_id)

        pack = retrieve_creator_intelligence(plan)
        plan.creator_retrieval = pack.to_dict()

        matches = pack.matches or []
        enabled = pack.enabled
        style = pack.recommended_creator_style or ""

        if enabled and matches:
            logger.info(
                "ai_creator_retrieval_completed job_id=%s matches=%d recommended_style=%s",
                job_id, len(matches), style,
            )
            for m in matches[:3]:
                logger.debug(
                    "ai_creator_retrieval_match job_id=%s id=%s type=%s score=%.2f",
                    job_id, m.match_id, m.pattern_type, m.retrieval_score,
                )
        else:
            logger.debug(
                "ai_creator_retrieval_skipped job_id=%s (no_matches)", job_id
            )

        _append_creator_retrieval_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.creator_retrieval = {
            "available": False,
            "enabled": False,
            "retrieval_mode": "assistive_only",
            "matches": [],
            "recommended_creator_style": "",
            "warnings": [f"creator_retrieval_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_retrieval_failed job_id=%s: %s", job_id, exc)


def _append_creator_retrieval_explainability(
    plan: "AIEditPlan",
    retrieval_dict: dict,
) -> None:
    """Append compact creator retrieval lines to explainability. Never raises."""
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

        enabled = retrieval_dict.get("enabled", False)
        matches = retrieval_dict.get("matches", [])
        style = retrieval_dict.get("recommended_creator_style", "")

        if enabled and matches:
            pacing_matches = [m for m in matches if isinstance(m, dict) and m.get("pattern_type") == "pacing"]
            subtitle_matches = [m for m in matches if isinstance(m, dict) and m.get("pattern_type") == "subtitle"]

            if pacing_matches:
                line = "Creator pacing patterns retrieved"
                if not any(line in str(l) for l in lines):
                    lines.append(line)
            if subtitle_matches:
                line = "Compact subtitle creator patterns applied"
                if not any(line in str(l) for l in lines):
                    lines.append(line)

            line = "Retrieval-based creator intelligence remains assistive-only"
            if not any("assistive-only" in str(l) for l in lines):
                lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 42 — Adaptive creator intelligence
# ---------------------------------------------------------------------------

def _attach_adaptive_creator_intelligence(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build adaptive learning pack from edit plan signals and creator profile.

    Assistive-only: influences metadata ranking only.
    Never mutates FFmpeg, never overrides executor, never rewrites subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack

        logger.debug("ai_adaptive_creator_intelligence_started job_id=%s", job_id)

        context: dict = {}
        raw_profile_id = getattr(request, "ai_adaptive_profile_id", None)
        if raw_profile_id:
            context["profile_id"] = str(raw_profile_id)

        pack = build_adaptive_learning_pack(plan, payload=request, context=context)
        plan.adaptive_creator_intelligence = pack.to_dict()

        if pack.enabled:
            profile_dict = pack.creator_profile or {}
            style = profile_dict.get("creator_style_preference", "")
            subtitle = profile_dict.get("preferred_subtitle_style", "")
            pacing = profile_dict.get("preferred_pacing_style", "")
            camera = profile_dict.get("preferred_camera_style", "")

            logger.info(
                "ai_adaptive_learning_applied job_id=%s style=%s subtitle=%s pacing=%s camera=%s",
                job_id, style, subtitle, pacing, camera,
            )
        else:
            logger.debug("ai_adaptive_learning_skipped job_id=%s (no_signals)", job_id)

        _append_adaptive_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.adaptive_creator_intelligence = {
            "available": False,
            "enabled": False,
            "learning_mode": "assistive_only",
            "creator_profile": {},
            "learned_preferences": {},
            "adaptive_influences": {},
            "warnings": [f"adaptive_creator_intelligence_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_adaptive_creator_intelligence_failed job_id=%s: %s", job_id, exc)


def _append_adaptive_explainability(
    plan: "AIEditPlan",
    adaptive_dict: dict,
) -> None:
    """Append compact adaptive intelligence lines to explainability. Never raises."""
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

        enabled = adaptive_dict.get("enabled", False)
        if not enabled:
            return

        learned = adaptive_dict.get("learned_preferences", {}) or {}
        subtitle_style = learned.get("subtitle_style", "")
        pacing_style = learned.get("pacing_style", "")
        camera_style = learned.get("camera_style", "")

        if subtitle_style:
            line = "Creator subtitle preferences learned"
            if not any("subtitle preferences" in str(l) for l in lines):
                lines.append(line)

        if pacing_style:
            line = "Adaptive creator preferences updated"
            if not any("Adaptive creator preferences" in str(l) for l in lines):
                lines.append(line)

        if camera_style:
            line = "Creator camera preferences learned"
            if not any("camera preferences" in str(l) for l in lines):
                lines.append(line)

        line = "Adaptive creator intelligence remains assistive-only"
        if not any("Adaptive creator intelligence" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 43 — Creator feedback loop intelligence
# ---------------------------------------------------------------------------

def _attach_creator_feedback_intelligence(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build feedback learning pack from creator behavior signals.

    Assistive-only: influences ranking biases only.
    Never mutates FFmpeg, never overrides executor, never rewrites subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack

        logger.debug("ai_creator_feedback_intelligence_started job_id=%s", job_id)

        context: dict = {}
        raw_fb_id = getattr(request, "ai_feedback_id", None)
        if raw_fb_id:
            context["feedback_id"] = str(raw_fb_id)

        for attr in (
            "ai_feedback_exported",
            "ai_feedback_selected",
            "ai_feedback_ignored",
            "ai_feedback_output_rank",
            "ai_feedback_creator_style",
            "ai_feedback_subtitle_style",
            "ai_feedback_pacing_style",
            "ai_feedback_camera_style",
            "ai_feedback_duration_bucket",
        ):
            val = getattr(request, attr, None)
            if val is not None:
                # Strip the "ai_feedback_" prefix to match context keys
                ctx_key = attr[len("ai_feedback_"):]
                if ctx_key == "output_rank":
                    ctx_key = "selected_output_rank"
                if ctx_key == "exported":
                    ctx_key = "exported"
                context[ctx_key] = val

        pack = build_feedback_learning_pack(plan, payload=request, context=context)
        plan.creator_feedback_intelligence = pack.to_dict()

        if pack.enabled:
            patterns = pack.learned_feedback_patterns or {}
            logger.info(
                "ai_feedback_learning_applied job_id=%s total_signals=%d exports=%d ignores=%d",
                job_id,
                patterns.get("total_signals", 0),
                patterns.get("total_exports", 0),
                patterns.get("total_ignores", 0),
            )
        else:
            logger.debug("ai_feedback_learning_skipped job_id=%s", job_id)

        _append_feedback_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.creator_feedback_intelligence = {
            "available": False,
            "enabled": False,
            "feedback_mode": "assistive_only",
            "feedback_signals": [],
            "learned_feedback_patterns": {},
            "ranking_biases": {},
            "warnings": [f"creator_feedback_intelligence_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_feedback_intelligence_failed job_id=%s: %s", job_id, exc)


def _append_feedback_explainability(
    plan: "AIEditPlan",
    feedback_dict: dict,
) -> None:
    """Append compact feedback intelligence lines to explainability. Never raises."""
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

        enabled = feedback_dict.get("enabled", False)
        if not enabled:
            return

        patterns = feedback_dict.get("learned_feedback_patterns", {}) or {}
        biases = feedback_dict.get("ranking_biases", {}) or {}

        total_exports = patterns.get("total_exports", 0)
        if total_exports > 0:
            line = "Ranking biases adapted from export behavior"
            if not any("Ranking biases" in str(l) for l in lines):
                lines.append(line)

        if biases.get("subtitle_weighting_bias", 0) > 0 or biases.get("pacing_weighting_bias", 0) > 0:
            line = "Creator feedback signals applied"
            if not any("Creator feedback signals" in str(l) for l in lines):
                lines.append(line)

        line = "Creator feedback intelligence remains assistive-only"
        if not any("Creator feedback intelligence" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 44 — Market-aware optimization intelligence
# ---------------------------------------------------------------------------

def _attach_market_optimization_intelligence(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build market optimization pack for the target platform.

    Assistive-only: influences subtitle/pacing/camera/hook metadata.
    Never mutates FFmpeg, never overrides executor, never rewrites subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.market.market_optimizer import build_market_optimization_pack

        logger.debug("ai_market_optimization_intelligence_started job_id=%s", job_id)

        context: dict = {}
        target = getattr(request, "ai_target_market", None) or getattr(request, "ai_mode", None)
        if target:
            context["target_market"] = str(target)

        pack = build_market_optimization_pack(plan, payload=request, context=context)
        plan.market_optimization_intelligence = pack.to_dict()

        if pack.enabled:
            logger.info(
                "ai_market_optimization_applied job_id=%s market=%s subtitle_w=%.3f pacing_w=%.3f",
                job_id,
                pack.target_market,
                pack.subtitle_market_bias.get("weight", 0.0),
                pack.pacing_market_bias.get("weight", 0.0),
            )
        else:
            logger.debug("ai_market_optimization_skipped job_id=%s market=%s", job_id, pack.target_market)

        _append_market_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.market_optimization_intelligence = {
            "available": False,
            "enabled": False,
            "optimization_mode": "assistive_only",
            "target_market": "",
            "market_profile": {},
            "subtitle_market_bias": {},
            "pacing_market_bias": {},
            "camera_market_bias": {},
            "hook_market_bias": {},
            "warnings": [f"market_optimization_intelligence_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_market_optimization_failed job_id=%s: %s", job_id, exc)


def _append_market_explainability(
    plan: "AIEditPlan",
    market_dict: dict,
) -> None:
    """Append compact market optimization lines to explainability. Never raises."""
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

        enabled = market_dict.get("enabled", False)
        if not enabled:
            return

        target = market_dict.get("target_market", "")
        profile = market_dict.get("market_profile", {}) or {}
        platform = profile.get("platform_type", "")

        # Platform-specific explainability line
        if platform in ("tiktok",):
            line = "TikTok market optimization applied"
        elif platform in ("youtube_shorts",):
            line = "YouTube Shorts market optimization applied"
        elif platform in ("facebook_reels",):
            line = "Facebook Reels market optimization applied"
        elif platform in ("podcast",):
            line = "Podcast readability optimization applied"
        elif platform in ("educational",):
            line = "Educational readability optimization applied"
        else:
            line = f"Market optimization applied ({target})" if target else "Market optimization applied"

        if not any("market optimization" in str(l).lower() for l in lines):
            lines.append(line)

        line = "Market optimization remains assistive-only"
        if not any("Market optimization remains" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 45 — AI Render Quality Evaluation
# ---------------------------------------------------------------------------

def _append_quality_explainability(
    plan: "AIEditPlan",
    quality_dict: dict,
) -> None:
    """Append compact quality evaluation lines to explainability. Never raises."""
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

        enabled = quality_dict.get("enabled", False)
        if not enabled:
            return

        scores = quality_dict.get("output_scores") or []
        if scores:
            best_id = quality_dict.get("best_quality_output_id", "")
            line = f"Render quality evaluated across {len(scores)} output(s)"
            if not any("Render quality evaluated" in str(l) for l in lines):
                lines.append(line)
            if best_id:
                line = f"Best quality output: {best_id}"
                if not any("Best quality output" in str(l) for l in lines):
                    lines.append(line)

        line = "Render quality evaluation remains evaluation-only"
        if not any("Render quality evaluation remains" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 46 — Creator Preset Evolution Intelligence
# ---------------------------------------------------------------------------

def _attach_creator_preset_evolution(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Build creator preset evolution pack and attach to plan.

    Assistive-only: evolves preset metadata, never mutates render output,
    never overrides executor, never rewrites subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack

        logger.debug("ai_preset_evolution_started job_id=%s", job_id)

        context: dict = {}
        target = getattr(request, "ai_target_market", None) or getattr(request, "ai_mode", None)
        if target:
            context["target_market"] = str(target)

        pack = build_preset_evolution_pack(plan, payload=request, context=context)
        plan.creator_preset_evolution = pack.to_dict()

        if pack.enabled:
            logger.info(
                "ai_preset_evolution_applied job_id=%s best_preset=%s recommended=%d evolved=%d",
                job_id,
                pack.best_preset_id,
                len(pack.recommended_presets),
                len(pack.evolved_presets),
            )
        else:
            logger.debug("ai_preset_evolution_skipped job_id=%s", job_id)

        _append_preset_evolution_explainability(plan, pack.to_dict())

    except Exception as exc:
        plan.creator_preset_evolution = {
            "available": False,
            "enabled": False,
            "evolution_mode": "assistive_only",
            "recommended_presets": [],
            "evolved_presets": [],
            "best_preset_id": "",
            "warnings": [f"creator_preset_evolution_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_preset_evolution_failed job_id=%s: %s", job_id, exc)


def _append_preset_evolution_explainability(
    plan: "AIEditPlan",
    pack_dict: dict,
) -> None:
    """Append compact preset evolution lines to explainability. Never raises."""
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

        enabled = pack_dict.get("enabled", False)
        if not enabled:
            return

        line = "Creator preset evolution prepared"
        if not any("Creator preset evolution" in str(l) for l in lines):
            lines.append(line)

        # Best evolved preset
        evolved = pack_dict.get("evolved_presets") or []
        if evolved:
            best_name = evolved[0].get("preset_name", "")
            if best_name:
                line = f"{best_name} recommended"
                if not any(best_name in str(l) for l in lines):
                    lines.append(line)

        line = "Preset evolution remains assistive-only"
        if not any("Preset evolution remains" in str(l) for l in lines):
            lines.append(line)

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Phase 47 — Multi-Signal AI Render Orchestrator attachment
# ---------------------------------------------------------------------------

def _attach_multi_signal_orchestration(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Orchestrate all AI signals into a unified render strategy. Phase 47.

    Reasoning-only: aggregates Phase 41–46 signals into one coherent
    recommendation. Never mutates render output, never overrides executor,
    never touches FFmpeg, playback_speed, or subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals

        logger.debug("ai_render_orchestrator_started job_id=%s", job_id)

        context: dict = {}
        target = getattr(request, "ai_target_market", None) or getattr(request, "ai_mode", None)
        if target:
            context["target_market"] = str(target)

        result = orchestrate_render_signals(plan, payload=request, context=context)
        plan.multi_signal_orchestration = result

        if result.get("enabled"):
            agg_conf = float(
                (result.get("confidence_scores") or {}).get("aggregate_confidence") or 0.0
            )
            active = int(
                (result.get("aggregated_signals") or {}).get("active_signal_count") or 0
            )
            logger.info(
                "ai_render_orchestrator_done job_id=%s enabled=True "
                "confidence=%.3f active_signals=%d",
                job_id, agg_conf, active,
            )
        else:
            logger.debug("ai_render_orchestrator_skipped job_id=%s", job_id)

    except Exception as exc:
        plan.multi_signal_orchestration = {
            "available": False,
            "enabled": False,
            "orchestration_mode": "reasoning_only",
            "warnings": [f"multi_signal_orchestration_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_multi_signal_orchestration_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 48 — Safe Controlled Influence Engine attachment
# ---------------------------------------------------------------------------

def _attach_safe_influence_pack(
    plan: "AIEditPlan",
    request: Any,
    job_id: str,
) -> None:
    """Compute safe controlled influence recommendations. Phase 48.

    Consumes Phase 47 multi_signal_orchestration output and produces
    conservative, confidence-gated influence recommendations.

    Safe influence only: subtitle bias, camera motion bias, clip ranking bias,
    market weight bias. Never mutates render output, never overrides executor,
    never touches FFmpeg, playback_speed, or subtitle timing.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.influence.influence_engine import compute_safe_influence

        logger.debug("ai_safe_influence_started job_id=%s", job_id)

        context: dict = {}
        target = getattr(request, "ai_target_market", None) or getattr(request, "ai_mode", None)
        if target:
            context["target_market"] = str(target)

        result = compute_safe_influence(plan, payload=request, context=context)
        plan.safe_influence_pack = result

        if result.get("enabled"):
            conf = float(result.get("confidence") or 0.0)
            tier = str((result.get("gate") or {}).get("tier") or "")
            logger.info(
                "ai_safe_influence_done job_id=%s enabled=True "
                "confidence=%.3f tier=%s",
                job_id, conf, tier,
            )
        else:
            logger.debug("ai_safe_influence_skipped job_id=%s", job_id)

    except Exception as exc:
        plan.safe_influence_pack = {
            "available": False,
            "enabled": False,
            "influence_mode": "safe_controlled",
            "warnings": [f"safe_influence_pack_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_safe_influence_pack_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 50A — Deep Subtitle Preference Intelligence attachment
# ---------------------------------------------------------------------------

def _attach_creator_subtitle_preference(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Infer deep subtitle preferences from all available AI metadata. Phase 50A.

    Reads Phase 17, 33, 42–48 signal fields from the edit plan and produces
    a rich subtitle preference profile. Inference-only: no render mutation,
    no subtitle engine rewrite, no timing rewrite, no executor override.
    Never raises.
    """
    if plan is None:
        return
    try:
        from app.ai.creator_subtitle.subtitle_preference_inference import (
            infer_subtitle_preference,
        )

        logger.debug("ai_subtitle_preference_started job_id=%s", job_id)
        result = infer_subtitle_preference(plan)
        plan.creator_subtitle_preference = result

        conf = (result.get("subtitle_preference") or {}).get("confidence", 0.0)
        style = (result.get("subtitle_preference") or {}).get("style", "unknown")
        logger.info(
            "ai_subtitle_preference_done job_id=%s style=%s confidence=%.2f",
            job_id, style, float(conf),
        )

    except Exception as exc:
        plan.creator_subtitle_preference = {
            "available": False,
            "inference_mode": "metadata_only",
            "subtitle_preference": {
                "style": "unknown", "density": "unknown", "line_count": 2,
                "uppercase": "unknown", "keyword_emphasis": "unknown",
                "motion_style": "unknown", "caption_box": "unknown",
                "readability_priority": "unknown", "mobile_safe": True,
                "confidence": 0.0, "signals": [],
            },
            "warnings": [f"creator_subtitle_preference_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_subtitle_preference_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 50B — Creator Camera Preference Intelligence attachment
# ---------------------------------------------------------------------------

def _attach_creator_camera_preference(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Infer creator camera preferences from all available AI metadata. Phase 50B.

    Reads Phase 34, 42–48 signal fields from the edit plan and produces a rich
    camera preference profile plus bounded MotionCropConfig tuning deltas.
    Inference-only metadata: no motion_crop rewrite, no tracking rewrite,
    no FFmpeg mutation, no executor override.
    """
    if plan is None:
        return
    try:
        from app.ai.creator_camera.camera_preference_inference import infer_camera_preference
        from app.ai.creator_camera.camera_tuning_engine import compute_camera_tuning
        from app.ai.creator_camera.camera_preference_schema import AICameraPreferencePack

        logger.debug("ai_camera_preference_started job_id=%s", job_id)
        camera_pref = infer_camera_preference(plan)
        tuning_pack = compute_camera_tuning(camera_pref)
        pack = AICameraPreferencePack(
            available=True,
            inference_mode="metadata_only",
            camera_preference=camera_pref,
            tuning_pack=tuning_pack,
        )
        plan.creator_camera_preference = pack.to_dict()

        conf = camera_pref.confidence
        style = camera_pref.motion_style
        tier = tuning_pack.confidence_tier
        logger.info(
            "ai_camera_preference_done job_id=%s style=%s confidence=%.2f tier=%s applied=%s",
            job_id, style, float(conf), tier, tuning_pack.applied,
        )

    except Exception as exc:
        plan.creator_camera_preference = {
            "available": False,
            "inference_mode": "metadata_only",
            "camera_preference": {
                "motion_style": "unknown", "crop_aggressiveness": "unknown",
                "stability_priority": "unknown", "deadzone_preference": "unknown",
                "subject_hold": "unknown", "scene_sensitivity": "unknown",
                "center_bias": "unknown", "reframing_risk_tolerance": "unknown",
                "smoothness_priority": "unknown", "confidence": 0.0, "signals": [],
            },
            "tuning_pack": {
                "applied": False, "confidence_tier": "low",
                "deadzone_delta": 0.0, "ema_alpha_delta": 0.0,
                "hold_frames_delta": 0, "scene_threshold_delta": 0.0,
                "smooth_window_delta": 0, "reasoning": [], "warnings": [],
            },
            "warnings": [f"creator_camera_preference_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_camera_preference_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 50C — Subtitle Preference Safe Influence attachment
# ---------------------------------------------------------------------------

def _attach_creator_subtitle_influence(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Compute bounded subtitle influence recommendations from Phase 50A preferences. Phase 50C.

    Reads plan.creator_subtitle_preference (produced by Phase 50A) and
    generates six bounded subtitle tuning signals.  No subtitle engine
    rewrite, no ASS generation rewrite, no timing rewrite, no FFmpeg mutation.
    """
    if plan is None:
        return
    try:
        from app.ai.creator_subtitle.subtitle_influence_engine import compute_subtitle_influence

        logger.debug("ai_subtitle_influence_started job_id=%s", job_id)
        pref_pack = getattr(plan, "creator_subtitle_influence", None)
        # Input is the Phase 50A preference pack, not the influence pack field
        subtitle_pref = getattr(plan, "creator_subtitle_preference", None) or {}
        influence = compute_subtitle_influence(subtitle_pref)
        plan.creator_subtitle_influence = influence.to_dict()

        tier  = influence.confidence_tier
        bias  = influence.preset_bias
        avail = influence.available
        logger.info(
            "ai_subtitle_influence_done job_id=%s tier=%s preset_bias=%s available=%s",
            job_id, tier, bias, avail,
        )
        del pref_pack  # unused variable guard

    except Exception as exc:
        plan.creator_subtitle_influence = {
            "available":                False,
            "confidence_tier":          "low",
            "preset_bias":              "unknown",
            "preset_bias_strength":     0.0,
            "density_nudge":            "none",
            "emphasis_delta":           0.0,
            "line_count_bias":          0,
            "motion_style_bias":        "unknown",
            "mobile_readability_nudge": 0.0,
            "reasoning":                [],
            "warnings": [f"creator_subtitle_influence_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_subtitle_influence_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 50D — Creator Preference Fusion attachment
# ---------------------------------------------------------------------------

def _attach_creator_preference_profile(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Fuse all creator intelligence signals into a unified preference profile. Phase 50D.

    Reads Phase 50A subtitle preference, Phase 50B camera preference, Phase 50C
    influence pack, and Phase 42–47 metadata.  Advisory metadata only — no render
    mutation, no executor override.
    """
    if plan is None:
        return
    try:
        from app.ai.creator_fusion.fusion_engine import fuse_creator_preferences

        logger.debug("ai_creator_preference_fusion_started job_id=%s", job_id)
        profile = fuse_creator_preferences(plan)
        plan.creator_preference_profile = profile.to_dict()

        sub_style   = profile.subtitle.style
        cam_motion  = profile.camera.motion_style
        conf        = profile.confidence
        n_conflicts = len(profile.conflicts_resolved)
        logger.info(
            "ai_creator_preference_fusion_done job_id=%s"
            " subtitle_style=%s camera_motion=%s confidence=%.2f conflicts=%d",
            job_id, sub_style, cam_motion, float(conf), n_conflicts,
        )

    except Exception as exc:
        plan.creator_preference_profile = {
            "available": False,
            "subtitle":  {"style": "unknown", "density": "unknown",
                          "keyword_emphasis": "unknown", "readability_priority": "unknown"},
            "camera":    {"motion_style": "unknown", "crop_aggressiveness": "unknown",
                          "stability_priority": "unknown", "smoothness_priority": "unknown"},
            "clip":      {"content_style": "unknown", "ranking_preference": "unknown"},
            "market_alignment":  {"target_market": "unknown", "market_fit": "unknown"},
            "quality_alignment": {"readability_priority": "unknown", "smoothness_priority": "unknown"},
            "confidence":         0.0,
            "reasoning":          [],
            "conflicts_resolved": [],
            "warnings": [f"creator_preference_profile_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_creator_preference_profile_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 51A — Safe Strategy Variant Generator attachment
# ---------------------------------------------------------------------------

def _attach_strategy_variants(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Generate safe candidate strategy variants from unified creator profile. Phase 51A.

    Reads Phase 50D creator_preference_profile, Phase 44 market_optimization_intelligence,
    and Phase 45 render_quality_evaluation.  Produces up to 3 deterministic candidate
    strategy variants.  Candidate-only — no evaluation, no selection, no execution.
    """
    if plan is None:
        return
    try:
        from app.ai.strategy_variants.variant_generator import generate_strategy_variants

        logger.debug("ai_strategy_variants_started job_id=%s", job_id)
        pack = generate_strategy_variants(plan)
        plan.strategy_variants = pack.to_dict()

        count   = pack.variant_count
        ids_str = ",".join(v.id for v in pack.strategy_variants[:3])
        logger.info(
            "ai_strategy_variants_done job_id=%s variant_count=%d ids=[%s]",
            job_id, count, ids_str,
        )

    except Exception as exc:
        plan.strategy_variants = {
            "available":         False,
            "strategy_variants": [{
                "id":         "creator_safe",
                "label":      "Creator Safe",
                "intent":     "fallback conservative strategy",
                "subtitle":   {"style": "unknown", "density": "unknown", "keyword_emphasis": "unknown"},
                "camera":     {"motion_style": "unknown", "stability_priority": "unknown",
                               "crop_aggressiveness": "unknown"},
                "ranking":    {"priority": "balanced"},
                "confidence": 0.0,
                "reasoning":  ["Conservative fallback — strategy variant generation failed"],
            }],
            "variant_count":   1,
            "generation_mode": "candidate_only",
            "warnings":        [f"strategy_variants_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_strategy_variants_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 51B — Variant Evaluation Engine attachment
# ---------------------------------------------------------------------------

def _attach_variant_evaluation(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Score and rank Phase 51A strategy variants. Phase 51B.

    Reads plan.strategy_variants (51A), creator_preference_profile (50D),
    market_optimization_intelligence (44), and render_quality_evaluation (45).
    Produces a deterministic ranked evaluation with best_variant_id.
    Evaluation-only — best_variant_id is advisory metadata, never applied to render.
    """
    if plan is None:
        return
    try:
        from app.ai.strategy_variants.variant_evaluator import evaluate_strategy_variants

        logger.debug("ai_variant_evaluation_started job_id=%s", job_id)
        pack = evaluate_strategy_variants(plan)
        plan.variant_evaluation = pack.to_dict()

        best     = pack.best_variant_id or "none"
        conf     = pack.confidence
        n_ranked = len(pack.ranking)
        logger.info(
            "ai_variant_evaluation_done job_id=%s best=%s ranked=%d confidence=%.2f",
            job_id, best, n_ranked, float(conf),
        )

    except Exception as exc:
        plan.variant_evaluation = {
            "available":       False,
            "best_variant_id": None,
            "ranking":         [],
            "confidence":      0.0,
            "reasoning":       [],
            "evaluation_mode": "evaluation_only",
            "warnings":        [f"variant_evaluation_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_variant_evaluation_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 51C — Best Strategy Reasoning attachment
# ---------------------------------------------------------------------------

def _attach_best_strategy_reasoning(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Build creator-facing reasoning for the best evaluated strategy. Phase 51C.

    Reads plan.variant_evaluation (51B) and plan.creator_preference_profile (50D).
    Produces deterministic explanation metadata: summary, why_selected, tradeoffs,
    and recommendation_strength.  Reasoning-only — never applied to render.
    """
    if plan is None:
        return
    try:
        from app.ai.strategy_variants.strategy_reasoner import build_best_strategy_reasoning

        logger.debug("ai_best_strategy_reasoning_started job_id=%s", job_id)
        reasoning = build_best_strategy_reasoning(plan)
        plan.best_strategy_reasoning = reasoning.to_dict()

        vid      = reasoning.selected_variant_id or "none"
        strength = reasoning.recommendation_strength
        conf     = reasoning.confidence
        logger.info(
            "ai_best_strategy_reasoning_done job_id=%s selected=%s strength=%s confidence=%.2f",
            job_id, vid, strength, float(conf),
        )

    except Exception as exc:
        plan.best_strategy_reasoning = {
            "selected_variant_id":     None,
            "selected_label":          "",
            "confidence":              0.0,
            "summary":                 "No confident AI strategy recommendation available.",
            "why_selected":            [],
            "tradeoffs":               [],
            "recommendation_strength": "none",
            "warnings":                [f"best_strategy_reasoning_error:{type(exc).__name__}"],
        }
        logger.debug("ai_director_best_strategy_reasoning_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 52A — Subtitle Quality Intelligence v2 attachment
# ---------------------------------------------------------------------------

def _attach_subtitle_quality_v2(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Evaluate subtitle quality across 5 dimensions + 2 risk scores. Phase 52A.

    Reads subtitle execution, creator preference, market, and quality signals.
    Produces deterministic quality metadata: per-dimension scores, risk scores,
    overall weighted score, confidence, and creator-facing reasoning.
    Evaluation-only — no subtitle mutation, no timing rewrite, no executor override.
    """
    if plan is None:
        return
    try:
        from app.ai.subtitle_quality.subtitle_quality_evaluator import evaluate_subtitle_quality_v2

        logger.debug("ai_subtitle_quality_v2_started job_id=%s", job_id)
        result = evaluate_subtitle_quality_v2(plan)

        # result is {"subtitle_quality_v2": {...}}
        plan.subtitle_quality_v2 = result.get("subtitle_quality_v2", {})

        sqv2    = plan.subtitle_quality_v2
        overall = sqv2.get("overall", 0)
        conf    = sqv2.get("confidence", 0.0)
        logger.info(
            "ai_subtitle_quality_v2_done job_id=%s overall=%d confidence=%.2f",
            job_id, overall, float(conf),
        )

    except Exception as exc:
        plan.subtitle_quality_v2 = {
            "mobile_readability":       0,
            "subtitle_balance":         0,
            "keyword_emphasis_quality": 0,
            "safe_zone_fit":            0,
            "creator_fit":              0,
            "overload_risk":            0,
            "fatigue_risk":             0,
            "overall":                  0,
            "confidence":               0.0,
            "reasoning":                [],
        }
        logger.debug("ai_director_subtitle_quality_v2_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 52B — Camera Quality Intelligence v2 attachment
# ---------------------------------------------------------------------------

def _attach_camera_quality_v2(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Evaluate camera quality across 4 dimensions + 2 risk scores. Phase 52B.

    Reads camera_motion_apply, creator_camera_preference, creator_preference_profile,
    market, beat_visual_execution, and quality signals.
    Produces deterministic quality metadata: per-dimension scores, risk scores,
    overall weighted score, confidence, and creator-facing reasoning.
    Evaluation-only — no motion_crop rewrite, no tracking rewrite, no executor override.
    """
    if plan is None:
        return
    try:
        from app.ai.camera_quality.camera_quality_evaluator import evaluate_camera_quality_v2

        logger.debug("ai_camera_quality_v2_started job_id=%s", job_id)
        result = evaluate_camera_quality_v2(plan)

        # result is {"camera_quality_v2": {...}}
        plan.camera_quality_v2 = result.get("camera_quality_v2", {})

        cqv2    = plan.camera_quality_v2
        overall = cqv2.get("overall", 0)
        conf    = cqv2.get("confidence", 0.0)
        logger.info(
            "ai_camera_quality_v2_done job_id=%s overall=%d confidence=%.2f",
            job_id, overall, float(conf),
        )

    except Exception as exc:
        plan.camera_quality_v2 = {
            "micro_jitter_risk": 0,
            "whip_pan_risk":     0,
            "crop_smoothness":   0,
            "subject_stability": 0,
            "scene_continuity":  0,
            "creator_fit":       0,
            "overall":           0,
            "confidence":        0.0,
            "reasoning":         [],
        }
        logger.debug("ai_director_camera_quality_v2_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 52C — Hook Quality Intelligence v2 attachment
# ---------------------------------------------------------------------------

def _attach_hook_quality_v2(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Evaluate hook quality across 6 dimensions + 1 risk score. Phase 52C.

    Reads story, retention, pacing, market_optimization_intelligence,
    creator_preference_profile, creator_preset_evolution, and adaptive_creator_intelligence.
    Produces deterministic quality metadata: per-dimension scores, risk score,
    overall weighted score, confidence, and creator-facing reasoning.
    Evaluation-only — no hook rewriting, no clip rewrite, no render mutation, no executor override.
    """
    if plan is None:
        return
    try:
        from app.ai.hook_quality.hook_quality_evaluator import evaluate_hook_quality_v2

        logger.debug("ai_hook_quality_v2_started job_id=%s", job_id)
        result = evaluate_hook_quality_v2(plan)

        # result is {"hook_quality_v2": {...}}
        plan.hook_quality_v2 = result.get("hook_quality_v2", {})

        hqv2    = plan.hook_quality_v2
        overall = hqv2.get("overall", 0)
        conf    = hqv2.get("confidence", 0.0)
        logger.info(
            "ai_hook_quality_v2_done job_id=%s overall=%d confidence=%.2f",
            job_id, overall, float(conf),
        )

    except Exception as exc:
        plan.hook_quality_v2 = {
            "first_3s_strength":  0,
            "first_5s_retention": 0,
            "curiosity_strength": 0,
            "open_loop_quality":  0,
            "hook_fatigue_risk":  0,
            "market_fit":         0,
            "creator_fit":        0,
            "overall":            0,
            "confidence":         0.0,
            "reasoning":          [],
        }
        logger.debug("ai_director_hook_quality_v2_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 52D — Unified Quality Score v2 attachment
# ---------------------------------------------------------------------------

def _attach_unified_quality_v2(
    plan: "AIEditPlan",
    job_id: str,
) -> None:
    """Fuse subtitle/camera/hook quality scores into one unified render quality score. Phase 52D.

    Reads subtitle_quality_v2 (52A), camera_quality_v2 (52B), hook_quality_v2 (52C),
    creator_preference_profile (50D), market_optimization_intelligence (44),
    variant_evaluation (51B), and best_strategy_reasoning (51C).
    Produces deterministic unified quality metadata: per-dimension scores, overall
    weighted score, confidence, and creator-facing reasoning.
    Evaluation-only — no render mutation, no executor override, no autonomous execution.
    """
    if plan is None:
        return
    try:
        from app.ai.unified_quality.unified_quality_evaluator import evaluate_unified_quality_v2

        logger.debug("ai_unified_quality_v2_started job_id=%s", job_id)
        result = evaluate_unified_quality_v2(plan)

        # result is {"render_quality_v2": {...}}
        plan.render_quality_v2 = result.get("render_quality_v2", {})

        rqv2    = plan.render_quality_v2
        overall = rqv2.get("overall", 0)
        conf    = rqv2.get("confidence", 0.0)
        logger.info(
            "ai_unified_quality_v2_done job_id=%s overall=%d confidence=%.2f",
            job_id, overall, float(conf),
        )

    except Exception as exc:
        plan.render_quality_v2 = {
            "subtitle_score": 0,
            "camera_score":   0,
            "hook_score":     0,
            "creator_fit":    0,
            "market_fit":     0,
            "strategy_fit":   0,
            "overall":        0,
            "confidence":     0.0,
            "reasoning":      [],
        }
        logger.debug("ai_director_unified_quality_v2_failed job_id=%s: %s", job_id, exc)


# ---------------------------------------------------------------------------
# Phase 53A — Knowledge Injection Foundation helper
# ---------------------------------------------------------------------------

def _attach_knowledge_injection(plan: "AIEditPlan", job_id: str) -> None:
    """Retrieve context-aware knowledge and attach to plan.knowledge_injection.

    Advisory only — informs; never mutates render parameters.
    """
    from app.ai.knowledge.knowledge_pack_retriever import retrieve_knowledge_context
    result = retrieve_knowledge_context(plan)
    plan.knowledge_injection = result.get("knowledge_context", {})
    ctx = plan.knowledge_injection
    logger.debug(
        "ai_knowledge_injection_done job_id=%s available=%s matches=%d confidence=%.2f",
        job_id,
        ctx.get("available", False),
        len(ctx.get("matches") or []),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 53E — Knowledge-Aware Render Reasoning helper
# ---------------------------------------------------------------------------

def _attach_knowledge_reasoning_context(plan: "AIEditPlan", job_id: str) -> None:
    """Route subtitle/camera/hook knowledge retrievers from quality signals.

    Builds cross-domain advisory reasoning context attached to
    plan.knowledge_reasoning_context.

    Advisory only — informs; never mutates render parameters.
    """
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context
    result = build_knowledge_reasoning_context(plan)
    plan.knowledge_reasoning_context = result.get("knowledge_reasoning_context", {})
    ctx = plan.knowledge_reasoning_context
    logger.debug(
        "ai_knowledge_reasoning_context_done job_id=%s available=%s domains=%s matches=%d confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("domains", []),
        len(ctx.get("matches") or []),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 54 — Knowledge-Aware Influence Upgrade helper
# ---------------------------------------------------------------------------

def _attach_knowledge_influence_context(plan: "AIEditPlan", job_id: str) -> None:
    """Build per-domain knowledge influence support and enrich influence reasoning.

    1. Reads plan.knowledge_reasoning_context (Phase 53E output).
    2. Builds knowledge_influence_context with per-domain confidence_delta metadata.
    3. Enriches plan.creator_subtitle_influence reasoning (additive only).
    4. Enriches plan.creator_camera_preference tuning reasoning (additive only).
    5. Enriches plan.safe_influence_pack reasoning (additive only).

    Advisory only — confidence_delta is metadata, NEVER fed to safety gate.
    Safety gates are NEVER lowered or bypassed. No render mutation.
    """
    from app.ai.knowledge.knowledge_influence_context import (
        build_knowledge_influence_context,
        enrich_subtitle_influence_reasoning,
        enrich_camera_influence_reasoning,
        enrich_ranking_influence_reasoning,
    )

    result = build_knowledge_influence_context(plan)
    plan.knowledge_influence_context = result.get("knowledge_influence_context", {})
    kic = plan.knowledge_influence_context

    if not kic.get("available"):
        logger.debug("ai_knowledge_influence_context_unavailable job_id=%s", job_id)
        return

    influence_support = kic.get("influence_support") or {}

    # --- Enrich subtitle influence reasoning (additive only) ---
    subtitle_support = influence_support.get("subtitle") or {}
    if subtitle_support.get("supported") and plan.creator_subtitle_influence:
        plan.creator_subtitle_influence = enrich_subtitle_influence_reasoning(
            plan.creator_subtitle_influence, subtitle_support
        )

    # --- Enrich camera preference tuning reasoning (additive only) ---
    camera_support = influence_support.get("camera") or {}
    if camera_support.get("supported") and plan.creator_camera_preference:
        cam_pref = plan.creator_camera_preference
        # Enrich the camera_preference dict (top level or nested tuning)
        tuning = cam_pref.get("camera_preference") or {}
        if tuning and isinstance(tuning, dict):
            enriched_tuning = enrich_camera_influence_reasoning(tuning, camera_support)
            plan.creator_camera_preference = {
                **cam_pref,
                "camera_preference": enriched_tuning,
            }

    # --- Enrich ranking influence reasoning (additive only) ---
    ranking_support = influence_support.get("ranking") or {}
    if ranking_support.get("supported") and plan.safe_influence_pack:
        plan.safe_influence_pack = enrich_ranking_influence_reasoning(
            plan.safe_influence_pack, ranking_support
        )

    logger.debug(
        "ai_knowledge_influence_context_done job_id=%s available=%s domains=%s confidence=%.2f",
        job_id,
        kic.get("available", False),
        kic.get("domains", []),
        float(kic.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55A — Platform Knowledge Foundation helper
# ---------------------------------------------------------------------------

def _attach_platform_context(plan: "AIEditPlan", request: Any, job_id: str) -> None:
    """Retrieve platform knowledge and attach advisory platform_context to plan.

    Reads platform and creator_type from the request (informational fields),
    calls the platform knowledge retriever, and attaches the result to
    plan.platform_context.

    Foundation only — no influence mutation, no render execution change.
    Advisory only — platform_context is metadata, never alters render parameters.
    """
    from app.ai.knowledge.platform_knowledge_retriever import build_platform_context

    platform = str(getattr(request, "platform", "") or "").strip().lower()
    creator_type = str(getattr(request, "creator_type", "") or "").strip().lower()

    result = build_platform_context(platform=platform, creator_type=creator_type)
    plan.platform_context = result.get("platform_context", {})
    ctx = plan.platform_context

    logger.debug(
        "ai_platform_context_done job_id=%s available=%s platform=%s creator_type=%s matches=%d confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("platform", ""),
        ctx.get("creator_type", ""),
        len(ctx.get("matches") or []),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55B — Platform Subtitle Intelligence helper
# ---------------------------------------------------------------------------

def _attach_platform_subtitle_context(plan: "AIEditPlan", request: Any, job_id: str) -> None:
    """Retrieve subtitle-specific platform knowledge and attach to plan.

    Reads platform and creator_type from request, calls the platform subtitle
    retriever, and attaches advisory platform_subtitle_context to the plan.

    Advisory only — no subtitle timing rewrite, no ASS rewrite, no segmentation
    rewrite, no executor override, no autonomous execution.
    """
    from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context

    platform = str(getattr(request, "platform", "") or "").strip().lower()
    creator_type = str(getattr(request, "creator_type", "") or "").strip().lower()

    result = build_platform_subtitle_context(platform=platform, creator_type=creator_type)
    plan.platform_subtitle_context = result.get("platform_subtitle_context", {})
    ctx = plan.platform_subtitle_context

    logger.debug(
        "ai_platform_subtitle_context_done job_id=%s available=%s platform=%s "
        "creator_type=%s confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("platform", ""),
        ctx.get("creator_type", ""),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55C — Platform Camera Intelligence helper
# ---------------------------------------------------------------------------

def _attach_platform_camera_context(plan: "AIEditPlan", request: Any, job_id: str) -> None:
    """Retrieve camera-specific platform knowledge and attach to plan.

    Reads platform and creator_type from request, calls the platform camera
    retriever, and attaches advisory platform_camera_context to the plan.

    Advisory only — no motion_crop rewrite, no tracking config change,
    no FFmpeg mutation, no executor override, no autonomous execution.
    """
    from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context

    platform = str(getattr(request, "platform", "") or "").strip().lower()
    creator_type = str(getattr(request, "creator_type", "") or "").strip().lower()

    result = build_platform_camera_context(platform=platform, creator_type=creator_type)
    plan.platform_camera_context = result.get("platform_camera_context", {})
    ctx = plan.platform_camera_context

    logger.debug(
        "ai_platform_camera_context_done job_id=%s available=%s platform=%s "
        "creator_type=%s confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("platform", ""),
        ctx.get("creator_type", ""),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55D — Platform Hook & Retention Intelligence helper
# ---------------------------------------------------------------------------

def _attach_platform_hook_context(plan: "AIEditPlan", request: Any, job_id: str) -> None:
    """Retrieve hook/retention-specific platform knowledge and attach to plan.

    Reads platform and creator_type from request, calls the platform hook
    retriever, and attaches advisory platform_hook_context to the plan.

    Advisory only — no transcript rewrite, no hook text rewrite, no clip
    boundary change, no render mutation, no executor override, no autonomous
    execution.
    """
    from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context

    platform = str(getattr(request, "platform", "") or "").strip().lower()
    creator_type = str(getattr(request, "creator_type", "") or "").strip().lower()

    result = build_platform_hook_context(platform=platform, creator_type=creator_type)
    plan.platform_hook_context = result.get("platform_hook_context", {})
    ctx = plan.platform_hook_context

    logger.debug(
        "ai_platform_hook_context_done job_id=%s available=%s platform=%s "
        "creator_type=%s confidence=%.2f",
        job_id,
        ctx.get("available", False),
        ctx.get("platform", ""),
        ctx.get("creator_type", ""),
        float(ctx.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 55E — Platform-Aware Render Strategy helper
# ---------------------------------------------------------------------------

def _attach_platform_render_strategy(plan: "AIEditPlan", job_id: str) -> None:
    """Fuse platform contexts into unified advisory render strategy and attach to plan.

    Reads platform_subtitle_context (55B), platform_camera_context (55C),
    platform_hook_context (55D), platform_context (55A), creator_preference_profile
    (50D), and render_quality_v2 (52D) from the plan and produces one
    deterministic platform_render_strategy.

    Advisory only — strategy enriches orchestrator reasoning, variant evaluation,
    and AI UX explanation. Never executes rendering, never overrides executor
    authority, never mutates render pipeline parameters.
    """
    from app.ai.knowledge.platform_render_strategy_engine import build_platform_render_strategy

    result = build_platform_render_strategy(plan)
    plan.platform_render_strategy = result.get("platform_render_strategy", {})
    strat = plan.platform_render_strategy

    logger.debug(
        "ai_platform_render_strategy_done job_id=%s available=%s platform=%s "
        "creator_type=%s confidence=%.2f",
        job_id,
        strat.get("available", False),
        strat.get("platform", ""),
        strat.get("creator_type", ""),
        float(strat.get("confidence") or 0.0),
    )


# ---------------------------------------------------------------------------
# Phase 56 — Platform-Aware Strategy Influence helper
# ---------------------------------------------------------------------------

def _attach_platform_strategy_influence(plan: "AIEditPlan", job_id: str) -> None:
    """Build platform strategy influence context and enrich influence dicts.

    Reads plan.platform_render_strategy (Phase 55E), builds per-domain influence
    support (subtitle, camera, ranking) with bounded confidence deltas, and
    enriches existing influence reasoning (additive only):
      1. plan.creator_subtitle_influence reasoning
      2. plan.creator_camera_preference tuning reasoning
      3. plan.safe_influence_pack reasoning

    Advisory only — confidence_delta is metadata, NEVER fed to safety gate.
    Safety gates are NEVER lowered or bypassed by platform strategy.
    No render mutation, no executor override, no pipeline changes.
    """
    from app.ai.knowledge.platform_strategy_influence_context import (
        build_platform_strategy_influence,
        enrich_subtitle_influence_reasoning,
        enrich_camera_influence_reasoning,
        enrich_ranking_influence_reasoning,
    )

    result = build_platform_strategy_influence(plan)
    plan.platform_strategy_influence = result.get("platform_strategy_influence", {})
    psi = plan.platform_strategy_influence

    if not psi.get("available"):
        logger.debug("ai_platform_strategy_influence_unavailable job_id=%s", job_id)
        return

    # --- Enrich subtitle influence reasoning (additive only) ---
    subtitle_support = psi.get("subtitle") or {}
    if subtitle_support.get("supported") and plan.creator_subtitle_influence:
        plan.creator_subtitle_influence = enrich_subtitle_influence_reasoning(
            plan.creator_subtitle_influence, subtitle_support,
        )

    # --- Enrich camera preference tuning reasoning (additive only) ---
    camera_support = psi.get("camera") or {}
    if camera_support.get("supported") and plan.creator_camera_preference:
        cam_pref = plan.creator_camera_preference
        tuning = cam_pref.get("camera_preference") or {}
        if tuning and isinstance(tuning, dict):
            enriched_tuning = enrich_camera_influence_reasoning(tuning, camera_support)
            plan.creator_camera_preference = {
                **cam_pref,
                "camera_preference": enriched_tuning,
            }

    # --- Enrich ranking influence reasoning (additive only) ---
    ranking_support = psi.get("ranking") or {}
    if ranking_support.get("supported") and plan.safe_influence_pack:
        plan.safe_influence_pack = enrich_ranking_influence_reasoning(
            plan.safe_influence_pack, ranking_support,
        )

    logger.debug(
        "ai_platform_strategy_influence_done job_id=%s available=%s "
        "platform=%s creator_type=%s confidence=%.2f",
        job_id,
        psi.get("available", False),
        psi.get("platform", ""),
        psi.get("creator_type", ""),
        float(psi.get("confidence") or 0.0),
    )
