"""Tests for app.features.render.engine.pipeline.pipeline_ranking."""
from __future__ import annotations

import pytest

from app.features.render.engine.pipeline.pipeline_ranking import (
    resolve_combined_score_weights,
    _score_component,
    _first_score,
    _compute_output_ranking_entry,
)


# ---------------------------------------------------------------------------
# resolve_combined_score_weights — adaptive=False (fixed weights)
# ---------------------------------------------------------------------------

def test_fixed_weights_sum_to_1():
    result = resolve_combined_score_weights(
        target_market="US",
        has_market_score=True,
        has_hook_score=True,
        duration=30.0,
        adaptive_enabled=False,
    )
    total = result["viral_weight"] + result["market_weight"] + result["hook_weight"]
    assert total == pytest.approx(1.0)


def test_fixed_weights_returns_fixed_reason():
    result = resolve_combined_score_weights(
        target_market=None,
        has_market_score=True,
        has_hook_score=True,
        duration=30.0,
        adaptive_enabled=False,
    )
    assert result["reason"] == "fixed"


def test_fixed_weights_values_match_defaults():
    result = resolve_combined_score_weights(
        target_market="JP",
        has_market_score=True,
        has_hook_score=True,
        duration=30.0,
        adaptive_enabled=False,
    )
    assert result["viral_weight"] == pytest.approx(0.50)
    assert result["market_weight"] == pytest.approx(0.30)
    assert result["hook_weight"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# resolve_combined_score_weights — adaptive=True
# ---------------------------------------------------------------------------

def test_adaptive_us_market_boosts_hook_and_viral():
    fixed = resolve_combined_score_weights(
        target_market="US",
        has_market_score=True,
        has_hook_score=True,
        duration=30.0,
        adaptive_enabled=False,
    )
    adaptive = resolve_combined_score_weights(
        target_market="US",
        has_market_score=True,
        has_hook_score=True,
        duration=30.0,
        adaptive_enabled=True,
    )
    # US market: hook+viral boosted vs fixed; market reduced
    assert adaptive["hook_weight"] > fixed["hook_weight"]
    assert adaptive["viral_weight"] > fixed["viral_weight"]
    assert adaptive["market_weight"] < fixed["market_weight"]


def test_adaptive_no_market_score_redistributes():
    result = resolve_combined_score_weights(
        target_market="US",
        has_market_score=False,
        has_hook_score=True,
        duration=30.0,
        adaptive_enabled=True,
    )
    # market weight must be 0 when no market score
    assert result["market_weight"] == pytest.approx(0.0)
    total = result["viral_weight"] + result["market_weight"] + result["hook_weight"]
    assert total == pytest.approx(1.0)


def test_adaptive_weights_always_sum_to_1_various_inputs():
    scenarios = [
        ("US", True, True, 30.0),
        ("EU", True, False, 60.0),
        ("JP", False, True, 5.0),
        (None, False, False, 120.0),
        ("US", True, True, 0.0),
    ]
    for market, has_mkt, has_hook, dur in scenarios:
        result = resolve_combined_score_weights(
            target_market=market,
            has_market_score=has_mkt,
            has_hook_score=has_hook,
            duration=dur,
            adaptive_enabled=True,
        )
        total = result["viral_weight"] + result["market_weight"] + result["hook_weight"]
        assert total == pytest.approx(1.0, abs=1e-4), (
            f"Weights did not sum to 1.0 for scenario {market},{has_mkt},{has_hook},{dur}: {result}"
        )


# ---------------------------------------------------------------------------
# _score_component
# ---------------------------------------------------------------------------

def test_score_component_none_returns_default():
    assert _score_component(None, 50.0) == pytest.approx(50.0)


def test_score_component_empty_string_returns_default():
    assert _score_component("", 42.0) == pytest.approx(42.0)


def test_score_component_clamps_above_100():
    assert _score_component(150.0) == pytest.approx(100.0)


def test_score_component_clamps_below_0():
    assert _score_component(-10.0) == pytest.approx(0.0)


def test_score_component_valid_value_returned():
    assert _score_component(75.5) == pytest.approx(75.5)


def test_score_component_invalid_string_returns_default():
    assert _score_component("notanumber", 33.0) == pytest.approx(33.0)


# ---------------------------------------------------------------------------
# _first_score
# ---------------------------------------------------------------------------

def test_first_score_picks_first_non_none():
    seg = {"a": None, "b": 70.0, "c": 90.0}
    result = _first_score(seg, ["a", "b", "c"])
    assert result == pytest.approx(70.0)


def test_first_score_all_missing_returns_default():
    seg = {}
    result = _first_score(seg, ["x", "y", "z"], default=55.0)
    assert result == pytest.approx(55.0)


def test_first_score_empty_string_treated_as_missing():
    seg = {"a": "", "b": 60.0}
    result = _first_score(seg, ["a", "b"])
    assert result == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# _compute_output_ranking_entry — Sacred Contract #1
# ---------------------------------------------------------------------------

def test_compute_output_ranking_entry_contains_sacred_contract_keys():
    """Sacred Contract #1: output_rank_score, is_best_output, is_best_clip must always be present."""
    seg = {"viral_score": 70, "hook_score": 80}
    result = _compute_output_ranking_entry(1, seg, "/output/part1.mp4")
    assert "output_rank_score" in result
    assert "is_best_output" in result
    assert "is_best_clip" in result


def test_compute_output_ranking_entry_output_rank_score_is_0_to_100():
    seg = {"viral_score": 70, "hook_score": 80, "retention_score": 65}
    result = _compute_output_ranking_entry(1, seg, "/output/part1.mp4")
    score = result["output_rank_score"]
    assert isinstance(score, float)
    assert 0.0 <= score <= 100.0


def test_compute_output_ranking_entry_is_best_output_is_bool():
    seg = {"viral_score": 70}
    result = _compute_output_ranking_entry(1, seg, "/output/part1.mp4")
    assert isinstance(result["is_best_output"], bool)


def test_compute_output_ranking_entry_is_best_clip_is_bool():
    seg = {"viral_score": 70}
    result = _compute_output_ranking_entry(1, seg, "/output/part1.mp4")
    assert isinstance(result["is_best_clip"], bool)


def test_compute_output_ranking_entry_initial_best_flags_are_false():
    """Entry initialises is_best_output and is_best_clip to False (set by orchestrator later)."""
    seg = {"viral_score": 90, "hook_score": 95}
    result = _compute_output_ranking_entry(1, seg, "/output/part1.mp4")
    assert result["is_best_output"] is False
    assert result["is_best_clip"] is False


def test_compute_output_ranking_entry_empty_seg_uses_defaults():
    """Empty segment dict must not raise — defaults fill in all scores."""
    result = _compute_output_ranking_entry(3, {}, "/output/part3.mp4")
    assert result["ok"] if "ok" in result else True  # ok key not required
    assert "output_rank_score" in result
    assert 0.0 <= result["output_rank_score"] <= 100.0


# ---------------------------------------------------------------------------
# _resolve_rank_from_plan — rank wiring (P5)
# ---------------------------------------------------------------------------

from types import SimpleNamespace
from app.features.render.engine.pipeline.pipeline_ranking import _resolve_rank_from_plan


def _clip(rank: int) -> SimpleNamespace:
    return SimpleNamespace(rank=rank)


def _plan(clips: list) -> SimpleNamespace:
    return SimpleNamespace(clips=clips)


def test_rank_no_plan_returns_fallback():
    mapping, tag = _resolve_rank_from_plan(None, [{}], set())
    assert mapping is None
    assert tag == "fallback"


def test_rank_empty_clips_returns_fallback_no_plan_rank():
    mapping, tag = _resolve_rank_from_plan(_plan([]), [{}], set())
    assert mapping is None
    assert tag == "fallback_no_plan_rank"


def test_rank_zero_returns_fallback_no_plan_rank():
    # AI didn't emit rank — ClipPlan.rank defaults to 0
    mapping, tag = _resolve_rank_from_plan(_plan([_clip(0)]), [{}], set())
    assert mapping is None
    assert tag == "fallback_no_plan_rank"


def test_rank_valid_permutation_returns_mapping():
    # 3 clips, ranks [2, 1, 3] — valid permutation
    plan = _plan([_clip(2), _clip(1), _clip(3)])
    mapping, tag = _resolve_rank_from_plan(plan, [{}, {}, {}], set())
    assert tag == "render_plan"
    assert mapping == {1: 2, 2: 1, 3: 3}


def test_rank_collision_returns_fallback_collision():
    plan = _plan([_clip(1), _clip(1)])
    mapping, tag = _resolve_rank_from_plan(plan, [{}, {}], set())
    assert mapping is None
    assert tag == "fallback_rank_collision"


def test_rank_non_sequential_returns_fallback_invalid():
    # [1, 3] is not a valid 1..N permutation for N=2
    plan = _plan([_clip(1), _clip(3)])
    mapping, tag = _resolve_rank_from_plan(plan, [{}, {}], set())
    assert mapping is None
    assert tag == "fallback_rank_invalid"


def test_rank_flag_off_returns_fallback(monkeypatch):
    monkeypatch.setenv("LLM_EMIT_RENDER_PLAN", "0")
    plan = _plan([_clip(1)])
    mapping, tag = _resolve_rank_from_plan(plan, [{}], set())
    assert mapping is None
    assert tag == "fallback"
