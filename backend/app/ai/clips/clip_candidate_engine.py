"""
clip_candidate_engine.py — Deterministic AI clip candidate discovery engine. Phase 35.

Discovers and ranks candidate clip windows from AI metadata (story, retention,
timing, creator style). Never executes renders. Never mutates payload. Never
calls external APIs. No GPU requirement. No internet dependency.

Public API:
    discover_clip_candidates(edit_plan, payload=None, context=None) -> AIClipCandidatePack
"""
from __future__ import annotations

import logging
import math
from typing import Any, Optional

from app.ai.clips.clip_candidate_schema import AIClipCandidate, AIClipCandidatePack
from app.ai.clips.clip_candidate_safety import is_candidate_safe, sanitize_candidate

logger = logging.getLogger("app.ai.clips")

# ── Scoring weights (composite = weighted sum, max 100) ───────────────────────
_W_RETENTION = 0.30
_W_STORY     = 0.20
_W_HOOK      = 0.25
_W_PACING    = 0.15
_W_STYLE     = 0.10

# Story segment types → value contribution to story_score
_SEGMENT_VALUE: dict[str, float] = {
    "hook":     90.0,
    "climax":   85.0,
    "payoff":   80.0,
    "tension":  65.0,
    "build_up": 55.0,
    "setup":    40.0,
    "outro":    30.0,
    "unknown":  20.0,
}

# Narrative flows that reward hook detection
_HOOK_REWARD_FLOWS = frozenset({"climax_first", "hook_open", "viral_hook"})

# Duration bounds defaults
_DEFAULT_MIN_DUR = 15.0
_DEFAULT_MAX_DUR = 60.0
_DEFAULT_LIMIT   = 5


# ── Public entry point ────────────────────────────────────────────────────────

def discover_clip_candidates(
    edit_plan: Any,
    payload: Optional[Any] = None,
    context: Optional[dict] = None,
) -> AIClipCandidatePack:
    """Discover and rank clip candidates from edit plan metadata.

    Never raises. Returns an empty pack (enabled=False) when discovery is
    disabled or when no valid candidates can be found.
    """
    try:
        return _discover(edit_plan, payload, context or {})
    except Exception as exc:
        logger.warning("clip_candidate_discovery_failed: %s", exc)
        return AIClipCandidatePack(
            available=False,
            enabled=False,
            mode="discovery_only",
            warnings=[f"discovery_error:{type(exc).__name__}"],
        )


# ── Core discovery ────────────────────────────────────────────────────────────

