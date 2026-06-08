"""Motion-crop pixel-diff path — frame-pair pixel-difference motion
tracking + scene-cut detection. Used as the fallback path when the
subject-tracker pipeline cannot find or hold a subject lock.

Sprint 7.1 (2026-06-05) — renamed from ``legacy.py`` to
``motion_pixel_diff.py``. The "legacy" name historically misled
auditors into thinking the module was dead code (it is NOT — three
live render-path callers depend on it; see
``docs/review/SPRINT_7_1_MOTION_RENAME_2026-06-05.md`` and
``docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md`` Â§4).
File contents unchanged — pure rename + comment refresh.

Sprint 6.D-3.7 — extracted verbatim from motion_crop.py
(lines 1162-1363 of the post-3.5c file). No logic changes; pure relocation.

Contents (preserved in original source order):

  detect_motion_center(prev_gray, gray, frame_width, frame_height, cfg)
    Frame-pair motion centroid via cv2.absdiff → threshold →
    Gaussian blur → dilate → contours. Weighted by area + center
    preference (cfg.prefer_center_bias). Returns frame center when
    no motion contour exceeds cfg.min_contour_area_ratio.

  _build_motion_path_legacy(video_path, crop_w, crop_h, cfg)
    Full-video pixel-diff motion tracker (legacy fallback).
    Per-frame: detect_motion_center → dead-zone gate → EMA-smoothed
    target → pan-speed clamp → pan-accel clamp. Then two post-passes:
    temporal smoothing window (cfg.temporal_smooth_window), and
    jerk limiter (max_step = src_w * 0.006, max_accel = src_w * 0.0022).
    Returns (list of (x, y) top-left tuples, fps).

  _detect_scene_ranges_in_clip(video_path, cfg)
    Per-clip scene-cut detection by downsampled-frame absdiff vs
    cfg.scene_cut_threshold. Sampled at fps/6 cadence with 0.35-second
    minimum gap between consecutive cuts. Returns
    [(start_sec, end_sec)] ranges covering the clip duration.

Out of scope (stays in motion_crop.py):
  build_motion_path() dispatcher routes between subject-mode (calls
  build_subject_path, which stays in motion_crop) and motion-mode
  (calls _build_motion_path_legacy here). Keeping the dispatcher in
  motion_crop.py avoids a load-time cycle (this module would otherwise
  need to import_back build_subject_path from motion_crop, which
  hasn't finished loading when this module is parsed).

Internal-only — no external imports of these 3 symbols today. The
module is re-exported from motion_crop/__init__.py so existing
internal call sites (build_motion_path dispatcher,
render_motion_aware_crop, build_subject_path_scene fallback) keep
their bare references.

Dependency-import strategy (same pattern as 6.D-3.5c):
  Imports MotionCropConfig from motion_crop_config and clamp/ema from
  motion_crop_utils **directly** — not via motion_crop, which would
  hit a load-time cycle.
"""
from __future__ import annotations

import math
from typing import List, Tuple

import cv2
import numpy as np

from app.features.render.engine.motion.config import MotionCropConfig
from app.features.render.engine.motion.utils import clamp, ema
# T2.2 — Audit 2026-06-08 closure (Batch A V9-F3): cancel poll for the
# pixel-diff fallback loops. See engine/encoder/ffmpeg_helpers.py.
from app.features.render.engine.encoder.ffmpeg_helpers import check_thread_cancel


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
        # T2.2 — cancel poll for the pixel-diff motion-tracking loop.
        check_thread_cancel()
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
            # T2.2 — cancel poll for the scene-cut detection loop.
            check_thread_cancel()
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

