"""
camera_quality_scorer.py — Deterministic camera quality dimension scorers. Phase 52B.

All scorers:
  - return int scores in [0, 100]
  - never raise
  - are metadata-based only (no frame analysis, no tracking, no motion_crop rewrite)
  - tolerate None / missing inputs

Public API:
    score_micro_jitter_risk(edit_plan) -> int
    score_whip_pan_risk(edit_plan) -> int
    score_crop_smoothness(edit_plan) -> int
    score_subject_stability(edit_plan) -> int
    score_scene_continuity(edit_plan) -> int
    score_creator_fit(edit_plan) -> int
    compute_confidence(edit_plan) -> float
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("app.ai.camera_quality.scorer")

# Baseline when signal is absent
_BASELINE = 55


# ---------------------------------------------------------------------------
# Micro jitter risk
# ---------------------------------------------------------------------------

def score_micro_jitter_risk(edit_plan: Any) -> int:
    """Evaluate micro-jitter risk from stability, deadzone, smoothing signals. Lower = better."""
    try:
        risk = 20  # moderate baseline — some jitter always possible

        cam_pref = _cam_pref(edit_plan)
        cma      = _get(edit_plan, "camera_motion_apply")

        stability  = str(cam_pref.get("stability_priority") or "unknown").lower()
        deadzone   = str(cam_pref.get("deadzone_preference") or "unknown").lower()
        risk_tol   = str(cam_pref.get("reframing_risk_tolerance") or "unknown").lower()
        smoothness = str(cam_pref.get("smoothness_priority") or "unknown").lower()

        # High stability → lower jitter risk
        if stability == "high":
            risk -= 10
        elif stability == "medium":
            risk -= 4
        elif stability == "low":
            risk += 8

        # Wide deadzone → less reactive → lower jitter
        if deadzone == "wide":
            risk -= 8
        elif deadzone == "narrow":
            risk += 10

        # Low risk tolerance → creator dislikes jitter → score reflects their risk
        if risk_tol == "low":
            risk -= 4  # conservative → lower operational jitter risk

        # High smoothness priority → better jitter suppression
        if smoothness == "high":
            risk -= 6
        elif smoothness == "low":
            risk += 5

        # motion_smoothing_hint applied → explicit jitter reduction
        applied = cma.get("applied") or []
        for entry in applied[:6]:
            if isinstance(entry, dict):
                cam_type = str(entry.get("camera_type") or "")
                if cam_type == "motion_smoothing_hint":
                    risk -= 8
                    break

        # Camera apply warnings → potential instability
        if cma.get("warnings"):
            risk += 5

        # Camera apply safety check failure → higher jitter risk
        for entry in (cma.get("applied") or []) + (cma.get("blocked") or []):
            if isinstance(entry, dict) and entry.get("safe") is False:
                risk += 6
                break

        return _clamp(round(risk))
    except Exception:
        return 20


# ---------------------------------------------------------------------------
# Whip-pan risk
# ---------------------------------------------------------------------------

def score_whip_pan_risk(edit_plan: Any) -> int:
    """Evaluate whip-pan / rapid framing change risk. Lower = better."""
    try:
        risk = 15  # moderate baseline

        cam_pref = _cam_pref(edit_plan)
        pacing   = _get(edit_plan, "pacing")
        bve      = _get(edit_plan, "beat_visual_execution")
        moi      = _get(edit_plan, "market_optimization_intelligence")

        motion_style = str(cam_pref.get("motion_style") or "unknown").lower()
        crop_agg     = str(cam_pref.get("crop_aggressiveness") or "unknown").lower()
        scene_sens   = str(cam_pref.get("scene_sensitivity") or "unknown").lower()

        # Motion style is the strongest predictor
        if motion_style == "static_center":
            risk -= 10
        elif motion_style == "smooth_subject":
            risk += 0
        elif motion_style == "dynamic_subject":
            risk += 15

        # High crop aggressiveness → more rapid reframing → higher whip-pan risk
        if crop_agg == "high":
            risk += 12
        elif crop_agg == "low":
            risk -= 8

        # High scene sensitivity → jumps on cuts → more whip-pan potential
        if scene_sens == "high":
            risk += 8
        elif scene_sens == "low":
            risk -= 4

        # Fast BPM + beat-synced visual → rapid camera events → more whip-pan
        bpm = float(pacing.get("bpm") or 0.0)
        if bpm > 160 and motion_style == "dynamic_subject":
            risk += 10
        elif bpm > 140:
            risk += 5
        elif bpm > 0 and bpm < 90:
            risk -= 4

        # Beat visual execution active → camera events happen on beat → lower arbitrary risk
        if bve.get("available"):
            risk -= 3

        # Camera market bias for high-energy markets → more dynamic → more whip-pan
        cam_bias = (moi.get("camera_market_bias") or {})
        cam_style = str(cam_bias.get("preferred_style") or "").lower()
        if cam_style == "dynamic_subject":
            risk += 6
        elif cam_style == "static_center":
            risk -= 4

        return _clamp(round(risk))
    except Exception:
        return 15


# ---------------------------------------------------------------------------
# Crop smoothness
# ---------------------------------------------------------------------------

def score_crop_smoothness(edit_plan: Any) -> int:
    """Evaluate crop motion smoothness from smoothing metadata and creator preference."""
    try:
        base = _BASELINE

        cam_pref = _cam_pref(edit_plan)
        cma      = _get(edit_plan, "camera_motion_apply")
        rqe      = _get(edit_plan, "render_quality_evaluation")

        smoothness = str(cam_pref.get("smoothness_priority") or "unknown").lower()
        deadzone   = str(cam_pref.get("deadzone_preference") or "unknown").lower()
        stability  = str(cam_pref.get("stability_priority") or "unknown").lower()

        # Smoothness priority directly maps to crop smoothness
        if smoothness == "high":
            base += 14
        elif smoothness == "medium":
            base += 6
        elif smoothness == "low":
            base -= 8

        # Wide deadzone → smoother crop motion
        if deadzone == "wide":
            base += 8
        elif deadzone == "medium":
            base += 3
        elif deadzone == "narrow":
            base -= 5

        # High stability → inherently smoother
        if stability == "high":
            base += 6

        # motion_smoothing_hint applied → explicit smoothing
        applied = cma.get("applied") or []
        for entry in applied[:6]:
            if isinstance(entry, dict):
                cam_type = str(entry.get("camera_type") or "")
                changes  = entry.get("changes") or {}
                if cam_type == "motion_smoothing_hint":
                    base += 8
                    break
                if changes.get("motion_smoothing"):
                    base += 5
                    break

        # Camera apply warnings → possible smoothness degradation
        if cma.get("warnings"):
            base -= 5

        # Phase 45 camera_smoothness feeds in (output_scores average)
        scores = rqe.get("output_scores") or []
        if scores:
            cam_scores = [
                float(s.get("camera_smoothness") or 0.0)
                for s in scores
                if isinstance(s, dict)
            ]
            if cam_scores:
                avg_cam = sum(cam_scores) / len(cam_scores)
                # Blend: 70% our metadata, 30% Phase 45 signal
                base = base * 0.7 + avg_cam * 0.3

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Subject stability
# ---------------------------------------------------------------------------

def score_subject_stability(edit_plan: Any) -> int:
    """Evaluate subject tracking stability from hold, center-bias, and camera signals."""
    try:
        base = _BASELINE

        cam_pref = _cam_pref(edit_plan)
        cma      = _get(edit_plan, "camera_motion_apply")

        subject_hold   = str(cam_pref.get("subject_hold") or "unknown").lower()
        stability      = str(cam_pref.get("stability_priority") or "unknown").lower()
        center_bias    = str(cam_pref.get("center_bias") or "unknown").lower()
        motion_style   = str(cam_pref.get("motion_style") or "unknown").lower()

        # Long subject hold → more stable subject framing
        if subject_hold == "long":
            base += 12
        elif subject_hold == "medium":
            base += 5
        elif subject_hold == "short":
            base -= 6

        # High stability priority → subject is kept stable
        if stability == "high":
            base += 10
        elif stability == "medium":
            base += 4
        elif stability == "low":
            base -= 6

        # Strong center bias → subject consistently centered → stable
        if center_bias == "high":
            base += 6
        elif center_bias == "medium":
            base += 2

        # Static center motion style → inherently stable subject
        if motion_style == "static_center":
            base += 8
        elif motion_style == "dynamic_subject":
            base -= 4

        # subject_lock_preference applied → explicit stability
        applied = cma.get("applied") or []
        for entry in applied[:6]:
            if isinstance(entry, dict):
                cam_type = str(entry.get("camera_type") or "")
                if cam_type == "subject_lock_preference":
                    base += 8
                    break

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Scene continuity
# ---------------------------------------------------------------------------

def score_scene_continuity(edit_plan: Any) -> int:
    """Evaluate scene-aware continuity from sensitivity and beat-visual signals."""
    try:
        base = _BASELINE

        cam_pref = _cam_pref(edit_plan)
        bve      = _get(edit_plan, "beat_visual_execution")
        story    = _get(edit_plan, "story")
        cma      = _get(edit_plan, "camera_motion_apply")

        scene_sens = str(cam_pref.get("scene_sensitivity") or "unknown").lower()
        motion_style = str(cam_pref.get("motion_style") or "unknown").lower()

        # Medium scene sensitivity = best continuity (responsive but not jumpy)
        if scene_sens == "medium":
            base += 10
        elif scene_sens == "low":
            base += 3    # less responsive but stable
        elif scene_sens == "high":
            base -= 3    # jumpy on cuts → continuity disruption

        # Beat-visual execution available → scene-aware camera transitions
        if bve.get("available"):
            base += 6
            if bve.get("warnings"):
                base -= 3

        # Story intelligence available → narrative-aware camera
        if story.get("available"):
            seg_count = len(story.get("segments") or [])
            if seg_count > 0:
                base += 4

        # dynamic_safe camera type applied → scene-aware motion
        applied = cma.get("applied") or []
        for entry in applied[:6]:
            if isinstance(entry, dict):
                cam_type = str(entry.get("camera_type") or "")
                if cam_type == "dynamic_safe":
                    base += 6
                    break

        # Static motion style → high scene continuity (no abrupt reframes)
        if motion_style == "static_center":
            base += 5
        elif motion_style == "dynamic_subject":
            base -= 3

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Creator camera fit
# ---------------------------------------------------------------------------

def score_creator_fit(edit_plan: Any) -> int:
    """Evaluate how well camera decisions align with creator's established camera preferences."""
    try:
        base = _BASELINE

        ccp  = _get(edit_plan, "creator_camera_preference")
        cpp  = _get(edit_plan, "creator_preference_profile")
        cpe  = _get(edit_plan, "creator_preset_evolution")
        aci  = _get(edit_plan, "adaptive_creator_intelligence")

        available_50b = bool(ccp.get("available"))

        if not available_50b:
            return _clamp(round(base))

        # Phase 50B: camera preference confidence
        cam_pref_dict = ccp.get("camera_preference") or {}
        pref_conf     = float(cam_pref_dict.get("confidence") or 0.0)
        pref_motion   = str(cam_pref_dict.get("motion_style") or "unknown").lower()
        pref_stab     = str(cam_pref_dict.get("stability_priority") or "unknown").lower()

        if pref_conf >= 0.7:
            base += 15
        elif pref_conf >= 0.5:
            base += 10
        elif pref_conf >= 0.3:
            base += 5

        # Phase 50B tuning pack tier
        tuning = ccp.get("tuning_pack") or {}
        tier   = str(tuning.get("confidence_tier") or "low").lower()
        if tier == "high":
            base += 10
        elif tier == "medium":
            base += 5

        # Phase 50D: creator preference profile camera confidence
        cam_profile = cpp.get("camera") or {}
        prof_motion = str(cam_profile.get("motion_style") or "unknown").lower()
        prof_conf   = float(cam_profile.get("confidence") or 0.0)

        if prof_motion != "unknown" and prof_motion == pref_motion:
            base += 6  # 50B + 50D agree → strong alignment
        if prof_conf >= 0.6:
            base += 4

        # Stability preference satisfied: high stability in preference
        if pref_stab == "high":
            base += 4

        # Phase 46: preset evolution maturity
        if cpe.get("available") and cpe.get("evolved_presets"):
            base += 3

        # Phase 42: adaptive style confidence
        profile = aci.get("creator_profile") or {}
        style_conf = float(profile.get("style_confidence") or 0.0)
        if style_conf >= 0.4:
            base += min(6, round(style_conf * 8))

        return _clamp(round(base))
    except Exception:
        return _BASELINE


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def compute_confidence(edit_plan: Any) -> float:
    """Compute evaluation confidence from signal richness. 0–1."""
    try:
        signals = 0
        for attr in (
            "creator_camera_preference",
            "camera_motion_apply",
            "creator_preference_profile",
            "market_optimization_intelligence",
            "creator_preset_evolution",
            "beat_visual_execution",
            "pacing",
            "render_quality_evaluation",
        ):
            d = _get(edit_plan, attr)
            if d and (d.get("available") or d.get("enabled") or len(d) > 1):
                signals += 1

        # AICameraPlan is always present
        cam = _get_attr(edit_plan, "camera")
        if cam is not None:
            signals += 1

        raw = signals / 9.0
        return round(max(0.0, min(1.0, raw)), 2)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cam_pref(edit_plan: Any) -> dict:
    """Get camera_preference sub-dict from creator_camera_preference."""
    try:
        ccp = _get(edit_plan, "creator_camera_preference")
        pref = ccp.get("camera_preference")
        return pref if isinstance(pref, dict) else {}
    except Exception:
        return {}


def _get(edit_plan: Any, attr: str) -> dict:
    try:
        if edit_plan is None:
            return {}
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _get_attr(edit_plan: Any, attr: str) -> Any:
    try:
        return getattr(edit_plan, attr, None)
    except Exception:
        return None


def _clamp(v: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(v)))
