"""
camera_tuning_engine.py — Safe camera parameter tuning engine. Phase 50B.

Translates AICameraPreference into bounded MotionCropConfig parameter deltas.
All deltas are conservative additive offsets — absolute bounds are always enforced.

Public API:
    compute_camera_tuning(camera_preference) -> AICameraTuningPack
    build_tuned_crop_config(base_cfg, tuning_pack) -> MotionCropConfig

Safety contract:
    ❌ No motion_crop rewrite
    ❌ No tracking rewrite
    ❌ No new crop engine
    ❌ No FFmpeg mutation
    ❌ No executor override
    ❌ No autonomous execution
    ✅ All deltas clamped to absolute bounds
    ✅ Never raises
"""
from __future__ import annotations

import logging
from copy import copy
from typing import TYPE_CHECKING

from app.ai.creator_camera.camera_preference_schema import (
    AICameraPreference, AICameraTuningPack,
    DEADZONE_DELTA_MIN, DEADZONE_DELTA_MAX, DEADZONE_ABS_MIN, DEADZONE_ABS_MAX,
    EMA_DELTA_MIN, EMA_DELTA_MAX,
    EMA_SLOW_ABS_MIN, EMA_SLOW_ABS_MAX,
    EMA_NORMAL_ABS_MIN, EMA_NORMAL_ABS_MAX,
    EMA_FAST_ABS_MIN, EMA_FAST_ABS_MAX,
    HOLD_DELTA_MIN, HOLD_DELTA_MAX, HOLD_ABS_MIN, HOLD_ABS_MAX,
    SCENE_DELTA_MIN, SCENE_DELTA_MAX, SCENE_ABS_MIN, SCENE_ABS_MAX,
    SMOOTH_WINDOW_DELTA_MIN, SMOOTH_WINDOW_DELTA_MAX, SMOOTH_WINDOW_ABS_MIN, SMOOTH_WINDOW_ABS_MAX,
    SOFT_TIER_MULTIPLIER,
)

if TYPE_CHECKING:
    from app.services.motion_crop import MotionCropConfig

logger = logging.getLogger("app.ai.creator_camera.tuning")

# Confidence thresholds for tier gates
_CONFIDENCE_HIGH = 0.88
_CONFIDENCE_MEDIUM = 0.75


def compute_camera_tuning(camera_preference: AICameraPreference) -> AICameraTuningPack:
    """Compute bounded parameter deltas from camera preference. Never raises.

    Args:
        camera_preference: Inferred AICameraPreference (may have unknown fields).

    Returns:
        AICameraTuningPack with deltas and confidence tier.
    """
    try:
        return _compute_tuning(camera_preference)
    except Exception as exc:
        logger.debug("camera_tuning_compute_error: %s", exc)
        return AICameraTuningPack(
            applied=False,
            confidence_tier="low",
            warnings=[f"tuning_compute_error:{type(exc).__name__}"],
        )


def build_tuned_crop_config(base_cfg: "MotionCropConfig", tuning_pack: AICameraTuningPack) -> "MotionCropConfig":
    """Apply bounded deltas to base MotionCropConfig. Never raises.

    Creates a shallow copy with delta-adjusted parameters clamped to absolute bounds.
    If tuning_pack.applied is False, returns the base config unchanged.

    Args:
        base_cfg: Existing MotionCropConfig from render pipeline.
        tuning_pack: Deltas from compute_camera_tuning().

    Returns:
        MotionCropConfig with safely-applied parameter adjustments.
    """
    try:
        return _apply_tuning(base_cfg, tuning_pack)
    except Exception as exc:
        logger.debug("camera_tuning_apply_error: %s", exc)
        return base_cfg


# ---------------------------------------------------------------------------
# Tuning computation
# ---------------------------------------------------------------------------

