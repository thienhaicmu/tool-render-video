"""
timing_apply_safety.py — Safety gates for safe timing mutation apply. Phase 32.

Deterministic only. Never raises. All validation is local/offline.
No FFmpeg. No subtitle timing rewrite. No segment reorder.
"""
from __future__ import annotations

from typing import Any, Optional

from app.ai.timing.timing_apply_schema import (
    _ALLOWED_MUTATION_TYPES,
    _FORBIDDEN_MUTATION_TYPES,
    _MAX_SINGLE_DELTA_SEC,
    _MIN_CONFIDENCE,
)

# Minimum segment duration remaining after any timing mutation
_MIN_SEGMENT_DURATION_SEC: float = 2.0


def sanitize_timing_candidate(candidate: Any) -> dict:
    """Return a sanitized copy of a timing candidate dict. Never raises."""
    try:
        if not isinstance(candidate, dict):
            return {}
        result: dict = {}
        result["mutation_id"] = str(candidate.get("mutation_id") or "")
        result["mutation_type"] = str(
            candidate.get("mutation_type") or candidate.get("action") or ""
        )
        result["source_candidate_id"] = str(candidate.get("source_candidate_id") or "")
        result["confidence"] = float(candidate.get("confidence") or 0.0)

        if "start_sec" in candidate:
            result["start_sec"] = float(candidate["start_sec"])
        elif "start" in candidate:
            result["start_sec"] = float(candidate["start"])
        else:
            result["start_sec"] = None

        if "end_sec" in candidate:
            result["end_sec"] = float(candidate["end_sec"])
        elif "end" in candidate:
            result["end_sec"] = float(candidate["end"])
        else:
            result["end_sec"] = None

        result["delta_sec"] = float(
            candidate.get("delta_sec") or candidate.get("max_trim_seconds") or 0.0
        )
        result["reason"] = str(candidate.get("reason") or "")
        result["warnings"] = list(candidate.get("warnings") or [])
        return result
    except Exception:
        return {}


def is_timing_mutation_safe(candidate: dict, context: Optional[dict] = None) -> bool:
    """Return True only if all safety gates pass. Never raises."""
    try:
        if not isinstance(candidate, dict):
            return False

        mut_type = str(candidate.get("mutation_type") or "")

        # Hard reject forbidden types (NEVER bypassed)
        if mut_type in _FORBIDDEN_MUTATION_TYPES:
            return False

        # Require known allowed type
        if mut_type not in _ALLOWED_MUTATION_TYPES:
            return False

        # Confidence gate
        confidence = float(candidate.get("confidence") or 0.0)
        if confidence < _MIN_CONFIDENCE:
            return False

        # Delta bounds
        delta = float(candidate.get("delta_sec") or 0.0)
        if delta <= 0.0 or delta > _MAX_SINGLE_DELTA_SEC:
            return False

        start = candidate.get("start_sec")
        end = candidate.get("end_sec")

        # Negative timing guard
        if start is not None and float(start) < 0.0:
            return False

        # Safe segment duration guard — post-mutation duration must stay above minimum
        if start is not None and end is not None:
            remaining = float(end) - float(start) - delta
            if remaining < _MIN_SEGMENT_DURATION_SEC:
                return False

        # Context-based guards
        if context is not None:
            protected_windows = context.get("protected_windows") or []
            if start is not None and _overlaps_any_window(float(start), protected_windows):
                return False

            subtitle_dense = context.get("subtitle_dense_regions") or []
            if start is not None and _overlaps_any_window(float(start), subtitle_dense):
                return False

        return True
    except Exception:
        return False


def _overlaps_any_window(position: float, windows: list) -> bool:
    """Return True if position falls inside any [start, end] window. Never raises."""
    try:
        for w in windows:
            if not isinstance(w, dict):
                continue
            ws = float(w.get("start", -1))
            we = float(w.get("end", -1))
            if ws <= position <= we:
                return True
        return False
    except Exception:
        return False
