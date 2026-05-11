"""
camera_preference_inference.py — Creator Camera Preference Intelligence Engine. Phase 50B.

Infers nine creator camera preference dimensions from available AI metadata signals.
Metadata-only: no motion_crop rewrite, no tracking logic change, no FFmpeg mutation.
No executor override. No internet. No cloud AI.

Public API:
    infer_camera_preference(edit_plan) -> AICameraPreference

Safety contract:
    ❌ No motion_crop rewrite
    ❌ No tracking rewrite
    ❌ No new crop engine
    ❌ No FFmpeg mutation
    ❌ No executor override
    ❌ No autonomous execution
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.creator_camera.camera_preference_schema import (
    ALLOWED_MOTION_STYLES, ALLOWED_AGGRESSIVENESS, ALLOWED_STABILITY_PRIORITY,
    ALLOWED_DEADZONE, ALLOWED_SUBJECT_HOLD, ALLOWED_SCENE_SENSITIVITY,
    ALLOWED_CENTER_BIAS, ALLOWED_RISK_TOLERANCE, ALLOWED_SMOOTHNESS_PRIORITY,
    AICameraPreference,
)

logger = logging.getLogger("app.ai.creator_camera.inference")

# Number of distinct signal domains we draw from
_MAX_SIGNAL_DOMAINS = 8

# Max creator-facing signal strings
_MAX_SIGNAL_ITEMS = 5


def infer_camera_preference(edit_plan: Any) -> AICameraPreference:
    """Infer creator camera preferences from AI metadata. Never raises.

    Args:
        edit_plan: AIEditPlan with Phase 23, 34, 42–48 metadata (or None).

    Returns:
        AICameraPreference with inferred dimensions and confidence.
    """
    if edit_plan is None:
        return AICameraPreference()
    try:
        return _infer(edit_plan)
    except Exception as exc:
        logger.debug("camera_preference_inference_error: %s", exc)
        return AICameraPreference()


def _infer(edit_plan: Any) -> AICameraPreference:
    signals: list[str] = []
    active_domains = 0

    # Collect signal source dicts
    camera_apply   = _get_dict(edit_plan, "camera_motion_apply")
    adaptive       = _get_dict(edit_plan, "adaptive_creator_intelligence")
    feedback       = _get_dict(edit_plan, "creator_feedback_intelligence")
    market         = _get_dict(edit_plan, "market_optimization_intelligence")
    quality        = _get_dict(edit_plan, "render_quality_evaluation")
    preset_ev      = _get_dict(edit_plan, "creator_preset_evolution")
    influence      = _get_dict(edit_plan, "safe_influence_pack")
    orchestration  = _get_dict(edit_plan, "multi_signal_orchestration")

    # ── Motion style ─────────────────────────────────────────────────────────
    motion_style, ms_sig = _infer_motion_style(
        camera_apply, influence, orchestration, market, feedback
    )
    if ms_sig:
        signals.append(ms_sig)
        active_domains += 1

    # ── Crop aggressiveness ───────────────────────────────────────────────────
    crop_aggressiveness, ca_sig = _infer_crop_aggressiveness(motion_style, market, quality)
    if ca_sig:
        signals.append(ca_sig)
        active_domains += 1

    # ── Stability priority ────────────────────────────────────────────────────
    stability_priority, sp_sig = _infer_stability_priority(motion_style, quality, feedback)
    if sp_sig:
        signals.append(sp_sig)
        active_domains += 1

    # ── Deadzone preference ───────────────────────────────────────────────────
    deadzone_preference, dz_sig = _infer_deadzone_preference(motion_style, market)
    if dz_sig:
        signals.append(dz_sig)
        active_domains += 1

    # ── Subject hold ─────────────────────────────────────────────────────────
    subject_hold, sh_sig = _infer_subject_hold(motion_style, market)
    if sh_sig:
        signals.append(sh_sig)
        active_domains += 1

    # ── Scene sensitivity ─────────────────────────────────────────────────────
    scene_sensitivity, ss_sig = _infer_scene_sensitivity(motion_style, market)
    if ss_sig:
        signals.append(ss_sig)
        active_domains += 1

    # ── Center bias (derived from motion style) ────────────────────────────────
    center_bias = _infer_center_bias(motion_style)

    # ── Reframing risk tolerance ──────────────────────────────────────────────
    risk_tolerance, rt_sig = _infer_risk_tolerance(
        motion_style, quality, feedback
    )
    if rt_sig:
        signals.append(rt_sig)
        active_domains += 1

    # ── Smoothness priority ───────────────────────────────────────────────────
    smoothness_priority = _infer_smoothness_priority(stability_priority, motion_style)

    # ── Confidence ────────────────────────────────────────────────────────────
    confidence = _compute_confidence(active_domains, adaptive, feedback)

    return AICameraPreference(
        motion_style=motion_style,
        crop_aggressiveness=crop_aggressiveness,
        stability_priority=stability_priority,
        deadzone_preference=deadzone_preference,
        subject_hold=subject_hold,
        scene_sensitivity=scene_sensitivity,
        center_bias=center_bias,
        reframing_risk_tolerance=risk_tolerance,
        smoothness_priority=smoothness_priority,
        confidence=confidence,
        signals=signals[:_MAX_SIGNAL_ITEMS],
    )


# ---------------------------------------------------------------------------
# Dimension inference — motion style
# ---------------------------------------------------------------------------

def _infer_motion_style(camera_apply, influence, orchestration, market, feedback):
    """Infer motion style. Returns (style, signal_str)."""

    # 1. Phase 48 camera bias
    si = influence.get("safe_influence") or {}
    cam_bias = str(si.get("camera_motion_bias") or "").lower()
    mapped = _map_motion_style(cam_bias)
    if mapped != "unknown":
        return mapped, f"AI influence recommended {mapped} camera motion"

    # 2. Phase 47 orchestration
    rec = orchestration.get("recommended_strategy") or {}
    orc_cam = _map_motion_style(str(rec.get("camera_motion") or ""))
    if orc_cam != "unknown":
        return orc_cam, f"Multi-signal orchestration recommended {orc_cam} camera style"

    # 3. Phase 34 camera apply
    applied = camera_apply.get("applied") or []
    for entry in applied[:3]:
        if isinstance(entry, dict):
            changes = entry.get("changes") or {}
            cam_behavior = str(changes.get("camera_behavior") or "").lower()
            mapped = _map_motion_style(cam_behavior)
            if mapped != "unknown":
                return mapped, f"Prior camera apply metadata suggests {mapped} motion"

    # 4. Phase 43 feedback (look for camera_style dominance)
    fb_patterns = feedback.get("learned_patterns") or {}
    fb_cam = str(fb_patterns.get("camera_style_pattern") or "").lower()
    fb_mapped = _map_motion_style(fb_cam)
    if fb_mapped != "unknown":
        return fb_mapped, f"Creator feedback shows preference for {fb_mapped} camera style"

    # 5. Market profile
    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower()
    if "tiktok" in target or "reels" in target:
        return "dynamic_subject", "Viral market typically uses dynamic subject tracking"
    if "podcast" in target or "educational" in target:
        return "static_center", f"{target} market uses static center framing"
    if "shorts" in target or "youtube" in target:
        return "smooth_subject", "YouTube Shorts market uses smooth subject tracking"

    return "unknown", ""


def _map_motion_style(raw: str) -> str:
    if not raw:
        return "unknown"
    s = raw.lower().strip()
    if s in ("static", "static_center", "locked", "static_framing", "static_podcast"):
        return "static_center"
    if s in ("smooth_subject", "smooth", "smooth_social", "creator_framing", "social_framing",
             "cinematic", "smooth_engagement"):
        return "smooth_subject"
    if s in ("dynamic_subject", "dynamic", "dynamic_safe", "fast_follow"):
        return "dynamic_subject"
    if s in ALLOWED_MOTION_STYLES and s != "unknown":
        return s
    return "unknown"


# ---------------------------------------------------------------------------
# Dimension inference — crop aggressiveness
# ---------------------------------------------------------------------------

def _infer_crop_aggressiveness(motion_style: str, market, quality):
    """Infer crop aggressiveness. Returns (value, signal_str)."""

    # Quality evaluation — camera_smoothness score guides aggressiveness
    output_scores = quality.get("output_scores") or []
    if output_scores:
        try:
            cam_scores = [
                float(s.get("camera_smoothness") or 0.0)
                for s in output_scores if isinstance(s, dict)
            ]
            if cam_scores:
                avg = sum(cam_scores) / len(cam_scores)
                if avg >= 0.70:
                    return "low", f"High camera smoothness score (avg={avg:.2f}) suggests low aggressiveness"
                elif avg >= 0.40:
                    return "medium", f"Moderate camera smoothness score (avg={avg:.2f})"
                else:
                    return "high", f"Low camera smoothness (avg={avg:.2f}) may benefit from higher aggressiveness"
        except Exception:
            pass

    # Derive from motion style
    if motion_style == "static_center":
        return "low", "Static center framing prefers low crop aggressiveness"
    if motion_style == "smooth_subject":
        return "low", "Smooth subject tracking works best with low aggressiveness"
    if motion_style == "dynamic_subject":
        return "medium", "Dynamic subject tracking uses medium crop aggressiveness"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Dimension inference — stability priority
# ---------------------------------------------------------------------------

def _infer_stability_priority(motion_style: str, quality, feedback):
    """Infer stability priority. Returns (value, signal_str)."""

    # Quality evaluation
    output_scores = quality.get("output_scores") or []
    if output_scores:
        try:
            cam_scores = [
                float(s.get("camera_smoothness") or 0.0)
                for s in output_scores if isinstance(s, dict)
            ]
            if cam_scores:
                avg = sum(cam_scores) / len(cam_scores)
                if avg >= 0.70:
                    return "high", f"Camera smoothness consistently high (avg={avg:.2f})"
                elif avg >= 0.45:
                    return "medium", f"Camera smoothness moderate (avg={avg:.2f})"
        except Exception:
            pass

    # Creator feedback pattern
    fb_patterns = feedback.get("learned_patterns") or {}
    total_exports = _safe_int(feedback.get("total_exports"))
    if total_exports >= 5:
        if motion_style in ("static_center", "smooth_subject"):
            return "high", "Creator export history aligns with high stability preference"

    if motion_style == "static_center":
        return "high", "Static center framing prioritizes stability"
    if motion_style == "smooth_subject":
        return "medium", "Smooth subject tracking uses medium stability priority"
    if motion_style == "dynamic_subject":
        return "low", "Dynamic subject tracking uses lower stability priority"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Dimension inference — deadzone
# ---------------------------------------------------------------------------

def _infer_deadzone_preference(motion_style: str, market):
    """Infer deadzone preference. Returns (value, signal_str)."""

    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower()

    if motion_style == "static_center":
        return "wide", "Static center framing uses wide deadzone to minimize drift"
    if motion_style == "smooth_subject":
        if "podcast" in target or "educational" in target:
            return "wide", f"{target} market prefers wide deadzone for stable framing"
        return "medium", "Smooth subject tracking uses medium deadzone"
    if motion_style == "dynamic_subject":
        return "narrow", "Dynamic subject tracking uses narrow deadzone for responsiveness"

    # Market fallback
    if "podcast" in target or "educational" in target:
        return "wide", f"{target} market uses wide deadzone for stability"
    if "tiktok" in target or "reels" in target:
        return "narrow", "Viral market uses narrower deadzone for energy"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Dimension inference — subject hold
# ---------------------------------------------------------------------------

def _infer_subject_hold(motion_style: str, market):
    """Infer subject hold duration. Returns (value, signal_str)."""

    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower()

    if motion_style == "static_center":
        return "long", "Static center framing holds subject for longer periods"
    if motion_style == "smooth_subject":
        return "long", "Smooth subject tracking maintains longer hold frames"
    if motion_style == "dynamic_subject":
        return "short", "Dynamic subject tracking uses shorter hold durations"

    if "podcast" in target or "educational" in target:
        return "long", f"{target} market uses long subject hold for continuity"
    if "tiktok" in target or "reels" in target:
        return "short", "Viral market uses shorter subject holds for energy"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Dimension inference — scene sensitivity
# ---------------------------------------------------------------------------

def _infer_scene_sensitivity(motion_style: str, market):
    """Infer scene sensitivity level. Returns (value, signal_str)."""

    mp = market.get("market_profile") or {}
    target = str(mp.get("target_market") or "").lower()

    if motion_style == "static_center":
        return "low", "Static center framing uses low scene cut sensitivity"
    if motion_style == "smooth_subject":
        return "medium", "Smooth subject tracking uses medium scene sensitivity"
    if motion_style == "dynamic_subject":
        return "high", "Dynamic subject tracking uses high scene sensitivity"

    if "podcast" in target or "educational" in target:
        return "low", f"{target} market uses lower scene sensitivity"
    if "tiktok" in target or "reels" in target:
        return "high", "Viral market uses higher scene sensitivity for cuts"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Dimension inference — center bias (derived)
# ---------------------------------------------------------------------------

def _infer_center_bias(motion_style: str) -> str:
    if motion_style == "static_center":
        return "high"
    if motion_style == "smooth_subject":
        return "medium"
    if motion_style == "dynamic_subject":
        return "low"
    return "unknown"


# ---------------------------------------------------------------------------
# Dimension inference — reframing risk tolerance
# ---------------------------------------------------------------------------

def _infer_risk_tolerance(motion_style: str, quality, feedback):
    """Infer reframing risk tolerance. Returns (value, signal_str)."""

    # Quality evaluation
    output_scores = quality.get("output_scores") or []
    if output_scores:
        try:
            cam_scores = [
                float(s.get("camera_smoothness") or 0.0)
                for s in output_scores if isinstance(s, dict)
            ]
            if cam_scores:
                avg = sum(cam_scores) / len(cam_scores)
                if avg >= 0.70:
                    return "low", f"High smoothness scores suggest low reframing risk tolerance"
        except Exception:
            pass

    # Creator feedback
    total_exports = _safe_int(feedback.get("total_exports"))
    if total_exports >= 5 and motion_style in ("static_center", "smooth_subject"):
        return "low", "Creator export history shows preference for stable reframing"

    if motion_style == "static_center":
        return "low", "Static center framing prefers low reframing risk"
    if motion_style == "smooth_subject":
        return "low", "Smooth subject tracking uses low reframing risk tolerance"
    if motion_style == "dynamic_subject":
        return "medium", "Dynamic subject tracking accepts medium reframing risk"

    return "unknown", ""


# ---------------------------------------------------------------------------
# Dimension inference — smoothness priority (derived)
# ---------------------------------------------------------------------------

def _infer_smoothness_priority(stability_priority: str, motion_style: str) -> str:
    if stability_priority == "high":
        return "high"
    if stability_priority == "medium":
        return "medium"
    if stability_priority == "low":
        return "low"
    # Fallback from motion style
    if motion_style in ("static_center", "smooth_subject"):
        return "high"
    if motion_style == "dynamic_subject":
        return "medium"
    return "unknown"


# ---------------------------------------------------------------------------
# Confidence computation
# ---------------------------------------------------------------------------

def _compute_confidence(active_domains: int, adaptive, feedback) -> float:
    """Compute inference confidence. Clamped to [0.0, 1.0]."""
    base = min(active_domains / _MAX_SIGNAL_DOMAINS, 1.0)

    # Amplify from adaptive profile camera confidence
    adaptive_influences = adaptive.get("adaptive_influences") or {}
    cam_weight = _safe_float(
        adaptive_influences.get("camera_enhancement_weight")
        or (adaptive.get("creator_profile") or {}).get("camera_confidence")
    )

    # Amplify from feedback history
    total_exports = _safe_int(feedback.get("total_exports"))

    amplifier = 0.0
    if cam_weight > 0.20:
        amplifier += cam_weight * 0.10
    if total_exports >= 3:
        amplifier += min(total_exports * 0.015, 0.08)

    raw = base + amplifier
    return round(max(0.0, min(1.0, raw)), 2)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dict(edit_plan: Any, attr: str) -> dict:
    try:
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_float(val) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(val) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0
