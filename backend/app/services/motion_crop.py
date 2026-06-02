from __future__ import annotations

import math
import os
import subprocess
import time
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# Sprint 6.D-3.1: motion-path cache helpers extracted to a dedicated module.
# `_MOTION_CACHE_TTL_SEC` and the three functions below are unchanged from
# their original definitions; this is a pure mechanical relocation.
from app.services.motion_crop_cache import (
    _MOTION_CACHE_TTL_SEC,
    _motion_cache_key,
    _motion_path_cache_get,
    _motion_path_cache_put,
)

import cv2
import numpy as np

from app.services.bin_paths import get_ffmpeg_bin, _summarize_ffmpeg_stderr
from app.services.text_overlay import append_text_layer_filters
from app.services.encoder_helpers import (
    ffmpeg_encoders_text as _ffmpeg_encoders_text,
    has_encoder as _has_encoder,
    nvenc_runtime_ready as _nvenc_runtime_ready,
    resolve_encoder as _resolve_encoder,
    map_preset_for_encoder as _map_preset_for_encoder,
    codec_extra_flags as _codec_extra_flags_shared,
    reup_video_filters as _reup_video_filters,
    reup_audio_filter as _reup_audio_filter,
    safe_filter_path as _safe_filter_path,
    detect_windows_fontfile as _detect_windows_fontfile,
    detect_windows_fonts_dir as _detect_windows_fonts_dir,
    get_custom_fonts_dir as _get_custom_fonts_dir,
)

logger = logging.getLogger(__name__)
_TRACKER_CAPABILITY_LOGGED = False

# ---------------------------------------------------------------------------
# MediaPipe face detection — optional, CPU-safe, replaces Haar cascade
# ---------------------------------------------------------------------------

_mp_face_detector = None
_mp_face_detector_initialized = False


def _get_mp_detector():
    """Lazy-load MediaPipe FaceDetection. Returns None if unavailable (graceful fallback)."""
    global _mp_face_detector, _mp_face_detector_initialized
    if _mp_face_detector_initialized:
        return _mp_face_detector
    _mp_face_detector_initialized = True
    try:
        import mediapipe as mp  # noqa: PLC0415
        _mp_face_detector = mp.solutions.face_detection.FaceDetection(
            model_selection=1,           # full-range model (≤5m) — detects wide shots and small faces
            min_detection_confidence=0.5,
        )
        logger.info("mediapipe_face_detection_loaded model=full_range confidence_threshold=0.5")
    except Exception as exc:
        logger.info("mediapipe_unavailable fallback=haar reason=%s", exc)
        _mp_face_detector = None
    return _mp_face_detector


def _detect_mediapipe_faces(
    frame_bgr_small: np.ndarray,
    scale: float,
) -> List[Tuple[int, int, int, int]]:
    """
    Run MediaPipe Face Detection on a downscaled BGR frame.
    Returns (x, y, w, h) boxes in _det_frame coordinates (divided by scale).
    Returns [] if MediaPipe is unavailable or detects nothing.
    """
    detector = _get_mp_detector()
    if detector is None:
        return []
    try:
        h_s, w_s = frame_bgr_small.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr_small, cv2.COLOR_BGR2RGB)
        results = detector.process(frame_rgb)
        if not results.detections:
            return []
        boxes = []
        for det in results.detections:
            rb = det.location_data.relative_bounding_box
            # Convert relative → absolute in small-frame space, then → _det_frame space
            x = int((rb.xmin * w_s) / scale)
            y = int((rb.ymin * h_s) / scale)
            w = int((rb.width * w_s) / scale)
            h = int((rb.height * h_s) / scale)
            if w > 4 and h > 4:
                boxes.append((x, y, w, h))
        return boxes
    except Exception as exc:
        logger.debug("mediapipe_detection_error: %s", exc)
        return []


