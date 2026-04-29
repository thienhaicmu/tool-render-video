from __future__ import annotations

import math
import os
import subprocess
import time
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin, _summarize_ffmpeg_stderr
from app.services.text_overlay import append_text_layer_filters

logger = logging.getLogger(__name__)

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
    ema_alpha_fast: float = 0.35
    lookahead_frames: int = 4
    lost_subject_hold_frames: int = 18

    # --- Smoothing ---
    # Gaussian window size for the crop path (larger = smoother, less reactive)
    temporal_smooth_window: int = 31

    # Max camera pan speed (fraction of frame width per frame)
    max_pan_speed_ratio: float = 0.015

    # Max camera pan acceleration per frame
    max_pan_accel_ratio: float = 0.0045

    # Dead zone – ignore subject shifts smaller than this fraction of crop size
    dead_zone_ratio: float = 0.04

    # --- Legacy motion-mode settings (used when reframe_mode="motion") ---
    sample_every_n_frames: int = 1
    smooth_alpha: float = 0.10
    motion_threshold: int = 18
    min_contour_area_ratio: float = 0.002
    prefer_center_bias: float = 0.15

    fps_fallback: float = 30.0


# ---------------------------------------------------------------------------
# Encoder helpers (unchanged)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _ffmpeg_encoders_text() -> str:
    try:
        ffmpeg_bin = get_ffmpeg_bin()
        r = subprocess.run([ffmpeg_bin, "-hide_banner", "-encoders"], capture_output=True, text=True, check=True)
        return (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception:
        return ""


def _has_encoder(name: str) -> bool:
    return name in _ffmpeg_encoders_text()


@lru_cache(maxsize=2)
def _nvenc_runtime_ready(codec_name: str) -> bool:
    try:
        ffmpeg_bin = get_ffmpeg_bin()
        probe_cmd = [
            ffmpeg_bin, "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=16x16:d=0.1",
            "-an", "-c:v", codec_name, "-f", "null", "-",
        ]
        proc = subprocess.run(probe_cmd, capture_output=True, text=True)
        text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).lower()
        if proc.returncode == 0:
            return True
        blockers = (
            "cannot load nvcuda.dll",
            "no nvenc capable devices found",
            "cannot init cuda",
            "operation not permitted",
        )
        return not any(b in text for b in blockers)
    except Exception:
        return False


def _resolve_encoder(video_codec: str, encoder_mode: str = "auto") -> str:
    codec = (video_codec or "h264").lower()
    mode = (encoder_mode or "auto").lower()
    if mode in ("auto", "nvenc"):
        if codec == "h265" and _has_encoder("hevc_nvenc") and _nvenc_runtime_ready("hevc_nvenc"):
            return "hevc_nvenc"
        if codec != "h265" and _has_encoder("h264_nvenc") and _nvenc_runtime_ready("h264_nvenc"):
            return "h264_nvenc"
    if codec == "h265":
        return "libx265"
    return "libx264"


def _map_preset_for_encoder(video_preset: str, resolved_codec: str) -> str:
    p = (video_preset or "slow").lower()
    if resolved_codec in ("h264_nvenc", "hevc_nvenc"):
        mapping = {
            "ultrafast": "p2", "superfast": "p3", "veryfast": "p4",
            "faster": "p4", "fast": "p4", "medium": "p5",
            "slow": "p6", "slower": "p7", "veryslow": "p7",
        }
        return mapping.get(p, "p6")
    return p


