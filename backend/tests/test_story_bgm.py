"""Story Mode v2 — per-beat background music (Q1 + Phase 1 s3).

Covers: Beat.bgm_mood (de)serialise + coercion, StoryPlan.bgm_scenes() grouping by
mood-run, mixer.build_scene_bgm_track None-paths (no ffmpeg needed), and the
super-prompt carrying the bgm_mood field/vocab on the TIMELINE.
"""
from __future__ import annotations

import json

from app.domain.story_plan_v2 import (
    StoryPlan, CharacterDef, SettingDef, Visual, Beat, BeatAudio, BGM_MOODS,
)


def _plan() -> StoryPlan:
    p = StoryPlan(
        seed=7, language="vi", aspect_ratio="16:9",
        visuals=[
            Visual(id="v1", prompt="cold hall wide"),
            Visual(id="v2", prompt="sunrise field"),
        ],
        timeline=[
            Beat(id="b1", narration="Đêm lạnh buông.", visual_id="v1", bgm_mood="tense"),
            Beat(id="b2", narration="Hàn Phong bước tới.", visual_id="v1", bgm_mood="tense"),
            Beat(id="b3", narration="Bình minh lên.", visual_id="v2", bgm_mood="hopeful"),
        ],
    )
    p.render.beat_audio = {"b1": BeatAudio("a1.mp3", 3.0), "b2": BeatAudio("a2.mp3", 2.0),
                           "b3": BeatAudio("a3.mp3", 2.5)}
    p.build_cues()
    return p


# ── domain: bgm_mood field (per beat) ─────────────────────────────────────────

def test_beat_bgm_mood_roundtrip():
    p = _plan()
    p2 = StoryPlan.from_json(p.to_json())
    assert p2 is not None
    moods = {b.id: b.bgm_mood for b in p2.timeline}
    assert moods["b1"] == "tense" and moods["b3"] == "hopeful"


def test_beat_bgm_mood_unknown_coerced_empty():
    p = StoryPlan.from_json(json.dumps({
        "timeline": [{"id": "b1", "narration": "hi", "visual_id": "v1", "bgm_mood": "banana"}],
        "visuals": [{"id": "v1", "prompt": "x"}],
    }))
    assert p is not None
    assert p.timeline[0].bgm_mood == ""   # unknown → "" (falls back to default folder)


# ── domain: bgm_scenes() grouping by mood-run ─────────────────────────────────

def test_bgm_scenes_group_consecutive_same_mood():
    scenes = _plan().bgm_scenes()
    # b1+b2 share mood tense → ONE scene; b3 hopeful → second. Two scenes total.
    assert len(scenes) == 2
    assert scenes[0][0] == "tense"
    assert scenes[1][0] == "hopeful"
    assert scenes[0][1] >= 0.0                 # start clamped >= 0
    assert scenes[0][2] <= scenes[1][2]
    assert scenes[1][2] > scenes[1][1]


def test_bgm_scenes_splits_same_visual_on_mood_change():
    # per-BEAT mood: two beats on the SAME visual but different moods → TWO scenes.
    p = StoryPlan(
        seed=1, language="vi", visuals=[Visual(id="v1", prompt="x")],
        timeline=[Beat(id="b1", narration="a", visual_id="v1", bgm_mood="tense"),
                  Beat(id="b2", narration="b", visual_id="v1", bgm_mood="calm")],
    )
    p.render.beat_audio = {"b1": BeatAudio("a.mp3", 2.0), "b2": BeatAudio("b.mp3", 2.0)}
    p.build_cues()
    scenes = p.bgm_scenes()
    assert len(scenes) == 2
    assert scenes[0][0] == "tense" and scenes[1][0] == "calm"


def test_bgm_scenes_empty_when_no_cues():
    p = StoryPlan(visuals=[Visual(id="v1", prompt="x")])
    assert p.bgm_scenes() == []


def test_bgm_scenes_missing_mood_is_empty_string():
    p = StoryPlan(
        visuals=[Visual(id="v1", prompt="x")],
        timeline=[Beat(id="b1", narration="hi", visual_id="v1")],  # no bgm_mood
    )
    p.render.beat_audio = {"b1": BeatAudio("a.mp3", 2.0)}
    p.build_cues()
    scenes = p.bgm_scenes()
    assert len(scenes) == 1 and scenes[0][0] == ""


# ── mixer: build_scene_bgm_track None-paths (no ffmpeg) ───────────────────────

def test_build_scene_bgm_track_none_when_no_music():
    from app.features.render.engine.audio.mixer import build_scene_bgm_track
    # pick_fn always None → no mood has a file → None BEFORE any ffmpeg call.
    out = build_scene_bgm_track([("tense", 0.0, 5.0), ("hopeful", 5.0, 8.0)],
                                8.0, "unused.wav", pick_fn=lambda m: None)
    assert out is None


def test_build_scene_bgm_track_none_when_empty():
    from app.features.render.engine.audio.mixer import build_scene_bgm_track
    assert build_scene_bgm_track([], 0.0, "unused.wav", pick_fn=lambda m: "/x") is None


# ── prompt: bgm_mood carried into the super-prompt (on the timeline) ──────────

def test_super_prompt_carries_bgm_mood_vocab():
    from app.features.render.ai.llm.story_prompts_v2 import (
        build_super_story_prompt, build_super_idea_prompt, SUPER_PROMPT_VERSION, _MOOD_VOCAB,
    )
    assert SUPER_PROMPT_VERSION == "s3"
    assert "default" not in _MOOD_VOCAB.split("|")   # "default" is a fallback folder, not a choice
    _, user = build_super_story_prompt("once upon a time", "vi")
    assert "bgm_mood" in user
    assert "<MOOD_VOCAB>" not in user            # placeholder was substituted
    for mood in ("tense", "hopeful", "romantic"):
        assert mood in user
    _, user2 = build_super_idea_prompt("a hero rises", 60, "", "vi")
    assert "bgm_mood" in user2 and "<MOOD_VOCAB>" not in user2


def test_bgm_moods_constant_shape():
    assert "default" in BGM_MOODS
    assert "tense" in BGM_MOODS and "epic" in BGM_MOODS
