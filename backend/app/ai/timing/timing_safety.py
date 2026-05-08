"""
timing_safety.py — Safety gates for timing mutation candidates. Phase 19.

Deterministic only. Never raises. No timing mutation.
"""
from __future__ import annotations

from typing import Any, Optional

from app.ai.timing.timing_schema import (
    TimingMutationCandidate,
    _MAX_TRIM_SECONDS,
    _MIN_CONFIDENCE,
    _MIN_REGION_DURATION,
)

# Actions that are advisory-only — safe_to_apply must remain False
# hold_hook: advisory intent only (strengthen the hook, not trim it)
_ADVISORY_ONLY_ACTIONS: frozenset[str] = frozenset({"no_change", "none", "hold_hook"})


def clamp_trim_seconds(value: Any, max_value: float = _MAX_TRIM_SECONDS) -> float:
    """Return value clamped to [0.0, max_value]. Returns 0.0 on any error."""
    try:
        return max(0.0, min(float(max_value), float(value)))
    except Exception:
        return 0.0


def is_candidate_safe(
    candidate: TimingMutationCandidate,
    context: Optional[dict] = None,
) -> bool:
    """Return True only when all safety gates pass.

    Gates (all must pass):
    - confidence >= _MIN_CONFIDENCE (0.70)
    - action not in advisory-only set (no_change, none)
    - region duration (end - start) >= _MIN_REGION_DURATION (3.0 s)
    - start >= 0 (never trim before clip begins)
    - max_trim_seconds <= _MAX_TRIM_SECONDS (1.5 s)
    """
    try:
        if float(candidate.confidence) < _MIN_CONFIDENCE:
            return False
        if candidate.action in _ADVISORY_ONLY_ACTIONS:
            return False
        duration = float(candidate.end) - float(candidate.start)
        if duration < _MIN_REGION_DURATION:
            return False
        if float(candidate.start) < 0:
            return False
        if float(candidate.max_trim_seconds) > _MAX_TRIM_SECONDS:
            return False
        return True
    except Exception:
        return False
