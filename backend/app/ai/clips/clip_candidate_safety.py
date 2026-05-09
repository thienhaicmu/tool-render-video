"""
clip_candidate_safety.py — Candidate timing and score safety validation. Phase 35.

All functions: never raise, return safe fallback on any error.
No FFmpeg mutation. No segment reorder. No playback_speed changes.
"""
from __future__ import annotations

import math
from typing import Optional

_GLOBAL_MIN_DURATION = 5.0    # absolute floor (seconds)
_GLOBAL_MAX_DURATION = 300.0  # absolute ceiling (seconds)

_SCORE_KEYS = ("retention_score", "story_score", "hook_score", "pacing_score", "creator_style_score")


def sanitize_candidate(candidate: dict) -> dict:
    """Return a sanitized copy of the candidate dict. Never raises."""
    try:
        c = dict(candidate)

        # Timing — clamp to non-negative, reject NaN/inf
        start = _safe_float(c.get("start_sec", 0.0), 0.0)
        end = _safe_float(c.get("end_sec", 0.0), 0.0)
        start = max(0.0, start)
        end = max(0.0, end)

        c["start_sec"] = start
        c["end_sec"] = end
        c["duration_sec"] = max(0.0, end - start)

        # Confidence: clamp 0–1
        c["confidence"] = _clamp(_safe_float(c.get("confidence", 0.0), 0.0), 0.0, 1.0)

        # Scores: clamp 0–100
        for key in _SCORE_KEYS:
            c[key] = _clamp(_safe_float(c.get(key, 0.0), 0.0), 0.0, 100.0)

        return c
    except Exception:
        return dict(candidate)


def is_candidate_safe(candidate: dict, context: Optional[dict] = None) -> bool:
    """Return True if the candidate passes all safety checks. Never raises."""
    try:
        if not isinstance(candidate, dict):
            return False

        ctx = context or {}

        # ── Check RAW timing values first — reject NaN/inf/negative ──────────
        try:
            raw_start = float(candidate.get("start_sec", 0.0))
            raw_end   = float(candidate.get("end_sec",   0.0))
        except Exception:
            return False

        if not (math.isfinite(raw_start) and math.isfinite(raw_end)):
            return False
        if raw_start < 0.0 or raw_end < 0.0:
            return False
        if raw_end <= raw_start:
            return False

        # ── Sanitize then validate duration bounds ────────────────────────────
        c = sanitize_candidate(candidate)
        duration = float(c.get("duration_sec", 0.0))

        if not math.isfinite(duration) or duration <= 0.0:
            return False

        min_dur = max(_GLOBAL_MIN_DURATION, float(ctx.get("min_duration_sec", _GLOBAL_MIN_DURATION)))
        max_dur = min(_GLOBAL_MAX_DURATION, float(ctx.get("max_duration_sec", _GLOBAL_MAX_DURATION)))
        max_dur = max(max_dur, min_dur)

        if duration < min_dur:
            return False
        if duration > max_dur:
            return False

        return True
    except Exception:
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(value: object, default: float) -> float:
    try:
        v = float(value)  # type: ignore[arg-type]
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
