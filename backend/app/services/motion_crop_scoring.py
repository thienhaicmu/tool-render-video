"""Motion-crop subject scoring + plausibility filtering + best-subject pick.

Sprint 6.D-3.5b — extracted verbatim from motion_crop.py
(lines 141-158, 299-393, 396-442 of the post-3.5a file). No logic
changes; pure relocation.

Contents (preserved in original source order):

  Geometric ratio primitives (used by scorers and filters):
    _subject_area_ratio(subject, frame_w, frame_h) → [0, 1]
        subject_box_area / total_frame_area.
    _subject_edge_overlap_ratio(subject, frame_w, edge_ratio=0.10)
        Fraction of subject width that overlaps the left/right edge bands.

  Plausibility filtering (drop subjects unlikely to be the framing target):
    _is_plausible_subject(subject, frame_w, frame_h, subject_kind, previous_subject)
        Per-kind heuristics for "face" vs "body" — area, aspect, vertical
        position, edge overlap, center offset. Returns True/False.
        Treats same-as-previous subjects as automatically plausible to
        avoid tracker thrashing across frames.
    _filter_subject_candidates(subjects, frame_w, frame_h, kind, previous)
        Returns (kept_list, rejected_count).

  Best-subject selection (was scheduled for 3.5a in the original plan;
  deferred here to keep _score_subject_candidate in the same module
  and avoid a load-time cycle):
    _pick_best_subject(subjects, frame_w, frame_h, previous_subject)
        Iterates _score_subject_candidate over candidates, returns the
        highest-scoring one (or None when subjects is empty).

  Center primitive:
    _subject_center(subject) → (cx, cy) float tuple.

  Scoring function:
    _score_subject_candidate(subject, frame_w, frame_h, previous_subject)
        Weighted sum of area_score (×1.2), center_score (×0.9),
        edge_score (×0.6), stability_score (×1.0).

  Cross-frame identity check:
    _same_subject(a, b)
        Distance-based identity test: same subject if center distance
        ≤ max(24px, max(a.w, a.h, b.w, b.h) × 0.75).

Internal-only — no external imports of these 8 symbols today. The module
is re-exported from motion_crop.py so existing internal call sites
(build_subject_path, build_subject_path_scene) keep their bare
references unchanged.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple


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
