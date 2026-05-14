"""
render_outcome_tracking_engine.py — Phase 62A Render Outcome Tracking.

Deterministic, tracking-only module. Aggregates existing AI metadata to produce
a structured render_outcome_tracking object for audit, debug, and future learning.

NO render mutation.  NO influence mutation.  NO autonomous learning.  NO rerender.
NO external persistence / database write.  In-memory metadata-safe only.

Inputs (existing metadata only — no new render):
    ai_execution_metrics       (Phase 60A) — what AI did during execution
    ai_execution_summary       (Phase 60A) — compact execution flags
    ai_ab_evaluation           (Phase 60B) — A/B winner and quality deltas
    creator_benchmark_summary  (Phase 60C) — creator fit benchmark status
    creator_render_strategy    (Phase 61D) — fused creator strategy confidence
    render_quality_v2          (Phase 52D) — quality scores and confidence
    platform_quality_feedback  (Phase 57)  — platform quality signals
    ai_execution_mode          (Phase 60D) — resolved execution mode
    creator_preference_profile (Phase 50D) — creator_type and platform

Public API:
    build_render_outcome_tracking(edit_plan, context=None) -> dict

Output shape (available):
    {
        "render_outcome_tracking": {
            "available":      true,
            "render_id":      "rnd_3f8e1a2b",
            "creator_type":   "podcast",
            "platform":       "tiktok",
            "execution_mode": "balanced",
            "quality": {
                "subtitle": 84,
                "camera":   81,
                "hook":     79,
                "overall":  82
            },
            "ai_execution": {
                "subtitle_applied":    true,
                "camera_applied":      true,
                "segment_applied":     false,
                "quality_gate_blocks": 1
            },
            "ab_result": {
                "winner":        "ai_on",
                "overall_delta": 6
            },
            "benchmark_result": {
                "creator_fit":     "high",
                "benchmark_delta": 7
            },
            "ai_effectiveness": "strong",
            "overall_result":   "improved",
            "confidence": 0.84,
            "reasoning": [
                "AI ON delivered strong quality improvement vs baseline.",
                "Creator fit is strong for this archetype and creator type."
            ]
        }
    }

Output shape (fallback):
    {
        "render_outcome_tracking": {
            "available":  false,
            "confidence": 0.0,
            "reasoning":  []
        }
    }

Classification logic (deterministic, explicit thresholds):

    creator_fit  (from creator_benchmark_summary.benchmark_status):
        "high"   ← benchmark_status == "best_fit"
        "medium" ← benchmark_status == "improving"
        "low"    ← benchmark_status in ("needs_review", "unknown") or unavailable

    ai_effectiveness (from ai_ab_evaluation):
        "strong"   ← available AND winner=ai_on AND overall_delta >= 5
        "moderate" ← available AND winner=ai_on AND overall_delta >= 2
        "weak"     ← all other cases

    overall_result (from combination):
        "regression" ← available AND winner=ai_off
        "improved"   ← ai_effectiveness in ("strong", "moderate")
        "neutral"    ← all other cases

Safe render reference:
    render_id = "rnd_" + sha256(job_id)[:8]
    Never exposes internal IDs, file paths, or user identifiers.

Safety contract:
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ❌ No autonomous learning
    ❌ No external persistence
    ❌ No unsafe ID/path exposure
    ✅ Tracking-only — aggregates existing metadata
    ✅ Deterministic: same inputs → same output
    ✅ Returns fallback on any error
    ✅ Confidence clamped to [0.0, 1.0]
    ✅ Quality scores clamped to [0, 100]
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.outcome_tracking")

# ---------------------------------------------------------------------------
# Classification thresholds (explicit, tested)
# ---------------------------------------------------------------------------
_AB_STRONG_DELTA:   int = 5   # overall_delta >= 5 → strong
_AB_MODERATE_DELTA: int = 2   # overall_delta >= 2 → moderate (winner must be ai_on)

# Benchmark status → creator_fit label
_BENCHMARK_TO_FIT: dict[str, str] = {
    "best_fit":     "high",
    "improving":    "medium",
    "needs_review": "low",
    "unknown":      "low",
}

# Benchmark status → confidence contribution [0.0, 1.0]
_BENCHMARK_TO_CONF: dict[str, float] = {
    "best_fit":     0.90,
    "improving":    0.70,
    "needs_review": 0.40,
    "unknown":      0.00,
}

# Confidence blend weights (fixed denominator = sum = 1.0)
_W_QUALITY   = 0.30
_W_AB        = 0.30
_W_BENCHMARK = 0.20
_W_STRATEGY  = 0.20

# Maximum reasoning lines
_MAX_REASONING = 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_render_outcome_tracking(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build render outcome tracking metadata.

    Returns:
        {"render_outcome_tracking": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build(edit_plan, job_id)
    except Exception as exc:
        logger.warning(
            "render_outcome_tracking_unexpected_error job_id=%s: %s", job_id, exc
        )
        return _fallback()


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, job_id: str) -> dict:
    if edit_plan is None:
        return _fallback()

    # ── Read signal inputs ────────────────────────────────────────────────
    exec_summary = _get_dict(edit_plan, "ai_execution_summary")
    exec_metrics = _get_dict(edit_plan, "ai_execution_metrics")
    ab_eval      = _get_dict(edit_plan, "ai_ab_evaluation")
    benchmark    = _get_dict(edit_plan, "creator_benchmark_summary")
    crs          = _get_dict(edit_plan, "creator_render_strategy")
    rqv2         = _get_dict(edit_plan, "render_quality_v2")
    exec_mode_d  = _get_dict(edit_plan, "ai_execution_mode")
    creator_prof = _get_dict(edit_plan, "creator_preference_profile")

    # ── Creator type and platform ─────────────────────────────────────────
    creator_type = str(
        crs.get("creator_type") or
        benchmark.get("creator_type") or
        creator_prof.get("creator_type") or
        "unknown"
    ).lower()
    platform = str(creator_prof.get("platform") or "unknown").lower()

    # ── Execution mode ────────────────────────────────────────────────────
    execution_mode = str(exec_mode_d.get("resolved_mode") or "unknown").lower()

    # ── Quality scores ─────────────────────────────────────────────────────
    quality = _extract_quality(rqv2)

    # ── AI execution flags ─────────────────────────────────────────────────
    ai_execution = _extract_ai_execution(exec_summary, exec_metrics)

    # ── A/B result ─────────────────────────────────────────────────────────
    ab_available    = bool(ab_eval.get("available"))
    ab_winner       = str(ab_eval.get("winner") or "unknown")
    ab_delta_dict   = ab_eval.get("delta") or {}
    ab_overall_delta = int(ab_delta_dict.get("overall") or 0) if ab_available else 0

    ab_result = {
        "winner":        ab_winner if ab_available else "unknown",
        "overall_delta": ab_overall_delta,
    }

    # ── Benchmark result ──────────────────────────────────────────────────
    bench_available = bool(benchmark.get("available"))
    bench_status    = str(benchmark.get("benchmark_status") or "unknown")
    bench_delta     = int(benchmark.get("overall_delta") or 0) if bench_available else 0
    creator_fit     = _BENCHMARK_TO_FIT.get(bench_status, "low")

    benchmark_result = {
        "creator_fit":     creator_fit,
        "benchmark_delta": bench_delta,
    }

    # ── Outcome classifications ───────────────────────────────────────────
    ai_effectiveness = _classify_ai_effectiveness(ab_available, ab_winner, ab_overall_delta)
    overall_result   = _classify_overall_result(ab_available, ab_winner, ai_effectiveness)

    # ── Confidence blend ──────────────────────────────────────────────────
    quality_conf   = _clamp_f(rqv2.get("confidence"))
    ab_conf        = _clamp_f(ab_eval.get("confidence")) if ab_available else 0.0
    benchmark_conf = _BENCHMARK_TO_CONF.get(bench_status, 0.0)
    strategy_conf  = _clamp_f(crs.get("confidence"))
    confidence     = _blend_confidence(quality_conf, ab_conf, benchmark_conf, strategy_conf)

    # ── Reasoning ─────────────────────────────────────────────────────────
    reasoning = _build_reasoning(
        overall_result, ai_effectiveness, creator_fit,
        ab_available, ab_winner, quality, exec_summary,
    )

    # ── Safe render reference ──────────────────────────────────────────────
    render_id = _safe_render_ref(job_id)

    logger.info(
        "render_outcome_tracking_built job_id=%s creator=%s mode=%s "
        "overall_result=%s ai_effectiveness=%s creator_fit=%s confidence=%.3f",
        job_id, creator_type, execution_mode,
        overall_result, ai_effectiveness, creator_fit, confidence,
    )

    return {
        "render_outcome_tracking": {
            "available":        True,
            "render_id":        render_id,
            "creator_type":     creator_type,
            "platform":         platform,
            "execution_mode":   execution_mode,
            "quality":          quality,
            "ai_execution":     ai_execution,
            "ab_result":        ab_result,
            "benchmark_result": benchmark_result,
            "ai_effectiveness": ai_effectiveness,
            "overall_result":   overall_result,
            "confidence":       confidence,
            "reasoning":        reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Quality extraction
# ---------------------------------------------------------------------------

def _extract_quality(rqv2: dict) -> dict:
    subtitle = int(rqv2.get("subtitle_score") or rqv2.get("subtitle") or 0)
    camera   = int(rqv2.get("camera_score")   or rqv2.get("camera")   or 0)
    hook     = int(rqv2.get("hook_score")     or rqv2.get("hook")     or 0)
    overall  = int(rqv2.get("overall") or 0)

    if not overall and any((subtitle, camera, hook)):
        dims = [s for s in (subtitle, camera, hook) if s > 0]
        overall = round(sum(dims) / len(dims)) if dims else 0

    return {
        "subtitle": _clamp_i(subtitle),
        "camera":   _clamp_i(camera),
        "hook":     _clamp_i(hook),
        "overall":  _clamp_i(overall),
    }


# ---------------------------------------------------------------------------
# AI execution extraction
# ---------------------------------------------------------------------------

def _extract_ai_execution(exec_summary: dict, exec_metrics: dict) -> dict:
    subtitle_applied = bool(exec_summary.get("subtitle_apply"))
    camera_applied   = bool(exec_summary.get("camera_apply"))
    segment_applied  = bool(exec_summary.get("segment_apply"))

    qg_blocks = int(exec_summary.get("quality_gate_blocks") or 0)
    if not qg_blocks:
        qg = exec_metrics.get("quality_gate") or {}
        qg_blocks = sum(
            1 for k in ("subtitle_blocked", "camera_blocked", "segment_blocked")
            if qg.get(k)
        )

    return {
        "subtitle_applied":    subtitle_applied,
        "camera_applied":      camera_applied,
        "segment_applied":     segment_applied,
        "quality_gate_blocks": qg_blocks,
    }


# ---------------------------------------------------------------------------
# Classification functions (deterministic, explicit thresholds, tested)
# ---------------------------------------------------------------------------

def _classify_ai_effectiveness(
    ab_available: bool,
    winner: str,
    overall_delta: int,
) -> str:
    """Classify AI effectiveness from A/B result.

    strong:   ab_available AND winner=ai_on AND delta >= 5
    moderate: ab_available AND winner=ai_on AND delta >= 2
    weak:     all other cases
    """
    if not ab_available or winner != "ai_on":
        return "weak"
    if overall_delta >= _AB_STRONG_DELTA:
        return "strong"
    if overall_delta >= _AB_MODERATE_DELTA:
        return "moderate"
    return "weak"


def _classify_overall_result(
    ab_available: bool,
    winner: str,
    ai_effectiveness: str,
) -> str:
    """Classify overall render outcome.

    regression: ab_available AND winner=ai_off
    improved:   ai_effectiveness in (strong, moderate)
    neutral:    all other cases
    """
    if ab_available and winner == "ai_off":
        return "regression"
    if ai_effectiveness in ("strong", "moderate"):
        return "improved"
    return "neutral"


# ---------------------------------------------------------------------------
# Confidence blend
# ---------------------------------------------------------------------------

def _blend_confidence(
    quality_conf: float,
    ab_conf: float,
    benchmark_conf: float,
    strategy_conf: float,
) -> float:
    """Fixed-weight blend. Missing signals contribute 0.0 (lowers total confidence)."""
    total = (
        quality_conf   * _W_QUALITY +
        ab_conf        * _W_AB +
        benchmark_conf * _W_BENCHMARK +
        strategy_conf  * _W_STRATEGY
    )
    denominator = _W_QUALITY + _W_AB + _W_BENCHMARK + _W_STRATEGY
    conf = total / denominator if denominator > 0 else 0.0
    return round(max(0.0, min(1.0, conf)), 4)


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    overall_result: str,
    ai_effectiveness: str,
    creator_fit: str,
    ab_available: bool,
    ab_winner: str,
    quality: dict,
    exec_summary: dict,
) -> list[str]:
    lines: list[str] = []

    # Primary: overall result
    if overall_result == "improved":
        if ai_effectiveness == "strong":
            lines.append("AI ON delivered strong quality improvement vs baseline.")
        else:
            lines.append("AI ON improved render quality vs baseline.")
    elif overall_result == "regression":
        lines.append("AI OFF scored higher — AI may not fit this creator type currently.")
    else:
        if not ab_available:
            lines.append("No baseline available — outcome comparison not possible.")
        else:
            lines.append("AI ON and AI OFF produced similar quality — outcome is neutral.")

    # Creator fit
    if creator_fit == "high":
        lines.append("Creator fit is strong for this archetype and creator type.")
    elif creator_fit == "medium":
        lines.append("Creator fit is improving — benchmark threshold not yet reached.")
    elif creator_fit == "low":
        lines.append("Benchmark confidence is low — creator fit needs review.")

    # Quality highlights
    subtitle_q = quality.get("subtitle", 0)
    camera_q   = quality.get("camera", 0)
    if subtitle_q >= 80 and camera_q >= 80:
        lines.append("Subtitle and camera quality both above threshold.")
    elif subtitle_q >= 80:
        lines.append("Subtitle quality above threshold.")
    elif camera_q >= 80:
        lines.append("Camera quality above threshold.")

    # AI execution applied note
    subtitle_applied = bool(exec_summary.get("subtitle_apply"))
    camera_applied   = bool(exec_summary.get("camera_apply"))
    if subtitle_applied and camera_applied:
        lines.append("AI subtitle and camera promotion both applied.")
    elif subtitle_applied:
        lines.append("AI subtitle promotion applied.")
    elif camera_applied:
        lines.append("AI camera promotion applied.")

    return lines[:_MAX_REASONING]


# ---------------------------------------------------------------------------
# Safe render reference
# ---------------------------------------------------------------------------

def _safe_render_ref(job_id: str) -> str:
    """Opaque, deterministic render reference derived from job_id via one-way hash.

    Never exposes the internal job_id, file paths, or user identifiers.
    Format: rnd_{first8hex}
    """
    h = hashlib.sha256(str(job_id).encode("utf-8")).hexdigest()[:8]
    return f"rnd_{h}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dict(edit_plan: Any, attr: str) -> dict:
    try:
        val = (
            edit_plan.get(attr) if isinstance(edit_plan, dict)
            else getattr(edit_plan, attr, None)
        )
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _clamp_f(val: Any) -> float:
    try:
        return max(0.0, min(1.0, float(val or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _clamp_i(val: Any) -> int:
    try:
        return max(0, min(100, int(val or 0)))
    except (TypeError, ValueError):
        return 0


def _fallback() -> dict:
    return {
        "render_outcome_tracking": {
            "available":  False,
            "confidence": 0.0,
            "reasoning":  [],
        }
    }
