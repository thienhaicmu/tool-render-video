"""
camera_apply_engine.py — Safe camera motion apply engine. Phase 34.

Reads advisory camera metadata from Phase 18 (beat_visual_execution),
Phase 23 (creator_style_adaptation), Phase 25 (execution_recommendations),
Phase 27 (safe_render_mutations), Phase 33 (subtitle_text_apply).

Only applies camera guidance metadata when policy permits.
Deterministic. Never raises. Never rewrites crop coordinates.
No FFmpeg changes. No playback_speed mutation. No in-place payload mutation.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.camera.camera_apply_schema import (
    AICameraMotionApply,
    AICameraMotionApplyPack,
    _ALLOWED_CAMERA_TYPES,
    _FORBIDDEN_CAMERA_TYPES,
    _MIN_CONFIDENCE,
)
from app.ai.camera.camera_apply_safety import (
    sanitize_camera_motion_changes,
    is_camera_motion_apply_safe,
)

logger = logging.getLogger("app.ai.camera.camera_apply_engine")

# Hard cap on camera guidance entries applied per pack
_MAX_APPLIED: int = 6

# Policies that allow camera motion apply
_ALLOWED_POLICIES: frozenset[str] = frozenset({"balanced", "aggressive", "experimental"})


def build_camera_motion_apply_pack(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> AICameraMotionApplyPack:
    """Build a camera motion apply pack from edit plan metadata.

    Only applies guidance when:
    - policy is balanced, aggressive, or experimental
    - camera_type is in _ALLOWED_CAMERA_TYPES
    - all safety gates pass

    Returns a disabled pack if policy blocks. Never raises.
    Never rewrites crop coordinates. Never mutates payload in-place.
    """
    try:
        return _build_pack(edit_plan, payload, context or {})
    except Exception as exc:
        logger.debug("camera_apply_engine_failed: %s", exc)
        return _disabled_pack(reason=f"engine_error:{type(exc).__name__}")


def _build_pack(edit_plan: Any, payload: Any, context: dict) -> AICameraMotionApplyPack:
    job_id = str(context.get("job_id", "unknown"))

    # Policy gate
    effective_policy = _resolve_effective_policy(edit_plan, payload, context)
    if effective_policy not in _ALLOWED_POLICIES:
        logger.info(
            "ai_camera_motion_apply_skipped job_id=%s policy=%s",
            job_id, effective_policy,
        )
        return _disabled_pack(reason=f"policy_blocked:{effective_policy}")

    # Collect candidates from prior phase metadata
    raw_candidates = _collect_candidates(edit_plan)

    if not raw_candidates:
        logger.info(
            "ai_camera_motion_apply_skipped job_id=%s: no candidates", job_id
        )
        return AICameraMotionApplyPack(
            available=True,
            enabled=True,
            mode="active",
            applied=[],
            blocked=[],
            warnings=["no_camera_candidates_available"],
        )

    applied_list: list[AICameraMotionApply] = []
    blocked_list: list[AICameraMotionApply] = []

    for raw in raw_candidates:
        apply_id = str(raw.get("apply_id") or f"cma_{len(applied_list) + len(blocked_list)}")
        cam_type = str(raw.get("camera_type") or "")
        confidence = float(raw.get("confidence") or 0.0)
        source_id = str(raw.get("source_candidate_id") or "")
        changes = raw.get("changes") or {}

        # Applied count cap
        if len(applied_list) >= _MAX_APPLIED:
            blocked_list.append(AICameraMotionApply(
                apply_id=apply_id,
                camera_type=cam_type,
                source_candidate_id=source_id,
                confidence=confidence,
                applied=False,
                safe=False,
                changes=dict(changes),
                warnings=["max_applied_camera_guidance_reached"],
            ))
            continue

        if is_camera_motion_apply_safe(raw):
            safe_changes = sanitize_camera_motion_changes(changes)
            applied_list.append(AICameraMotionApply(
                apply_id=apply_id,
                camera_type=cam_type,
                source_candidate_id=source_id,
                confidence=confidence,
                applied=True,
                safe=True,
                target_scope="metadata",
                changes=safe_changes,
                explanation=[f"Safe {cam_type} guidance applied"],
            ))
            logger.info(
                "ai_camera_motion_guidance_applied job_id=%s apply_id=%s type=%s",
                job_id, apply_id, cam_type,
            )
        else:
            warn_reasons: list[str] = []
            if cam_type in _FORBIDDEN_CAMERA_TYPES:
                warn_reasons.append("forbidden_camera_type")
            elif cam_type not in _ALLOWED_CAMERA_TYPES:
                warn_reasons.append("unknown_camera_type")
            elif confidence < _MIN_CONFIDENCE:
                warn_reasons.append("confidence_too_low")
            else:
                raw_ch = raw.get("changes") or {}
                if isinstance(raw_ch, dict):
                    forbidden_found = [k for k in raw_ch if k in _FORBIDDEN_CHANGE_KEYS]
                    if forbidden_found:
                        warn_reasons.append(f"forbidden_change_key:{forbidden_found[0]}")
                if not warn_reasons:
                    warn_reasons.append("safety_gate_failed")

            blocked_list.append(AICameraMotionApply(
                apply_id=apply_id,
                camera_type=cam_type,
                source_candidate_id=source_id,
                confidence=confidence,
                applied=False,
                safe=False,
                changes=dict(changes),
                warnings=warn_reasons,
            ))
            logger.info(
                "ai_camera_motion_guidance_blocked job_id=%s apply_id=%s reason=%s",
                job_id, apply_id, warn_reasons[0] if warn_reasons else "unknown",
            )

    logger.info(
        "ai_camera_motion_apply_enabled job_id=%s applied=%d blocked=%d",
        job_id, len(applied_list), len(blocked_list),
    )
    return AICameraMotionApplyPack(
        available=True,
        enabled=True,
        mode="active",
        applied=applied_list,
        blocked=blocked_list,
        warnings=[],
    )


def _resolve_effective_policy(edit_plan: Any, payload: Any, context: dict) -> str:
    """Resolution priority: context > payload attribute > edit_plan dict > conservative."""
    try:
        ctx_policy = context.get("ai_apply_policy")
        if ctx_policy and isinstance(ctx_policy, str):
            return ctx_policy.strip().lower()
    except Exception:
        pass
    try:
        pol_attr = getattr(payload, "ai_apply_policy", None)
        if pol_attr and isinstance(pol_attr, str):
            return pol_attr.strip().lower()
    except Exception:
        pass
    try:
        plan_pol = getattr(edit_plan, "ai_apply_policy", {})
        if isinstance(plan_pol, dict):
            sp = plan_pol.get("selected_policy")
            if sp and isinstance(sp, str):
                return sp.strip().lower()
    except Exception:
        pass
    return "conservative"


def _collect_candidates(edit_plan: Any) -> list:
    """Collect camera guidance candidates from Phase metadata. Never raises."""
    candidates: list = []

    # Phase 18: beat_visual_execution — pulse regions and beat rhythm
    try:
        bve = getattr(edit_plan, "beat_visual_execution", {})
        if isinstance(bve, dict) and bve.get("available"):
            pulse_regions = bve.get("pulse_regions") or []
            if pulse_regions:
                bpm = bve.get("bpm")
                pulse_strength = float(bve.get("pulse_strength") or 0.2)
                # Clamp to safe range for beat_pulse_strength
                safe_pulse = max(0.0, min(0.35, pulse_strength))
                candidates.append({
                    "apply_id": "p18_beat_pulse",
                    "camera_type": "beat_aware_pulse",
                    "source_candidate_id": "beat_visual_execution",
                    "confidence": 0.75,
                    "target_scope": "metadata",
                    "changes": {
                        "beat_pulse_strength": safe_pulse,
                        "visual_rhythm_mode": "beat_sync",
                    },
                })
    except Exception:
        pass

    # Phase 23: creator_style_adaptation — camera behavior
    try:
        csa = getattr(edit_plan, "creator_style_adaptation", {})
        if isinstance(csa, dict) and csa.get("available"):
            adapted = csa.get("adapted_style") or {}
            if isinstance(adapted, dict):
                cam_behavior = str(adapted.get("camera_behavior") or adapted.get("camera") or "")
                conf = float(csa.get("confidence") or 0.0)
                if cam_behavior and conf >= _MIN_CONFIDENCE:
                    candidates.append({
                        "apply_id": "p23_creator_camera",
                        "camera_type": "creator_style_camera",
                        "source_candidate_id": "creator_style_adaptation",
                        "confidence": conf,
                        "target_scope": "metadata",
                        "changes": {"creator_style_camera": cam_behavior},
                    })
    except Exception:
        pass

    # Phase 5: camera plan (existing) — subtitle_safe framing
    try:
        camera_plan = getattr(edit_plan, "camera", None)
        if camera_plan is not None:
            subtitle_safe = bool(getattr(camera_plan, "subtitle_safe", True))
            mode = str(getattr(camera_plan, "mode", "default") or "default")
            confidence = 0.80  # camera plan is pre-validated
            if subtitle_safe:
                candidates.append({
                    "apply_id": "p5_subtitle_safe_framing",
                    "camera_type": "subtitle_safe_framing",
                    "source_candidate_id": "camera_plan",
                    "confidence": confidence,
                    "target_scope": "metadata",
                    "changes": {
                        "subtitle_safe_framing": True,
                        "camera_behavior": mode,
                    },
                })
    except Exception:
        pass

    # Phase 27: safe_render_mutations — motion smoothing hints
    try:
        srm = getattr(edit_plan, "safe_render_mutations", {})
        if isinstance(srm, dict) and srm.get("available"):
            for mut in (srm.get("mutations") or []):
                if not isinstance(mut, dict):
                    continue
                if str(mut.get("category") or "") == "visual_rhythm":
                    candidates.append({
                        "apply_id": f"p27_motion_smooth_{len(candidates)}",
                        "camera_type": "motion_smoothing_hint",
                        "source_candidate_id": "safe_render_mutations",
                        "confidence": 0.70,
                        "target_scope": "metadata",
                        "changes": {"motion_smoothing": True},
                    })
                    break  # one smoothing hint is enough
    except Exception:
        pass

    # Phase 33: subtitle_text_apply — if compact density applied, prefer subtitle_safe_framing
    try:
        sta = getattr(edit_plan, "subtitle_text_apply", {})
        if isinstance(sta, dict) and sta.get("enabled"):
            applied_opts = sta.get("applied") or []
            has_density = any(
                isinstance(o, dict) and o.get("optimization_type") in (
                    "compact_overload", "density_reduce"
                )
                for o in applied_opts
            )
            if has_density:
                # Only add if not already present from Phase 5
                already = any(c.get("camera_type") == "subtitle_safe_framing" for c in candidates)
                if not already:
                    candidates.append({
                        "apply_id": "p33_subtitle_safe_camera",
                        "camera_type": "subtitle_safe_framing",
                        "source_candidate_id": "subtitle_text_apply",
                        "confidence": 0.72,
                        "target_scope": "metadata",
                        "changes": {"subtitle_safe_framing": True},
                    })
    except Exception:
        pass

    return candidates


def _disabled_pack(reason: str = "disabled") -> AICameraMotionApplyPack:
    return AICameraMotionApplyPack(
        available=True,
        enabled=False,
        mode="disabled",
        applied=[],
        blocked=[],
        warnings=[reason],
    )
