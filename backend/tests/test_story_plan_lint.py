"""
P3 — Story plan semantic lint (non-mutating) + F-12 dead-field removal.

  * lint_story_plan surfaces soft quality signals (orphan visuals, generic-look
    speakers, unused cast, looping narration) WITHOUT mutating the plan.
  * The super-prompt schema no longer advertises negative_prompt (SVG render
    ignores it — F-12), but the Visual dataclass field still exists so stored
    plans deserialize unchanged (Sacred #2).
"""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual, Beat
from app.features.render.ai.llm.story_director_v2 import lint_story_plan
from app.features.render.ai.llm.story_prompts_v2 import build_super_story_prompt


def _plan() -> StoryPlan:
    return StoryPlan(
        language="vi",
        characters=[
            CharacterDef(id="hero", name="Hero", canonical_desc="a young swordsman"),
            CharacterDef(id="ghost", name="Ghost", canonical_desc=""),   # speaks, no look
            CharacterDef(id="extra", name="Extra", canonical_desc="unused"),  # never used
        ],
        settings=[SettingDef(id="s1", name="Forest")],
        visuals=[
            Visual(id="v1", setting_id="s1", prompt="wide forest", character_ids=["hero"]),
            Visual(id="v2", setting_id="s1", prompt="orphan scene"),   # no beat uses it
        ],
        timeline=[
            Beat(id="b1", narration="Mở đầu.", speaker_id="hero", visual_id="v1"),
            Beat(id="b2", narration="Lặp.", speaker_id="ghost", visual_id="v1"),
            Beat(id="b3", narration="Lặp.", speaker_id="ghost", visual_id="v1"),
            Beat(id="b4", narration="Lặp.", speaker_id="ghost", visual_id="v1"),
        ],
    )


def test_lint_flags_soft_issues():
    p = _plan()
    before = p.to_json()
    warnings = lint_story_plan(p)
    joined = " | ".join(warnings)
    assert "ghost" in joined and "canonical_desc" in joined      # generic-look speaker
    assert "v2" in joined                                        # orphan visual
    assert "extra" in joined                                     # unused cast
    assert "repeated" in joined                                  # looping narration
    # Non-mutating: the plan is untouched.
    assert p.to_json() == before


def test_lint_clean_plan_no_warnings():
    p = StoryPlan(
        language="vi",
        characters=[CharacterDef(id="hero", name="Hero", canonical_desc="a hero")],
        visuals=[Visual(id="v1", setting_id="", prompt="scene", character_ids=["hero"])],
        timeline=[Beat(id="b1", narration="Một câu.", speaker_id="hero", visual_id="v1")],
    )
    assert lint_story_plan(p) == []


def test_lint_never_raises_on_junk():
    assert lint_story_plan(None) == []
    assert lint_story_plan(object()) == []


def test_super_prompt_drops_negative_prompt():
    _, user = build_super_story_prompt("once upon a time", "vi")
    assert "negative_prompt" not in user
    # The dataclass field still exists (backward-compat for stored plans).
    assert hasattr(Visual(), "negative_prompt")
