"""
quality_gate_engine.py — Phase 59D Quality-Gated Influence.

Reads quality signals (subtitle_quality_v2, camera_quality_v2, hook_quality_v2,
render_quality_v2, platform_quality_feedback) to gate, block, or soften the
execution promotions from Phases 59A (subtitle), 59B (camera), 59C (segment).

Gate actions:
    Subtitle:
        block_keyword_strengthening — keyword_emphasis_quality low → revert highlight_per_word
        allow_density_reduction     — overload_risk high (advisory only, no revert)
        allow_readability_bias      — safe_zone_fit or mobile_readability low (advisory)
        no_change                   — quality signals acceptable

    Camera:
        block_aggressive_motion     — whip_pan_risk high → revert reframe_mode→center
        prefer_stability            — micro_jitter_risk high → downgrade motion→subject
        allow_subject_hold          — jitter risk high but reframe already safe (advisory)
        no_change                   — quality signals acceptable

    Segment:
        allow_ai_selected_segments  — hook quality strong
        allow_reorder_only          — hook quality weak but not critical (advisory)
        fallback_default_segments   — hook fatigue or render quality too low → revert scored
        no_change                   — no segment promotion was applied

Public API:
    apply_quality_gate(payload, edit_plan, context=None) -> tuple[Any, dict]
        Handles subtitle and camera gates (can revert 59A/59B payload fields).
        Called from render_influence.py after _apply_subtitle_promotion().

    apply_segment_quality_gate(scored, scored_original, edit_plan, context=None)
        -> tuple[list, dict]
        Handles segment gate (can revert 59C scored order).
        Called from render_pipeline.py after Phase 59C block.

Report shape:
    apply_quality_gate returns:
    {
        "quality_gated_influence": {
            "applied": true,
            "subtitle": {
                "gate_action": "block_keyword_strengthening",
                "reverted_fields": ["highlight_per_word"],
                "quality_signals": {"keyword_emphasis_quality": 25, ...},
                "confidence": 0.85,
                "reasoning": ["keyword_emphasis_quality=25 below threshold 40"],
                "applied": true
            },
            "camera": {
                "gate_action": "no_change",
                "reverted_fields": [],
                "quality_signals": {"micro_jitter_risk": 30, "whip_pan_risk": 20},
                "confidence": 0.90,
                "reasoning": [],
                "applied": false
            }
        }
    }

    apply_segment_quality_gate returns:
    {
        "segment_quality_gate": {
            "gate_action": "fallback_default_segments",
            "reverted": true,
            "quality_signals": {"hook_fatigue_risk": 70, ...},
            "confidence": 0.80,
            "reasoning": ["hook_fatigue_risk=70 >= threshold 60"],
            "applied": true
        }
    }

Safety contract:
    ❌ Never raises
    ❌ No new timestamp generation
    ❌ No subtitle timing rewrite
    ❌ No FFmpeg mutation
    ✅ Only reverts payload.highlight_per_word and payload.reframe_mode set by 59A/59B
    ✅ Only reverts scored to scored_original — never to empty list
    ✅ Advisory actions (allow_*) never mutate payload
    ✅ Original payload returned unchanged on any gate failure
    ✅ Confidence gate enforced before applying quality signals
    ✅ Deterministic: same inputs → same output
    ✅ Executor remains final authority
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.quality_gate")

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Subtitle gate thresholds
_KEYWORD_EMPHASIS_BLOCK: int = 40   # keyword_emphasis_quality below this → block
_OVERLOAD_RISK_HIGH: int = 60       # overload_risk above this → allow density reduction
_SAFE_ZONE_FIT_LOW: int = 40        # safe_zone_fit below this → allow readability bias
_MOBILE_READABILITY_LOW: int = 40   # mobile_readability below this → allow readability bias

# Camera gate thresholds
_WHIP_PAN_BLOCK: int = 60           # whip_pan_risk above this → block aggressive motion
_JITTER_STABILITY: int = 60         # micro_jitter_risk above this → prefer stability

# Segment gate thresholds
_HOOK_FATIGUE_FALLBACK: int = 60    # hook_fatigue_risk above this → fallback default
_HOOK_RENDER_SCORE_LOW: int = 35    # render_quality_v2.hook_score below this → fallback
_HOOK_FIRST3S_WEAK: int = 40        # first_3s_strength below this (+ low overall) → reorder_only
_HOOK_OVERALL_WEAK: int = 50        # hook overall below this (+ weak first3s) → reorder_only
_PLATFORM_HOOK_FIT_LOW: int = 40    # platform_quality_feedback.hook_fit below this → reorder_only

# Minimum confidence in the quality signal itself before trusting it
_MIN_SIGNAL_CONFIDENCE: float = 0.50


# ---------------------------------------------------------------------------
# Public API — subtitle + camera gate
# ---------------------------------------------------------------------------

def apply_quality_gate(
    payload: Any,
    edit_plan: Any,
    context: Optional[dict] = None,
) -> tuple[Any, dict]:
    """Apply quality gates to subtitle and camera promotions from Phase 59A/59B.

    May revert:
        payload.highlight_per_word  (if keyword_emphasis_quality is low)
        payload.reframe_mode        (if camera quality risk is high)

    Returns:
        (payload, {"quality_gated_influence": {"applied": bool, "subtitle": ..., "camera": ...}})
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _gate(payload, edit_plan, job_id)
    except Exception as exc:
        logger.warning("quality_gate_unexpected_error job_id=%s: %s", job_id, exc)
        return payload, {
            "quality_gated_influence": {
                "applied": False,
                "subtitle": _sub_result("no_change", reason="gate_error"),
                "camera":   _cam_result("no_change", reason="gate_error"),
                "reason":   "gate_error",
            }
        }


