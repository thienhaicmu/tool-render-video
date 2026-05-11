"""
render_influence.py — Bounded, opt-in AI render influence module.

Applies small, safe adjustments from an AI edit plan to a render payload.
All changes are logged in an influence_report for full traceability.

Design rules:
- Never raises under any circumstances.
- Only applies changes that are already permitted by the payload's existing state.
- Hard numerical bounds are enforced via clamp_ai_influence().
- Phase 10 conservatively influences camera and subtitle only.
- Pacing and memory influence are report-only (deferred to Phase 11+).
- playback_speed, segment start/end, output validation — NEVER touched.

Public API:
    apply_ai_render_influence(payload, edit_plan, context=None) -> tuple[object, dict]
    clamp_ai_influence(value, min_value, max_value, default) -> float
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.director.render_influence")

# ── Hard numerical bounds ─────────────────────────────────────────────────────
_MAX_ZOOM_STRENGTH   = 1.18   # AI camera zoom never exceeds this
_MAX_FOLLOW_STRENGTH = 0.85   # AI follow strength never exceeds this

# Camera behaviors that can trigger motion-aware crop (if conditions are safe)
_MOTION_BEHAVIORS = frozenset({"fast_follow", "dramatic_push", "slow_reveal"})

# reframe_mode values that already imply subject/motion tracking
_MOTION_REFRAME_MODES = frozenset({"motion", "subject", "face"})


# ── Public helpers ────────────────────────────────────────────────────────────

def clamp_ai_influence(
    value: Any,
    min_value: float,
    max_value: float,
    default: float,
) -> float:
    """Return value clamped to [min_value, max_value]. Returns default on any error."""
    try:
        return max(min_value, min(max_value, float(value)))
    except Exception:
        return default


# ── Primary entry point ───────────────────────────────────────────────────────

def apply_ai_render_influence(
    payload: Any,
    edit_plan: Any,
    context: Optional[dict] = None,
) -> tuple[Any, dict]:
    """Apply bounded AI influence to render payload.

    Mutates payload fields in-place where safe to do so (existing pipeline code
    reads payload fields directly; returning the same object is correct).

    Args:
        payload:   RenderRequest-compatible object with render config fields.
        edit_plan: AIEditPlan (or None) — source of AI decisions.
        context:   Optional metadata dict (e.g. {"job_id": "..."}).

    Returns:
        (payload, influence_report) where influence_report is:
        {
            "enabled": bool,
            "applied":  list[str],   # descriptions of changes made
            "skipped":  list[str],   # descriptions of skipped decisions (with reason)
            "warnings": list[str],
        }
    """
    report: dict = {"enabled": True, "applied": [], "skipped": [], "warnings": []}

    if edit_plan is None:
        report["warnings"].append("no_edit_plan")
        logger.debug("ai_render_influence_skipped: no edit plan")
        return payload, report

    try:
        _apply_camera_influence(payload, edit_plan, report)
        _apply_subtitle_influence(payload, edit_plan, report)
        _apply_pacing_influence(payload, edit_plan, report)
        _apply_memory_influence(payload, edit_plan, report)
        _report_beat_visual_execution(payload, edit_plan, report)
        _report_timing_mutation(payload, edit_plan, report)
        _report_story_optimization(payload, edit_plan, report)
        _report_variant_plans(payload, edit_plan, report)
        _report_variant_selection(payload, edit_plan, report)
        _report_render_decision_preview(payload, edit_plan, report)
        _report_execution_recommendations(payload, edit_plan, report)
        _report_execution_simulation(payload, edit_plan, report)
        _report_safe_mutations(payload, edit_plan, report)
        _report_multivariant_plans(payload, edit_plan, report)
        _report_multivariant_execution(payload, edit_plan, report)
        _report_output_ranking(payload, edit_plan, report)
        _report_ai_apply_policy(payload, edit_plan, report)
        _report_timing_apply(payload, edit_plan, report)
        _report_subtitle_text_apply(payload, edit_plan, report)
        _report_camera_motion_apply(payload, edit_plan, report)
        _report_clip_candidate_discovery(payload, edit_plan, report)
        _report_clip_segment_selection(payload, edit_plan, report)
        _report_clip_batch_planning(payload, edit_plan, report)
        _report_feature_enhancement(payload, edit_plan, report)
        _report_creator_retrieval(payload, edit_plan, report)
        _report_adaptive_creator_intelligence(payload, edit_plan, report)
        _report_creator_feedback_intelligence(payload, edit_plan, report)
        _report_market_optimization_intelligence(payload, edit_plan, report)
        _report_render_quality_evaluation(payload, edit_plan, report)
        _report_creator_preset_evolution(payload, edit_plan, report)
        _report_multi_signal_orchestration(payload, edit_plan, report)
        _report_safe_influence_pack(payload, edit_plan, report)
        _report_creator_subtitle_preference(payload, edit_plan, report)
        _report_creator_camera_preference(payload, edit_plan, report)
        _report_creator_subtitle_influence(payload, edit_plan, report)
        _report_creator_preference_profile(payload, edit_plan, report)
        _update_explainability(edit_plan, report)
    except Exception as exc:
        report["warnings"].append(f"influence_error:{type(exc).__name__}")
        logger.warning("ai_render_influence_unexpected_error: %s", exc)

    logger.info(
        "ai_render_influence_applied applied=%d skipped=%d warnings=%d",
        len(report["applied"]),
        len(report["skipped"]),
        len(report["warnings"]),
    )
    return payload, report


# ── Camera influence ──────────────────────────────────────────────────────────

def _apply_camera_influence(payload: Any, edit_plan: Any, report: dict) -> None:
    """Enable motion_aware_crop when camera plan warrants it and conditions are safe.

    Safety gate: only activates if motion_aware_crop is already true OR
    reframe_mode already implies motion/subject tracking.
    Never force-enables motion crop on an otherwise static render request.
    """
    camera = getattr(edit_plan, "camera", None)
    if camera is None:
        report["skipped"].append("camera:no_camera_plan")
        return

    behavior = str(getattr(camera, "behavior", "none") or "none").strip().lower()

    # Clamp AI strengths to hard bounds (for report accuracy)
    zoom_strength = clamp_ai_influence(
        getattr(camera, "zoom_strength", 1.0), 1.0, _MAX_ZOOM_STRENGTH, 1.0
    )
    follow_strength = clamp_ai_influence(
        getattr(camera, "follow_strength", 0.5), 0.0, _MAX_FOLLOW_STRENGTH, 0.5
    )

    if behavior not in _MOTION_BEHAVIORS:
        report["skipped"].append(f"camera:behavior_not_motion({behavior!r})")
        return

    already_motion = bool(getattr(payload, "motion_aware_crop", False))
    reframe = str(getattr(payload, "reframe_mode", "center") or "center").strip().lower()
    reframe_supports_motion = reframe in _MOTION_REFRAME_MODES

    if not (already_motion or reframe_supports_motion):
        report["skipped"].append(
            f"camera:motion_aware_crop_not_safe"
            f"(behavior={behavior!r}, reframe={reframe!r}, "
            f"motion_aware_crop={already_motion})"
        )
        return

    try:
        payload.motion_aware_crop = True
        report["applied"].append(
            f"camera:motion_aware_crop=true"
            f"(behavior={behavior!r}, zoom_clamped={zoom_strength:.2f},"
            f" follow_clamped={follow_strength:.2f})"
        )
    except Exception as exc:
        report["skipped"].append(f"camera:set_failed:{type(exc).__name__}")


# ── Subtitle influence ────────────────────────────────────────────────────────

def _apply_subtitle_influence(payload: Any, edit_plan: Any, report: dict) -> None:
    """Enable per-word keyword highlight when subtitle plan requests it.

    Only activates if add_subtitle is already enabled on the payload.
    Never alters subtitle timing, text content, or ASS formatting.
    """
    subtitle = getattr(edit_plan, "subtitle", None)
    if subtitle is None:
        report["skipped"].append("subtitle:no_subtitle_plan")
        return

    if not bool(getattr(subtitle, "highlight_keywords", False)):
        report["skipped"].append("subtitle:highlight_keywords=false")
        return

    if not bool(getattr(payload, "add_subtitle", False)):
        report["skipped"].append("subtitle:add_subtitle=false(no_subtitle_to_highlight)")
        return

    try:
        payload.highlight_per_word = True
        report["applied"].append("subtitle:highlight_per_word=true(keyword_highlight)")
    except Exception as exc:
        report["skipped"].append(f"subtitle:set_failed:{type(exc).__name__}")


# ── Pacing influence (Phase 11 beat execution integration) ───────────────────

def _apply_pacing_influence(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record pacing metadata; run beat execution planning when enabled.

    Beat execution (Phase 11) builds a metadata-only plan from pacing data.
    No timing, subtitle, or playback_speed mutations occur.
    """
    pacing = getattr(edit_plan, "pacing", None)
    if pacing is None:
        report["skipped"].append("pacing:no_pacing_plan")
        return

    style = str(getattr(pacing, "pacing_style", "default") or "default")
    energy = getattr(pacing, "energy_level", None)
    beat_available = bool(getattr(pacing, "beat_available", False))

    beat_execution_enabled = bool(getattr(payload, "ai_beat_execution_enabled", False))

    if beat_execution_enabled and beat_available:
        try:
            from app.ai.director.beat_execution import build_beat_execution_plan
            beat_report = build_beat_execution_plan(edit_plan, payload)
            edit_plan.beat_execution = beat_report
            if beat_report.get("enabled"):
                bpm = beat_report.get("bpm", 0)
                pulse = beat_report.get("pulse_strength", 0.0)
                transition = beat_report.get("suggested_transition_style", "none")
                report["applied"].append(
                    f"pacing:beat_execution_planned("
                    f"bpm={bpm:.1f},pulse={pulse:.3f},"
                    f"transition={transition!r})"
                )
            else:
                beat_warns = beat_report.get("warnings", [])
                reason = beat_warns[0] if beat_warns else "unknown"
                report["skipped"].append(f"pacing:beat_execution_skipped({reason})")
        except Exception as exc:
            report["warnings"].append(f"pacing:beat_execution_error:{type(exc).__name__}")
    elif beat_execution_enabled and not beat_available:
        report["skipped"].append(
            f"pacing:beat_execution_skipped(beat_data_unavailable,"
            f"style={style!r},energy={energy})"
        )
    else:
        report["skipped"].append(
            f"pacing:report_only(style={style!r},energy={energy},"
            f"beat_execution_disabled)"
        )


