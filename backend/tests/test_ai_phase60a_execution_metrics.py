"""
test_ai_phase60a_execution_metrics.py — Tests for Phase 60A AI Execution Metrics.

Coverage:
  - Subtitle metrics: eligible, applied, blocked, fallback, user override, confidence
  - Camera metrics: reframe_applied, crop, tuning, blocked, user override
  - Segment metrics: selected_count, total_count, blocked, fallback
  - Quality gate summary: subtitle/camera/segment_blocked, gate_actions
  - User override summary: per-domain tracking
  - Summary calculation: overall_ai_assistance levels
  - Confidence clamping: out-of-range, NaN-safe
  - Deterministic output: same inputs → same output
  - Fallback-safe: no crash on empty input or None edit_plan

REQUIRED EXECUTION TESTS:
  test_execution_59b_camera_applied_tracked   — Phase 59B applies camera, metrics reflect it
  test_execution_59d_camera_blocked_tracked   — Phase 59D blocks camera, metrics reflect it
  test_execution_59a_subtitle_applied_tracked — Phase 59A applies subtitle emphasis, metrics reflect it
  test_execution_59c_segment_applied_tracked  — Phase 59C reorders segments, metrics reflect it
  test_execution_59d_segment_reverted_tracked — Phase 59D reverts segment, metrics reflect it
"""
import pytest
from types import SimpleNamespace

from app.ai.metrics.ai_execution_metrics_engine import build_ai_execution_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edit_plan(
    subtitle_execution_promotion=None,
    camera_execution_promotion=None,
    segment_selection_promotion=None,
    quality_gated_influence=None,
):
    return SimpleNamespace(
        subtitle_execution_promotion=subtitle_execution_promotion or {},
        camera_execution_promotion=camera_execution_promotion   or {},
        segment_selection_promotion=segment_selection_promotion  or {},
        quality_gated_influence=quality_gated_influence          or {},
    )


def _sub_promo(applied=True, reason="promotion_applied", confidence=0.87,
               preset=None, emphasis=False, fallback=False):
    return {
        "applied":                  applied,
        "preset_applied":           preset,
        "keyword_emphasis_applied": emphasis,
        "density_applied":          None,
        "confidence":               confidence,
        "reason":                   reason,
        "reasoning":                [],
        "fallback_used":            fallback,
    }


def _cam_promo(applied=True, reason="promotion_applied", confidence=0.83,
               reframe=None, crop=False, tuning=None, fallback=False):
    return {
        "applied":                  applied,
        "reframe_mode_applied":     reframe,
        "motion_aware_crop_applied": crop,
        "tuning_applied":           tuning or {},
        "confidence":               confidence,
        "reason":                   reason,
        "reasoning":                [],
        "fallback_used":            fallback,
    }


def _seg_promo(applied=True, reason="promotion_applied", confidence=0.84,
               selected=2, total=4, fallback=False):
    return {
        "applied":        applied,
        "selected_count": selected,
        "total_count":    total,
        "source":         "ai_selected_segments" if applied else "default_segment_builder",
        "confidence":     confidence,
        "reason":         reason,
        "reasoning":      [],
        "fallback_used":  fallback,
    }


def _quality_gate(sub_action="no_change", sub_applied=False,
                  cam_action="no_change", cam_applied=False,
                  seg_action="no_change", seg_applied=False):
    return {
        "applied": sub_applied or cam_applied,
        "subtitle": {
            "gate_action":    sub_action,
            "reverted_fields": ["highlight_per_word"] if sub_applied else [],
            "applied":        sub_applied,
            "confidence":     0.85,
            "reasoning":      [],
            "quality_signals": {},
        },
        "camera": {
            "gate_action":    cam_action,
            "reverted_fields": ["reframe_mode"] if cam_applied else [],
            "applied":        cam_applied,
            "confidence":     0.88,
            "reasoning":      [],
            "quality_signals": {},
        },
        "segment": {
            "gate_action": seg_action,
            "reverted":    seg_applied,
            "applied":     seg_applied,
            "confidence":  0.80,
            "reasoning":   [],
            "quality_signals": {},
        },
    }


# ---------------------------------------------------------------------------
# REQUIRED EXECUTION TESTS
# ---------------------------------------------------------------------------

