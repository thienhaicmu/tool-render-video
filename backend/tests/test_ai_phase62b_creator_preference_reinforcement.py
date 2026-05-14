"""
test_ai_phase62b_creator_preference_reinforcement.py — Tests for Phase 62B.

Coverage:
    - Positive subtitle reinforcement
    - Positive camera reinforcement
    - Positive ranking reinforcement (strong + high creator_fit)
    - Negative signal captured (ai_off winner)
    - Negative signal for regression outcome
    - Platform quality feedback weak adds negative signal
    - A/B missing with low confidence blocks reinforcement (fallback)
    - A/B missing with high confidence still returns available
    - User override excluded from reinforcement
    - Confidence delta per domain bounded [0, 0.05]
    - Negative signal delta bounded [−0.05, 0]
    - Total absolute delta cap 0.12
    - Fallback on None / empty / garbage input
    - Deterministic output
    - No crash on empty input
    - No unsafe/execution fields in output
    - creator_type unknown → fallback
    - outcome unavailable → fallback
    - quality missing → fallback
    - No reinforcement when outcome neutral
    - Reinforcement confidence scaling formula
    - Negative signals advisory-only (no "applied" key)

Required execution tests:
    test_execution_subtitle_reinforced_when_improved
    test_execution_winner_ai_off_negative_signal
    test_execution_advisory_only_no_mutation
    test_execution_ab_missing_blocks_low_conf
"""
import pytest
from types import SimpleNamespace