def _codec_flags(resolved_codec: str, video_crf: int, video_preset: str = "slow") -> list[str]:
    p = (video_preset or "slow").lower()
    if resolved_codec in ("h264_nvenc", "hevc_nvenc"):
        return [
            "-rc", "vbr_hq", "-cq", str(video_crf), "-b:v", "0",
            "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
            "-rc-lookahead", "32", "-bf", "3",
        ]
    if resolved_codec == "libx265":
        if p in ("veryslow", "slower"):
            x265p = "aq-mode=3:aq-strength=1.0:deblock=-1,-1:rc-lookahead=60:ref=5:bframes=4:psy-rdoq=1.0:rdoq-level=2"
        elif p == "slow":
            x265p = "aq-mode=3:aq-strength=0.8:deblock=-1,-1:rc-lookahead=40:ref=4:bframes=4"
        else:
            x265p = "aq-mode=2:rc-lookahead=20:ref=3:bframes=3"
        return ["-crf", str(video_crf), "-tag:v", "hvc1", "-x265-params", x265p]

    # libx264 — tiered by preset
    if p in ("veryslow", "slower"):
        x264p = "ref=5:bframes=3:me=umh:subme=9:analyse=all:trellis=2:deblock=-1,-1:aq-mode=3:aq-strength=0.8:psy-rd=1.0:psy-rdoq=0.0"
    elif p == "slow":
        x264p = "ref=4:bframes=3:me=hex:subme=7:trellis=1:deblock=-1,-1:aq-mode=3:aq-strength=0.8:psy-rd=1.0"
    else:
        x264p = "ref=3:bframes=2:me=hex:subme=6:trellis=0:aq-mode=2"
    return [
        "-crf", str(video_crf),
        "-profile:v", "high", "-level:v", "5.1",
        "-tune", "film",
        "-x264-params", x264p,
    ]


def _reup_video_filters() -> list[str]:
    return [
        "eq=contrast=1.04:saturation=1.10:brightness=0.01",
        "unsharp=5:5:0.45:3:3:0.0",
        "hqdn3d=1.2:1.2:6:6",
    ]


