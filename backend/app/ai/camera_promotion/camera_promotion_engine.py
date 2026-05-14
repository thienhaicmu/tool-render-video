"""
camera_promotion_engine.py — Phase 59B Camera Influence Promotion.

Promotes advisory camera influence metadata into actual camera render
configuration on the payload. Second safe execution promotion layer.

Promoted fields:
    payload.reframe_mode          (center → motion/subject/face)
    payload.motion_aware_crop     (enable only, never disable)

Advisory only (no payload mutation):
    tuning_applied.deadzone_delta
    tuning_applied.smoothing_delta   (ema_alpha_delta)
    tuning_applied.subject_hold_delta
    tuning_applied.crop_aggressiveness

Design rules:
  - Never raises — returns safe fallback on any error.
  - User explicit reframe_mode wins: only promotes FROM the AI-neutral default.
  - camera_ai_reframe_lock blocks all promotion.
  - Only enable motion_aware_crop — never disable.
  - Quality gates restrict to stability when risk signals are high.
  - Confidence thresholds block low-quality promotions.
  - No motion_crop algorithm rewrite.
  - No tracking logic rewrite.
  - No scene detection rewrite.
  - No FFmpeg mutation.
  - No playback_speed mutation.
  - Executor remains authority.

Public API:
    promote_camera_influence(payload, edit_plan, context=None)
        -> tuple[payload, dict]

Promotion report shape:
    {
        "camera_execution_promotion": {
            "applied": bool,
            "reframe_mode_applied": str | None,
            "motion_aware_crop_applied": bool,
            "tuning_applied": dict,    # advisory only — no field mutation
            "confidence": float,
            "reason": str,
            "reasoning": list[str],
        }
    }

Safety contract:
    ❌ No motion_crop algorithm rewrite
    ❌ No tracking logic rewrite
    ❌ No scene detection rewrite
    ❌ No FFmpeg mutation
    ❌ No render pipeline rewrite
    ❌ No playback_speed mutation
    ❌ No executor override
    ❌ No new reframe mode generation
    ✅ Only promotes from AI-neutral default reframe_mode
    ✅ Reframe mode validated against ALLOWED_PROMOTION_MODES
    ✅ Confidence gates enforced before any mutation
    ✅ Quality gates block risky promotions
    ✅ User override respected (reframe_mode not in neutral set → no change)
    ✅ motion_aware_crop enable-only (never disabled)
    ✅ Tuning deltas bounded by hard limits
    ✅ Deterministic: same inputs → same output
    ✅ Never raises — fallback-safe on any error
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.camera_promotion")

# ---------------------------------------------------------------------------
# Allowed promotion targets
# ---------------------------------------------------------------------------
ALLOWED_REFRAME_MODES: frozenset = frozenset({"center", "motion", "subject", "face"})
ALLOWED_PROMOTION_MODES: frozenset = frozenset({"motion", "subject", "face"})

# Modes that mean "user has no explicit preference" — AI may promote from these.
# "center" is the RenderRequest default. None/"" covers unset/null.
_AI_NEUTRAL_REFRAME: frozenset = frozenset({"center", None, ""})

# Confidence thresholds (conservative)
_CONF_THRESHOLD_REFRAME:     float = 0.82
_CONF_THRESHOLD_MOTION_CROP: float = 0.85
_CONF_THRESHOLD_TUNING:      float = 0.80

# Hard bounds for advisory tuning report (enforced even though no field is mutated)
_MAX_DEADZONE_DELTA:     float = 0.05
_MAX_SMOOTHING_DELTA:    float = 0.08
_MAX_SUBJECT_HOLD_DELTA: int   = 12

# Quality gate thresholds (integer scores 0–100 from Phase 52B)
_HIGH_RISK_THRESHOLD:    int = 60   # micro_jitter_risk or whip_pan_risk >= this → restrict
_LOW_FIT_THRESHOLD:      int = 30   # camera_fit <= this (when available) → conservative only

# Reframe modes that justify enabling motion_aware_crop
_CROP_ELIGIBLE_REFRAME_MODES: frozenset = frozenset({"motion", "subject", "face"})

# Phase 50B motion_style → reframe_mode mapping
_MOTION_STYLE_TO_REFRAME: dict = {
    "smooth_subject":  "subject",
    "dynamic_subject": "motion",
    "static_center":   None,   # explicitly means "don't change"
}

# Phase 55E platform motion_energy → reframe_mode (conservative)
_MOTION_ENERGY_TO_REFRAME: dict = {
    "high":        "motion",
    "medium_high": "motion",
    "medium":      "subject",
    "low_medium":  "subject",
    "low":         None,   # conservative — don't promote
    "unknown":     None,
}

# Maximum reasoning lines in the promotion report
_MAX_REASONING = 6


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def promote_camera_influence(
    payload: Any,
    edit_plan: Any,
    context: Optional[dict] = None,
) -> tuple[Any, dict]:
    """Promote advisory camera influence metadata to actual render configuration.

    May mutate payload.reframe_mode and/or payload.motion_aware_crop in-place
    when promotion conditions are met. Returns (payload, promotion_report).

    Args:
        payload:   RenderRequest-compatible object with camera config fields.
        edit_plan: AIEditPlan (or None/dict) with Phase 50B–57 metadata.
        context:   Optional dict with "job_id" etc. for logging.

    Returns:
        (payload, {"camera_execution_promotion": {...}})
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        report = _promote(payload, edit_plan, job_id)
        return payload, report
    except Exception as exc:
        logger.warning("camera_promotion_unexpected_error job_id=%s: %s", job_id, exc)
        return payload, _fallback_report("promotion_error")


