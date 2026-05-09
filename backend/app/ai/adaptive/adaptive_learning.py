"""
adaptive_learning.py — Adaptive creator learning engine. Phase 42.

Public API:
    build_adaptive_learning_pack(edit_plan, payload=None, context=None)
        -> AIAdaptiveLearningPack

Rules:
- Deterministic only
- Never raises
- Assistive-only (influences metadata, never overrides user settings)
- No payload mutation in-place
- No render execution
- No autonomous override
- No internet, no cloud AI, no model fine-tuning
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.adaptive.adaptive_schema import AIAdaptiveLearningPack, AICreatorPreferenceProfile
from app.ai.adaptive.adaptive_memory import load_creator_profile, update_creator_profile
from app.ai.adaptive.adaptive_safety import sanitize_adaptive_profile

logger = logging.getLogger("app.ai.adaptive.learning")

# Confidence threshold above which adaptive influence is reported as active
_INFLUENCE_THRESHOLD = 0.2

# How much retrieval intelligence contributes to initial influence weighting
_RETRIEVAL_WEIGHT = 0.15


def build_adaptive_learning_pack(
    edit_plan: Any,
    payload: Optional[Any] = None,
    context: Optional[dict] = None,
) -> AIAdaptiveLearningPack:
    """Build adaptive learning pack from edit plan and creator choices.

    Reads creator profile, derives learning signals, computes adaptive influences.
    Saves updated profile locally. Never raises.

    Args:
        edit_plan:  AIEditPlan with all Phase 1–41 metadata attached.
        payload:    Optional render request (read-only). Never mutated.
        context:    Optional dict with session context (e.g. selected choices).

    Returns:
        AIAdaptiveLearningPack with creator_profile, learned_preferences,
        adaptive_influences, and warnings.
    """
    try:
        return _build_pack(edit_plan, payload, context)
    except Exception as exc:
        logger.debug("adaptive_learning_build_error: %s", exc)
        return AIAdaptiveLearningPack(
            available=False,
            enabled=False,
            learning_mode="assistive_only",
            warnings=[f"adaptive_learning_error:{type(exc).__name__}"],
        )


def _build_pack(
    edit_plan: Any,
    payload: Optional[Any],
    context: Optional[dict],
) -> AIAdaptiveLearningPack:
    ctx = context or {}
    warnings: list[str] = []

    profile_id = str(ctx.get("profile_id", "default") or "default")

    # Load existing profile (never raises)
    profile = load_creator_profile(profile_id)

    # Extract learning signals from edit_plan + context
    feedback = _extract_feedback_signals(edit_plan, payload, ctx)

    has_feedback = any(bool(v) for v in feedback.values())

    if has_feedback:
        profile = update_creator_profile(profile, feedback)
        logger.info(
            "ai_adaptive_learning_applied profile_id=%s style=%s subtitle=%s pacing=%s camera=%s",
            profile_id,
            profile.creator_style_preference,
            profile.preferred_subtitle_style,
            profile.preferred_pacing_style,
            profile.preferred_camera_style,
        )
    else:
        logger.debug("ai_adaptive_learning_skipped profile_id=%s no_feedback_signals", profile_id)

    # Build learned preferences summary
    learned_preferences = _build_learned_preferences(profile)

    # Build adaptive influences (bounded, assistive-only)
    adaptive_influences = _build_adaptive_influences(profile, edit_plan)

    enabled = has_feedback or profile.selection_history_count > 0

    pack = AIAdaptiveLearningPack(
        available=True,
        enabled=enabled,
        learning_mode="assistive_only",
        creator_profile=sanitize_adaptive_profile(profile.to_dict()),
        learned_preferences=learned_preferences,
        adaptive_influences=adaptive_influences,
        warnings=warnings,
    )

    return pack


def _extract_feedback_signals(
    edit_plan: Any,
    payload: Optional[Any],
    context: dict,
) -> dict:
    """Extract safe learning signals from edit plan, payload, and context. Never raises."""
    feedback: dict = {}

    try:
        # From context (explicit session choices)
        for key in (
            "selected_creator_style",
            "selected_subtitle_style",
            "selected_pacing_style",
            "selected_camera_style",
            "selected_duration_range",
            "selected_variant_strategy",
            "export_completed",
        ):
            val = context.get(key)
            if val is not None:
                feedback[key] = val

        # From edit_plan metadata (inferred signals)
        if edit_plan is not None:
            _infer_from_edit_plan(edit_plan, feedback)

        # From payload (read-only inference)
        if payload is not None:
            _infer_from_payload(payload, feedback)

    except Exception as exc:
        logger.debug("adaptive_learning_signal_error: %s", exc)

    return feedback


def _infer_from_edit_plan(edit_plan: Any, feedback: dict) -> None:
    """Infer learning signals from edit plan metadata. Never raises. Read-only."""
    try:
        # Creator style from creator_style_adaptation
        if "selected_creator_style" not in feedback:
            csa = getattr(edit_plan, "creator_style_adaptation", None) or {}
            if isinstance(csa, dict):
                adapted = csa.get("adapted_style") or csa.get("creator_style") or ""
                if adapted:
                    feedback["selected_creator_style"] = str(adapted)

        # Subtitle style from subtitle_text_apply
        if "selected_subtitle_style" not in feedback:
            sta = getattr(edit_plan, "subtitle_text_apply", None) or {}
            if isinstance(sta, dict):
                style = sta.get("subtitle_style") or sta.get("applied_style") or ""
                if style:
                    feedback["selected_subtitle_style"] = str(style)

        # Pacing from pacing plan
        if "selected_pacing_style" not in feedback:
            pacing = getattr(edit_plan, "pacing", None)
            if pacing is not None:
                style = str(getattr(pacing, "pacing_style", "") or "")
                if style and style != "default":
                    feedback["selected_pacing_style"] = style

        # Camera from camera_motion_apply
        if "selected_camera_style" not in feedback:
            cma = getattr(edit_plan, "camera_motion_apply", None) or {}
            if isinstance(cma, dict):
                behavior = cma.get("camera_behavior") or cma.get("applied_behavior") or ""
                if behavior:
                    feedback["selected_camera_style"] = str(behavior)

        # Duration range from selected_segments
        if "selected_duration_range" not in feedback:
            segments = getattr(edit_plan, "selected_segments", None) or []
            if segments:
                total_dur = sum(
                    float(getattr(s, "end", 0) or 0) - float(getattr(s, "start", 0) or 0)
                    for s in segments
                )
                if total_dur > 0:
                    feedback["selected_duration_range"] = _classify_duration(total_dur)

        # Variant strategy from variant_selection
        if "selected_variant_strategy" not in feedback:
            vs = getattr(edit_plan, "variant_selection", None) or {}
            if isinstance(vs, dict) and vs.get("selected_variant_id"):
                feedback["selected_variant_strategy"] = "selected_variant"

    except Exception as exc:
        logger.debug("adaptive_infer_edit_plan_error: %s", exc)


def _infer_from_payload(payload: Any, feedback: dict) -> None:
    """Infer signals from render payload (read-only). Never raises."""
    try:
        mode = str(getattr(payload, "ai_mode", "") or "")
        if mode and "selected_creator_style" not in feedback:
            feedback["selected_creator_style"] = mode
    except Exception as exc:
        logger.debug("adaptive_infer_payload_error: %s", exc)


def _classify_duration(total_sec: float) -> str:
    if total_sec < 30:
        return "short_form"
    if total_sec < 90:
        return "mid_form"
    return "long_form"


def _build_learned_preferences(profile: AICreatorPreferenceProfile) -> dict:
    """Build a compact learned preferences summary. Never raises."""
    try:
        return {
            "creator_style": profile.creator_style_preference,
            "subtitle_style": profile.preferred_subtitle_style,
            "pacing_style": profile.preferred_pacing_style,
            "camera_style": profile.preferred_camera_style,
            "duration_range": profile.preferred_duration_range,
            "variant_strategy": profile.preferred_variant_strategy,
            "confidence": {
                "style": round(profile.style_confidence, 4),
                "subtitle": round(profile.subtitle_confidence, 4),
                "pacing": round(profile.pacing_confidence, 4),
                "camera": round(profile.camera_confidence, 4),
            },
            "history": {
                "selections": profile.selection_history_count,
                "exports": profile.export_history_count,
            },
        }
    except Exception:
        return {}


def _build_adaptive_influences(
    profile: AICreatorPreferenceProfile,
    edit_plan: Any,
) -> dict:
    """Build bounded adaptive influence signals. Assistive-only. Never raises.

    Influences:
    - retrieval ranking weight adjustment
    - subtitle enhancement weighting
    - pacing enhancement weighting
    - camera enhancement weighting
    - variant ranking weighting

    All values are metadata-only. No FFmpeg, no playback_speed, no subtitle timing.
    """
    try:
        influences: dict = {
            "retrieval_ranking_weight": 0.0,
            "subtitle_enhancement_weight": 0.0,
            "pacing_enhancement_weight": 0.0,
            "camera_enhancement_weight": 0.0,
            "variant_ranking_weight": 0.0,
            "preferred_creator_style": profile.creator_style_preference,
            "preferred_subtitle_style": profile.preferred_subtitle_style,
            "preferred_pacing_style": profile.preferred_pacing_style,
            "preferred_camera_style": profile.preferred_camera_style,
            "assistive_only": True,
        }

        # Influence retrieval ranking if style is well-learned
        if profile.style_confidence >= _INFLUENCE_THRESHOLD:
            influences["retrieval_ranking_weight"] = _bound(
                profile.style_confidence * _RETRIEVAL_WEIGHT
            )

        # Influence subtitle enhancement if subtitle preference is learned
        if profile.subtitle_confidence >= _INFLUENCE_THRESHOLD:
            influences["subtitle_enhancement_weight"] = _bound(
                profile.subtitle_confidence * 0.20
            )

        # Influence pacing enhancement if pacing preference is learned
        if profile.pacing_confidence >= _INFLUENCE_THRESHOLD:
            influences["pacing_enhancement_weight"] = _bound(
                profile.pacing_confidence * 0.20
            )

        # Influence camera enhancement if camera preference is learned
        if profile.camera_confidence >= _INFLUENCE_THRESHOLD:
            influences["camera_enhancement_weight"] = _bound(
                profile.camera_confidence * 0.20
            )

        # Influence variant ranking from export history
        if profile.export_history_count > 0:
            raw_variant_weight = min(profile.export_history_count * 0.02, 0.15)
            influences["variant_ranking_weight"] = _bound(raw_variant_weight)

        # Append retrieval intelligence signal if available
        _inject_retrieval_influence(influences, edit_plan, profile)

        return influences

    except Exception as exc:
        logger.debug("adaptive_influences_build_error: %s", exc)
        return {"assistive_only": True}


def _inject_retrieval_influence(
    influences: dict,
    edit_plan: Any,
    profile: AICreatorPreferenceProfile,
) -> None:
    """Incorporate retrieval intelligence into adaptive influences. Never raises."""
    try:
        cr = getattr(edit_plan, "creator_retrieval", None)
        if not isinstance(cr, dict) or not cr.get("enabled"):
            return

        matches = cr.get("matches", []) or []
        if not matches or not isinstance(matches, list):
            return

        # If retrieval matches creator style preference, amplify retrieval weight slightly
        for m in matches:
            if not isinstance(m, dict):
                continue
            style = str(m.get("creator_style", "") or "")
            if style and style == profile.creator_style_preference and profile.style_confidence >= _INFLUENCE_THRESHOLD:
                current = influences.get("retrieval_ranking_weight", 0.0)
                influences["retrieval_ranking_weight"] = _bound(current + 0.03)
                break

    except Exception as exc:
        logger.debug("adaptive_retrieval_inject_error: %s", exc)


def _bound(value: float) -> float:
    """Clamp influence weight to [0.0, 0.30]. Never raises."""
    try:
        return round(max(0.0, min(0.30, float(value))), 4)
    except Exception:
        return 0.0
