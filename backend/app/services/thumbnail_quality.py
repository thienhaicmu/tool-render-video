"""
S4.3: Thumbnail Quality Intelligence
Gate: S4_THUMBNAIL_QUALITY_ENABLED=1

Scores JPEG frames for sharpness, exposure, and face visibility using only
tools already bundled with the project (OpenCV Laplacian, mean brightness,
Haar cascade — no model downloads, no external APIs).

Extracts up to 3 candidate frames around the heuristic offset and returns
the best-quality one. Falls back to None on any failure so the caller can
use the original extract_thumbnail_frame() path (RC3).
"""
from __future__ import annotations

import logging
import os
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

_S4_SEARCH_WINDOW_SEC = 1.5   # seconds either side of heuristic offset
_S4_SHARPNESS_GOOD   = 80.0   # Laplacian variance — above this = sharp frame
_S4_SHARPNESS_NORM   = 200.0  # saturation point for sharpness contribution
_S4_BRIGHTNESS_MIN   = 35.0   # below this = near-black / transition frame
_S4_BRIGHTNESS_MAX   = 215.0  # above this = overexposed
_S4_BRIGHTNESS_IDEAL = 128.0  # target for peak exposure bonus

# Haar cascade singleton (lazy-loaded, graceful fail if OpenCV absent)
_haar_cascade = None
_haar_attempted = False


def _load_haar():
    """Lazy-load the frontal-face Haar cascade bundled with OpenCV.

    Returns cv2.CascadeClassifier or None if OpenCV is unavailable or the
    cascade is missing (RC3 — score still works on sharpness + exposure alone).
    """
    global _haar_cascade, _haar_attempted
    if _haar_attempted:
        return _haar_cascade
    _haar_attempted = True
    try:
        import cv2  # noqa: PLC0415
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        c = cv2.CascadeClassifier(path)
        if not c.empty():
            _haar_cascade = c
            logger.debug("s4.3: Haar cascade loaded from %s", path)
        else:
            logger.debug("s4.3: Haar cascade empty — face scoring disabled")
    except Exception as exc:
        logger.debug("s4.3: Haar cascade unavailable: %s", exc)
    return _haar_cascade


def score_frame_quality(jpeg_bytes: bytes) -> Optional[Dict]:
    """Score a JPEG frame for thumbnail suitability.

    Returns a dict with composite score and component signals, or None if the
    frame cannot be decoded (e.g. corrupt bytes).

    Components:
      sharpness   — Laplacian variance; high = crisp, low = motion-blurred/transition
      brightness  — mean gray pixel [0,255]; penalises near-black and blown-out
      face_score  — normalized Haar face area [0,1]; 0 when no face detected
      reasons     — list of fired tags for RC7 observability
    """
    try:
        import cv2       # noqa: PLC0415
        import numpy as np  # noqa: PLC0415
    except ImportError:
        return None

    try:
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None or img.size == 0:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    except Exception:
        return None

    h, w = gray.shape
    reasons: List[str] = []
    score = 0.0

    # ── Sharpness: Laplacian variance ────────────────────────────────────────
    try:
        import numpy as np  # noqa: PLC0415, F811
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    except Exception:
        lap_var = 0.0
    sharp_norm = min(1.0, lap_var / _S4_SHARPNESS_NORM)
    score += sharp_norm * 40.0
    if lap_var >= _S4_SHARPNESS_GOOD:
        reasons.append("sharp_frame")

    # ── Brightness / exposure ─────────────────────────────────────────────────
    try:
        import numpy as np  # noqa: PLC0415, F811
        brightness = float(np.mean(gray))
    except Exception:
        brightness = 128.0
    if _S4_BRIGHTNESS_MIN <= brightness <= _S4_BRIGHTNESS_MAX:
        # Bonus peaks at ideal brightness, tapers at edges of acceptable range
        exp_bonus = 20.0 - abs(brightness - _S4_BRIGHTNESS_IDEAL) / _S4_BRIGHTNESS_IDEAL * 10.0
        score += max(0.0, exp_bonus)
        reasons.append("good_exposure")
    elif brightness < 15.0 or brightness > 240.0:
        score -= 20.0  # near-black transition or blown-out

    # ── Face visibility: Haar cascade (bundled with OpenCV, no download) ──────
    face_score = 0.0
    cascade = _load_haar()
    if cascade is not None:
        try:
            min_face = max(20, int(min(h, w) * 0.06))
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(min_face, min_face),
            )
            if len(faces) > 0:
                max_face_area = max(int(fw) * int(fh) for (_, _, fw, fh) in faces)
                # Normalize: face covering ~4% of frame = score 1.0
                face_score = min(1.0, max_face_area / max(h * w * 0.04, 1.0))
                score += face_score * 30.0
                reasons.append("good_face_visibility")
                # Expression proxy: face present + frame sharp enough
                # (sharp = not in a blink / motion moment)
                if lap_var >= 60.0:
                    reasons.append("expression_ok")
        except Exception:
            pass

    return {
        "score":      score,
        "sharpness":  lap_var,
        "brightness": brightness,
        "face_score": face_score,
        "reasons":    reasons,
    }


def select_best_thumbnail(
    clip_path: str,
    base_offset: float,
    clip_duration: float,
    width: int = 640,
) -> Tuple[Optional[bytes], float, List[str]]:
    """Extract up to 3 frames around base_offset; return the best-quality one.

    Candidate offsets: [base - window, base, base + window], all clamped to
    [0.5s, clip_duration - 0.5s].  Deduplication prevents redundant extractions
    when clamping collapses candidates.

    Gate: S4_THUMBNAIL_QUALITY_ENABLED=1.

    Returns:
      (jpeg_bytes, chosen_offset, quality_reasons)
      jpeg_bytes is None when no candidate was extractable — caller must fall
      back to the original extract_thumbnail_frame() call (RC3).
    """
    if os.getenv("S4_THUMBNAIL_QUALITY_ENABLED") != "1":
        return None, base_offset, []

    try:
        from app.services.render_engine import extract_thumbnail_frame  # noqa: PLC0415
    except ImportError as exc:
        logger.debug("s4.3: render_engine unavailable: %s", exc)
        return None, base_offset, []

    dur = max(2.0, float(clip_duration or 0))
    lo, hi = 0.5, dur - 0.5

    raw = [base_offset - _S4_SEARCH_WINDOW_SEC, base_offset, base_offset + _S4_SEARCH_WINDOW_SEC]
    offsets: List[float] = sorted({round(max(lo, min(hi, t)), 3) for t in raw})

    best_bytes: Optional[bytes] = None
    best_offset = base_offset
    best_score = -1.0
    best_reasons: List[str] = []

    for offset in offsets:
        try:
            jpeg = extract_thumbnail_frame(clip_path, offset, width=width)
        except Exception:
            jpeg = None
        if not jpeg:
            continue

        quality = score_frame_quality(jpeg)
        if quality is None:
            # Decode failed — still track bytes so we have a fallback
            if best_bytes is None:
                best_bytes = jpeg
                best_offset = offset
            continue

        if quality["score"] > best_score:
            best_score = quality["score"]
            best_bytes = jpeg
            best_offset = offset
            best_reasons = quality.get("reasons", [])

    return best_bytes, best_offset, best_reasons
