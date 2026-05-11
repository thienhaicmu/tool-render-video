"""
signal_aggregation.py — Unified signal aggregation layer. Phase 47.

Aggregates creator, market, quality, preset, feedback, and retrieval signals
from the AI edit plan into a single unified signal dict.

Rules:
- Deterministic, conservative-first
- Tolerates missing signals — graceful fallback to {"available": False}
- Never raises
- No mutation of edit plan
- No render execution
- No FFmpeg, no playback_speed, no subtitle_timing, no executor override
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.orchestrator.signal_aggregation")


def aggregate_signals(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Aggregate all AI signals from the edit plan into a unified dict.

    Args:
        edit_plan: AIEditPlan (or None) with Phase 41–46 signal fields.
        context:   Optional session context.

    Returns:
        {
            "creator_signal": {...},
            "market_signal": {...},
            "quality_signal": {...},
            "preset_signal": {...},
            "feedback_signal": {...},
            "retrieval_signal": {...},
            "confidence": float,
            "active_signal_count": int,
        }
    """
    try:
        return _aggregate(edit_plan, context or {})
    except Exception as exc:
        logger.debug("signal_aggregation_error: %s", exc)
        return _empty_signals(error=type(exc).__name__)


def _aggregate(edit_plan: Any, ctx: dict) -> dict:
    creator_signal = _extract_creator_signal(edit_plan)
    market_signal = _extract_market_signal(edit_plan)
    quality_signal = _extract_quality_signal(edit_plan)
    preset_signal = _extract_preset_signal(edit_plan)
    feedback_signal = _extract_feedback_signal(edit_plan)
    retrieval_signal = _extract_retrieval_signal(edit_plan)

    active_signals = sum(
        1 for s in (creator_signal, market_signal, quality_signal,
                    preset_signal, feedback_signal, retrieval_signal)
        if s.get("available")
    )
    aggregate_confidence = round(_clamp(active_signals / 6.0), 4)

    return {
        "creator_signal": creator_signal,
        "market_signal": market_signal,
        "quality_signal": quality_signal,
        "preset_signal": preset_signal,
        "feedback_signal": feedback_signal,
        "retrieval_signal": retrieval_signal,
        "confidence": aggregate_confidence,
        "active_signal_count": active_signals,
    }


def _extract_creator_signal(edit_plan: Any) -> dict:
    """Extract creator intelligence from adaptive (Ph42) + style adaptation (Ph23)."""
    try:
        aci = _get_dict(edit_plan, "adaptive_creator_intelligence")
        csa = _get_dict(edit_plan, "creator_style_adaptation")
        if not aci and not csa:
            return {"available": False}

        profile = aci.get("creator_profile") or {}
        adapted_style = str(csa.get("adapted_style") or "")
        style_confidence = _clamp(float(profile.get("style_confidence") or 0.0))
        subtitle_confidence = _clamp(float(profile.get("subtitle_confidence") or 0.0))
        pacing_confidence = _clamp(float(profile.get("pacing_confidence") or 0.0))
        camera_confidence = _clamp(float(profile.get("camera_confidence") or 0.0))

        return {
            "available": True,
            "adapted_style": adapted_style,
            "style_confidence": round(style_confidence, 4),
            "subtitle_confidence": round(subtitle_confidence, 4),
            "pacing_confidence": round(pacing_confidence, 4),
            "camera_confidence": round(camera_confidence, 4),
            "adaptive_enabled": bool(aci.get("enabled")),
            "adaptive_influences": dict(aci.get("adaptive_influences") or {}),
        }
    except Exception:
        return {"available": False}


def _extract_market_signal(edit_plan: Any) -> dict:
    """Extract market optimization from Phase 44."""
    try:
        moi = _get_dict(edit_plan, "market_optimization_intelligence")
        if not moi or not moi.get("available"):
            return {"available": False}

        profile = moi.get("market_profile") or {}
        return {
            "available": True,
            "target_market": str(moi.get("target_market") or ""),
            "market_confidence": round(_clamp(float(profile.get("confidence") or 0.0)), 4),
            "subtitle_bias": dict(moi.get("subtitle_market_bias") or {}),
            "pacing_bias": dict(moi.get("pacing_market_bias") or {}),
            "camera_bias": dict(moi.get("camera_market_bias") or {}),
            "hook_bias": dict(moi.get("hook_market_bias") or {}),
            "optimization_mode": str(moi.get("optimization_mode") or "assistive_only"),
        }
    except Exception:
        return {"available": False}


