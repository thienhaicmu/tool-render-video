"""Motion-crop trackerless guard — confidence scoring + center-guard
clamping for the no-tracker (detection-only) path.

Sprint 6.D-3.5c — extracted verbatim from motion_crop.py
(lines 183-296 of the post-3.5b file). No logic changes; pure relocation.

When OpenCV trackers are unavailable (or skipped by config), the
reframe pipeline relies on per-frame detections alone. Without
inter-frame state, the crop center can jitter or drift towards
spurious detections. This module provides the safety net:

  _trackerless_offcenter_ratio(subject, frame_w, crop_w)
    Subject center distance from frame center as a fraction of the
    pan half-range. 0 = centered, 1 = at the pan limit.

  _trackerless_detection_confidence(subject, frame_w, frame_h, crop_w,
                                    subject_kind, previous_subject,
                                    confirm_count)
    Composite [0, 1] confidence score blending: kind base (face > body
    > other), confirm_count (saturates at 3), area-ratio sweet spot
    (0.02-0.12), offcenter penalty, edge-overlap penalty,
    same-as-previous bonus, plus penalties for extreme offcenter/edge.

  _trackerless_hold_frames_for_confidence(base_hold_frames, confidence)
    Reduce hold-frame budget when confidence is low. <0.55 → −4 frames
    (floor 3), <0.78 → −2 frames (floor 4), else base.

  _trackerless_crop_side_fill_ratio(target_cx, frame_w, crop_w,
                                    band_ratio=0.28)
    Fraction of the crop window that overlaps the left or right
    edge band of the source frame. Used to detect crops that would
    fill with mostly background.

  _apply_trackerless_center_guard(target_cx, default_cx, frame_w,
                                  crop_w, confidence_score, stable_count)
    Clamp how far the trackerless target can deviate from the default
    (typically frame-centered) crop center. Stricter clamps at low
    confidence; further tightened by edge-fill detection. Returns
    (final_cx, was_guarded, reason). Reason strings:
      "none", "weak_trackerless_guard", "medium_trackerless_guard",
      "edge_fill_guard".

Internal-only — no external imports of these 5 symbols today. The
module is re-exported from motion_crop.py so existing internal call
sites (build_subject_path, build_subject_path_scene) keep their bare
references unchanged.

Dependency-import note:
  Imports `_subject_*`, `_same_subject` from motion_crop_scoring and
  `clamp` from motion_crop_utils directly — not via motion_crop, which
  would create a load-time cycle (motion_crop.py imports this module
  at its top, so motion_crop hasn't finished loading yet when we run).
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

from app.services.motion_crop_utils import clamp
from app.services.motion_crop_scoring import (
    _subject_center,
    _subject_area_ratio,
    _subject_edge_overlap_ratio,
    _same_subject,
)


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
