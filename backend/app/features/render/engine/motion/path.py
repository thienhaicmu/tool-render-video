"""Motion-crop subject-path entry point — CapCut-style Auto Reframe.

Sprint 5.2 split (from 977-LOC path.py):
  - build_subject_path stays here (~340 LOC including the multi-scene
    dispatch loop). This is the public entry surface reached through
    `app.services.motion_crop.build_subject_path`.
  - build_subject_path_scene moved to path_scene.py (~530 LOC). The
    per-scene state machine had no clean interior seam, so it ships
    as a single file rather than further sub-modules.

Historical lineage (preserved from Sprint 6.D-3.6a):
  build_subject_path is the CapCut Auto Reframe equivalent. Every
  cfg.subject_detect_interval frames it runs face → body detection on
  a half-size frame; between detections a CSRT tracker plus
  _ByteTrackSubject (velocity-predicted IoU gate) keeps the lock.
  Raw (cx, cy) → Gaussian smooth → velocity limit. Falls back to
  _build_motion_path_legacy when no subject is ever found and
  cfg.motion_fallback is True.

  Multi-scene dispatch: when _scene_ranges has 2+ ranges, this iterates
  build_subject_path_scene per range, carrying the last visible crop
  center forward as warmup_center to avoid snapping back to frame
  center at scene boundaries.

Deferred-import strategy (unchanged from 6.D-3.6a):
  _subject_to_crop_center, _apply_velocity_limiter,
  _required_lock_confirm_frames, build_subject_path_scene are imported
  via `from app.features.render.engine.motion import ...` inside the function
  body. The package __init__ re-exports build_subject_path_scene from
  path_scene.py, so the deferred lookup keeps working across the split.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.features.render.engine.motion.config import MotionCropConfig, _apply_content_type_to_cfg
from app.features.render.engine.motion.utils import (
    clamp,
    _load_cascade,
    _gaussian_smooth_1d,
)
from app.features.render.engine.motion.tracker import _ByteTrackSubject, _create_tracker
from app.features.render.engine.motion.detection import (
    prepare_detection_frame,
    _detect_subjects_in_frame,
    _get_eye_anchor_rel,
)
from app.features.render.engine.motion.scoring import (
    _filter_subject_candidates,
    _pick_best_subject,
    _same_subject,
)
from app.features.render.engine.motion.trackerless import (
    _trackerless_detection_confidence,
    _trackerless_offcenter_ratio,
    _apply_trackerless_center_guard,
)
from app.features.render.engine.motion.pixel_diff import _build_motion_path_legacy
# T2.2 — Audit 2026-06-08 closure (Batch A V9-F3). Lightweight cancel
# poll for OpenCV per-frame loops. No-op on threads with no registered
# cancel event so direct test calls into this module are unaffected.
from app.features.render.engine.encoder.ffmpeg_helpers import check_thread_cancel

logger = logging.getLogger("app.services.motion_crop")


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
       half-size frame (4Ã— faster), pick the best subject.
    2. Between detections: use CSRT tracker (fast, robust to occlusion).
    3. If tracker drifts or loses target, re-detect on next interval.
    4. Build raw (cx, cy) path, apply Gaussian smoothing, then velocity limit.

    Falls back to legacy motion mode if no subject is ever detected and
    `cfg.motion_fallback` is True.
    """
    # Deferred imports break the load-time cycle with motion_crop.py.
    # Resolution cost is amortized over the entire per-frame loop.
    from app.features.render.engine.motion import (
        _subject_to_crop_center,
        _apply_velocity_limiter,
        _required_lock_confirm_frames,
        build_subject_path_scene,
    )

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
        # T2.2 — Audit 2026-06-08 closure (Batch A V9-F3). Cancel poll
        # at the top of each frame iteration. check_thread_cancel raises
        # JobCancelledError when the operator clicks Cancel; the
        # exception propagates up to _common.process_render where it is
        # caught and turned into status=CANCELLED. On the raise path
        # `cap` is released by OpenCV's __del__ + Python GC (the
        # explicit cap.release() after the loop is skipped on cancel).
        check_thread_cancel()
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

