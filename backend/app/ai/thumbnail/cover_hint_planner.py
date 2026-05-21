"""
cover_hint_planner.py — S3.3 Thumbnail/Cover Intelligence.

Per-clip best-frame hint for TikTok/Reels/Shorts cover selection.
Advisory metadata only — NEVER affects selection, scoring, retry,
diversity, creator DNA, or render output. No render changes.

Distinct from UP15 (render_pipeline._select_cover_frame_time):
  - UP15: runs at render time, uses hook_score + platform + variant_type
  - S3.3: runs at plan assembly, uses S2 signals (hook_intelligence_type,
          moment_type, structure_phases) + S3.2 retention prediction
  - S3.3 hint is passed to UP15 as an optional extra candidate only (RC6 cap)

Required changes applied:
    RC1: S3_THUMBNAIL_ENABLED / S3_THUMBNAIL_MIN_SCORE env naming
    RC2: confidence gate — emit null hint for segment_score < threshold
    RC3: existing packaging crop metadata (S3.1 packaging_applied) → +0.08
         confidence bonus. No new CV system added.
    RC4: thumbnail_risks explainability list per clip
         (low_face_presence, late_payoff, weak_expression, low_signal,
          scene_fallback)
    RC5: S3_THUMBNAIL_ENABLED=0 produces bit-identical behavior
    RC6: UP15 candidate cap — hint adds maximum +1 candidate only;
         UP15 remains authoritative

Set S3_THUMBNAIL_ENABLED=0 for full rollback.

Public API:
    plan_cover_hints(selected_raw, retention_predictions, goal, packaging_applied) -> dict
    S3_THUMBNAIL_ENABLED: bool
    S3_THUMBNAIL_MIN_SCORE: float
"""
from __future__ import annotations

import os

S3_THUMBNAIL_ENABLED: bool = os.environ.get("S3_THUMBNAIL_ENABLED", "1") == "1"
S3_THUMBNAIL_MIN_SCORE: float = float(os.environ.get("S3_THUMBNAIL_MIN_SCORE", "40"))

# Base confidence before any signal contributions.
_BASE_CONFIDENCE: float = 0.20

# Confidence contribution per signal.
_CONF_HOOK_KNOWN: float = 0.20
_CONF_MOMENT_KNOWN: float = 0.25
_CONF_RETENTION_AVAIL: float = 0.15
_CONF_STRUCTURE_PHASES: float = 0.10
_CONF_CROP_META: float = 0.08   # RC3: S3.1 packaging_applied non-empty → bonus

# Moment type → (min_ratio, max_ratio) of clip duration.
# Midpoint of this range becomes the base preferred_offset_ratio.
_MOMENT_OFFSET_RANGE: dict[str, tuple[float, float]] = {
    "payoff":      (0.50, 0.70),
    "hook_payoff": (0.40, 0.60),
    "hook_opener": (0.08, 0.18),
    "full_story":  (0.30, 0.45),
    "explainer":   (0.15, 0.35),
    "narrative":   (0.15, 0.35),
}

# Hook type → offset nudge applied on top of moment midpoint.
# Negative = pull earlier (strong visual impact); positive = push later.
_HOOK_OFFSET_NUDGE: dict[str, float] = {
    "surprise":     -0.10,
    "warning":      -0.10,
    "result_first": -0.10,
    "story":        +0.08,
    "authority":    +0.08,
}

# Content types with likely face/subject presence (talking-head formats).
# Used to gate the low_face_presence risk — only fires when content type
# is known and explicitly NOT in this set.
_FACE_HEAVY_CONTENT: frozenset[str] = frozenset({
    "interview", "talking_head", "vlog", "tutorial", "commentary",
})

# Conservative fallback range used when moment_type is unknown but
# other signals exist (hook_type known, etc.).
_DEFAULT_OFFSET_RANGE: tuple[float, float] = (0.25, 0.45)

# Hard clamp bounds on the preferred_offset_ratio output.
# Avoids first/last 5% of the clip (opening cut artifacts, outro fade).
_RATIO_MIN: float = 0.05
_RATIO_MAX: float = 0.90


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_cover_hints(
    selected_raw: list[dict],
    retention_predictions: dict,
    goal: str = "",
    packaging_applied: dict | None = None,
) -> dict:
    """Compute per-clip thumbnail frame hints at plan assembly time.

    Returns {clip_index (int): cover_hint_dict}.

    cover_hint_dict fields:
        preferred_offset_ratio  float | None  — ratio of clip duration [0.05, 0.90]
                                                or None when signal is absent/weak
        confidence              float         — [0.10, 1.0] signal depth (RC2/RC3)
        reason                  list[str]     — explainability signals present
        thumbnail_risks         list[str]     — risk factors (RC4)

    RC1 (env naming):    S3_THUMBNAIL_ENABLED / S3_THUMBNAIL_MIN_SCORE
    RC2 (conf gate):     segment_score < threshold → null hint, UP15 unchanged
    RC3 (crop meta):     packaging_applied[idx] non-empty → +0.08 confidence
    RC4 (risks):         thumbnail_risks per clip (late_payoff, weak_expression…)
    RC5 (exact no-op):   S3_THUMBNAIL_ENABLED=0 → {} → bit-identical to pre-S3.3
    RC6 (UP15 cap):      hint is one extra candidate at most; UP15 authoritative

    Advisory only — return value MUST NEVER influence clip selection, retry,
    ranking, diversity penalty, or creator DNA.
    """
    if not S3_THUMBNAIL_ENABLED:
        return {}  # RC5: exact no-op

    result: dict = {}
    pkg = packaging_applied or {}

    for idx, seg in enumerate(selected_raw):
        try:
            retention    = retention_predictions.get(idx) or {}
            pkg_for_clip = pkg.get(idx) or {}
            hint         = _hint_one(seg, retention, pkg_for_clip)
            result[idx]  = hint
        except Exception:
            # Per-clip failure swallowed — never propagates.
            pass

    return result


