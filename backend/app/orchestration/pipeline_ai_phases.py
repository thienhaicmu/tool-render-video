"""
pipeline_ai_phases.py — AI advisory phases extracted from run_render_pipeline().

Extracted from render_pipeline.py (Phase A-2). No behavior change.
All functions are pure advisory — they mutate ai_edit_plan metadata fields or return
updated local state. None of them touch FFmpeg, modify SRT files, or alter render output.

Each function wraps its phase in the same try/except that existed inline — failure is
silent, advisory, and never crashes the render.
"""

import logging

from app.orchestration.render_events import _job_log, _emit_render_event
from app.orchestration.pipeline_segment_selection import _map_ai_segments_to_scored

logger = logging.getLogger("app.render")


# ---------------------------------------------------------------------------
# Phase 43 — Creator feedback learning pack (advisory metadata only)
# ---------------------------------------------------------------------------

def run_phase_43_feedback_learning(ai_edit_plan, payload, job_id: str, channel: str) -> None:
    """Build creator feedback learning pack and attach to ai_edit_plan."""
    if ai_edit_plan is None or not getattr(payload, "ai_director_enabled", False):
        return
    try:
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        _feedback_pack = build_feedback_learning_pack(
            ai_edit_plan,
            payload=payload,
            context={"job_id": job_id},
        )
        if _feedback_pack is not None:
            ai_edit_plan.creator_feedback_intelligence = _feedback_pack.to_dict()
            _job_log(
                channel, job_id,
                f"feedback_learning: {len(getattr(_feedback_pack, 'feedback_signals', []))} signals, "
                f"{len(getattr(_feedback_pack, 'ranking_biases', []))} biases computed",
                kind="info",
            )
    except Exception as _fb_err:
        _job_log(channel, job_id, f"feedback_learning_skipped: {_fb_err}", kind="warning")


# ---------------------------------------------------------------------------
# Phase 44 — AI content-driven segment selection
# ---------------------------------------------------------------------------

def run_phase_44_content_selection(
    ai_edit_plan, scored: list, payload, channel: str, job_id: str
) -> list:
    """Replace heuristic scored[] with AI Director content-aware selections.

    Returns the updated scored list. Returns the original scored list unchanged
    if the phase is not eligible or fails.
    """
    if not (
        getattr(payload, "ai_content_driven_selection", False)
        and ai_edit_plan is not None
        and not ai_edit_plan.fallback_used
        and ai_edit_plan.selected_segments
    ):
        return scored
    try:
        _ai_mapped = _map_ai_segments_to_scored(ai_edit_plan.selected_segments, scored)
        if _ai_mapped:
            _job_log(
                channel, job_id,
                f"phase44_ai_content_selection: ai_clips={len(_ai_mapped)} "
                f"replaced heuristic={len(scored)} "
                f"(ai_mode={ai_edit_plan.mode})",
                kind="info",
            )
            _emit_render_event(
                channel_code=channel, job_id=job_id,
                event="ai_content_selection_applied",
                level="INFO",
                message=f"Phase 44: AI content-driven selection active — {len(_ai_mapped)} clips",
                step="ai_director.selection",
                context={
                    "ai_clips": len(_ai_mapped),
                    "heuristic_clips": len(scored),
                    "ai_mode": ai_edit_plan.mode,
                },
            )
            return _ai_mapped
        else:
            _job_log(
                channel, job_id,
                "phase44_ai_content_selection_empty: fallback to heuristic scored[]",
                kind="warning",
            )
    except Exception as _p44_err:
        _job_log(
            channel, job_id,
            f"phase44_ai_content_selection_failed: {_p44_err} — heuristic scored[] unchanged",
            kind="warning",
        )
    return scored


# ---------------------------------------------------------------------------
# Phase 60D — AI execution mode resolution + mode-off rollback
# ---------------------------------------------------------------------------

def run_phase_60d_execution_mode(ai_edit_plan, payload, job_id: str) -> str:
    """Resolve AI execution mode. Returns effective mode string (default 'safe').

    Must run BEFORE Phase 59 blocks so they can be gated correctly.
    """
    if ai_edit_plan is None:
        return "safe"
    try:
        from app.ai.execution_mode.execution_mode_engine import (
            resolve_execution_mode as _resolve_exec_mode,
        )
        _mode_result = _resolve_exec_mode(payload, context={"job_id": job_id})
        _mode_data = _mode_result.get("ai_execution_mode") or {}
        _mode = str(_mode_data.get("effective_mode") or "safe")
        try:
            ai_edit_plan.ai_execution_mode = _mode_data
        except Exception:
            pass
        logger.info(
            "ai_execution_mode_resolved job_id=%s mode=%s source=%s",
            job_id, _mode, _mode_data.get("source", "unknown"),
        )
        return _mode
    except Exception as _mode_err:
        logger.warning(
            "ai_execution_mode_resolution_failed job_id=%s: %s", job_id, _mode_err
        )
        return "safe"


