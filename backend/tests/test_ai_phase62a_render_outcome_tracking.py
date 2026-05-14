"""
test_ai_phase62a_render_outcome_tracking.py — Tests for Phase 62A Render Outcome Tracking.

Coverage:
    - Output shape and available=True on valid input
    - Fallback on None / empty / dict input
    - creator_fit classification (high / medium / low)
    - ai_effectiveness classification (strong / moderate / weak)
    - overall_result classification (improved / neutral / regression)
    - Confidence clamped to [0.0, 1.0]
    - Confidence blend formula (all zero → 0.0)
    - Safe render reference format (rnd_ prefix, no raw job_id)
    - No unsafe fields in output (no file paths, no execution keys)
    - Deterministic: same inputs → same output
    - Quality scores extracted from render_quality_v2
    - AI execution flags extracted from ai_execution_summary
    - Quality gate blocks counted
    - No crash on garbage/partial inputs
    - Creator type from multiple fallback sources
    - Platform from creator_preference_profile
    - Execution mode from ai_execution_mode

Required execution tests:
    test_execution_full_ai_on_improved      — ai_on winner + delta≥5 + best_fit → improved/strong/high
    test_execution_baseline_missing_neutral — no ab baseline → neutral/weak/low
    test_execution_regression               — ai_off winner → regression result
    test_execution_advisory_only_no_mutation — no execution flags in output shape
"""
import pytest
from types import SimpleNamespace
from app.ai.outcome_tracking.render_outcome_tracking_engine import (
    build_render_outcome_tracking,
    _classify_ai_effectiveness,
    _classify_overall_result,
    _blend_confidence,
    _extract_quality,
    _extract_ai_execution,
    _safe_render_ref,
    _BENCHMARK_TO_FIT,
    _BENCHMARK_TO_CONF,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan(
    ab_available=True,
    ab_winner="ai_on",
    ab_delta=6,
    bench_status="best_fit",
    bench_delta=7,
    quality_overall=82,
    quality_subtitle=84,
    quality_camera=81,
    quality_hook=79,
    quality_conf=0.88,
    ab_conf=0.85,
    strategy_conf=0.86,
    subtitle_apply=True,
    camera_apply=True,
    segment_apply=False,
    qg_blocks=1,
    creator_type="podcast",
    platform="tiktok",
    execution_mode="balanced",
) -> SimpleNamespace:
    ab_eval = {
        "available":  ab_available,
        "winner":     ab_winner,
        "delta":      {"subtitle": 8, "camera": 4, "hook": 5, "overall": ab_delta},
        "confidence": ab_conf,
    } if ab_available else {
        "available":  False,
        "reason":     "baseline_missing",
        "winner":     "unknown",
        "delta":      {},
        "confidence": 0.0,
    }

    return SimpleNamespace(
        ai_execution_summary={
            "subtitle_apply":       subtitle_apply,
            "camera_apply":         camera_apply,
            "segment_apply":        segment_apply,
            "quality_gate_blocks":  qg_blocks,
            "overall_ai_assistance": "high",
        },
        ai_execution_metrics={"quality_gate": {}},
        ai_ab_evaluation=ab_eval,
        creator_benchmark_summary={
            "available":        bench_status != "unknown",
            "creator_type":     creator_type,
            "benchmark_status": bench_status,
            "overall_delta":    bench_delta,
        },
        creator_render_strategy={
            "available":    True,
            "creator_type": creator_type,
            "confidence":   strategy_conf,
        },
        render_quality_v2={
            "overall":        quality_overall,
            "subtitle_score": quality_subtitle,
            "camera_score":   quality_camera,
            "hook_score":     quality_hook,
            "confidence":     quality_conf,
        },
        ai_execution_mode={"resolved_mode": execution_mode},
        creator_preference_profile={"creator_type": creator_type, "platform": platform},
        platform_quality_feedback={},
    )


# ---------------------------------------------------------------------------
# Required execution tests
# ---------------------------------------------------------------------------

def test_execution_full_ai_on_improved():
    """Full pipeline: ai_on winner, delta≥5, best_fit benchmark → improved/strong/high."""
    plan = _plan(
        ab_available=True, ab_winner="ai_on", ab_delta=6,
        bench_status="best_fit", bench_delta=7,
        quality_overall=82, quality_subtitle=84, quality_camera=81,
        quality_conf=0.88, ab_conf=0.85, strategy_conf=0.86,
        subtitle_apply=True, camera_apply=True, qg_blocks=1,
        creator_type="podcast", platform="tiktok", execution_mode="balanced",
    )
    result = build_render_outcome_tracking(plan, context={"job_id": "test-job"})
    rot = result["render_outcome_tracking"]

    assert rot["available"] is True
    assert rot["overall_result"] == "improved"
    assert rot["ai_effectiveness"] == "strong"
    assert rot["benchmark_result"]["creator_fit"] == "high"
    assert rot["confidence"] > 0.0
    assert rot["confidence"] <= 1.0
    assert rot["creator_type"] == "podcast"
    assert rot["platform"] == "tiktok"
    assert rot["execution_mode"] == "balanced"
    assert rot["ai_execution"]["subtitle_applied"] is True
    assert rot["ai_execution"]["camera_applied"] is True
    assert rot["ai_execution"]["quality_gate_blocks"] == 1
    assert rot["ab_result"]["winner"] == "ai_on"
    assert rot["ab_result"]["overall_delta"] == 6
    assert rot["benchmark_result"]["benchmark_delta"] == 7
    assert len(rot["reasoning"]) > 0
    assert rot["render_id"].startswith("rnd_")


def test_execution_baseline_missing_neutral():
    """No baseline available → neutral outcome, weak effectiveness, low creator_fit."""
    plan = _plan(
        ab_available=False,
        bench_status="unknown",
        bench_delta=0,
    )
    result = build_render_outcome_tracking(plan, context={"job_id": "test-no-baseline"})
    rot = result["render_outcome_tracking"]

    assert rot["available"] is True
    assert rot["overall_result"] == "neutral"
    assert rot["ai_effectiveness"] == "weak"
    assert rot["benchmark_result"]["creator_fit"] == "low"
    assert rot["ab_result"]["winner"] == "unknown"
    # Cautious confidence — no ab signal
    assert rot["confidence"] < 0.7


def test_execution_regression():
    """A/B winner=ai_off → overall_result=regression."""
    plan = _plan(ab_available=True, ab_winner="ai_off", ab_delta=-5)
    result = build_render_outcome_tracking(plan, context={"job_id": "regress-test"})
    rot = result["render_outcome_tracking"]

    assert rot["available"] is True
    assert rot["overall_result"] == "regression"
    assert rot["ai_effectiveness"] == "weak"
    assert "regression" in rot["reasoning"][0].lower() or "ai off" in rot["reasoning"][0].lower()


def test_execution_advisory_only_no_mutation():
    """Phase 62A produces NO execution/mutation/ffmpeg/override keys in output."""
    plan = _plan()
    result = build_render_outcome_tracking(plan, context={"job_id": "safety-check"})
    rot = result["render_outcome_tracking"]

    forbidden = {
        "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
        "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
        "executable", "python_code", "shell", "executor_override",
        "direct_execution", "output_path", "queue_priority", "hook_rewrite",
        "crop_coordinates",
    }
    for key in forbidden:
        assert key not in rot, f"Forbidden key found in output: {key}"


# ---------------------------------------------------------------------------
# Output shape tests
# ---------------------------------------------------------------------------

def test_output_shape_available():
    """Available=True output has all expected top-level keys."""
    plan = _plan()
    rot = build_render_outcome_tracking(plan)["render_outcome_tracking"]
    for key in (
        "available", "render_id", "creator_type", "platform", "execution_mode",
        "quality", "ai_execution", "ab_result", "benchmark_result",
        "ai_effectiveness", "overall_result", "confidence", "reasoning",
    ):
        assert key in rot, f"Missing key: {key}"


def test_output_shape_quality_keys():
    """Quality dict has subtitle, camera, hook, overall."""
    plan = _plan()
    q = build_render_outcome_tracking(plan)["render_outcome_tracking"]["quality"]
    for k in ("subtitle", "camera", "hook", "overall"):
        assert k in q


def test_output_shape_ai_execution_keys():
    """ai_execution dict has expected keys."""
    plan = _plan()
    ae = build_render_outcome_tracking(plan)["render_outcome_tracking"]["ai_execution"]
    for k in ("subtitle_applied", "camera_applied", "segment_applied", "quality_gate_blocks"):
        assert k in ae


def test_output_shape_ab_result_keys():
    """ab_result dict has winner and overall_delta."""
    plan = _plan()
    ab = build_render_outcome_tracking(plan)["render_outcome_tracking"]["ab_result"]
    assert "winner" in ab
    assert "overall_delta" in ab


def test_output_shape_benchmark_result_keys():
    """benchmark_result has creator_fit and benchmark_delta."""
    plan = _plan()
    br = build_render_outcome_tracking(plan)["render_outcome_tracking"]["benchmark_result"]
    assert "creator_fit" in br
    assert "benchmark_delta" in br


# ---------------------------------------------------------------------------
# Fallback tests
# ---------------------------------------------------------------------------

def test_fallback_on_none():
    result = build_render_outcome_tracking(None)
    rot = result["render_outcome_tracking"]
    assert rot["available"] is False
    assert rot["confidence"] == 0.0
    assert rot["reasoning"] == []


def test_fallback_on_empty_namespace():
    result = build_render_outcome_tracking(SimpleNamespace())
    rot = result["render_outcome_tracking"]
    assert rot["available"] is True
    assert rot["confidence"] == 0.0


def test_fallback_on_empty_dict():
    result = build_render_outcome_tracking({})
    rot = result["render_outcome_tracking"]
    assert rot["available"] is True
    assert rot["confidence"] == 0.0


def test_no_crash_on_garbage_input():
    """No exception on completely garbage input — engine returns gracefully."""
    result = build_render_outcome_tracking("garbage_string")
    rot = result["render_outcome_tracking"]
    # String input: _get_dict falls back to empty dicts, returns available=True with zeros
    assert isinstance(rot, dict)
    assert "available" in rot
    assert rot["confidence"] == 0.0


def test_no_crash_partial_data():
    """Partial data — missing most fields — returns gracefully."""
    plan = SimpleNamespace(render_quality_v2={"overall": 75, "confidence": 0.80})
    result = build_render_outcome_tracking(plan)
    rot = result["render_outcome_tracking"]
    assert rot["available"] is True
    assert rot["quality"]["overall"] == 75


# ---------------------------------------------------------------------------
# creator_fit classification tests
# ---------------------------------------------------------------------------

def test_creator_fit_high_when_best_fit():
    assert _BENCHMARK_TO_FIT["best_fit"] == "high"


def test_creator_fit_medium_when_improving():
    assert _BENCHMARK_TO_FIT["improving"] == "medium"


def test_creator_fit_low_when_needs_review():
    assert _BENCHMARK_TO_FIT["needs_review"] == "low"


def test_creator_fit_low_when_unknown():
    assert _BENCHMARK_TO_FIT["unknown"] == "low"


def test_creator_fit_in_output_best_fit():
    plan = _plan(bench_status="best_fit")
    rot = build_render_outcome_tracking(plan)["render_outcome_tracking"]
    assert rot["benchmark_result"]["creator_fit"] == "high"


def test_creator_fit_in_output_improving():
    plan = _plan(bench_status="improving")
    rot = build_render_outcome_tracking(plan)["render_outcome_tracking"]
    assert rot["benchmark_result"]["creator_fit"] == "medium"


def test_creator_fit_in_output_needs_review():
    plan = _plan(bench_status="needs_review")
    rot = build_render_outcome_tracking(plan)["render_outcome_tracking"]
    assert rot["benchmark_result"]["creator_fit"] == "low"


# ---------------------------------------------------------------------------
# ai_effectiveness classification tests
# ---------------------------------------------------------------------------

def test_ai_effectiveness_strong_delta_ge5():
    assert _classify_ai_effectiveness(True, "ai_on", 5) == "strong"
    assert _classify_ai_effectiveness(True, "ai_on", 10) == "strong"


def test_ai_effectiveness_moderate_delta_2_to_4():
    assert _classify_ai_effectiveness(True, "ai_on", 2) == "moderate"
    assert _classify_ai_effectiveness(True, "ai_on", 4) == "moderate"


def test_ai_effectiveness_weak_delta_lt2():
    assert _classify_ai_effectiveness(True, "ai_on", 1) == "weak"
    assert _classify_ai_effectiveness(True, "ai_on", 0) == "weak"


def test_ai_effectiveness_weak_when_ai_off():
    assert _classify_ai_effectiveness(True, "ai_off", 10) == "weak"


def test_ai_effectiveness_weak_when_tie():
    assert _classify_ai_effectiveness(True, "tie", 0) == "weak"


def test_ai_effectiveness_weak_when_ab_unavailable():
    assert _classify_ai_effectiveness(False, "ai_on", 8) == "weak"


# ---------------------------------------------------------------------------
# overall_result classification tests
# ---------------------------------------------------------------------------

def test_overall_result_improved_strong():
    assert _classify_overall_result(True, "ai_on", "strong") == "improved"


def test_overall_result_improved_moderate():
    assert _classify_overall_result(True, "ai_on", "moderate") == "improved"


def test_overall_result_regression():
    assert _classify_overall_result(True, "ai_off", "weak") == "regression"


def test_overall_result_neutral_tie():
    assert _classify_overall_result(True, "tie", "weak") == "neutral"


def test_overall_result_neutral_no_baseline():
    assert _classify_overall_result(False, "unknown", "weak") == "neutral"


def test_regression_takes_priority_over_weak():
    assert _classify_overall_result(True, "ai_off", "weak") == "regression"


# ---------------------------------------------------------------------------
# Confidence tests
# ---------------------------------------------------------------------------

def test_confidence_clamped_above():
    result = _blend_confidence(1.5, 1.5, 1.5, 1.5)
    assert result == 1.0


def test_confidence_clamped_below():
    result = _blend_confidence(-1.0, -1.0, -1.0, -1.0)
    assert result == 0.0


def test_confidence_all_zero():
    result = _blend_confidence(0.0, 0.0, 0.0, 0.0)
    assert result == 0.0


def test_confidence_only_quality():
    """Only quality signal available — others zero."""
    result = _blend_confidence(1.0, 0.0, 0.0, 0.0)
    # quality weight = 0.30, total denominator = 1.0 → conf = 0.30
    assert abs(result - 0.30) < 0.001


def test_confidence_full_blend():
    """All signals at 1.0 → confidence = 1.0."""
    result = _blend_confidence(1.0, 1.0, 1.0, 1.0)
    assert result == 1.0


def test_confidence_no_ab_lowers_total():
    """Missing AB signal (0.0) should produce lower confidence than when AB=1.0."""
    conf_with_ab    = _blend_confidence(0.9, 0.9, 0.9, 0.9)
    conf_without_ab = _blend_confidence(0.9, 0.0, 0.9, 0.9)
    assert conf_without_ab < conf_with_ab


# ---------------------------------------------------------------------------
# Safe render reference tests
# ---------------------------------------------------------------------------

def test_safe_render_ref_format():
    ref = _safe_render_ref("job-123")
    assert ref.startswith("rnd_")
    assert len(ref) == 12  # "rnd_" + 8 hex chars


def test_safe_render_ref_deterministic():
    assert _safe_render_ref("job-abc") == _safe_render_ref("job-abc")


def test_safe_render_ref_different_ids():
    assert _safe_render_ref("job-a") != _safe_render_ref("job-b")


def test_safe_render_ref_no_raw_job_id():
    """render_id must not equal the job_id."""
    job_id = "my-internal-job-12345"
    ref = _safe_render_ref(job_id)
    assert job_id not in ref


def test_render_id_in_output():
    plan = _plan()
    rot = build_render_outcome_tracking(plan, context={"job_id": "test-id"})["render_outcome_tracking"]
    assert rot["render_id"].startswith("rnd_")
    assert "test-id" not in rot["render_id"]


# ---------------------------------------------------------------------------
# Quality extraction tests
# ---------------------------------------------------------------------------

def test_quality_extracted_from_rqv2():
    rqv2 = {"subtitle_score": 84, "camera_score": 81, "hook_score": 79, "overall": 82}
    q = _extract_quality(rqv2)
    assert q["subtitle"] == 84
    assert q["camera"] == 81
    assert q["hook"] == 79
    assert q["overall"] == 82


def test_quality_scores_clamped():
    rqv2 = {"subtitle_score": 150, "camera_score": -10, "hook_score": 0, "overall": 200}
    q = _extract_quality(rqv2)
    assert q["subtitle"] == 100
    assert q["camera"] == 0
    assert q["overall"] == 100


def test_quality_overall_derived_when_missing():
    rqv2 = {"subtitle_score": 80, "camera_score": 80, "hook_score": 80}
    q = _extract_quality(rqv2)
    assert q["overall"] == 80


# ---------------------------------------------------------------------------
# AI execution extraction tests
# ---------------------------------------------------------------------------

def test_ai_execution_flags_from_summary():
    summary = {
        "subtitle_apply": True,
        "camera_apply": False,
        "segment_apply": True,
        "quality_gate_blocks": 2,
    }
    ae = _extract_ai_execution(summary, {})
    assert ae["subtitle_applied"] is True
    assert ae["camera_applied"] is False
    assert ae["segment_applied"] is True
    assert ae["quality_gate_blocks"] == 2


def test_quality_gate_blocks_from_metrics():
    """Falls back to counting from exec_metrics.quality_gate when summary shows 0."""
    summary = {"subtitle_apply": True, "camera_apply": True, "segment_apply": False, "quality_gate_blocks": 0}
    metrics = {"quality_gate": {"subtitle_blocked": True, "camera_blocked": True, "segment_blocked": False}}
    ae = _extract_ai_execution(summary, metrics)
    assert ae["quality_gate_blocks"] == 2


# ---------------------------------------------------------------------------
# Determinism tests
# ---------------------------------------------------------------------------

def test_deterministic_output():
    """Same inputs → same output."""
    plan = _plan()
    r1 = build_render_outcome_tracking(plan, context={"job_id": "det-test"})
    r2 = build_render_outcome_tracking(plan, context={"job_id": "det-test"})
    assert r1 == r2


# ---------------------------------------------------------------------------
# Creator type / platform / mode source tests
# ---------------------------------------------------------------------------

def test_creator_type_from_creator_render_strategy():
    plan = SimpleNamespace(
        creator_render_strategy={"available": True, "creator_type": "viral_short_form", "confidence": 0.8},
        creator_benchmark_summary={},
        creator_preference_profile={},
        ai_execution_summary={},
        ai_execution_metrics={},
        ai_ab_evaluation={},
        render_quality_v2={},
        ai_execution_mode={},
        platform_quality_feedback={},
    )
    rot = build_render_outcome_tracking(plan)["render_outcome_tracking"]
    assert rot["creator_type"] == "viral_short_form"


def test_platform_from_creator_preference_profile():
    plan = _plan(platform="youtube_shorts")
    rot = build_render_outcome_tracking(plan)["render_outcome_tracking"]
    assert rot["platform"] == "youtube_shorts"


def test_execution_mode_from_ai_execution_mode():
    plan = _plan(execution_mode="safe")
    rot = build_render_outcome_tracking(plan)["render_outcome_tracking"]
    assert rot["execution_mode"] == "safe"
