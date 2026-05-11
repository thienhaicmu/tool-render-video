"""
render_orchestrator.py — Multi-Signal AI Render Orchestrator. Phase 47.

Unifies all AI intelligence signals (Phases 41–46) into a single coherent
render reasoning engine.

Public API:
    orchestrate_render_signals(edit_plan, payload=None, context=None) -> dict

Hard safety rules — STRICTLY BLOCKED:
    ❌ FFmpeg mutation
    ❌ render rewrite
    ❌ subtitle timing rewrite
    ❌ playback_speed mutation
    ❌ rerender
    ❌ executor override
    ❌ autonomous execution
    ❌ destructive mutation

AI ONLY: reasons, recommends, explains. Never executes.

Rules:
- Reasoning-only — no render mutation whatsoever
- Deterministic for identical inputs
- Conservative-first
- Fallback-safe (never raises)
- Backward compatible
- No internet, no cloud AI, no GPU required
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.orchestrator.signal_aggregation import aggregate_signals
from app.ai.orchestrator.confidence_engine import compute_signal_confidence
from app.ai.orchestrator.conflict_resolver import resolve_conflicts
from app.ai.orchestrator.strategy_planner import plan_render_strategy

logger = logging.getLogger("app.ai.orchestrator.render_orchestrator")


def orchestrate_render_signals(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> dict:
    """Orchestrate all AI signals into a unified render strategy recommendation.

    Args:
        edit_plan: AIEditPlan (or None) with Phase 41–46 signal fields.
        payload:   Render request (read-only — never mutated).
        context:   Optional session context.

    Returns:
        {
            "available": bool,
            "enabled": bool,
            "orchestration_mode": "reasoning_only",
            "aggregated_signals": {...},
            "confidence_scores": {...},
            "resolved_conflicts": {...},
            "recommended_strategy": {...},
            "strategy_confidence": float,
            "strategy_mode": "recommendation_only",
            "explainability": {"why_this_strategy": [...], ...},
            "warnings": [...],
        }
    """
    try:
        return _orchestrate(edit_plan, payload, context or {})
    except Exception as exc:
        logger.debug("render_orchestrator_error: %s", exc)
        return _safe_fallback(error=type(exc).__name__)


def _orchestrate(edit_plan: Any, payload: Any, ctx: dict) -> dict:
    warnings: list[str] = []

    if edit_plan is None:
        logger.debug("render_orchestrator_skipped reason=no_edit_plan")
        return {
            "available": True,
            "enabled": False,
            "orchestration_mode": "reasoning_only",
            "warnings": ["no_edit_plan_available"],
        }

    # Step 1: Aggregate all AI signals
    aggregated = aggregate_signals(edit_plan, context=ctx)
    active_count = int(aggregated.get("active_signal_count") or 0)

    if active_count == 0:
        logger.debug("render_orchestrator_skipped reason=no_active_signals")
        return {
            "available": True,
            "enabled": False,
            "orchestration_mode": "reasoning_only",
            "aggregated_signals": aggregated,
            "warnings": ["no_active_signals_available"],
        }

    # Step 2: Compute per-signal confidence
    confidence = compute_signal_confidence(aggregated)

    # Step 3: Resolve signal conflicts deterministically
    resolved = resolve_conflicts(aggregated, confidence)

    # Step 4: Plan the unified render strategy (recommendation only)
    strategy = plan_render_strategy(aggregated, confidence, resolved)

    # Step 5: Generate explainability metadata
    explainability = _build_explainability(aggregated, confidence, resolved, strategy)

    agg_conf = float(confidence.get("aggregate_confidence") or 0.0)
    enabled = agg_conf > 0.0 and bool(strategy.get("recommended_strategy"))

    logger.info(
        "render_orchestrator_done active_signals=%d aggregate_confidence=%.3f enabled=%s",
        active_count, agg_conf, enabled,
    )

    return {
        "available": True,
        "enabled": enabled,
        "orchestration_mode": "reasoning_only",
        "aggregated_signals": aggregated,
        "confidence_scores": confidence,
        "resolved_conflicts": resolved,
        **strategy,
        "explainability": explainability,
        "warnings": warnings,
    }


def _build_explainability(
    signals: dict,
    confidence: dict,
    conflicts: dict,
    strategy: dict,
) -> dict:
    """Build future UI-safe AI reasoning metadata.

    Deterministic, metadata-only — never applied to render execution.
    Powers the future AI Strategy Panel.
    """
    try:
        reasons: list[str] = []

        creator_sig = signals.get("creator_signal") or {}
        market_sig = signals.get("market_signal") or {}
        preset_sig = signals.get("preset_signal") or {}
        feedback_sig = signals.get("feedback_signal") or {}
        retrieval_sig = signals.get("retrieval_signal") or {}

        creator_conf = float(confidence.get("creator_confidence") or 0.0)
        market_conf = float(confidence.get("market_confidence") or 0.0)
        preset_conf = float(confidence.get("preset_confidence") or 0.0)
        feedback_conf = float(confidence.get("feedback_confidence") or 0.0)
        retrieval_conf = float(confidence.get("retrieval_confidence") or 0.0)

        # Creator signal explanation
        if creator_sig.get("available") and creator_conf > 0.3:
            style = str(creator_sig.get("adapted_style") or "")
            if style:
                reasons.append(
                    f"Creator intelligence adapted to '{style}' style "
                    f"(confidence={round(creator_conf, 2)})"
                )

        # Feedback signal explanation
        if feedback_sig.get("available") and feedback_conf > 0.2:
            exports = int(feedback_sig.get("total_exports") or 0)
            dominant_pacing = str(feedback_sig.get("dominant_pacing_style") or "")
            if exports > 0:
                reasons.append(f"Creator has {exports} prior export(s) — feedback patterns active")
            if dominant_pacing:
                reasons.append(f"Historical creator pacing preference: {dominant_pacing}")

        # Market signal explanation
        if market_sig.get("available") and market_conf > 0.2:
            target = str(market_sig.get("target_market") or "")
            if target:
                reasons.append(
                    f"{target.upper()} market optimization active "
                    f"(confidence={round(market_conf, 2)})"
                )

        # Preset signal explanation
        if preset_sig.get("available") and preset_conf > 0.2:
            best_id = str(preset_sig.get("best_preset_id") or "")
            best_score = float(preset_sig.get("best_preset_score") or 0.0)
            if best_id:
                reasons.append(
                    f"Preset '{best_id}' strongly matched "
                    f"(score={round(best_score, 1)})"
                )

        # Retrieval signal explanation
        if retrieval_sig.get("available") and retrieval_conf > 0.2:
            match_count = int(retrieval_sig.get("match_count") or 0)
            top_style = str(retrieval_sig.get("top_matched_style") or "")
            if match_count > 0:
                reasons.append(
                    f"{match_count} creator pattern match(es) found via retrieval"
                    + (f" — top style: {top_style}" if top_style else "")
                )

        # Conflict resolution explanation
        conflict_count = int(conflicts.get("conflict_count") or 0)
        if conflict_count > 0:
            resolution_notes = []
            for dim in ("subtitle_style", "pacing_style", "camera_style"):
                res = conflicts.get(dim) or {}
                winner = str(res.get("winner") or "")
                if winner and winner not in ("conservative_default", ""):
                    resolution_notes.append(f"{dim}: {winner} preferred")
            if resolution_notes:
                reasons.append(
                    f"{conflict_count} signal conflict(s) resolved — "
                    + "; ".join(resolution_notes)
                )

        # Hook emphasis explanation
        rec = strategy.get("recommended_strategy") or {}
        hook = str(rec.get("hook_emphasis") or "")
        if hook and hook != "default":
            reasons.append(f"Hook emphasis set to '{hook}' from combined signal analysis")

        if not reasons:
            reasons.append(
                "Insufficient signal richness — conservative default strategy applied"
            )

        strategy_conf = float(strategy.get("strategy_confidence") or 0.0)

        return {
            "why_this_strategy": reasons,
            "signal_count": int(signals.get("active_signal_count") or 0),
            "strategy_confidence": round(strategy_conf, 4),
        }
    except Exception as exc:
        logger.debug("explainability_build_error: %s", exc)
        return {
            "why_this_strategy": ["explainability_unavailable"],
            "signal_count": 0,
            "strategy_confidence": 0.0,
        }


def _safe_fallback(error: str = "") -> dict:
    result: dict = {
        "available": True,
        "enabled": False,
        "orchestration_mode": "reasoning_only",
        "warnings": ["orchestration_error_fallback"],
    }
    if error:
        result["warnings"].append(f"error:{error}")
    return result