def test_execution_59b_camera_applied_tracked():
    """Phase 59B applies reframe_mode=motion — metrics.camera.applied must be True."""
    plan = _edit_plan(
        camera_execution_promotion=_cam_promo(
            applied=True, reframe="motion", confidence=0.83
        ),
        quality_gated_influence=_quality_gate(cam_action="no_change", cam_applied=False),
    )
    result = build_ai_execution_metrics(plan)

    cam = result["ai_execution_metrics"]["camera"]
    assert cam["applied"] is True, "camera.applied must be True when 59B applied reframe"
    assert cam["reframe_applied"] == "motion"
    assert cam["blocked"] is False


def test_execution_59d_camera_blocked_tracked():
    """Phase 59D blocks aggressive camera motion — metrics.camera.blocked must be True."""
    plan = _edit_plan(
        camera_execution_promotion=_cam_promo(
            applied=True, reframe="motion", confidence=0.83
        ),
        quality_gated_influence=_quality_gate(
            cam_action="block_aggressive_motion", cam_applied=True
        ),
    )
    result = build_ai_execution_metrics(plan)

    cam = result["ai_execution_metrics"]["camera"]
    assert cam["blocked"] is True, "camera.blocked must be True when 59D blocked it"
    assert cam["applied"] is False, "camera.applied must be False after gate revert"
    qg = result["ai_execution_metrics"]["quality_gate"]
    assert qg["camera_blocked"] is True
    assert qg["camera_gate_action"] == "block_aggressive_motion"


def test_execution_59a_subtitle_applied_tracked():
    """Phase 59A applies keyword emphasis — metrics.subtitle.applied must be True."""
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(
            applied=True, emphasis=True, confidence=0.90
        ),
        quality_gated_influence=_quality_gate(sub_action="no_change", sub_applied=False),
    )
    result = build_ai_execution_metrics(plan)

    sub = result["ai_execution_metrics"]["subtitle"]
    assert sub["applied"] is True
    assert sub["blocked"] is False
    assert sub["confidence"] == 0.9


def test_execution_59c_segment_applied_tracked():
    """Phase 59C reorders segments — metrics.segment.applied must be True."""
    plan = _edit_plan(
        segment_selection_promotion=_seg_promo(
            applied=True, selected=3, total=5, confidence=0.86
        ),
        quality_gated_influence=_quality_gate(seg_action="allow_ai_selected_segments"),
    )
    result = build_ai_execution_metrics(plan)

    seg = result["ai_execution_metrics"]["segment"]
    assert seg["applied"] is True
    assert seg["selected_count"] == 3
    assert seg["total_count"] == 5
    assert seg["blocked"] is False


def test_execution_59d_segment_reverted_tracked():
    """Phase 59D reverts segment order — metrics.segment.blocked must be True."""
    plan = _edit_plan(
        segment_selection_promotion=_seg_promo(
            applied=True, selected=2, total=4, confidence=0.82
        ),
        quality_gated_influence=_quality_gate(
            seg_action="fallback_default_segments", seg_applied=True
        ),
    )
    result = build_ai_execution_metrics(plan)

    seg = result["ai_execution_metrics"]["segment"]
    assert seg["blocked"] is True
    assert seg["applied"] is False
    qg = result["ai_execution_metrics"]["quality_gate"]
    assert qg["segment_blocked"] is True
    assert qg["segment_gate_action"] == "fallback_default_segments"


# ---------------------------------------------------------------------------
# Subtitle metrics tests
# ---------------------------------------------------------------------------

def test_subtitle_eligible_when_reason_is_promotion_applied():
    plan = _edit_plan(subtitle_execution_promotion=_sub_promo(applied=True))
    result = build_ai_execution_metrics(plan)
    assert result["ai_execution_metrics"]["subtitle"]["eligible"] is True


def test_subtitle_not_eligible_when_ai_disabled():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(
            applied=False, reason="ai_director_disabled", fallback=True
        )
    )
    result = build_ai_execution_metrics(plan)
    sub = result["ai_execution_metrics"]["subtitle"]
    assert sub["eligible"] is False
    assert sub["applied"] is False


def test_subtitle_user_override_tracked():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(
            applied=False, reason="user_override:subtitle_ai_style_lock=true", fallback=True
        )
    )
    result = build_ai_execution_metrics(plan)
    uo = result["ai_execution_metrics"]["user_override"]
    assert uo["subtitle"] is True
    assert uo["camera"] is False
    assert uo["segment"] is False


