"""
creator_benchmark_engine.py — Phase 60C Creator Benchmark Suite.

Benchmarking/validation-only module. For a given render, evaluates AI quality
performance against creator archetype benchmarks using A/B evaluation signals
from Phase 60B.

NO render mutation.  NO automatic rerender.  NO payload change.

Public API
----------
    build_creator_benchmark(edit_plan, context=None) -> dict

Args:
    edit_plan: AIEditPlan or duck-typed object with:
                   creator_preference_profile (Phase 50D)
                   ai_ab_evaluation (Phase 60B)
    context:   Optional {"job_id": str} for logging.

Benchmark status thresholds
---------------------------
    best_fit:     overall_delta >= +5  AND  winner_rate >= 0.70
    improving:    overall_delta  > +2  AND  winner_rate >= 0.60  (middle ground)
    needs_review: overall_delta <= +2  OR   winner_rate  < 0.60
    unknown:      no A/B evaluation available or winner=unknown

Winner-rate mapping (single render)
-------------------------------------
    ai_on   → 1.0
    tie     → 0.5
    ai_off  → 0.0
    unknown → None  (→ unknown status)

Supported creator archetypes
------------------------------
    podcast, talking_head, educational, viral_short_form,
    storytelling, interview, motivation

Output shape (available)
------------------------
    {
        "creator_benchmark_summary": {
            "available":        true,
            "creator_type":     "podcast",
            "archetype_label":  "Podcast",
            "benchmark_status": "best_fit",
            "overall_delta":    6,
            "winner":           "ai_on",
            "winner_rate":      1.0,
            "reasoning":        ["AI ON exceeded the benchmark threshold for Podcast (delta=+6, winner_rate=1.00)."]
        }
    }

Output shape (unavailable)
--------------------------
    {
        "creator_benchmark_summary": {
            "available":        false,
            "reason":           "ab_evaluation_unavailable",
            "creator_type":     "podcast",
            "archetype_label":  "Podcast",
            "benchmark_status": "unknown",
            "overall_delta":    null,
            "winner":           "unknown",
            "winner_rate":      null,
            "reasoning":        ["A/B evaluation unavailable — benchmark cannot be assessed."]
        }
    }

Safety contract
---------------
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ✅ Reads edit_plan attributes only
    ✅ Deterministic: same inputs → same output
    ✅ Returns fallback on any error
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.creator_benchmark")

# ---------------------------------------------------------------------------
# Thresholds (explicit, tested)
# ---------------------------------------------------------------------------
_BEST_FIT_DELTA:        int   = 5     # overall_delta >= +5 required for best_fit
_NEEDS_REVIEW_DELTA:    int   = 2     # overall_delta <= +2 triggers needs_review
_BEST_FIT_WIN_RATE:     float = 0.70  # winner_rate >= 0.70 required for best_fit
_NEEDS_REVIEW_WIN_RATE: float = 0.60  # winner_rate < 0.60 triggers needs_review

# Benchmark status labels
_STATUS_BEST_FIT:     str = "best_fit"
_STATUS_IMPROVING:    str = "improving"
_STATUS_NEEDS_REVIEW: str = "needs_review"
_STATUS_UNKNOWN:      str = "unknown"

# Supported creator archetypes
_CREATOR_ARCHETYPES: frozenset[str] = frozenset({
    "podcast",
    "talking_head",
    "educational",
    "viral_short_form",
    "storytelling",
    "interview",
    "motivation",
})

_ARCHETYPE_LABELS: dict[str, str] = {
    "podcast":          "Podcast",
    "talking_head":     "Talking Head",
    "educational":      "Educational",
    "viral_short_form": "Viral Short-Form",
    "storytelling":     "Storytelling",
    "interview":        "Interview",
    "motivation":       "Motivation",
}

# Single-render winner → winner_rate mapping
_WINNER_RATES: dict[str, Optional[float]] = {
    "ai_on":   1.0,
    "tie":     0.5,
    "ai_off":  0.0,
    "unknown": None,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_creator_benchmark(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build creator benchmark summary for this render.

    Returns:
        {"creator_benchmark_summary": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _benchmark(edit_plan, job_id)
    except Exception as exc:
        logger.warning("creator_benchmark_unexpected_error job_id=%s: %s", job_id, exc)
        return _fallback_report()


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def _benchmark(edit_plan: Any, job_id: str) -> dict:
    # Creator type from Phase 50D
    creator_profile = _attr_dict(edit_plan, "creator_preference_profile")
    creator_type = str(creator_profile.get("creator_type") or "unknown").lower()
    if creator_type not in _CREATOR_ARCHETYPES:
        creator_type = "unknown"
    archetype_label = _ARCHETYPE_LABELS.get(
        creator_type,
        creator_type.replace("_", " ").title() if creator_type != "unknown" else "Unknown",
    )

    # A/B evaluation from Phase 60B
    ab_eval = _attr_dict(edit_plan, "ai_ab_evaluation")
    ab_available = bool(ab_eval.get("available"))

    if not ab_available:
        reason = str(ab_eval.get("reason") or "ab_evaluation_unavailable")
        logger.debug(
            "creator_benchmark_no_ab_eval job_id=%s creator_type=%s reason=%s",
            job_id, creator_type, reason,
        )
        return {
            "creator_benchmark_summary": {
                "available":        False,
                "reason":           reason,
                "creator_type":     creator_type,
                "archetype_label":  archetype_label,
                "benchmark_status": _STATUS_UNKNOWN,
                "overall_delta":    None,
                "winner":           "unknown",
                "winner_rate":      None,
                "reasoning":        ["A/B evaluation unavailable — benchmark cannot be assessed."],
            }
        }

    # Extract delta and winner
    delta_dict = ab_eval.get("delta") or {}
    overall_delta = int(delta_dict.get("overall") or 0)
    winner = str(ab_eval.get("winner") or "unknown")
    winner_rate = _WINNER_RATES.get(winner)  # None for unrecognised winner values

    # Compute status
    status = _compute_status(overall_delta, winner_rate)
    reasoning = _generate_reasoning(status, archetype_label, overall_delta, winner_rate)

    logger.info(
        "creator_benchmark_complete job_id=%s creator_type=%s status=%s "
        "delta=%+d winner=%s winner_rate=%s",
        job_id, creator_type, status, overall_delta, winner,
        f"{winner_rate:.2f}" if winner_rate is not None else "None",
    )

    return {
        "creator_benchmark_summary": {
            "available":        True,
            "creator_type":     creator_type,
            "archetype_label":  archetype_label,
            "benchmark_status": status,
            "overall_delta":    overall_delta,
            "winner":           winner,
            "winner_rate":      winner_rate,
            "reasoning":        reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------

def _compute_status(overall_delta: int, winner_rate: Optional[float]) -> str:
    """Compute benchmark_status from delta and winner_rate.

    best_fit:     delta >= +5  AND  winner_rate >= 0.70
    needs_review: delta <= +2  OR   winner_rate < 0.60
    improving:    delta  > +2  AND  winner_rate >= 0.60  (middle ground)
    unknown:      winner_rate is None (no reliable winner signal)
    """
    if winner_rate is None:
        return _STATUS_UNKNOWN

    if overall_delta >= _BEST_FIT_DELTA and winner_rate >= _BEST_FIT_WIN_RATE:
        return _STATUS_BEST_FIT

    if overall_delta <= _NEEDS_REVIEW_DELTA or winner_rate < _NEEDS_REVIEW_WIN_RATE:
        return _STATUS_NEEDS_REVIEW

    return _STATUS_IMPROVING


# ---------------------------------------------------------------------------
# Reasoning generation
# ---------------------------------------------------------------------------

def _generate_reasoning(
    status: str,
    archetype_label: str,
    overall_delta: int,
    winner_rate: Optional[float],
) -> list[str]:
    lines: list[str] = []
    wr_str = f"{winner_rate:.2f}" if winner_rate is not None else "n/a"
    delta_str = f"{overall_delta:+d}"

    if status == _STATUS_BEST_FIT:
        lines.append(
            f"AI ON exceeded the benchmark threshold for {archetype_label} "
            f"(delta={delta_str}, winner_rate={wr_str})."
        )
    elif status == _STATUS_IMPROVING:
        lines.append(
            f"AI ON is improving for {archetype_label} but has not reached the best-fit threshold "
            f"(delta={delta_str}, winner_rate={wr_str})."
        )
    elif status == _STATUS_NEEDS_REVIEW:
        if overall_delta <= _NEEDS_REVIEW_DELTA and winner_rate is not None and winner_rate < _NEEDS_REVIEW_WIN_RATE:
            lines.append(
                f"AI ON underperformed for {archetype_label} — "
                f"both delta and win rate are below threshold "
                f"(delta={delta_str}, winner_rate={wr_str})."
            )
        elif overall_delta <= _NEEDS_REVIEW_DELTA:
            lines.append(
                f"AI ON delta is at or below the review threshold for {archetype_label} "
                f"(delta={delta_str})."
            )
        else:
            lines.append(
                f"AI ON win rate is below the review threshold for {archetype_label} "
                f"(winner_rate={wr_str})."
            )
    else:
        lines.append("Benchmark status unknown — insufficient data.")

    if not lines:
        lines.append("Benchmark evaluation complete — see delta and winner_rate for details.")
    return lines


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attr_dict(obj: Any, attr: str) -> dict:
    """Duck-typed attribute access returning a dict or {}."""
    try:
        val = obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _fallback_report() -> dict:
    return {
        "creator_benchmark_summary": {
            "available":        False,
            "creator_type":     "unknown",
            "archetype_label":  "Unknown",
            "benchmark_status": _STATUS_UNKNOWN,
            "overall_delta":    None,
            "winner":           "unknown",
            "winner_rate":      None,
            "reasoning":        [],
        }
    }