# ---------------------------------------------------------------------------
# Core promotion
# ---------------------------------------------------------------------------

def _promote(payload: Any, edit_plan: Any, job_id: str) -> dict:
    """Core promotion logic. May raise — caller wraps in try/except."""

    # ── Gate 1: AI flags ───────────────────────────────────────────────────
    if not bool(getattr(payload, "ai_director_enabled", False)):
        return _fallback_report("ai_director_disabled")

    if not bool(getattr(payload, "ai_render_influence_enabled", False)):
        return _fallback_report("ai_render_influence_disabled")

    if edit_plan is None:
        return _fallback_report("no_edit_plan")

    # ── Gate 2: user override detection ───────────────────────────────────
    current_reframe = str(getattr(payload, "reframe_mode", "center") or "center").strip().lower()
    reframe_locked  = bool(getattr(payload, "camera_ai_reframe_lock", False))

    if reframe_locked:
        logger.debug("camera_promotion_skipped job_id=%s reason=reframe_locked", job_id)
        return _fallback_report("user_override", note="camera_ai_reframe_lock=true")

    if current_reframe not in _AI_NEUTRAL_REFRAME:
        logger.debug(
            "camera_promotion_skipped job_id=%s reason=user_set_reframe reframe=%r",
            job_id, current_reframe,
        )
        return _fallback_report("user_override", note=f"reframe_mode={current_reframe!r}")

    # ── Read signal sources ────────────────────────────────────────────────
    cam_pref  = _get_dict(edit_plan, "creator_camera_preference")
    cam_qual  = _get_dict(edit_plan, "camera_quality_v2")
    prs       = _get_dict(edit_plan, "platform_render_strategy")
    psi       = _get_dict(edit_plan, "platform_strategy_influence")
    pqf       = _get_dict(edit_plan, "platform_quality_feedback")

    # ── Effective confidence ───────────────────────────────────────────────
    pref_inner  = (cam_pref.get("camera_preference") or {}) if cam_pref else {}
    pref_conf   = _safe_float(pref_inner.get("confidence"))
    prs_conf    = _safe_float(prs.get("confidence")) if (prs and prs.get("available")) else 0.0
    effective_conf = max(pref_conf, prs_conf)

    # ── Quality gates ──────────────────────────────────────────────────────
    quality_flags = _check_quality_gates(cam_qual, pqf)

    reasoning: list[str] = []
    applied_any = False

    # ── Reframe mode promotion ─────────────────────────────────────────────
    reframe_applied: Optional[str] = None
    if effective_conf >= _CONF_THRESHOLD_REFRAME:
        candidate, reframe_reason = _resolve_reframe_mode(
            cam_pref, pref_inner, prs, psi, quality_flags
        )
        if candidate and candidate in ALLOWED_PROMOTION_MODES:
            try:
                payload.reframe_mode = candidate
                reframe_applied = candidate
                applied_any = True
                reasoning.append(reframe_reason)
                logger.info(
                    "camera_reframe_promoted job_id=%s reframe=%r conf=%.3f",
                    job_id, candidate, effective_conf,
                )
            except Exception as exc:
                logger.debug(
                    "camera_reframe_set_failed job_id=%s: %s", job_id, exc
                )

    # ── motion_aware_crop promotion ────────────────────────────────────────
    # Enable only — never disable.
    motion_crop_applied = False
    existing_motion_crop = bool(getattr(payload, "motion_aware_crop", False))

    if (
        not existing_motion_crop
        and effective_conf >= _CONF_THRESHOLD_MOTION_CROP
        and not quality_flags["high_jitter"]
        and not quality_flags["high_whip_pan"]
    ):
        # Only enable if the resulting reframe_mode justifies it
        final_reframe = reframe_applied or current_reframe
        if final_reframe in _CROP_ELIGIBLE_REFRAME_MODES:
            try:
                payload.motion_aware_crop = True
                motion_crop_applied = True
                applied_any = True
                reasoning.append(
                    f"Reframe mode {final_reframe!r} justifies motion-aware crop with "
                    f"conf={effective_conf:.3f}"
                )
                logger.info(
                    "camera_motion_crop_promoted job_id=%s reframe=%r conf=%.3f",
                    job_id, final_reframe, effective_conf,
                )
            except Exception as exc:
                logger.debug(
                    "camera_motion_crop_set_failed job_id=%s: %s", job_id, exc
                )

    # ── Advisory tuning (no field mutation) ───────────────────────────────
    tuning_applied: dict = {}
    if effective_conf >= _CONF_THRESHOLD_TUNING:
        tuning_applied = _resolve_tuning_advisory(cam_pref, quality_flags)
        if tuning_applied:
            tuning_desc = ", ".join(f"{k}={v}" for k, v in tuning_applied.items())
            reasoning.append(f"Advisory tuning: {tuning_desc}")

    if not applied_any:
        return _fallback_report(
            "no_eligible_promotion",
            confidence=effective_conf,
            reasoning=reasoning,
        )

    logger.info(
        "camera_promotion_applied job_id=%s reframe=%r crop=%s tuning=%r conf=%.3f",
        job_id, reframe_applied, motion_crop_applied, list(tuning_applied.keys()), effective_conf,
    )

    return {
        "camera_execution_promotion": {
            "applied":                  True,
            "reframe_mode_applied":     reframe_applied,
            "motion_aware_crop_applied": motion_crop_applied,
            "tuning_applied":           tuning_applied,   # advisory only
            "confidence":               round(effective_conf, 4),
            "reason":                   "promotion_applied",
            "reasoning":                reasoning[:_MAX_REASONING],
        }
    }


