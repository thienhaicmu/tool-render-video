"""Motion-crop configuration dataclass + content-type tracking overrides.

Sprint 6.D-3.2 — extracted verbatim from motion_crop.py
(lines 212–313 of the pre-3.2 file). No logic changes; pure relocation.

Contents (preserved in original source order):
  - `_CONTENT_TYPE_TRACKING` dict — per-content-type multipliers for
    detect_interval, ema, and pan_speed. Keys: interview / commentary /
    vlog / tutorial / montage / podcast / education / reaction /
    storytelling / high-energy.
  - `_apply_content_type_to_cfg(cfg, content_type)` — returns a shallow
    dataclasses.replace() copy of cfg with the content-type multipliers
    applied to four tracking params (subject_detect_interval,
    ema_alpha_slow/normal/fast, max_pan_speed_ratio).
  - `MotionCropConfig` dataclass — ~30 tracking parameters: output dims,
    subject detection cadence, EMA smoothing, scene-cut awareness,
    Gaussian smoothing window, pan-speed caps, legacy-motion settings.

Public API: only `MotionCropConfig` is imported by external modules
(render_engine.py, render/legacy_renderer.py). The two private helpers
remain motion_crop-internal and are re-exported by motion_crop.py for
its own existing call sites.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Content-type-aware tracking parameter overrides
# ---------------------------------------------------------------------------

_CONTENT_TYPE_TRACKING: dict[str, dict] = {
    # interview/commentary/tutorial: speech-heavy, face is primary subject.
    # Detect MORE often (0.5×) so tracker loss over 8 frames max, not 32.
    # Slower pan + stronger EMA keep the camera stable between detections.
    "interview":    {"detect_interval_mul": 0.5, "ema_mul": 0.65, "pan_speed_mul": 0.70},
    "commentary":   {"detect_interval_mul": 0.5, "ema_mul": 0.80, "pan_speed_mul": 0.85},
    "vlog":         {"detect_interval_mul": 1.0, "ema_mul": 1.00, "pan_speed_mul": 1.00},
    "tutorial":     {"detect_interval_mul": 0.5, "ema_mul": 0.65, "pan_speed_mul": 0.70},
    # montage: subject moves fast — detect more often, pan faster, more reactive
    "montage":      {"detect_interval_mul": 0.5, "ema_mul": 1.30, "pan_speed_mul": 1.40},
    # S4.4 content types — mapped to nearest existing profile
    "podcast":      {"detect_interval_mul": 0.5, "ema_mul": 0.65, "pan_speed_mul": 0.70},
    "education":    {"detect_interval_mul": 0.5, "ema_mul": 0.65, "pan_speed_mul": 0.70},
    "reaction":     {"detect_interval_mul": 0.5, "ema_mul": 0.80, "pan_speed_mul": 0.85},
    "storytelling": {"detect_interval_mul": 1.0, "ema_mul": 0.90, "pan_speed_mul": 0.90},
    "high-energy":  {"detect_interval_mul": 0.5, "ema_mul": 1.30, "pan_speed_mul": 1.40},
}


def _apply_content_type_to_cfg(cfg: MotionCropConfig, content_type: str) -> MotionCropConfig:
    """Return a shallow copy of cfg with content-type-adjusted tracking parameters."""
    import dataclasses as _dc
    p = _CONTENT_TYPE_TRACKING.get(content_type) or _CONTENT_TYPE_TRACKING["vlog"]
    di_mul = p["detect_interval_mul"]
    ema_mul = p["ema_mul"]
    pan_mul = p["pan_speed_mul"]
    return _dc.replace(
        cfg,
        subject_detect_interval=max(1, int(round(cfg.subject_detect_interval * di_mul))),
        ema_alpha_slow=min(0.30, cfg.ema_alpha_slow * ema_mul),
        ema_alpha_normal=min(0.40, cfg.ema_alpha_normal * ema_mul),
        ema_alpha_fast=min(0.50, cfg.ema_alpha_fast * ema_mul),
        max_pan_speed_ratio=min(0.025, cfg.max_pan_speed_ratio * pan_mul),
    )

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class MotionCropConfig:
    # Output dimensions
    output_width: int = 1080
    output_height: int = 1440
    scale_x_percent: float = 100.0
    scale_y_percent: float = 106.0

    # --- Auto Reframe (CapCut-style) settings ---
    # "subject" = face/body tracking (default, like CapCut)
    # "motion"  = legacy pixel-diff motion tracking
    reframe_mode: str = "subject"

    # How many frames between full subject re-detections
    subject_detect_interval: int = 16

    # Padding factor around detected subject box (larger = more context shown)
    subject_padding: float = 0.55

    # Fall back to body detection when no face is found
    use_body_fallback: bool = True

    # Fall back to legacy motion mode when no subject found at all
    motion_fallback: bool = True

    # Reset subject tracking and smoothing across detected scene cuts
    scene_aware_tracking: bool = True
    scene_cut_threshold: float = 30.0
    subtitle_safe_bottom_ratio: float = 0.12
    subject_switch_margin: float = 1.25
    subject_switch_confirm_frames: int = 2
    ema_alpha_slow: float = 0.08
    ema_alpha_normal: float = 0.18
    ema_alpha_fast: float = 0.25
    lookahead_frames: int = 4
    lost_subject_hold_frames: int = 45

    # --- Smoothing ---
    # Gaussian window size for the crop path (larger = smoother, less reactive)
    temporal_smooth_window: int = 45

    # Max camera pan speed (fraction of frame width per frame)
    max_pan_speed_ratio: float = 0.010

    # Max camera pan acceleration per frame
    max_pan_accel_ratio: float = 0.0045

    # Dead zone – ignore subject shifts smaller than this fraction of crop size
    dead_zone_ratio: float = 0.06

    # --- Legacy motion-mode settings (used when reframe_mode="motion") ---
    sample_every_n_frames: int = 1
    smooth_alpha: float = 0.10
    motion_threshold: int = 18
    min_contour_area_ratio: float = 0.002
    prefer_center_bias: float = 0.15

    fps_fallback: float = 30.0
    max_tracking_seconds: float = 300.0

    # Sprint 1: RenderPlan.camera_strategy.tracker hint.
    # "" = auto (KCF→CSRT→MOSSE fallback chain, existing behaviour)
    # "trackerless" = force detection-only (no OpenCV tracker object)
    # "bytetrack" / "legacy" = reserved vocabulary, treated as auto for now
    tracker_hint: str = ""

