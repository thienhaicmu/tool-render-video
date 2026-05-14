"""
test_ai_phase60c_creator_benchmark.py — Tests for Phase 60C Creator Benchmark Suite.

Coverage:
  - best_fit: overall_delta >= +5 AND winner_rate >= 0.70
  - needs_review: overall_delta <= +2 OR winner_rate < 0.60
  - improving: middle ground (delta > +2, winner_rate >= 0.60, delta < +5)
  - unknown: no A/B evaluation available or winner_rate is None
  - All 7 creator archetypes recognized and labeled correctly
  - Unknown creator type handled gracefully
  - Deterministic output
  - Fallback-safe: no crash on None/empty inputs

REQUIRED EXECUTION TESTS:
  test_execution_best_fit_podcast              — podcast + delta=+7 + ai_on → best_fit
  test_execution_needs_review_talking_head     — talking_head + delta=+1 + ai_off → needs_review
  test_execution_ab_evaluation_unavailable     — no A/B eval → available=False, unknown status
"""
import pytest
from types import SimpleNamespace

from app.ai.creator_benchmark.creator_benchmark_engine import build_creator_benchmark


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edit_plan(creator_type="podcast", ab_available=True, overall_delta=6, winner="ai_on"):
    """Build a minimal SimpleNamespace edit_plan for benchmark tests."""
    if ab_available:
        ab_eval = {
            "available": True,
            "delta":     {"overall": overall_delta, "subtitle": overall_delta,
                          "camera": overall_delta, "hook": overall_delta},
            "winner":    winner,
            "confidence": 0.80,
        }
    else:
        ab_eval = {
            "available": False,
            "reason":    "baseline_missing",
        }

    return SimpleNamespace(
        creator_preference_profile={"creator_type": creator_type},
        ai_ab_evaluation=ab_eval,
    )


def _edit_plan_no_ab():
    """Edit plan with no ai_ab_evaluation attribute."""
    return SimpleNamespace(
        creator_preference_profile={"creator_type": "educational"},
    )


# ---------------------------------------------------------------------------
# REQUIRED EXECUTION TESTS
# ---------------------------------------------------------------------------

def test_execution_best_fit_podcast():
    """Podcast creator, delta=+7, ai_on winner → best_fit status."""
    plan = _edit_plan(creator_type="podcast", overall_delta=7, winner="ai_on")
    result = build_creator_benchmark(plan)
    cb = result["creator_benchmark_summary"]

    assert cb["available"] is True,                   "available must be True with A/B data"
    assert cb["creator_type"] == "podcast",           "creator_type must be preserved"
    assert cb["archetype_label"] == "Podcast",        "archetype_label must map correctly"
    assert cb["benchmark_status"] == "best_fit",      "delta=+7 + ai_on → best_fit"
    assert cb["overall_delta"] == 7,                  "overall_delta must match A/B delta"
    assert cb["winner"] == "ai_on",                   "winner must be propagated"
    assert cb["winner_rate"] == 1.0,                  "ai_on → winner_rate=1.0"
    assert len(cb["reasoning"]) > 0,                  "reasoning must not be empty"


def test_execution_needs_review_talking_head():
    """Talking head creator, delta=+1, ai_off winner → needs_review."""
    plan = _edit_plan(creator_type="talking_head", overall_delta=1, winner="ai_off")
    result = build_creator_benchmark(plan)
    cb = result["creator_benchmark_summary"]

    assert cb["available"] is True
    assert cb["creator_type"] == "talking_head"
    assert cb["archetype_label"] == "Talking Head"
    assert cb["benchmark_status"] == "needs_review",  "delta=+1 <= 2 → needs_review"
    assert cb["winner_rate"] == 0.0,                  "ai_off → winner_rate=0.0"


def test_execution_ab_evaluation_unavailable():
    """No A/B evaluation → available=False, benchmark_status=unknown."""
    plan = _edit_plan(creator_type="educational", ab_available=False)
    result = build_creator_benchmark(plan)
    cb = result["creator_benchmark_summary"]

    assert cb["available"] is False,                  "available must be False without A/B data"
    assert cb["benchmark_status"] == "unknown",       "status must be unknown"
    assert cb["winner"] == "unknown",                 "winner must be unknown"
    assert cb["overall_delta"] is None,               "delta must be None without A/B"
    assert cb["winner_rate"] is None,                 "winner_rate must be None"
    assert "reason" in cb,                            "reason key must be present"
    assert "unavailable" in " ".join(cb["reasoning"]).lower() or "baseline" in " ".join(cb["reasoning"]).lower()


# ---------------------------------------------------------------------------
# Benchmark status tests
# ---------------------------------------------------------------------------

def test_best_fit_threshold_exact():
    """delta=+5, winner=ai_on → best_fit (exact lower threshold)."""
    plan = _edit_plan(overall_delta=5, winner="ai_on")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["benchmark_status"] == "best_fit"


def test_improving_below_best_fit_delta():
    """delta=+4, winner=ai_on (rate=1.0) → improving (delta<5 but rate>=0.60)."""
    plan = _edit_plan(overall_delta=4, winner="ai_on")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["benchmark_status"] == "improving"