# ---------------------------------------------------------------------------
# Quality gate checker
# ---------------------------------------------------------------------------

def _check_quality_gates(cam_qual: dict, pqf: dict) -> dict:
    """Evaluate risk signals. Returns a flags dict — never raises."""
    flags = {
        "high_jitter":   False,
        "high_whip_pan": False,
        "low_camera_fit": False,
    }
    try:
        jitter   = int(cam_qual.get("micro_jitter_risk") or 0)
        whip_pan = int(cam_qual.get("whip_pan_risk") or 0)
        if jitter >= _HIGH_RISK_THRESHOLD:
            flags["high_jitter"] = True
        if whip_pan >= _HIGH_RISK_THRESHOLD:
            flags["high_whip_pan"] = True
    except (TypeError, ValueError):
        pass

    try:
        if pqf and pqf.get("available"):
            cam_fit = int(pqf.get("camera_fit") or 0)
            if cam_fit <= _LOW_FIT_THRESHOLD:
                flags["low_camera_fit"] = True
    except (TypeError, ValueError):
        pass

    return flags


# ---------------------------------------------------------------------------
# Signal resolvers
# ---------------------------------------------------------------------------

def _resolve_reframe_mode(
    cam_pref: dict,
    pref_inner: dict,
    prs: dict,
    psi: dict,
    quality_flags: dict,
) -> tuple[Optional[str], str]:
    """Priority-ordered reframe mode resolution. Returns (reframe_mode | None, reason)."""

    # Quality override: if low camera fit → conservative only (no motion/dynamic)
    restrict_to_subject = quality_flags["high_jitter"] or quality_flags["low_camera_fit"]

    # 1. Phase 50B creator camera preference (most creator-specific)
    if cam_pref and cam_pref.get("available"):
        motion_style = str(pref_inner.get("motion_style") or "unknown").strip().lower()
        reframe = _MOTION_STYLE_TO_REFRAME.get(motion_style)
        if reframe is not None and reframe in ALLOWED_PROMOTION_MODES:
            if restrict_to_subject and reframe == "motion":
                reframe = "subject"  # downgrade to stable subject tracking
                return reframe, (
                    f"Creator camera preference {motion_style!r} downgraded to "
                    f"'subject' due to quality risk flags"
                )
            return reframe, f"Creator camera preference motion_style={motion_style!r} → reframe={reframe!r}"

    # 2. Phase 55E platform render strategy (requires available=True)
    if prs and prs.get("available"):
        prs_cam = (prs.get("strategy") or {}).get("camera") or {}
        motion_energy = str(prs_cam.get("motion_energy") or "unknown").strip().lower()
        reframe = _MOTION_ENERGY_TO_REFRAME.get(motion_energy)
        if reframe and reframe in ALLOWED_PROMOTION_MODES:
            platform = str(prs.get("platform") or "")
            if restrict_to_subject and reframe == "motion":
                reframe = "subject"
                return reframe, (
                    f"Platform strategy ({platform}) motion_energy={motion_energy!r} "
                    f"downgraded to 'subject' due to quality risk flags"
                )
            return reframe, (
                f"Platform strategy ({platform}) motion_energy={motion_energy!r} "
                f"→ reframe={reframe!r}"
            )

    # 3. Phase 56 platform strategy influence
    if psi and psi.get("available"):
        psi_cam = (psi.get("camera") or {})
        if psi_cam.get("supported"):
            psi_bias = (psi_cam.get("bias") or {})
            psi_energy = str(psi_bias.get("motion_energy") or "").strip().lower()
            reframe = _MOTION_ENERGY_TO_REFRAME.get(psi_energy)
            if reframe and reframe in ALLOWED_PROMOTION_MODES:
                if restrict_to_subject and reframe == "motion":
                    reframe = "subject"
                return reframe, (
                    f"Platform strategy influence motion_energy={psi_energy!r} "
                    f"→ reframe={reframe!r}"
                )

    return None, ""


