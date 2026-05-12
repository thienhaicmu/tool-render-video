"""
camera_quality_evaluator.py — Camera Quality Intelligence v2 evaluator. Phase 52B.

Orchestrates all camera quality dimension scorers into a single
CameraQualityV2 result with weighted overall score, risk penalty,
and creator-facing reasoning.

Public API:
    evaluate_camera_quality_v2(edit_plan) -> dict

Safety contract:
    ❌ No motion_crop rewrite
    ❌ No tracking rewrite
    ❌ No scene detection mutation
    ❌ No FFmpeg mutation
    ❌ No render pipeline rewrite
    ❌ No executor override
    ❌ No autonomous execution
    ✅ Evaluation-only — enriches quality metadata, never mutates
    ✅ Deterministic — same inputs always produce same output
    ✅ Never raises
    ✅ Fallback-safe — returns all-zero dict on any error
"""
from __future__ import annotations

import logging
from typing import Any, List

from app.ai.camera_quality.camera_quality_schema import (
    CameraQualityV2,
    SCORE_WEIGHTS,
    RISK_WEIGHT,
    fallback_camera_quality_v2,
)
from app.ai.camera_quality.camera_quality_scorer import (
    score_micro_jitter_risk,
    score_whip_pan_risk,
    score_crop_smoothness,
    score_subject_stability,
    score_scene_continuity,
    score_creator_fit,
    compute_confidence,
)

logger = logging.getLogger("app.ai.camera_quality.evaluator")


def evaluate_camera_quality_v2(edit_plan: Any) -> dict:
    """Evaluate camera quality across 4 dimensions + 2 risk scores. Never raises.

    Args:
        edit_plan: AIEditPlan with Phase 18, 34, 44, 46, 50B, 50D signals.

    Returns:
        dict matching the camera_quality_v2 schema spec.
        Falls back to all-zero dict on any failure.
    """
    try:
        return _evaluate(edit_plan)
    except Exception as exc:
        logger.debug("camera_quality_v2_error: %s", exc)
        return {"camera_quality_v2": fallback_camera_quality_v2()}


def _evaluate(edit_plan: Any) -> dict:
    if edit_plan is None:
        return {"camera_quality_v2": fallback_camera_quality_v2()}

    # Score all dimensions
    jitter     = score_micro_jitter_risk(edit_plan)
    whip_pan   = score_whip_pan_risk(edit_plan)
    smoothness = score_crop_smoothness(edit_plan)
    stability  = score_subject_stability(edit_plan)
    continuity = score_scene_continuity(edit_plan)
    creator    = score_creator_fit(edit_plan)
    confidence = compute_confidence(edit_plan)

    # Weighted positive dimensions
    raw_positive = (
        smoothness * SCORE_WEIGHTS["crop_smoothness"]
        + stability  * SCORE_WEIGHTS["subject_stability"]
        + continuity * SCORE_WEIGHTS["scene_continuity"]
        + creator    * SCORE_WEIGHTS["creator_fit"]
    )

    # Risk penalty: average of both risks, weighted at RISK_WEIGHT (0.10)
    avg_risk = (jitter + whip_pan) / 2.0
    risk_penalty = avg_risk * RISK_WEIGHT

    overall = max(0, min(100, round(raw_positive - risk_penalty)))

    reasoning = _build_reasoning(
        jitter, whip_pan, smoothness, stability, continuity, creator, edit_plan,
    )

    result = CameraQualityV2(
        micro_jitter_risk=jitter,
        whip_pan_risk=whip_pan,
        crop_smoothness=smoothness,
        subject_stability=stability,
        scene_continuity=continuity,
        creator_fit=creator,
        overall=overall,
        confidence=confidence,
        reasoning=reasoning,
    )

    logger.debug(
        "camera_quality_v2_done overall=%d confidence=%.2f jitter=%d whip_pan=%d "
        "smoothness=%d stability=%d continuity=%d creator=%d",
        overall, confidence, jitter, whip_pan,
        smoothness, stability, continuity, creator,
    )

    return {"camera_quality_v2": result.to_dict()}


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    jitter: int,
    whip_pan: int,
    smoothness: int,
    stability: int,
    continuity: int,
    creator: int,
    edit_plan: Any,
) -> List[str]:
    lines: List[str] = []

    # Stability comment — most visible quality aspect
    if stability >= 75:
        lines.append("Subject framing remained stable throughout")
    elif stability >= 55:
        lines.append("Subject framing was generally stable")
    else:
        lines.append("Subject tracking stability signals are limited")

    # Crop smoothness comment
    if smoothness >= 75:
        lines.append("Crop motion is smooth and well controlled")
    elif smoothness < 50:
        lines.append("Crop smoothness signals suggest room for improvement")

    # Scene continuity comment
    if continuity >= 70:
        lines.append("Scene-aware camera transitions are consistent")
    elif continuity < 48:
        lines.append("Scene continuity signals are weak")

    # Creator fit comment
    if creator >= 70:
        lines.append("Crop motion matched your creator camera preference")
    elif creator >= 55:
        lines.append("Camera style partially reflects your creator preferences")

    # Risk warnings (creator-facing, no debug text)
    if jitter >= 35:
        lines.append("Micro-jitter risk detected — consider higher stability settings")
    elif jitter < 15:
        lines.append("Low jitter risk improves camera quality")

    if whip_pan >= 35:
        lines.append("Rapid framing changes detected — may feel aggressive")

    # Phase 53C: optional anti-jitter knowledge enrichment
    if len(lines) < 6 and jitter >= 35:
        k_hint = _jitter_knowledge_hint()
        if k_hint:
            lines.append(k_hint)

    # Phase 55C: optional platform camera context hint
    if len(lines) < 6:
        p_hint = _platform_camera_hint(edit_plan)
        if p_hint:
            lines.append(p_hint)

    return lines


def _platform_camera_hint(edit_plan: Any) -> str:
    """Return an optional platform-aware camera reasoning hint. Never raises.

    Phase 55C platform camera intelligence — metadata-only, additive.
    Reads platform_camera_context from the edit plan when available.
    """
    try:
        ctx = getattr(edit_plan, "platform_camera_context", None)
        if not ctx or not isinstance(ctx, dict) or not ctx.get("available"):
            return ""
        guidance = ctx.get("guidance") or {}
        reasoning = ctx.get("reasoning") or []
        platform = str(ctx.get("platform") or "")
        motion = str(guidance.get("motion_energy") or "")
        stability = str(guidance.get("stability_priority") or "")

        if reasoning:
            return str(reasoning[0])
        if platform and motion:
            return f"{platform.replace('_', ' ').title()} camera guidance recommends {motion} motion energy"
        if motion and stability:
            return f"Platform guidance supports {motion} motion energy with {stability} stability priority"
        return ""
    except Exception:
        return ""


def _jitter_knowledge_hint() -> str:
    """Return an optional knowledge-informed anti-jitter hint. Never raises.

    Phase 53C camera knowledge integration — metadata-only, additive.
    Enriches reasoning when micro-jitter risk is elevated.
    """
    try:
        from app.ai.knowledge.camera_knowledge_retriever import retrieve_knowledge
        pack = retrieve_knowledge(domain="camera", tags=["anti_jitter", "jitter"], max_results=1)
        if not pack.available or not pack.items:
            return ""
        patterns = pack.items[0].camera_patterns
        if patterns.get("overreactive_tracking_risk") or patterns.get("deadzone") == "wide":
            return "Wider deadzone and higher smoothing can reduce micro-jitter risk"
        return ""
    except Exception:
        return ""
