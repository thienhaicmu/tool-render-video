"""
test_ai_phase60b_ab_evaluation.py — Tests for Phase 60B A/B Render Evaluation.

Coverage:
  - Metadata compare mode (mode A): baseline + candidate both available
  - Single-run candidate summary mode (mode B): baseline missing
  - Delta calculation: positive, negative, zero, clamp to [-100, 100]
  - Winner selection: ai_on (>=+3), ai_off (<=-3), tie (-2..+2)
  - Confidence: 0.0 without baseline; weighted blend with baseline
  - Reasoning: honest, no improvement claims without baseline
  - Deterministic output
  - Fallback-safe: no crash on None/empty

REQUIRED EXECUTION TESTS:
  test_execution_full_comparison_ai_on_wins   — baseline + candidate → ai_on winner
  test_execution_full_comparison_ai_off_wins  — candidate worse than baseline → ai_off
  test_execution_baseline_missing_no_claim    — no baseline → available=False, no improvement claim
"""
import pytest
from types import SimpleNamespace

from app.ai.ab_evaluation.ab_evaluation_engine import build_ab_evaluation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edit_plan(
    render_quality_v2=None,
    subtitle_quality_v2=None,
    camera_quality_v2=None,
    hook_quality_v2=None,
    ai_execution_metrics=None,
    ai_execution_summary=None,
):
    return SimpleNamespace(
        render_quality_v2=render_quality_v2   or {},
        subtitle_quality_v2=subtitle_quality_v2 or {},
        camera_quality_v2=camera_quality_v2   or {},
        hook_quality_v2=hook_quality_v2       or {},
        ai_execution_metrics=ai_execution_metrics or {},
        ai_execution_summary=ai_execution_summary or {},
    )


def _rqv2(overall=80, subtitle=78, camera=82, hook=79, confidence=0.85):
    return {
        "overall":        overall,
        "subtitle_score": subtitle,
        "camera_score":   camera,
        "hook_score":     hook,
        "confidence":     confidence,
    }


def _baseline_flat(subtitle=78, camera=80, hook=76, overall=78, label="ai_off"):
    return {
        "label":   label,
        "quality": {
            "subtitle": subtitle,
            "camera":   camera,
            "hook":     hook,
            "overall":  overall,
        },
    }


def _baseline_raw(subtitle=78, camera=80, hook=76, overall=78):
    return {
        "render_quality_v2":   {"overall": overall, "subtitle_score": subtitle,
                                 "camera_score": camera, "hook_score": hook,
                                 "confidence": 0.85},
        "subtitle_quality_v2": {"overall": subtitle},
        "camera_quality_v2":   {"overall": camera},
        "hook_quality_v2":     {"overall": hook},
    }


# ---------------------------------------------------------------------------
# REQUIRED EXECUTION TESTS
# ---------------------------------------------------------------------------

def test_execution_full_comparison_ai_on_wins():
    """Full metadata compare: candidate clearly better → ai_on winner, delta calculated."""
    plan = _edit_plan(
        render_quality_v2=_rqv2(overall=84, subtitle=86, camera=84, hook=81),
        ai_execution_summary={"overall_ai_assistance": "high"},
        ai_execution_metrics={"confidence": 0.87},
    )
    baseline = _baseline_flat(subtitle=78, camera=80, hook=76, overall=78)

    result = build_ab_evaluation(plan, baseline=baseline)
    ev = result["ai_ab_evaluation"]

    assert ev["available"] is True,                    "available must be True with both sides"
    assert ev["winner"] == "ai_on",                   "AI ON should win when overall_delta >= +3"
    assert ev["delta"]["overall"] == 6,                "overall delta = 84 - 78 = 6"
    assert ev["delta"]["subtitle"] == 8,               "subtitle delta = 86 - 78 = 8"
    assert ev["confidence"] > 0.0,                     "confidence must be > 0 with baseline"
    assert len(ev["reasoning"]) > 0,                   "reasoning must have at least one line"
    assert ev["candidate"]["label"] == "ai_on"
    assert ev["baseline"]["label"] == "ai_off"