def test_subtitle_fallback_tracked():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(
            applied=False, reason="low_confidence", confidence=0.60, fallback=True
        )
    )
    result = build_ai_execution_metrics(plan)
    sub = result["ai_execution_metrics"]["subtitle"]
    assert sub["fallback_used"] is True
    assert sub["eligible"] is True   # low_confidence is eligible — system was not disabled


# ---------------------------------------------------------------------------
# Camera metrics tests
# ---------------------------------------------------------------------------

def test_camera_metrics_reframe_and_crop():
    plan = _edit_plan(
        camera_execution_promotion=_cam_promo(
            applied=True, reframe="subject", crop=True,
            tuning={"deadzone_delta": 0.03, "smoothing_delta": 0.05},
            confidence=0.84,
        ),
    )
    result = build_ai_execution_metrics(plan)
    cam = result["ai_execution_metrics"]["camera"]
    assert cam["applied"] is True
    assert cam["reframe_applied"] == "subject"
    assert cam["crop_applied"] is True
    assert cam["tuning_applied"] is True


def test_camera_user_override_tracked():
    plan = _edit_plan(
        camera_execution_promotion=_cam_promo(
            applied=False,
            reason="user_override:camera_ai_reframe_lock=true",
            fallback=True,
        )
    )
    result = build_ai_execution_metrics(plan)
    uo = result["ai_execution_metrics"]["user_override"]
    assert uo["camera"] is True


def test_camera_not_eligible_when_influence_disabled():
    plan = _edit_plan(
        camera_execution_promotion=_cam_promo(
            applied=False, reason="ai_render_influence_disabled", fallback=True
        )
    )
    result = build_ai_execution_metrics(plan)
    cam = result["ai_execution_metrics"]["camera"]
    assert cam["eligible"] is False


# ---------------------------------------------------------------------------
# Segment metrics tests
# ---------------------------------------------------------------------------

def test_segment_user_override_tracked():
    plan = _edit_plan(
        segment_selection_promotion=_seg_promo(
            applied=False,
            reason="user_override:segment_ai_lock=true",
            fallback=True,
        )
    )
    result = build_ai_execution_metrics(plan)
    uo = result["ai_execution_metrics"]["user_override"]
    assert uo["segment"] is True


def test_segment_low_confidence_eligible_not_applied():
    plan = _edit_plan(
        segment_selection_promotion=_seg_promo(
            applied=False, reason="low_confidence", confidence=0.72, fallback=True
        )
    )
    result = build_ai_execution_metrics(plan)
    seg = result["ai_execution_metrics"]["segment"]
    assert seg["eligible"] is True
    assert seg["applied"] is False
    assert seg["fallback_used"] is True


# ---------------------------------------------------------------------------
# Quality gate summary tests
# ---------------------------------------------------------------------------

def test_quality_gate_all_blocked():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(applied=True, confidence=0.88),
        camera_execution_promotion=_cam_promo(applied=True, reframe="motion", confidence=0.84),
        segment_selection_promotion=_seg_promo(applied=True, confidence=0.82),
        quality_gated_influence=_quality_gate(
            sub_action="block_keyword_strengthening", sub_applied=True,
            cam_action="block_aggressive_motion",     cam_applied=True,
            seg_action="fallback_default_segments",   seg_applied=True,
        ),
    )
    result = build_ai_execution_metrics(plan)
    qg = result["ai_execution_metrics"]["quality_gate"]
    assert qg["subtitle_blocked"] is True
    assert qg["camera_blocked"] is True
    assert qg["segment_blocked"] is True

    summary = result["ai_execution_summary"]
    assert summary["quality_gate_blocks"] == 3
    assert summary["overall_ai_assistance"] == "none"


def test_quality_gate_no_blocks():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(applied=True, confidence=0.90),
        camera_execution_promotion=_cam_promo(applied=True, reframe="motion", confidence=0.85),
        segment_selection_promotion=_seg_promo(applied=True, confidence=0.83),
        quality_gated_influence=_quality_gate(),
    )
    result = build_ai_execution_metrics(plan)
    qg = result["ai_execution_metrics"]["quality_gate"]
    assert qg["subtitle_blocked"] is False
    assert qg["camera_blocked"] is False
    assert qg["segment_blocked"] is False

    summary = result["ai_execution_summary"]
    assert summary["quality_gate_blocks"] == 0
    assert summary["overall_ai_assistance"] == "high"


