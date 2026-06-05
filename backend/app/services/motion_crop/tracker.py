"""Motion-crop subject tracker — Kalman-inspired single-target tracker
plus OpenCV tracker factory with KCF → CSRT → MOSSE fallback chain.

Sprint 6.D-3.4 — extracted verbatim from motion_crop.py
(lines 257-348 of the post-3.3 file, originally lines 461-553 of the
pre-Sprint-6.D file). No logic changes; pure relocation.

Contents:
  - `_ByteTrackSubject` (class) — single-subject tracker with velocity
    state. predict() advances position by velocity (with 0.90 damping).
    update(box, gain=0.5) lerps toward measurement, rejects with IoU<0.10
    after ≥3 coast frames. Eliminates two problems from the OpenCV-tracker-
    only approach: (1) static last_subject hold replaced by velocity-
    predicted position, (2) unchecked tracker drift caught by IoU gate.
  - `_create_tracker()` — OpenCV tracker factory: tries KCF first (fastest),
    falls back to CSRT (more accurate, slower), then MOSSE (deprecated but
    sometimes available). Returns None if no tracker available — caller
    runs detection-only mode. Logs the chosen tracker once per process
    via `_TRACKER_CAPABILITY_LOGGED` flag.

Internal-only — no external imports of these symbols. Re-exported from
motion_crop.py so the existing 4 call sites (build_subject_path,
build_subject_path_scene) inside motion_crop.py keep their bare references.

Logger note:
  The original `_create_tracker()` used `logger = logging.getLogger(__name__)`
  where __name__ was "app.services.motion_crop". To preserve log routing
  semantics (downstream filters/handlers that target that logger name),
  this module explicitly binds `logger = logging.getLogger("app.services.motion_crop")`
  rather than re-deriving via __name__. This is a pure-relocation
  preservation, not a behavior change.
"""
from __future__ import annotations

import logging
from typing import Tuple

import cv2

from app.services.motion_crop.utils import _iou_xywh

# Preserve original logger name so downstream log filters / handlers
# targeting "app.services.motion_crop" still match (Sprint 6.D-3.4 note).
logger = logging.getLogger("app.services.motion_crop")

_TRACKER_CAPABILITY_LOGGED = False


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