def _discover(
    edit_plan: Any,
    payload: Optional[Any],
    context: dict,
) -> AIClipCandidatePack:
    # ── Config from payload or context ───────────────────────────────────────
    enabled = bool(
        getattr(payload, "ai_clip_discovery_enabled", False)
        if payload is not None
        else context.get("ai_clip_discovery_enabled", False)
    )
    if not enabled:
        logger.debug("clip_candidate_discovery_skipped: disabled")
        return AIClipCandidatePack(
            available=True,
            enabled=False,
            mode="discovery_only",
            warnings=["discovery_disabled"],
        )

    min_dur = _clamp_f(
        _get_attr(payload, "ai_clip_min_duration_sec", context.get("min_duration_sec", _DEFAULT_MIN_DUR)),
        5.0, 180.0,
    )
    max_dur = _clamp_f(
        _get_attr(payload, "ai_clip_max_duration_sec", context.get("max_duration_sec", _DEFAULT_MAX_DUR)),
        10.0, 300.0,
    )
    max_dur = max(max_dur, min_dur)
    limit = int(_clamp_f(
        _get_attr(payload, "ai_clip_candidate_limit", context.get("candidate_limit", _DEFAULT_LIMIT)),
        1.0, 20.0,
    ))

    safety_ctx = {"min_duration_sec": min_dur, "max_duration_sec": max_dur}

    # ── Pull AI metadata from edit plan ──────────────────────────────────────
    story              = _safe_dict(getattr(edit_plan, "story", None))
    retention          = _safe_dict(getattr(edit_plan, "retention", None))
    creator_style_adap = _safe_dict(getattr(edit_plan, "creator_style_adaptation", None))
    timing_apply       = _safe_dict(getattr(edit_plan, "timing_apply", None))
    camera_motion_apply = _safe_dict(getattr(edit_plan, "camera_motion_apply", None))
    subtitle_text_apply = _safe_dict(getattr(edit_plan, "subtitle_text_apply", None))
    pacing             = getattr(edit_plan, "pacing", None)
    selected_segments  = list(getattr(edit_plan, "selected_segments", None) or [])

    # ── Build candidate windows ───────────────────────────────────────────────
    windows = _collect_windows(selected_segments, story, min_dur, max_dur)
    if not windows:
        logger.debug("clip_candidate_discovery: no windows found")
        return AIClipCandidatePack(
            available=True,
            enabled=True,
            mode="discovery_only",
            warnings=["no_candidate_windows_found"],
        )

    # ── Precompute global signals ─────────────────────────────────────────────
    overall_retention = float(retention.get("overall_retention_score", 50.0) if retention else 50.0)
    risk_regions      = list(retention.get("risk_regions", []) if retention else [])
    story_segs        = list(story.get("segments", []) if story else [])
    narrative_flow    = str(story.get("narrative_flow", "unknown") if story else "unknown")
    style_confidence  = float(creator_style_adap.get("confidence", 0.0) if creator_style_adap else 0.0)
    timing_applied    = bool(timing_apply.get("enabled") if timing_apply else False)
    camera_applied    = bool(camera_motion_apply.get("enabled") if camera_motion_apply else False)
    pacing_energy     = _safe_f(getattr(pacing, "energy_level", None), 0.5)
    pacing_bpm        = _safe_f(getattr(pacing, "bpm", None), 0.0)

    # Total duration hint for hook scoring
    all_ends  = [w["end"] for w in windows]
    total_dur = max(all_ends) if all_ends else 0.0

    # ── Score and validate each window ────────────────────────────────────────
    candidates: list[AIClipCandidate] = []
    for idx, w in enumerate(windows):
        cid  = f"clip_{idx:02d}"
        c    = _score_window(
            cid, w, idx,
            overall_retention, risk_regions, story_segs, narrative_flow,
            style_confidence, pacing_energy, pacing_bpm, total_dur,
            timing_applied, camera_applied,
        )
        raw  = c.to_dict()
        sane = sanitize_candidate(raw)
        c.confidence       = sane["confidence"]
        c.retention_score  = sane["retention_score"]
        c.story_score      = sane["story_score"]
        c.hook_score       = sane["hook_score"]
        c.pacing_score     = sane["pacing_score"]
        c.creator_style_score = sane["creator_style_score"]
        c.safe = is_candidate_safe(sane, safety_ctx)
        candidates.append(c)

    # ── Keep only safe, rank by composite score ───────────────────────────────
    safe_candidates = [c for c in candidates if c.safe]
    ranked = sorted(safe_candidates, key=_composite, reverse=True)[:limit]

    if not ranked:
        return AIClipCandidatePack(
            available=True,
            enabled=True,
            mode="discovery_only",
            warnings=["no_safe_candidates_after_validation"],
        )

    recommended_id = ranked[0].candidate_id

    logger.info(
        "ai_clip_candidate_discovery_enabled candidates=%d safe=%d recommended=%s",
        len(candidates), len(ranked), recommended_id,
    )

    return AIClipCandidatePack(
        available=True,
        enabled=True,
        mode="discovery_only",
        candidates=ranked,
        recommended_candidate_id=recommended_id,
    )


# ── Window collection ─────────────────────────────────────────────────────────