# ---------------------------------------------------------------------------
# Summary calculation tests
# ---------------------------------------------------------------------------

def test_summary_assistance_none_when_nothing_applied():
    plan = _edit_plan()   # all empty
    result = build_ai_execution_metrics(plan)
    summary = result["ai_execution_summary"]
    assert summary["overall_ai_assistance"] == "none"
    assert summary["subtitle_apply"] is False
    assert summary["camera_apply"] is False
    assert summary["segment_apply"] is False


def test_summary_assistance_low_one_applied():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(applied=True, confidence=0.88),
    )
    result = build_ai_execution_metrics(plan)
    assert result["ai_execution_summary"]["overall_ai_assistance"] == "low"


def test_summary_assistance_medium_two_applied():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(applied=True, confidence=0.88),
        camera_execution_promotion=_cam_promo(applied=True, reframe="subject", confidence=0.83),
    )
    result = build_ai_execution_metrics(plan)
    assert result["ai_execution_summary"]["overall_ai_assistance"] == "medium"


def test_summary_user_override_count():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(
            applied=False, reason="user_override:subtitle_ai_style_lock=true"
        ),
        camera_execution_promotion=_cam_promo(
            applied=False, reason="user_override:camera_ai_reframe_lock=true"
        ),
    )
    result = build_ai_execution_metrics(plan)
    assert result["ai_execution_summary"]["user_override_count"] == 2


# ---------------------------------------------------------------------------
# Confidence clamping tests
# ---------------------------------------------------------------------------

def test_confidence_clamped_above_one():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(applied=True, confidence=1.5),
    )
    result = build_ai_execution_metrics(plan)
    sub_conf = result["ai_execution_metrics"]["subtitle"]["confidence"]
    assert sub_conf <= 1.0


def test_confidence_clamped_below_zero():
    plan = _edit_plan(
        camera_execution_promotion=_cam_promo(applied=True, confidence=-0.3),
    )
    result = build_ai_execution_metrics(plan)
    cam_conf = result["ai_execution_metrics"]["camera"]["confidence"]
    assert cam_conf >= 0.0


def test_aggregate_confidence_mean_of_nonzero():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(applied=True, confidence=0.80),
        camera_execution_promotion=_cam_promo(applied=True, confidence=0.90),
    )
    result = build_ai_execution_metrics(plan)
    agg = result["ai_execution_metrics"]["confidence"]
    assert 0.84 < agg < 0.86   # mean of 0.80 and 0.90 = 0.85


# ---------------------------------------------------------------------------
# Deterministic output test
# ---------------------------------------------------------------------------

def test_deterministic_output():
    plan = _edit_plan(
        subtitle_execution_promotion=_sub_promo(applied=True, confidence=0.88),
        camera_execution_promotion=_cam_promo(applied=True, reframe="motion", confidence=0.83),
        segment_selection_promotion=_seg_promo(applied=True, confidence=0.84),
        quality_gated_influence=_quality_gate(
            cam_action="prefer_stability", cam_applied=True,
        ),
    )
    result_a = build_ai_execution_metrics(plan)
    result_b = build_ai_execution_metrics(plan)
    assert result_a == result_b


# ---------------------------------------------------------------------------
# Safety / fallback tests
# ---------------------------------------------------------------------------

def test_never_raises_on_none_edit_plan():
    result = build_ai_execution_metrics(None)
    assert "ai_execution_metrics" in result
    assert "ai_execution_summary" in result
    assert result["ai_execution_metrics"]["confidence"] == 0.0


def test_never_raises_on_empty_plan():
    plan = _edit_plan()
    result = build_ai_execution_metrics(plan)
    assert "ai_execution_metrics" in result
    metrics = result["ai_execution_metrics"]
    assert "subtitle" in metrics
    assert "camera" in metrics
    assert "segment" in metrics
    assert "quality_gate" in metrics
    assert "user_override" in metrics


def test_fallback_shape_complete():
    result = build_ai_execution_metrics(None)
    summary = result["ai_execution_summary"]
    assert "subtitle_apply" in summary
    assert "camera_apply" in summary
    assert "segment_apply" in summary
    assert "quality_gate_blocks" in summary
    assert "user_override_count" in summary
    assert "overall_ai_assistance" in summary
    assert summary["overall_ai_assistance"] in ("none", "low", "medium", "high")