def run_phase_60d_mode_off_rollback(ai_edit_plan, ai_exec_mode: str, job_id: str) -> None:
    """Write rollback metadata and stub promotion reports when mode=off."""
    if ai_edit_plan is None or ai_exec_mode != "off":
        return
    _rollback = {
        "active":          True,
        "reason":          "mode_off",
        "blocked_domains": ["subtitle", "camera", "segment"],
    }
    try:
        ai_edit_plan.ai_execution_rollback = _rollback
    except Exception:
        pass
    _mode_off_stub = {
        "applied":  False,
        "eligible": True,
        "reason":   "mode_off",
        "blocked":  True,
        "confidence": 0.0,
    }
    try:
        ai_edit_plan.subtitle_execution_promotion = dict(_mode_off_stub)
        ai_edit_plan.camera_execution_promotion   = dict(_mode_off_stub)
        ai_edit_plan.segment_selection_promotion  = dict(_mode_off_stub)
    except Exception:
        pass
    logger.info(
        "ai_execution_rollback_active job_id=%s reason=mode_off blocked=subtitle,camera,segment",
        job_id,
    )


# ---------------------------------------------------------------------------
# Phase 11 — AI Beat Execution (metadata-only beat plan)
# ---------------------------------------------------------------------------

def run_phase_11_beat_execution(ai_edit_plan, payload, job_id: str) -> dict:
    """Build beat execution plan. Returns beat report dict."""
    if ai_edit_plan is None or not getattr(payload, "ai_beat_execution_enabled", False):
        return {"enabled": False}
    beat_exec_cached = getattr(ai_edit_plan, "beat_execution", None)
    if isinstance(beat_exec_cached, dict) and beat_exec_cached.get("beat_available"):
        logger.info(
            "ai_beat_execution_planned job_id=%s bpm=%s count=%d enabled=%s",
            job_id,
            beat_exec_cached.get("bpm"),
            beat_exec_cached.get("beat_count", 0),
            beat_exec_cached.get("enabled", False),
        )
        return beat_exec_cached
    try:
        from app.ai.director.beat_execution import build_beat_execution_plan as _build_beat
        _ai_beat_report = _build_beat(ai_edit_plan, payload, context={"job_id": job_id})
        ai_edit_plan.beat_execution = _ai_beat_report
        logger.info(
            "ai_beat_execution_planned job_id=%s bpm=%s count=%d enabled=%s",
            job_id,
            _ai_beat_report.get("bpm"),
            _ai_beat_report.get("beat_count", 0),
            _ai_beat_report.get("enabled", False),
        )
        return _ai_beat_report
    except Exception as _beat_err:
        _ai_beat_report = {
            "enabled": False,
            "warnings": [f"beat_execution_module_error:{type(_beat_err).__name__}"],
        }
        logger.warning("ai_beat_execution_module_failed job_id=%s: %s", job_id, _beat_err)
        return _ai_beat_report


# ---------------------------------------------------------------------------
# Phase 60A — AI Execution Metrics (observability only)
# ---------------------------------------------------------------------------

def run_phase_60a_execution_metrics(ai_edit_plan, payload, job_id: str) -> None:
    """Collect AI execution metrics and attach to ai_edit_plan."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.metrics.ai_execution_metrics_engine import (
            build_ai_execution_metrics as _build_metrics,
        )
        _metrics_result = _build_metrics(ai_edit_plan, payload, context={"job_id": job_id})
        try:
            ai_edit_plan.ai_execution_metrics = (
                _metrics_result.get("ai_execution_metrics") or {}
            )
            ai_edit_plan.ai_execution_summary = (
                _metrics_result.get("ai_execution_summary") or {}
            )
        except Exception:
            pass
        _summary = _metrics_result.get("ai_execution_summary") or {}
        logger.info(
            "ai_execution_metrics_collected job_id=%s "
            "sub=%s cam=%s seg=%s qg_blocks=%d uo=%d assistance=%s",
            job_id,
            _summary.get("subtitle_apply"),
            _summary.get("camera_apply"),
            _summary.get("segment_apply"),
            _summary.get("quality_gate_blocks", 0),
            _summary.get("user_override_count", 0),
            _summary.get("overall_ai_assistance", "none"),
        )
    except Exception as _met_err:
        logger.warning("ai_execution_metrics_failed job_id=%s: %s", job_id, _met_err)


# ---------------------------------------------------------------------------
# Phase 60B — A/B Render Evaluation (evaluation only)
# ---------------------------------------------------------------------------

def run_phase_60b_ab_evaluation(ai_edit_plan, job_id: str) -> None:
    """Build A/B render evaluation and attach to ai_edit_plan."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.ab_evaluation.ab_evaluation_engine import (
            build_ab_evaluation as _build_ab_eval,
        )
        _ab_result = _build_ab_eval(
            ai_edit_plan,
            baseline=None,
            context={"job_id": job_id},
        )
        try:
            ai_edit_plan.ai_ab_evaluation = _ab_result.get("ai_ab_evaluation") or {}
        except Exception:
            pass
        _ab = _ab_result.get("ai_ab_evaluation") or {}
        logger.info(
            "ai_ab_evaluation_collected job_id=%s available=%s winner=%s confidence=%.3f",
            job_id,
            _ab.get("available"),
            _ab.get("winner", "unknown"),
            float(_ab.get("confidence") or 0.0),
        )
    except Exception as _ab_err:
        logger.warning("ai_ab_evaluation_failed job_id=%s: %s", job_id, _ab_err)


