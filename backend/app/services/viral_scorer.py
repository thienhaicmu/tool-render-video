"""
Viral scoring for video segments.

Two scoring modes:
  1. Heuristic (default) — improved multi-factor formula calibrated for
     TikTok content patterns (60-90s sweet spot, fast pacing, early hooks).

  2. ML (optional) — lightweight sklearn Ridge regression trained on actual
     performance feedback (views, likes).  Falls back to heuristic if no
     model has been trained yet.

Feedback collection:
  Call `record_feedback(segment_features, actual_views, actual_likes)` after
  a video is posted and performance data is available.  Once enough samples
  are collected, call `train_model()` to update the ML model.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Paths for persistence
# ─────────────────────────────────────────────────────────────────────────────

_DATA_DIR = Path(__file__).parents[3] / "data"
_FEEDBACK_PATH = _DATA_DIR / "viral_feedback.jsonl"
_MODEL_PATH = _DATA_DIR / "viral_model.pkl"
_MIN_SAMPLES_TO_TRAIN = 30  # Need at least this many feedback records to train


# ─────────────────────────────────────────────────────────────────────────────
# Feature extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_features(seg: Dict, scenes: List[Dict], total_segments: int, seg_index: int) -> Dict[str, float]:
    """
    Extract a fixed feature vector from a segment + its scene context.
    All features are normalized to [0, 1] or small positive floats so that
    a linear model can be trained without feature scaling.
    """
    start = float(seg.get("start", 0))
    end = float(seg.get("end", 0))
    duration = max(1.0, end - start)

    # Scenes that overlap with this segment
    seg_scenes = [s for s in scenes if float(s.get("start", 0)) >= start and float(s.get("end", start)) <= end]
    n_scenes = len(seg_scenes)
    scene_density = n_scenes / duration  # scene cuts per second

    # Does the segment start right after a scene cut? (strong hook)
    starts_at_cut = any(abs(float(s.get("end", -99)) - start) < 1.5 for s in scenes)

    # Does the segment end at a scene cut? (clean ending)
    ends_at_cut = any(abs(float(s.get("start", -99)) - end) < 1.5 for s in scenes)

    # Pacing acceleration: are scene cuts getting faster toward the end?
    pacing_accel = 0.0
    if len(seg_scenes) >= 4:
        half = len(seg_scenes) // 2
        first_half_density = half / max(1.0, (seg_scenes[half - 1]["end"] - seg_scenes[0]["start"]))
        second_half_density = (len(seg_scenes) - half) / max(1.0, (seg_scenes[-1]["end"] - seg_scenes[half]["start"]))
        pacing_accel = max(0.0, second_half_density - first_half_density)

    # Duration: TikTok sweet spot 55-85s → peak score, penalize outside
    # Using a Gaussian-shaped score centered at 70s, σ=15s
    duration_score = math.exp(-0.5 * ((duration - 70.0) / 20.0) ** 2)

    # Position in video: earlier is often better (more viewer energy), but
    # position 2-3 can be good too (past the intro).
    position_ratio = seg_index / max(1, total_segments - 1) if total_segments > 1 else 0.0
    position_score = max(0.0, 1.0 - position_ratio * 0.55)  # linear decay, 45% penalty for last

    # Scene quality
    scene_quality = float(seg.get("scene_quality_avg", 55.0)) / 100.0

    return {
        "scene_density": min(1.0, scene_density * 8.0),       # normalized: 0.125 cuts/s → 1.0
        "n_scenes_norm": min(1.0, n_scenes / 20.0),            # normalized: 20 cuts → 1.0
        "starts_at_cut": float(starts_at_cut),
        "ends_at_cut": float(ends_at_cut),
        "pacing_accel": min(1.0, pacing_accel * 5.0),
        "duration_score": duration_score,
        "position_score": position_score,
        "scene_quality": scene_quality,
        "is_first": float(seg_index == 0),
        "is_second": float(seg_index == 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic scorer (improved)
# ─────────────────────────────────────────────────────────────────────────────

# Weights calibrated for TikTok content patterns:
#   - Fast pacing (scene density) matters most
#   - Duration fit (55-85s sweet spot) is critical
#   - Starting at a scene cut = strong hook
#   - Earlier segments slightly favored
_HEURISTIC_WEIGHTS = {
    "scene_density":  0.28,
    "n_scenes_norm":  0.06,
    "starts_at_cut":  0.14,
    "ends_at_cut":    0.05,
    "pacing_accel":   0.09,
    "duration_score": 0.20,
    "position_score": 0.08,
    "scene_quality":  0.06,
    "is_first":       0.02,
    "is_second":      0.02,
}
assert abs(sum(_HEURISTIC_WEIGHTS.values()) - 1.0) < 1e-6, "Weights must sum to 1.0"


def _heuristic_score(features: Dict[str, float]) -> float:
    """Weighted linear combination of features → score in [0, 100]."""
    raw = sum(_HEURISTIC_WEIGHTS.get(k, 0.0) * v for k, v in features.items())
    return round(min(100.0, max(0.0, raw * 100.0)), 1)


# ─────────────────────────────────────────────────────────────────────────────
# ML scorer (sklearn Ridge regression)
# ─────────────────────────────────────────────────────────────────────────────

_ml_model = None  # Lazy-loaded Ridge model
_FEATURE_KEYS = list(_HEURISTIC_WEIGHTS.keys())


def _features_to_vector(features: Dict[str, float]) -> list:
    return [features.get(k, 0.0) for k in _FEATURE_KEYS]


def _load_model():
    global _ml_model
    if _ml_model is not None:
        return _ml_model
    if not _MODEL_PATH.exists():
        return None
    try:
        import pickle
        with open(_MODEL_PATH, "rb") as f:
            _ml_model = pickle.load(f)
        logger.info("Viral scorer: loaded ML model from %s", _MODEL_PATH)
        return _ml_model
    except Exception as exc:
        logger.warning("Failed to load viral ML model: %s", exc)
        return None


def _ml_score(features: Dict[str, float]) -> float | None:
    model = _load_model()
    if model is None:
        return None
    try:
        vec = [_features_to_vector(features)]
        pred = float(model.predict(vec)[0])
        return round(min(100.0, max(0.0, pred)), 1)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Feedback & training
# ─────────────────────────────────────────────────────────────────────────────

def record_feedback(features: Dict[str, float], views: int, likes: int):
    """
    Save a feedback record so the ML model can be trained later.
    *views* and *likes* are the actual TikTok performance metrics.
    """
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Normalize to a 0-100 target score using engagement proxy
    like_rate = likes / max(1, views)
    target = min(100.0, math.log1p(views) * 5.0 + like_rate * 30.0)
    record = {"features": features, "target": round(target, 2)}
    with open(_FEEDBACK_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def train_model() -> str:
    """
    Train (or retrain) the Ridge regression model from collected feedback.
    Returns a status message.
    """
    if not _FEEDBACK_PATH.exists():
        return "No feedback data found."
    records = []
    with open(_FEEDBACK_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    if len(records) < _MIN_SAMPLES_TO_TRAIN:
        return f"Need at least {_MIN_SAMPLES_TO_TRAIN} samples, have {len(records)}."
    try:
        from sklearn.linear_model import Ridge
        import pickle

        X = [_features_to_vector(r["features"]) for r in records]
        y = [r["target"] for r in records]
        model = Ridge(alpha=1.0)
        model.fit(X, y)
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump(model, f)
        global _ml_model
        _ml_model = model
        return f"Model trained on {len(records)} samples."
    except ImportError:
        return "sklearn not installed; pip install scikit-learn to enable ML scoring."
    except Exception as exc:
        return f"Training failed: {exc}"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def score_segments(segments: List[Dict], scenes: List[Dict]) -> List[Dict]:
    """
    Score all segments and return them sorted by viral_score descending.
    Uses ML model if trained, otherwise falls back to heuristic scoring.
    """
    total = len(segments)
    scored = []

    for idx, seg in enumerate(segments):
        features = extract_features(seg, scenes, total, idx)

        # Try ML first, fall back to heuristic
        viral_score = _ml_score(features)
        scoring_mode = "ml"
        if viral_score is None:
            viral_score = _heuristic_score(features)
            scoring_mode = "heuristic"

        # Keep legacy sub-scores for UI display (back-compat)
        duration = max(1.0, float(seg.get("end", 0)) - float(seg.get("start", 0)))
        seg_scenes = [s for s in scenes if float(s.get("start", 0)) >= seg.get("start", 0)
                      and float(s.get("end", seg.get("start", 0))) <= seg.get("end", 0)]
        scene_density = len(seg_scenes) / duration
        motion_score = min(100, int(scene_density * 1100))
        hook_timing_score = round(features["starts_at_cut"] * 40 + features["position_score"] * 40
                                  + features["duration_score"] * 20, 1)

        scored.append({
            **seg,
            "duration": round(duration, 2),
            "viral_score": int(viral_score),
            "motion_score": motion_score,
            "hook_timing_score": hook_timing_score,
            "hook_score": hook_timing_score,  # DB backward-compat alias
            "scene_quality_score": round(float(seg.get("scene_quality_avg", 55.0)), 2),
            "speech_density_score": min(100, 45 + len(seg_scenes) * 3),
            "scene_change_score": min(100, len(seg_scenes) * 6),
            "_features": features,       # stored for feedback recording
            "_scoring_mode": scoring_mode,
        })

    scored.sort(key=lambda x: x["viral_score"], reverse=True)
    for rank, item in enumerate(scored, start=1):
        item["priority_rank"] = rank

    return scored
