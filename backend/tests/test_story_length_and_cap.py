"""
Regression — "3-minute idea → 29s cụt ngủn" bug.

Two independent root causes, both fixed:
  1. cap_visuals used to DELETE beats whose visual was cut → an over-imaged plan
     (≈one image per beat) lost its whole back half when capped, collapsing a long
     story to a stub. It must now REMAP those beats to a kept visual (story intact).
  2. The idea-mode super-prompt said "Never pad" + a soft length target, so the model
     under-delivered. It must now make the target length a REQUIREMENT with a beat guide.
"""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, SettingDef, Visual, Beat
from app.features.render.ai.llm.story_prompts_v2 import build_super_idea_prompt


def test_cap_visuals_remaps_not_drops_beats():
    # Over-imaged: 12 beats, one distinct visual each (all in setting s1).
    plan = StoryPlan(
        settings=[SettingDef(id="s1", name="Place")],
        visuals=[Visual(id=f"v{i}", setting_id="s1", prompt="x") for i in range(1, 13)],
        timeline=[Beat(id=f"b{i}", narration=f"beat {i}", visual_id=f"v{i}") for i in range(1, 13)],
    )
    plan.cap_visuals(3)
    # Images capped …
    assert plan.image_count() == 3
    # … but EVERY beat survives (no truncation) and points at a kept visual.
    assert plan.beat_count() == 12
    kept = {v.id for v in plan.visuals}
    assert all(b.visual_id in kept for b in plan.timeline)


def test_cap_visuals_prefers_same_setting_on_remap():
    plan = StoryPlan(
        settings=[SettingDef(id="s1"), SettingDef(id="s2")],
        visuals=[
            Visual(id="v1", setting_id="s1", prompt="a"),
            Visual(id="v2", setting_id="s2", prompt="b"),
            Visual(id="v3", setting_id="s2", prompt="c"),   # will be cut → remap to s2's kept v2
        ],
        timeline=[
            Beat(id="b1", narration="1", visual_id="v1"),
            Beat(id="b2", narration="2", visual_id="v2"),
            Beat(id="b3", narration="3", visual_id="v3"),   # setting s2
        ],
    )
    plan.cap_visuals(2)
    b3 = next(b for b in plan.timeline if b.id == "b3")
    assert b3.visual_id == "v2"          # remapped to the kept visual in the SAME setting
    assert plan.beat_count() == 3


def test_cap_visuals_unchanged_when_under_ceiling():
    plan = StoryPlan(
        visuals=[Visual(id="v1", prompt="x"), Visual(id="v2", prompt="y")],
        timeline=[Beat(id="b1", narration="a", visual_id="v1"),
                  Beat(id="b2", narration="b", visual_id="v2")],
    )
    plan.cap_visuals(5)
    assert plan.image_count() == 2 and plan.beat_count() == 2


def test_idea_prompt_enforces_length_no_never_pad():
    _, user = build_super_idea_prompt("a lone knight", duration_sec=180, language="vi")
    low = user.lower()
    assert "never pad" not in low                     # the length-killer instruction is gone
    assert "requires" in low or "genuinely fill" in low
    # 180s × 15 cps = 2700 chars budgeted, and a beat-count guide appears.
    assert "2700 characters" in user
    assert "beats" in low
    # Reuse is quantified (decouples long timeline from a small image set).
    assert "beats per visual" in low or "far fewer" in low


def test_idea_prompt_no_duration_is_soft():
    _, user = build_super_idea_prompt("a lone knight", duration_sec=0, language="vi")
    assert "model decides" in user.lower()