# ---------------------------------------------------------------------------
# Internal — per-clip hint computation
# ---------------------------------------------------------------------------

def _hint_one(seg: dict, retention: dict, pkg_for_clip: dict) -> dict:
    """Compute thumbnail hint dict for a single clip segment."""
    score = float(seg.get("score", 0.0) or 0.0)

    # RC2: confidence gate — weak clips get null hint, UP15 runs unchanged.
    if score < S3_THUMBNAIL_MIN_SCORE:
        return {
            "preferred_offset_ratio": None,
            "confidence":             0.10,
            "reason":                 ["weak_clip_score"],
            "thumbnail_risks":        ["low_signal"],
        }

    hook_type    = str(seg.get("hook_intelligence_type", "none") or "none").lower()
    moment_type  = str(seg.get("moment_type", "unknown") or "unknown").lower()
    struct_phases = list(seg.get("structure_phases", []) or [])
    content_hint  = str(seg.get("content_type_hint", "") or "").lower()
    source        = str(seg.get("source", "") or "").lower()

    retention_available = bool(retention.get("retention_available", False))
    retention_risks     = list(
        (retention.get("retention_explanation") or {}).get("risks", []) or []
    )

    # No signals at all → null hint (UP15 runs unchanged).
    if moment_type == "unknown" and hook_type == "none":
        return {
            "preferred_offset_ratio": None,
            "confidence":             0.10,
            "reason":                 ["no_signals"],
            "thumbnail_risks":        ["low_signal"],
        }

    # ── Preferred offset ratio ─────────────────────────────────────────────
    offset_range    = _MOMENT_OFFSET_RANGE.get(moment_type, _DEFAULT_OFFSET_RANGE)
    midpoint        = (offset_range[0] + offset_range[1]) / 2.0
    nudge           = _HOOK_OFFSET_NUDGE.get(hook_type, 0.0)
    preferred_ratio = round(max(_RATIO_MIN, min(_RATIO_MAX, midpoint + nudge)), 3)

    # ── Confidence ─────────────────────────────────────────────────────────
    conf = _BASE_CONFIDENCE
    if hook_type != "none":
        conf += _CONF_HOOK_KNOWN
    if moment_type in _MOMENT_OFFSET_RANGE:
        conf += _CONF_MOMENT_KNOWN
    if retention_available:
        conf += _CONF_RETENTION_AVAIL
    if struct_phases:
        conf += _CONF_STRUCTURE_PHASES
    # RC3: reuse existing crop metadata — S3.1 packaging_applied non-empty.
    if pkg_for_clip:
        conf += _CONF_CROP_META
    confidence = round(max(0.10, min(1.0, conf)), 3)

    # ── Reason list (explainability) ───────────────────────────────────────
    reason: list[str] = []
    if moment_type in _MOMENT_OFFSET_RANGE:
        reason.append(f"moment_{moment_type}")
    if hook_type != "none":
        reason.append(f"hook_{hook_type}")
    if retention_available:
        risk_level = str(retention.get("risk_level") or "").lower()
        if risk_level == "low":
            reason.append("retention_high")
        elif risk_level == "high":
            reason.append("retention_low")
    if pkg_for_clip:
        reason.append("crop_meta_present")   # RC3 signal visible in explainability
    if not reason:
        reason.append("signal_present")

    # ── Thumbnail risks (RC4) ───────────────────────────────────────────────
    thumbnail_risks: list[str] = []

    # late_payoff: payoff moment but no structure phases to locate its start.
    if moment_type == "payoff" and not struct_phases:
        thumbnail_risks.append("late_payoff")

    # low_face_presence: content type is known and not a face-heavy format.
    if content_hint and content_hint not in _FACE_HEAVY_CONTENT:
        thumbnail_risks.append("low_face_presence")

    # weak_expression: flat emotion detected by S3.2 retention predictor.
    if "flat_emotion" in retention_risks:
        thumbnail_risks.append("weak_expression")

    # low_signal: overall confidence below reliable threshold.
    if confidence < 0.30:
        thumbnail_risks.append("low_signal")

    # scene_fallback: no transcript — frame position is speculative.
    if source == "scene_score":
        thumbnail_risks.append("scene_fallback")

    return {
        "preferred_offset_ratio": preferred_ratio,
        "confidence":             confidence,
        "reason":                 reason,
        "thumbnail_risks":        thumbnail_risks,
    }