# ---------------------------------------------------------------------------
# Public API — segment gate
# ---------------------------------------------------------------------------

def apply_segment_quality_gate(
    scored: list,
    scored_original: list,
    edit_plan: Any,
    context: Optional[dict] = None,
) -> tuple[list, dict]:
    """Apply quality gate to segment selection from Phase 59C.

    May revert scored list to scored_original when hook quality is insufficient.

    Returns:
        (scored, {"segment_quality_gate": {...}})
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _segment_gate(scored, scored_original, edit_plan, job_id)
    except Exception as exc:
        logger.warning("segment_quality_gate_unexpected_error job_id=%s: %s", job_id, exc)
        safe = list(scored) if isinstance(scored, list) else []
        return safe, {
            "segment_quality_gate": {
                "gate_action": "no_change",
                "reverted":    False,
                "quality_signals": {},
                "confidence":  0.0,
                "reasoning":   [],
                "applied":     False,
                "reason":      "gate_error",
            }
        }


# ---------------------------------------------------------------------------
# Core — subtitle + camera
# ---------------------------------------------------------------------------

def _gate(
    payload: Any,
    edit_plan: Any,
    job_id: str,
) -> tuple[Any, dict]:
    sub = _evaluate_subtitle_gate(payload, edit_plan, job_id)
    cam = _evaluate_camera_gate(payload, edit_plan, job_id)

    gate_applied = bool(sub.get("reverted_fields") or cam.get("reverted_fields"))

    if gate_applied:
        logger.info(
            "quality_gate_applied job_id=%s subtitle_action=%s camera_action=%s",
            job_id,
            sub.get("gate_action"),
            cam.get("gate_action"),
        )
    else:
        logger.debug(
            "quality_gate_no_change job_id=%s subtitle_action=%s camera_action=%s",
            job_id,
            sub.get("gate_action"),
            cam.get("gate_action"),
        )

    return payload, {
        "quality_gated_influence": {
            "applied": gate_applied,
            "subtitle": sub,
            "camera":   cam,
        }
    }


def _evaluate_subtitle_gate(payload: Any, edit_plan: Any, job_id: str) -> dict:
    sqv2 = _attr_dict(edit_plan, "subtitle_quality_v2")
    sqv2_conf = float(sqv2.get("confidence") or 0.0)

    # Skip if signal confidence is too low and no overall score
    if sqv2_conf < _MIN_SIGNAL_CONFIDENCE and not int(sqv2.get("overall") or 0):
        return _sub_result("no_change", reason="insufficient_signal_confidence")

    keq   = int(sqv2.get("keyword_emphasis_quality") or 0)
    ovrld = int(sqv2.get("overload_risk")            or 0)
    sfz   = int(sqv2.get("safe_zone_fit")            or 0)
    mob   = int(sqv2.get("mobile_readability")       or 0)
    signals = {
        "keyword_emphasis_quality": keq,
        "overload_risk":            ovrld,
        "safe_zone_fit":            sfz,
        "mobile_readability":       mob,
    }

    # Was keyword emphasis set by Phase 59A?
    sub_promo = _attr_dict(edit_plan, "subtitle_execution_promotion")
    keyword_was_applied = bool(sub_promo.get("keyword_emphasis_applied"))

    # Gate 1 (highest priority): block keyword strengthening
    if keq < _KEYWORD_EMPHASIS_BLOCK:
        reverted: list[str] = []
        if keyword_was_applied:
            try:
                payload.highlight_per_word = False
                reverted = ["highlight_per_word"]
            except Exception:
                pass
            logger.info(
                "quality_gate_subtitle_block_keyword job_id=%s keq=%d reverted=%s",
                job_id, keq, reverted,
            )
        return _sub_result(
            "block_keyword_strengthening",
            reverted_fields=reverted,
            signals=signals,
            confidence=sqv2_conf,
            reasoning=[f"keyword_emphasis_quality={keq} < threshold {_KEYWORD_EMPHASIS_BLOCK}"],
            applied=bool(reverted),
        )

    # Gate 2: allow density reduction (advisory)
    if ovrld >= _OVERLOAD_RISK_HIGH:
        return _sub_result(
            "allow_density_reduction",
            signals=signals,
            confidence=sqv2_conf,
            reasoning=[f"overload_risk={ovrld} >= threshold {_OVERLOAD_RISK_HIGH}"],
        )

    # Gate 3: allow readability bias (advisory)
    if sfz < _SAFE_ZONE_FIT_LOW or mob < _MOBILE_READABILITY_LOW:
        reasoning: list[str] = []
        if sfz < _SAFE_ZONE_FIT_LOW:
            reasoning.append(f"safe_zone_fit={sfz} < threshold {_SAFE_ZONE_FIT_LOW}")
        if mob < _MOBILE_READABILITY_LOW:
            reasoning.append(f"mobile_readability={mob} < threshold {_MOBILE_READABILITY_LOW}")
        return _sub_result(
            "allow_readability_bias",
            signals=signals,
            confidence=sqv2_conf,
            reasoning=reasoning,
        )

    return _sub_result("no_change", signals=signals, confidence=sqv2_conf)


def _evaluate_camera_gate(payload: Any, edit_plan: Any, job_id: str) -> dict:
    cqv2 = _attr_dict(edit_plan, "camera_quality_v2")
    cqv2_conf = float(cqv2.get("confidence") or 0.0)

    if cqv2_conf < _MIN_SIGNAL_CONFIDENCE and not int(cqv2.get("overall") or 0):
        return _cam_result("no_change", reason="insufficient_signal_confidence")

    jitter   = int(cqv2.get("micro_jitter_risk") or 0)
    whip_pan = int(cqv2.get("whip_pan_risk")     or 0)
    signals = {
        "micro_jitter_risk": jitter,
        "whip_pan_risk":     whip_pan,
    }

    # Was reframe_mode set by Phase 59B?
    cam_promo = _attr_dict(edit_plan, "camera_execution_promotion")
    reframe_was_applied = bool(cam_promo.get("reframe_mode_applied"))

    current_reframe = str(getattr(payload, "reframe_mode", "center") or "center").lower()

    # Gate 1 (highest priority): block aggressive motion (whip_pan)
    if whip_pan >= _WHIP_PAN_BLOCK:
        reverted: list[str] = []
        reverted_to: Optional[str] = None
        if reframe_was_applied and current_reframe == "motion":
            try:
                payload.reframe_mode = "center"
                reverted = ["reframe_mode"]
                reverted_to = "center"
            except Exception:
                pass
            logger.info(
                "quality_gate_camera_block_aggressive job_id=%s whip_pan=%d motion->center",
                job_id, whip_pan,
            )
        result = _cam_result(
            "block_aggressive_motion",
            reverted_fields=reverted,
            signals=signals,
            confidence=cqv2_conf,
            reasoning=[f"whip_pan_risk={whip_pan} >= threshold {_WHIP_PAN_BLOCK}"],
            applied=bool(reverted),
        )
        if reverted_to:
            result["reverted_reframe_mode"] = reverted_to
        return result

    # Gate 2: prefer stability (jitter)
    if jitter >= _JITTER_STABILITY:
        reverted = []
        reverted_to = None
        if current_reframe == "motion":
            if reframe_was_applied:
                try:
                    payload.reframe_mode = "subject"
                    reverted = ["reframe_mode"]
                    reverted_to = "subject"
                except Exception:
                    pass
                logger.info(
                    "quality_gate_camera_prefer_stability job_id=%s jitter=%d motion->subject",
                    job_id, jitter,
                )
            result = _cam_result(
                "prefer_stability",
                reverted_fields=reverted,
                signals=signals,
                confidence=cqv2_conf,
                reasoning=[f"micro_jitter_risk={jitter} >= threshold {_JITTER_STABILITY}, motion→subject"],
                applied=bool(reverted),
            )
            if reverted_to:
                result["reverted_reframe_mode"] = reverted_to
            return result
        else:
            # Reframe already safe — advisory only
            return _cam_result(
                "allow_subject_hold",
                signals=signals,
                confidence=cqv2_conf,
                reasoning=[f"micro_jitter_risk={jitter} high; reframe={current_reframe!r} already safe"],
            )

    return _cam_result("no_change", signals=signals, confidence=cqv2_conf)


# ---------------------------------------------------------------------------
# Core — segment gate
# ---------------------------------------------------------------------------

def _segment_gate(
    scored: list,
    scored_original: list,
    edit_plan: Any,
    job_id: str,
) -> tuple[list, dict]:
    if not isinstance(scored, list):
        scored = []
    if not isinstance(scored_original, list):
        scored_original = list(scored)

    # If Phase 59C didn't run there's nothing to gate
    seg_promo = _attr_dict(edit_plan, "segment_selection_promotion")
    if not seg_promo.get("applied"):
        return list(scored), {
            "segment_quality_gate": {
                "gate_action": "no_change",
                "reverted":    False,
                "quality_signals": {},
                "confidence":  0.0,
                "reasoning":   ["no_segment_promotion_applied"],
                "applied":     False,
            }
        }

    hqv2 = _attr_dict(edit_plan, "hook_quality_v2")
    rqv2 = _attr_dict(edit_plan, "render_quality_v2")
    pqf  = _attr_dict(edit_plan, "platform_quality_feedback")

    hqv2_conf   = float(hqv2.get("confidence") or 0.0)
    fatigue     = int(hqv2.get("hook_fatigue_risk")  or 0)
    first_3s    = int(hqv2.get("first_3s_strength")  or 0)
    hook_ov     = int(hqv2.get("overall")            or 0)
    render_hook = int(rqv2.get("hook_score")         or 0)

    pqf_available = bool(pqf.get("available", False))
    plat_hook_fit = int(pqf.get("hook_fit") or 0) if pqf_available else 100

    signals = {
        "hook_fatigue_risk":  fatigue,
        "first_3s_strength":  first_3s,
        "hook_overall":       hook_ov,
        "render_hook_score":  render_hook,
        "platform_hook_fit":  plat_hook_fit,
    }

    # Gate 1 (highest priority): fallback to default segments
    # Triggers when hook fatigue is critically high OR render hook score is too low
    render_hook_low = render_hook > 0 and render_hook < _HOOK_RENDER_SCORE_LOW
    if fatigue >= _HOOK_FATIGUE_FALLBACK or render_hook_low:
        reasoning: list[str] = []
        if fatigue >= _HOOK_FATIGUE_FALLBACK:
            reasoning.append(f"hook_fatigue_risk={fatigue} >= threshold {_HOOK_FATIGUE_FALLBACK}")
        if render_hook_low:
            reasoning.append(f"render_hook_score={render_hook} < threshold {_HOOK_RENDER_SCORE_LOW}")

        result_scored = list(scored_original) if scored_original else list(scored)
        logger.info(
            "quality_gate_segment_fallback job_id=%s fatigue=%d render_hook=%d",
            job_id, fatigue, render_hook,
        )
        return result_scored, {
            "segment_quality_gate": {
                "gate_action": "fallback_default_segments",
                "reverted":    True,
                "quality_signals": signals,
                "confidence":  round(hqv2_conf, 4),
                "reasoning":   reasoning,
                "applied":     True,
            }
        }

    # Gate 2: allow reorder only (advisory) — hook quality weak
    hook_first3s_and_overall_weak = first_3s < _HOOK_FIRST3S_WEAK and hook_ov < _HOOK_OVERALL_WEAK
    plat_hook_weak = pqf_available and plat_hook_fit < _PLATFORM_HOOK_FIT_LOW
    if hook_first3s_and_overall_weak or plat_hook_weak:
        reasoning = []
        if hook_first3s_and_overall_weak:
            reasoning.append(
                f"first_3s_strength={first_3s} and hook_overall={hook_ov} both below thresholds"
            )
        if plat_hook_weak:
            reasoning.append(f"platform_hook_fit={plat_hook_fit} < threshold {_PLATFORM_HOOK_FIT_LOW}")
        logger.debug(
            "quality_gate_segment_reorder_only job_id=%s first3s=%d hook_ov=%d plat_hook=%d",
            job_id, first_3s, hook_ov, plat_hook_fit,
        )
        return list(scored), {
            "segment_quality_gate": {
                "gate_action": "allow_reorder_only",
                "reverted":    False,
                "quality_signals": signals,
                "confidence":  round(hqv2_conf, 4),
                "reasoning":   reasoning,
                "applied":     False,
            }
        }

    # Hook quality acceptable — allow AI selection
    logger.debug("quality_gate_segment_allow_ai job_id=%s hook_ov=%d", job_id, hook_ov)
    return list(scored), {
        "segment_quality_gate": {
            "gate_action": "allow_ai_selected_segments",
            "reverted":    False,
            "quality_signals": signals,
            "confidence":  round(hqv2_conf, 4),
            "reasoning":   ["hook quality acceptable, AI segment selection allowed"],
            "applied":     False,
        }
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attr_dict(obj: Any, attr: str) -> dict:
    """Duck-typed attribute access returning a dict or empty dict."""
    try:
        val = obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _sub_result(
    gate_action: str,
    reverted_fields: Optional[list] = None,
    signals: Optional[dict] = None,
    confidence: float = 0.0,
    reasoning: Optional[list] = None,
    applied: bool = False,
    reason: str = "",
) -> dict:
    result: dict = {
        "gate_action":     gate_action,
        "reverted_fields": reverted_fields or [],
        "quality_signals": signals or {},
        "confidence":      round(confidence, 4),
        "reasoning":       reasoning or [],
        "applied":         applied,
    }
    if reason:
        result["reason"] = reason
    return result


def _cam_result(
    gate_action: str,
    reverted_fields: Optional[list] = None,
    signals: Optional[dict] = None,
    confidence: float = 0.0,
    reasoning: Optional[list] = None,
    applied: bool = False,
    reason: str = "",
) -> dict:
    result: dict = {
        "gate_action":     gate_action,
        "reverted_fields": reverted_fields or [],
        "quality_signals": signals or {},
        "confidence":      round(confidence, 4),
        "reasoning":       reasoning or [],
        "applied":         applied,
    }
    if reason:
        result["reason"] = reason
    return result
