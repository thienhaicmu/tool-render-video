"""Story Mode v2 — B3 super director (fake call_fn, no network)."""
from __future__ import annotations

import json

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, Visual
from app.features.render.ai.llm.story_director_v2 import (
    run_super_plan, inject_character_canon,
)


def _super_json(nvis=2, nbeat=2) -> str:
    return json.dumps({
        "topic": "tiên hiệp", "language": "vi", "art_style": "wuxia",
        "characters": [{"id": "han", "name": "Hàn Phong", "canonical_desc": "áo trắng, tóc bạc", "voice_gender": "male"}],
        "settings": [{"id": "s1", "name": "Đại điện", "canonical_desc": "đá lạnh"}],
        "visuals": [{"id": f"v{i}", "setting_id": "s1", "prompt": f"cold hall scene {i}",
                     "character_ids": ["han"], "tier": "medium"} for i in range(1, nvis + 1)],
        "timeline": [{"id": f"b{i}", "narration": f"đoạn {i}", "visual_id": "v1", "focus": "center"}
                     for i in range(1, nbeat + 1)],
    })


_CHAPTER = "Chương 1. " + ("Hàn Phong bước đi trong đêm. " * 20)


def test_mode_a_paste_builds_plan():
    seen = {}
    def fake(system, user):
        seen["mode"] = "idea" if "DRAMATIZE" in user else "story"   # s21 idea marker (was "create FROM this")
        return _super_json()
    p = run_super_plan(call_fn=fake, source="paste", chapter=_CHAPTER, language="vi",
                       art_style="wuxia", series_id="s", chapter_no=5)
    assert isinstance(p, StoryPlan) and seen["mode"] == "story"
    assert p.image_count() == 2 and p.beat_count() == 2
    assert p.series_id == "s" and p.chapter_no == 5 and p.seed != 0


def test_mode_b_idea_uses_idea_builder():
    seen = {}
    def fake(system, user):
        seen["mode"] = "idea" if "DRAMATIZE" in user else "story"   # s21 idea marker (was "create FROM this")
        return _super_json()
    p = run_super_plan(call_fn=fake, source="idea", idea="A fallen disciple rises.",
                       duration_sec=120, genre="wuxia", language="vi")
    assert p is not None and seen["mode"] == "idea"


def test_canon_not_injected_into_visual_prompt():
    # P-A (s11): Story is SVG-only → run_super_plan no longer appends canonical_desc
    # to visual.prompt (that was an image-gen concern). Character continuity lives in
    # canonical_desc via series memory, not the visual prompt.
    p = run_super_plan(call_fn=lambda s, u: _super_json(), source="paste", chapter=_CHAPTER)
    assert "áo trắng" not in (p.visual("v1").prompt or "")


def test_none_and_empty():
    assert run_super_plan(call_fn=lambda s, u: None, source="paste", chapter=_CHAPTER) is None
    assert run_super_plan(call_fn=lambda s, u: _super_json(), source="paste", chapter="  ") is None
    assert run_super_plan(call_fn=lambda s, u: _super_json(), source="idea", idea="") is None


def test_repair_pass_recovers(monkeypatch):
    monkeypatch.setenv("STORY_PLAN_REPAIR", "1")
    def fake(system, user):
        return _super_json() if "Fix this into" in user else "garbage not json {"
    p = run_super_plan(call_fn=fake, source="paste", chapter=_CHAPTER)
    assert p is not None and p.beat_count() == 2


def test_long_chapter_chunk_merge(monkeypatch):
    monkeypatch.setenv("STORY_MAX_CHAPTER_CHARS_SINGLE", "100")  # force chunk
    calls = {"n": 0}
    def fake(system, user):
        calls["n"] += 1
        return _super_json(nvis=2, nbeat=2)
    long_ch = "Đoạn A.\n\n" + ("x" * 200) + "\n\nĐoạn B.\n\n" + ("y" * 200)
    p = run_super_plan(call_fn=fake, source="paste", chapter=long_ch, language="vi")
    assert p is not None
    assert calls["n"] >= 2                      # two super calls (one per half)
    assert p.beat_count() >= 3                  # merged beats from both halves


def test_call_raising_swallowed():
    def boom(system, user):
        raise RuntimeError("provider down")
    assert run_super_plan(call_fn=boom, source="paste", chapter=_CHAPTER) is None


def test_inject_noop_without_characters():
    p = StoryPlan(visuals=[Visual(id="v1", prompt="scene")])
    inject_character_canon(p)
    assert p.visual("v1").prompt == "scene"


def test_dispatch_v2_no_key_returns_none():
    from app.features.render.ai.llm import generate_story_plan_v2
    assert generate_story_plan_v2(source="paste", chapter=_CHAPTER, api_key="") is None