def _has_subject_in_sample(video_path: str, sample_count: int = 24) -> bool:
    """Sample sparse frames; return True if any face is detected.

    Used as an early-exit gate before the expensive full per-frame MediaPipe
    scan. Conservative: returns True (assume subject present) on any error or
    when MediaPipe is unavailable, so the full path is always the safe fallback.
    """
    if _get_mp_detector() is None:
        return True  # MediaPipe not available → assume subject present
    try:
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total < 1:
            cap.release()
            return True
        step = max(1, total // max(1, sample_count))
        found = False
        for i in range(0, total, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(i))
            ret, frame = cap.read()
            if not ret:
                continue
            h_f, w_f = frame.shape[:2]
            det_scale = 320.0 / max(w_f, 1)
            small = cv2.resize(frame, (int(w_f * det_scale), int(h_f * det_scale)))
            if _detect_mediapipe_faces(small, det_scale):
                found = True
                break
        cap.release()
        return found
    except Exception:
        return True  # conservative


# ---------------------------------------------------------------------------
# MediaPipe Pose — eye-level anchor for premium framing composition (OQ-3.3)
# ---------------------------------------------------------------------------

_mp_pose_detector = None
_mp_pose_initialized = False
_POSE_LEFT_EYE = 2    # mp.solutions.pose.PoseLandmark.LEFT_EYE
_POSE_RIGHT_EYE = 5   # mp.solutions.pose.PoseLandmark.RIGHT_EYE
_EYE_CROP_THIRDS = 0.33  # eyes at rule-of-thirds from top of crop window


def _get_mp_pose():
    """Lazy-load MediaPipe Pose (BlazePose Lite). Returns None if unavailable."""
    global _mp_pose_detector, _mp_pose_initialized
    if _mp_pose_initialized:
        return _mp_pose_detector
    _mp_pose_initialized = True
    if os.environ.get("POSE_EYE_ANCHOR_ENABLED", "1") != "1":
        return None
    try:
        import mediapipe as mp  # noqa: PLC0415
        _mp_pose_detector = mp.solutions.pose.Pose(
            static_image_mode=True,
            model_complexity=0,
            min_detection_confidence=0.4,
        )
        logger.info("mediapipe_pose_loaded model_complexity=0 eye_anchor=enabled")
    except Exception as exc:
        logger.info("mediapipe_pose_unavailable reason=%s", exc)
        _mp_pose_detector = None
    return _mp_pose_detector


def _get_eye_anchor_rel(
    frame_bgr_small: np.ndarray,
    face_box_src: Tuple[int, int, int, int],
    detect_scale: float,
    det_sy: float = 1.0,
) -> Optional[float]:
    """Return eye midpoint y as a fraction of face-box height from its top.

    Runs MediaPipe Pose on the detect-scale frame. Validates the detected nose
    falls within the selected face box to reject background subjects.
    Returns None on any failure — caller falls back to y + h * 0.34.
    """
    pose = _get_mp_pose()
    if pose is None:
        return None
    try:
        h_s, w_s = frame_bgr_small.shape[:2]
        frame_rgb = cv2.cvtColor(frame_bgr_small, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)
        if not results.pose_landmarks:
            return None
        lm = results.pose_landmarks.landmark
        # Convert relative-small coords → src-frame y coords
        l_eye_y = (lm[_POSE_LEFT_EYE].y * h_s / detect_scale) / det_sy
        r_eye_y = (lm[_POSE_RIGHT_EYE].y * h_s / detect_scale) / det_sy
        nose_y  = (lm[0].y * h_s / detect_scale) / det_sy
        # Validate: nose must be within the selected face box (±20% margin)
        fx, fy, fw, fh = face_box_src
        if not (fy - fh * 0.2 <= nose_y <= fy + fh * 1.2):
            return None
        eye_mid_y = (l_eye_y + r_eye_y) / 2.0
        eye_rel = (eye_mid_y - fy) / max(1.0, float(fh))
        if not (0.0 <= eye_rel <= 0.65):
            return None
        return eye_rel
    except Exception:
        return None


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


def _codec_flags(resolved_codec: str, video_crf: int, video_preset: str = "slow") -> list[str]:
    """Return encoder flags for the motion-crop FFmpeg command.

    NVENC path uses unconstrained VBR (no -maxrate cap) since motion-crop
    pipes raw frames and operates under tighter latency constraints.
    CPU paths delegate to encoder_helpers.codec_extra_flags for a single
    source of truth on libx264/libx265 tuning parameters.
    """
    if resolved_codec in ("h264_nvenc", "hevc_nvenc"):
        return [
            "-rc", "vbr_hq", "-cq", str(video_crf), "-b:v", "0",
            "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
            "-rc-lookahead", "32", "-bf", "3",
        ]
    return _codec_extra_flags_shared(resolved_codec, video_crf, video_preset)


def _safe_filter_path(path: str) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _detect_windows_fontfile() -> str | None:
    windir = os.environ.get("WINDIR")
    if not windir:
        return None
    fonts_dir = Path(windir) / "Fonts"
    for name in ("arial.ttf", "segoeui.ttf", "tahoma.ttf"):
        p = fonts_dir / name
        if p.exists():
            return str(p)
    return None


def _detect_windows_fonts_dir() -> str | None:
    windir = os.environ.get("WINDIR")
    if not windir:
        return None
    p = Path(windir) / "Fonts"
    return str(p) if p.exists() else None


def _get_custom_fonts_dir() -> str | None:
    """Return path to bundled fonts directory."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "fonts",  # backend/fonts (current project layout)
        here.parents[3] / "fonts",  # legacy: repo/fonts
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


# ---------------------------------------------------------------------------
# Video probe helpers
# ---------------------------------------------------------------------------

def ffprobe_video_info(video_path: str) -> Tuple[int, int, float]:
    """Return (width, height, fps) via the shared cached probe service.

    Delegates to render_engine.probe_video_metadata() which caches results by
    (abspath, mtime_ns, size_bytes) — zero subprocess cost on repeat calls to the
    same unmodified file.  Falls back to fps=30.0 when the probe cannot determine
    a valid frame rate.

    Deferred import used to break the render_engine ↔ motion_crop module-level
    circular dependency (render_engine imports motion_crop at its own module level).
    """
    from app.services.render_engine import probe_video_metadata
    meta = probe_video_metadata(video_path)
    fps = meta["fps"] if meta["fps"] > 0 else 30.0
    return meta["width"], meta["height"], fps


def has_audio_stream(video_path: str) -> bool:
    """Return True when the file has at least one audio stream (uses cached probe)."""
    from app.services.render_engine import _has_audio_stream
    return _has_audio_stream(video_path)


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def ema(prev: float, new: float, alpha: float) -> float:
    return prev * (1.0 - alpha) + new * alpha


def _smoothstep(t: float) -> float:
    """Classic cubic smoothstep: slow-in → fast-mid → slow-out, result in [0, 1].

    t is clamped to [0, 1] before evaluation so callers don't need to pre-clamp.
    Used for cinematic camera easing — no overshoot, C1-continuous at both ends.
    """
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _gaussian_smooth_1d(arr: np.ndarray, window: int) -> np.ndarray:
    """Apply Gaussian smoothing to a 1D array using convolution."""
    if window < 3 or len(arr) < 3:
        return arr.copy()
    half = window // 2
    sigma = window / 6.0
    k = np.arange(-half, half + 1, dtype=float)
    kernel = np.exp(-(k ** 2) / (2 * sigma ** 2))
    kernel /= kernel.sum()
    # Reflect-pad to avoid border shrinkage
    padded = np.pad(arr, half, mode="reflect")
    smoothed = np.convolve(padded, kernel, mode="valid")
    return smoothed[: len(arr)]


# ---------------------------------------------------------------------------
# CapCut-style Auto Reframe: Subject detection & tracking
# ---------------------------------------------------------------------------

def _load_cascade(filename: str) -> Optional[cv2.CascadeClassifier]:
    """Load an OpenCV Haar cascade, return None if unavailable."""
    try:
        path = cv2.data.haarcascades + filename
        cascade = cv2.CascadeClassifier(path)
        return cascade if not cascade.empty() else None
    except Exception:
        return None


def _iou_xywh(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
    """Intersection-over-Union for two (x, y, w, h) boxes. Returns [0, 1]."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(ax, bx)
    iy = max(ay, by)
    iw = max(0, min(ax + aw, bx + bw) - ix)
    ih = max(0, min(ay + ah, by + bh) - iy)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    return float(inter) / max(float(union), 1.0)


class _ByteTrackSubject:
    """Kalman-inspired single-subject tracker for reframe stability.

    Maintains (cx, cy, w, h, vx, vy) state between detections.
    predict() advances position by velocity (with gentle damping).
    update() lerps toward measurement and computes new velocity.
    Rejects measurements with IoU < 0.10 after ≥3 coast frames.

    Eliminates two problems from the OpenCV-tracker-only approach:
      1. Static last_subject hold → replaced by velocity-predicted position.
      2. Unchecked tracker drift accepted → IoU gate rejects bad tracker output.

    Uses existing cfg.lost_subject_hold_frames to bound coast lifetime.
    """

    _MIN_VALIDATE_COAST = 3   # frames coasted before IoU rejection kicks in
    _MIN_IOU = 0.10           # IoU below this after coast → reject update

    def __init__(self, box: Tuple[int, int, int, int]) -> None:
        x, y, w, h = box
        self.cx = float(x + w / 2)
        self.cy = float(y + h / 2)
        self.w = max(1.0, float(w))
        self.h = max(1.0, float(h))
        self.vx = 0.0
        self.vy = 0.0
        self.coast = 0

    def predict(self) -> None:
        """Advance state one frame using current velocity (no measurement)."""
        self.cx += self.vx
        self.cy += self.vy
        self.vx *= 0.90   # gentle damping — prevents runaway drift
        self.vy *= 0.90
        self.coast += 1

    def update(self, box: Tuple[int, int, int, int], gain: float = 0.5) -> bool:
        """Update from a detection or tracker measurement.

        Returns False if the measurement is rejected (coasted + IoU too low).
        Caller should create a new _ByteTrackSubject when rejected after long coast.
        """
        x, y, w, h = box
        det_cx = float(x + w / 2)
        det_cy = float(y + h / 2)

        if self.coast >= self._MIN_VALIDATE_COAST:
            if _iou_xywh(self._to_box(), box) < self._MIN_IOU:
                return False

        # Update velocity from observed displacement, then lerp position.
        self.vx = (det_cx - self.cx) * gain
        self.vy = (det_cy - self.cy) * gain
        self.cx = self.cx * (1.0 - gain) + det_cx * gain
        self.cy = self.cy * (1.0 - gain) + det_cy * gain
        self.w = self.w * 0.90 + max(1.0, float(w)) * 0.10
        self.h = self.h * 0.90 + max(1.0, float(h)) * 0.10
        self.coast = 0
        return True

    def is_alive(self, max_coast: int) -> bool:
        return self.coast <= max_coast

    def get_subject(self) -> Tuple[int, int, int, int]:
        return self._to_box()

    def _to_box(self) -> Tuple[int, int, int, int]:
        x = int(self.cx - self.w / 2)
        y = int(self.cy - self.h / 2)
        return (max(0, x), max(0, y), max(1, int(self.w)), max(1, int(self.h)))


def _create_tracker():
    """Create fast available OpenCV tracker (KCF > CSRT > MOSSE)."""
    global _TRACKER_CAPABILITY_LOGGED
    for tracker_name, factory in (
        ("KCF", lambda: cv2.TrackerKCF_create()),
        ("CSRT", lambda: cv2.TrackerCSRT_create()),
        ("MOSSE", lambda: cv2.TrackerMOSSE_create()),
    ):
        try:
            tracker = factory()
            if not _TRACKER_CAPABILITY_LOGGED:
                logger.info("motion_crop tracker_available=%s tracker=%s", True, tracker_name)
                _TRACKER_CAPABILITY_LOGGED = True
            return tracker
        except AttributeError:
            continue
    if not _TRACKER_CAPABILITY_LOGGED:
        logger.warning("motion_crop tracker_available=%s tracker=none subject_mode=detection_only", False)
        _TRACKER_CAPABILITY_LOGGED = True
    return None


def _sanitize_speed(playback_speed: float | int | None) -> float:
    try:
        v = float(playback_speed or 1.0)
    except Exception:
        v = 1.0
    return max(0.5, min(1.5, v))


def _subject_area_ratio(subject: Tuple[int, int, int, int], frame_w: int, frame_h: int) -> float:
    _, _, w, h = subject
    return (w * h) / max(1.0, float(frame_w * frame_h))


def _subject_edge_overlap_ratio(
    subject: Tuple[int, int, int, int],
    frame_w: int,
    edge_ratio: float = 0.10,
) -> float:
    x, _, w, _ = subject
    if w <= 0:
        return 1.0
    left_band = frame_w * edge_ratio
    right_band = frame_w * (1.0 - edge_ratio)
    left_overlap = max(0.0, min(x + w, left_band) - max(0.0, x))
    right_overlap = max(0.0, min(x + w, frame_w) - max(right_band, x))
    return (left_overlap + right_overlap) / max(1.0, float(w))


def _required_lock_confirm_frames(
    cfg: MotionCropConfig,
    tracker_available: bool,
    confidence_score: float | None = None,
    offcenter_ratio: float = 0.0,
) -> int:
    if tracker_available:
        return 1
    base = max(2, int(cfg.subject_switch_confirm_frames or 0))
    if confidence_score is None:
        return base
    if confidence_score < 0.55 or offcenter_ratio > 0.35:
        return max(3, base + 1)
    if confidence_score < 0.72:
        return max(2, base)
    return base


def _untracked_hold_frames(cfg: MotionCropConfig, detect_interval: int) -> int:
    return max(4, min(cfg.lost_subject_hold_frames, max(6, detect_interval // 2)))


def _trackerless_offcenter_ratio(
    subject: Tuple[int, int, int, int],
    frame_w: int,
    crop_w: int,
) -> float:
    cx, _ = _subject_center(subject)
    pan_half_range = max(1.0, float(frame_w - crop_w) / 2.0)
    return abs(cx - frame_w / 2.0) / pan_half_range


def _trackerless_detection_confidence(
    subject: Tuple[int, int, int, int],
    frame_w: int,
    frame_h: int,
    crop_w: int,
    subject_kind: str = "face",
    previous_subject: Optional[Tuple[int, int, int, int]] = None,
    confirm_count: int = 1,
) -> float:
    area_ratio = _subject_area_ratio(subject, frame_w, frame_h)
    edge_overlap = _subject_edge_overlap_ratio(subject, frame_w)
    offcenter_ratio = _trackerless_offcenter_ratio(subject, frame_w, crop_w)

    if subject_kind == "face":
        score = 0.25
    elif subject_kind == "body":
        score = 0.18
    else:
        score = 0.15

    score += 0.25 * clamp(confirm_count / 3.0, 0.0, 1.0)

    if 0.02 <= area_ratio <= 0.12:
        score += 0.18
    elif 0.010 <= area_ratio < 0.02 or 0.12 < area_ratio <= 0.18:
        score += 0.10
    else:
        score += 0.04

    score += 0.15 * clamp(1.0 - offcenter_ratio, 0.0, 1.0)
    score += 0.10 * clamp(1.0 - edge_overlap, 0.0, 1.0)

    if previous_subject is not None and _same_subject(previous_subject, subject):
        score += 0.07

    if offcenter_ratio > 0.35:
        score -= 0.12
    if edge_overlap > 0.30:
        score -= 0.08

    return clamp(score, 0.0, 1.0)


def _trackerless_hold_frames_for_confidence(base_hold_frames: int, confidence_score: float) -> int:
    if confidence_score < 0.55:
        return max(3, base_hold_frames - 4)
    if confidence_score < 0.78:
        return max(4, base_hold_frames - 2)
    return base_hold_frames


def _trackerless_crop_side_fill_ratio(
    target_cx: float,
    frame_w: int,
    crop_w: int,
    band_ratio: float = 0.28,
) -> float:
    crop_left = clamp(target_cx - crop_w / 2.0, 0.0, frame_w - crop_w)
    crop_right = crop_left + crop_w
    left_band = frame_w * band_ratio
    right_band = frame_w * (1.0 - band_ratio)
    left_overlap = max(0.0, min(crop_right, left_band) - crop_left)
    right_overlap = max(0.0, crop_right - max(crop_left, right_band))
    return max(left_overlap, right_overlap) / max(1.0, float(crop_w))


def _apply_trackerless_center_guard(
    target_cx: float,
    default_cx: float,
    frame_w: int,
    crop_w: int,
    confidence_score: float,
    stable_count: int,
) -> Tuple[float, bool, str]:
    if confidence_score >= 0.82 and stable_count >= 3:
        return target_cx, False, "none"

    side_fill_ratio = _trackerless_crop_side_fill_ratio(target_cx, frame_w, crop_w)
    if confidence_score < 0.55:
        max_offset = crop_w * 0.18
        if side_fill_ratio > 0.18:
            max_offset = min(max_offset, crop_w * 0.14)
        reason = "weak_trackerless_guard"
    elif confidence_score < 0.78:
        max_offset = crop_w * 0.28
        if side_fill_ratio > 0.22:
            max_offset = min(max_offset, crop_w * 0.22)
            reason = "edge_fill_guard"
        else:
            reason = "medium_trackerless_guard"
    else:
        max_offset = crop_w * (0.32 + min(0.10, stable_count * 0.02))
        if side_fill_ratio > 0.24:
            max_offset = min(max_offset, crop_w * 0.26)
            reason = "edge_fill_guard"
        else:
            reason = "none"

    dx = target_cx - default_cx
    if abs(dx) <= max_offset:
        return target_cx, False, "none" if side_fill_ratio <= 0.22 else reason

    guarded_cx = default_cx + math.copysign(max_offset, dx)
    return guarded_cx, True, reason


def _is_plausible_subject(
    subject: Tuple[int, int, int, int],
    frame_w: int,
    frame_h: int,
    subject_kind: str = "face",
    previous_subject: Optional[Tuple[int, int, int, int]] = None,
) -> bool:
    x, y, w, h = subject
    if w <= 0 or h <= 0:
        return False

    cx, cy = _subject_center(subject)
    area_ratio = _subject_area_ratio(subject, frame_w, frame_h)
    aspect = w / max(1.0, float(h))
    center_y_ratio = cy / max(1.0, float(frame_h))
    center_offset_ratio = abs(cx - frame_w / 2.0) / max(1.0, float(frame_w))
    edge_overlap = _subject_edge_overlap_ratio(subject, frame_w)
    same_as_previous = previous_subject is not None and _same_subject(previous_subject, subject)

    if subject_kind == "face":
        if area_ratio < 0.0012:
            return False
        if aspect < 0.55 or aspect > 1.65:
            return False
        if center_y_ratio > 0.82:
            return False
        if same_as_previous:
            return True
        if edge_overlap > 0.45 and area_ratio < 0.040:
            return False
        if center_y_ratio > 0.72 and area_ratio > 0.030 and center_offset_ratio > 0.10:
            return False
        if center_y_ratio > 0.67 and area_ratio > 0.025 and (
            x < frame_w * 0.30 or (x + w) > frame_w * 0.70
        ):
            return False
        return True

    if subject_kind == "body":
        if area_ratio < 0.015:
            return False
        if aspect < 0.24 or aspect > 1.05:
            return False
        if same_as_previous:
            return True
        if w < frame_w * 0.09 and area_ratio < 0.030:
            return False
        if edge_overlap > 0.40 and area_ratio < 0.050:
            return False
        return True

    return True


def _filter_subject_candidates(
    subjects: List[Tuple[int, int, int, int]],
    frame_w: int,
    frame_h: int,
    subject_kind: str = "face",
    previous_subject: Optional[Tuple[int, int, int, int]] = None,
) -> Tuple[List[Tuple[int, int, int, int]], int]:
    filtered: List[Tuple[int, int, int, int]] = []
    rejected = 0
    for subject in subjects:
        if _is_plausible_subject(subject, frame_w, frame_h, subject_kind, previous_subject):
            filtered.append(subject)
        else:
            rejected += 1
    return filtered, rejected


def prepare_detection_frame(
    frame: np.ndarray,
    max_height: int = 720,
) -> Tuple[np.ndarray, float, float, Tuple[int, int], Tuple[int, int]]:
    """
    Cap frame height to max_height before Haar cascade detection.
    Returns (detect_frame, scale_x, scale_y, original_wh, scaled_wh).
    Divide detected bbox coords by scale_x/scale_y to recover original-frame coords.
    If source height <= max_height, returns frame unchanged with scale 1.0.
    """
    h, w = frame.shape[:2]
    if h <= max_height:
        return frame, 1.0, 1.0, (w, h), (w, h)
    scale = max_height / h
    new_w = max(1, int(round(w * scale)))
    resized = cv2.resize(frame, (new_w, max_height), interpolation=cv2.INTER_LINEAR)
    return resized, scale, scale, (w, h), (new_w, max_height)


def _detect_subjects_in_frame(
    gray_small: np.ndarray,
    face_cascade: Optional[cv2.CascadeClassifier],
    body_cascade: Optional[cv2.CascadeClassifier],
    scale: float,
    frame_bgr_small: Optional[np.ndarray] = None,
) -> Tuple[List[Tuple[int, int, int, int]], str]:
    """
    Detect faces (MediaPipe primary → Haar cascade fallback) then bodies as fallback.
    Returns (list of (x,y,w,h) in _det_frame coords, kind).
    """
    # MediaPipe primary path — neural, confidence-based, angle/lighting tolerant
    if frame_bgr_small is not None:
        mp_boxes = _detect_mediapipe_faces(frame_bgr_small, scale)
        if mp_boxes:
            return mp_boxes, "face"

    # Haar cascade fallback (used when MediaPipe unavailable or returns nothing)
    if face_cascade is not None:
        min_dim = max(20, int(gray_small.shape[1] * 0.05))
        faces = face_cascade.detectMultiScale(
            gray_small, scaleFactor=1.1, minNeighbors=4,
            minSize=(min_dim, min_dim),
        )
        if len(faces) > 0:
            scaled = [(int(x / scale), int(y / scale), int(w / scale), int(h / scale))
                      for (x, y, w, h) in faces]
            return scaled, "face"

    if body_cascade is not None:
        min_w = max(30, int(gray_small.shape[1] * 0.06))
        min_h = max(60, int(gray_small.shape[0] * 0.08))
        bodies = body_cascade.detectMultiScale(
            gray_small, scaleFactor=1.05, minNeighbors=2,
            minSize=(min_w, min_h),
        )
        if len(bodies) > 0:
            scaled = [(int(x / scale), int(y / scale), int(w / scale), int(h / scale))
                      for (x, y, w, h) in bodies]
            return scaled, "body"

    return [], "none"


def _pick_best_subject(
    subjects: List[Tuple[int, int, int, int]],
    frame_w: int,
    frame_h: int,
    previous_subject: Optional[Tuple[int, int, int, int]] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Choose the most prominent subject: largest area with slight
    preference for subjects closer to frame center.
    """
    if not subjects:
        return None
    best, best_score = None, -1.0
    for subject in subjects:
        score = _score_subject_candidate(subject, frame_w, frame_h, previous_subject)
        if score > best_score:
            best_score = score
            best = subject
    return best


def _subject_center(subject: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x, y, w, h = subject
    return x + w / 2.0, y + h / 2.0


def _score_subject_candidate(
    subject: Tuple[int, int, int, int],
    frame_w: int,
    frame_h: int,
    previous_subject: Optional[Tuple[int, int, int, int]] = None,
) -> float:
    x, y, w, h = subject
    frame_area = max(1.0, float(frame_w * frame_h))
    area_score = min(1.0, (w * h) / frame_area * 10.0)

    cx, cy = _subject_center(subject)
    center_x, center_y = frame_w / 2.0, frame_h / 2.0
    max_dist = max(1.0, math.hypot(center_x, center_y))
    center_score = 1.0 - min(1.0, math.hypot(cx - center_x, cy - center_y) / max_dist)

    edge_margin = frame_w * 0.12
    edge_score = 1.0
    if cx < edge_margin:
        edge_score = max(0.0, cx / max(1.0, edge_margin))
    elif cx > frame_w - edge_margin:
        edge_score = max(0.0, (frame_w - cx) / max(1.0, edge_margin))

    stability_score = 0.5
    if previous_subject is not None:
        pcx, pcy = _subject_center(previous_subject)
        stability_score = 1.0 - min(1.0, math.hypot(cx - pcx, cy - pcy) / max_dist)

    return area_score * 1.2 + center_score * 0.9 + edge_score * 0.6 + stability_score * 1.0


def _same_subject(
    a: Optional[Tuple[int, int, int, int]],
    b: Optional[Tuple[int, int, int, int]],
) -> bool:
    if a is None or b is None:
        return False
    acx, acy = _subject_center(a)
    bcx, bcy = _subject_center(b)
    _, _, aw, ah = a
    _, _, bw, bh = b
    threshold = max(24.0, max(aw, ah, bw, bh) * 0.75)
    return math.hypot(acx - bcx, acy - bcy) <= threshold


def _subject_to_crop_center(
    subject: Tuple[int, int, int, int],
    crop_w: int,
    crop_h: int,
    frame_w: int,
    frame_h: int,
    padding: float,
    subtitle_safe_ratio: float = 0.0,
    subject_kind: str = "face",
    eye_anchor_rel: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Convert a subject bounding box to the desired crop-window center.
    When eye_anchor_rel is provided (from MediaPipe Pose), places the eye
    midpoint at rule-of-thirds (1/3 from top of crop) for premium framing.
    Falls back to a slight upward bias (y + h * 0.34) when unavailable.
    """
    x, y, w, h = subject
    cx = x + w / 2.0
    if eye_anchor_rel is not None and subject_kind != "body":
        # Premium framing: eyes at rule-of-thirds (1/3 from crop top)
        eye_y = y + h * eye_anchor_rel
        cy = eye_y + crop_h * (0.5 - _EYE_CROP_THIRDS)
    elif subject_kind == "body":
        cy = y + h * 0.50
    else:
        cy = y + h * 0.34

    subject_ratio = (w * h) / max(1.0, float(frame_w * frame_h))
    if subject_ratio > 0.18:
        cx = cx * 0.55 + (frame_w / 2.0) * 0.45
        if eye_anchor_rel is None:
            cy = cy * 0.70 + (frame_h * 0.42) * 0.30
    elif subject_ratio < 0.035:
        if eye_anchor_rel is None:
            cy = min(cy, y + h * 0.42)

    # Apply padding: zoom the crop window out around the subject
    # (padding > 0 means we follow a larger region, feels less claustrophobic)
    # Already handled by subject_padding in the caller's crop_w/crop_h—
    # here we just clamp so the crop stays inside the frame.
    cx = clamp(cx, crop_w / 2.0, frame_w - crop_w / 2.0)
    max_cy = frame_h - crop_h / 2.0
    if subtitle_safe_ratio > 0:
        max_cy -= frame_h * subtitle_safe_ratio * 0.35
    max_cy = max(crop_h / 2.0, max_cy)
    cy = clamp(cy, crop_h / 2.0, max_cy)
    return cx, cy


def _apply_velocity_limiter(
    centers_xy: List[Tuple[float, float]],
    src_w: int,
    src_h: int,
    crop_w: int,
    crop_h: int,
    cfg: MotionCropConfig,
) -> List[Tuple[int, int]]:
    """Convert (cx, cy) float centers → (x, y) integer top-left crop coords.

    Applies velocity + acceleration limits with smoothstep easing for
    cinematic panning: full speed when far from target, graceful deceleration
    when close — no snap, no overshoot.

    Also enforces subtitle_safe_bottom_ratio so the velocity limiter cannot
    push the crop into the subtitle zone even if the input path is at the
    boundary.
    """
    if not centers_xy:
        return []

    max_v = max(1.0, src_w * cfg.max_pan_speed_ratio)
    max_a = max(0.5, src_w * cfg.max_pan_accel_ratio)

    # Subtitle-safe ceiling for crop center Y — same formula as EMA loop.
    max_cy = src_h - crop_h / 2.0
    if cfg.subtitle_safe_bottom_ratio > 0:
        max_cy -= src_h * cfg.subtitle_safe_bottom_ratio * 0.35
    max_cy = max(crop_h / 2.0, max_cy)

    result: List[Tuple[int, int]] = []
    px, py = centers_xy[0]
    pvx, pvy = 0.0, 0.0

    for tx, ty in centers_xy:
        dist = math.hypot(tx - px, ty - py)
        # Smoothstep easing: t=0 near target (decelerate), t=1 far from target (full speed).
        # Minimum 0.12 so the camera always creeps toward target even when very close.
        t = clamp(dist / max(1.0, max_v * 8.0), 0.0, 1.0)
        ease = clamp(_smoothstep(t), 0.12, 1.0)
        dvx = clamp((tx - px) * ease, -max_v, max_v)
        dvy = clamp((ty - py) * ease, -max_v, max_v)
        vx = clamp(dvx, pvx - max_a, pvx + max_a)
        vy = clamp(dvy, pvy - max_a, pvy + max_a)
        nx = clamp(px + vx, crop_w / 2.0, src_w - crop_w / 2.0)
        ny = clamp(py + vy, crop_h / 2.0, max_cy)   # subtitle-safe ceiling

        # Convert center → top-left
        ix = int(clamp(round(nx - crop_w / 2.0), 0, src_w - crop_w))
        iy = int(clamp(round(ny - crop_h / 2.0), 0, src_h - crop_h))
        result.append((ix, iy))

        px, py = nx, ny
        pvx, pvy = vx, vy

    return result


def build_subject_path(
    video_path: str,
    crop_w: int,
    crop_h: int,
    cfg: MotionCropConfig,
    _scene_ranges=None,
    content_type: str = "vlog",
) -> Tuple[List[Tuple[int, int]], float]:
    """
    CapCut Auto Reframe equivalent.

    Algorithm:
    1. Every `subject_detect_interval` frames: run face → body detection on a
       half-size frame (4× faster), pick the best subject.
    2. Between detections: use CSRT tracker (fast, robust to occlusion).
    3. If tracker drifts or loses target, re-detect on next interval.
    4. Build raw (cx, cy) path, apply Gaussian smoothing, then velocity limit.

    Falls back to legacy motion mode if no subject is ever detected and
    `cfg.motion_fallback` is True.
    """
    if _scene_ranges and len(_scene_ranges) > 1:
        all_centers: List[Tuple[int, int]] = []
        fps = cfg.fps_fallback
        # Carries the final rendered crop center from each scene into the next
        # so that smooth_cx/smooth_cy in the EMA loop starts from the last
        # visible position rather than default frame center.
        _warmup_center: Optional[Tuple[float, float]] = None

        for index, (start_sec, end_sec) in enumerate(_scene_ranges):
            fallback_used = False
            try:
                scene_centers, fps = build_subject_path_scene(
                    video_path, crop_w, crop_h, cfg, start_sec, end_sec,
                    scene_index=index, warmup_center=_warmup_center,
                    content_type=content_type,
                )
            except Exception:
                fallback_used = True
                scene_fps = fps or cfg.fps_fallback
                cap = cv2.VideoCapture(video_path)
                if cap.isOpened():
                    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS) or scene_fps
                    scene_fps = fps
                    cap.release()
                else:
                    src_w = crop_w
                    src_h = crop_h
                frame_total = max(1, int(round(max(0.0, end_sec - start_sec) * scene_fps)))
                center_x = int(clamp(round(src_w / 2.0 - crop_w / 2.0), 0, max(0, src_w - crop_w)))
                center_y = int(clamp(round(src_h / 2.0 - crop_h / 2.0), 0, max(0, src_h - crop_h)))
                scene_centers = [(center_x, center_y)] * frame_total

            if fallback_used:
                logger.info(
                    "motion_crop scene=%d strategy=%s locked_subject=%s switches=%d avg_motion=%.2f fallback=%s",
                    index,
                    "center_fallback",
                    False,
                    0,
                    0.0,
                    True,
                )

            # Capture final rendered crop center for next scene warmup.
            # Converts top-left (x, y) → crop center (cx, cy) in source coords.
            if scene_centers:
                _last_x, _last_y = scene_centers[-1]
                _warmup_center = (_last_x + crop_w / 2.0, _last_y + crop_h / 2.0)

            all_centers.extend(scene_centers)

        return all_centers, fps

    cfg = _apply_content_type_to_cfg(cfg, content_type)
    face_cascade = _load_cascade("haarcascade_frontalface_default.xml")
    body_cascade = _load_cascade("haarcascade_fullbody.xml") if cfg.use_body_fallback else None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or cfg.fps_fallback
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Reduced-resolution scale for faster detection
    detect_scale = 0.30
    if src_h > 720:
        _det_scaled_w = max(1, int(round(src_w * 720.0 / src_h)))
        logger.debug(
            "motion_tracking_downscale_applied tracking_resolution_original=%dx%d "
            "tracking_resolution_scaled=%dx%d scale_ratio=%.3f",
            src_w, src_h, _det_scaled_w, 720, 720.0 / src_h,
        )

    default_cx = src_w / 2.0
    default_cy = src_h / 2.0

    tracker = _create_tracker()
    tracker_available = tracker is not None
    tracking = False
    last_subject: Optional[Tuple[int, int, int, int]] = None
    subjects_found_total = 0
    _btrack: Optional[_ByteTrackSubject] = None
    _last_eye_rel: Optional[float] = None

    raw_centers: List[Tuple[float, float]] = []
    frame_idx = 0
    detect_interval = max(1, cfg.subject_detect_interval)
    logger.info(
        "motion_crop_detect_interval input=%s content_type=%s detect_interval=%d tracker=%s",
        Path(video_path).name, content_type, detect_interval,
        "available" if tracker_available else "unavailable",
    )
    required_lock_confirm = _required_lock_confirm_frames(cfg, tracker_available)
    pending_subject: Optional[Tuple[int, int, int, int]] = None
    pending_count = 0
    trackerless_confidence = 0.0
    trackerless_confirm_streak = 0

    _tracking_start = time.monotonic()
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        _elapsed = time.monotonic() - _tracking_start
        if _elapsed > cfg.max_tracking_seconds:
            logger.warning(
                "motion_tracking_timeout elapsed_s=%.1f max_s=%.1f "
                "frames_processed=%d centers_collected=%d",
                _elapsed, cfg.max_tracking_seconds, frame_idx, len(raw_centers),
            )
            if raw_centers:
                logger.info(
                    "motion_tracking_partial_centers_used frames_processed=%d centers_collected=%d",
                    frame_idx, len(raw_centers),
                )
            else:
                logger.warning(
                    "motion_tracking_aborted_safe frames_processed=%d reason=no_centers_at_timeout",
                    frame_idx,
                )
            break

        subject: Optional[Tuple[int, int, int, int]] = None

        if _btrack is not None:
            _btrack.predict()
            if not _btrack.is_alive(cfg.lost_subject_hold_frames):
                _btrack = None

        # --- Step 1: update tracker ---
        if tracking and tracker is not None:
            ok_track, bbox = tracker.update(frame)
            if ok_track:
                x, y, w, h = [int(v) for v in bbox]
                # Sanity-check: reject obviously degenerate boxes
                if w > 4 and h > 4 and x >= 0 and y >= 0:
                    subject = (x, y, w, h)
                    last_subject = subject
                    if _btrack is not None:
                        if _btrack.update(subject, gain=0.20):
                            subject = _btrack.get_subject()
                        else:
                            tracking = False
                else:
                    tracking = False
            else:
                tracking = False

        # --- Step 2: re-detect every N frames (or when tracker lost) ---
        if frame_idx % detect_interval == 0 or (tracker_available and not tracking):
            _det_frame, _det_sx, _det_sy, _, _ = prepare_detection_frame(frame)
            small = cv2.resize(_det_frame, None, fx=detect_scale, fy=detect_scale)
            gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            detected, _kind = _detect_subjects_in_frame(
                gray_small, face_cascade, body_cascade, detect_scale, small
            )
            if _det_sx != 1.0:
                detected = [
                    (int(x / _det_sx), int(y / _det_sy), int(bw / _det_sx), int(bh / _det_sy))
                    for (x, y, bw, bh) in detected
                ]
            detected, _ = _filter_subject_candidates(detected, src_w, src_h, _kind, last_subject)
            best = _pick_best_subject(detected, src_w, src_h, last_subject)

            if best is not None:
                if last_subject is None and not tracker_available:
                    candidate_count = pending_count + 1 if _same_subject(pending_subject, best) else 1
                    candidate_confidence = _trackerless_detection_confidence(
                        best,
                        src_w,
                        src_h,
                        crop_w,
                        _kind,
                        pending_subject,
                        candidate_count,
                    )
                    candidate_offcenter = _trackerless_offcenter_ratio(best, src_w, crop_w)
                    confirm_needed = _required_lock_confirm_frames(
                        cfg,
                        tracker_available,
                        candidate_confidence,
                        candidate_offcenter,
                    )
                    if _same_subject(pending_subject, best):
                        pending_count = candidate_count
                    else:
                        pending_subject = best
                        pending_count = candidate_count
                    if pending_count < confirm_needed:
                        best = None
                    else:
                        pending_subject = None
                        pending_count = 0
                        trackerless_confidence = candidate_confidence
                        trackerless_confirm_streak = confirm_needed
                if best is not None:
                    subjects_found_total += 1
                    if tracker is not None:
                        bx, by, bw, bh = best
                        tracker.init(frame, (bx, by, bw, bh))
                        tracking = True
                    subject = best
                    if not tracker_available:
                        trackerless_confirm_streak = min(max(1, trackerless_confirm_streak) + 1, 6)
                        trackerless_confidence = _trackerless_detection_confidence(
                            best,
                            src_w,
                            src_h,
                            crop_w,
                            _kind,
                            last_subject,
                            trackerless_confirm_streak,
                        )
                    last_subject = best
                    _eye_rel = _get_eye_anchor_rel(small, best, detect_scale, _det_sy)
                    if _eye_rel is not None:
                        _last_eye_rel = _eye_rel
                    if _btrack is not None:
                        if not _btrack.update(best, gain=0.55):
                            _btrack = _ByteTrackSubject(best)
                    else:
                        _btrack = _ByteTrackSubject(best)

        # --- Step 3: compute crop center ---
        if subject is not None:
            cx, cy = _subject_to_crop_center(
                subject, crop_w, crop_h, src_w, src_h, cfg.subject_padding,
                cfg.subtitle_safe_bottom_ratio, eye_anchor_rel=_last_eye_rel,
            )
            if not tracker_available:
                cx, _, _ = _apply_trackerless_center_guard(
                    cx,
                    default_cx,
                    src_w,
                    crop_w,
                    trackerless_confidence,
                    trackerless_confirm_streak,
                )
        elif _btrack is not None and _btrack.is_alive(cfg.lost_subject_hold_frames):
            cx, cy = _subject_to_crop_center(
                _btrack.get_subject(), crop_w, crop_h, src_w, src_h, cfg.subject_padding,
                cfg.subtitle_safe_bottom_ratio, eye_anchor_rel=_last_eye_rel,
            )
            if not tracker_available:
                cx, _, _ = _apply_trackerless_center_guard(
                    cx,
                    default_cx,
                    src_w,
                    crop_w,
                    trackerless_confidence,
                    trackerless_confirm_streak,
                )
        elif last_subject is not None:
            # Hold last known subject position (subject momentarily occluded)
            cx, cy = _subject_to_crop_center(
                last_subject, crop_w, crop_h, src_w, src_h, cfg.subject_padding,
                cfg.subtitle_safe_bottom_ratio, eye_anchor_rel=_last_eye_rel,
            )
            if not tracker_available:
                cx, _, _ = _apply_trackerless_center_guard(
                    cx,
                    default_cx,
                    src_w,
                    crop_w,
                    trackerless_confidence,
                    trackerless_confirm_streak,
                )
        else:
            cx, cy = default_cx, default_cy

        raw_centers.append((cx, cy))
        frame_idx += 1

    cap.release()

    # If we never found a subject and fallback is enabled, use legacy motion
    if subjects_found_total == 0 and cfg.motion_fallback:
        logger.warning(
            "motion_fallback_triggered input=%s content_type=%s reason=no_subject_detected "
            "frames_scanned=%d detect_interval=%d → switching to legacy pixel-diff",
            Path(video_path).name, content_type, frame_idx, detect_interval,
        )
        return _build_motion_path_legacy(video_path, crop_w, crop_h, cfg)

    # Pad to frame_count
    default = (default_cx, default_cy)
    while len(raw_centers) < frame_count:
        raw_centers.append(raw_centers[-1] if raw_centers else default)

    # --- Step 4: Gaussian smoothing on X and Y paths separately ---
    window = max(3, cfg.temporal_smooth_window | 1)  # force odd
    xs = np.array([c[0] for c in raw_centers], dtype=float)
    ys = np.array([c[1] for c in raw_centers], dtype=float)
    xs = _gaussian_smooth_1d(xs, window)
    ys = _gaussian_smooth_1d(ys, window)
    smoothed = list(zip(xs.tolist(), ys.tolist()))

    # --- Step 5: velocity limiter → integer top-left coords ---
    centers = _apply_velocity_limiter(smoothed, src_w, src_h, crop_w, crop_h, cfg)

    return centers, fps


def build_subject_path_scene(
    video_path: str,
    crop_w: int,
    crop_h: int,
    cfg: MotionCropConfig,
    start_sec: float,
    end_sec: float,
    scene_index: int = 0,
    warmup_center: Optional[Tuple[float, float]] = None,
    content_type: str = "vlog",
) -> Tuple[List[Tuple[int, int]], float]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    try:
        cfg = _apply_content_type_to_cfg(cfg, content_type)
        face_cascade = _load_cascade("haarcascade_frontalface_default.xml")
        body_cascade = _load_cascade("haarcascade_fullbody.xml") if cfg.use_body_fallback else None

        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or cfg.fps_fallback
        start_frame = max(0, int(round(start_sec * fps)))
        end_frame = max(start_frame, int(round(end_sec * fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        detect_scale = 0.30
        if src_h > 720:
            _det_scaled_w = max(1, int(round(src_w * 720.0 / src_h)))
            logger.debug(
                "motion_tracking_downscale_applied scene=%d tracking_resolution_original=%dx%d "
                "tracking_resolution_scaled=%dx%d scale_ratio=%.3f",
                scene_index, src_w, src_h, _det_scaled_w, 720, 720.0 / src_h,
            )
        default_cx = src_w / 2.0
        default_cy = src_h / 2.0

        tracker = _create_tracker()
        tracker_available = tracker is not None
        tracking = False
        locked_subject: Optional[Tuple[int, int, int, int]] = None
        locked_kind = "none"
        pending_subject: Optional[Tuple[int, int, int, int]] = None
        pending_kind = "none"
        pending_count = 0
        switch_count = 0
        switch_cooldown = 0   # frames remaining in post-switch easing window
        lost_frames = 0
        # Continuity: if a warmup center from the previous scene is available,
        # initialize the EMA state from it so the camera doesn't snap to frame
        # center at scene boundaries.  Subject identity is NOT carried over.
        if warmup_center is not None:
            smooth_cx, smooth_cy = float(warmup_center[0]), float(warmup_center[1])
            last_good_center = (smooth_cx, smooth_cy)
            logger.info(
                "scene_warmup_center_used scene=%d warmup_cx=%.1f warmup_cy=%.1f",
                scene_index, smooth_cx, smooth_cy,
            )
        else:
            smooth_cx = default_cx
            smooth_cy = default_cy
            last_good_center = (default_cx, default_cy)
            if scene_index > 0:
                logger.debug(
                    "scene_warmup_center_skipped scene=%d (no prior center available)",
                    scene_index,
                )
        raw_centers: List[Tuple[float, float]] = []
        detect_interval = max(1, cfg.subject_detect_interval)
        logger.info(
            "motion_crop_detect_interval input=%s scene=%d content_type=%s detect_interval=%d tracker=%s",
            Path(video_path).name, scene_index, content_type, detect_interval,
            "available" if tracker_available else "unavailable",
        )
        required_lock_confirm = _required_lock_confirm_frames(cfg, tracker_available)
        untracked_hold_frames = _untracked_hold_frames(cfg, detect_interval)
        dead_zone_x = crop_w * cfg.dead_zone_ratio
        dead_zone_y = crop_h * cfg.dead_zone_ratio
        frame_idx = start_frame
        motion_total = 0.0
        motion_samples = 0
        detections_rejected = 0
        lock_confirmed = 0
        detect_miss_intervals = 0
        fallback_reason = "none"
        scene_fallback_reason = "none"
        trackerless_confidence = 0.0
        trackerless_confirm_streak = 0
        center_guard_active = False
        _btrack: Optional[_ByteTrackSubject] = None
        _last_eye_rel: Optional[float] = None

        _tracking_start = time.monotonic()
        while frame_idx < end_frame:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            _elapsed = time.monotonic() - _tracking_start
            if _elapsed > cfg.max_tracking_seconds:
                logger.warning(
                    "motion_tracking_timeout scene=%d elapsed_s=%.1f max_s=%.1f "
                    "frames_processed=%d centers_collected=%d",
                    scene_index, _elapsed, cfg.max_tracking_seconds,
                    frame_idx - start_frame, len(raw_centers),
                )
                if raw_centers:
                    logger.info(
                        "motion_tracking_partial_centers_used scene=%d "
                        "frames_processed=%d centers_collected=%d",
                        scene_index, frame_idx - start_frame, len(raw_centers),
                    )
                else:
                    logger.warning(
                        "motion_tracking_aborted_safe scene=%d frames_processed=%d "
                        "reason=no_centers_at_timeout",
                        scene_index, frame_idx - start_frame,
                    )
                break

            subject: Optional[Tuple[int, int, int, int]] = None

            if _btrack is not None:
                _btrack.predict()
                if not _btrack.is_alive(cfg.lost_subject_hold_frames):
                    _btrack = None

            if tracking and tracker is not None:
                ok_track, bbox = tracker.update(frame)
                if ok_track:
                    x, y, w, h = [int(v) for v in bbox]
                    if w > 4 and h > 4 and x >= 0 and y >= 0:
                        subject = (x, y, w, h)
                        locked_subject = subject
                        lost_frames = 0
                        if _btrack is not None:
                            if _btrack.update(subject, gain=0.20):
                                subject = _btrack.get_subject()
                            else:
                                tracking = False
                    else:
                        tracking = False
                else:
                    tracking = False

            scene_frame_idx = frame_idx - start_frame
            if tracker_available:
                should_detect = scene_frame_idx % detect_interval == 0 or not tracking
            else:
                should_detect = scene_frame_idx % detect_interval == 0
            detection_confirmed = False
            if should_detect:
                _det_frame, _det_sx, _det_sy, _, _ = prepare_detection_frame(frame)
                small = cv2.resize(_det_frame, None, fx=detect_scale, fy=detect_scale)
                gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                detected, detected_kind = _detect_subjects_in_frame(
                    gray_small, face_cascade, body_cascade, detect_scale, small
                )
                if _det_sx != 1.0:
                    detected = [
                        (int(x / _det_sx), int(y / _det_sy), int(bw / _det_sx), int(bh / _det_sy))
                        for (x, y, bw, bh) in detected
                    ]
                detected, rejected = _filter_subject_candidates(
                    detected, src_w, src_h, detected_kind, locked_subject
                )
                detections_rejected += rejected
                best = _pick_best_subject(detected, src_w, src_h, locked_subject)

                if best is not None:
                    if locked_subject is None:
                        if tracker_available:
                            locked_subject = best
                            locked_kind = detected_kind
                            subject = best
                            lost_frames = 0
                            pending_subject = None
                            pending_kind = "none"
                            pending_count = 0
                            lock_confirmed += 1
                            detection_confirmed = True
                        else:
                            candidate_count = pending_count + 1 if _same_subject(pending_subject, best) else 1
                            candidate_confidence = _trackerless_detection_confidence(
                                best,
                                src_w,
                                src_h,
                                crop_w,
                                detected_kind,
                                pending_subject,
                                candidate_count,
                            )
                            candidate_offcenter = _trackerless_offcenter_ratio(best, src_w, crop_w)
                            confirm_needed = _required_lock_confirm_frames(
                                cfg,
                                tracker_available,
                                candidate_confidence,
                                candidate_offcenter,
                            )
                            if _same_subject(pending_subject, best):
                                pending_count = candidate_count
                            else:
                                pending_subject = best
                                pending_kind = detected_kind
                                pending_count = candidate_count
                            fallback_reason = "await_initial_confirmation"
                            scene_fallback_reason = fallback_reason
                            if pending_count >= confirm_needed:
                                locked_subject = best
                                locked_kind = pending_kind or detected_kind
                                subject = best
                                lost_frames = 0
                                pending_subject = None
                                pending_kind = "none"
                                pending_count = 0
                                lock_confirmed += 1
                                detection_confirmed = True
                                fallback_reason = "none"
                                trackerless_confidence = candidate_confidence
                                trackerless_confirm_streak = confirm_needed
                    elif _same_subject(locked_subject, best):
                        if not tracker_available:
                            trackerless_confirm_streak = min(max(1, trackerless_confirm_streak) + 1, 6)
                            trackerless_confidence = _trackerless_detection_confidence(
                                best,
                                src_w,
                                src_h,
                                crop_w,
                                detected_kind,
                                locked_subject,
                                trackerless_confirm_streak,
                            )
                        locked_subject = best
                        locked_kind = detected_kind
                        subject = best
                        lost_frames = 0
                        pending_subject = None
                        pending_kind = "none"
                        pending_count = 0
                        detection_confirmed = True
                    else:
                        current_score = _score_subject_candidate(locked_subject, src_w, src_h, locked_subject)
                        new_score = _score_subject_candidate(best, src_w, src_h, locked_subject)
                        if new_score >= current_score * cfg.subject_switch_margin:
                            candidate_count = pending_count + 1 if _same_subject(pending_subject, best) else 1
                            candidate_confidence = _trackerless_detection_confidence(
                                best,
                                src_w,
                                src_h,
                                crop_w,
                                detected_kind,
                                locked_subject,
                                candidate_count,
                            )
                            candidate_offcenter = _trackerless_offcenter_ratio(best, src_w, crop_w)
                            confirm_needed = _required_lock_confirm_frames(
                                cfg,
                                tracker_available,
                                candidate_confidence if not tracker_available else None,
                                candidate_offcenter if not tracker_available else 0.0,
                            )
                            if _same_subject(pending_subject, best):
                                pending_count = candidate_count
                            else:
                                pending_subject = best
                                pending_kind = detected_kind
                                pending_count = candidate_count

                            fallback_reason = "await_switch_confirmation"
                            scene_fallback_reason = fallback_reason
                            if pending_count >= confirm_needed:
                                locked_subject = best
                                locked_kind = pending_kind or detected_kind
                                subject = best
                                switch_count += 1
                                lost_frames = 0
                                pending_subject = None
                                pending_kind = "none"
                                pending_count = 0
                                lock_confirmed += 1
                                detection_confirmed = True
                                fallback_reason = "none"
                                trackerless_confidence = candidate_confidence
                                trackerless_confirm_streak = confirm_needed
                                # Activate easing window: camera pans toward new subject
                                # without dead-zone suppression for ~0.5 s.
                                switch_cooldown = max(4, int(fps * 0.5))
                        else:
                            pending_subject = None
                            pending_kind = "none"
                            pending_count = 0

                    if subject is None and tracking:
                        subject = locked_subject

                    if subject is not None and tracker is not None:
                        bx, by, bw, bh = subject
                        tracker = _create_tracker()
                        if tracker is not None:
                            tracker.init(frame, (bx, by, bw, bh))
                            tracking = True
                if detection_confirmed:
                    detect_miss_intervals = 0
                    if locked_subject is not None:
                        _eye_rel = _get_eye_anchor_rel(small, locked_subject, detect_scale, _det_sy)
                        if _eye_rel is not None:
                            _last_eye_rel = _eye_rel
                        if _btrack is not None:
                            if not _btrack.update(locked_subject, gain=0.55):
                                _btrack = _ByteTrackSubject(locked_subject)
                        else:
                            _btrack = _ByteTrackSubject(locked_subject)
                elif locked_subject is not None and not tracking:
                    detect_miss_intervals += 1

            trackerless_hold_frames = _trackerless_hold_frames_for_confidence(
                untracked_hold_frames,
                trackerless_confidence,
            ) if not tracker_available else untracked_hold_frames

            if subject is None and locked_subject is not None:
                if tracking:
                    subject = locked_subject
                else:
                    lost_frames += 1
                    if (
                        not tracker_available
                        and detect_miss_intervals >= 1
                        and lost_frames >= trackerless_hold_frames
                    ):
                        locked_subject = None
                        locked_kind = "none"
                        pending_subject = None
                        pending_kind = "none"
                        pending_count = 0
                        fallback_reason = "stale_untracked_lock"
                        scene_fallback_reason = fallback_reason

            hold_frames = cfg.lost_subject_hold_frames if tracker_available else trackerless_hold_frames
            if subject is not None:
                target_cx, target_cy = _subject_to_crop_center(
                    subject, crop_w, crop_h, src_w, src_h, cfg.subject_padding,
                    cfg.subtitle_safe_bottom_ratio, locked_kind,
                    eye_anchor_rel=_last_eye_rel,
                )
                if not tracker_available:
                    target_cx, guard_hit, guard_reason = _apply_trackerless_center_guard(
                        target_cx,
                        default_cx,
                        src_w,
                        crop_w,
                        trackerless_confidence,
                        trackerless_confirm_streak,
                    )
                    center_guard_active = center_guard_active or guard_hit
                    if guard_reason != "none":
                        scene_fallback_reason = guard_reason
                last_good_center = (target_cx, target_cy)
            elif locked_subject is not None and lost_frames <= hold_frames:
                target_cx, target_cy = last_good_center
            else:
                # Smoothstep return: slow start → faster mid → soft landing at center.
                # Ramps over 1.0 s instead of 0.75 s to feel less abrupt.
                t_return = min(1.0, (lost_frames - hold_frames) / max(1.0, fps * 1.0))
                return_alpha_cap = 0.16 if (not tracker_available and trackerless_confidence < 0.78) else 0.10
                return_alpha = _smoothstep(t_return) * return_alpha_cap
                target_cx = ema(last_good_center[0], default_cx, return_alpha)
                target_cy = ema(last_good_center[1], default_cy, return_alpha)
                last_good_center = (target_cx, target_cy)

            movement = math.hypot(target_cx - smooth_cx, target_cy - smooth_cy)
            if movement < min(crop_w, crop_h) * 0.025:
                alpha = cfg.ema_alpha_slow
            elif movement < min(crop_w, crop_h) * 0.12:
                alpha = cfg.ema_alpha_normal
            else:
                alpha = cfg.ema_alpha_fast

            active_subject = subject or locked_subject
            if active_subject is not None:
                _, _, sw, sh = active_subject
                subject_ratio = (sw * sh) / max(1.0, float(src_w * src_h))
                if subject_ratio > 0.18:
                    alpha *= 0.65
                elif subject_ratio < 0.035:
                    alpha *= 1.15
            alpha = clamp(alpha, 0.03, 0.50)

            # During post-switch cooldown: bypass dead-zone so the camera
            # actively pans toward the new subject without hesitation.
            # Alpha is floored at ema_alpha_normal to maintain responsiveness.
            force_recenter = not tracker_available and locked_subject is None and lost_frames > 0
            if switch_cooldown > 0:
                switch_cooldown -= 1
                alpha = max(alpha, cfg.ema_alpha_normal)
                smooth_cx = ema(smooth_cx, target_cx, alpha)
                smooth_cy = ema(smooth_cy, target_cy, alpha)
            elif force_recenter:
                recenter_floor = cfg.ema_alpha_fast if trackerless_confidence < 0.78 else cfg.ema_alpha_normal
                alpha = max(alpha, recenter_floor)
                smooth_cx = ema(smooth_cx, target_cx, alpha)
                smooth_cy = ema(smooth_cy, target_cy, alpha)
            else:
                if abs(target_cx - smooth_cx) > dead_zone_x:
                    smooth_cx = ema(smooth_cx, target_cx, alpha)
                if abs(target_cy - smooth_cy) > dead_zone_y:
                    smooth_cy = ema(smooth_cy, target_cy, alpha)

            smooth_cx = clamp(smooth_cx, crop_w / 2.0, src_w - crop_w / 2.0)
            max_cy = src_h - crop_h / 2.0
            if cfg.subtitle_safe_bottom_ratio > 0:
                max_cy -= src_h * cfg.subtitle_safe_bottom_ratio * 0.35
            max_cy = max(crop_h / 2.0, max_cy)
            smooth_cy = clamp(smooth_cy, crop_h / 2.0, max_cy)

            if raw_centers:
                motion_total += math.hypot(smooth_cx - raw_centers[-1][0], smooth_cy - raw_centers[-1][1])
                motion_samples += 1
            raw_centers.append((smooth_cx, smooth_cy))
            frame_idx += 1

        expected_frames = max(1, end_frame - start_frame)
        default = (default_cx, default_cy)
        while len(raw_centers) < expected_frames:
            raw_centers.append(raw_centers[-1] if raw_centers else default)

        lookahead = max(0, int(cfg.lookahead_frames))
        if lookahead > 0 and len(raw_centers) > 2:
            looked: List[Tuple[float, float]] = []
            for i, center in enumerate(raw_centers):
                hi = min(len(raw_centers), i + lookahead + 1)
                span = raw_centers[i:hi]
                weight_total = 1.0
                sx, sy = center
                for offset, future in enumerate(span[1:], start=1):
                    weight = 0.28 / offset
                    sx += future[0] * weight
                    sy += future[1] * weight
                    weight_total += weight
                looked.append((sx / weight_total, sy / weight_total))
            raw_centers = looked

        avg_motion = motion_total / max(1, motion_samples)
        scene_frames = len(raw_centers)

        # Adaptive Gaussian window: scales with scene length and motion level.
        # Short scenes cap tightly to avoid over-smoothing edge frames;
        # longer scenes absorb the lag cost and benefit from wider passes.
        # Floor: 7 frames (always odd).  Ceiling: min(25, scene_frames // 6).
        if avg_motion > 2.0:
            scene_gaussian_window = 7
        elif avg_motion > 0.5:
            scene_gaussian_window = 13
        else:
            scene_gaussian_window = 21
        max_window = max(7, min(25, scene_frames // 6))
        scene_gaussian_window = max(3, min(scene_gaussian_window, max_window) | 1)
        logger.debug(
            "scene_gaussian_window_used scene=%d window=%d max_window=%d avg_motion=%.2f frames=%d",
            scene_index, scene_gaussian_window, max_window, avg_motion, scene_frames,
        )

        xs = np.array([c[0] for c in raw_centers], dtype=float)
        ys = np.array([c[1] for c in raw_centers], dtype=float)
        xs = _gaussian_smooth_1d(xs, scene_gaussian_window)
        ys = _gaussian_smooth_1d(ys, scene_gaussian_window)
        smoothed = list(zip(xs.tolist(), ys.tolist()))
        final_centers = _apply_velocity_limiter(smoothed, src_w, src_h, crop_w, crop_h, cfg)
        crop_x_values = [xy[0] for xy in final_centers] if final_centers else [int(default_cx - crop_w / 2.0)]

        strategy = "subject_lock" if locked_subject is not None else "center_hold"
        logger.info(
            "motion_crop scene=%d strategy=%s tracker_available=%s locked=%s "
            "trackerless_confidence=%.2f center_guard_active=%s crop_x_range=%d-%d "
            "lock_confirmed=%d detections_rejected=%d fallback=%s switches=%d "
            "avg_motion=%.2f gauss_window=%d subtitle_safe=%.3f "
            "hold_frames_used=%d dead_zone_used=%.3f pan_speed_limit_used=%.4f",
            scene_index,
            strategy,
            tracker_available,
            bool(locked_subject),
            trackerless_confidence,
            center_guard_active,
            min(crop_x_values),
            max(crop_x_values),
            lock_confirmed,
            detections_rejected,
            scene_fallback_reason if scene_fallback_reason != "none" else fallback_reason,
            switch_count,
            avg_motion,
            scene_gaussian_window,
            cfg.subtitle_safe_bottom_ratio,
            cfg.lost_subject_hold_frames,
            cfg.dead_zone_ratio,
            cfg.max_pan_speed_ratio,
        )

        # Log the final rendered crop center so the caller can pass it as warmup
        # to the next scene — enables scene-boundary camera continuity.
        if final_centers:
            _fc_x, _fc_y = final_centers[-1]
            _final_cx = _fc_x + crop_w / 2.0
            _final_cy = _fc_y + crop_h / 2.0
        else:
            _final_cx, _final_cy = default_cx, default_cy
        logger.info(
            "scene_path_final_center scene=%d final_cx=%.1f final_cy=%.1f frames=%d",
            scene_index, _final_cx, _final_cy, scene_frames,
        )

        return final_centers, fps
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Legacy motion-based tracking (pixel-diff, kept as fallback)
# ---------------------------------------------------------------------------

def detect_motion_center(
    prev_gray: np.ndarray,
    gray: np.ndarray,
    frame_width: int,
    frame_height: int,
    cfg: MotionCropConfig,
) -> Tuple[float, float]:
    diff = cv2.absdiff(prev_gray, gray)
    _, thresh = cv2.threshold(diff, cfg.motion_threshold, 255, cv2.THRESH_BINARY)
    thresh = cv2.GaussianBlur(thresh, (7, 7), 0)
    thresh = cv2.threshold(thresh, 25, 255, cv2.THRESH_BINARY)[1]
    thresh = cv2.dilate(thresh, None, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = frame_width * frame_height
    min_area = frame_area * cfg.min_contour_area_ratio

    weighted_x = weighted_y = total_weight = 0.0
    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue
        x, y, w, h = cv2.boundingRect(c)
        cx, cy = x + w / 2.0, y + h / 2.0
        center_x, center_y = frame_width / 2.0, frame_height / 2.0
        dist_center = math.hypot(cx - center_x, cy - center_y)
        max_dist = math.hypot(center_x, center_y)
        center_bonus = 1.0 - (dist_center / max_dist) * cfg.prefer_center_bias
        weight = area * center_bonus
        weighted_x += cx * weight
        weighted_y += cy * weight
        total_weight += weight

    if total_weight <= 0:
        return frame_width / 2.0, frame_height / 2.0
    return weighted_x / total_weight, weighted_y / total_weight


def _build_motion_path_legacy(
    video_path: str,
    crop_w: int,
    crop_h: int,
    cfg: MotionCropConfig,
) -> Tuple[List[Tuple[int, int]], float]:
    """Original pixel-diff motion tracking (legacy fallback)."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or cfg.fps_fallback
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    ok, first = cap.read()
    if not ok or first is None:
        cap.release()
        raise RuntimeError("Cannot read first frame")

    prev_gray = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    cx, cy = src_w / 2.0, src_h / 2.0

    centers: List[Tuple[int, int]] = []
    max_pan_px = max(3.0, src_w * cfg.max_pan_speed_ratio)
    max_accel_px = max(1.0, src_w * cfg.max_pan_accel_ratio)
    dead_zone_x = crop_w * cfg.dead_zone_ratio
    dead_zone_y = crop_h * cfg.dead_zone_ratio
    prev_dx = prev_dy = 0.0

    def center_to_top_left(center_x: float, center_y: float) -> Tuple[int, int]:
        x = int(clamp(round(center_x - crop_w / 2.0), 0, src_w - crop_w))
        y = int(clamp(round(center_y - crop_h / 2.0), 0, src_h - crop_h))
        return x, y

    centers.append(center_to_top_left(cx, cy))

    idx = 1
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if idx % cfg.sample_every_n_frames == 0:
            motion_cx, motion_cy = detect_motion_center(prev_gray, gray, src_w, src_h, cfg)
            target_cx = ema(cx, motion_cx, cfg.smooth_alpha) if abs(motion_cx - cx) > dead_zone_x else cx
            target_cy = ema(cy, motion_cy, cfg.smooth_alpha) if abs(motion_cy - cy) > dead_zone_y else cy
            desired_dx = clamp(target_cx - cx, -max_pan_px, max_pan_px)
            desired_dy = clamp(target_cy - cy, -max_pan_px, max_pan_px)
            dx = clamp(desired_dx, prev_dx - max_accel_px, prev_dx + max_accel_px)
            dy = clamp(desired_dy, prev_dy - max_accel_px, prev_dy + max_accel_px)
            cx += dx
            cy += dy
            prev_dx, prev_dy = dx, dy
        else:
            cx += prev_dx * 0.92
            cy += prev_dy * 0.92
            prev_dx *= 0.92
            prev_dy *= 0.92
        centers.append(center_to_top_left(cx, cy))
        prev_gray = gray
        idx += 1

    cap.release()

    while len(centers) < frame_count and centers:
        centers.append(centers[-1])

    # Temporal smoothing pass
    if centers and cfg.temporal_smooth_window > 2:
        half = cfg.temporal_smooth_window // 2
        smoothed: List[Tuple[int, int]] = []
        for i in range(len(centers)):
            lo, hi = max(0, i - half), min(len(centers), i + half + 1)
            xs = [centers[j][0] for j in range(lo, hi)]
            ys = [centers[j][1] for j in range(lo, hi)]
            x = int(clamp(round(sum(xs) / max(1, len(xs))), 0, src_w - crop_w))
            y = int(clamp(round(sum(ys) / max(1, len(ys))), 0, src_h - crop_h))
            smoothed.append((x, y))
        centers = smoothed

    # Jerk limiter pass
    if len(centers) > 1:
        limited: List[Tuple[int, int]] = [centers[0]]
        prev_x, prev_y = float(centers[0][0]), float(centers[0][1])
        prev_dx, prev_dy = 0.0, 0.0
        max_step = max(1.0, src_w * 0.006)
        max_accel = max(0.5, src_w * 0.0022)
        for i in range(1, len(centers)):
            tx, ty = float(centers[i][0]), float(centers[i][1])
            desired_dx = clamp(tx - prev_x, -max_step, max_step)
            desired_dy = clamp(ty - prev_y, -max_step, max_step)
            dx = clamp(desired_dx, prev_dx - max_accel, prev_dx + max_accel)
            dy = clamp(desired_dy, prev_dy - max_accel, prev_dy + max_accel)
            nx = clamp(prev_x + dx, 0, src_w - crop_w)
            ny = clamp(prev_y + dy, 0, src_h - crop_h)
            limited.append((int(round(nx)), int(round(ny))))
            prev_x, prev_y = nx, ny
            prev_dx, prev_dy = dx, dy
        centers = limited

    return centers, fps


def _detect_scene_ranges_in_clip(video_path: str, cfg: MotionCropConfig):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return [(0.0, 0.0)]

    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or cfg.fps_fallback
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0

        prev_gray = None
        cuts: List[float] = []
        frame_idx = 0
        sample_every = max(1, int(round(fps / 6.0)))

        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            if frame_idx % sample_every != 0:
                frame_idx += 1
                continue

            small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = float(np.mean(cv2.absdiff(prev_gray, gray)))
                if diff >= cfg.scene_cut_threshold:
                    t = frame_idx / fps if fps > 0 else 0.0
                    if not cuts or t - cuts[-1] > 0.35:
                        cuts.append(t)
            prev_gray = gray
            frame_idx += 1

        if duration <= 0.0 and fps > 0:
            duration = frame_idx / fps

        ranges: List[Tuple[float, float]] = []
        start = 0.0
        for cut in cuts:
            cut = clamp(cut, 0.0, duration)
            if cut > start:
                ranges.append((start, cut))
                start = cut
        if duration > start:
            ranges.append((start, duration))
        return ranges or [(0.0, duration)]
    except Exception:
        fps = cap.get(cv2.CAP_PROP_FPS) or cfg.fps_fallback
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
        return [(0.0, duration)]
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# Public entry point (called by render_engine / render_motion_aware_crop)
# ---------------------------------------------------------------------------

def build_motion_path(
    video_path: str,
    crop_w: int,
    crop_h: int,
    cfg: MotionCropConfig,
    _scene_ranges=None,
    content_type: str = "vlog",
) -> Tuple[List[Tuple[int, int]], float]:
    """
    Route to the appropriate tracking algorithm based on cfg.reframe_mode.

    - "subject" (default): CapCut-style face/body detection + CSRT tracker
    - "motion":            legacy pixel-diff motion tracking
    """
    if cfg.reframe_mode == "subject":
        return build_subject_path(
            video_path, crop_w, crop_h, cfg,
            _scene_ranges=_scene_ranges, content_type=content_type,
        )
    return _build_motion_path_legacy(video_path, crop_w, crop_h, cfg)


# ---------------------------------------------------------------------------
# Main render function (signature unchanged)
# ---------------------------------------------------------------------------

def render_motion_aware_crop(
    input_path: str,
    output_path: str,
    aspect_ratio: str = "3:4",
    scale_x_percent: float = 100.0,
    scale_y_percent: float = 106.0,
    subtitle_file: str | None = None,
    title_text: str | None = None,
    effect_preset: str = "slay_soft_01",
    transition_sec: float = 0.25,
    video_codec: str = "h264",
    video_crf: int = 20,
    video_preset: str = "medium",
    audio_bitrate: str = "192k",
    retry_count: int = 2,
    encoder_mode: str = "auto",
    output_fps: int = 60,
    reup_mode: bool = False,
    reup_overlay_enable: bool = True,
    reup_overlay_opacity: float = 0.08,
    reup_bgm_enable: bool = False,
    reup_bgm_path: str | None = None,
    reup_bgm_gain: float = 0.18,
    playback_speed: float = 1.07,
    text_layers: list[dict] | None = None,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    cfg: MotionCropConfig | None = None,
    subtitle_safe_bottom_ratio: float | None = None,
    content_type: str = "vlog",
    _cache_key: str | None = None,
) -> str:
    layer_count = len(text_layers or [])
    if layer_count:
        logger.info("Applying %d text overlay layer(s) in motion-aware pipeline", layer_count)
    cfg = cfg or MotionCropConfig(scale_x_percent=scale_x_percent, scale_y_percent=scale_y_percent)
    if subtitle_safe_bottom_ratio is not None:
        cfg.subtitle_safe_bottom_ratio = max(0.0, min(0.35, float(subtitle_safe_bottom_ratio)))

    logger.info(
        "motion_smoothing_profile hold_frames=%d dead_zone=%.3f pan_speed=%.4f "
        "ema_fast=%.3f ema_normal=%.3f ema_slow=%.3f gauss_window=%d mode=%s",
        cfg.lost_subject_hold_frames,
        cfg.dead_zone_ratio,
        cfg.max_pan_speed_ratio,
        cfg.ema_alpha_fast,
        cfg.ema_alpha_normal,
        cfg.ema_alpha_slow,
        cfg.temporal_smooth_window,
        cfg.reframe_mode,
    )

    src_w, src_h, probe_fps = ffprobe_video_info(input_path)

    if aspect_ratio == "1:1":
        out_w, out_h = 1080, 1080
    elif aspect_ratio == "9:16":
        out_w, out_h = 1080, 1920
    elif aspect_ratio == "16:9":
        out_w, out_h = 1920, 1080
    else:
        out_w, out_h = 1080, 1440  # 3:4, 4:5, and any unrecognised value

    scaled_w = int(round(src_w * (cfg.scale_x_percent / 100.0)))
    scaled_h = int(round(src_h * (cfg.scale_y_percent / 100.0)))

    target_ratio = out_w / out_h
    scale_ratio = scaled_w / scaled_h

    if scale_ratio > target_ratio:
        crop_h = scaled_h
        crop_w = int(round(crop_h * target_ratio))
    else:
        crop_w = scaled_w
        crop_h = int(round(crop_w / target_ratio))

    crop_w = min(crop_w, scaled_w)
    crop_h = min(crop_h, scaled_h)

    crop_w_src = int(round(crop_w / (cfg.scale_x_percent / 100.0)))
    crop_h_src = int(round(crop_h / (cfg.scale_y_percent / 100.0)))
    crop_w_src = min(crop_w_src, src_w)
    crop_h_src = min(crop_h_src, src_h)

    # Build crop path (subject-tracking or legacy motion)
    scene_ranges = None
    if cfg.scene_aware_tracking:
        scene_ranges = _detect_scene_ranges_in_clip(input_path, cfg)
        if not scene_ranges or len(scene_ranges) <= 1:
            scene_ranges = None
        else:
            logger.info("scene-aware scenes=%d", len(scene_ranges))

    # UP28.1: motion path cache — skip frame scan on rerender of same clip
    _motion_hit = False
    if _cache_key:
        _cached_motion = _motion_path_cache_get(_cache_key)
        if _cached_motion is not None:
            centers, detected_fps = _cached_motion
            _motion_hit = True
            logger.info("motion_cache_hit key=%s centers=%d fps=%.2f", _cache_key[:8], len(centers), detected_fps)
    if not _motion_hit:
        # C3b Early exit: skip expensive per-frame MediaPipe scan on videos
        # with no people. Sample 24 sparse frames first; if no face found,
        # fall back to faster legacy motion tracking instead of subject tracking.
        _skip_subject = (
            cfg.reframe_mode == "subject"
            and not _has_subject_in_sample(input_path)
        )
        if _skip_subject:
            logger.info("motion_crop_early_exit: no face in sample, using motion fallback")
            centers, detected_fps = _build_motion_path_legacy(input_path, crop_w_src, crop_h_src, cfg)
        else:
            centers, detected_fps = build_motion_path(
                input_path,
                crop_w_src,
                crop_h_src,
                cfg,
                _scene_ranges=scene_ranges,
                content_type=content_type,
            )
        if _cache_key:
            _motion_path_cache_put(_cache_key, centers, detected_fps)
            logger.info("motion_cache_miss key=%s centers=%d fps=%.2f", _cache_key[:8], len(centers), detected_fps)

    # Diagnostic: log crop-box sample positions (first, midpoint, last)
    if centers:
        _n = len(centers)
        _sample_mid = centers[_n // 2]
        logger.debug(
            "motion_crop_path input=%s centers=%d crop_src=%dx%d out=%dx%d "
            "first_xy=%s mid_xy=%s last_xy=%s",
            Path(input_path).name, _n, crop_w_src, crop_h_src, out_w, out_h,
            centers[0], _sample_mid, centers[-1],
        )

    # Build ffmpeg video filter chain
    vf_parts = []
    preset_low = (video_preset or "").lower()
    # hqdn3d denoiser only for slower/veryslow (quality mode)
    if preset_low in ("slower", "veryslow"):
        vf_parts.append("hqdn3d=1.5:1.5:6:6")
    if reup_mode:
        # Reup mode: dedicated reup filters (already includes eq+unsharp+hqdn3d)
        vf_parts.extend(_reup_video_filters())
        if reup_overlay_enable:
            opacity = max(0.01, min(0.20, float(reup_overlay_opacity or 0.08)))
            vf_parts.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{opacity}:t=fill")
    else:
        # Normal mode: apply creative effect filter
        if effect_preset == "slay_pop_01":
            vf_parts.append("eq=contrast=1.08:saturation=1.18:brightness=0.01:gamma=1.02,unsharp=5:5:1.2:3:3:0.5")
        elif effect_preset == "story_clean_01":
            vf_parts.append("eq=contrast=1.03:saturation=1.05:brightness=0.0,unsharp=3:3:0.6:3:3:0.15")
        else:
            vf_parts.append("eq=contrast=1.05:saturation=1.10:brightness=0.0:gamma=1.01,unsharp=5:5:0.9:3:3:0.35")

    vf_parts.append("format=yuv420p")
    if transition_sec and transition_sec > 0:
        vf_parts.append(f"fade=t=in:st=0:d={max(0.05, min(0.8, transition_sec))}")

    if subtitle_file and os.path.exists(subtitle_file):
        sub_safe = _safe_filter_path(subtitle_file)
        fonts_dir = _get_custom_fonts_dir() or _detect_windows_fonts_dir()
        if fonts_dir:
            vf_parts.append(f"ass='{sub_safe}':fontsdir='{_safe_filter_path(fonts_dir)}'")
        else:
            vf_parts.append(f"ass='{sub_safe}'")

    if title_text:
        fontfile = _detect_windows_fontfile()
        safe_title = title_text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")
        drawtext = f"drawtext=text='{safe_title}':fontcolor=white:fontsize=36:x=(w-text_w)/2:y=50:enable='lt(t\\,3)'"
        if fontfile:
            drawtext += f":fontfile='{_safe_filter_path(fontfile)}'"
        vf_parts.append(drawtext)
    append_text_layer_filters(vf_parts, text_layers)

    speed = _sanitize_speed(playback_speed)
    if abs(speed - 1.0) > 1e-4:
        # setpts must come BEFORE fps so the fps filter receives speed-adjusted
        # timestamps and produces a constant-rate output at exactly target_fps.
        vf_parts.append(f"setpts=PTS/{speed:.4f}")

    # Source fps: prefer ffprobe (probe_fps) over OpenCV (detected_fps).
    # OpenCV CAP_PROP_FPS returns 0 for some MKV/TS containers; using it for
    # the ffmpeg -r flag would declare the wrong input rate and cause truncated
    # or jittery output.  ffprobe avg_frame_rate is always authoritative.
    _FPS_CAP = 60
    src_fps = max(1.0, float(probe_fps or detected_fps or cfg.fps_fallback))
    if not output_fps:
        target_fps = max(1, min(int(round(src_fps)), _FPS_CAP))
        fps_policy = f"fps_policy=auto src={src_fps:.3f} target={target_fps}"
    else:
        target_fps = max(1, min(int(round(src_fps)), int(output_fps), _FPS_CAP))
        fps_policy = f"fps_policy=user({output_fps}) src={src_fps:.3f} target={target_fps}"
    logger.info("motion_crop: %s | input=%s", fps_policy, Path(input_path).name)
    # fps filter is always the last video filter — guarantees CFR output.
    vf_parts.append(f"fps={target_fps}")

    resolved_codec = _resolve_encoder(video_codec, encoder_mode=encoder_mode)
    resolved_preset = _map_preset_for_encoder(video_preset, resolved_codec)

    bgm_path = str(reup_bgm_path or "").strip()
    bgm_ok = reup_bgm_enable and bgm_path and Path(bgm_path).is_file()
    input_has_audio = has_audio_stream(input_path)

    ffmpeg_cmd = [
        get_ffmpeg_bin(),
        "-hide_banner", "-loglevel", "error", "-nostats", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{out_w}x{out_h}",
        "-r", str(src_fps),
        "-i", "-",
        "-i", input_path,
    ]
    if bgm_ok:
        ffmpeg_cmd += ["-stream_loop", "-1", "-i", bgm_path]
    vf_chain = ",".join(vf_parts) if vf_parts else ""
    _threads = ffmpeg_threads if ffmpeg_threads is not None else max(1, min(8, (os.cpu_count() or 4) // 2))
    codec_flags = [
        "-c:v", resolved_codec,
        "-preset", resolved_preset,
        *_codec_flags(resolved_codec, int(video_crf), video_preset),
        "-threads", str(_threads),
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-movflags", "+faststart",
    ]
    if bgm_ok:
        gain = max(0.01, min(1.0, float(reup_bgm_gain or 0.18)))
        if input_has_audio:
            # Merge video filters + audio mix into one -filter_complex graph
            fc_parts = []
            if vf_chain:
                fc_parts.append(f"[0:v]{vf_chain}[vout]")
            # Prepend loudnorm to the original audio chain when requested (not in reup mode).
            a0_chain = ("loudnorm=I=-16:LRA=11:TP=-1.5,volume=1.0"
                        if (loudnorm_enabled and not reup_mode) else "volume=1.0")
            a1_chain = f"volume={gain}"
            if abs(speed - 1.0) > 1e-4:
                a0_chain += f",atempo={speed:.4f}"
                a1_chain += f",atempo={speed:.4f}"
            fc_parts.append(f"[1:a]{a0_chain}[a0];[2:a]{a1_chain}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]")
            v_label = "[vout]" if vf_chain else "0:v:0"
            ffmpeg_cmd += ["-filter_complex", ";".join(fc_parts),
                           "-map", v_label, "-map", "[aout]"]
        else:
            if vf_chain:
                fc = f"[0:v]{vf_chain}[vout]"
                af = f"volume={gain}"
                if abs(speed - 1.0) > 1e-4:
                    af += f",atempo={speed:.4f}"
                ffmpeg_cmd += ["-filter_complex", fc,
                               "-map", "[vout]", "-map", "2:a:0",
                               "-filter:a", af, "-shortest"]
            else:
                af = f"volume={gain}"
                if abs(speed - 1.0) > 1e-4:
                    af += f",atempo={speed:.4f}"
                ffmpeg_cmd += ["-map", "0:v:0", "-map", "2:a:0",
                               "-filter:a", af, "-shortest"]
    else:
        if vf_chain:
            ffmpeg_cmd += ["-vf", vf_chain]
        ffmpeg_cmd += ["-map", "0:v:0", "-map", "1:a?"]
        if input_has_audio:
            af_parts = []
            if loudnorm_enabled and not reup_mode:
                af_parts.append("loudnorm=I=-16:LRA=11:TP=-1.5")
            if reup_mode:
                af_parts.append(_reup_audio_filter())
            if abs(speed - 1.0) > 1e-4:
                af_parts.append(f"atempo={speed:.4f}")
            if af_parts:
                ffmpeg_cmd += ["-af", ",".join(af_parts)]
    ffmpeg_cmd += [*codec_flags, "-c:a", "aac", "-b:a", audio_bitrate, "-shortest", output_path]

    attempt = 0
    while True:
        attempt += 1
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open input video: {input_path}")
        proc = None
        try:
            proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            frame_idx = 0
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break

                x, y = centers[frame_idx] if frame_idx < len(centers) else centers[-1]
                crop = frame[y:y + crop_h_src, x:x + crop_w_src]
                if crop.size == 0:
                    crop = frame

                target_w = int(round(crop.shape[1] * cfg.scale_x_percent / 100.0))
                target_h = int(round(crop.shape[0] * cfg.scale_y_percent / 100.0))
                upscale = target_w > crop.shape[1] or target_h > crop.shape[0]
                interp = cv2.INTER_CUBIC if upscale else cv2.INTER_AREA
                scaled = cv2.resize(crop, (target_w, target_h), interpolation=interp)
                sh, sw = scaled.shape[:2]
                start_x = max(0, (sw - out_w) // 2)
                start_y = max(0, (sh - out_h) // 2)
                end_x = min(sw, start_x + out_w)
                end_y = min(sh, start_y + out_h)
                final_frame = scaled[start_y:end_y, start_x:end_x]
                if final_frame.shape[1] != out_w or final_frame.shape[0] != out_h:
                    final_frame = cv2.resize(final_frame, (out_w, out_h), interpolation=cv2.INTER_CUBIC)

                if proc.stdin is None:
                    raise RuntimeError("ffmpeg stdin closed unexpectedly")
                proc.stdin.write(final_frame.tobytes())
                frame_idx += 1

            if proc.stdin:
                proc.stdin.close()
            rc = proc.wait()
            if rc != 0:
                err_tail = ""
                try:
                    if proc.stderr is not None:
                        raw = proc.stderr.read() or b""
                        err_tail = raw.decode(errors="ignore")[-2000:].strip()
                except Exception:
                    err_tail = ""
                diag = _summarize_ffmpeg_stderr(err_tail)
                raise RuntimeError(
                    f"FFmpeg render failed: {diag} (exit={rc})"
                    + (f"\n{err_tail}" if err_tail else "")
                )
            cap.release()
            break
        except BrokenPipeError:
            cap.release()
            err_tail = ""
            try:
                if proc and proc.stderr is not None:
                    raw = proc.stderr.read() or b""
                    err_tail = raw.decode(errors="ignore")[-2000:].strip()
            except Exception:
                err_tail = ""
            try:
                if proc and proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            if attempt > retry_count:
                diag = _summarize_ffmpeg_stderr(err_tail)
                raise RuntimeError(
                    f"FFmpeg render failed (broken pipe): {diag}"
                    + (f"\n{err_tail}" if err_tail else "")
                )
            time.sleep(0.8 * attempt)
            continue
        except Exception:
            cap.release()
            try:
                if proc and proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                if proc and proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            if attempt > retry_count:
                raise
            time.sleep(0.8 * attempt)

    return output_path