def _reup_audio_filter() -> str:
    return (
        "highpass=f=120,"
        "lowpass=f=11000,"
        "acompressor=threshold=-16dB:ratio=2.2:attack=20:release=200:makeup=2,"
        "alimiter=limit=0.95"
    )


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
    """Return (width, height, fps) via ffprobe.

    Probes avg_frame_rate (actual cadence) and r_frame_rate (container-declared
    max).  avg_frame_rate is preferred for accuracy with VFR content.
    Falls back to 30.0 if both probes fail or are out of the sane [1, 120] range.
    """
    def _parse(s: str) -> float:
        s = (s or "").strip()
        if "/" in s:
            try:
                a, b = s.split("/", 1)
                return float(a) / float(b) if float(b) else 0.0
            except (ValueError, ZeroDivisionError):
                return 0.0
        try:
            return float(s) if s else 0.0
        except ValueError:
            return 0.0

    cmd = [
        get_ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
        "-of", "default=noprint_wrappers=1:nokey=1", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = [x.strip() for x in result.stdout.splitlines() if x.strip()]
    width  = int(lines[0])
    height = int(lines[1])
    avg_fps = _parse(lines[2]) if len(lines) > 2 else 0.0
    r_fps   = _parse(lines[3]) if len(lines) > 3 else 0.0
    fps = 30.0
    for candidate in (avg_fps, r_fps):
        if 1.0 <= candidate <= 120.0:
            fps = candidate
            break
    return width, height, fps


def has_audio_stream(video_path: str) -> bool:
    cmd = [
        get_ffprobe_bin(), "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=index", "-of", "csv=p=0", video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return bool((result.stdout or "").strip())
    except Exception:
        return False


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


def _create_tracker():
    """Create fast available OpenCV tracker (KCF > CSRT > MOSSE)."""
    for factory in (
        lambda: cv2.TrackerKCF_create(),
        lambda: cv2.TrackerCSRT_create(),
        lambda: cv2.TrackerMOSSE_create(),
    ):
        try:
            return factory()
        except AttributeError:
            continue
    return None


def _sanitize_speed(playback_speed: float | int | None) -> float:
    try:
        v = float(playback_speed or 1.0)
    except Exception:
        v = 1.0
    return max(0.5, min(1.5, v))


def _detect_subjects_in_frame(
    gray_small: np.ndarray,
    face_cascade: Optional[cv2.CascadeClassifier],
    body_cascade: Optional[cv2.CascadeClassifier],
    scale: float,
) -> Tuple[List[Tuple[int, int, int, int]], str]:
    """
    Detect faces first, then bodies as fallback.
    Returns (list of (x,y,w,h) in original-frame coords, kind).
    """
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
) -> Tuple[float, float]:
    """
    Convert a subject bounding box to the desired crop-window center.
    Uses a slight upward bias so the face sits in the upper portion
    of the crop, leaving room for text/chin — just like CapCut.
    """
    x, y, w, h = subject
    # Face: focus on center-top; body: focus on full center
    cx = x + w / 2.0
    if subject_kind == "body":
        cy = y + h * 0.34
    else:
        cy = y + h * 0.34

    subject_ratio = (w * h) / max(1.0, float(frame_w * frame_h))
    if subject_ratio > 0.18:
        cx = cx * 0.55 + (frame_w / 2.0) * 0.45
        cy = cy * 0.70 + (frame_h * 0.42) * 0.30
    elif subject_ratio < 0.035:
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

        for index, (start_sec, end_sec) in enumerate(_scene_ranges):
            fallback_used = False
            try:
                scene_centers, fps = build_subject_path_scene(
                    video_path, crop_w, crop_h, cfg, start_sec, end_sec, scene_index=index
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
            all_centers.extend(scene_centers)

        return all_centers, fps

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

    default_cx = src_w / 2.0
    default_cy = src_h / 2.0

    tracker = _create_tracker()
    tracking = False
    last_subject: Optional[Tuple[int, int, int, int]] = None
    subjects_found_total = 0

    raw_centers: List[Tuple[float, float]] = []
    frame_idx = 0
    detect_interval = max(1, cfg.subject_detect_interval)

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        subject: Optional[Tuple[int, int, int, int]] = None

        # --- Step 1: update tracker ---
        if tracking and tracker is not None:
            ok_track, bbox = tracker.update(frame)
            if ok_track:
                x, y, w, h = [int(v) for v in bbox]
                # Sanity-check: reject obviously degenerate boxes
                if w > 4 and h > 4 and x >= 0 and y >= 0:
                    subject = (x, y, w, h)
                    last_subject = subject
                else:
                    tracking = False
            else:
                tracking = False

        # --- Step 2: re-detect every N frames (or when tracker lost) ---
        if frame_idx % detect_interval == 0 or not tracking:
            small = cv2.resize(frame, None, fx=detect_scale, fy=detect_scale)
            gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            detected, _kind = _detect_subjects_in_frame(
                gray_small, face_cascade, body_cascade, detect_scale
            )
            best = _pick_best_subject(detected, src_w, src_h)

            if best is not None:
                subjects_found_total += 1
                # Re-init tracker on detected subject
                if tracker is not None:
                    bx, by, bw, bh = best
                    tracker.init(frame, (bx, by, bw, bh))
                    tracking = True
                subject = best
                last_subject = best

        # --- Step 3: compute crop center ---
        if subject is not None:
            cx, cy = _subject_to_crop_center(
                subject, crop_w, crop_h, src_w, src_h, cfg.subject_padding,
                cfg.subtitle_safe_bottom_ratio
            )
        elif last_subject is not None:
            # Hold last known subject position (subject momentarily occluded)
            cx, cy = _subject_to_crop_center(
                last_subject, crop_w, crop_h, src_w, src_h, cfg.subject_padding,
                cfg.subtitle_safe_bottom_ratio
            )
        else:
            cx, cy = default_cx, default_cy

        raw_centers.append((cx, cy))
        frame_idx += 1

    cap.release()

    # If we never found a subject and fallback is enabled, use legacy motion
    if subjects_found_total == 0 and cfg.motion_fallback:
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
) -> Tuple[List[Tuple[int, int]], float]:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    try:
        face_cascade = _load_cascade("haarcascade_frontalface_default.xml")
        body_cascade = _load_cascade("haarcascade_fullbody.xml") if cfg.use_body_fallback else None

        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or cfg.fps_fallback
        start_frame = max(0, int(round(start_sec * fps)))
        end_frame = max(start_frame, int(round(end_sec * fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        detect_scale = 0.30
        default_cx = src_w / 2.0
        default_cy = src_h / 2.0

        tracker = _create_tracker()
        tracking = False
        locked_subject: Optional[Tuple[int, int, int, int]] = None
        locked_kind = "none"
        pending_subject: Optional[Tuple[int, int, int, int]] = None
        pending_count = 0
        switch_count = 0
        switch_cooldown = 0   # frames remaining in post-switch easing window
        lost_frames = 0
        last_good_center = (default_cx, default_cy)
        raw_centers: List[Tuple[float, float]] = []
        detect_interval = max(1, cfg.subject_detect_interval)
        dead_zone_x = crop_w * cfg.dead_zone_ratio
        dead_zone_y = crop_h * cfg.dead_zone_ratio
        smooth_cx = default_cx
        smooth_cy = default_cy
        frame_idx = start_frame
        motion_total = 0.0
        motion_samples = 0

        while frame_idx < end_frame:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            subject: Optional[Tuple[int, int, int, int]] = None

            if tracking and tracker is not None:
                ok_track, bbox = tracker.update(frame)
                if ok_track:
                    x, y, w, h = [int(v) for v in bbox]
                    if w > 4 and h > 4 and x >= 0 and y >= 0:
                        subject = (x, y, w, h)
                        locked_subject = subject
                        lost_frames = 0
                    else:
                        tracking = False
                else:
                    tracking = False

            scene_frame_idx = frame_idx - start_frame
            should_detect = scene_frame_idx % detect_interval == 0 or not tracking
            if should_detect:
                small = cv2.resize(frame, None, fx=detect_scale, fy=detect_scale)
                gray_small = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                detected, detected_kind = _detect_subjects_in_frame(
                    gray_small, face_cascade, body_cascade, detect_scale
                )
                best = _pick_best_subject(detected, src_w, src_h, locked_subject)

                if best is not None:
                    if locked_subject is None:
                        locked_subject = best
                        locked_kind = detected_kind
                        subject = best
                        lost_frames = 0
                        pending_subject = None
                        pending_count = 0
                    elif _same_subject(locked_subject, best):
                        locked_subject = best
                        locked_kind = detected_kind
                        subject = best
                        lost_frames = 0
                        pending_subject = None
                        pending_count = 0
                    else:
                        current_score = _score_subject_candidate(locked_subject, src_w, src_h, locked_subject)
                        new_score = _score_subject_candidate(best, src_w, src_h, locked_subject)
                        if new_score >= current_score * cfg.subject_switch_margin:
                            if _same_subject(pending_subject, best):
                                pending_count += 1
                            else:
                                pending_subject = best
                                pending_count = 1

                            if pending_count >= max(1, cfg.subject_switch_confirm_frames):
                                locked_subject = best
                                locked_kind = detected_kind
                                subject = best
                                switch_count += 1
                                lost_frames = 0
                                pending_subject = None
                                pending_count = 0
                                # Activate easing window: camera pans toward new subject
                                # without dead-zone suppression for ~0.5 s.
                                switch_cooldown = max(4, int(fps * 0.5))
                        else:
                            pending_subject = None
                            pending_count = 0

                    if subject is None and tracking:
                        subject = locked_subject

                    if subject is not None and tracker is not None:
                        bx, by, bw, bh = subject
                        tracker = _create_tracker()
                        if tracker is not None:
                            tracker.init(frame, (bx, by, bw, bh))
                            tracking = True

            if subject is None and locked_subject is not None:
                if tracking:
                    subject = locked_subject
                else:
                    lost_frames += 1

            if subject is not None:
                target_cx, target_cy = _subject_to_crop_center(
                    subject, crop_w, crop_h, src_w, src_h, cfg.subject_padding,
                    cfg.subtitle_safe_bottom_ratio, locked_kind
                )
                last_good_center = (target_cx, target_cy)
            elif lost_frames <= cfg.lost_subject_hold_frames:
                target_cx, target_cy = last_good_center
            else:
                # Smoothstep return: slow start → faster mid → soft landing at center.
                # Ramps over 1.0 s instead of 0.75 s to feel less abrupt.
                t_return = min(1.0, (lost_frames - cfg.lost_subject_hold_frames) / max(1.0, fps * 1.0))
                return_alpha = _smoothstep(t_return) * 0.10  # max alpha 0.10
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
            if switch_cooldown > 0:
                switch_cooldown -= 1
                alpha = max(alpha, cfg.ema_alpha_normal)
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

        # Adaptive Gaussian window: micro-jitter cleanup only.
        # High-motion scenes need maximum responsiveness (window=5);
        # static/talking-head scenes benefit from a slightly wider smooth (window=9).
        # Hard cap at 9 — EMA already handled coarse smoothing frame-by-frame.
        if avg_motion > 2.0:
            scene_gaussian_window = 5
        elif avg_motion > 0.5:
            scene_gaussian_window = 7
        else:
            scene_gaussian_window = 9
        scene_gaussian_window = max(3, min(scene_gaussian_window, 9) | 1)

        xs = np.array([c[0] for c in raw_centers], dtype=float)
        ys = np.array([c[1] for c in raw_centers], dtype=float)
        xs = _gaussian_smooth_1d(xs, scene_gaussian_window)
        ys = _gaussian_smooth_1d(ys, scene_gaussian_window)
        smoothed = list(zip(xs.tolist(), ys.tolist()))

        strategy = "subject_lock" if locked_subject is not None else "center_hold"
        logger.info(
            "motion_crop scene=%d strategy=%s locked=%s switches=%d "
            "avg_motion=%.2f gauss_window=%d subtitle_safe=%.3f",
            scene_index,
            strategy,
            bool(locked_subject),
            switch_count,
            avg_motion,
            scene_gaussian_window,
            cfg.subtitle_safe_bottom_ratio,
        )

        return _apply_velocity_limiter(smoothed, src_w, src_h, crop_w, crop_h, cfg), fps
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
) -> Tuple[List[Tuple[int, int]], float]:
    """
    Route to the appropriate tracking algorithm based on cfg.reframe_mode.

    - "subject" (default): CapCut-style face/body detection + CSRT tracker
    - "motion":            legacy pixel-diff motion tracking
    """
    if cfg.reframe_mode == "subject":
        return build_subject_path(video_path, crop_w, crop_h, cfg, _scene_ranges=_scene_ranges)
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
) -> str:
    layer_count = len(text_layers or [])
    if layer_count:
        logger.info("Applying %d text overlay layer(s) in motion-aware pipeline", layer_count)
    cfg = cfg or MotionCropConfig(scale_x_percent=scale_x_percent, scale_y_percent=scale_y_percent)
    if subtitle_safe_bottom_ratio is not None:
        cfg.subtitle_safe_bottom_ratio = max(0.0, min(0.35, float(subtitle_safe_bottom_ratio)))

    src_w, src_h, probe_fps = ffprobe_video_info(input_path)

    if aspect_ratio == "1:1":
        out_w, out_h = 1080, 1080
    elif aspect_ratio == "9:16":
        out_w, out_h = 1080, 1920
    else:
        out_w, out_h = cfg.output_width, cfg.output_height

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

    centers, detected_fps = build_motion_path(
        input_path,
        crop_w_src,
        crop_h_src,
        cfg,
        _scene_ranges=scene_ranges,
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