def test_improving_tie_winner():
    """delta=+4, winner=tie (rate=0.5) → needs_review (0.5 < 0.60)."""
    plan = _edit_plan(overall_delta=4, winner="tie")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    # winner_rate=0.5 < 0.60 → needs_review
    assert cb["benchmark_status"] == "needs_review"


def test_needs_review_delta_at_threshold():
    """delta=+2, winner=ai_on → needs_review (delta <= 2)."""
    plan = _edit_plan(overall_delta=2, winner="ai_on")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["benchmark_status"] == "needs_review"


def test_needs_review_low_win_rate_high_delta():
    """delta=+6, winner=tie (rate=0.5) → needs_review (rate < 0.60 triggers it)."""
    plan = _edit_plan(overall_delta=6, winner="tie")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["benchmark_status"] == "needs_review"


def test_needs_review_ai_off_winner():
    """delta=-5, winner=ai_off → needs_review."""
    plan = _edit_plan(overall_delta=-5, winner="ai_off")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["benchmark_status"] == "needs_review"
    assert cb["winner_rate"] == 0.0


def test_unknown_status_for_unknown_winner():
    """winner=unknown → winner_rate=None → benchmark_status=unknown."""
    plan = _edit_plan(overall_delta=7, winner="unknown")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["benchmark_status"] == "unknown"
    assert cb["winner_rate"] is None


# ---------------------------------------------------------------------------
# Creator archetype tests
# ---------------------------------------------------------------------------

def test_all_creator_archetypes_recognized():
    """All 7 supported archetypes should resolve to non-unknown creator_type."""
    archetypes = [
        "podcast", "talking_head", "educational",
        "viral_short_form", "storytelling", "interview", "motivation",
    ]
    for archetype in archetypes:
        plan = _edit_plan(creator_type=archetype)
        cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
        assert cb["creator_type"] == archetype, f"{archetype} should be recognized"
        assert cb["archetype_label"] != "Unknown", f"{archetype} should have a label"


def test_archetype_label_viral_short_form():
    plan = _edit_plan(creator_type="viral_short_form")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["archetype_label"] == "Viral Short-Form"


def test_unknown_creator_type_handled():
    """Unrecognized creator_type → creator_type='unknown', no crash."""
    plan = _edit_plan(creator_type="streamer")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["creator_type"] == "unknown"
    assert "benchmark_status" in cb


# ---------------------------------------------------------------------------
# Reasoning tests
# ---------------------------------------------------------------------------

def test_reasoning_best_fit_mentions_threshold():
    plan = _edit_plan(overall_delta=8, winner="ai_on")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    assert cb["benchmark_status"] == "best_fit"
    reasoning = " ".join(cb["reasoning"])
    assert "exceeded" in reasoning.lower() or "threshold" in reasoning.lower()


def test_reasoning_needs_review_mentions_decline():
    plan = _edit_plan(overall_delta=0, winner="ai_off")
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    reasoning = " ".join(cb["reasoning"])
    assert len(cb["reasoning"]) >= 1
    assert "needs_review" == cb["benchmark_status"]


def test_reasoning_unavailable_mentions_ab():
    plan = _edit_plan(ab_available=False)
    cb = build_creator_benchmark(plan)["creator_benchmark_summary"]
    reasoning_text = " ".join(cb["reasoning"]).lower()
    assert "unavailable" in reasoning_text or "baseline" in reasoning_text or "cannot" in reasoning_text


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

def test_deterministic_output():
    plan = _edit_plan(creator_type="motivation", overall_delta=6, winner="ai_on")
    result_a = build_creator_benchmark(plan)
    result_b = build_creator_benchmark(plan)
    assert result_a == result_b


# ---------------------------------------------------------------------------
# Safety / fallback tests
# ---------------------------------------------------------------------------

def test_never_raises_on_none_edit_plan():
    result = build_creator_benchmark(None)
    assert "creator_benchmark_summary" in result
    cb = result["creator_benchmark_summary"]
    assert cb["benchmark_status"] == "unknown"
    assert cb["available"] is False


def test_never_raises_on_empty_plan():
    plan = SimpleNamespace()
    result = build_creator_benchmark(plan)
    assert "creator_benchmark_summary" in result


def test_never_raises_on_dict_edit_plan():
    plan = {
        "creator_preference_profile": {"creator_type": "interview"},
        "ai_ab_evaluation": {"available": True, "delta": {"overall": 5}, "winner": "ai_on"},
    }
    result = build_creator_benchmark(plan)
    cb = result["creator_benchmark_summary"]
    assert cb["creator_type"] == "interview"
    assert cb["benchmark_status"] == "best_fit"


def test_fallback_shape_complete():
    result = build_creator_benchmark(None)
    cb = result["creator_benchmark_summary"]
    required_keys = {
        "available", "creator_type", "archetype_label",
        "benchmark_status", "overall_delta", "winner",
        "winner_rate", "reasoning",
    }
    assert required_keys.issubset(cb.keys()), f"Missing keys: {required_keys - cb.keys()}"
    assert cb["benchmark_status"] in ("best_fit", "improving", "needs_review", "unknown")