def _compute_tuning(pref: AICameraPreference) -> AICameraTuningPack:
    conf = float(pref.confidence)
    motion_style = str(pref.motion_style)
    stability = str(pref.stability_priority)
    deadzone = str(pref.deadzone_preference)
    smoothness = str(pref.smoothness_priority)
    subject_hold = str(pref.subject_hold)
    scene_sensitivity = str(pref.scene_sensitivity)

    # Confidence gate
    if conf < _CONFIDENCE_MEDIUM:
        return AICameraTuningPack(
            applied=False,
            confidence_tier="low",
            reasoning=[f"Confidence {conf:.2f} below threshold {_CONFIDENCE_MEDIUM} — no tuning applied"],
        )

    tier = "high" if conf >= _CONFIDENCE_HIGH else "medium"
    multiplier = 1.0 if tier == "high" else SOFT_TIER_MULTIPLIER

    reasoning: list[str] = [f"Confidence tier={tier} (conf={conf:.2f})"]
    warnings: list[str] = []

    # ── Deadzone delta ────────────────────────────────────────────────────────
    deadzone_delta = _compute_deadzone_delta(motion_style, deadzone, stability)
    deadzone_delta = _clamp(deadzone_delta * multiplier, DEADZONE_DELTA_MIN, DEADZONE_DELTA_MAX)
    if deadzone_delta != 0.0:
        reasoning.append(f"deadzone_delta={deadzone_delta:+.4f} from {motion_style}/{deadzone}")

    # ── EMA alpha delta ───────────────────────────────────────────────────────
    ema_delta = _compute_ema_delta(motion_style, smoothness, stability)
    ema_delta = _clamp(ema_delta * multiplier, EMA_DELTA_MIN, EMA_DELTA_MAX)
    if ema_delta != 0.0:
        reasoning.append(f"ema_alpha_delta={ema_delta:+.4f} from {motion_style}/{smoothness}")

    # ── Hold frames delta ─────────────────────────────────────────────────────
    hold_delta = _compute_hold_delta(motion_style, subject_hold)
    hold_delta_scaled = int(round(hold_delta * multiplier))
    hold_delta_scaled = int(_clamp(hold_delta_scaled, HOLD_DELTA_MIN, HOLD_DELTA_MAX))
    if hold_delta_scaled != 0:
        reasoning.append(f"hold_frames_delta={hold_delta_scaled:+d} from {motion_style}/{subject_hold}")

    # ── Scene threshold delta ─────────────────────────────────────────────────
    scene_delta = _compute_scene_delta(motion_style, scene_sensitivity)
    scene_delta = _clamp(scene_delta * multiplier, SCENE_DELTA_MIN, SCENE_DELTA_MAX)
    if scene_delta != 0.0:
        reasoning.append(f"scene_threshold_delta={scene_delta:+.4f} from {motion_style}/{scene_sensitivity}")

    # ── Smooth window delta ───────────────────────────────────────────────────
    smooth_delta = _compute_smooth_window_delta(motion_style, smoothness)
    smooth_delta_scaled = int(round(smooth_delta * multiplier))
    smooth_delta_scaled = int(_clamp(smooth_delta_scaled, SMOOTH_WINDOW_DELTA_MIN, SMOOTH_WINDOW_DELTA_MAX))
    if smooth_delta_scaled != 0:
        reasoning.append(f"smooth_window_delta={smooth_delta_scaled:+d} from {motion_style}/{smoothness}")

    applied = any([
        deadzone_delta != 0.0,
        ema_delta != 0.0,
        hold_delta_scaled != 0,
        scene_delta != 0.0,
        smooth_delta_scaled != 0,
    ])

    return AICameraTuningPack(
        applied=applied,
        confidence_tier=tier,
        deadzone_delta=deadzone_delta,
        ema_alpha_delta=ema_delta,
        hold_frames_delta=hold_delta_scaled,
        scene_threshold_delta=scene_delta,
        smooth_window_delta=smooth_delta_scaled,
        reasoning=reasoning[:5],
        warnings=warnings[:5],
    )


# ---------------------------------------------------------------------------
# Delta computation helpers
# ---------------------------------------------------------------------------

def _compute_deadzone_delta(motion_style: str, deadzone: str, stability: str) -> float:
    """Wider deadzone for stable/static, narrower for dynamic."""
    if motion_style == "static_center" or deadzone == "wide":
        return DEADZONE_DELTA_MAX      # +0.04 — maximize stability
    if motion_style == "dynamic_subject" or deadzone == "narrow":
        return DEADZONE_DELTA_MIN      # -0.02 — more responsive
    if motion_style == "smooth_subject" or deadzone == "medium":
        if stability == "high":
            return DEADZONE_DELTA_MAX * 0.5   # +0.02
        return 0.0
    return 0.0


def _compute_ema_delta(motion_style: str, smoothness: str, stability: str) -> float:
    """Higher EMA for stable/smooth, lower for dynamic."""
    if motion_style == "static_center" or smoothness == "high" or stability == "high":
        return EMA_DELTA_MAX           # +0.04 — smoother tracking
    if motion_style == "dynamic_subject" or smoothness == "low":
        return EMA_DELTA_MIN           # -0.04 — faster tracking
    if motion_style == "smooth_subject" or smoothness == "medium":
        return EMA_DELTA_MAX * 0.5     # +0.02
    return 0.0


