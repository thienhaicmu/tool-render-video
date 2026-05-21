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
import os
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

    # Transition quality: average visual abruptness of scene cuts in segment.
    # High = energetic/sharp cuts; 0.0 = no cuts (talking head / continuous content).
    # Uses transition_score already computed by scene_detector._compute_transition_scores.
    if seg_scenes:
        avg_transition_quality = sum(s.get("transition_score", 0.5) for s in seg_scenes) / len(seg_scenes)
    else:
        avg_transition_quality = 0.0

    # Duration: TikTok sweet spot 55-85s → peak score, penalize outside
    # Using a Gaussian-shaped score centered at 70s, σ=15s
    duration_score = math.exp(-0.5 * ((duration - 70.0) / 20.0) ** 2)

    # Position in video: earlier is often better (more viewer energy), but
    # position 2-3 can be good too (past the intro).
    position_ratio = seg_index / max(1, total_segments - 1) if total_segments > 1 else 0.0
    position_score = max(0.25, 1.0 - position_ratio * 0.55)  # linear decay, 45% penalty, 0.25 floor

    # Scene quality
    scene_quality = float(seg.get("scene_quality_avg", 55.0)) / 100.0

    return {
        "scene_density":          min(1.0, scene_density * 8.0),  # normalized: 0.125 cuts/s → 1.0
        "n_scenes_norm":          min(1.0, n_scenes / 20.0),      # normalized: 20 cuts → 1.0
        "avg_transition_quality": avg_transition_quality,          # cut energy quality [0, 1]
        "starts_at_cut":          float(starts_at_cut),
        "ends_at_cut":            float(ends_at_cut),
        "pacing_accel":           min(1.0, pacing_accel * 5.0),
        "duration_score":         duration_score,
        "position_score":         position_score,
        "scene_quality":          scene_quality,
        "is_first":               float(seg_index == 0),
        "is_second":              float(seg_index == 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Heuristic scorer (improved)
# ─────────────────────────────────────────────────────────────────────────────

# Weights calibrated for multi-signal content quality:
#   - Duration fit (55-85s sweet spot) is critical
#   - Starting at a scene cut = strong hook entry
#   - Transition quality (avg_transition_quality) reflects cut energy, not just frequency
#   - scene_density reduced: raw cut count alone does not equal content quality
_HEURISTIC_WEIGHTS = {
    "scene_density":          0.18,  # was 0.28 — cut frequency alone ≠ quality
    "n_scenes_norm":          0.04,  # was 0.06
    "avg_transition_quality": 0.10,  # NEW — visual cut energy (transition_score avg)
    "starts_at_cut":          0.16,  # was 0.14
    "ends_at_cut":            0.04,  # was 0.05
    "pacing_accel":           0.07,  # was 0.09
    "duration_score":         0.20,  # unchanged
    "position_score":         0.08,  # unchanged
    "scene_quality":          0.09,  # was 0.06 — content quality matters more
    "is_first":               0.02,  # unchanged
    "is_second":              0.02,  # unchanged
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
# Fixed feature key order for ML model backward-compatibility.
# New heuristic features (e.g. avg_transition_quality) live in _HEURISTIC_WEIGHTS
# but NOT here — adding here would break any saved model's input dimensions.
_FEATURE_KEYS = [
    "scene_density", "n_scenes_norm", "starts_at_cut", "ends_at_cut",
    "pacing_accel", "duration_score", "position_score", "scene_quality",
    "is_first", "is_second",
]


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

# ─────────────────────────────────────────────────────────────────────────────
# S4.4: Content Type Intelligence V2 (env-gated: S4_CONTENT_INTELLIGENCE_ENABLED=1)
# ─────────────────────────────────────────────────────────────────────────────

def _classify_content_type_v2(
    scene_density: float,
    features: Dict[str, float],
    seg_scenes: list,
    seg: Dict,
    avg_tq: float,
) -> str:
    """Multi-signal content type classifier — nine types vs the legacy four.

    Priority order (first match wins):
      high-energy → montage → education → reaction → storytelling →
      podcast → commentary → vlog → interview
    Falls back to scene-density buckets at the bottom so a type is always returned.
    """
    n_scenes   = len(seg_scenes)
    p_acc      = float(features.get("pacing_accel", 0.0))    # normalized [0, 1]
    starts_cut = float(features.get("starts_at_cut", 0.0))
    # speech_density_score > 0 only when populated from real SRT;
    # 0 means unavailable — do not treat proxy value as a speech signal.
    speech_raw = float(seg.get("speech_density_score", 0.0))

    # ── High-energy: dense fast cuts + sharp transitions + accelerating rhythm ─
    if scene_density >= 0.20 and avg_tq >= 0.55 and p_acc >= 0.30:
        logger.debug(
            "content_type=high-energy seg=[%.1f,%.1f] density=%.3f avg_tq=%.2f p_acc=%.2f",
            float(seg.get("start", 0)), float(seg.get("end", 0)),
            scene_density, avg_tq, p_acc,
        )
        return "high-energy"

    # ── Montage: high density, any cut quality ─────────────────────────────────
    if scene_density >= 0.18:
        return "montage"

    # ── Education: steady instructional rhythm + precise cuts (≥3 scenes) ──────
    # Optional speech_density boost confirms narration-heavy content.
    if n_scenes >= 3 and scene_density >= 0.03:
        _steady = max(0.0, 1.0 - p_acc / 0.40)
        _sharp  = min(1.0, avg_tq / 0.65)
        _speech_boost = 0.08 if speech_raw > 55 else 0.0
        _edu_score = 0.55 * _sharp + 0.37 * _steady + _speech_boost
        _edu_threshold = 0.68 if scene_density >= 0.08 else 0.73
        if _edu_score >= _edu_threshold:
            logger.debug(
                "content_type=education seg=[%.1f,%.1f] density=%.3f avg_tq=%.2f "
                "p_acc=%.2f score=%.2f",
                float(seg.get("start", 0)), float(seg.get("end", 0)),
                scene_density, avg_tq, p_acc, _edu_score,
            )
            return "education"

    # ── Reaction: commentary-range density with reactive cutting pattern ────────
    if 0.03 <= scene_density < 0.10 and starts_cut >= 0.5 and avg_tq >= 0.50:
        logger.debug(
            "content_type=reaction seg=[%.1f,%.1f] density=%.3f starts_cut=%.0f avg_tq=%.2f",
            float(seg.get("start", 0)), float(seg.get("end", 0)),
            scene_density, starts_cut, avg_tq,
        )
        return "reaction"

    # ── Storytelling: moderate density, flat pacing, soft cuts — narrative arc ──
    if 0.06 <= scene_density < 0.18 and p_acc < 0.20 and avg_tq < 0.45:
        logger.debug(
            "content_type=storytelling seg=[%.1f,%.1f] density=%.3f p_acc=%.2f avg_tq=%.2f",
            float(seg.get("start", 0)), float(seg.get("end", 0)),
            scene_density, p_acc, avg_tq,
        )
        return "storytelling"

    # ── Podcast: low visual activity + confirmed real-SRT speech coverage ───────
    if scene_density < 0.05 and speech_raw > 55:
        return "podcast"

    # ── Fallback: scene-density buckets (same thresholds as legacy v1) ─────────
    if scene_density < 0.03:
        return "interview"
    if scene_density < 0.08:
        return "commentary"
    if scene_density < 0.18:
        return "vlog"
    return "montage"


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
        # Improved motion_score: cut frequency × transition quality.
        # Rewards energetic editing rather than raw cut count.
        # Talking-head / no-cut content scores 0 (by design — PART B handles ranking).
        avg_trans_val = features.get("avg_transition_quality", 0.0)
        motion_score = min(100, int(scene_density * 660 * max(0.1, avg_trans_val))) if seg_scenes else 0
        hook_timing_score = round(features["starts_at_cut"] * 40 + features["position_score"] * 40
                                  + features["duration_score"] * 20, 1)

        # Content type hint — informs ranking explainability and S4.2 retention signals (PART C).
        # S4.4 gate: multi-signal V2 classifier when enabled, legacy density buckets otherwise.
        if os.getenv("S4_CONTENT_INTELLIGENCE_ENABLED") == "1":
            content_type_hint = _classify_content_type_v2(
                scene_density, features, seg_scenes, seg, avg_trans_val
            )
        else:
            # Legacy: four primary buckets inferred from scene density alone.
            if scene_density < 0.03:
                content_type_hint = "interview"
            elif scene_density < 0.08:
                content_type_hint = "commentary"
            elif scene_density < 0.18:
                content_type_hint = "vlog"
            else:
                content_type_hint = "montage"

            # Tutorial detection pass (QUALITY-UP10B):
            # Steady rhythm + sharp/hard cuts within vlog/commentary density range.
            if content_type_hint in ("vlog", "commentary") and len(seg_scenes) >= 3:
                _steady = max(0.0, 1.0 - features["pacing_accel"] / 0.40)
                _sharp  = min(1.0, avg_trans_val / 0.65)
                _tutorial_likelihood = 0.60 * _sharp + 0.40 * _steady
                _tut_threshold = 0.70 if content_type_hint == "vlog" else 0.75
                if _tutorial_likelihood >= _tut_threshold:
                    content_type_hint = "tutorial"
                    logger.debug(
                        "content_type_hint=tutorial inferred seg=[%.1f,%.1f] "
                        "scene_density=%.3f avg_tq=%.2f pacing_accel=%.2f likelihood=%.2f",
                        float(seg.get("start", 0)), float(seg.get("end", 0)),
                        scene_density, avg_trans_val, features["pacing_accel"], _tutorial_likelihood,
                    )

        # Selection reason: human-readable signal summary for UI (PART E).
        _sel: list[str] = []
        if features.get("starts_at_cut", 0.0) >= 0.5:
            _sel.append("Strong opening hook")
        if content_type_hint in ("interview", "commentary", "podcast"):
            if features.get("scene_quality", 0.0) >= 0.65:
                _sel.append("High-quality spoken content")
        elif content_type_hint in ("tutorial", "education"):
            _sel.append("Steady instructional pacing")
        elif content_type_hint == "storytelling":
            _sel.append("Narrative arc flow")
        elif content_type_hint == "reaction":
            _sel.append("Reactive editing style")
        elif content_type_hint == "high-energy":
            _sel.append("High-energy action")
        elif features.get("scene_density", 0.0) >= 0.5:
            _sel.append("Fast-paced editing")
        if features.get("duration_score", 0.0) >= 0.85:
            _sel.append("Ideal duration")
        elif features.get("position_score", 0.0) >= 0.85:
            _sel.append("Strong early position")
        selection_reason = ", ".join(_sel[:2]) if _sel else ""

        # speech_density_score: use real speech data from segment builder when available
        # (populated by build_segments_from_scenes_with_subtitles via SRT coverage ratio).
        # Fall back to scene-count proxy when no speech data has been computed yet.
        _real_speech = float(seg.get("speech_density_score", 0.0))
        _speech_density_score = int(_real_speech) if _real_speech > 0 else min(100, 45 + len(seg_scenes) * 3)

        scored.append({
            **seg,
            "duration": round(duration, 2),
            "viral_score": int(viral_score),
            "motion_score": motion_score,
            "hook_timing_score": hook_timing_score,
            "hook_score": hook_timing_score,  # DB backward-compat alias
            "scene_quality_score": round(float(seg.get("scene_quality_avg", 55.0)), 2),
            "speech_density_score": _speech_density_score,
            "scene_change_score": min(100, len(seg_scenes) * 6),
            "content_type_hint": content_type_hint,
            "selection_reason": selection_reason,
            "_features": features,       # stored for feedback recording
            "_scoring_mode": scoring_mode,
        })

    scored.sort(key=lambda x: x["viral_score"], reverse=True)
    for rank, item in enumerate(scored, start=1):
        item["priority_rank"] = rank

    return scored


# ─────────────────────────────────────────────────────────────────────────────
# S4.2: Real Retention Proxy (env-gated: S4_RETENTION_PROXY_ENABLED=1)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_transcript_signals(
    transcript_blocks: List[Dict], seg_start: float, seg_end: float
) -> Dict[str, float] | None:
    """Extract words/sec, pause ratio, and speech variance for a [seg_start, seg_end] window."""
    seg_blocks = [
        b for b in transcript_blocks
        if float(b.get("end", 0)) > seg_start and float(b.get("start", 0)) < seg_end
    ]
    if not seg_blocks:
        return None
    duration = max(seg_end - seg_start, 1.0)
    total_words = sum(len(str(b.get("text", "")).split()) for b in seg_blocks)
    words_per_sec = total_words / duration
    # Pause ratio: fraction of segment in gaps > 1.5s between consecutive blocks
    pause_total = 0.0
    for k in range(1, len(seg_blocks)):
        gap = float(seg_blocks[k].get("start", 0)) - float(seg_blocks[k - 1].get("end", 0))
        if gap > 1.5:
            pause_total += gap
    pause_ratio = min(1.0, pause_total / duration)
    # Words-per-block coefficient of variation (speech dynamics)
    wpb = [len(str(b.get("text", "")).split()) for b in seg_blocks]
    mean_wpb = sum(wpb) / max(len(wpb), 1)
    var_wpb = sum((w - mean_wpb) ** 2 for w in wpb) / max(len(wpb), 1)
    wps_variance = math.sqrt(var_wpb) / max(mean_wpb, 0.1)
    return {
        "words_per_sec":   words_per_sec,
        "pause_ratio":     pause_ratio,
        "wps_variance":    wps_variance,
        "seg_block_count": len(seg_blocks),
    }


def _compute_retention_delta(seg: Dict, tsig: Dict | None) -> tuple:
    """Compute retention delta ∈ [-15, +15] and reason tags for one segment.

    Tier-1 signals use only pre-computed segment fields (always available).
    Tier-2 signals use transcript data (silently skipped when tsig is None).
    """
    def _c(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(v)))

    feat   = seg.get("_features") or {}
    hook   = float(seg.get("hook_opening_score", 50.0))
    payoff = float(seg.get("payoff_score", 50.0))
    avg_q  = float(seg.get("scene_quality_avg", 50.0))
    sc_den = float(feat.get("scene_density", 0.3))   # normalized [0, 1]
    p_acc  = float(feat.get("pacing_accel", 0.3))    # normalized [0, 1]
    ctype  = str(seg.get("content_type_hint", ""))
    dur    = float(seg.get("duration", 60.0))

    delta: float = 0.0
    reasons: List[str] = []

    # A — Dead opening: weak hook + minimal visual energy
    if hook < 35.0 and sc_den < 0.15:
        delta -= _c((35.0 - hook) / 35.0 * 6.0, 0.0, 6.0)
        reasons.append("dead_opening")

    # B — Flat zone: completely static talking-head, no pacing variation.
    # Guard: pacing_accel = 0.0 is a data artifact when scene_count < 4 (extract_features
    # requires >=4 scenes to compute acceleration). Treat insufficient data as unknown,
    # not as flat pacing — otherwise ~51% of production segments are falsely penalised.
    if (ctype in ("interview", "commentary")
            and p_acc < 0.05
            and int(seg.get("scene_count", 0)) >= 4):
        delta -= _c((0.05 - p_acc) / 0.05 * 4.0, 0.0, 4.0)
        reasons.append("flat_zone")

    # C — Semantic density: content-dense speech (tier-2)
    if tsig and tsig.get("seg_block_count", 0) >= 3:
        wps = float(tsig.get("words_per_sec", 0.0))
        if wps > 2.5:
            delta += _c((wps - 2.5) / 2.5 * 5.0, 0.0, 5.0)
            reasons.append("semantic_density")

    # D — Payoff continuation: segment builds to a strong ending
    if payoff > avg_q + 25.0 and payoff > 70.0:
        delta += _c((payoff - (avg_q + 25.0)) / 30.0 * 4.0, 0.0, 4.0)
        reasons.append("payoff_continuation")

    # E — Dead zone: long spoken segment with heavy silence (tier-2 required)
    if (ctype in ("interview", "commentary") and dur > 75.0
            and sc_den < 0.10
            and tsig and float(tsig.get("pause_ratio", 0.0)) > 0.30):
        delta -= _c((float(tsig["pause_ratio"]) - 0.30) / 0.50 * 4.0, 0.0, 4.0)
        reasons.append("dead_zone")

    # F — Natural rhythm: healthy pacing acceleration range [0.10, 0.65]
    if 0.10 <= p_acc <= 0.65:
        delta += _c(1.0 - abs(p_acc - 0.35) / 0.35, 0.0, 1.0) * 3.0
        reasons.append("healthy_rhythm")

    # G — Speech dynamics: healthy within-segment variation (tier-2)
    if tsig and tsig.get("seg_block_count", 0) >= 4:
        wps_var = float(tsig.get("wps_variance", 0.0))
        if 0.30 <= wps_var <= 0.80:
            delta += _c(1.0 - abs(wps_var - 0.55) / 0.55, 0.0, 1.0) * 2.0
            if "healthy_rhythm" not in reasons:
                reasons.append("healthy_rhythm")

    return _c(delta, -15.0, 15.0), reasons


def apply_retention_proxy(
    scored: List[Dict],
    transcript_blocks: List[Dict] | None = None,
) -> List[Dict]:
    """Adjust viral_score by a multi-signal retention delta bounded to [-15, +15].

    Gate: S4_RETENTION_PROXY_ENABLED=1. Returns scored unchanged when the gate
    is off or on any exception (RC3). Transcript signals are skipped when
    transcript_blocks is None (RC3). Clip count is never changed (RC6).
    retention_adjustment_reason records which signals fired (RC8).
    """
    if os.getenv("S4_RETENTION_PROXY_ENABLED") != "1":
        return scored

    # Pre-compute transcript signals per segment (tier-2, optional)
    tsig_map: Dict[int, Dict] = {}
    if transcript_blocks:
        for i, seg in enumerate(scored):
            try:
                sig = _compute_transcript_signals(
                    transcript_blocks,
                    float(seg.get("start", 0.0)),
                    float(seg.get("end", 0.0)),
                )
                if sig:
                    tsig_map[i] = sig
            except Exception:
                pass

    result: List[Dict] = []
    for i, seg in enumerate(scored):
        try:
            delta, reasons = _compute_retention_delta(seg, tsig_map.get(i))
        except Exception as exc:
            logger.debug("retention_delta_failed seg=%d: %s", i, exc)
            result.append(seg)
            continue

        if delta == 0.0 and not reasons:
            result.append(seg)
            continue

        seg = dict(seg)
        seg["viral_score"] = int(min(100.0, max(0.0, float(seg.get("viral_score", 0)) + delta)))
        if reasons:
            seg["retention_adjustment_reason"] = reasons
        result.append(seg)

    return result