def _extract_quality_signal(edit_plan: Any) -> dict:
    """Extract render quality evaluation from Phase 45."""
    try:
        rqe = _get_dict(edit_plan, "render_quality_evaluation")
        if not rqe or not rqe.get("enabled"):
            return {"available": False}

        best_id = str(rqe.get("best_quality_output_id") or "")
        scores = rqe.get("output_scores") or []
        best_score = 0.0
        if isinstance(scores, list):
            for s in scores:
                if isinstance(s, dict) and s.get("output_id") == best_id:
                    best_score = float(s.get("overall_score") or 0.0)
                    break

        return {
            "available": True,
            "best_output_id": best_id,
            "best_overall_score": round(best_score, 2),
            "evaluated_output_count": len(scores),
            "evaluation_mode": str(rqe.get("evaluation_mode") or "evaluation_only"),
        }
    except Exception:
        return {"available": False}


def _extract_preset_signal(edit_plan: Any) -> dict:
    """Extract creator preset evolution from Phase 46."""
    try:
        cpe = _get_dict(edit_plan, "creator_preset_evolution")
        if not cpe or not cpe.get("available"):
            return {"available": False}

        best_preset_id = str(cpe.get("best_preset_id") or "")
        recommended = cpe.get("recommended_presets") or []
        evolved = cpe.get("evolved_presets") or []

        best_score = 0.0
        best_subtitle = ""
        best_pacing = ""
        best_camera = ""

        for p in recommended:
            if isinstance(p, dict) and p.get("preset_id") == best_preset_id:
                best_score = float(p.get("_score") or 0.0)
                best_subtitle = str(p.get("subtitle_style") or "")
                best_pacing = str(p.get("pacing_style") or "")
                best_camera = str(p.get("camera_style") or "")
                break

        if not best_subtitle and evolved and isinstance(evolved[0], dict):
            ev = evolved[0]
            best_subtitle = str(ev.get("subtitle_style") or "")
            best_pacing = str(ev.get("pacing_style") or "")
            best_camera = str(ev.get("camera_style") or "")

        return {
            "available": True,
            "best_preset_id": best_preset_id,
            "best_preset_score": round(best_score, 2),
            "best_subtitle_style": best_subtitle,
            "best_pacing_style": best_pacing,
            "best_camera_style": best_camera,
            "recommended_count": len(recommended),
            "evolved_count": len(evolved),
            "evolution_mode": str(cpe.get("evolution_mode") or "assistive_only"),
        }
    except Exception:
        return {"available": False}


def _extract_feedback_signal(edit_plan: Any) -> dict:
    """Extract creator feedback loop signal from Phase 43."""
    try:
        cfi = _get_dict(edit_plan, "creator_feedback_intelligence")
        if not cfi or not cfi.get("available"):
            return {"available": False}

        patterns = cfi.get("learned_feedback_patterns") or {}
        biases = cfi.get("ranking_biases") or {}

        return {
            "available": True,
            "total_exports": int(patterns.get("total_exports") or 0),
            "dominant_creator_style": str(patterns.get("dominant_creator_style") or ""),
            "dominant_subtitle_style": str(patterns.get("dominant_subtitle_style") or ""),
            "dominant_pacing_style": str(patterns.get("dominant_pacing_style") or ""),
            "subtitle_weighting_bias": round(
                _clamp(float(biases.get("subtitle_weighting_bias") or 0.0), 0.0, 0.30), 4
            ),
            "pacing_weighting_bias": round(
                _clamp(float(biases.get("pacing_weighting_bias") or 0.0), 0.0, 0.30), 4
            ),
            "feedback_mode": str(cfi.get("feedback_mode") or "assistive_only"),
        }
    except Exception:
        return {"available": False}


def _extract_retrieval_signal(edit_plan: Any) -> dict:
    """Extract creator retrieval intelligence from Phase 41."""
    try:
        cr = _get_dict(edit_plan, "creator_retrieval")
        if not cr or not cr.get("enabled"):
            return {"available": False}

        matches = cr.get("matches") or []
        top_style = ""
        if matches and isinstance(matches[0], dict):
            top_style = str(matches[0].get("creator_style") or "")

        return {
            "available": True,
            "match_count": len(matches),
            "top_matched_style": top_style,
            "retrieval_confidence": round(_clamp(len(matches) / max(1, 5)), 4),
        }
    except Exception:
        return {"available": False}


def _empty_signals(error: str = "") -> dict:
    base: dict = {
        "creator_signal": {"available": False},
        "market_signal": {"available": False},
        "quality_signal": {"available": False},
        "preset_signal": {"available": False},
        "feedback_signal": {"available": False},
        "retrieval_signal": {"available": False},
        "confidence": 0.0,
        "active_signal_count": 0,
    }
    if error:
        base["aggregation_error"] = error
    return base


def _get_dict(edit_plan: Any, attr: str) -> dict:
    try:
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except Exception:
        return lo
