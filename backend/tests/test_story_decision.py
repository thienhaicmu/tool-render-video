"""Story-to-Video P3 — per-shot asset decision + budget guard tests (pure)."""
from __future__ import annotations

from app.domain.story_plan import Shot
from app.features.render.engine.visual.story_decision import (
    decide_shot_asset, tier_cost, BudgetTracker,
)


def test_tier_from_shot_no_budget():
    assert decide_shot_asset(Shot(index=0, visual_prompt="x", quality_tier="low")) == ("ai_image", "low")
    assert decide_shot_asset(Shot(index=0, visual_prompt="x", quality_tier="high")) == ("ai_image", "high")


def test_no_prompt_falls_back_local():
    assert decide_shot_asset(Shot(index=0, visual_prompt="", quality_tier="high"))[0] == "local"


def test_explicit_overrides():
    assert decide_shot_asset(Shot(index=0, visual_prompt="x", asset_type="local"))[0] == "local"
    assert decide_shot_asset(Shot(index=0, visual_prompt="x", asset_type="pin"))[0] == "pin"
    assert decide_shot_asset(Shot(index=0, visual_prompt="x", visual_source="color"))[0] == "local"


def test_budget_downgrades_tier():
    # cap fits medium (0.042) but not high (0.167) → downgrade high→medium.
    budget = BudgetTracker(cap=0.05)
    atype, tier = decide_shot_asset(Shot(index=0, visual_prompt="x", quality_tier="high"), budget)
    assert atype == "ai_image" and tier == "medium"
    assert abs(budget.spent - tier_cost("medium")) < 1e-9


def test_budget_exhausted_falls_back_local():
    budget = BudgetTracker(cap=0.005)  # below even low (0.011)
    atype, _ = decide_shot_asset(Shot(index=0, visual_prompt="x", quality_tier="high"), budget)
    assert atype == "local"


def test_budget_accumulates_across_shots():
    budget = BudgetTracker(cap=0.06)
    decide_shot_asset(Shot(index=0, visual_prompt="x", quality_tier="medium"), budget)  # spent 0.042
    # Second medium would exceed 0.06 (0.084); low (0.042+0.011=0.053) still fits → low.
    _, tier = decide_shot_asset(Shot(index=1, visual_prompt="x", quality_tier="medium"), budget)
    assert tier == "low"


def test_budget_second_shot_falls_local_when_no_tier_fits():
    budget = BudgetTracker(cap=0.05)
    decide_shot_asset(Shot(index=0, visual_prompt="x", quality_tier="medium"), budget)  # spent 0.042
    # Remaining 0.008 < low (0.011) → no tier fits → local.
    atype, _ = decide_shot_asset(Shot(index=1, visual_prompt="x", quality_tier="medium"), budget)
    assert atype == "local"
