"""test_content_wave3.py — CU-7/8: provider registry + Decision Tree + budget.

Pure unit tests (no LLM / ffmpeg / network): the provider capability manifest and
the deterministic cost/budget routing.
"""
from __future__ import annotations

from app.domain.content_plan import ContentScene
from app.features.render.engine.visual.registry import get_manifest, is_online
from app.features.render.engine.visual.decision import BudgetTracker, decide_provider, estimate_cost


def _sc(**kw):
    return ContentScene(index=0, narration="n", **kw)


# ── CU-7 registry ────────────────────────────────────────────────────────────

def test_registry_cost_tiers_ordered():
    assert (get_manifest("ai_video").cost_tier
            > get_manifest("ai_image").cost_tier
            > get_manifest("stock").cost_tier
            > get_manifest("local").cost_tier)


def test_registry_online_flags_and_unknown_default():
    assert is_online("ai_image") and is_online("stock") and is_online("ai_video")
    assert not is_online("local")
    assert get_manifest("midjourney").name == "local"   # unknown → local
    assert get_manifest("ai_image").supports_reference is True


# ── CU-8 cost ordering ───────────────────────────────────────────────────────

def test_estimate_cost_ordering():
    assert estimate_cost("local") == 0.0
    assert estimate_cost("ai_video") > estimate_cost("ai_image") >= estimate_cost("stock") >= 0.0


# ── CU-8 decision tree ───────────────────────────────────────────────────────

def test_decision_scene_override_wins_local():
    assert decide_provider(_sc(visual_source="image", visual_path="/x.png"), "ai_image") == "local"


def test_decision_offline_provider_local():
    assert decide_provider(_sc(visual_prompt="a cat"), "local") == "local"


def test_decision_no_prompt_local():
    assert decide_provider(_sc(visual_prompt=""), "ai_image") == "local"


def test_decision_suggestion_downgrades_only():
    assert decide_provider(_sc(visual_prompt="x", asset_suggestion="upload"), "ai_image") == "local"
    assert decide_provider(_sc(visual_prompt="x", asset_suggestion="stock"), "ai_image") == "stock"
    # suggestion never UPGRADES: stock job provider stays stock even if scene says ai_video
    assert decide_provider(_sc(visual_prompt="x", asset_suggestion="ai_video"), "stock") == "stock"


def test_decision_short_scene_skips_veo():
    assert decide_provider(_sc(visual_prompt="x"), "ai_video", est_duration_sec=3) == "ai_image"
    assert decide_provider(_sc(visual_prompt="x"), "ai_video", est_duration_sec=12) == "ai_video"


def test_decision_budget_downgrades():
    # Cap fits exactly one Veo clip; the second scene must downgrade.
    cap = estimate_cost("ai_video") + 0.001
    b = BudgetTracker(cap=cap)
    assert decide_provider(_sc(visual_prompt="a"), "ai_video", b, 12) == "ai_video"
    p2 = decide_provider(_sc(visual_prompt="b"), "ai_video", b, 12)
    assert p2 in ("stock", "local")  # budget exhausted → cheaper source


def test_budget_unlimited_when_cap_zero():
    b = BudgetTracker(cap=0)
    for _ in range(10):
        assert decide_provider(_sc(visual_prompt="x"), "ai_video", b, 12) == "ai_video"
    assert b.would_exceed(999) is False
