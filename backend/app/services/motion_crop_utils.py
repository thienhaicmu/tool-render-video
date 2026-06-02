"""Motion-crop generic helpers — codec flags, font detection, ffprobe,
math primitives, OpenCV cascade/IoU.

Sprint 6.D-3.3 — extracted verbatim from motion_crop.py
(lines 316–459 of the pre-3.2 file, lines 227–369 of the post-3.2 file).
No logic changes; pure relocation.

Contents (preserved in original source order):
  - _codec_flags(resolved_codec, video_crf, video_preset)
    NVENC path uses VBR-HQ (motion-crop is latency-sensitive). CPU paths
    delegate to encoder_helpers.codec_extra_flags for a single source of
    truth on libx264/libx265 tuning.
  - _safe_filter_path(path) — FFmpeg filter-graph path escape.
  - _detect_windows_fontfile / _detect_windows_fonts_dir /
    _get_custom_fonts_dir — Windows + bundled-font discovery for FFmpeg
    drawtext subtitle rendering.
  - ffprobe_video_info(video_path) → (width, height, fps).
    Delegates to render_engine.probe_video_metadata() which caches
    by (abspath, mtime_ns, size_bytes). Falls back to fps=30.0.
  - has_audio_stream(video_path) → bool. Delegates to
    render_engine._has_audio_stream() (also cached).
  - clamp / ema / _smoothstep — math primitives used by EMA smoothing
    and cinematic camera easing throughout the crop-path builder.
  - _gaussian_smooth_1d(arr, window) — 1-D Gaussian convolution with
    reflect-pad for camera-path temporal smoothing.
  - _load_cascade(filename) — OpenCV Haar cascade loader (None on failure).
  - _iou_xywh(a, b) → Intersection-over-Union for two (x, y, w, h) boxes.

Public re-export contract:
  - `ffprobe_video_info`, `has_audio_stream` — used by tests/test_probe_unification.py
  - `_codec_flags` — used by tests/test_motion_crop_guards.py +
                     tests/test_render_audit_p0_fixes.py

These three plus all 10 other helpers are re-exported from
app.services.motion_crop so all existing import paths keep working.

Deferred-import note (ffprobe_video_info / has_audio_stream):
  Both helpers do a deferred `from app.services.render_engine import ...`
  inside the function body to break the render_engine ↔ motion_crop
  module-level circular dependency (render_engine imports
  render_motion_aware_crop from motion_crop at its module top). Keep
  the imports deferred — moving them to module top here would
  reintroduce the cycle.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from app.services.encoder_helpers import (
    codec_extra_flags as _codec_extra_flags_shared,
)


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