# ---------------------------------------------------------------------------
# Phase 60C — Creator Benchmark Suite (benchmarking only)
# ---------------------------------------------------------------------------

def run_phase_60c_creator_benchmark(ai_edit_plan, job_id: str) -> None:
    """Build creator benchmark evaluation and attach to ai_edit_plan."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.creator_benchmark.creator_benchmark_engine import (
            build_creator_benchmark as _build_creator_benchmark,
        )
        _cb_result = _build_creator_benchmark(ai_edit_plan, context={"job_id": job_id})
        try:
            ai_edit_plan.creator_benchmark_summary = (
                _cb_result.get("creator_benchmark_summary") or {}
            )
        except Exception:
            pass
        _cb = _cb_result.get("creator_benchmark_summary") or {}
        logger.info(
            "creator_benchmark_collected job_id=%s available=%s "
            "creator_type=%s status=%s delta=%s",
            job_id,
            _cb.get("available"),
            _cb.get("creator_type", "unknown"),
            _cb.get("benchmark_status", "unknown"),
            _cb.get("overall_delta"),
        )
    except Exception as _cb_err:
        logger.warning("creator_benchmark_failed job_id=%s: %s", job_id, _cb_err)


# ---------------------------------------------------------------------------
# Phase 61A — Creator Archetype Strategy (advisory metadata only)
# ---------------------------------------------------------------------------

def run_phase_61a_archetype_strategy(ai_edit_plan, job_id: str) -> None:
    """Build creator archetype strategy and attach to ai_edit_plan."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.creator_archetype.creator_archetype_engine import (
            build_creator_archetype_strategy as _build_archetype_strategy,
        )
        _arch_result = _build_archetype_strategy(ai_edit_plan, context={"job_id": job_id})
        try:
            ai_edit_plan.creator_archetype_strategy = (
                _arch_result.get("creator_archetype_strategy") or {}
            )
        except Exception:
            pass
        _arch = _arch_result.get("creator_archetype_strategy") or {}
        logger.info(
            "creator_archetype_strategy_built job_id=%s available=%s "
            "creator_type=%s confidence=%.3f",
            job_id,
            _arch.get("available"),
            _arch.get("creator_type", "unknown"),
            float(_arch.get("confidence") or 0.0),
        )
    except Exception as _arch_err:
        logger.warning(
            "creator_archetype_strategy_failed job_id=%s: %s", job_id, _arch_err
        )


# ---------------------------------------------------------------------------
# Phase 61D — Creator Render Strategy Fusion (advisory metadata only)
# ---------------------------------------------------------------------------

def run_phase_61d_creator_render_strategy(ai_edit_plan, job_id: str) -> None:
    """Build creator render strategy and attach to ai_edit_plan."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.creator_style.creator_render_strategy_engine import (
            build_creator_render_strategy as _build_creator_render_strategy,
        )
        _crs_result = _build_creator_render_strategy(ai_edit_plan, context={"job_id": job_id})
        try:
            ai_edit_plan.creator_render_strategy = (
                _crs_result.get("creator_render_strategy") or {}
            )
        except Exception:
            pass
        _crs = _crs_result.get("creator_render_strategy") or {}
        logger.info(
            "creator_render_strategy_built job_id=%s available=%s "
            "creator_type=%s confidence=%.3f",
            job_id,
            _crs.get("available"),
            _crs.get("creator_type", "unknown"),
            float(_crs.get("confidence") or 0.0),
        )
    except Exception as _crs_err:
        logger.warning(
            "creator_render_strategy_failed job_id=%s: %s", job_id, _crs_err
        )


# ---------------------------------------------------------------------------
# Phase 62A — Render Outcome Tracking (tracking-only, no mutation)
# ---------------------------------------------------------------------------

def run_phase_62a_outcome_tracking(ai_edit_plan, job_id: str) -> None:
    """Build render outcome tracking record and attach to ai_edit_plan."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.outcome_tracking.render_outcome_tracking_engine import (
            build_render_outcome_tracking as _build_render_outcome_tracking,
        )
        _rot_result = _build_render_outcome_tracking(ai_edit_plan, context={"job_id": job_id})
        try:
            ai_edit_plan.render_outcome_tracking = (
                _rot_result.get("render_outcome_tracking") or {}
            )
        except Exception:
            pass
        _rot = _rot_result.get("render_outcome_tracking") or {}
        logger.info(
            "render_outcome_tracking_built job_id=%s available=%s "
            "overall_result=%s ai_effectiveness=%s creator_fit=%s confidence=%.3f",
            job_id,
            _rot.get("available"),
            _rot.get("overall_result", "unknown"),
            _rot.get("ai_effectiveness", "unknown"),
            (_rot.get("benchmark_result") or {}).get("creator_fit", "unknown"),
            float(_rot.get("confidence") or 0.0),
        )
    except Exception as _rot_err:
        logger.warning(
            "render_outcome_tracking_failed job_id=%s: %s", job_id, _rot_err
        )