def _collect_windows(
    selected_segments: list,
    story: dict,
    min_dur: float,
    max_dur: float,
) -> list[dict]:
    """Collect candidate windows from selected_segments and story segments."""
    windows: list[dict] = []
    seen: set[tuple] = set()

    def _add(start: float, end: float, label: str, source: str) -> None:
        s = round(max(0.0, start), 3)
        e = round(max(0.0, end), 3)
        dur = e - s
        if dur < min_dur or dur > max_dur:
            return
        key = (s, e)
        if key in seen:
            return
        seen.add(key)
        windows.append({"start": s, "end": e, "label": label, "source": source})

    # Primary: selected_segments (already AI-selected clip windows)
    for seg in selected_segments:
        try:
            s = float(getattr(seg, "start", None) or 0.0)
            e = float(getattr(seg, "end", None) or 0.0)
            reason = str(getattr(seg, "reason", "") or "")
            _add(s, e, reason or "ai_selected", "selected_segment")
        except Exception:
            continue

    # Secondary: story segments with explicit timing
    for seg_d in (story.get("segments", []) if story else []):
        if not isinstance(seg_d, dict):
            continue
        try:
            s = float(seg_d.get("start", 0.0))
            e = float(seg_d.get("end", 0.0))
            stype = str(seg_d.get("type", "unknown"))
            _add(s, e, stype, "story_segment")
        except Exception:
            continue

    return windows


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score_window(
    cid: str,
    w: dict,
    idx: int,
    overall_retention: float,
    risk_regions: list,
    story_segs: list,
    narrative_flow: str,
    style_confidence: float,
    pacing_energy: float,
    pacing_bpm: float,
    total_dur: float,
    timing_applied: bool,
    camera_applied: bool,
) -> AIClipCandidate:
    start = float(w["start"])
    end   = float(w["end"])
    dur   = end - start
    label = str(w.get("label", ""))

    reasons: list[str] = []
    warnings: list[str] = []

    # ── Retention score ───────────────────────────────────────────────────────
    ret_score = float(overall_retention)
    overlap_penalty = 0.0
    for region in risk_regions:
        if not isinstance(region, dict):
            continue
        try:
            rs = float(region.get("start", 0.0))
            re = float(region.get("end", 0.0))
            overlap = _overlap_sec(start, end, rs, re)
            if overlap > 0.0:
                risk_val = float(region.get("risk", 0.5))
                severity = str(region.get("severity", "medium"))
                sev_mult = {"high": 1.5, "medium": 1.0, "low": 0.5}.get(severity, 1.0)
                overlap_penalty += risk_val * sev_mult * (overlap / dur) * 25.0
        except Exception:
            continue
    ret_score = max(0.0, ret_score - overlap_penalty)

    if overlap_penalty < 5.0:
        reasons.append("low_retention_risk_region")
    elif overlap_penalty > 15.0:
        warnings.append("overlaps_retention_risk_region")

    # Bonus for timing-apply being active (suggests well-tuned timing)
    if timing_applied:
        ret_score = min(100.0, ret_score + 3.0)

    # ── Story score ───────────────────────────────────────────────────────────
    story_score = 30.0  # baseline
    best_seg_val = 0.0
    best_seg_type = "unknown"
    for seg_d in story_segs:
        if not isinstance(seg_d, dict):
            continue
        try:
            ss = float(seg_d.get("start", 0.0))
            se = float(seg_d.get("end", 0.0))
            stype = str(seg_d.get("type", "unknown"))
            overlap = _overlap_sec(start, end, ss, se)
            if overlap > 0.0:
                val = _SEGMENT_VALUE.get(stype, 20.0)
                if val > best_seg_val:
                    best_seg_val = val
                    best_seg_type = stype
        except Exception:
            continue

    story_score = max(story_score, best_seg_val)
    if best_seg_type in ("hook", "climax", "payoff"):
        reasons.append(f"contains_{best_seg_type}_segment")

    # Narrative flow bonus
    if narrative_flow in _HOOK_REWARD_FLOWS and start / max(total_dur, 1.0) < 0.3:
        story_score = min(100.0, story_score + 8.0)

    # Camera guidance bonus
    if camera_applied:
        story_score = min(100.0, story_score + 3.0)

    # ── Hook score ────────────────────────────────────────────────────────────
    hook_score = 0.0
    position_ratio = start / max(total_dur, 1.0) if total_dur > 0.0 else 0.0

    if position_ratio < 0.10:
        hook_score = 90.0
        reasons.append("early_hook_window")
    elif position_ratio < 0.20:
        hook_score = 75.0
        reasons.append("opening_hook_region")
    elif position_ratio < 0.35:
        hook_score = 55.0
    elif position_ratio < 0.60:
        hook_score = 40.0
    elif position_ratio < 0.80:
        hook_score = 60.0  # climax zone
    else:
        hook_score = 30.0

    if best_seg_type == "hook":
        hook_score = min(100.0, hook_score + 15.0)
    elif best_seg_type in ("climax", "payoff"):
        hook_score = min(100.0, hook_score + 10.0)

    if narrative_flow in _HOOK_REWARD_FLOWS and position_ratio < 0.15:
        hook_score = min(100.0, hook_score + 10.0)

    # ── Pacing score ──────────────────────────────────────────────────────────
    pacing_score = 50.0
    if pacing_energy > 0.0:
        pacing_score = _clamp_f(pacing_energy * 100.0, 20.0, 95.0)
    if pacing_bpm >= 140:
        pacing_score = min(100.0, pacing_score + 8.0)
        reasons.append("high_bpm_pacing")
    elif pacing_bpm >= 100:
        pacing_score = min(100.0, pacing_score + 4.0)

    # Subtitle text optimization bonus (cleaner text = better clip)
    if subtitle_text_applied := _is_subtitle_text_active(w):  # noqa: F841
        pacing_score = min(100.0, pacing_score + 2.0)

    # ── Creator style score ───────────────────────────────────────────────────
    creator_style_score = _clamp_f(style_confidence * 100.0, 0.0, 100.0)

    # ── Composite confidence ──────────────────────────────────────────────────
    composite = (
        ret_score   * _W_RETENTION +
        story_score * _W_STORY     +
        hook_score  * _W_HOOK      +
        pacing_score* _W_PACING    +
        creator_style_score * _W_STYLE
    )
    confidence = _clamp_f(composite / 100.0, 0.0, 1.0)

    return AIClipCandidate(
        candidate_id=cid,
        label=label or best_seg_type,
        start_sec=start,
        end_sec=end,
        duration_sec=dur,
        confidence=confidence,
        retention_score=_clamp_f(ret_score, 0.0, 100.0),
        story_score=_clamp_f(story_score, 0.0, 100.0),
        hook_score=_clamp_f(hook_score, 0.0, 100.0),
        pacing_score=_clamp_f(pacing_score, 0.0, 100.0),
        creator_style_score=_clamp_f(creator_style_score, 0.0, 100.0),
        safe=False,  # set by caller after sanitize + is_candidate_safe
        reasons=reasons,
        warnings=warnings,
    )


def _is_subtitle_text_active(w: dict) -> bool:
    return w.get("source", "") == "story_segment"


# ── Ranking ───────────────────────────────────────────────────────────────────

def _composite(c: AIClipCandidate) -> float:
    return (
        c.retention_score   * _W_RETENTION +
        c.story_score       * _W_STORY     +
        c.hook_score        * _W_HOOK      +
        c.pacing_score      * _W_PACING    +
        c.creator_style_score * _W_STYLE
    )


# ── Utilities ─────────────────────────────────────────────────────────────────

def _overlap_sec(a_start: float, a_end: float, b_start: float, b_end: float) -> float:
    overlap_start = max(a_start, b_start)
    overlap_end   = min(a_end, b_end)
    return max(0.0, overlap_end - overlap_start)


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
