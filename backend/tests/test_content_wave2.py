"""test_content_wave2.py — CU-4/5/6: multi-pass Director + Story Bible + consistency.

Runs fully offline: the Gemini call helper (_call_gemini_content) is mocked to
return canned JSON, so no SDK / network is needed. Covers the domain (v3 Bible +
scene characters/continuity), the bible parser, the deterministic validator (CU-5)
+ character-fragment injection (CU-6), and the 2-pass director orchestration incl.
its single-pass fallback.
"""
from __future__ import annotations

import json

from app.domain.content_plan import (
    BibleCharacter, ContentPlan, ContentScene, StoryBible,
)


# ── Domain (schema v3) ───────────────────────────────────────────────────────

def test_story_bible_and_scene_fields_roundtrip():
    plan = ContentPlan(
        story_bible=StoryBible(
            setting="1815 Europe", hook="A last gamble", cta="Subscribe",
            characters=[BibleCharacter(id="napoleon", name="Napoleon", description="short general, blue coat")],
        ),
        scenes=[ContentScene(index=0, narration="x", characters=["napoleon"], continuity="from prev")],
    )
    back = ContentPlan.from_json(plan.to_json())
    assert back is not None and back.schema_version == 3
    assert back.story_bible.setting == "1815 Europe"
    assert back.story_bible.character("napoleon").description == "short general, blue coat"
    assert back.scenes[0].characters == ["napoleon"]
    assert back.scenes[0].continuity == "from prev"


def test_v2_blob_loads_without_bible():
    plan = ContentPlan.from_json(json.dumps({"topic": "x", "scenes": [{"index": 0, "narration": "n"}]}))
    assert plan is not None
    assert plan.story_bible.is_empty()
    assert plan.scenes[0].characters == []


# ── Pass-A bible parser ──────────────────────────────────────────────────────

def test_parse_story_bible_response():
    from app.features.render.ai.llm.content_parser import parse_story_bible_response
    r = parse_story_bible_response(json.dumps({
        "topic": "Mars", "tone": "documentary", "audience": "general", "video_style": "explainer",
        "setting": "the red planet",
        "characters": [{"id": "rover", "name": "Rover", "description": "a six-wheeled robot"}],
    }))
    assert r is not None
    bible, meta = r
    assert meta["topic"] == "Mars" and meta["video_style"] == "explainer"
    assert bible.character("rover").description == "a six-wheeled robot"
    assert parse_story_bible_response("not json") is None


# ── CU-5 validator + CU-6 injection (deterministic) ──────────────────────────

def test_validate_and_repair_filters_and_reindexes():
    from app.features.render.ai.llm.content_quality import validate_and_repair
    bible = StoryBible(characters=[BibleCharacter(id="a", name="A", description="d")])
    plan = ContentPlan(scenes=[
        ContentScene(index=0, narration="one", characters=["a", "ghost"]),
        ContentScene(index=1, narration=""),      # dropped (empty)
        ContentScene(index=2, narration="two", characters=["A"]),
    ])
    validate_and_repair(plan, bible)
    assert [s.index for s in plan.scenes] == [0, 1]          # reindexed densely
    assert plan.scenes[0].characters == ["a"]                # unknown "ghost" filtered
    assert plan.scenes[1].characters == ["A"]                # name match kept
    assert len(plan.scenes) == 2                             # empty-narration scene dropped


def test_inject_character_fragments_idempotent():
    from app.features.render.ai.llm.content_quality import inject_character_fragments
    bible = StoryBible(characters=[BibleCharacter(id="a", name="A", description="a tall wizard in red")])
    plan = ContentPlan(scenes=[
        ContentScene(index=0, narration="x", characters=["a"], visual_prompt="a dark forest"),
        ContentScene(index=1, narration="y", characters=["a"]),  # no base prompt
        ContentScene(index=2, narration="z", characters=[]),     # no character → untouched
    ])
    inject_character_fragments(plan, bible)
    assert plan.scenes[0].visual_prompt == "a dark forest. a tall wizard in red"
    assert plan.scenes[1].visual_prompt == "a tall wizard in red"
    assert plan.scenes[2].visual_prompt == ""
    # idempotent — running again does not duplicate the fragment
    inject_character_fragments(plan, bible)
    assert plan.scenes[0].visual_prompt == "a dark forest. a tall wizard in red"


# ── Director orchestration (2-pass, mocked LLM) ──────────────────────────────

_BIBLE = json.dumps({
    "topic": "Napoleon", "tone": "documentary", "audience": "general", "video_style": "documentary",
    "setting": "1815 Europe", "hook": "A last gamble", "cta": "Subscribe",
    "characters": [{"id": "napoleon", "name": "Napoleon", "description": "a 45yo general in a blue coat"}],
})
_PLAN = json.dumps({
    "scenes": [
        {"index": 0, "role": "hook", "narration": "Napoleon marches to Waterloo.",
         "characters": ["napoleon"], "visual_prompt": "a battlefield at dawn"},
        {"index": 1, "role": "conclusion", "narration": "And there he fell.",
         "characters": ["napoleon"]},
    ],
})


def _mock_call(monkeypatch, bible_out=_BIBLE, plan_out=_PLAN):
    import app.features.render.ai.llm.providers.gemini as gem
    monkeypatch.setattr(gem, "_GENAI_SDK", True)

    def _fake(api_key, model, system, user):
        return bible_out if "STORY EDITOR" in system else plan_out
    monkeypatch.setattr(gem, "_call_gemini_content", _fake)
    return gem


def test_director_two_pass_grounds_and_injects(monkeypatch):
    gem = _mock_call(monkeypatch)
    monkeypatch.setattr(gem, "_CONTENT_MULTIPASS", True)
    # P2.1 gates Pass A by script length; this test exercises the two-pass
    # grounding MECHANISM, so disable the length gate (threshold 0 = always on).
    monkeypatch.setattr(gem, "_CONTENT_MULTIPASS_MIN_CHARS", 0)
    plan = gem.select_content_plan(script="Napoleon lost at Waterloo", api_key="k")
    assert plan is not None
    assert len(plan.story_bible.characters) == 1                  # bible stamped
    assert plan.topic == "Napoleon" and plan.video_style == "documentary"  # meta stamped
    # CU-6: the canonical character description is injected into every scene.
    assert "blue coat" in plan.scenes[0].visual_prompt
    assert "blue coat" in plan.scenes[1].visual_prompt           # scene w/o base prompt


def test_director_falls_back_when_bible_pass_fails(monkeypatch):
    gem = _mock_call(monkeypatch, bible_out=None)  # bible pass returns nothing
    monkeypatch.setattr(gem, "_CONTENT_MULTIPASS", True)
    plan = gem.select_content_plan(script="x", api_key="k")
    assert plan is not None and plan.scene_count() == 2
    assert plan.story_bible.is_empty()  # no bible → ungrounded single-pass result


def test_director_single_pass_when_flag_off(monkeypatch):
    import app.features.render.ai.llm.providers.gemini as gem
    monkeypatch.setattr(gem, "_GENAI_SDK", True)
    monkeypatch.setattr(gem, "_CONTENT_MULTIPASS", False)
    calls = {"bible": 0}

    def _fake(api_key, model, system, user):
        if "STORY EDITOR" in system:
            calls["bible"] += 1
        return _PLAN
    monkeypatch.setattr(gem, "_call_gemini_content", _fake)
    plan = gem.select_content_plan(script="x", api_key="k")
    assert plan is not None and calls["bible"] == 0  # no Pass-A call when flag off
