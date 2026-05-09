"""
quality_scoring.py — Deterministic render quality scoring engine. Phase 45.

Public API:
    score_render_quality(output_metadata, edit_plan=None, context=None)
        -> AIRenderQualityScore

Scoring model (weighted blend → overall_score):
    pacing_quality         20%
    subtitle_readability   20%
    camera_smoothness      15%
    hook_strength          15%
    retention_quality      15%
    creator_consistency    10%
    market_fit              5%

Rules:
- Deterministic only
- Never raises
- No file deletion or overwrite
- No render execution
- No payload mutation
- Scores clamped 0–100; confidence clamped 0–1
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from app.ai.quality.quality_schema import AIRenderQualityScore
from app.ai.quality.quality_safety import _clamp_score, _clamp_confidence

logger = logging.getLogger("app.ai.quality.scoring")

# Dimension weights (must sum to 1.0)
_WEIGHTS = {
    "pacing_quality": 0.20,
    "subtitle_readability": 0.20,
    "camera_smoothness": 0.15,
    "hook_strength": 0.15,
    "retention_quality": 0.15,
    "creator_consistency": 0.10,
    "market_fit": 0.05,
}

# Penalty applied to outputs that are marked as failed
_FAILED_OUTPUT_PENALTY = 30.0

# Baseline score when no signals are available
_BASELINE = 50.0


def score_render_quality(
    output_metadata: Any,
    edit_plan: Any = None,
    context: Optional[dict] = None,
) -> AIRenderQualityScore:
    """Score a single render output using AI plan signals. Never raises.

    Args:
        output_metadata: dict-like with output info (output_id, failed, score, etc.)
        edit_plan:       AIEditPlan (or None) with all Phase 1–44 signals.
        context:         Optional session context.

    Returns:
        AIRenderQualityScore with per-dimension scores and overall weighted blend.
    """
    try:
        return _score(output_metadata, edit_plan, context)
    except Exception as exc:
        logger.debug("quality_scoring_error: %s", exc)
        return AIRenderQualityScore(
            score_id=str(uuid.uuid4())[:12],
            warnings=[f"quality_scoring_error:{type(exc).__name__}"],
        )


def _score(
    output_metadata: Any,
    edit_plan: Any,
    context: Optional[dict],
) -> AIRenderQualityScore:
    ctx = context or {}
    meta = output_metadata if isinstance(output_metadata, dict) else {}

    output_id = str(meta.get("output_id") or meta.get("part_no") or ctx.get("output_id") or "")
    output_path = str(meta.get("output_path") or meta.get("file") or "")
    is_failed = bool(meta.get("failed") or meta.get("error"))
    score_id = str(uuid.uuid4())[:12]

    flags: list[str] = []
    warnings: list[str] = []
    explanation: list[str] = []

    # Extract dimension scores
    pacing = _score_pacing(edit_plan, meta, flags)
    subtitle = _score_subtitle(edit_plan, meta, flags)
    camera = _score_camera(edit_plan, meta, flags)
    hook = _score_hook(edit_plan, meta, flags)
    retention = _score_retention(edit_plan, meta, flags)
    creator = _score_creator_consistency(edit_plan, meta, flags)
    market = _score_market_fit(edit_plan, meta, flags)

    # Apply failed-output penalty
    if is_failed:
        penalty_factor = (_FAILED_OUTPUT_PENALTY / 100.0)
        pacing = _clamp_score(pacing * (1 - penalty_factor))
        subtitle = _clamp_score(subtitle * (1 - penalty_factor))
        camera = _clamp_score(camera * (1 - penalty_factor))
        hook = _clamp_score(hook * (1 - penalty_factor))
        retention = _clamp_score(retention * (1 - penalty_factor))
        creator = _clamp_score(creator * (1 - penalty_factor))
        market = _clamp_score(market * (1 - penalty_factor))
        flags.append("failed_output_penalty_applied")
        warnings.append("output_failed_quality_penalized")

    # Weighted overall score
    overall = _clamp_score(
        pacing * _WEIGHTS["pacing_quality"]
        + subtitle * _WEIGHTS["subtitle_readability"]
        + camera * _WEIGHTS["camera_smoothness"]
        + hook * _WEIGHTS["hook_strength"]
        + retention * _WEIGHTS["retention_quality"]
        + creator * _WEIGHTS["creator_consistency"]
        + market * _WEIGHTS["market_fit"]
    )

    confidence = _compute_confidence(edit_plan, meta)

    # Build explanation
    if overall >= 80:
        explanation.append("High quality render output")
    elif overall >= 60:
        explanation.append("Good quality render output")
    elif overall >= 40:
        explanation.append("Acceptable quality render output")
    else:
        explanation.append("Low quality render output — review recommended")

    if pacing >= 70:
        explanation.append("Pacing quality strong")
    if subtitle >= 70:
        explanation.append("Subtitle readability strong")
    if hook >= 70:
        explanation.append("Hook strength strong")
    if is_failed:
        explanation.append("Output failed — quality penalized")

    logger.debug(
        "ai_render_quality_score_created output_id=%s overall=%.1f confidence=%.2f",
        output_id, overall, confidence,
    )

    return AIRenderQualityScore(
        score_id=score_id,
        output_id=output_id,
        output_path=output_path,
        overall_score=overall,
        pacing_quality=pacing,
        subtitle_readability=subtitle,
        camera_smoothness=camera,
        hook_strength=hook,
        retention_quality=retention,
        creator_consistency=creator,
        market_fit=market,
        confidence=confidence,
        quality_flags=flags,
        warnings=warnings,
        explanation=explanation,
    )


# ── Dimension scorers ─────────────────────────────────────────────────────────

def _score_pacing(edit_plan: Any, meta: dict, flags: list) -> float:
    """Score pacing quality from timing_apply, retention, story, market signals. Never raises."""
    try:
        base = _BASELINE
        signals = 0

        # market pacing bias
        moi = _get_dict(edit_plan, "market_optimization_intelligence")
        pac_bias = moi.get("pacing_market_bias", {})
        if pac_bias.get("weight", 0) > 0:
            base = min(100.0, base + pac_bias["weight"] * 50)
            signals += 1

        # timing_apply quality
        ta = _get_dict(edit_plan, "timing_apply")
        if ta.get("available") or ta.get("enabled"):
            base = min(100.0, base + 8.0)
            signals += 1
            if ta.get("warnings"):
                base -= 5.0
                flags.append("timing_apply_warnings")

        # story pacing signal
        so = _get_dict(edit_plan, "story_optimization")
        if so.get("available"):
            base = min(100.0, base + 5.0)
            signals += 1

        # retention dead-air avoidance
        ret = _get_dict(edit_plan, "retention")
        risk = ret.get("risk_regions") or []
        if isinstance(risk, list) and len(risk) > 3:
            base -= 5.0
            flags.append("high_retention_risk")
        elif isinstance(risk, list) and len(risk) == 0:
            base = min(100.0, base + 3.0)

        # output-level score hint
        seg_score = _meta_score(meta)
        if seg_score > 0:
            base = base * 0.7 + seg_score * 0.3

        return _clamp_score(base)
    except Exception:
        return _BASELINE


def _score_subtitle(edit_plan: Any, meta: dict, flags: list) -> float:
    """Score subtitle readability from subtitle_text_apply, subtitle_execution, market. Never raises."""
    try:
        base = _BASELINE
        sta = _get_dict(edit_plan, "subtitle_text_apply")
        se = _get_dict(edit_plan, "subtitle_execution")
        moi = _get_dict(edit_plan, "market_optimization_intelligence")
        sub_bias = moi.get("subtitle_market_bias", {})

        if sta.get("available") or sta.get("enabled"):
            base = min(100.0, base + 10.0)
        if se.get("available"):
            base = min(100.0, base + 5.0)
        if se.get("warnings"):
            base -= 4.0
            flags.append("subtitle_execution_warnings")
        # check for subtitle overload
        se_meta = se.get("execution_metadata") or {}
        if se_meta.get("overload") or "subtitle_overload" in str(se.get("warnings", [])):
            base -= 8.0
            flags.append("subtitle_overload_detected")

        if sub_bias.get("weight", 0) > 0:
            base = min(100.0, base + sub_bias["weight"] * 40)

        # adaptive subtitle preference
        aci = _get_dict(edit_plan, "adaptive_creator_intelligence")
        sub_conf = aci.get("creator_profile", {}).get("subtitle_confidence", 0.0)
        if sub_conf >= 0.3:
            base = min(100.0, base + sub_conf * 10)

        return _clamp_score(base)
    except Exception:
        return _BASELINE


def _score_camera(edit_plan: Any, meta: dict, flags: list) -> float:
    """Score camera smoothness from camera_motion_apply, visual rhythm. Never raises."""
    try:
        base = _BASELINE
        cma = _get_dict(edit_plan, "camera_motion_apply")
        bve = _get_dict(edit_plan, "beat_visual_execution")
        moi = _get_dict(edit_plan, "market_optimization_intelligence")
        cam_bias = moi.get("camera_market_bias", {})

        if cma.get("available") or cma.get("enabled"):
            base = min(100.0, base + 10.0)
            if cma.get("safety_check_passed") is False:
                base -= 8.0
                flags.append("camera_motion_safety_issue")
        if bve.get("available"):
            base = min(100.0, base + 5.0)

        if cam_bias.get("weight", 0) > 0:
            base = min(100.0, base + cam_bias["weight"] * 35)

        return _clamp_score(base)
    except Exception:
        return _BASELINE


def _score_hook(edit_plan: Any, meta: dict, flags: list) -> float:
    """Score hook strength from story, retention, clip_candidate_discovery, market. Never raises."""
    try:
        base = _BASELINE
        story = _get_dict(edit_plan, "story")
        ret = _get_dict(edit_plan, "retention")
        ccd = _get_dict(edit_plan, "clip_candidate_discovery")
        moi = _get_dict(edit_plan, "market_optimization_intelligence")
        hook_bias = moi.get("hook_market_bias", {})

        # story hook score
        hook_score = float(story.get("hook_score", 0) or 0)
        if hook_score > 0:
            base = base * 0.5 + hook_score * 100 * 0.5

        # retention hook overlap
        if ret.get("hook_score"):
            ret_hook = float(ret.get("hook_score") or 0)
            base = base * 0.7 + ret_hook * 100 * 0.3

        # clip candidate hook discovery
        cands = ccd.get("candidates") or []
        hook_cands = [c for c in cands if isinstance(c, dict) and c.get("has_hook")]
        if hook_cands:
            base = min(100.0, base + len(hook_cands) * 3.0)
            flags.append("hook_candidates_detected")

        if hook_bias.get("weight", 0) > 0:
            base = min(100.0, base + hook_bias["weight"] * 40)

        return _clamp_score(base)
    except Exception:
        return _BASELINE


def _score_retention(edit_plan: Any, meta: dict, flags: list) -> float:
    """Score retention quality from retention intelligence, feedback, output_ranking. Never raises."""
    try:
        base = _BASELINE
        ret = _get_dict(edit_plan, "retention")
        cfi = _get_dict(edit_plan, "creator_feedback_intelligence")
        orr = _get_dict(edit_plan, "output_ranking")

        # overall retention score
        ret_score = float(ret.get("overall_score") or ret.get("retention_score") or 0)
        if ret_score > 0:
            base = base * 0.4 + ret_score * 100 * 0.6

        # feedback quality signal
        patterns = cfi.get("learned_feedback_patterns", {}) or {}
        exports = int(patterns.get("total_exports", 0) or 0)
        if exports > 0:
            base = min(100.0, base + min(exports * 2.0, 10.0))

        # output ranking signal
        if orr.get("available") and orr.get("best_output_id"):
            base = min(100.0, base + 5.0)

        return _clamp_score(base)
    except Exception:
        return _BASELINE


def _score_creator_consistency(edit_plan: Any, meta: dict, flags: list) -> float:
    """Score creator consistency from retrieval, adaptive intelligence, style adaptation. Never raises."""
    try:
        base = _BASELINE
        cr = _get_dict(edit_plan, "creator_retrieval")
        aci = _get_dict(edit_plan, "adaptive_creator_intelligence")
        csa = _get_dict(edit_plan, "creator_style_adaptation")

        if cr.get("enabled") and cr.get("matches"):
            match_count = len(cr["matches"])
            base = min(100.0, base + min(match_count * 4.0, 16.0))

        # adaptive style confidence
        profile = aci.get("creator_profile", {}) or {}
        style_conf = float(profile.get("style_confidence", 0) or 0)
        if style_conf >= 0.2:
            base = min(100.0, base + style_conf * 15)

        # style adaptation
        if csa.get("adapted_style"):
            base = min(100.0, base + 5.0)

        return _clamp_score(base)
    except Exception:
        return _BASELINE


def _score_market_fit(edit_plan: Any, meta: dict, flags: list) -> float:
    """Score market fit from market_optimization_intelligence. Never raises."""
    try:
        base = _BASELINE
        moi = _get_dict(edit_plan, "market_optimization_intelligence")

        if not moi.get("enabled"):
            return base

        profile = moi.get("market_profile", {}) or {}
        market_confidence = float(profile.get("confidence", 0) or 0)
        if market_confidence > 0:
            base = base * 0.3 + market_confidence * 100 * 0.7

        # bonus for all biases being active
        active_biases = sum(
            1 for key in ("subtitle_market_bias", "pacing_market_bias",
                          "camera_market_bias", "hook_market_bias")
            if moi.get(key, {}).get("weight", 0) > 0
        )
        base = min(100.0, base + active_biases * 3.0)

        return _clamp_score(base)
    except Exception:
        return _BASELINE


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_dict(edit_plan: Any, attr: str) -> dict:
    """Safely retrieve a dict attribute from edit_plan. Never raises."""
    try:
        if edit_plan is None:
            return {}
        val = getattr(edit_plan, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _meta_score(meta: dict) -> float:
    """Extract a 0–100 quality hint from output metadata. Never raises."""
    try:
        score = meta.get("score") or meta.get("ranking_score") or 0
        return _clamp_score(float(score) * 100 if float(score) <= 1.0 else float(score))
    except Exception:
        return 0.0


def _compute_confidence(edit_plan: Any, meta: dict) -> float:
    """Compute confidence from signal richness. Never raises."""
    try:
        signals = 0
        if edit_plan is not None:
            for attr in ("timing_apply", "subtitle_text_apply", "camera_motion_apply",
                         "retention", "story", "creator_retrieval",
                         "market_optimization_intelligence", "adaptive_creator_intelligence"):
                d = _get_dict(edit_plan, attr)
                if d and (d.get("available") or d.get("enabled") or len(d) > 1):
                    signals += 1
        if meta:
            signals += 1
        return _clamp_confidence(min(1.0, signals / 9.0))
    except Exception:
        return 0.0
