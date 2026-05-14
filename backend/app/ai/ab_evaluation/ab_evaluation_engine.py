"""
ab_evaluation_engine.py — Phase 60B A/B Render Evaluation.

Evaluation-only module. Compares an AI-ON candidate render's quality metadata
against an AI-OFF baseline to determine whether AI execution promotion improved
output quality.

NO automatic rerender.  NO render behavior change.  NO execution mutation.

Supported modes
---------------
A. Metadata compare mode
    Both baseline and candidate quality data are available.
    Computes per-dimension deltas, selects winner, generates reasoning.

B. Single-run candidate summary mode
    Only the AI-ON candidate metadata is available (no baseline stored).
    Returns available=False with candidate_summary.
    Does NOT claim improvement without baseline.

Public API
----------
    build_ab_evaluation(edit_plan, baseline=None, context=None) -> dict

Args:
    edit_plan: AIEditPlan or duck-typed object with quality dicts populated
               by Phases 52A–52D:
                   subtitle_quality_v2, camera_quality_v2,
                   hook_quality_v2, render_quality_v2,
               and Phase 60A:
                   ai_execution_metrics, ai_execution_summary
    baseline:  Optional dict describing a prior AI-OFF render.
               Shape A (flat quality):
                   {
                     "quality": {"subtitle": int, "camera": int,
                                 "hook": int, "overall": int},
                     "label": "ai_off"            # optional
                   }
               Shape B (raw quality dicts, same as edit_plan attributes):
                   {
                     "render_quality_v2":   {"overall": int, ...},
                     "subtitle_quality_v2": {"overall": int, ...},
                     "camera_quality_v2":   {"overall": int, ...},
                     "hook_quality_v2":     {"overall": int, ...},
                   }
               If None or empty → mode B (candidate summary only).
    context:   Optional {"job_id": str} for logging.

Winner selection (requires baseline)
--------------------
    overall_delta >= +3  → "ai_on"
    overall_delta <= -3  → "ai_off"
    -2 <= delta <= +2    → "tie"
    missing data         → "unknown"

Output shape (mode A — full comparison)
-----------------------------------------
    {
        "ai_ab_evaluation": {
            "available": true,
            "baseline": {
                "label": "ai_off",
                "quality": {"subtitle": 78, "camera": 80,
                            "hook": 76, "overall": 78}
            },
            "candidate": {
                "label": "ai_on",
                "quality": {"subtitle": 86, "camera": 84,
                            "hook": 81, "overall": 84},
                "ai_assistance_level": "high"
            },
            "delta": {"subtitle": 8, "camera": 4,
                      "hook": 5, "overall": 6},
            "winner": "ai_on",
            "confidence": 0.82,
            "reasoning": ["AI ON improved subtitle quality (+8) vs baseline.",
                          "Overall quality improved by 6 points."]
        }
    }

Output shape (mode B — baseline missing)
-----------------------------------------
    {
        "ai_ab_evaluation": {
            "available": false,
            "reason": "baseline_missing",
            "candidate_summary": {
                "label": "ai_on",
                "quality": {"subtitle": 84, "camera": 82,
                            "hook": 79, "overall": 82},
                "ai_assistance_level": "medium"
            },
            "baseline": {},
            "candidate": {},
            "delta": {},
            "winner": "unknown",
            "confidence": 0.0,
            "reasoning": ["Baseline missing — A/B winner cannot be determined."]
        }
    }

Safety contract
---------------
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ❌ No automatic rerender
    ✅ Reads edit_plan attributes and explicit baseline only
    ✅ Never claims AI improvement without baseline
    ✅ Deterministic: same inputs → same output
    ✅ All scores clamped to [0, 100]
    ✅ Confidence clamped to [0.0, 1.0]
    ✅ Returns fallback on any error
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.ab_evaluation")

# ---------------------------------------------------------------------------
# Winner thresholds (explicit, tested)
# ---------------------------------------------------------------------------
_WIN_THRESHOLD:  int = 3    # overall_delta >= +3  → ai_on
_LOSE_THRESHOLD: int = -3   # overall_delta <= -3  → ai_off
# -2 <= delta <= +2  → tie  (gap between WIN and LOSE is intentional dead-band)

# Allowed winner values
_WINNER_AI_ON:  str = "ai_on"
_WINNER_AI_OFF: str = "ai_off"
_WINNER_TIE:    str = "tie"
_WINNER_UNKNOWN: str = "unknown"

# Minimum number of quality dimensions to trust a comparison
_MIN_COMPARABLE_DIMS: int = 1

# Confidence weights (sum to 1.0)
_CONF_BASE:       float = 0.40
_CONF_DIM_MAX:    float = 0.20   # reward for having all 4 dims
_CONF_QUAL_MAX:   float = 0.20   # reward for high quality signal confidence
_CONF_EXEC_MAX:   float = 0.20   # reward for high execution metrics confidence


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_ab_evaluation(
    edit_plan: Any,
    baseline: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict:
    """Build A/B evaluation comparing AI-ON candidate against baseline.

    Returns:
        {"ai_ab_evaluation": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _evaluate(edit_plan, baseline, job_id)
    except Exception as exc:
        logger.warning("ab_evaluation_unexpected_error job_id=%s: %s", job_id, exc)
        return _fallback_report()


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def _evaluate(edit_plan: Any, baseline: Optional[dict], job_id: str) -> dict:
    # Extract candidate quality from current edit_plan
    candidate_quality = _extract_candidate_quality(edit_plan)
    candidate_has_data = any(v > 0 for v in candidate_quality.values())

    # Determine baseline availability — any of the four expected keys present is enough
    baseline_quality = _extract_baseline_quality(baseline) if baseline else {}
    _QUALITY_KEYS = frozenset({"subtitle", "camera", "hook", "overall"})
    baseline_available = bool(
        baseline_quality and _QUALITY_KEYS.intersection(baseline_quality)
    )

    # AI assistance level for candidate
    exec_summary = _attr_dict(edit_plan, "ai_execution_summary")
    ai_assistance = str(exec_summary.get("overall_ai_assistance") or "none")

    # ── Mode B: no baseline ───────────────────────────────────────────────
    if not baseline_available:
        candidate_summary = {
            "label":              "ai_on",
            "quality":            candidate_quality,
            "ai_assistance_level": ai_assistance,
        } if candidate_has_data else {}

        logger.debug(
            "ab_evaluation_no_baseline job_id=%s candidate_has_data=%s",
            job_id, candidate_has_data,
        )
        return {
            "ai_ab_evaluation": {
                "available":        False,
                "reason":           "baseline_missing",
                "candidate_summary": candidate_summary,
                "baseline":         {},
                "candidate":        {},
                "delta":            {},
                "winner":           _WINNER_UNKNOWN,
                "confidence":       0.0,
                "reasoning":        ["Baseline missing — A/B winner cannot be determined."],
            }
        }

    # ── Mode A: full comparison ────────────────────────────────────────────
    delta, comparable_dims = _compute_delta(baseline_quality, candidate_quality)
    winner = _select_winner(delta["overall"], comparable_dims)

    # Confidence uses quality signal confidence from edit_plan
    rqv2_conf = float(_attr_dict(edit_plan, "render_quality_v2").get("confidence") or 0.0)
    exec_metrics = _attr_dict(edit_plan, "ai_execution_metrics")
    exec_conf = float(exec_metrics.get("confidence") or 0.0)
    confidence = _compute_confidence(comparable_dims, rqv2_conf, exec_conf)

    baseline_label = str((baseline or {}).get("label") or "ai_off")
    reasoning = _generate_reasoning(delta, winner, ai_assistance)

    logger.info(
        "ab_evaluation_complete job_id=%s winner=%s delta_overall=%+d "
        "confidence=%.3f dims=%d",
        job_id, winner, delta["overall"], confidence, comparable_dims,
    )

    return {
        "ai_ab_evaluation": {
            "available": True,
            "baseline": {
                "label":   baseline_label,
                "quality": baseline_quality,
            },
            "candidate": {
                "label":              "ai_on",
                "quality":            candidate_quality,
                "ai_assistance_level": ai_assistance,
            },
            "delta":      delta,
            "winner":     winner,
            "confidence": confidence,
            "reasoning":  reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Quality extraction
# ---------------------------------------------------------------------------

def _extract_candidate_quality(edit_plan: Any) -> dict:
    """Extract flat quality scores from edit_plan Phase 52 dicts.

    Priority: render_quality_v2 composite scores first (unified signal),
    then individual quality v2 overall scores.
    """
    rqv2 = _attr_dict(edit_plan, "render_quality_v2")
    sqv2 = _attr_dict(edit_plan, "subtitle_quality_v2")
    cqv2 = _attr_dict(edit_plan, "camera_quality_v2")
    hqv2 = _attr_dict(edit_plan, "hook_quality_v2")

    subtitle = int(rqv2.get("subtitle_score") or sqv2.get("overall") or 0)
    camera   = int(rqv2.get("camera_score")   or cqv2.get("overall") or 0)
    hook     = int(rqv2.get("hook_score")     or hqv2.get("overall") or 0)
    overall  = int(rqv2.get("overall") or 0)

    # Derive overall from available dimensions if not directly present
    if not overall:
        available = [s for s in (subtitle, camera, hook) if s > 0]
        overall = round(sum(available) / len(available)) if available else 0

    return {
        "subtitle": _clamp(subtitle),
        "camera":   _clamp(camera),
        "hook":     _clamp(hook),
        "overall":  _clamp(overall),
    }


def _extract_baseline_quality(baseline: dict) -> dict:
    """Extract flat quality scores from a baseline dict.

    Supports two input shapes:
        Shape A: {"quality": {"subtitle": int, ...}}
        Shape B: {"render_quality_v2": {"overall": int, ...}, ...}
    """
    if not isinstance(baseline, dict):
        return {}

    # Shape A: explicit flat quality dict
    flat = baseline.get("quality")
    if isinstance(flat, dict) and flat:
        return {
            "subtitle": _clamp(int(flat.get("subtitle") or 0)),
            "camera":   _clamp(int(flat.get("camera")   or 0)),
            "hook":     _clamp(int(flat.get("hook")     or 0)),
            "overall":  _clamp(int(flat.get("overall")  or 0)),
        }

    # Shape B: raw quality dicts (mirrors edit_plan attribute layout)
    rqv2 = baseline.get("render_quality_v2") or {}
    sqv2 = baseline.get("subtitle_quality_v2") or {}
    cqv2 = baseline.get("camera_quality_v2")  or {}
    hqv2 = baseline.get("hook_quality_v2")    or {}

    subtitle = int(rqv2.get("subtitle_score") or sqv2.get("overall") or 0)
    camera   = int(rqv2.get("camera_score")   or cqv2.get("overall") or 0)
    hook     = int(rqv2.get("hook_score")     or hqv2.get("overall") or 0)
    overall  = int(rqv2.get("overall") or 0)

    if not overall:
        available = [s for s in (subtitle, camera, hook) if s > 0]
        overall = round(sum(available) / len(available)) if available else 0

    return {
        "subtitle": _clamp(subtitle),
        "camera":   _clamp(camera),
        "hook":     _clamp(hook),
        "overall":  _clamp(overall),
    }


# ---------------------------------------------------------------------------
# Delta, winner, confidence, reasoning
# ---------------------------------------------------------------------------

def _compute_delta(baseline: dict, candidate: dict) -> tuple[dict, int]:
    """Compute per-dimension deltas (candidate - baseline).

    Returns (delta_dict, comparable_dims_count).
    Allows negative deltas. Clamps result to [-100, 100].
    """
    dims = ("subtitle", "camera", "hook", "overall")
    delta: dict[str, int] = {}
    comparable = 0
    for dim in dims:
        b = baseline.get(dim, 0)
        c = candidate.get(dim, 0)
        if b > 0 or c > 0:
            comparable += 1
        d = c - b
        delta[dim] = max(-100, min(100, d))

    # overall dim counts separately from the three sub-dims
    comparable_sub_dims = sum(
        1 for dim in ("subtitle", "camera", "hook")
        if baseline.get(dim, 0) > 0 or candidate.get(dim, 0) > 0
    )
    return delta, comparable_sub_dims


def _select_winner(overall_delta: int, comparable_dims: int) -> str:
    if comparable_dims < _MIN_COMPARABLE_DIMS:
        return _WINNER_UNKNOWN
    if overall_delta >= _WIN_THRESHOLD:
        return _WINNER_AI_ON
    if overall_delta <= _LOSE_THRESHOLD:
        return _WINNER_AI_OFF
    return _WINNER_TIE


def _compute_confidence(
    comparable_dims: int,
    rqv2_conf: float,
    exec_conf: float,
) -> float:
    """Confidence in the A/B evaluation (0.0 → 1.0).

    Components:
        base                  = 0.40  (always, given baseline exists)
        dim_coverage_bonus    = 0.20 * (dims / 3)   up to 3 sub-dims
        quality_signal_bonus  = 0.20 * rqv2_conf
        execution_conf_bonus  = 0.20 * exec_conf
    """
    dim_bonus  = _CONF_DIM_MAX * min(1.0, comparable_dims / 3.0)
    qual_bonus = _CONF_QUAL_MAX * max(0.0, min(1.0, rqv2_conf))
    exec_bonus = _CONF_EXEC_MAX * max(0.0, min(1.0, exec_conf))

    conf = _CONF_BASE + dim_bonus + qual_bonus + exec_bonus
    return round(max(0.0, min(1.0, conf)), 4)


def _generate_reasoning(delta: dict, winner: str, ai_assistance: str) -> list[str]:
    """Generate honest, creator-facing reasoning lines.

    No raw JSON, no stack traces, no internal details, no unsupported claims.
    """
    lines: list[str] = []

    if winner == _WINNER_AI_ON:
        improved: list[str] = []
        if delta.get("subtitle", 0) >= _WIN_THRESHOLD:
            improved.append(f"subtitle quality (+{delta['subtitle']})")
        if delta.get("camera", 0) >= _WIN_THRESHOLD:
            improved.append(f"camera quality (+{delta['camera']})")
        if delta.get("hook", 0) >= _WIN_THRESHOLD:
            improved.append(f"hook strength (+{delta['hook']})")
        if improved:
            lines.append(f"AI ON improved {', '.join(improved)} vs baseline.")
        overall_d = delta.get("overall", 0)
        if overall_d >= _WIN_THRESHOLD:
            lines.append(f"Overall quality improved by {overall_d} points.")

    elif winner == _WINNER_AI_OFF:
        overall_d = abs(delta.get("overall", 0))
        lines.append(f"AI OFF scored {overall_d} points higher on overall quality.")
        declined: list[str] = []
        if delta.get("subtitle", 0) <= _LOSE_THRESHOLD:
            lines.append(
                f"Subtitle quality declined by {abs(delta['subtitle'])} points with AI ON."
            )
        if delta.get("camera", 0) <= _LOSE_THRESHOLD:
            lines.append(
                f"Camera quality declined by {abs(delta['camera'])} points with AI ON."
            )
        if delta.get("hook", 0) <= _LOSE_THRESHOLD:
            lines.append(
                f"Hook quality declined by {abs(delta['hook'])} points with AI ON."
            )

    elif winner == _WINNER_TIE:
        overall_d = delta.get("overall", 0)
        sign = f"+{overall_d}" if overall_d > 0 else str(overall_d)
        lines.append(
            f"AI ON and AI OFF produced similar quality (overall delta={sign})."
        )

    else:
        lines.append("Evaluation complete — see delta scores for details.")

    if not lines:
        lines.append("Evaluation complete — see delta scores for details.")

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


def _clamp(value: int) -> int:
    return max(0, min(100, int(value or 0)))


def _fallback_report() -> dict:
    return {
        "ai_ab_evaluation": {
            "available":        False,
            "baseline":         {},
            "candidate":        {},
            "delta":            {},
            "winner":           _WINNER_UNKNOWN,
            "confidence":       0.0,
            "reasoning":        [],
        }
    }