# ── Memory influence (report-only in Phase 10) ───────────────────────────────

def _apply_memory_influence(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record memory context only — no render setting changes in Phase 10."""
    memory_context = getattr(edit_plan, "memory_context", None)
    if not memory_context:
        report["skipped"].append("memory:no_memory_context")
        return

    results = memory_context.get("results") or memory_context.get("memories") or []
    count = len(results) if isinstance(results, (list, tuple)) else 0
    report["skipped"].append(
        f"memory:report_only(context_results={count},render_influence_deferred)"
    )


# ── Beat visual execution — report-only in Phase 18 ─────────────────────────

def _report_beat_visual_execution(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record beat visual execution metadata — deferred in Phase 18.

    No FFmpeg commands altered. No timing changed. No visual effects applied.
    """
    bve = getattr(edit_plan, "beat_visual_execution", None)
    if not isinstance(bve, dict):
        report["skipped"].append("beat_visual_execution:no_plan")
        return

    if not bve.get("available", False):
        warns = bve.get("warnings", [])
        reason = warns[0] if warns else "unavailable"
        report["skipped"].append(f"beat_visual_execution:deferred({reason})")
        return

    bpm = bve.get("bpm")
    pulse_count = len(bve.get("pulse_regions", []))
    hint_count = len(bve.get("transition_hints", []))
    report["skipped"].append(
        f"beat_visual_execution:deferred_phase18("
        f"bpm={bpm},pulse_regions={pulse_count},"
        f"transition_hints={hint_count})"
    )
    logger.debug(
        "beat_visual_execution_deferred bpm=%s pulse_regions=%d transition_hints=%d",
        bpm, pulse_count, hint_count,
    )


# ── Variant selection — report-only in Phase 22 ──────────────────────────────

def _report_variant_selection(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record variant selection metadata — deferred in Phase 22.

    No variant rendered. No payload mutated. No FFmpeg commands altered.
    """
    vs = getattr(edit_plan, "variant_selection", None)
    if not isinstance(vs, dict):
        report["skipped"].append("variant_selection:no_result")
        return

    if not vs:
        report["skipped"].append("variant_selection:empty")
        return

    selected = vs.get("selected_variant_id")
    confidence = vs.get("selection_confidence", 0.0)
    fallback = vs.get("fallback_used", False)
    rejected = vs.get("rejected_count", 0)

    report["skipped"].append(
        f"variant_selection:deferred_phase22("
        f"selected={selected!r},confidence={confidence:.4f},"
        f"fallback={fallback},rejected={rejected})"
    )
    logger.debug(
        "variant_selection_deferred selected=%s confidence=%.4f fallback=%s rejected=%d",
        selected, confidence, fallback, rejected,
    )


# ── Variant planning — report-only in Phase 21 ───────────────────────────────

def _report_variant_plans(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record variant planning metadata — deferred in Phase 21.

    No extra render jobs enqueued. No payload mutated. No FFmpeg commands altered.
    """
    variants = getattr(edit_plan, "variants", None)
    if not isinstance(variants, dict):
        report["skipped"].append("variant_planning:no_plan")
        return

    if not variants.get("available", False):
        warns = variants.get("warnings", [])
        reason = warns[0] if warns else "unavailable"
        report["skipped"].append(f"variant_planning:deferred({reason})")
        return

    mode = variants.get("mode", "advisory")
    variant_count = len(variants.get("variants", []))
    safe_count = sum(
        1 for v in variants.get("variants", [])
        if isinstance(v, dict) and v.get("safe_to_render", False)
    )
    recommended = variants.get("recommended_variant_id")

    report["skipped"].append(
        f"variant_planning:deferred_phase21("
        f"mode={mode!r},variants={variant_count},"
        f"safe={safe_count},recommended={recommended!r})"
    )
    logger.debug(
        "variant_planning_deferred mode=%s variants=%d safe=%d recommended=%s",
        mode, variant_count, safe_count, recommended,
    )


# ── Story optimization — report-only in Phase 20 ─────────────────────────────

def _report_story_optimization(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record story optimization metadata — deferred in Phase 20.

    No segment ordering changed. No timing changed. No subtitle rewritten.
    No FFmpeg commands altered.
    """
    so = getattr(edit_plan, "story_optimization", None)
    if not isinstance(so, dict):
        report["skipped"].append("story_optimization:no_plan")
        return

    if not so.get("available", False):
        warns = so.get("warnings", [])
        reason = warns[0] if warns else "unavailable"
        report["skipped"].append(f"story_optimization:deferred({reason})")
        return

    flow_type = so.get("flow_type", "unknown")
    score = so.get("narrative_score", 0.0)
    issue_count = len(so.get("issues", []))
    rec_count = len(so.get("recommendations", []))

    report["skipped"].append(
        f"story_optimization:deferred_phase20("
        f"flow={flow_type!r},score={score:.1f},"
        f"issues={issue_count},recommendations={rec_count})"
    )
    logger.debug(
        "story_optimization_deferred flow=%s score=%.1f issues=%d recommendations=%d",
        flow_type, score, issue_count, rec_count,
    )


# ── Timing mutation — report-only in Phase 19 ────────────────────────────────

def _report_timing_mutation(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record timing mutation metadata — deferred in Phase 19.

    No segment start/end changed. No playback_speed changed. No FFmpeg commands altered.
    """
    tm = getattr(edit_plan, "timing_mutation", None)
    if not isinstance(tm, dict):
        report["skipped"].append("timing_mutation:no_plan")
        return

    if not tm.get("available", False):
        warns = tm.get("warnings", [])
        reason = warns[0] if warns else "unavailable"
        report["skipped"].append(f"timing_mutation:deferred({reason})")
        return

    mode = tm.get("mode", "advisory")
    candidate_count = len(tm.get("candidates", []))
    safe_count = sum(
        1 for c in tm.get("candidates", [])
        if isinstance(c, dict) and c.get("safe_to_apply", False)
    )
    gain = tm.get("estimated_retention_gain", 0.0)

    report["skipped"].append(
        f"timing_mutation:deferred_phase19("
        f"mode={mode!r},candidates={candidate_count},"
        f"safe={safe_count},gain={gain:.4f})"
    )
    logger.debug(
        "timing_mutation_deferred mode=%s candidates=%d safe=%d gain=%.4f",
        mode, candidate_count, safe_count, gain,
    )


# ── Render decision preview — report-only in Phase 24 ────────────────────────

def _report_render_decision_preview(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record render decision preview metadata — deferred in Phase 24.

    No render actions executed. No payload mutated. No FFmpeg commands altered.
    """
    rdp = getattr(edit_plan, "render_decision_preview", None)
    if not isinstance(rdp, dict):
        report["skipped"].append("render_decision_preview:no_result")
        return

    if not rdp:
        report["skipped"].append("render_decision_preview:empty")
        return

    status = rdp.get("safety_status", "unavailable")
    confidence = rdp.get("confidence", 0.0)
    selected = rdp.get("selected_variant_id")

    report["skipped"].append(
        f"render_decision_preview:deferred_phase24("
        f"status={status!r},confidence={confidence:.4f},"
        f"selected_variant={selected!r})"
    )
    logger.debug(
        "render_decision_preview_deferred status=%s confidence=%.4f selected=%s",
        status, confidence, selected,
    )


# ── Execution recommendations — report-only in Phase 25 ──────────────────────

def _report_execution_recommendations(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record execution recommendation metadata — deferred in Phase 25.

    No recommendations applied. No payload mutated. No FFmpeg commands altered.
    """
    er = getattr(edit_plan, "execution_recommendations", None)
    if not isinstance(er, dict):
        report["skipped"].append("execution_recommendations:no_result")
        return

    if not er:
        report["skipped"].append("execution_recommendations:empty")
        return

    count = len(er.get("recommendations") or [])
    recommended_id = er.get("recommended_pack_id")

    report["skipped"].append(
        f"execution_recommendations:deferred_phase25("
        f"count={count},recommended={recommended_id!r})"
    )
    logger.debug(
        "execution_recommendations_deferred count=%d recommended=%s",
        count, recommended_id,
    )


# ── Execution simulation — report-only in Phase 26 ───────────────────────────

def _report_execution_simulation(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record execution simulation metadata — deferred in Phase 26.

    No simulations applied. No payload mutated. No FFmpeg commands altered.
    """
    es = getattr(edit_plan, "execution_simulation", None)
    if not isinstance(es, dict):
        report["skipped"].append("execution_simulation:no_result")
        return

    if not es:
        report["skipped"].append("execution_simulation:empty")
        return

    count = len(es.get("simulations") or [])
    recommended_id = es.get("recommended_simulation_id")

    report["skipped"].append(
        f"execution_simulation:deferred_phase26("
        f"count={count},recommended={recommended_id!r})"
    )
    logger.debug(
        "execution_simulation_deferred count=%d recommended=%s",
        count, recommended_id,
    )


# ── Safe render mutations — applied + blocked report in Phase 27 ─────────────

def _report_safe_mutations(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report safe mutation results from Phase 27.

    Applied mutations appear in report["applied"] — first AI-managed
    metadata mutations to reach the applied list. Blocked mutations appear
    in report["skipped"]. Payload is never mutated here.
    """
    srm = getattr(edit_plan, "safe_render_mutations", None)
    if not isinstance(srm, dict) or not srm:
        report["skipped"].append("safe_render_mutations:no_result")
        return

    mutations = srm.get("mutations") or []
    applied_ids = set(srm.get("applied_mutation_ids") or [])
    blocked_ids = srm.get("blocked_mutations") or []

    for mut in mutations:
        if not isinstance(mut, dict):
            continue
        mid = str(mut.get("mutation_id") or "")
        cat = str(mut.get("category") or "")
        changes = mut.get("changes") or {}
        changes_str = ",".join(f"{k}={v}" for k, v in list(changes.items())[:3])

        if mid in applied_ids:
            report["applied"].append(
                f"safe_mutation:applied({mid},{cat}:[{changes_str}])"
            )
            logger.info(
                "ai_safe_mutation_applied mutation_id=%s category=%s", mid, cat
            )
        else:
            report["skipped"].append(
                f"safe_mutation:blocked({mid},{cat})"
            )
            logger.info("ai_safe_mutation_blocked mutation_id=%s", mid)

    # Record any blocked IDs that have no corresponding mutation dict
    for bid in blocked_ids:
        if not any(isinstance(m, dict) and m.get("mutation_id") == bid for m in mutations):
            report["skipped"].append(f"safe_mutation:blocked_id({bid})")

    logger.debug(
        "safe_mutations_reported applied=%d blocked=%d",
        len(applied_ids), len(blocked_ids),
    )


# ── Multi-variant render plans — planning_only, deferred in Phase 28 ─────────

def _report_multivariant_plans(payload: Any, edit_plan: Any, report: dict) -> None:
    """Record multi-variant render plan metadata — deferred in Phase 28.

    No variants are enqueued. No render jobs are created. No payload mutated.
    All plans are advisory planning_only; safe_to_enqueue is for future use.
    """
    mvp = getattr(edit_plan, "multivariant_render_plans", None)
    if not isinstance(mvp, dict) or not mvp:
        report["skipped"].append("multivariant_render_plans:no_result")
        return

    plans = mvp.get("plans") or []
    recommended_id = mvp.get("recommended_plan_id") or "none"
    safe_count = sum(1 for p in plans if isinstance(p, dict) and p.get("safe_to_enqueue"))

    report["skipped"].append(
        f"multivariant_render_plans:deferred_phase28"
        f"(count={len(plans)},safe={safe_count},recommended={recommended_id})"
    )
    logger.debug(
        "multivariant_plans_reported count=%d safe=%d recommended=%s",
        len(plans), safe_count, recommended_id,
    )


# ── Multi-variant execution — summary reporting in Phase 29 ──────────────────

def _report_multivariant_execution(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report multi-variant execution results from Phase 29.

    Executed plans appear in report["applied"] as bounded render job descriptors.
    Blocked/disabled plans appear in report["skipped"].
    Payload is never mutated here — execution payloads were copies built at AI Director time.
    """
    mvx = getattr(edit_plan, "multivariant_execution", None)
    if not isinstance(mvx, dict) or not mvx:
        report["skipped"].append("multivariant_execution:no_result")
        return

    execution_enabled = mvx.get("execution_enabled", False)
    executed_ids = mvx.get("executed_plan_ids") or []
    blocked_ids = mvx.get("blocked_plan_ids") or []
    executions = mvx.get("executions") or []

    if not execution_enabled:
        report["skipped"].append(
            f"multivariant_execution:disabled_phase29"
            f"(plans={len(executions)},blocked={len(blocked_ids)})"
        )
        logger.debug("multivariant_execution_reported disabled plans=%d", len(executions))
        return

    for exec_entry in executions:
        if not isinstance(exec_entry, dict):
            continue
        exec_id = str(exec_entry.get("execution_id") or "")
        plan_id = str(exec_entry.get("plan_id") or "")
        enabled = exec_entry.get("enabled", False)
        safe = exec_entry.get("safe", False)
        overrides = exec_entry.get("payload_overrides") or {}
        overrides_str = ",".join(f"{k}={v}" for k, v in list(overrides.items())[:3])

        if enabled and safe and plan_id in executed_ids:
            report["applied"].append(
                f"multivariant_exec:executed({exec_id},{plan_id}:[{overrides_str}])"
            )
            logger.info(
                "ai_multivariant_execution_created execution_id=%s plan_id=%s",
                exec_id, plan_id,
            )
        else:
            reason = exec_entry.get("warnings") or ["blocked"]
            report["skipped"].append(
                f"multivariant_exec:blocked({exec_id},{plan_id}:{reason[0] if reason else 'unknown'})"
            )
            logger.info("ai_multivariant_execution_blocked execution_id=%s", exec_id)

    logger.debug(
        "multivariant_execution_reported executed=%d blocked=%d",
        len(executed_ids), len(blocked_ids),
    )


# ── Output ranking — recommendation_only advisory in Phase 30 ─────────────────

def _report_output_ranking(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report AI output ranking metadata — recommendation_only in Phase 30.

    No files are uploaded, deleted, overwritten, or published.
    Ranking is advisory only. Best output recommendation goes to report["skipped"]
    as a deferred/planning entry (actual ranking is post-render).
    """
    orr = getattr(edit_plan, "output_ranking", None)
    if not isinstance(orr, dict) or not orr:
        report["skipped"].append("output_ranking:no_result")
        return

    available = orr.get("available", False)
    best_id = orr.get("best_output_id") or "none"
    outputs = orr.get("outputs") or []

    if not available:
        report["skipped"].append(
            f"output_ranking:deferred_phase30"
            f"(best={best_id},outputs={len(outputs)})"
        )
    else:
        report["skipped"].append(
            f"output_ranking:recommendation_only"
            f"(best={best_id},outputs={len(outputs)})"
        )
    logger.debug(
        "output_ranking_reported available=%s best=%s outputs=%d",
        available, best_id, len(outputs),
    )


# ── AI apply policy — summary reporting in Phase 31 ──────────────────────────

def _report_ai_apply_policy(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report AI apply policy metadata from Phase 31.

    Policy summary and blocked capabilities go to report["skipped"].
    Payload is never mutated. No executor authority overridden.
    """
    pol = getattr(edit_plan, "ai_apply_policy", None)
    if not isinstance(pol, dict) or not pol:
        report["skipped"].append("ai_apply_policy:no_result")
        return

    selected = pol.get("selected_policy") or "conservative"
    blocked = pol.get("blocked_capabilities") or []
    available = pol.get("available", False)

    report["skipped"].append(
        f"ai_apply_policy:phase31"
        f"(policy={selected},available={available},blocked_count={len(blocked)})"
    )
    logger.debug(
        "ai_apply_policy_reported policy=%s blocked=%d",
        selected, len(blocked),
    )


# ── Timing apply — applied/blocked summary in Phase 32 ───────────────────────

def _report_timing_apply(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report safe timing mutation apply results from Phase 32.

    Applied mutations appear in report["applied"] as bounded timing metadata.
    Blocked mutations appear in report["skipped"].
    Payload is never mutated here. No FFmpeg changes. No subtitle timing rewrite.
    """
    ta = getattr(edit_plan, "timing_apply", None)
    if not isinstance(ta, dict) or not ta:
        report["skipped"].append("timing_apply:no_result")
        return

    enabled = ta.get("enabled", False)
    mode = ta.get("mode", "disabled")
    total_delta = ta.get("total_delta_sec", 0.0)
    applied = ta.get("applied_mutations") or []
    blocked = ta.get("blocked_mutations") or []

    if not enabled or mode == "disabled":
        report["skipped"].append(
            f"timing_apply:disabled_phase32"
            f"(applied={len(applied)},blocked={len(blocked)})"
        )
        logger.debug("timing_apply_reported disabled")
        return

    for mut in applied:
        if not isinstance(mut, dict):
            continue
        mut_id = str(mut.get("mutation_id") or "")
        mut_type = str(mut.get("mutation_type") or "")
        delta = float(mut.get("delta_sec") or 0.0)
        report["applied"].append(
            f"timing_apply:applied({mut_id},{mut_type}:delta={delta:.2f}s)"
        )
        logger.info(
            "ai_timing_mutation_applied mutation_id=%s type=%s delta=%.2f",
            mut_id, mut_type, delta,
        )

    for mut in blocked:
        if not isinstance(mut, dict):
            continue
        mut_id = str(mut.get("mutation_id") or "")
        mut_type = str(mut.get("mutation_type") or "")
        warnings = mut.get("warnings") or ["blocked"]
        reason = warnings[0] if warnings else "blocked"
        report["skipped"].append(
            f"timing_apply:blocked({mut_id},{mut_type}:{reason})"
        )
        logger.info("ai_timing_mutation_blocked mutation_id=%s reason=%s", mut_id, reason)

    logger.debug(
        "timing_apply_reported applied=%d blocked=%d total_delta=%.2f",
        len(applied), len(blocked), total_delta,
    )


# ── Subtitle text apply — applied/blocked summary in Phase 33 ────────────────

def _report_subtitle_text_apply(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report subtitle text optimization apply results from Phase 33.

    Applied optimizations appear in report["applied"] as bounded metadata descriptors.
    Blocked optimizations and the timestamp-rewrite safety invariant go to report["skipped"].
    Payload is never mutated here. No subtitle timestamp rewrite. No FFmpeg changes.
    """
    sta = getattr(edit_plan, "subtitle_text_apply", None)
    if not isinstance(sta, dict) or not sta:
        report["skipped"].append("subtitle_text_apply:no_result")
        return

    enabled = sta.get("enabled", False)
    mode = sta.get("mode", "disabled")
    applied = sta.get("applied") or []
    blocked = sta.get("blocked") or []

    if not enabled or mode == "disabled":
        report["skipped"].append(
            f"subtitle_text_apply:disabled_phase33"
            f"(applied={len(applied)},blocked={len(blocked)})"
        )
        report["skipped"].append("subtitle_timestamp_rewrite:always_blocked_phase33")
        logger.debug("subtitle_text_apply_reported disabled")
        return

    for opt in applied:
        if not isinstance(opt, dict):
            continue
        apply_id = str(opt.get("apply_id") or "")
        opt_type = str(opt.get("optimization_type") or "")
        changes = opt.get("changes") or {}
        changes_str = ",".join(f"{k}={v}" for k, v in list(changes.items())[:3])
        report["applied"].append(
            f"subtitle_text_apply:applied({apply_id},{opt_type}:[{changes_str}])"
        )
        logger.info(
            "ai_subtitle_text_optimization_applied apply_id=%s type=%s",
            apply_id, opt_type,
        )

    for opt in blocked:
        if not isinstance(opt, dict):
            continue
        apply_id = str(opt.get("apply_id") or "")
        opt_type = str(opt.get("optimization_type") or "")
        warns = opt.get("warnings") or ["blocked"]
        reason = warns[0] if warns else "blocked"
        report["skipped"].append(
            f"subtitle_text_apply:blocked({apply_id},{opt_type}:{reason})"
        )
        logger.info(
            "ai_subtitle_text_optimization_blocked apply_id=%s reason=%s",
            apply_id, reason,
        )

    # Safety invariant always reported
    report["skipped"].append("subtitle_timestamp_rewrite:always_blocked_phase33")
    logger.debug(
        "subtitle_text_apply_reported applied=%d blocked=%d",
        len(applied), len(blocked),
    )


# ── Camera motion apply — applied/blocked summary in Phase 34 ────────────────

def _report_camera_motion_apply(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report camera motion apply results from Phase 34.

    Applied guidance appears in report["applied"] as bounded metadata descriptors.
    Blocked guidance and the direct crop-coordinate safety invariant go to report["skipped"].
    Payload is never mutated. No crop coordinates changed. No FFmpeg mutation.
    """
    cma = getattr(edit_plan, "camera_motion_apply", None)
    if not isinstance(cma, dict) or not cma:
        report["skipped"].append("camera_motion_apply:no_result")
        return

    enabled = cma.get("enabled", False)
    mode = cma.get("mode", "disabled")
    applied = cma.get("applied") or []
    blocked = cma.get("blocked") or []

    if not enabled or mode == "disabled":
        report["skipped"].append(
            f"camera_motion_apply:disabled_phase34"
            f"(applied={len(applied)},blocked={len(blocked)})"
        )
        report["skipped"].append("direct_crop_coordinate_rewrite:always_blocked_phase34")
        logger.debug("camera_motion_apply_reported disabled")
        return

    for cam in applied:
        if not isinstance(cam, dict):
            continue
        apply_id = str(cam.get("apply_id") or "")
        cam_type = str(cam.get("camera_type") or "")
        changes = cam.get("changes") or {}
        changes_str = ",".join(f"{k}={v}" for k, v in list(changes.items())[:3])
        report["applied"].append(
            f"camera_motion_apply:applied({apply_id},{cam_type}:[{changes_str}])"
        )
        logger.info(
            "ai_camera_motion_guidance_applied apply_id=%s type=%s",
            apply_id, cam_type,
        )

    for cam in blocked:
        if not isinstance(cam, dict):
            continue
        apply_id = str(cam.get("apply_id") or "")
        cam_type = str(cam.get("camera_type") or "")
        warns = cam.get("warnings") or ["blocked"]
        reason = warns[0] if warns else "blocked"
        report["skipped"].append(
            f"camera_motion_apply:blocked({apply_id},{cam_type}:{reason})"
        )
        logger.info(
            "ai_camera_motion_guidance_blocked apply_id=%s reason=%s",
            apply_id, reason,
        )

    # Safety invariant always reported
    report["skipped"].append("direct_crop_coordinate_rewrite:always_blocked_phase34")
    logger.debug(
        "camera_motion_apply_reported applied=%d blocked=%d",
        len(applied), len(blocked),
    )


# ── Clip candidate discovery — discovery_only reporting in Phase 35 ──────────

def _report_clip_candidate_discovery(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report clip candidate discovery metadata — discovery_only in Phase 35.

    No actual clips are cut. No segments mutated. No FFmpeg altered.
    No playback_speed changed. No subtitle timing rewritten.
    """
    ccd = getattr(edit_plan, "clip_candidate_discovery", None)
    if not isinstance(ccd, dict) or not ccd:
        report["skipped"].append("clip_candidate_discovery:no_result")
        return

    enabled = ccd.get("enabled", False)
    candidates = ccd.get("candidates") or []
    recommended = ccd.get("recommended_candidate_id") or "none"
    safe_count = sum(
        1 for c in candidates if isinstance(c, dict) and c.get("safe", False)
    )

    if not enabled:
        report["skipped"].append(
            f"clip_candidate_discovery:disabled_phase35"
            f"(candidates={len(candidates)},recommended={recommended!r})"
        )
    else:
        report["skipped"].append(
            f"clip_candidate_discovery:discovery_only_phase35"
            f"(candidates={len(candidates)},safe={safe_count},"
            f"recommended={recommended!r})"
        )

    logger.debug(
        "clip_candidate_discovery_reported enabled=%s candidates=%d recommended=%s",
        enabled, len(candidates), recommended,
    )


# ── Clip segment selection — selection_only reporting in Phase 36 ────────────

def _report_clip_segment_selection(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report clip segment selection metadata — selection_only in Phase 36.

    No actual clips are rendered. No source segments mutated. No FFmpeg altered.
    No playback_speed changed. No subtitle timing rewritten.
    """
    css = getattr(edit_plan, "clip_segment_selection", None)
    if not isinstance(css, dict) or not css:
        report["skipped"].append("clip_segment_selection:no_result")
        return

    enabled  = css.get("enabled", False)
    selected = css.get("selected_segments") or []
    rejected = css.get("rejected_candidates") or []
    safe_count = sum(
        1 for s in selected if isinstance(s, dict) and s.get("safe", False)
    )

    if not enabled:
        report["skipped"].append(
            f"clip_segment_selection:disabled_phase36"
            f"(selected={len(selected)},rejected={len(rejected)})"
        )
    else:
        report["skipped"].append(
            f"clip_segment_selection:selection_only_phase36"
            f"(selected={len(selected)},safe={safe_count},"
            f"rejected={len(rejected)})"
        )

    logger.debug(
        "clip_segment_selection_reported enabled=%s selected=%d rejected=%d",
        enabled, len(selected), len(rejected),
    )


def _report_clip_batch_planning(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report batch planning metadata — planning_only in Phase 37.

    No batch renders executed. No jobs enqueued. No FFmpeg altered.
    No playback_speed changed. No subtitle timing rewritten.
    """
    cbp = getattr(edit_plan, "clip_batch_planning", None)
    if not isinstance(cbp, dict) or not cbp:
        report["skipped"].append("clip_batch_planning:no_result")
        return

    enabled = cbp.get("enabled", False)
    plans = cbp.get("plans") or []
    recommended = cbp.get("recommended_plan_ids") or []
    safe_count = sum(
        1 for p in plans if isinstance(p, dict) and p.get("safe", False)
    )

    if not enabled:
        report["skipped"].append(
            f"clip_batch_planning:disabled_phase37"
            f"(plans={len(plans)},recommended={len(recommended)})"
        )
    else:
        report["skipped"].append(
            f"clip_batch_planning:planning_only_phase37"
            f"(plans={len(plans)},safe={safe_count},"
            f"recommended={len(recommended)})"
        )

    logger.debug(
        "clip_batch_planning_reported enabled=%s plans=%d recommended=%d",
        enabled, len(plans), len(recommended),
    )


# ── Explainability update ─────────────────────────────────────────────────────

def _update_explainability(edit_plan: Any, report: dict) -> None:
    """Append a compact AI influence status line to the existing explainability summary.

    Cosmetic-only — never raises, failure is silently ignored.
    """
    try:
        explainability = getattr(edit_plan, "explainability", None)
        if not isinstance(explainability, dict):
            return
        summary = explainability.get("summary")
        if not isinstance(summary, dict):
            return
        lines = summary.get("summary_lines")
        if not isinstance(lines, list):
            return

        n_applied = len(report.get("applied", []))
        line = (
            f"AI render influence applied safely ({n_applied} adjustment"
            + ("s" if n_applied != 1 else "")
            + ")"
            if n_applied > 0
            else "AI render influence enabled (no adjustments needed)"
        )
        if not any("AI render influence" in str(l) for l in lines):
            lines.append(line)

        beat_exec = getattr(edit_plan, "beat_execution", None)
        if isinstance(beat_exec, dict) and beat_exec.get("beat_available"):
            if beat_exec.get("enabled"):
                beat_line = "Beat-aware execution planned safely"
            else:
                beat_warns = beat_exec.get("warnings", [])
                reason = beat_warns[0] if beat_warns else "beat data unavailable"
                beat_line = f"Beat execution skipped: {reason}"
            if not any("Beat" in str(l) for l in lines):
                lines.append(beat_line)
    except Exception:
        pass


def _report_feature_enhancement(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report feature enhancement metadata — assistive_only in Phase 38.

    No render execution. No FFmpeg altered. No playback_speed changed.
    No subtitle timing rewritten. AI enhances existing features only.
    """
    feh = getattr(edit_plan, "feature_enhancement", None)
    if not isinstance(feh, dict) or not feh:
        report["skipped"].append("feature_enhancement:no_result")
        return

    available = feh.get("available", False)
    mode = feh.get("mode", "assistive_only")

    categories = []
    for key in (
        "subtitle_enhancement", "camera_enhancement", "timing_enhancement",
        "clip_selection_enhancement", "creator_style_enhancement",
        "variant_enhancement", "output_ranking_enhancement",
    ):
        enh = feh.get(key, {})
        if isinstance(enh, dict) and enh.get("enabled", False):
            categories.append(key.replace("_enhancement", ""))

    if not available:
        report["skipped"].append("feature_enhancement:unavailable_phase38")
    else:
        report["skipped"].append(
            f"feature_enhancement:{mode}_phase38"
            f"(categories={len(categories)}:{','.join(categories) or 'none'})"
        )

    logger.debug(
        "feature_enhancement_reported mode=%s categories=%d",
        mode, len(categories),
    )


def _report_creator_retrieval(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report creator intelligence retrieval metadata — assistive_only in Phase 41.

    No render execution. No FFmpeg altered. No playback_speed changed.
    No subtitle timing rewritten. Creator intelligence influences metadata only.
    """
    cr = getattr(edit_plan, "creator_retrieval", None)
    if not isinstance(cr, dict) or not cr:
        report["skipped"].append("creator_retrieval:no_result")
        return

    available = cr.get("available", False)
    enabled = cr.get("enabled", False)
    mode = cr.get("retrieval_mode", "assistive_only")
    matches = cr.get("matches", [])
    recommended_style = cr.get("recommended_creator_style", "")

    if not isinstance(matches, list):
        matches = []

    # Collect retrieved influence categories
    influence_categories = set()
    retrieved_styles = set()
    for m in matches:
        if not isinstance(m, dict):
            continue
        ptype = m.get("pattern_type", "")
        if ptype:
            influence_categories.add(ptype)
        style = m.get("creator_style", "")
        if style:
            retrieved_styles.add(style)

    if not available:
        report["skipped"].append("creator_retrieval:unavailable_phase41")
    elif not enabled or not matches:
        report["skipped"].append("creator_retrieval:assistive_only_phase41(no_matches)")
    else:
        cats_str = ",".join(sorted(influence_categories)) or "none"
        styles_str = ",".join(sorted(retrieved_styles)) or "none"
        report["skipped"].append(
            f"creator_retrieval:{mode}_phase41"
            f"(matches={len(matches)},categories={cats_str}"
            f",styles={styles_str},recommended={recommended_style or 'none'})"
        )

    logger.debug(
        "creator_retrieval_reported mode=%s matches=%d categories=%s",
        mode, len(matches), sorted(influence_categories),
    )


# ── Adaptive creator intelligence — assistive_only advisory in Phase 42 ──────

def _report_adaptive_creator_intelligence(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report adaptive creator learning metadata — assistive_only in Phase 42.

    No render execution. No FFmpeg altered. No playback_speed changed.
    No subtitle timing rewritten. No executor override.
    Adaptive influences are metadata-only and bounded.
    """
    aci = getattr(edit_plan, "adaptive_creator_intelligence", None)
    if not isinstance(aci, dict) or not aci:
        report["skipped"].append("adaptive_creator_intelligence:no_result")
        return

    available = aci.get("available", False)
    enabled = aci.get("enabled", False)
    mode = aci.get("learning_mode", "assistive_only")

    learned = aci.get("learned_preferences", {}) or {}
    influences = aci.get("adaptive_influences", {}) or {}
    profile = aci.get("creator_profile", {}) or {}

    style = profile.get("creator_style_preference", "")
    subtitle = profile.get("preferred_subtitle_style", "")
    pacing = profile.get("preferred_pacing_style", "")
    camera = profile.get("preferred_camera_style", "")
    history = learned.get("history", {}) or {}
    selections = history.get("selections", 0)
    exports = history.get("exports", 0)

    retrieval_w = influences.get("retrieval_ranking_weight", 0.0)
    subtitle_w = influences.get("subtitle_enhancement_weight", 0.0)
    pacing_w = influences.get("pacing_enhancement_weight", 0.0)
    camera_w = influences.get("camera_enhancement_weight", 0.0)

    if not available:
        report["skipped"].append("adaptive_creator_intelligence:unavailable_phase42")
    elif not enabled:
        report["skipped"].append(
            f"adaptive_creator_intelligence:assistive_only_phase42"
            f"(mode={mode},selections={selections})"
        )
    else:
        report["skipped"].append(
            f"adaptive_creator_intelligence:{mode}_phase42"
            f"(style={style!r},subtitle={subtitle!r},pacing={pacing!r}"
            f",camera={camera!r},selections={selections},exports={exports}"
            f",retrieval_w={retrieval_w:.3f},subtitle_w={subtitle_w:.3f}"
            f",pacing_w={pacing_w:.3f},camera_w={camera_w:.3f})"
        )

    logger.debug(
        "adaptive_creator_intelligence_reported mode=%s enabled=%s style=%s selections=%d",
        mode, enabled, style, selections,
    )


# ── Creator feedback intelligence — assistive_only advisory in Phase 43 ──────

def _report_creator_feedback_intelligence(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report creator feedback learning metadata — assistive_only in Phase 43.

    No render execution. No FFmpeg altered. No playback_speed changed.
    No subtitle timing rewritten. No executor override.
    Feedback influences are metadata-only and bounded.
    """
    cfi = getattr(edit_plan, "creator_feedback_intelligence", None)
    if not isinstance(cfi, dict) or not cfi:
        report["skipped"].append("creator_feedback_intelligence:no_result")
        return

    available = cfi.get("available", False)
    enabled = cfi.get("enabled", False)
    mode = cfi.get("feedback_mode", "assistive_only")

    patterns = cfi.get("learned_feedback_patterns", {}) or {}
    biases = cfi.get("ranking_biases", {}) or {}

    total_signals = patterns.get("total_signals", 0)
    total_exports = patterns.get("total_exports", 0)
    total_ignores = patterns.get("total_ignores", 0)
    dominant_style = patterns.get("dominant_creator_style", "")

    output_bias = biases.get("output_ranking_bias", 0.0)
    variant_bias = biases.get("variant_ranking_bias", 0.0)
    retrieval_bias = biases.get("retrieval_weighting_bias", 0.0)
    subtitle_bias = biases.get("subtitle_weighting_bias", 0.0)
    pacing_bias = biases.get("pacing_weighting_bias", 0.0)
    camera_bias = biases.get("camera_weighting_bias", 0.0)

    if not available:
        report["skipped"].append("creator_feedback_intelligence:unavailable_phase43")
    elif not enabled:
        report["skipped"].append(
            f"creator_feedback_intelligence:assistive_only_phase43"
            f"(mode={mode},signals={total_signals})"
        )
    else:
        report["skipped"].append(
            f"creator_feedback_intelligence:{mode}_phase43"
            f"(signals={total_signals},exports={total_exports},ignores={total_ignores}"
            f",style={dominant_style!r}"
            f",output_bias={output_bias:.3f},variant_bias={variant_bias:.3f}"
            f",retrieval_bias={retrieval_bias:.3f},subtitle_bias={subtitle_bias:.3f}"
            f",pacing_bias={pacing_bias:.3f},camera_bias={camera_bias:.3f})"
        )

    logger.debug(
        "creator_feedback_intelligence_reported mode=%s enabled=%s signals=%d exports=%d",
        mode, enabled, total_signals, total_exports,
    )


# ── Market optimization intelligence — assistive_only advisory in Phase 44 ───

def _report_market_optimization_intelligence(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report market optimization metadata — assistive_only in Phase 44.

    No render execution. No FFmpeg altered. No playback_speed changed.
    No subtitle timing rewritten. No executor override.
    Market biases are metadata-only and bounded.
    """
    moi = getattr(edit_plan, "market_optimization_intelligence", None)
    if not isinstance(moi, dict) or not moi:
        report["skipped"].append("market_optimization_intelligence:no_result")
        return

    available = moi.get("available", False)
    enabled = moi.get("enabled", False)
    mode = moi.get("optimization_mode", "assistive_only")
    target = moi.get("target_market", "")

    sub_bias = moi.get("subtitle_market_bias", {}) or {}
    pac_bias = moi.get("pacing_market_bias", {}) or {}
    cam_bias = moi.get("camera_market_bias", {}) or {}
    hook_bias = moi.get("hook_market_bias", {}) or {}

    sub_w = sub_bias.get("weight", 0.0)
    pac_w = pac_bias.get("weight", 0.0)
    cam_w = cam_bias.get("weight", 0.0)
    hook_w = hook_bias.get("weight", 0.0)

    sub_style = sub_bias.get("preferred_style", "")
    pac_style = pac_bias.get("preferred_style", "")
    cam_style = cam_bias.get("preferred_style", "")

    if not available:
        report["skipped"].append("market_optimization_intelligence:unavailable_phase44")
    elif not enabled:
        report["skipped"].append(
            f"market_optimization_intelligence:assistive_only_phase44"
            f"(mode={mode},market={target!r})"
        )
    else:
        report["skipped"].append(
            f"market_optimization_intelligence:{mode}_phase44"
            f"(market={target!r}"
            f",subtitle={sub_style!r},subtitle_w={sub_w:.3f}"
            f",pacing={pac_style!r},pacing_w={pac_w:.3f}"
            f",camera={cam_style!r},camera_w={cam_w:.3f}"
            f",hook_w={hook_w:.3f})"
        )

    logger.debug(
        "market_optimization_intelligence_reported mode=%s enabled=%s market=%s sub_w=%.3f pac_w=%.3f",
        mode, enabled, target, sub_w, pac_w,
    )


# ── Render quality evaluation — evaluation_only advisory in Phase 45 ─────────

def _report_render_quality_evaluation(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report render quality evaluation metadata — evaluation_only in Phase 45.

    No render execution. No file mutation. No output deletion.
    Quality scores are metadata-only and bounded 0–100.
    """
    rqe = getattr(edit_plan, "render_quality_evaluation", None)
    if not isinstance(rqe, dict) or not rqe:
        report["skipped"].append("render_quality_evaluation:no_result")
        return

    available = rqe.get("available", False)
    enabled = rqe.get("enabled", False)
    mode = rqe.get("evaluation_mode", "evaluation_only")

    output_scores = rqe.get("output_scores") or []
    best_id = rqe.get("best_quality_output_id", "")

    if not available:
        report["skipped"].append("render_quality_evaluation:unavailable_phase45")
    elif not enabled:
        report["skipped"].append(
            f"render_quality_evaluation:pending_post_render_phase45"
            f"(mode={mode})"
        )
    else:
        report["skipped"].append(
            f"render_quality_evaluation:{mode}_phase45"
            f"(outputs_scored={len(output_scores)},best_id={best_id!r})"
        )

    logger.debug(
        "render_quality_evaluation_reported mode=%s enabled=%s outputs=%d best_id=%s",
        mode, enabled, len(output_scores), best_id,
    )


# ── Creator preset evolution — assistive_only advisory in Phase 46 ────────────

def _report_creator_preset_evolution(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report creator preset evolution metadata — assistive_only in Phase 46.

    No render execution. No FFmpeg altered. No playback_speed changed.
    No subtitle timing rewritten. No executor override.
    Preset evolution is metadata-only and assistive.
    """
    cpe = getattr(edit_plan, "creator_preset_evolution", None)
    if not isinstance(cpe, dict) or not cpe:
        report["skipped"].append("creator_preset_evolution:no_result")
        return

    available = cpe.get("available", False)
    enabled = cpe.get("enabled", False)
    mode = cpe.get("evolution_mode", "assistive_only")

    recommended = cpe.get("recommended_presets") or []
    evolved = cpe.get("evolved_presets") or []
    best_preset_id = cpe.get("best_preset_id", "")

    if not available:
        report["skipped"].append("creator_preset_evolution:unavailable_phase46")
    elif not enabled:
        report["skipped"].append(
            f"creator_preset_evolution:assistive_only_phase46"
            f"(mode={mode})"
        )
    else:
        report["skipped"].append(
            f"creator_preset_evolution:{mode}_phase46"
            f"(recommended={len(recommended)},evolved={len(evolved)}"
            f",best_preset={best_preset_id!r})"
        )

    logger.debug(
        "creator_preset_evolution_reported mode=%s enabled=%s recommended=%d evolved=%d best=%s",
        mode, enabled, len(recommended), len(evolved), best_preset_id,
    )


def _report_multi_signal_orchestration(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report multi-signal orchestration metadata — reasoning_only in Phase 47.

    No render execution. No FFmpeg altered. No playback_speed changed.
    No subtitle timing rewritten. No executor override.
    Orchestration is metadata-only and reasoning-only.
    """
    mso = getattr(edit_plan, "multi_signal_orchestration", None)
    if not isinstance(mso, dict) or not mso:
        report["skipped"].append("multi_signal_orchestration:no_result")
        return

    available = mso.get("available", False)
    enabled = mso.get("enabled", False)
    mode = mso.get("orchestration_mode", "reasoning_only")

    if not available:
        report["skipped"].append("multi_signal_orchestration:unavailable_phase47")
        return

    confidence_scores = mso.get("confidence_scores") or {}
    agg_conf = float(confidence_scores.get("aggregate_confidence") or 0.0)
    active = int((mso.get("aggregated_signals") or {}).get("active_signal_count") or 0)

    if not enabled:
        report["skipped"].append(
            f"multi_signal_orchestration:{mode}_phase47"
            f"(active_signals={active},confidence={round(agg_conf, 3)})"
        )
    else:
        rec_strategy = mso.get("recommended_strategy") or {}
        subtitle = str(rec_strategy.get("subtitle_style") or "")
        camera = str(rec_strategy.get("camera_motion") or "")
        hook = str(rec_strategy.get("hook_emphasis") or "")
        report["skipped"].append(
            f"multi_signal_orchestration:{mode}_phase47"
            f"(active_signals={active}"
            f",confidence={round(agg_conf, 3)}"
            f",subtitle={subtitle!r}"
            f",camera={camera!r}"
            f",hook={hook!r})"
        )

    logger.debug(
        "multi_signal_orchestration_reported mode=%s enabled=%s active=%d confidence=%.3f",
        mode, enabled, active, agg_conf,
    )


def _report_safe_influence_pack(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report safe influence pack metadata — safe_controlled in Phase 48.

    No render execution. No FFmpeg altered. No playback_speed changed.
    No subtitle timing rewritten. No executor override.
    Influence is metadata-only and recommendation-only.
    """
    sip = getattr(edit_plan, "safe_influence_pack", None)
    if not isinstance(sip, dict) or not sip:
        report["skipped"].append("safe_influence_pack:no_result")
        return

    available = sip.get("available", False)
    enabled = sip.get("enabled", False)
    mode = sip.get("influence_mode", "safe_controlled")

    if not available:
        report["skipped"].append("safe_influence_pack:unavailable_phase48")
        return

    conf = float(sip.get("confidence") or 0.0)
    gate = sip.get("gate") or {}
    tier = str(gate.get("tier") or "")

    if not enabled:
        gate_reason = str(gate.get("reason") or "")
        report["skipped"].append(
            f"safe_influence_pack:{mode}_phase48"
            f"(enabled=False,tier={tier!r},reason={gate_reason!r})"
        )
    else:
        safe_inf = sip.get("safe_influence") or {}
        subtitle_style = str(safe_inf.get("subtitle_style_bias") or "")
        subtitle_density = str(safe_inf.get("subtitle_density_bias") or "")
        camera = str(safe_inf.get("camera_motion_bias") or "")
        ranking = str(safe_inf.get("ranking_priority_bias") or "")
        market = str((sip.get("market_weights") or {}).get("target_market") or "")
        report["skipped"].append(
            f"safe_influence_pack:{mode}_phase48"
            f"(tier={tier!r}"
            f",confidence={round(conf, 3)}"
            f",subtitle_style={subtitle_style!r}"
            f",subtitle_density={subtitle_density!r}"
            f",camera={camera!r}"
            f",ranking={ranking!r}"
            f",market={market!r})"
        )

    logger.debug(
        "safe_influence_pack_reported mode=%s enabled=%s tier=%s confidence=%.3f",
        mode, enabled, tier, conf,
    )


def _report_creator_subtitle_preference(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report creator subtitle preference metadata — inference_only in Phase 50A.

    No render execution. No subtitle engine rewrite. No timing rewrite.
    No FFmpeg altered. No executor override.
    Subtitle preference is metadata-only and inference-only.
    """
    csp = getattr(edit_plan, "creator_subtitle_preference", None)
    if not isinstance(csp, dict) or not csp:
        report["skipped"].append("creator_subtitle_preference:no_result_phase50a")
        return

    available = csp.get("available", False)
    if not available:
        report["skipped"].append("creator_subtitle_preference:unavailable_phase50a")
        return

    pref = csp.get("subtitle_preference") or {}
    style = str(pref.get("style") or "unknown")
    density = str(pref.get("density") or "unknown")
    emphasis = str(pref.get("keyword_emphasis") or "unknown")
    conf = float(pref.get("confidence") or 0.0)
    signal_count = len(pref.get("signals") or [])

    # Phase 50A always reports to skipped — inference-only, no render execution.
    report["skipped"].append(
        f"creator_subtitle_preference:inference_only_phase50a"
        f"(style={style!r}"
        f",density={density!r}"
        f",emphasis={emphasis!r}"
        f",confidence={round(conf, 3)}"
        f",signals={signal_count})"
    )

    logger.debug(
        "creator_subtitle_preference_reported style=%s density=%s confidence=%.3f",
        style, density, conf,
    )


def _report_creator_camera_preference(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report creator camera preference metadata — inference_only in Phase 50B.

    No render execution. No motion_crop rewrite. No tracking rewrite.
    No FFmpeg altered. No executor override.
    Camera preference is metadata-only and inference-only.
    """
    ccp = getattr(edit_plan, "creator_camera_preference", None)
    if not isinstance(ccp, dict) or not ccp:
        report["skipped"].append("creator_camera_preference:no_result_phase50b")
        return

    available = ccp.get("available", False)
    if not available:
        report["skipped"].append("creator_camera_preference:unavailable_phase50b")
        return

    pref = ccp.get("camera_preference") or {}
    tuning = ccp.get("tuning_pack") or {}
    style = pref.get("motion_style", "unknown")
    stability = pref.get("stability_priority", "unknown")
    conf = float(pref.get("confidence") or 0.0)
    tier = tuning.get("confidence_tier", "low")
    applied = bool(tuning.get("applied", False))
    signal_count = len(pref.get("signals") or [])

    # Phase 50B always reports to skipped — inference-only, no render execution.
    report["skipped"].append(
        f"creator_camera_preference:inference_only_phase50b"
        f"(style={style!r}"
        f",stability={stability!r}"
        f",confidence={round(conf, 3)}"
        f",tier={tier!r}"
        f",tuning_applied={applied}"
        f",signals={signal_count})"
    )

    logger.debug(
        "creator_camera_preference_reported style=%s stability=%s confidence=%.3f tier=%s",
        style, stability, conf, tier,
    )


def _report_creator_subtitle_influence(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report creator subtitle influence metadata — influence_ready in Phase 50C.

    No render execution. No subtitle engine rewrite. No ASS generation rewrite.
    No subtitle timing rewrite. No segmentation rewrite. No FFmpeg altered.
    No executor override. Subtitle influence is metadata-only.
    """
    csi = getattr(edit_plan, "creator_subtitle_influence", None)
    if not isinstance(csi, dict) or not csi:
        report["skipped"].append("creator_subtitle_influence:no_result_phase50c")
        return

    available = csi.get("available", False)
    if not available:
        report["skipped"].append(
            f"creator_subtitle_influence:unavailable_phase50c"
            f"(tier={csi.get('confidence_tier', 'low')!r})"
        )
        return

    tier      = csi.get("confidence_tier",          "low")
    bias      = csi.get("preset_bias",               "unknown")
    strength  = float(csi.get("preset_bias_strength", 0.0))
    nudge     = csi.get("density_nudge",             "none")
    emp_delta = float(csi.get("emphasis_delta",       0.0))
    motion    = csi.get("motion_style_bias",          "unknown")
    mob_nudge = float(csi.get("mobile_readability_nudge", 0.0))

    # Phase 50C always reports to skipped — bounded influence metadata only,
    # no render execution path activated.
    report["skipped"].append(
        f"creator_subtitle_influence:influence_ready_phase50c"
        f"(tier={tier!r}"
        f",preset_bias={bias!r}"
        f",bias_strength={round(strength, 3)}"
        f",density_nudge={nudge!r}"
        f",emphasis_delta={round(emp_delta, 3):+}"
        f",motion_bias={motion!r}"
        f",mobile_nudge={round(mob_nudge, 3)})"
    )

    logger.debug(
        "creator_subtitle_influence_reported tier=%s preset_bias=%s density_nudge=%s emphasis_delta=%.3f",
        tier, bias, nudge, emp_delta,
    )


def _report_creator_preference_profile(payload: Any, edit_plan: Any, report: dict) -> None:
    """Report unified creator preference fusion metadata — fused_phase50d in Phase 50D.

    No render execution. No subtitle engine rewrite. No motion_crop rewrite.
    No FFmpeg altered. No executor override.
    Creator preference fusion is advisory metadata only.
    """
    cpp = getattr(edit_plan, "creator_preference_profile", None)
    if not isinstance(cpp, dict) or not cpp:
        report["skipped"].append("creator_preference_profile:no_result_phase50d")
        return

    available = cpp.get("available", False)
    if not available:
        report["skipped"].append("creator_preference_profile:unavailable_phase50d")
        return

    sub_style      = (cpp.get("subtitle") or {}).get("style",        "unknown")
    cam_motion     = (cpp.get("camera")   or {}).get("motion_style", "unknown")
    content_style  = (cpp.get("clip")     or {}).get("content_style","unknown")
    market_fit     = (cpp.get("market_alignment") or {}).get("market_fit", "unknown")
    confidence     = float(cpp.get("confidence") or 0.0)
    n_conflicts    = len(cpp.get("conflicts_resolved") or [])

    # Phase 50D always reports to skipped — advisory metadata only, no execution path.
    report["skipped"].append(
        f"creator_preference_profile:fused_phase50d"
        f"(subtitle_style={sub_style!r}"
        f",camera_motion={cam_motion!r}"
        f",content_style={content_style!r}"
        f",market_fit={market_fit!r}"
        f",confidence={round(confidence, 3)}"
        f",conflicts_resolved={n_conflicts})"
    )

    logger.debug(
        "creator_preference_profile_reported subtitle=%s camera=%s confidence=%.3f conflicts=%d",
        sub_style, cam_motion, confidence, n_conflicts,
    )