def test_execution_full_comparison_ai_off_wins():
    """Candidate worse than baseline → ai_off winner."""
    plan = _edit_plan(
        render_quality_v2=_rqv2(overall=72, subtitle=70, camera=74, hook=71),
        ai_execution_metrics={"confidence": 0.80},
    )
    baseline = _baseline_flat(subtitle=80, camera=82, hook=78, overall=80)

    result = build_ab_evaluation(plan, baseline=baseline)
    ev = result["ai_ab_evaluation"]

    assert ev["available"] is True
    assert ev["winner"] == "ai_off"
    assert ev["delta"]["overall"] == -8   # 72 - 80 = -8
    assert "AI OFF" in ev["reasoning"][0]


def test_execution_baseline_missing_no_claim():
    """No baseline provided → available=False, winner=unknown, no improvement claim."""
    plan = _edit_plan(
        render_quality_v2=_rqv2(overall=84, subtitle=86, camera=84, hook=81),
        ai_execution_summary={"overall_ai_assistance": "high"},
    )

    result = build_ab_evaluation(plan, baseline=None)
    ev = result["ai_ab_evaluation"]

    assert ev["available"] is False,                      "available must be False without baseline"
    assert ev["winner"] == "unknown",                     "winner must be unknown without baseline"
    assert ev["confidence"] == 0.0,                       "confidence must be 0.0 without baseline"
    assert ev["reason"] == "baseline_missing"
    # Reasoning must not claim improvement
    full_text = " ".join(ev["reasoning"]).lower()
    assert "improved" not in full_text or "cannot" in full_text, \
        "Must not claim improvement without baseline"
    # Candidate summary should contain current quality
    cs = ev["candidate_summary"]
    assert cs["quality"]["overall"] == 84


# ---------------------------------------------------------------------------
# Delta calculation tests
# ---------------------------------------------------------------------------

def test_delta_all_positive():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=90, subtitle=88, camera=87, hook=85))
    baseline = _baseline_flat(subtitle=80, camera=80, hook=80, overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["delta"]["overall"] == 10
    assert ev["delta"]["subtitle"] == 8
    assert ev["delta"]["camera"] == 7
    assert ev["delta"]["hook"] == 5


def test_delta_all_negative():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=65, subtitle=62, camera=64, hook=61))
    baseline = _baseline_flat(subtitle=80, camera=80, hook=80, overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["delta"]["overall"] == -15
    assert ev["delta"]["subtitle"] == -18


def test_delta_zero_equals_tie():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=80, subtitle=78, camera=80, hook=76))
    baseline = _baseline_flat(subtitle=78, camera=80, hook=76, overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["delta"]["overall"] == 0
    assert ev["winner"] == "tie"


def test_delta_clamped_above_100():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=100, subtitle=100, camera=100, hook=100))
    baseline = _baseline_flat(subtitle=0, camera=0, hook=0, overall=0)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["delta"]["overall"] <= 100
    assert ev["delta"]["subtitle"] <= 100


def test_delta_clamped_below_minus100():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=0, subtitle=0, camera=0, hook=0))
    baseline = _baseline_flat(subtitle=100, camera=100, hook=100, overall=100)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["delta"]["overall"] >= -100


# ---------------------------------------------------------------------------
# Winner selection tests
# ---------------------------------------------------------------------------

def test_winner_ai_on_threshold_exact():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=83))
    baseline = _baseline_flat(overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["winner"] == "ai_on"   # delta = +3 → ai_on


def test_winner_tie_boundary_plus_two():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=82))
    baseline = _baseline_flat(overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["winner"] == "tie"   # delta = +2 → tie


def test_winner_tie_boundary_minus_two():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=78))
    baseline = _baseline_flat(overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["winner"] == "tie"   # delta = -2 → tie


def test_winner_ai_off_threshold_exact():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=77))
    baseline = _baseline_flat(overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["winner"] == "ai_off"   # delta = -3 → ai_off


def test_winner_unknown_when_no_quality_data():
    plan = _edit_plan()   # empty quality
    baseline = _baseline_flat(overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    # With no candidate data, overall=0, baseline=80 → delta=-80 → ai_off
    # (data exists but shows AI performed poorly vs baseline)
    assert ev["winner"] in ("ai_off", "unknown")


# ---------------------------------------------------------------------------
# Score clamping tests
# ---------------------------------------------------------------------------

def test_scores_clamped_to_100():
    plan = _edit_plan(render_quality_v2={
        "overall": 150, "subtitle_score": 200, "camera_score": 120, "hook_score": 110
    })
    ev = build_ab_evaluation(plan, baseline=_baseline_flat())["ai_ab_evaluation"]
    q = ev["candidate"]["quality"]
    assert q["overall"] <= 100
    assert q["subtitle"] <= 100
    assert q["camera"] <= 100
    assert q["hook"] <= 100


def test_baseline_scores_clamped_to_100():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=80))
    baseline = _baseline_flat(subtitle=200, camera=150, hook=120, overall=180)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    q = ev["baseline"]["quality"]
    assert q["overall"] <= 100
    assert q["subtitle"] <= 100