def _resolve_tuning_advisory(cam_pref: dict, quality_flags: dict) -> dict:
    """Build an advisory tuning delta dict. No field is mutated — report only."""
    tuning: dict = {}

    if not (cam_pref and cam_pref.get("available")):
        return tuning

    tp = cam_pref.get("tuning_pack") or {}
    if not tp.get("applied"):
        return tuning

    # whip_pan_risk high → block all aggressive tuning
    if quality_flags["high_whip_pan"]:
        return tuning

    def _clamp_f(val: Any, lo: float, hi: float) -> Optional[float]:
        try:
            v = float(val)
            if v == 0.0:
                return None
            return max(lo, min(hi, v))
        except (TypeError, ValueError):
            return None

    def _clamp_i(val: Any, lo: int, hi: int) -> Optional[int]:
        try:
            v = int(val)
            if v == 0:
                return None
            return max(lo, min(hi, v))
        except (TypeError, ValueError):
            return None

    # Reduce tuning aggressiveness when jitter risk is high
    scale = 0.5 if quality_flags["high_jitter"] else 1.0

    dz = _clamp_f(
        (tp.get("deadzone_delta") or 0.0) * scale,
        -_MAX_DEADZONE_DELTA, _MAX_DEADZONE_DELTA,
    )
    if dz is not None:
        tuning["deadzone_delta"] = round(dz, 4)

    sm = _clamp_f(
        (tp.get("ema_alpha_delta") or 0.0) * scale,
        -_MAX_SMOOTHING_DELTA, _MAX_SMOOTHING_DELTA,
    )
    if sm is not None:
        tuning["smoothing_delta"] = round(sm, 4)

    hf = _clamp_i(
        int((tp.get("hold_frames_delta") or 0) * scale),
        -_MAX_SUBJECT_HOLD_DELTA, _MAX_SUBJECT_HOLD_DELTA,
    )
    if hf is not None:
        tuning["subject_hold_delta"] = hf

    # Crop aggressiveness from Phase 50B preference (advisory label, not numeric)
    pref_inner = cam_pref.get("camera_preference") or {}
    crop_agg = str(pref_inner.get("crop_aggressiveness") or "").strip().lower()
    if crop_agg in ("low", "medium", "high") and not quality_flags["high_jitter"]:
        tuning["crop_aggressiveness"] = crop_agg

    return tuning


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fallback_report(
    reason: str,
    note: str = "",
    confidence: float = 0.0,
    reasoning: Optional[list] = None,
) -> dict:
    full_reason = f"{reason}:{note}" if note else reason
    return {
        "camera_execution_promotion": {
            "applied":                   False,
            "reframe_mode_applied":      None,
            "motion_aware_crop_applied": False,
            "tuning_applied":            {},
            "confidence":                round(confidence, 4),
            "reason":                    full_reason,
            "reasoning":                 list(reasoning or []),
        }
    }


def _get_dict(edit_plan: Any, attr: str) -> dict:
    """Duck-typed attribute read — works for AIEditPlan or dict. Never raises."""
    try:
        if isinstance(edit_plan, dict):
            val = edit_plan.get(attr)
        else:
            val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_float(val: Any) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0
