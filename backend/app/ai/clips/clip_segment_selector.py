"""
clip_segment_selector.py — Deterministic AI clip segment selector. Phase 36.

Converts Phase 35 clip candidate discovery metadata into selected segment plans.
Never executes renders. Never mutates payload. Never calls external APIs.
No GPU. No internet. Deterministic output.

Public API:
    select_clip_segments(edit_plan, payload=None, context=None) -> AIClipSegmentSelection
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

from app.ai.clips.clip_segment_schema import AIClipSegmentPlan, AIClipSegmentSelection
from app.ai.clips.clip_segment_safety import is_segment_plan_safe, sanitize_segment_plan

try:
    from app.ai.analyzers.diversity_analyzer import (
        build_candidate_context as _div_build_ctx,
        compute_diversity_penalty as _div_penalty,
        DIVERSITY_INTELLIGENCE_ENABLED as _DIVERSITY_ENABLED,
    )
    _DIVERSITY_AVAILABLE = True
except ImportError:
    _DIVERSITY_AVAILABLE = False
    _DIVERSITY_ENABLED = False

    def _div_build_ctx(*a, **kw) -> dict: return {}   # type: ignore[misc]
    def _div_penalty(*a, **kw) -> float: return 0.0   # type: ignore[misc]

logger = logging.getLogger("app.ai.clips")

# ── Composite score weights (mirror Phase 35 engine) ─────────────────────────
_W_RETENTION = 0.30
_W_STORY     = 0.20
_W_HOOK      = 0.25
_W_PACING    = 0.15
_W_STYLE     = 0.10

# Overlap fraction threshold above which a candidate is considered a duplicate
_OVERLAP_THRESHOLD = 0.50

# Duration bounds defaults
_DEFAULT_MIN_DUR     = 15.0
_DEFAULT_MAX_DUR     = 60.0
_DEFAULT_TARGET_COUNT = 3


# ── Public entry point ────────────────────────────────────────────────────────

def select_clip_segments(
    edit_plan: Any,
    payload: Optional[Any] = None,
    context: Optional[dict] = None,
) -> AIClipSegmentSelection:
    """Select and rank clip segments from discovered candidates.

    Never raises. Returns a disabled selection when selection is off or
    no usable candidates are found.
    """
    try:
        return _select(edit_plan, payload, context or {})
    except Exception as exc:
        logger.warning("clip_segment_selection_failed: %s", exc)
        return AIClipSegmentSelection(
            available=False,
            enabled=False,
            mode="selection_only",
            warnings=[f"selection_error:{type(exc).__name__}"],
        )


# ── Core selection ────────────────────────────────────────────────────────────

def _select(
    edit_plan: Any,
    payload: Optional[Any],
    context: dict,
) -> AIClipSegmentSelection:
    # ── Config ────────────────────────────────────────────────────────────────
    enabled = bool(
        getattr(payload, "ai_clip_segment_selection_enabled", False)
        if payload is not None
        else context.get("ai_clip_segment_selection_enabled", False)
    )
    if not enabled:
        logger.debug("clip_segment_selection_skipped: disabled")
        return AIClipSegmentSelection(
            available=True,
            enabled=False,
            mode="selection_only",
            warnings=["selection_disabled"],
        )

    target_count = int(_clamp_f(
        _get_attr(payload, "ai_clip_target_count", context.get("target_count", _DEFAULT_TARGET_COUNT)),
        1.0, 20.0,
    ))
    min_dur = _clamp_f(
        _get_attr(payload, "ai_clip_min_duration_sec", context.get("min_duration_sec", _DEFAULT_MIN_DUR)),
        5.0, 180.0,
    )
    max_dur = _clamp_f(
        _get_attr(payload, "ai_clip_max_duration_sec", context.get("max_duration_sec", _DEFAULT_MAX_DUR)),
        10.0, 300.0,
    )
    max_dur = max(max_dur, min_dur)
    safety_ctx = {"min_duration_sec": min_dur, "max_duration_sec": max_dur}

    # ── Pull Phase 35 candidates ───────────────────────────────────────────────
    ccd = _safe_dict(getattr(edit_plan, "clip_candidate_discovery", None))
    candidates: list[dict] = [
        c for c in (ccd.get("candidates") or []) if isinstance(c, dict)
    ]

    # ── Fallback: use selected_segments when no Phase 35 candidates ───────────
    if not candidates:
        candidates = _build_fallback_candidates(edit_plan)

    if not candidates:
        logger.debug("clip_segment_selection: no candidates available")
        return AIClipSegmentSelection(
            available=True,
            enabled=True,
            mode="selection_only",
            warnings=["no_candidates_available"],
        )

    # ── Score and apply warning penalties ─────────────────────────────────────
    scored: list[dict] = []
    for c in candidates:
        base = _composite_score(c)
        penalty = _warning_penalty(c)
        scored.append({
            "candidate": c,
            "adjusted_score": max(0.0, base - penalty),
        })

    # Deterministic sort: score desc, candidate_id asc as tiebreaker
    scored.sort(
        key=lambda x: (-x["adjusted_score"], str(x["candidate"].get("candidate_id", "")))
    )

    # Total duration estimate for position_ratio (diversity context).
    all_ends = [
        _safe_f(item["candidate"].get("end_sec", 0.0), 0.0) for item in scored
    ]
    total_dur_est = max(all_ends) if all_ends else 1.0
    top_score     = scored[0]["adjusted_score"] if scored else 100.0

    # ── Select, dedup, and reject ─────────────────────────────────────────────
    # S2.4: Greedy per-round selection so diversity penalties can influence
    # ordering correctly.  Each round: apply diversity-adjusted scores to all
    # remaining candidates, pick the best non-overlapping safe one.
    # Pool is ≤ 20 candidates (ai_clip_candidate_limit), so O(n²) is trivial.
    selected_windows: list[tuple[float, float]] = []
    selected_plans:   list[AIClipSegmentPlan]  = []
    selected_ctxs:    list[dict]               = []
    rejected:         list[dict]               = []
    remaining = list(scored)

    while remaining and len(selected_plans) < target_count:
        best_item:  dict | None = None
        best_adj    = -1.0

        for item in remaining:
            c     = item["candidate"]
            score = item["adjusted_score"]
            start = _safe_f(c.get("start_sec", 0.0), 0.0)
            end   = _safe_f(c.get("end_sec",   0.0), 0.0)

            if _is_overlapping(start, end, selected_windows):
                continue

            seg_raw_check = _build_seg_raw(c, score)
            if not is_segment_plan_safe(seg_raw_check, safety_ctx):
                continue

            # Diversity-adjusted comparison score (never stored in plan).
            if _DIVERSITY_AVAILABLE and _DIVERSITY_ENABLED and selected_ctxs:
                hook_proxy = _hook_type_from_reasons(list(c.get("reasons", [])))
                div_ctx    = _div_build_ctx(
                    hook_type=hook_proxy,
                    phases=[],
                    position_ratio=start / max(total_dur_est, 1.0),
                )
                div_pen = _div_penalty(
                    div_ctx, selected_ctxs,
                    goal=context.get("goal", ""),
                    top_score=top_score,
                    candidate_score=score,
                    clip_count=target_count,
                )
                adj = score - div_pen
            else:
                adj = score

            if adj > best_adj:
                best_adj  = adj
                best_item = item

        if best_item is None:
            break

        remaining.remove(best_item)
        c     = best_item["candidate"]
        score = best_item["adjusted_score"]   # original score for plan output
        start = _safe_f(c.get("start_sec", 0.0), 0.0)
        end   = _safe_f(c.get("end_sec",   0.0), 0.0)
        seg_raw = _build_seg_raw(c, score)

        # Final safety gate (deterministic re-check; passed above so always True).
        if not is_segment_plan_safe(seg_raw, safety_ctx):
            rejected.append({**seg_raw, "reject_reason": "safety_check_failed"})
            continue

        rank = len(selected_plans) + 1
        plan = AIClipSegmentPlan(
            segment_id=f"seg_{rank:02d}",
            candidate_id=str(c.get("candidate_id", "")),
            label=str(c.get("label", "")),
            start_sec=start,
            end_sec=end,
            duration_sec=end - start,
            selected=True,
            rank=rank,
            confidence=_clamp_f(c.get("confidence", 0.0), 0.0, 1.0),
            score=_clamp_f(score, 0.0, 100.0),
            source_scores={
                "retention_score":    _clamp_f(c.get("retention_score",    0.0), 0.0, 100.0),
                "story_score":        _clamp_f(c.get("story_score",        0.0), 0.0, 100.0),
                "hook_score":         _clamp_f(c.get("hook_score",         0.0), 0.0, 100.0),
                "pacing_score":       _clamp_f(c.get("pacing_score",       0.0), 0.0, 100.0),
                "creator_style_score":_clamp_f(c.get("creator_style_score",0.0), 0.0, 100.0),
            },
            safe=True,
            reasons=list(c.get("reasons", [])),
            warnings=list(c.get("warnings", [])),
        )
        selected_plans.append(plan)
        selected_windows.append((start, end))
        if _DIVERSITY_AVAILABLE and _DIVERSITY_ENABLED:
            hook_proxy = _hook_type_from_reasons(list(c.get("reasons", [])))
            selected_ctxs.append(_div_build_ctx(
                hook_type=hook_proxy,
                phases=[],
                position_ratio=start / max(total_dur_est, 1.0),
            ))

    # Capture remaining as rejected (target_count_reached or exhausted).
    for item in remaining:
        c     = item["candidate"]
        score = item["adjusted_score"]
        seg_raw = _build_seg_raw(c, score)
        start = _safe_f(c.get("start_sec", 0.0), 0.0)
        end   = _safe_f(c.get("end_sec",   0.0), 0.0)
        if _is_overlapping(start, end, selected_windows):
            reason = "overlap_with_selected"
        elif len(selected_plans) >= target_count:
            reason = "target_count_reached"
        else:
            reason = "exhausted"
        rejected.append({**seg_raw, "reject_reason": reason})

    logger.info(
        "ai_clip_segment_selection_enabled selected=%d rejected=%d target=%d",
        len(selected_plans), len(rejected), target_count,
    )
    for plan in selected_plans:
        logger.info(
            "ai_clip_segment_selected segment_id=%s candidate_id=%s "
            "start=%.2f end=%.2f score=%.2f",
            plan.segment_id, plan.candidate_id,
            plan.start_sec, plan.end_sec, plan.score,
        )
    for rej in rejected:
        logger.debug(
            "ai_clip_segment_rejected candidate_id=%s reason=%s",
            rej.get("candidate_id", ""), rej.get("reject_reason", ""),
        )

    return AIClipSegmentSelection(
        available=True,
        enabled=True,
        mode="selection_only",
        selected_segments=selected_plans,
        rejected_candidates=rejected,
    )


# ── Fallback candidate builder ────────────────────────────────────────────────

def _build_fallback_candidates(edit_plan: Any) -> list[dict]:
    """Build minimal candidate dicts from edit_plan.selected_segments. Never raises."""
    try:
        segs = list(getattr(edit_plan, "selected_segments", None) or [])
        out: list[dict] = []
        for i, seg in enumerate(segs):
            try:
                start = _safe_f(getattr(seg, "start", None), 0.0)
                end   = _safe_f(getattr(seg, "end",   None), 0.0)
                score = _safe_f(getattr(seg, "score", 50.0), 50.0)
                dur   = end - start
                if dur <= 0.0:
                    continue
                out.append({
                    "candidate_id": f"fallback_{i:02d}",
                    "label": str(getattr(seg, "reason", "") or "fallback"),
                    "start_sec": start,
                    "end_sec": end,
                    "duration_sec": dur,
                    "confidence": 0.5,
                    "retention_score": _clamp_f(score, 0.0, 100.0),
                    "story_score": 50.0,
                    "hook_score": 50.0,
                    "pacing_score": 50.0,
                    "creator_style_score": 50.0,
                    "safe": True,
                    "reasons": ["fallback_from_selected_segments"],
                    "warnings": [],
                })
            except Exception:
                continue
        return out
    except Exception:
        return []


# ── Diversity helpers ─────────────────────────────────────────────────────────

def _hook_type_from_reasons(reasons: list[str]) -> str:
    """Map Phase 35 story-segment reason labels to a hook_type proxy for diversity."""
    for r in reasons:
        if "hook" in r:
            return "story"       # hook segment → story hook proxy
        if "climax" in r:
            return "surprise"    # climax → surprise/reaction proxy
        if "payoff" in r:
            return "result_first"  # payoff → result_first proxy
        if "early_hook_window" in r:
            return "curiosity"   # positional early hook → curiosity proxy
    return "none"


# ── Overlap detection ─────────────────────────────────────────────────────────

def _is_overlapping(
    start: float,
    end: float,
    windows: list[tuple[float, float]],
) -> bool:
    dur = end - start
    if dur <= 0.0:
        return False
    for (ws, we) in windows:
        overlap = max(0.0, min(end, we) - max(start, ws))
        shorter = min(dur, we - ws)
        if shorter > 0.0 and (overlap / shorter) > _OVERLAP_THRESHOLD:
            return True
    return False


# ── Scoring ───────────────────────────────────────────────────────────────────

def _composite_score(c: dict) -> float:
    return (
        _clamp_f(c.get("retention_score",    0.0), 0.0, 100.0) * _W_RETENTION +
        _clamp_f(c.get("story_score",        0.0), 0.0, 100.0) * _W_STORY     +
        _clamp_f(c.get("hook_score",         0.0), 0.0, 100.0) * _W_HOOK      +
        _clamp_f(c.get("pacing_score",       0.0), 0.0, 100.0) * _W_PACING    +
        _clamp_f(c.get("creator_style_score",0.0), 0.0, 100.0) * _W_STYLE
    )


def _warning_penalty(c: dict) -> float:
    warns = list(c.get("warnings", []))
    penalty = 0.0
    if any("subtitle_overload" in w for w in warns):
        penalty += 8.0
    if any("silence_gap" in w or "overlaps_retention_risk" in w for w in warns):
        penalty += 5.0
    return penalty


# ── Raw segment dict builder ──────────────────────────────────────────────────

def _build_seg_raw(c: dict, score: float) -> dict:
    start = _safe_f(c.get("start_sec", 0.0), 0.0)
    end   = _safe_f(c.get("end_sec",   0.0), 0.0)
    return {
        "candidate_id": str(c.get("candidate_id", "")),
        "start_sec":    start,
        "end_sec":      end,
        "duration_sec": end - start,
        "confidence":   _clamp_f(c.get("confidence", 0.0), 0.0, 1.0),
        "score":        _clamp_f(score, 0.0, 100.0),
        "source_scores": {
            "retention_score":    _clamp_f(c.get("retention_score",    0.0), 0.0, 100.0),
            "story_score":        _clamp_f(c.get("story_score",        0.0), 0.0, 100.0),
            "hook_score":         _clamp_f(c.get("hook_score",         0.0), 0.0, 100.0),
            "pacing_score":       _clamp_f(c.get("pacing_score",       0.0), 0.0, 100.0),
            "creator_style_score":_clamp_f(c.get("creator_style_score",0.0), 0.0, 100.0),
        },
    }


# ── Utilities ─────────────────────────────────────────────────────────────────

def _safe_dict(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _safe_f(value: object, default: float) -> float:
    try:
        v = float(value)  # type: ignore[arg-type]
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _clamp_f(value: object, lo: float, hi: float) -> float:
    try:
        v = float(value)  # type: ignore[arg-type]
        return max(lo, min(hi, v if math.isfinite(v) else lo))
    except Exception:
        return lo


def _get_attr(obj: object, attr: str, default: object) -> object:
    if obj is None:
        return default
    val = getattr(obj, attr, None)
    return val if val is not None else default
