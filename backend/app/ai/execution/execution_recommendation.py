"""
execution_recommendation.py — Advisory execution recommendation builder. Phase 25.

Converts advisory AI planning metadata into compact execution-ready recommendation
packs WITHOUT directly mutating render execution.

Design rules:
- Deterministic only.
- Never raises.
- Advisory metadata only — no payload mutation, no FFmpeg, no render trigger.
- Reads from: variant_selection, creator_style_adaptation, retention,
  subtitle_execution, beat_visual_execution, story_optimization, explainability.
- safe_baseline always present.

Public API:
    build_execution_recommendations(edit_plan, context=None) -> AIExecutionPack
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.execution.execution_schema import (
    AIExecutionPack,
    AIExecutionRecommendation,
    VALID_CATEGORIES,
)
from app.ai.execution.execution_safety import sanitize_execution_settings

logger = logging.getLogger("app.ai.execution")

# Per-style camera behavior hints
_STYLE_TO_CAMERA: dict[str, str] = {
    "viral_tiktok": "fast_follow",
    "cinematic": "slow_reveal",
    "educational": "static",
    "podcast": "static",
    "product_demo": "static",
    "storytelling": "dramatic_push",
    "commentary": "fast_follow",
    "interview": "static",
    "safe_generic": "auto",
}

# Per-style pacing hints
_STYLE_TO_PACING: dict[str, str] = {
    "viral_tiktok": "fast",
    "cinematic": "slow_build",
    "educational": "medium",
    "podcast": "medium",
    "product_demo": "medium",
    "storytelling": "slow_build",
    "commentary": "fast",
    "interview": "slow",
    "safe_generic": "default",
}

# Recommendation scoring bonuses by category
_CATEGORY_BONUS: dict[str, float] = {
    "retention": 15.0,
    "creator_style": 10.0,
    "pacing": 8.0,
    "subtitle": 6.0,
    "visual_rhythm": 4.0,
    "camera": 3.0,
    "safe_baseline": 0.0,
}


def build_execution_recommendations(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> AIExecutionPack:
    """Build advisory execution recommendation pack from edit plan metadata.

    Aggregates variant selection, creator style, retention, subtitle, visual
    rhythm, and story optimization metadata into a compact advisory pack.

    Args:
        edit_plan:  AIEditPlan or None. Read-only.
        context:    Optional metadata dict.

    Returns:
        Serialisable AIExecutionPack. Never raises.
    """
    try:
        return _build(edit_plan, context or {})
    except Exception as exc:
        logger.debug("build_execution_recommendations_failed: %s", exc)
        return _fallback_pack(str(exc))


# ── Internal builder ──────────────────────────────────────────────────────────

def _build(edit_plan: Any, context: dict) -> AIExecutionPack:
    if edit_plan is None:
        logger.info("ai_execution_recommendations_skipped: no_edit_plan")
        return AIExecutionPack(
            available=False,
            mode="advisory",
            warnings=["no_edit_plan"],
        )

    recommendations: list[AIExecutionRecommendation] = []

    # ── Safe baseline — always present ────────────────────────────────────────
    recommendations.append(_build_safe_baseline())

    # ── Creator style adaptation ──────────────────────────────────────────────
    csa = _safe_dict(getattr(edit_plan, "creator_style_adaptation", {}))
    if csa.get("detected"):
        rec = _build_creator_style_recommendation(csa)
        if rec is not None:
            recommendations.append(rec)

    # ── Retention intelligence ────────────────────────────────────────────────
    retention = _safe_dict(getattr(edit_plan, "retention", {}))
    if retention:
        rec = _build_retention_recommendation(retention)
        if rec is not None:
            recommendations.append(rec)

    # ── Subtitle execution ────────────────────────────────────────────────────
    se = _safe_dict(getattr(edit_plan, "subtitle_execution", {}))
    if se.get("available"):
        rec = _build_subtitle_recommendation(se)
        if rec is not None:
            recommendations.append(rec)

    # ── Beat visual execution ─────────────────────────────────────────────────
    bve = _safe_dict(getattr(edit_plan, "beat_visual_execution", {}))
    if bve.get("available"):
        rec = _build_visual_rhythm_recommendation(bve)
        if rec is not None:
            recommendations.append(rec)

    # ── Story optimization pacing ─────────────────────────────────────────────
    so = _safe_dict(getattr(edit_plan, "story_optimization", {}))
    if so.get("available"):
        rec = _build_story_pacing_recommendation(so)
        if rec is not None:
            recommendations.append(rec)

    # ── Sanitize all settings ─────────────────────────────────────────────────
    for r in recommendations:
        r.recommended_settings = sanitize_execution_settings(r.recommended_settings)

    # ── Select best recommendation ────────────────────────────────────────────
    recommended_pack_id = _select_recommended(recommendations)

    logger.info(
        "ai_execution_recommendations_created count=%d recommended=%s",
        len(recommendations),
        recommended_pack_id or "none",
    )

    return AIExecutionPack(
        available=True,
        mode="advisory",
        recommendations=recommendations,
        recommended_pack_id=recommended_pack_id,
    )


# ── Recommendation builders ───────────────────────────────────────────────────

def _build_safe_baseline() -> AIExecutionRecommendation:
    return AIExecutionRecommendation(
        recommendation_id="safe_baseline",
        label="Safe Baseline Execution",
        category="safe_baseline",
        confidence=1.0,
        safe_to_apply=True,
        advisory_only=True,
        recommended_settings=sanitize_execution_settings({
            "ai_mode": "advisory",
            "pacing_style": "default",
        }),
        explanation=["Safe baseline — no AI mutations applied", "Advisory mode only"],
    )


def _build_creator_style_recommendation(
    csa: dict,
) -> Optional[AIExecutionRecommendation]:
    try:
        primary_style = str(csa.get("primary_style") or "safe_generic")
        confidence = float(csa.get("confidence") or 0.0)
        adaptation = _safe_dict(csa.get("adaptation") or {})

        camera_behavior = _STYLE_TO_CAMERA.get(primary_style, "auto")
        pacing_hint = _STYLE_TO_PACING.get(primary_style, "default")
        # Prefer adaptation hint if present
        if adaptation.get("camera_hint"):
            camera_behavior = str(adaptation["camera_hint"])
        if adaptation.get("pacing_hint"):
            pacing_hint = str(adaptation["pacing_hint"])

        style_label = primary_style.replace("_", " ").title()
        return AIExecutionRecommendation(
            recommendation_id=f"creator_style_{primary_style}",
            label=f"{style_label} Camera Guidance",
            category="creator_style",
            confidence=confidence,
            safe_to_apply=confidence >= 0.50,
            advisory_only=True,
            recommended_settings={
                "creator_style": primary_style,
                "camera_behavior": camera_behavior,
                "pacing_style": pacing_hint,
            },
            explanation=[
                f"Creator style: {primary_style}",
                f"Camera behavior: {camera_behavior}",
                f"Pacing: {pacing_hint}",
            ],
        )
    except Exception as exc:
        logger.debug("_build_creator_style_recommendation_failed: %s", exc)
        return None


def _build_retention_recommendation(retention: dict) -> Optional[AIExecutionRecommendation]:
    try:
        score = float(retention.get("overall_retention_score") or 50)

        if score < 40:
            pacing_style = "fast_cuts"
            hook_density = "high"
            confidence = 0.80
        elif score < 70:
            pacing_style = "retention_optimized"
            hook_density = "medium"
            confidence = 0.65
        else:
            pacing_style = "standard"
            hook_density = "low"
            confidence = 0.55

        return AIExecutionRecommendation(
            recommendation_id="retention_pacing",
            label="Retention-Oriented Pacing",
            category="retention",
            confidence=confidence,
            safe_to_apply=True,
            advisory_only=True,
            recommended_settings={
                "pacing_style": pacing_style,
                "hook_density": hook_density,
            },
            explanation=[
                f"Retention score: {score:.0f}/100",
                f"Pacing hint: {pacing_style}",
                f"Hook density: {hook_density}",
            ],
        )
    except Exception as exc:
        logger.debug("_build_retention_recommendation_failed: %s", exc)
        return None


def _build_subtitle_recommendation(se: dict) -> Optional[AIExecutionRecommendation]:
    try:
        density = str(se.get("density") or "normal")
        emphasis = str(se.get("emphasis_style") or "none")
        confidence = float(se.get("confidence") or 0.5)

        return AIExecutionRecommendation(
            recommendation_id="compact_subtitle",
            label="Compact Subtitle Execution",
            category="subtitle",
            confidence=confidence,
            safe_to_apply=True,
            advisory_only=True,
            recommended_settings={
                "subtitle_density": density,
                "subtitle_emphasis": emphasis,
            },
            explanation=[
                f"Subtitle density: {density}",
                f"Emphasis: {emphasis}",
            ],
        )
    except Exception as exc:
        logger.debug("_build_subtitle_recommendation_failed: %s", exc)
        return None


def _build_visual_rhythm_recommendation(bve: dict) -> Optional[AIExecutionRecommendation]:
    try:
        bpm_raw = bve.get("bpm")
        bpm = float(bpm_raw) if bpm_raw is not None else 0.0

        if bpm > 120:
            mode = "energetic"
        elif bpm > 80:
            mode = "moderate"
        else:
            mode = "calm"

        return AIExecutionRecommendation(
            recommendation_id="visual_rhythm",
            label="Visual Rhythm Execution",
            category="visual_rhythm",
            confidence=0.60,
            safe_to_apply=True,
            advisory_only=True,
            recommended_settings={"visual_rhythm_mode": mode},
            explanation=[
                f"BPM: {bpm:.0f}" if bpm > 0 else "BPM unavailable",
                f"Visual rhythm mode: {mode}",
            ],
        )
    except Exception as exc:
        logger.debug("_build_visual_rhythm_recommendation_failed: %s", exc)
        return None


def _build_story_pacing_recommendation(so: dict) -> Optional[AIExecutionRecommendation]:
    try:
        flow_type = str(so.get("flow_type") or "standard")
        narrative_score = float(so.get("narrative_score") or 50)

        if flow_type in ("three_act", "hero_journey"):
            pacing = "story_driven"
        elif flow_type in ("montage", "highlight"):
            pacing = "fast_cuts"
        else:
            pacing = "standard"

        return AIExecutionRecommendation(
            recommendation_id="story_pacing",
            label="Story-Driven Pacing",
            category="pacing",
            confidence=round(min(1.0, narrative_score / 100.0), 4),
            safe_to_apply=narrative_score >= 50,
            advisory_only=True,
            recommended_settings={"pacing_style": pacing},
            explanation=[
                f"Story flow: {flow_type}",
                f"Narrative score: {narrative_score:.0f}/100",
            ],
        )
    except Exception as exc:
        logger.debug("_build_story_pacing_recommendation_failed: %s", exc)
        return None


# ── Scoring and selection ─────────────────────────────────────────────────────

def _score_recommendation(rec: AIExecutionRecommendation) -> float:
    base = rec.confidence * 100
    base += _CATEGORY_BONUS.get(rec.category, 0.0)
    if not rec.safe_to_apply:
        base -= 20.0
    return base


def _select_recommended(
    recommendations: list[AIExecutionRecommendation],
) -> Optional[str]:
    if not recommendations:
        return None
    try:
        best = max(recommendations, key=_score_recommendation)
        return best.recommendation_id
    except Exception:
        return recommendations[0].recommendation_id if recommendations else None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_dict(val: Any) -> dict:
    return val if isinstance(val, dict) else {}


def _fallback_pack(reason: str) -> AIExecutionPack:
    logger.info("ai_execution_recommendation_fallback reason=%s", reason)
    return AIExecutionPack(
        available=False,
        mode="advisory",
        recommendations=[_build_safe_baseline()],
        recommended_pack_id="safe_baseline",
        warnings=[f"pack_error:{reason}"],
    )
