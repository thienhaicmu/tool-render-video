"""
influence_engine.py — Safe Controlled Influence Engine. Phase 48.

Consumes Phase 47 Multi-Signal Orchestration output and produces
conservative, confidence-gated influence recommendations.

Public API:
    compute_safe_influence(edit_plan, payload=None, context=None) -> dict

Architecture:
    Phase 47 output → Safety Gate → Per-domain bias modules → Unified pack

Safety contract:
    ❌ No FFmpeg mutation
    ❌ No render rewrite
    ❌ No playback_speed mutation
    ❌ No subtitle timing rewrite
    ❌ No rerender
    ❌ No executor override
    ❌ No crop engine rewrite
    ❌ No autonomous execution
    ❌ No destructive pipeline changes

AI ONLY: recommends, softly influences, explains. Never executes.

Rules:
- Safe influence ONLY — no render mutation
- Deterministic for identical inputs
- Conservative-first — gate blocks low confidence (< 0.70)
- Fallback-safe (never raises)
- Additive only — no breaking changes
- Backward compatible
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.influence.safety_gate import evaluate_gate, TIER_BLOCKED
from app.ai.influence.subtitle_bias import compute_subtitle_bias
from app.ai.influence.camera_bias import compute_camera_bias
from app.ai.influence.ranking_bias import compute_ranking_bias
from app.ai.influence.market_weighting import compute_market_weights

logger = logging.getLogger("app.ai.influence.influence_engine")


def compute_safe_influence(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> dict:
    """Compute safe controlled influence recommendations from Phase 47 output.

    Args:
        edit_plan: AIEditPlan (or None) with `multi_signal_orchestration` populated.
        payload:   Render request (read-only — never mutated).
        context:   Optional session context.

    Returns:
        {
            "available": bool,
            "enabled": bool,
            "influence_mode": "safe_controlled",
            "gate": {
                "passed": bool,
                "tier": str,
                "confidence": float,
                "reason": str,
            },
            "safe_influence": {
                "subtitle_style_bias":    str,
                "subtitle_density_bias":  str,
                "camera_motion_bias":     str,
                "ranking_priority_bias":  str,
            },
            "subtitle_bias":    {...},
            "camera_bias":      {...},
            "ranking_bias":     {...},
            "market_weights":   {...},
            "confidence":       float,
            "explainability":   [str, ...],
            "warnings":         [str, ...],
        }
    """
    try:
        return _compute(edit_plan, payload, context or {})
    except Exception as exc:
        logger.debug("influence_engine_error: %s", exc)
        return _safe_fallback(error=type(exc).__name__)


def _compute(edit_plan: Any, payload: Any, ctx: dict) -> dict:
    warnings: list[str] = []

    # --- Extract Phase 47 orchestration output ---
    mso = _get_dict(edit_plan, "multi_signal_orchestration")
    if not mso or not mso.get("available"):
        return {
            "available": True,
            "enabled": False,
            "influence_mode": "safe_controlled",
            "warnings": ["no_orchestration_available_phase47"],
        }

    # Confidence and strategy from Phase 47
    confidence_scores = mso.get("confidence_scores") or {}
    agg_confidence = float(confidence_scores.get("aggregate_confidence") or 0.0)
    recommended_strategy = mso.get("recommended_strategy") or {}
    aggregated_signals = mso.get("aggregated_signals") or {}

    # --- Safety gate evaluation ---
    gate = evaluate_gate(agg_confidence)

    if not gate.get("passed"):
        logger.debug(
            "influence_gate_blocked confidence=%.3f reason=%s",
            agg_confidence, gate.get("reason"),
        )
        return {
            "available": True,
            "enabled": False,
            "influence_mode": "safe_controlled",
            "gate": gate,
            "confidence": agg_confidence,
            "warnings": [f"gate_blocked:{gate.get('reason')}"],
        }

    # --- Per-domain bias computations ---
    subtitle = compute_subtitle_bias(recommended_strategy, gate)
    camera = compute_camera_bias(recommended_strategy, gate)
    ranking = compute_ranking_bias(recommended_strategy, gate)
    market = compute_market_weights(aggregated_signals, gate)

    # --- Unified safe_influence surface ---
    safe_influence: dict = {
        "subtitle_style_bias":   subtitle.get("subtitle_style_bias") or "",
        "subtitle_density_bias": subtitle.get("subtitle_density_bias") or "",
        "camera_motion_bias":    camera.get("camera_motion_bias") or "",
        "ranking_priority_bias": ranking.get("ranking_priority_bias") or "",
    }

    # --- Explainability ---
    explainability = _build_explainability(gate, subtitle, camera, ranking, market)

    any_active = any([
        subtitle.get("available"),
        camera.get("available"),
        ranking.get("available"),
        market.get("available"),
    ])
    enabled = any_active

    logger.info(
        "influence_engine_done tier=%s confidence=%.3f enabled=%s "
        "subtitle=%s camera=%s ranking=%s market=%s",
        gate.get("tier"), agg_confidence, enabled,
        subtitle.get("available"), camera.get("available"),
        ranking.get("available"), market.get("available"),
    )

    return {
        "available": True,
        "enabled": enabled,
        "influence_mode": "safe_controlled",
        "gate": gate,
        "safe_influence": safe_influence,
        "subtitle_bias": subtitle,
        "camera_bias": camera,
        "ranking_bias": ranking,
        "market_weights": market,
        "confidence": round(agg_confidence, 4),
        "explainability": explainability,
        "warnings": warnings,
    }


def _build_explainability(
    gate: dict,
    subtitle: dict,
    camera: dict,
    ranking: dict,
    market: dict,
) -> list[str]:
    """Build human-readable explainability lines. Deterministic, metadata-only."""
    try:
        reasons: list[str] = []
        tier = str(gate.get("tier") or "")
        conf = float(gate.get("confidence") or 0.0)

        reasons.append(
            f"Safety gate passed — tier={tier} confidence={round(conf, 3)}"
        )

        if subtitle.get("available"):
            parts = []
            if subtitle.get("subtitle_style_bias"):
                parts.append(f"style→{subtitle['subtitle_style_bias']}")
            if subtitle.get("subtitle_density_bias") and subtitle["subtitle_density_bias"] != "unchanged":
                parts.append(f"density→{subtitle['subtitle_density_bias']}")
            if parts:
                reasons.append("Subtitle bias: " + ", ".join(parts))

        if camera.get("available"):
            parts = []
            if camera.get("camera_motion_bias"):
                parts.append(f"motion→{camera['camera_motion_bias']}")
            if camera.get("smoothing_preference"):
                parts.append(f"smooth→{camera['smoothing_preference']}")
            if parts:
                reasons.append("Camera bias: " + ", ".join(parts))

        if ranking.get("available"):
            bias = str(ranking.get("ranking_priority_bias") or "")
            if bias:
                reasons.append(f"Ranking bias: priority→{bias}")

        if market.get("available"):
            target = str(market.get("target_market") or "")
            if target:
                reasons.append(
                    f"Market weights active for '{target}' platform"
                )

        return reasons
    except Exception:
        return ["explainability_unavailable"]


def _get_dict(edit_plan: Any, attr: str) -> dict:
    try:
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_fallback(error: str = "") -> dict:
    result: dict = {
        "available": True,
        "enabled": False,
        "influence_mode": "safe_controlled",
        "warnings": ["influence_engine_error_fallback"],
    }
    if error:
        result["warnings"].append(f"error:{error}")
    return result
