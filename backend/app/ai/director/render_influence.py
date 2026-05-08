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
