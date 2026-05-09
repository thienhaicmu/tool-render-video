"""
clip_segment_safety.py — Segment plan timing and score safety validation. Phase 36.

All functions: never raise, return safe fallback on any error.
No FFmpeg mutation. No segment reorder. No render execution.
"""
from __future__ import annotations

import math
from typing import Optional

_GLOBAL_MIN_DURATION = 5.0    # absolute floor (seconds)
_GLOBAL_MAX_DURATION = 300.0  # absolute ceiling (seconds)

_SCORE_KEYS = ("retention_score", "story_score", "hook_score", "pacing_score", "creator_style_score")


def sanitize_segment_plan(segment: dict) -> dict:
    """Return a sanitized copy of the segment plan dict. Never raises."""
    try:
        s = dict(segment)

        # Timing — reject NaN/inf, clamp to non-negative
        start = _safe_float(s.get("start_sec", 0.0), 0.0)
        end   = _safe_float(s.get("end_sec",   0.0), 0.0)
        start = max(0.0, start)
        end   = max(0.0, end)

        s["start_sec"]   = start
        s["end_sec"]     = end
        s["duration_sec"] = max(0.0, end - start)

        # Confidence: clamp 0–1
        s["confidence"] = _clamp(_safe_float(s.get("confidence", 0.0), 0.0), 0.0, 1.0)

        # Score: clamp 0–100
        s["score"] = _clamp(_safe_float(s.get("score", 0.0), 0.0), 0.0, 100.0)

        # Source scores: clamp each 0–100
        raw_src = s.get("source_scores", {})
        if isinstance(raw_src, dict):
            s["source_scores"] = {
                k: _clamp(_safe_float(v, 0.0), 0.0, 100.0)
                for k, v in raw_src.items()
            }
        else:
            s["source_scores"] = {}

        return s
    except Exception:
        return dict(segment)


def is_segment_plan_safe(segment: dict, context: Optional[dict] = None) -> bool:
    """Return True if the segment plan passes all safety checks. Never raises."""
    try:
        if not isinstance(segment, dict):
            return False

        ctx = context or {}

        # ── Check RAW timing — reject NaN/inf/negative before sanitizing ─────
        try:
            raw_start = float(segment.get("start_sec", 0.0))
            raw_end   = float(segment.get("end_sec",   0.0))
        except Exception:
            return False

        if not (math.isfinite(raw_start) and math.isfinite(raw_end)):
            return False
        if raw_start < 0.0 or raw_end < 0.0:
            return False
        if raw_end <= raw_start:
            return False

        # ── Sanitize then validate duration bounds ────────────────────────────
        san = sanitize_segment_plan(segment)
        duration = float(san.get("duration_sec", 0.0))

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
