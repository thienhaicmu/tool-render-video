"""
test_ai_phase59d_quality_gate.py — Tests for Phase 59D Quality-Gated Influence.

Coverage:
  - Subtitle gate: block_keyword_strengthening, allow_density_reduction,
    allow_readability_bias, no_change
  - Camera gate: block_aggressive_motion, prefer_stability, allow_subject_hold, no_change
  - Segment gate: fallback_default_segments, allow_reorder_only,
    allow_ai_selected_segments, no_change
  - Safety: no raises on malformed inputs, payload unchanged on error paths

REQUIRED EXECUTION TEST:
  test_execution_keyword_emphasis_blocked_by_low_quality — verifies that when
  Phase 59A applied keyword emphasis and subtitle_quality_v2.keyword_emphasis_quality
  is low, Phase 59D reverts payload.highlight_per_word to False.
"""
import pytest
from types import SimpleNamespace

from app.ai.quality_gate.quality_gate_engine import (
    apply_quality_gate,
    apply_segment_quality_gate,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _payload(**kwargs):
    defaults = {
        "highlight_per_word": False,
        "reframe_mode":       "center",
        "add_subtitle":       True,
        "ai_director_enabled": True,
        "ai_render_influence_enabled": True,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _edit_plan(
    subtitle_quality_v2=None,
    camera_quality_v2=None,
    hook_quality_v2=None,
    render_quality_v2=None,
    platform_quality_feedback=None,
    subtitle_execution_promotion=None,
    camera_execution_promotion=None,
    segment_selection_promotion=None,
):
    return SimpleNamespace(
        subtitle_quality_v2=subtitle_quality_v2 or {},
        camera_quality_v2=camera_quality_v2 or {},
        hook_quality_v2=hook_quality_v2 or {},
        render_quality_v2=render_quality_v2 or {},
        platform_quality_feedback=platform_quality_feedback or {},
        subtitle_execution_promotion=subtitle_execution_promotion or {},
        camera_execution_promotion=camera_execution_promotion or {},
        segment_selection_promotion=segment_selection_promotion or {},
        quality_gated_influence={},
    )


def _sub_quality(
    keyword_emphasis_quality=80,
    overload_risk=20,
    safe_zone_fit=80,
    mobile_readability=80,
    overall=78,
    confidence=0.85,
):
    return {
        "keyword_emphasis_quality": keyword_emphasis_quality,
        "overload_risk":            overload_risk,
        "safe_zone_fit":            safe_zone_fit,
        "mobile_readability":       mobile_readability,
        "overall":                  overall,
        "confidence":               confidence,
    }


def _cam_quality(
    micro_jitter_risk=20,
    whip_pan_risk=20,
    overall=75,
    confidence=0.88,
):
    return {
        "micro_jitter_risk": micro_jitter_risk,
        "whip_pan_risk":     whip_pan_risk,
        "overall":           overall,
        "confidence":        confidence,
    }


def _hook_quality(
    hook_fatigue_risk=20,
    first_3s_strength=75,
    overall=78,
    confidence=0.82,
):
    return {
        "hook_fatigue_risk": hook_fatigue_risk,
        "first_3s_strength": first_3s_strength,
        "overall":           overall,
        "confidence":        confidence,
    }


def _scored_list(n=3):
    return [{"start": i * 10.0, "end": i * 10.0 + 8.0, "duration": 8.0} for i in range(n)]


# ---------------------------------------------------------------------------
# REQUIRED EXECUTION TEST
# ---------------------------------------------------------------------------

def test_execution_keyword_emphasis_blocked_by_low_quality():
    """Phase 59A applied keyword emphasis; Phase 59D blocks it when quality is low."""
    payload = _payload(highlight_per_word=True)   # Phase 59A already applied this
    plan = _edit_plan(
        subtitle_quality_v2=_sub_quality(keyword_emphasis_quality=25),
        subtitle_execution_promotion={"keyword_emphasis_applied": True, "applied": True},
    )

    result_payload, report = apply_quality_gate(payload, plan)

    assert result_payload.highlight_per_word is False, "Gate must revert highlight_per_word"
    gate = report["quality_gated_influence"]
    assert gate["applied"] is True
    sub = gate["subtitle"]
    assert sub["gate_action"] == "block_keyword_strengthening"
    assert "highlight_per_word" in sub["reverted_fields"]
    assert sub["applied"] is True


# ---------------------------------------------------------------------------
# Subtitle gate tests
# ---------------------------------------------------------------------------

def test_subtitle_no_change_when_quality_adequate():
    payload = _payload(highlight_per_word=True)
    plan = _edit_plan(
        subtitle_quality_v2=_sub_quality(keyword_emphasis_quality=70),
        subtitle_execution_promotion={"keyword_emphasis_applied": True},
    )
    result_payload, report = apply_quality_gate(payload, plan)

    assert result_payload.highlight_per_word is True   # not reverted
    gate = report["quality_gated_influence"]
    assert gate["subtitle"]["gate_action"] == "no_change"
    assert gate["subtitle"]["applied"] is False


def test_subtitle_block_keyword_advisory_when_59a_not_applied():
    """Low quality but Phase 59A didn't apply emphasis — advisory only (no revert)."""
    payload = _payload(highlight_per_word=False)
    plan = _edit_plan(
        subtitle_quality_v2=_sub_quality(keyword_emphasis_quality=20),
        subtitle_execution_promotion={"keyword_emphasis_applied": False},
    )
    result_payload, report = apply_quality_gate(payload, plan)

    assert result_payload.highlight_per_word is False   # unchanged
    sub = report["quality_gated_influence"]["subtitle"]
    assert sub["gate_action"] == "block_keyword_strengthening"
    assert sub["reverted_fields"] == []
    assert sub["applied"] is False


def test_subtitle_allow_density_reduction_when_overload_risk_high():
    payload = _payload()
    plan = _edit_plan(
        subtitle_quality_v2=_sub_quality(keyword_emphasis_quality=70, overload_risk=70),
    )
    _, report = apply_quality_gate(payload, plan)

    sub = report["quality_gated_influence"]["subtitle"]
    assert sub["gate_action"] == "allow_density_reduction"
    assert sub["reverted_fields"] == []
    assert sub["applied"] is False


def test_subtitle_allow_readability_bias_when_safe_zone_fit_low():
    payload = _payload()
    plan = _edit_plan(
        subtitle_quality_v2=_sub_quality(keyword_emphasis_quality=70, safe_zone_fit=30),
    )
    _, report = apply_quality_gate(payload, plan)

    sub = report["quality_gated_influence"]["subtitle"]
    assert sub["gate_action"] == "allow_readability_bias"
    assert sub["applied"] is False


def test_subtitle_allow_readability_bias_when_mobile_readability_low():
    payload = _payload()
    plan = _edit_plan(
        subtitle_quality_v2=_sub_quality(keyword_emphasis_quality=70, mobile_readability=30),
    )
    _, report = apply_quality_gate(payload, plan)

    sub = report["quality_gated_influence"]["subtitle"]
    assert sub["gate_action"] == "allow_readability_bias"


def test_subtitle_block_takes_priority_over_overload():
    """keyword_emphasis_quality < 40 takes priority over overload_risk check."""
    payload = _payload(highlight_per_word=True)
    plan = _edit_plan(
        subtitle_quality_v2=_sub_quality(keyword_emphasis_quality=25, overload_risk=75),
        subtitle_execution_promotion={"keyword_emphasis_applied": True},
    )
    _, report = apply_quality_gate(payload, plan)

    sub = report["quality_gated_influence"]["subtitle"]
    assert sub["gate_action"] == "block_keyword_strengthening"


def test_subtitle_no_gate_when_signal_confidence_too_low():
    payload = _payload()
    plan = _edit_plan(
        subtitle_quality_v2={"keyword_emphasis_quality": 10, "confidence": 0.30, "overall": 0},
    )
    _, report = apply_quality_gate(payload, plan)

    sub = report["quality_gated_influence"]["subtitle"]
    assert sub["gate_action"] == "no_change"
    assert sub["reason"] == "insufficient_signal_confidence"


# ---------------------------------------------------------------------------
# Camera gate tests
# ---------------------------------------------------------------------------

def test_camera_no_change_when_risks_low():
    payload = _payload(reframe_mode="motion")
    plan = _edit_plan(
        camera_quality_v2=_cam_quality(micro_jitter_risk=20, whip_pan_risk=20),
        camera_execution_promotion={"reframe_mode_applied": "motion", "applied": True},
    )
    result_payload, report = apply_quality_gate(payload, plan)

    assert result_payload.reframe_mode == "motion"
    cam = report["quality_gated_influence"]["camera"]
    assert cam["gate_action"] == "no_change"
    assert cam["applied"] is False


def test_camera_block_aggressive_motion_when_whip_pan_high():
    """whip_pan_risk >= 60 with reframe=motion → revert to center."""
    payload = _payload(reframe_mode="motion")
    plan = _edit_plan(
        camera_quality_v2=_cam_quality(whip_pan_risk=70),
        camera_execution_promotion={"reframe_mode_applied": "motion"},
    )
    result_payload, report = apply_quality_gate(payload, plan)

    assert result_payload.reframe_mode == "center"
    cam = report["quality_gated_influence"]["camera"]
    assert cam["gate_action"] == "block_aggressive_motion"
    assert "reframe_mode" in cam["reverted_fields"]
    assert cam["applied"] is True
    assert cam["reverted_reframe_mode"] == "center"


def test_camera_prefer_stability_when_jitter_high():
    """micro_jitter_risk >= 60 with reframe=motion → downgrade to subject."""
    payload = _payload(reframe_mode="motion")
    plan = _edit_plan(
        camera_quality_v2=_cam_quality(micro_jitter_risk=70, whip_pan_risk=20),
        camera_execution_promotion={"reframe_mode_applied": "motion"},
    )
    result_payload, report = apply_quality_gate(payload, plan)

    assert result_payload.reframe_mode == "subject"
    cam = report["quality_gated_influence"]["camera"]
    assert cam["gate_action"] == "prefer_stability"
    assert cam["applied"] is True
    assert cam["reverted_reframe_mode"] == "subject"


def test_camera_prefer_stability_advisory_when_reframe_already_safe():
    """Jitter high but reframe is already subject — advisory only."""
    payload = _payload(reframe_mode="subject")
    plan = _edit_plan(
        camera_quality_v2=_cam_quality(micro_jitter_risk=70, whip_pan_risk=20),
        camera_execution_promotion={"reframe_mode_applied": "subject"},
    )
    result_payload, report = apply_quality_gate(payload, plan)

    assert result_payload.reframe_mode == "subject"   # unchanged
    cam = report["quality_gated_influence"]["camera"]
    assert cam["gate_action"] == "allow_subject_hold"
    assert cam["applied"] is False


def test_camera_whip_pan_wins_over_jitter():
    """When both jitter and whip_pan are high, block_aggressive_motion wins."""
    payload = _payload(reframe_mode="motion")
    plan = _edit_plan(
        camera_quality_v2=_cam_quality(micro_jitter_risk=70, whip_pan_risk=70),
        camera_execution_promotion={"reframe_mode_applied": "motion"},
    )
    result_payload, report = apply_quality_gate(payload, plan)

    assert result_payload.reframe_mode == "center"
    cam = report["quality_gated_influence"]["camera"]
    assert cam["gate_action"] == "block_aggressive_motion"


# ---------------------------------------------------------------------------
# Segment gate tests
# ---------------------------------------------------------------------------

def _seg_plan_with_promo_applied(**hq_kwargs):
    return _edit_plan(
        hook_quality_v2=_hook_quality(**hq_kwargs),
        render_quality_v2={"hook_score": 60, "overall": 72, "confidence": 0.80},
        segment_selection_promotion={"applied": True, "selected_count": 2, "total_count": 3},
    )


def test_segment_no_change_when_promo_not_applied():
    scored = _scored_list(3)
    original = _scored_list(3)
    plan = _edit_plan(segment_selection_promotion={"applied": False})

    result, report = apply_segment_quality_gate(scored, original, plan)
    sg = report["segment_quality_gate"]
    assert sg["gate_action"] == "no_change"
    assert sg["reverted"] is False


def test_segment_fallback_when_hook_fatigue_high():
    scored = [{"start": 5.0, "end": 13.0, "duration": 8.0}]   # reordered
    original = _scored_list(3)                                  # original order
    plan = _seg_plan_with_promo_applied(hook_fatigue_risk=70)

    result, report = apply_segment_quality_gate(scored, original, plan)
    sg = report["segment_quality_gate"]
    assert sg["gate_action"] == "fallback_default_segments"
    assert sg["reverted"] is True
    assert sg["applied"] is True
    assert result == original


def test_segment_fallback_when_render_hook_score_low():
    scored = _scored_list(2)
    original = _scored_list(3)
    plan = _edit_plan(
        hook_quality_v2=_hook_quality(hook_fatigue_risk=20),
        render_quality_v2={"hook_score": 25, "overall": 60, "confidence": 0.80},
        segment_selection_promotion={"applied": True},
    )

    result, report = apply_segment_quality_gate(scored, original, plan)
    sg = report["segment_quality_gate"]
    assert sg["gate_action"] == "fallback_default_segments"
    assert result == original


def test_segment_allow_reorder_only_when_hook_weak():
    scored = _scored_list(3)
    original = _scored_list(3)
    plan = _seg_plan_with_promo_applied(
        hook_fatigue_risk=20,
        first_3s_strength=30,
        overall=40,
    )

    result, report = apply_segment_quality_gate(scored, original, plan)
    sg = report["segment_quality_gate"]
    assert sg["gate_action"] == "allow_reorder_only"
    assert sg["reverted"] is False
    assert result == scored   # not reverted


def test_segment_allow_ai_selected_when_hook_quality_good():
    scored = _scored_list(3)
    original = _scored_list(3)
    plan = _seg_plan_with_promo_applied(
        hook_fatigue_risk=20,
        first_3s_strength=80,
        overall=82,
    )

    result, report = apply_segment_quality_gate(scored, original, plan)
    sg = report["segment_quality_gate"]
    assert sg["gate_action"] == "allow_ai_selected_segments"
    assert sg["reverted"] is False
    assert result == scored


def test_segment_allow_reorder_only_when_platform_hook_fit_low():
    scored = _scored_list(3)
    original = _scored_list(3)
    plan = _edit_plan(
        hook_quality_v2=_hook_quality(hook_fatigue_risk=10, first_3s_strength=70, overall=75),
        render_quality_v2={"hook_score": 65, "overall": 70, "confidence": 0.80},
        platform_quality_feedback={"available": True, "hook_fit": 30, "overall": 50},
        segment_selection_promotion={"applied": True},
    )

    result, report = apply_segment_quality_gate(scored, original, plan)
    sg = report["segment_quality_gate"]
    assert sg["gate_action"] == "allow_reorder_only"


# ---------------------------------------------------------------------------
# Safety / error path tests
# ---------------------------------------------------------------------------

def test_never_raises_on_none_edit_plan():
    payload = _payload()
    result_payload, report = apply_quality_gate(payload, None)

    assert "quality_gated_influence" in report
    gate = report["quality_gated_influence"]
    assert gate["applied"] is False


def test_never_raises_on_empty_quality_dicts():
    payload = _payload()
    plan = _edit_plan()   # all quality dicts empty

    result_payload, report = apply_quality_gate(payload, plan)
    assert "quality_gated_influence" in report


def test_segment_gate_never_raises_on_malformed_scored():
    result, report = apply_segment_quality_gate(
        None, None, _edit_plan(segment_selection_promotion={"applied": True})
    )
    assert isinstance(result, list)
    assert "segment_quality_gate" in report


def test_payload_unchanged_when_no_quality_signals():
    payload = _payload(highlight_per_word=True, reframe_mode="motion")
    plan = _edit_plan()   # empty signals

    result_payload, _ = apply_quality_gate(payload, plan)
    # With empty signals both confidence=0.0 and overall=0 → insufficient confidence path
    # payload should remain unchanged
    assert result_payload.highlight_per_word is True
    assert result_payload.reframe_mode == "motion"
