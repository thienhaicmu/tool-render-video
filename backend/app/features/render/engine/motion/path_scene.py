"""Per-scene subject-path state machine â€” CapCut-style Auto Reframe.

Sprint 5.2 split from path.py (was 977 LOC). This module owns
build_subject_path_scene; the multi-scene dispatcher remains in path.py.

build_subject_path_scene operates only on the [start_sec, end_sec] frame
range of a single scene. Carries warmup_center (final crop center from
the previous scene) into smooth_cx/smooth_cy so the camera doesn't snap
back to frame center at scene boundaries. Subject identity is NOT
carried across scenes â€” each scene re-locks independently.

State machine per frame:
  predict (_ByteTrackSubject) â†’ tracker.update â†’ re-detect every
  detect_interval frames â†’ confirm lock (with trackerless confidence
  gating when no tracker) â†’ switch-subject arbitration
  (cfg.subject_switch_margin) â†’ eye-anchor refinement â†’ EMA smoothing
  (with dead-zone gating + post-switch cooldown) â†’ safety clamping â†’
  lookahead pass â†’ adaptive Gaussian smoothing (window scales with
  avg_motion + scene length) â†’ velocity limiter.

Deferred-import strategy:
  _subject_to_crop_center, _apply_velocity_limiter,
  _required_lock_confirm_frames, _untracked_hold_frames live in
  motion_crop/__init__.py. Imported lazily inside the function body
  to break the load-time cycle (motion_crop package imports this
  module at load-time via path.py + the __init__ re-export).
"""
from __future__ import annotations

import logging
import math
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

from app.features.render.engine.motion.config import MotionCropConfig, _apply_content_type_to_cfg
from app.features.render.engine.motion.utils import (
    clamp,
    ema,
    _smoothstep,
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
    _score_subject_candidate,
)
from app.features.render.engine.motion.trackerless import (
    _trackerless_detection_confidence,
    _trackerless_offcenter_ratio,
    _apply_trackerless_center_guard,
    _trackerless_hold_frames_for_confidence,
)

logger = logging.getLogger("app.services.motion_crop")


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
    # Deferred imports break the load-time cycle with motion_crop.py.
    # Same pattern as build_subject_path in path.py.
    from app.features.render.engine.motion import (
        _subject_to_crop_center,
        _apply_velocity_limiter,
        _required_lock_confirm_frames,
        _untracked_hold_frames,
    )

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
                # Smoothstep return: slow start â†’ faster mid â†’ soft landing at center.
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
        # to the next scene â€” enables scene-boundary camera continuity.
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