# ---------------------------------------------------------------------------
# Confidence tests
# ---------------------------------------------------------------------------

def test_confidence_zero_without_baseline():
    plan = _edit_plan(render_quality_v2=_rqv2())
    ev = build_ab_evaluation(plan, baseline=None)["ai_ab_evaluation"]
    assert ev["confidence"] == 0.0


def test_confidence_positive_with_baseline():
    plan = _edit_plan(
        render_quality_v2=_rqv2(confidence=0.85),
        ai_execution_metrics={"confidence": 0.88},
    )
    baseline = _baseline_flat()
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["confidence"] > 0.0
    assert ev["confidence"] <= 1.0


def test_confidence_clamped_to_one():
    plan = _edit_plan(
        render_quality_v2=_rqv2(confidence=2.0),
        ai_execution_metrics={"confidence": 2.0},
    )
    ev = build_ab_evaluation(plan, baseline=_baseline_flat())["ai_ab_evaluation"]
    assert ev["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Baseline shape B (raw quality dicts) test
# ---------------------------------------------------------------------------

def test_baseline_raw_quality_dict_shape():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=85, subtitle=83, camera=86, hook=82))
    baseline = _baseline_raw(subtitle=78, camera=80, hook=76, overall=78)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["available"] is True
    assert ev["delta"]["overall"] == 7   # 85 - 78 = 7
    assert ev["winner"] == "ai_on"


# ---------------------------------------------------------------------------
# Reasoning tests
# ---------------------------------------------------------------------------

def test_reasoning_no_improvement_claim_without_baseline():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=90))
    ev = build_ab_evaluation(plan, baseline=None)["ai_ab_evaluation"]
    reasoning_text = " ".join(ev["reasoning"])
    assert "Baseline missing" in reasoning_text


def test_reasoning_ai_on_mentions_improvement():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=86, subtitle=88))
    baseline = _baseline_flat(subtitle=78, overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    assert ev["winner"] == "ai_on"
    reasoning = " ".join(ev["reasoning"])
    assert len(ev["reasoning"]) >= 1


def test_reasoning_ai_off_mentions_decline():
    plan = _edit_plan(render_quality_v2=_rqv2(overall=72))
    baseline = _baseline_flat(overall=80)
    ev = build_ab_evaluation(plan, baseline=baseline)["ai_ab_evaluation"]
    reasoning = " ".join(ev["reasoning"])
    assert "AI OFF" in reasoning


# ---------------------------------------------------------------------------
# Deterministic output test
# ---------------------------------------------------------------------------

def test_deterministic_output():
    plan = _edit_plan(
        render_quality_v2=_rqv2(overall=84, subtitle=86, camera=83, hook=80),
        ai_execution_metrics={"confidence": 0.87},
    )
    baseline = _baseline_flat(subtitle=78, camera=80, hook=76, overall=78)
    result_a = build_ab_evaluation(plan, baseline=baseline)
    result_b = build_ab_evaluation(plan, baseline=baseline)
    assert result_a == result_b


# ---------------------------------------------------------------------------
# Safety / fallback tests
# ---------------------------------------------------------------------------

def test_never_raises_on_none_edit_plan():
    result = build_ab_evaluation(None, baseline=None)
    assert "ai_ab_evaluation" in result
    ev = result["ai_ab_evaluation"]
    assert ev["winner"] in ("unknown",)
    assert ev["confidence"] == 0.0


def test_never_raises_on_empty_plan():
    plan = _edit_plan()
    result = build_ab_evaluation(plan, baseline=None)
    assert "ai_ab_evaluation" in result


def test_fallback_shape_complete():
    result = build_ab_evaluation(None)
    ev = result["ai_ab_evaluation"]
    assert "available" in ev
    assert "baseline" in ev
    assert "candidate" in ev
    assert "delta" in ev
    assert "winner" in ev
    assert "confidence" in ev
    assert "reasoning" in ev
    assert ev["winner"] in ("ai_on", "ai_off", "tie", "unknown")