from app.ai.outcome_tracking.creator_preference_reinforcement_engine import (
    build_creator_preference_reinforcement,
    _passes_evidence_gate,
    _positive_delta,
    _compute_confidence,
    _check_user_overrides,
    _apply_total_delta_cap,
    _compute_negative_signals,
    _MAX_POSITIVE_DELTA,
    _MAX_NEGATIVE_DELTA,
    _MAX_TOTAL_DELTA,
    _AB_MISSING_CONF_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan(
    rot_available=True,
    rot_overall="improved",
    rot_effectiveness="strong",
    rot_confidence=0.84,
    rot_creator_type="podcast",
    rot_quality_subtitle=84,
    rot_quality_camera=81,
    rot_quality_hook=79,
    rot_quality_overall=82,
    rot_subtitle_applied=True,
    rot_camera_applied=True,
    rot_segment_applied=False,
    rot_qg_blocks=1,
    rot_ab_winner="ai_on",
    rot_ab_delta=6,
    rot_creator_fit="high",
    rot_bench_delta=7,
    ab_available=True,
    ab_winner="ai_on",
    ab_conf=0.85,
    bench_status="best_fit",
    bench_overall_delta=7,
    crs_style="clean_pro",
    crs_density="balanced",
    crs_keyword="selective",
    crs_stability="high",
    crs_crop="low",
    crs_ranking_priority="retention_creator_fit",
    crs_confidence=0.86,
    subtitle_promo_reason="",
    camera_promo_reason="",
    pqf_available=False,
    pqf_camera_fit=80,
    metrics_available=True,
) -> SimpleNamespace:
    return SimpleNamespace(
        render_outcome_tracking={
            "available":        rot_available,
            "creator_type":     rot_creator_type,
            "overall_result":   rot_overall,
            "ai_effectiveness": rot_effectiveness,
            "confidence":       rot_confidence,
            "quality": {
                "subtitle": rot_quality_subtitle,
                "camera":   rot_quality_camera,
                "hook":     rot_quality_hook,
                "overall":  rot_quality_overall,
            },
            "ai_execution": {
                "subtitle_applied":    rot_subtitle_applied,
                "camera_applied":      rot_camera_applied,
                "segment_applied":     rot_segment_applied,
                "quality_gate_blocks": rot_qg_blocks,
            },
            "ab_result": {
                "winner":        rot_ab_winner,
                "overall_delta": rot_ab_delta,
            },
            "benchmark_result": {
                "creator_fit":     rot_creator_fit,
                "benchmark_delta": rot_bench_delta,
            },
        },
        creator_render_strategy={
            "available":    True,
            "creator_type": rot_creator_type,
            "confidence":   crs_confidence,
            "strategy": {
                "subtitle": {
                    "style":            crs_style,
                    "density":          crs_density,
                    "keyword_emphasis": crs_keyword,
                    "readability_priority": "high",
                },
                "camera": {
                    "stability_priority":  crs_stability,
                    "crop_aggressiveness": crs_crop,
                    "motion_energy":       "low",
                    "subject_hold":        "high",
                },
                "ranking": {
                    "priority": crs_ranking_priority,
                },
            },
        },
        ai_execution_metrics={"quality_gate": {}} if metrics_available else {},
        ai_execution_summary={"subtitle_apply": True, "camera_apply": True} if metrics_available else {},
        ai_ab_evaluation={
            "available":  ab_available,
            "winner":     ab_winner,
            "delta":      {"overall": rot_ab_delta},
            "confidence": ab_conf,
        } if ab_available else {
            "available": False,
            "reason":    "baseline_missing",
            "winner":    "unknown",
            "delta":     {},
            "confidence": 0.0,
        },
        creator_benchmark_summary={
            "available":        True,
            "benchmark_status": bench_status,
            "overall_delta":    bench_overall_delta,
            "creator_type":     rot_creator_type,
        },
        platform_quality_feedback={
            "available":   pqf_available,
            "camera_fit":  pqf_camera_fit,
        },
        subtitle_execution_promotion={"reason": subtitle_promo_reason},
        camera_execution_promotion={"reason": camera_promo_reason},
        render_quality_v2={"overall": rot_quality_overall, "confidence": 0.88},
    )


# ---------------------------------------------------------------------------
# Required execution tests
# ---------------------------------------------------------------------------

def test_execution_subtitle_reinforced_when_improved():
    """Full pipeline: improved+strong+ai_on+subtitle_applied+quality≥70 → subtitle reinforced."""
    plan = _plan(
        rot_overall="improved", rot_effectiveness="strong", rot_ab_winner="ai_on",
        rot_subtitle_applied=True, rot_quality_subtitle=84,
        rot_creator_type="podcast",
    )
    result = build_creator_preference_reinforcement(plan, context={"job_id": "test"})
    cpr = result["creator_preference_reinforcement"]

    assert cpr["available"] is True
    assert "subtitle" in cpr["reinforced_preferences"]
    sub = cpr["reinforced_preferences"]["subtitle"]
    assert sub["confidence_delta"] > 0.0
    assert sub["confidence_delta"] <= _MAX_POSITIVE_DELTA
    assert "style" in sub
    assert "density" in sub
    assert "keyword_emphasis" in sub
    # Ensure no execution mutation keys
    for key in ("ffmpeg_args", "render_command", "executor_override", "output_path"):
        assert key not in cpr


def test_execution_winner_ai_off_negative_signal():
    """winner=ai_off → negative signal recorded, no positive reinforcement."""
    plan = _plan(
        rot_overall="regression", rot_effectiveness="weak",
        rot_ab_winner="ai_off",
        ab_available=True, ab_winner="ai_off",
        rot_quality_subtitle=55, rot_quality_camera=50,
        rot_subtitle_applied=True, rot_camera_applied=True,
    )
    result = build_creator_preference_reinforcement(plan, context={"job_id": "test"})
    cpr = result["creator_preference_reinforcement"]

    assert cpr["available"] is True
    assert cpr["reinforced_preferences"] == {}
    assert len(cpr["negative_signals"]) > 0
    for sig in cpr["negative_signals"]:
        assert sig["confidence_delta"] < 0.0
        assert sig["confidence_delta"] >= -_MAX_NEGATIVE_DELTA


def test_execution_advisory_only_no_mutation():
    """Phase 62B output contains no execution/mutation/ffmpeg/override keys."""
    plan = _plan()
    result = build_creator_preference_reinforcement(plan, context={"job_id": "safety"})
    cpr = result["creator_preference_reinforcement"]

    forbidden = {
        "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
        "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
        "executable", "python_code", "shell", "executor_override",
        "direct_execution", "output_path", "queue_priority",
    }
    for key in forbidden:
        assert key not in cpr, f"Forbidden key found: {key}"


def test_execution_ab_missing_blocks_low_conf():
    """A/B baseline missing + confidence < threshold → fallback (conservative)."""
    plan = _plan(
        ab_available=False,
        rot_confidence=0.50,   # below _AB_MISSING_CONF_THRESHOLD=0.65
    )
    result = build_creator_preference_reinforcement(plan, context={"job_id": "test"})
    cpr = result["creator_preference_reinforcement"]

    assert cpr["available"] is False
    assert cpr["reinforced_preferences"] == {}
    assert cpr["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Positive reinforcement tests
# ---------------------------------------------------------------------------

def test_positive_subtitle_reinforcement():
    plan = _plan(rot_overall="improved", rot_effectiveness="strong",
                 rot_subtitle_applied=True, rot_quality_subtitle=84)
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert "subtitle" in cpr["reinforced_preferences"]
    sub = cpr["reinforced_preferences"]["subtitle"]
    assert sub["style"] == "clean_pro"
    assert sub["density"] == "balanced"
    assert sub["keyword_emphasis"] == "selective"
    assert 0.0 < sub["confidence_delta"] <= _MAX_POSITIVE_DELTA


def test_positive_camera_reinforcement():
    plan = _plan(rot_overall="improved", rot_effectiveness="strong",
                 rot_camera_applied=True, rot_quality_camera=81)
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert "camera" in cpr["reinforced_preferences"]
    cam = cpr["reinforced_preferences"]["camera"]
    assert cam["stability_priority"] == "high"
    assert cam["crop_aggressiveness"] == "low"
    assert 0.0 < cam["confidence_delta"] <= _MAX_POSITIVE_DELTA


def test_positive_ranking_reinforcement():
    """Ranking reinforced only when strong + creator_fit=high."""
    plan = _plan(
        rot_overall="improved", rot_effectiveness="strong",
        rot_creator_fit="high", rot_bench_delta=7,
    )
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert "ranking" in cpr["reinforced_preferences"]
    rank = cpr["reinforced_preferences"]["ranking"]
    assert rank["priority"] == "retention_creator_fit"
    assert 0.0 < rank["confidence_delta"] <= _MAX_POSITIVE_DELTA


def test_no_ranking_reinforcement_when_not_strong():
    """Ranking NOT reinforced when effectiveness=moderate (requires strong)."""
    plan = _plan(rot_overall="improved", rot_effectiveness="moderate",
                 rot_creator_fit="high")
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert "ranking" not in cpr["reinforced_preferences"]


def test_no_reinforcement_below_quality_threshold():
    """Domain quality below 70 → no reinforcement for that domain."""
    plan = _plan(rot_overall="improved", rot_effectiveness="strong",
                 rot_quality_subtitle=65, rot_quality_camera=65)
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert "subtitle" not in cpr["reinforced_preferences"]
    assert "camera" not in cpr["reinforced_preferences"]


def test_no_reinforcement_when_neutral_outcome():
    plan = _plan(rot_overall="neutral", rot_effectiveness="weak",
                 ab_available=True, ab_winner="tie")
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert cpr["available"] is True
    assert cpr["reinforced_preferences"] == {}


# ---------------------------------------------------------------------------
# Negative signal tests
# ---------------------------------------------------------------------------

def test_negative_signal_captured_ai_off():
    plan = _plan(
        rot_overall="regression", rot_effectiveness="weak",
        rot_ab_winner="ai_off", ab_available=True, ab_winner="ai_off",
        rot_quality_subtitle=50, rot_quality_camera=45,
        rot_subtitle_applied=True, rot_camera_applied=True,
    )
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert len(cpr["negative_signals"]) > 0


def test_negative_signal_regression_overall():
    signals = _compute_negative_signals(
        ab_available=True, ab_winner="ai_off",
        ai_execution={}, quality={}, pqf={}, overall_result="regression"
    )
    assert len(signals) > 0
    for sig in signals:
        assert sig["confidence_delta"] < 0.0


def test_negative_signal_advisory_only():
    """Negative signals have no 'applied' key — advisory only."""
    plan = _plan(
        rot_overall="regression", rot_effectiveness="weak",
        rot_ab_winner="ai_off", ab_available=True, ab_winner="ai_off",
    )
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    for sig in cpr["negative_signals"]:
        assert "applied" not in sig, "Negative signals must be advisory-only (no 'applied' key)"


def test_platform_feedback_weak_adds_negative_signal():
    plan = _plan(
        rot_overall="improved", rot_effectiveness="strong",
        rot_camera_applied=True,
        pqf_available=True, pqf_camera_fit=20,  # low fit → signal
    )
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    platform_sigs = [s for s in cpr["negative_signals"] if s["domain"] == "camera"]
    assert len(platform_sigs) > 0


def test_no_platform_negative_signal_when_fit_ok():
    plan = _plan(pqf_available=True, pqf_camera_fit=80)
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    platform_sigs = [s for s in cpr["negative_signals"] if s.get("signal") == "platform_camera_fit_weak"]
    assert len(platform_sigs) == 0


# ---------------------------------------------------------------------------
# Confidence delta bound tests
# ---------------------------------------------------------------------------

def test_confidence_delta_positive_bound():
    """Positive delta for any effectiveness/quality never exceeds _MAX_POSITIVE_DELTA."""
    for eff in ("strong", "moderate"):
        for q in range(0, 101, 10):
            delta = _positive_delta(eff, q)
            assert delta >= 0.0
            assert delta <= _MAX_POSITIVE_DELTA


def test_confidence_delta_negative_bound():
    """Negative signals after clamping are within [-MAX_NEGATIVE_DELTA, 0]."""
    signals = _compute_negative_signals(
        ab_available=True, ab_winner="ai_off",
        ai_execution={"subtitle_applied": True, "camera_applied": True},
        quality={"subtitle": 50, "camera": 45},
        pqf={"available": True, "camera_fit": 10},
        overall_result="regression",
    )
    for sig in signals:
        assert sig["confidence_delta"] >= -_MAX_NEGATIVE_DELTA
        assert sig["confidence_delta"] <= 0.0


def test_positive_delta_scales_with_quality():
    """Higher quality → higher positive delta."""
    delta_low  = _positive_delta("strong", 70)
    delta_high = _positive_delta("strong", 95)
    assert delta_high > delta_low


def test_positive_delta_strong_gt_moderate():
    """Strong effectiveness yields higher delta than moderate at same quality."""
    delta_strong   = _positive_delta("strong", 80)
    delta_moderate = _positive_delta("moderate", 80)
    assert delta_strong > delta_moderate


# ---------------------------------------------------------------------------
# Total delta cap tests
# ---------------------------------------------------------------------------

def test_total_delta_cap_applied():
    """When total absolute delta exceeds 0.12, deltas are scaled proportionally."""
    reinforced = {
        "subtitle": {"confidence_delta": 0.05},
        "camera":   {"confidence_delta": 0.05},
        "ranking":  {"confidence_delta": 0.05},
    }
    negative = [{"confidence_delta": -0.05}]
    _apply_total_delta_cap(reinforced, negative)

    total_after = (
        sum(abs(v["confidence_delta"]) for v in reinforced.values()) +
        sum(abs(s["confidence_delta"]) for s in negative)
    )
    assert total_after <= _MAX_TOTAL_DELTA + 1e-9


def test_total_delta_no_cap_when_under():
    """When total is under cap, deltas are unchanged."""
    reinforced = {"subtitle": {"confidence_delta": 0.03}}
    negative   = [{"confidence_delta": -0.02}]
    _apply_total_delta_cap(reinforced, negative)
    assert abs(reinforced["subtitle"]["confidence_delta"] - 0.03) < 1e-9


# ---------------------------------------------------------------------------
# Evidence gate tests
# ---------------------------------------------------------------------------

def test_gate_passes_valid_input():
    passed, reason = _passes_evidence_gate(
        True, "podcast", {"subtitle": 84, "camera": 81, "hook": 79, "overall": 82},
        {"metric": "ok"}, True, 0.84,
    )
    assert passed is True
    assert reason == "passed"


def test_gate_fails_outcome_unavailable():
    passed, reason = _passes_evidence_gate(False, "podcast", {"overall": 82}, {"x": 1}, True, 0.84)
    assert passed is False
    assert reason == "outcome_unavailable"


def test_gate_fails_creator_type_unknown():
    passed, reason = _passes_evidence_gate(True, "unknown", {"overall": 82}, {"x": 1}, True, 0.84)
    assert passed is False
    assert reason == "creator_type_unknown"


def test_gate_fails_quality_missing():
    passed, reason = _passes_evidence_gate(True, "podcast", {"overall": 0}, {"x": 1}, True, 0.84)
    assert passed is False
    assert reason == "quality_missing"


def test_gate_fails_metrics_missing():
    passed, reason = _passes_evidence_gate(True, "podcast", {"overall": 82}, {}, True, 0.84)
    assert passed is False
    assert reason == "execution_metrics_missing"


def test_gate_fails_ab_missing_low_conf():
    passed, reason = _passes_evidence_gate(
        True, "podcast", {"overall": 82}, {"x": 1},
        False, 0.50,   # ab_available=False, conf < 0.65
    )
    assert passed is False
    assert reason == "ab_missing_confidence_low"


def test_gate_passes_ab_missing_high_conf():
    """Ab missing but confidence above threshold → gate passes."""
    passed, reason = _passes_evidence_gate(
        True, "podcast", {"overall": 82}, {"x": 1},
        False, 0.75,   # ab_available=False but conf >= 0.65
    )
    assert passed is True


# ---------------------------------------------------------------------------
# User override tests
# ---------------------------------------------------------------------------

def test_user_override_excludes_subtitle():
    plan = _plan(subtitle_promo_reason="user_override")
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert "subtitle" not in cpr["reinforced_preferences"]
    assert any("subtitle" in r.lower() for r in cpr["reasoning"])


def test_user_override_excludes_camera():
    plan = _plan(camera_promo_reason="user_override")
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert "camera" not in cpr["reinforced_preferences"]
    assert any("camera" in r.lower() for r in cpr["reasoning"])


def test_check_user_overrides_both():
    overrides = _check_user_overrides(
        {"reason": "user_override"},
        {"reason": "user_override"},
    )
    assert "subtitle" in overrides
    assert "camera" in overrides


def test_check_user_overrides_none():
    overrides = _check_user_overrides({"reason": "applied"}, {"reason": "applied"})
    assert len(overrides) == 0


# ---------------------------------------------------------------------------
# Confidence scaling tests
# ---------------------------------------------------------------------------

def test_confidence_improved_ab_available():
    conf = _compute_confidence(0.84, True, "improved")
    assert abs(conf - 0.84) < 1e-4


def test_confidence_improved_ab_missing():
    conf = _compute_confidence(0.84, False, "improved")
    assert abs(conf - round(0.84 * 0.7, 4)) < 1e-4


def test_confidence_neutral():
    conf = _compute_confidence(0.84, True, "neutral")
    assert abs(conf - round(0.84 * 0.3, 4)) < 1e-4


def test_confidence_clamped():
    assert _compute_confidence(2.0, True, "improved") == 1.0
    assert _compute_confidence(-1.0, True, "improved") == 0.0


# ---------------------------------------------------------------------------
# Fallback tests
# ---------------------------------------------------------------------------

def test_fallback_on_none():
    result = build_creator_preference_reinforcement(None)
    cpr = result["creator_preference_reinforcement"]
    assert cpr["available"] is False
    assert cpr["reinforced_preferences"] == {}
    assert cpr["negative_signals"] == []
    assert cpr["confidence"] == 0.0
    assert cpr["reasoning"] == []


def test_fallback_on_empty_namespace():
    result = build_creator_preference_reinforcement(SimpleNamespace())
    cpr = result["creator_preference_reinforcement"]
    assert cpr["available"] is False


def test_fallback_on_empty_dict():
    result = build_creator_preference_reinforcement({})
    cpr = result["creator_preference_reinforcement"]
    assert cpr["available"] is False


def test_no_crash_on_garbage():
    result = build_creator_preference_reinforcement("garbage")
    cpr = result["creator_preference_reinforcement"]
    assert isinstance(cpr, dict)
    assert "available" in cpr


# ---------------------------------------------------------------------------
# Determinism test
# ---------------------------------------------------------------------------

def test_deterministic_output():
    plan = _plan()
    r1 = build_creator_preference_reinforcement(plan, context={"job_id": "det"})
    r2 = build_creator_preference_reinforcement(plan, context={"job_id": "det"})
    assert r1 == r2


# ---------------------------------------------------------------------------
# Output shape tests
# ---------------------------------------------------------------------------

def test_output_shape_available():
    plan = _plan()
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    for key in ("available", "creator_type", "reinforced_preferences",
                "negative_signals", "confidence", "reasoning"):
        assert key in cpr, f"Missing key: {key}"


def test_ab_missing_high_conf_still_returns_result():
    """Ab missing but confidence above threshold → engine returns available=True result."""
    plan = _plan(ab_available=False, rot_confidence=0.80)
    cpr = build_creator_preference_reinforcement(plan)["creator_preference_reinforcement"]
    assert cpr["available"] is True
    assert any("baseline" in r.lower() for r in cpr["reasoning"])
