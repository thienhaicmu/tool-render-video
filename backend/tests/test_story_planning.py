"""Story-to-Video P2 — storyboard parser + planning (map) + canon injection.

Uses a fake call_fn (no network). Covers parse_storyboard_response,
run_story_planning (scene→shot build + reindex + tier/transition defaults) and
inject_character_canon (visual consistency, idempotent)."""
from __future__ import annotations

import json

from app.domain.story_plan import StoryPlan, StoryScene, Shot, StoryBible, StoryCharacter
from app.features.render.ai.llm.story_parser import parse_storyboard_response
from app.features.render.ai.llm.story_director import (
    run_story_planning, inject_character_canon,
)

_CHAPTER = "\n\n".join(f"Đoạn {i}. " + ("Hàn Phong bước đi trong đêm. " * 15) for i in range(6))

_STORYBOARD = json.dumps({
    "scenes": [{
        "scene_title": "Mở đầu", "role": "hook", "emotion": "suspense",
        "characters": ["han_phong"],
        "shots": [
            {"shot_type": "establishing", "narration": "Đêm lạnh buông.",
             "camera": "zoom_in", "characters": ["han_phong"], "visual_prompt": "cold moonlit peak"},
            {"shot_type": "close_up", "narration": "Hàn Phong mở mắt.", "speaker": "han_phong",
             "characters": ["han_phong"], "visual_prompt": "close up of a youth's eyes"},
            {"shot_type": "insert", "narration": "", "visual_prompt": "a sword"},  # dropped (no narration)
        ],
    }],
})

_BIBLE = StoryBible(characters=[
    StoryCharacter(id="han_phong", name="Hàn Phong", description="áo trắng, tóc bạc, kiếm bạc"),
])


# ── parser ────────────────────────────────────────────────────────────────────

def test_parse_storyboard_valid():
    scenes = parse_storyboard_response(_STORYBOARD)
    assert scenes is not None and len(scenes) == 1
    # Shot without narration is filtered → 2 shots.
    assert len(scenes[0].shots) == 2
    assert scenes[0].shots[0].shot_type == "establishing"


def test_parse_storyboard_garbage_returns_none():
    assert parse_storyboard_response(None) is None
    assert parse_storyboard_response("nope") is None
    assert parse_storyboard_response(json.dumps({"scenes": []})) is None
    # Scenes present but no narrated shot → None.
    assert parse_storyboard_response(json.dumps({"scenes": [{"shots": [{"narration": ""}]}]})) is None


# ── planning (map) ─────────────────────────────────────────────────────────────

def test_run_story_planning_builds_plan_with_shots():
    out = run_story_planning(call_fn=lambda s, u: _STORYBOARD, chapter_text=_CHAPTER,
                             bible=_BIBLE, language="vi", art_style="wuxia", provider_label="test")
    assert isinstance(out, StoryPlan)
    # One scene per chunk (single storyboard reused for each chunk) → >=1 scene.
    assert out.scene_count() >= 1
    assert out.shot_count() >= 2
    first = out.all_shots()[0]
    assert first.sid  # seeded by reindex
    assert first.quality_tier == "low"          # establishing → low (domain default)
    # Character canon injected into the shot's visual_prompt.
    assert "áo trắng" in first.visual_prompt
    # 2-tier transition defaults.
    assert out.scenes[0].transition_out == "fade"
    assert first.transition_out == "cut"


def test_run_story_planning_none_cases():
    assert run_story_planning(call_fn=lambda s, u: None, chapter_text=_CHAPTER, bible=_BIBLE) is None
    assert run_story_planning(call_fn=lambda s, u: _STORYBOARD, chapter_text="  ", bible=_BIBLE) is None


def test_run_story_planning_carries_plan_metadata():
    out = run_story_planning(call_fn=lambda s, u: _STORYBOARD, chapter_text=_CHAPTER,
                             bible=_BIBLE, language="ja", art_style="anime",
                             series_id="s1", chapter_no=5, reading_pace="fast")
    assert out.language == "ja" and out.art_style == "anime"
    assert out.series_id == "s1" and out.chapter_no == 5 and out.reading_pace == "fast"


# ── canon injection ────────────────────────────────────────────────────────────

def test_inject_character_canon_idempotent():
    plan = StoryPlan(scenes=[StoryScene(shots=[
        Shot(index=0, narration="x", characters=["han_phong"], visual_prompt="a youth"),
    ])])
    inject_character_canon(plan, _BIBLE)
    once = plan.all_shots()[0].visual_prompt
    assert "áo trắng" in once
    inject_character_canon(plan, _BIBLE)  # again — must not double-append
    assert plan.all_shots()[0].visual_prompt == once


def test_inject_noop_without_characters():
    plan = StoryPlan(scenes=[StoryScene(shots=[Shot(index=0, narration="x", visual_prompt="scene")])])
    inject_character_canon(plan, _BIBLE)
    assert plan.all_shots()[0].visual_prompt == "scene"
