"""Motion-crop subject detection — MediaPipe lazy helpers + Haar cascade
fallback chain + per-frame detection orchestration.

Sprint 6.D-3.5a — extracted verbatim from motion_crop.py
(lines 84-248 + 510-570 of the post-3.4 file). No logic changes; pure
relocation.

Contents (preserved in original source order, two logical sub-blocks):

  MediaPipe face block:
    _mp_face_detector, _mp_face_detector_initialized — per-process state.
    _get_mp_detector() — lazy-load MediaPipe FaceDetection (full-range
      model, confidence â‰¥ 0.5). Returns None when MediaPipe is unavailable.
    _detect_mediapipe_faces(frame_bgr_small, scale) — return absolute
      (x, y, w, h) boxes in _det_frame coordinates. Returns [] on any failure.
    _has_subject_in_sample(video_path, sample_count=24) — sparse-frame
      pre-flight. Conservatively returns True on any error so the full
      path is always the safe fallback.

  MediaPipe pose block (OQ-3.3 eye-level anchor):
    _mp_pose_detector, _mp_pose_initialized — per-process state.
    _POSE_LEFT_EYE = 2, _POSE_RIGHT_EYE = 5 — BlazePose landmark indices.
    _EYE_CROP_THIRDS = 0.33 — rule-of-thirds eye placement target.
    _get_mp_pose() — lazy-load MediaPipe Pose (BlazePose Lite,
      model_complexity=0). Honors POSE_EYE_ANCHOR_ENABLED env var.
    _get_eye_anchor_rel(frame_bgr_small, face_box_src, detect_scale,
      det_sy=1.0) — return eye midpoint y as a fraction of face-box
      height from its top. Validates nose inside face box (Â±20% margin)
      to reject background subjects. Returns None on any failure.

  Detection orchestration:
    prepare_detection_frame(frame, max_height=720) — cap height to
      max_height before detection. Returns
      (detect_frame, scale_x, scale_y, original_wh, scaled_wh).
    _detect_subjects_in_frame(gray_small, face_cascade, body_cascade,
      scale, frame_bgr_small=None) — MediaPipe primary → Haar face
      cascade fallback → Haar body cascade fallback. Returns
      (list of (x, y, w, h), kind: "face"|"body"|"none").

Note on `_pick_best_subject`:
  The original plan Â§3.5a listed `_pick_best_subject` here. It is NOT
  moved in this commit because it depends on `_score_subject_candidate`,
  which the plan assigns to phase 3.5b. Extracting `_pick_best_subject`
  alone would require an `import ... from app.features.render.engine.motion`
  inside the new module — that creates a real load-time cycle since
  motion_crop.py imports from this module at its top. `_pick_best_subject`
  will move together with `_score_subject_candidate` in 3.5b.

Internal-only — no external imports of these symbols today. The module
is re-exported from motion_crop.py so existing internal call sites
(build_subject_path, build_subject_path_scene, build_motion_path)
keep working unchanged.

Logger note (same pattern as 6.D-3.4):
  Original code used `logging.getLogger(__name__)` where __name__ was
  "app.services.motion_crop". Preserved here by binding
  `logger = logging.getLogger("app.services.motion_crop")` explicitly
  so existing log filters/handlers continue to match.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

# T2.2 — Audit 2026-06-08 closure (Batch A V9-F3): cancel poll for the
# subject-detection sample scan. See engine/encoder/ffmpeg_helpers.py.
from app.features.render.engine.encoder.ffmpeg_helpers import check_thread_cancel

# Preserve original logger name so downstream log filters / handlers
# targeting "app.services.motion_crop" still match (same as 6.D-3.4).
logger = logging.getLogger("app.services.motion_crop")


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
            model_selection=1,           # full-range model (â‰¤5m) — detects wide shots and small faces
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
            # T2.2 — cancel poll for the subject-detection sample scan.
            check_thread_cancel()
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
        # Validate: nose must be within the selected face box (Â±20% margin)
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
# Detection-frame preparation + per-frame detection orchestration
# ---------------------------------------------------------------------------

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

