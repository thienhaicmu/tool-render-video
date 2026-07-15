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
    assert SUPER_PROMPT_VERSION == "s25"  # GĐ1 Story Compiler (mood vocab unchanged)
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


# ── s4: placed BGM (bgm_cue windows + intensity gain) ─────────────────────────

def _cued_plan(cues):
    """Build a 3-beat plan then override each cue's (bgm_cue, bgm_intensity)."""
    p = _plan()
    for c, (cue, inten) in zip(p.render.cues, cues):
        c.bgm_cue, c.bgm_intensity = cue, inten
    return p


def test_bgm_cues_under_merges_same_mood():
    # b1+b2 tense/under adjacent → merged into one window; b3 hopeful separate.
    p = _cued_plan([("under", "med"), ("under", "med"), ("under", "high")])
    segs = p.bgm_cues()
    assert len(segs) == 2
    assert segs[0][0] == "tense" and segs[0][3] == -18.0     # med gain
    assert segs[1][0] == "hopeful" and segs[1][3] == -12.0   # high gain
    # merged window spans b1.start .. b2.end
    assert segs[0][1] == p.render.cues[0].start_sec and segs[0][2] == p.render.cues[1].end_sec


def test_bgm_cue_intro_outro_windows():
    from app.domain.story_plan_v2 import BGM_EDGE_SEC
    p = _cued_plan([("intro", "low"), ("none", "med"), ("outro", "med")])
    segs = p.bgm_cues()
    # b2 none → skipped
    assert [s[0] for s in segs] == ["tense", "hopeful"]
    c1, c3 = p.render.cues[0], p.render.cues[2]
    intro = segs[0]; outro = segs[1]
    assert intro[3] == -24.0                                   # low gain
    assert abs(intro[2] - (max(0.0, c1.start_sec) + BGM_EDGE_SEC)) < 0.01   # intro window length
    assert abs(outro[1] - (c3.end_sec - BGM_EDGE_SEC)) < 0.01              # outro starts near end


def test_placed_bgm_track_none_without_music(tmp_path):
    from app.features.render.engine.audio.mixer import build_placed_bgm_track
    # pick_fn returns None → no music resolved → None (no ffmpeg call).
    out = build_placed_bgm_track([("tense", 0.0, 3.0, -18.0)], 5.0,
                                 str(tmp_path / "t.wav"), pick_fn=lambda m: None)
    assert out is None


def test_placed_bgm_track_empty_placements(tmp_path):
    from app.features.render.engine.audio.mixer import build_placed_bgm_track
    assert build_placed_bgm_track([], 5.0, str(tmp_path / "t.wav")) is None


def test_story_bgm_no_double_gain_and_gentle_duck(tmp_path, monkeypatch):
    # Fix: the placed track already carries each scene's gain; the story mix must NOT
    # attenuate a SECOND time (bgm_db_gain=0), and it ducks GENTLY so the music is
    # audible under near-continuous narration (ratio 2.5, not the default 6).
    from pathlib import Path
    from app.features.render.engine.audio import mixer
    from app.features.render.engine.stages.story import bgm_stage
    from app.domain.story_plan_v2 import StoryPlan, Cue
    p = StoryPlan()
    p.render.total_sec = 6.0
    p.render.cues = [Cue(beat_id="b1", visual_id="v1", start_sec=0.0, end_sec=6.0,
                         bgm_mood="tense", bgm_cue="under", bgm_intensity="med")]
    cap = {}
    monkeypatch.setattr(mixer, "build_placed_bgm_track", lambda *a, **k: str(tmp_path / "track.wav"))

    def _fake_mix(**kw):
        cap.update(kw)
        Path(kw["output_path"]).write_bytes(b"x")
        return kw["output_path"]
    monkeypatch.setattr(mixer, "mix_with_bgm", _fake_mix)
    monkeypatch.setattr(bgm_stage, "_emit_render_event", lambda **k: None)
    monkeypatch.setattr(bgm_stage, "_job_log", lambda *a, **k: None)
    final = tmp_path / "out.mp4"
    final.write_bytes(b"video")
    bgm_stage._mix_scene_bgm("job", "chan", p, str(final), tmp_path)
    assert cap.get("bgm_db_gain") == 0.0             # no second attenuation
    assert "ratio=2.5" in (cap.get("duck_params") or "")   # gentle duck