def _compute_hold_delta(motion_style: str, subject_hold: str) -> int:
    """Longer hold for stable/podcast, shorter for dynamic."""
    if motion_style == "static_center" or subject_hold == "long":
        return HOLD_DELTA_MAX          # +8
    if motion_style == "dynamic_subject" or subject_hold == "short":
        return HOLD_DELTA_MIN          # -5
    if motion_style == "smooth_subject":
        return HOLD_DELTA_MAX // 2     # +4
    return 0


def _compute_scene_delta(motion_style: str, scene_sensitivity: str) -> float:
    """Higher threshold for static (fewer resets), lower for dynamic (more resets)."""
    if motion_style == "static_center" or scene_sensitivity == "low":
        return SCENE_DELTA_MAX         # +3.0 — fewer scene resets
    if motion_style == "dynamic_subject" or scene_sensitivity == "high":
        return SCENE_DELTA_MIN         # -2.0 — more responsive to cuts
    if motion_style == "smooth_subject" or scene_sensitivity == "medium":
        return 0.0
    return 0.0


def _compute_smooth_window_delta(motion_style: str, smoothness: str) -> int:
    """Larger smooth window for stable, smaller for dynamic."""
    if motion_style == "static_center" or smoothness == "high":
        return SMOOTH_WINDOW_DELTA_MAX  # +6
    if motion_style == "dynamic_subject" or smoothness == "low":
        return SMOOTH_WINDOW_DELTA_MIN  # -4
    if motion_style == "smooth_subject" or smoothness == "medium":
        return SMOOTH_WINDOW_DELTA_MAX // 2  # +3
    return 0


# ---------------------------------------------------------------------------
# Config application
# ---------------------------------------------------------------------------

def _apply_tuning(base_cfg: "MotionCropConfig", tuning_pack: AICameraTuningPack) -> "MotionCropConfig":
    if not tuning_pack.applied:
        return base_cfg

    cfg = copy(base_cfg)

    # dead_zone_ratio
    new_dz = float(base_cfg.dead_zone_ratio) + tuning_pack.deadzone_delta
    cfg.dead_zone_ratio = _clamp(new_dz, DEADZONE_ABS_MIN, DEADZONE_ABS_MAX)

    # ema_alpha (apply same delta to all three tiers)
    new_slow = float(base_cfg.ema_alpha_slow) + tuning_pack.ema_alpha_delta
    new_normal = float(base_cfg.ema_alpha_normal) + tuning_pack.ema_alpha_delta
    new_fast = float(base_cfg.ema_alpha_fast) + tuning_pack.ema_alpha_delta
    cfg.ema_alpha_slow   = _clamp(new_slow,   EMA_SLOW_ABS_MIN,   EMA_SLOW_ABS_MAX)
    cfg.ema_alpha_normal = _clamp(new_normal, EMA_NORMAL_ABS_MIN, EMA_NORMAL_ABS_MAX)
    cfg.ema_alpha_fast   = _clamp(new_fast,   EMA_FAST_ABS_MIN,   EMA_FAST_ABS_MAX)

    # lost_subject_hold_frames
    new_hold = int(base_cfg.lost_subject_hold_frames) + tuning_pack.hold_frames_delta
    cfg.lost_subject_hold_frames = int(_clamp(new_hold, HOLD_ABS_MIN, HOLD_ABS_MAX))

    # scene_cut_threshold
    new_scene = float(base_cfg.scene_cut_threshold) + tuning_pack.scene_threshold_delta
    cfg.scene_cut_threshold = _clamp(new_scene, SCENE_ABS_MIN, SCENE_ABS_MAX)

    # temporal_smooth_window (force odd to satisfy Gaussian requirement)
    new_window = int(base_cfg.temporal_smooth_window) + tuning_pack.smooth_window_delta
    new_window = int(_clamp(new_window, SMOOTH_WINDOW_ABS_MIN, SMOOTH_WINDOW_ABS_MAX))
    cfg.temporal_smooth_window = new_window if new_window % 2 == 1 else new_window + 1

    logger.debug(
        "camera_tuning_applied tier=%s dz=%.4f ema=%.4f hold=%d scene=%.2f smooth=%d",
        tuning_pack.confidence_tier,
        cfg.dead_zone_ratio,
        cfg.ema_alpha_normal,
        cfg.lost_subject_hold_frames,
        cfg.scene_cut_threshold,
        cfg.temporal_smooth_window,
    )
    return cfg


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
