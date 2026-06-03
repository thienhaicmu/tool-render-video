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
# Sprint 6.D-3.2: MotionCropConfig + content-type tracking overrides
# extracted to a dedicated module. Re-exported here so external consumers
# (render_engine.py, render/legacy_renderer.py) and the rest of motion_crop.py
# keep their existing import paths working unchanged.
from app.services.motion_crop_config import (
    _CONTENT_TYPE_TRACKING,
    _apply_content_type_to_cfg,
    MotionCropConfig,
)
# Sprint 6.D-3.3: generic helpers (codec flags, font detection, ffprobe,
# math primitives, OpenCV cascade/IoU) extracted to a dedicated module.
# Re-exported here so existing callers in motion_crop.py + external tests
# (test_probe_unification, test_motion_crop_guards, test_render_audit_p0_fixes)
# keep their existing import paths working unchanged.
from app.services.motion_crop_utils import (
    _codec_flags,
    _safe_filter_path,
    _detect_windows_fontfile,
    _detect_windows_fonts_dir,
    _get_custom_fonts_dir,
    ffprobe_video_info,
    has_audio_stream,
    clamp,
    ema,
    _smoothstep,
    _gaussian_smooth_1d,
    _load_cascade,
    _iou_xywh,
)
# Sprint 6.D-3.4: _ByteTrackSubject + _create_tracker extracted to a
# dedicated module. The `_TRACKER_CAPABILITY_LOGGED` flag moved with
# `_create_tracker` (it's the function's own per-process guard).
# Re-exported here so existing internal call sites (build_subject_path,
# build_subject_path_scene) keep their bare references.
from app.services.motion_crop_tracker import (
    _ByteTrackSubject,
    _create_tracker,
)
# Sprint 6.D-3.5a: MediaPipe lazy helpers + detection orchestration
# extracted to a dedicated module. The two _mp_*_initialized module flags
# and the _POSE_LEFT_EYE/RIGHT_EYE/_EYE_CROP_THIRDS constants moved with
# their owning functions. Re-exported so existing internal call sites
# (build_subject_path, build_subject_path_scene, build_motion_path) keep
# their bare references.
# Note: _pick_best_subject deferred to phase 3.5b because it depends on
# _score_subject_candidate (3.5b's scope). See motion_crop_detection
# module docstring for rationale.
from app.services.motion_crop_detection import (
    _get_mp_detector,
    _detect_mediapipe_faces,
    _has_subject_in_sample,
    _get_mp_pose,
    _get_eye_anchor_rel,
    prepare_detection_frame,
    _detect_subjects_in_frame,
)
# Sprint 6.D-3.5b: scoring helpers + best-subject pick extracted to a
# dedicated module. Includes _pick_best_subject deferred from 3.5a (its
# scoring dependency lives here). Re-exported so existing internal call
# sites (build_subject_path, build_subject_path_scene) keep their bare
# references. Note: _subject_to_crop_center is NOT moved — it's a crop
# geometry concern (velocity limiting + composition), kept in motion_crop.
from app.services.motion_crop_scoring import (
    _subject_area_ratio,
    _subject_edge_overlap_ratio,
    _is_plausible_subject,
    _filter_subject_candidates,
    _pick_best_subject,
    _subject_center,
    _score_subject_candidate,
    _same_subject,
)
# Sprint 6.D-3.5c: trackerless guard helpers extracted to a dedicated
# module. The new module imports its dependencies directly from
# motion_crop_scoring + motion_crop_utils to avoid a load-time cycle
# (motion_crop.py imports trackerless at its top, so this module
# cannot import-back through motion_crop). Re-exported so existing
# internal call sites keep their bare references.
from app.services.motion_crop_trackerless import (
    _trackerless_offcenter_ratio,
    _trackerless_detection_confidence,
    _trackerless_hold_frames_for_confidence,
    _trackerless_crop_side_fill_ratio,
    _apply_trackerless_center_guard,
)
# Sprint 6.D-3.7: legacy motion-path implementation extracted to a
# dedicated module. The `build_motion_path` dispatcher stays in this
# file because it routes between build_subject_path (here) and
# _build_motion_path_legacy (there) — keeping it here avoids a
# load-time cycle. Re-exported so existing call sites
# (build_motion_path dispatcher, render_motion_aware_crop,
# build_subject_path_scene fallback) keep their bare references.
from app.services.motion_crop_legacy import (
    detect_motion_center,
    _build_motion_path_legacy,
    _detect_scene_ranges_in_clip,
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
# `_TRACKER_CAPABILITY_LOGGED` moved to motion_crop_tracker.py with
# _create_tracker (Sprint 6.D-3.4) — it's the function's per-process guard.

# Sprint 6.D-3.5a: MediaPipe face block (_get_mp_detector,
# _detect_mediapipe_faces, _has_subject_in_sample) + MediaPipe pose block
# (_get_mp_pose, _get_eye_anchor_rel) + per-process state flags
# (_mp_face_detector*, _mp_pose_detector*, _POSE_LEFT_EYE/RIGHT_EYE,
# _EYE_CROP_THIRDS) → moved to app.services.motion_crop_detection.
# Re-exported at the top of this file so existing internal call sites
# keep their bare references unchanged.


# `_CONTENT_TYPE_TRACKING`, `_apply_content_type_to_cfg`, and `MotionCropConfig`
# → moved to app.services.motion_crop_config (Sprint 6.D-3.2). Re-exported
# at the top of this file so the rest of motion_crop.py and external consumers
# keep using them via `app.services.motion_crop` import paths.


# Sprint 6.D-3.3: 13 generic helpers (codec flags, fonts, ffprobe, math,
# cascade/IoU) → moved to app.services.motion_crop_utils. Re-exported at
# the top of this file so existing callers in this module + tests keep
# their import paths.


# ---------------------------------------------------------------------------
# CapCut-style Auto Reframe: Subject detection & tracking
# ---------------------------------------------------------------------------

# Sprint 6.D-3.4: `_ByteTrackSubject` + `_create_tracker` → moved to
# app.services.motion_crop_tracker. Re-exported at the top of this file
# so existing internal call sites (build_subject_path,
# build_subject_path_scene) keep using them via bare references.


def _sanitize_speed(playback_speed: float | int | None) -> float:
    try:
        v = float(playback_speed or 1.0)
    except Exception:
        v = 1.0
    return max(0.5, min(1.5, v))


# `_subject_area_ratio` + `_subject_edge_overlap_ratio` → moved to
# app.services.motion_crop_scoring (Sprint 6.D-3.5b).


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


# Sprint 6.D-3.5c: 5 trackerless guard helpers → moved to
# app.services.motion_crop_trackerless. Re-exported at top of this file.


# Sprint 6.D-3.5b: _is_plausible_subject, _filter_subject_candidates,
# _pick_best_subject (deferred from 3.5a), _subject_center,
# _score_subject_candidate, _same_subject → moved to
# app.services.motion_crop_scoring. Re-exported at top of this file.
# `prepare_detection_frame` + `_detect_subjects_in_frame` were moved to
# motion_crop_detection in Sprint 6.D-3.5a.


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


# Sprint 6.D-3.7: detect_motion_center, _build_motion_path_legacy,
# _detect_scene_ranges_in_clip → moved to app.services.motion_crop_legacy.
# Re-exported at top of this file. build_motion_path dispatcher stays
# here because it routes to build_subject_path (also here).


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