# ---------------------------------------------------------------------------
# Phase 62B — Creator Preference Reinforcement (metadata only)
# ---------------------------------------------------------------------------

def run_phase_62b_preference_reinforcement(ai_edit_plan, job_id: str) -> None:
    """Build creator preference reinforcement signals and attach to ai_edit_plan."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.outcome_tracking.creator_preference_reinforcement_engine import (
            build_creator_preference_reinforcement as _build_cpr,
        )
        _cpr_result = _build_cpr(ai_edit_plan, context={"job_id": job_id})
        try:
            ai_edit_plan.creator_preference_reinforcement = (
                _cpr_result.get("creator_preference_reinforcement") or {}
            )
        except Exception:
            pass
        _cpr = _cpr_result.get("creator_preference_reinforcement") or {}
        logger.info(
            "creator_preference_reinforcement_built job_id=%s available=%s "
            "domains_reinforced=%d negative_signals=%d confidence=%.3f",
            job_id,
            _cpr.get("available"),
            len(_cpr.get("reinforced_preferences") or {}),
            len(_cpr.get("negative_signals") or []),
            float(_cpr.get("confidence") or 0.0),
        )
    except Exception as _cpr_err:
        logger.warning(
            "creator_preference_reinforcement_failed job_id=%s: %s", job_id, _cpr_err
        )


# ---------------------------------------------------------------------------
# Phase 62C — Success Pattern Mining (pattern metadata only)
# ---------------------------------------------------------------------------

def run_phase_62c_success_patterns(ai_edit_plan, job_id: str) -> None:
    """Discover success patterns from render outcome and attach to ai_edit_plan."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.outcome_tracking.render_success_pattern_engine import (
            build_render_success_patterns as _build_rsp,
        )
        _rsp_result = _build_rsp(ai_edit_plan, context={"job_id": job_id})
        try:
            ai_edit_plan.render_success_patterns = (
                _rsp_result.get("render_success_patterns") or {}
            )
        except Exception:
            pass
        _rsp = _rsp_result.get("render_success_patterns") or {}
        logger.info(
            "render_success_patterns_built job_id=%s available=%s "
            "pattern_count=%d confidence=%.3f",
            job_id,
            _rsp.get("available"),
            len(_rsp.get("patterns") or []),
            float(_rsp.get("confidence") or 0.0),
        )
    except Exception as _rsp_err:
        logger.warning(
            "render_success_patterns_failed job_id=%s: %s", job_id, _rsp_err
        )


# ---------------------------------------------------------------------------
# Phase 62D — Learning-Aware Influence Calibration (metadata only)
# ---------------------------------------------------------------------------

def run_phase_62d_learning_calibration(ai_edit_plan, job_id: str) -> None:
    """Calibrate bounded AI influence using patterns/reinforcement signals."""
    if ai_edit_plan is None:
        return
    try:
        from app.ai.outcome_tracking.learning_influence_calibration_engine import (
            build_learning_influence_calibration as _build_lic,
        )
        _lic_result = _build_lic(ai_edit_plan, context={"job_id": job_id})
        try:
            ai_edit_plan.learning_influence_calibration = (
                _lic_result.get("learning_influence_calibration") or {}
            )
        except Exception:
            pass
        _lic = _lic_result.get("learning_influence_calibration") or {}
        logger.info(
            "learning_influence_calibration_built job_id=%s available=%s "
            "mode=%s pos_domains=%d neg_entries=%d confidence=%.3f",
            job_id,
            _lic.get("available"),
            _lic.get("execution_mode", "unknown"),
            len(_lic.get("calibration") or {}),
            len(_lic.get("negative_calibration") or []),
            float(_lic.get("confidence") or 0.0),
        )
    except Exception as _lic_err:
        logger.warning(
            "learning_influence_calibration_failed job_id=%s: %s", job_id, _lic_err
        )
