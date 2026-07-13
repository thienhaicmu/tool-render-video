"""
Phase 3 (lean contract) — StoryPlan.derive_beat_styling().

The AI no longer emits the 9 mechanical per-beat style labels; they are derived
deterministically here. The rules must (a) keep the speaking-character overlay working
(char_anchor != 'none' for speakers — else no overlay is composited), (b) preserve
render variety (motion / transitions / bgm placement), and (c) be FILL-ONLY so a plan
that DID carry a value (P2 / legacy / approved override) is left untouched.
"""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual, Beat


def _plan(**kw):
    return StoryPlan(
        seed=7,
        characters=[CharacterDef(id="han"), CharacterDef(id="lan"), CharacterDef(id="vu")],
        settings=[SettingDef(id="s1")],
        visuals=[Visual(id="v1", setting_id="s1"), Visual(id="v2", setting_id="s1")],
        timeline=[
            Beat(id="b1", narration="a", speaker_id="", visual_id="v1"),      # narrator
            Beat(id="b2", narration="b", speaker_id="han", visual_id="v1"),
            Beat(id="b3", narration="c", speaker_id="lan", visual_id="v2"),
            Beat(id="b4", narration="d", speaker_id="vu", visual_id="v2"),
        ],
        **kw,
    )


def test_char_anchor_stable_per_character():
    p = _plan().derive_beat_styling()
    by = {b.id: b for b in p.timeline}
    assert by["b1"].char_anchor == "none"         # narrator → no overlay
    # first appearance order han, lan, vu → center, left, right
    assert by["b2"].char_anchor == "center"
    assert by["b3"].char_anchor == "left"
    assert by["b4"].char_anchor == "right"


def test_char_anchor_fill_only_preserves_explicit():
    p = _plan()
    p.timeline[1].char_anchor = "right"           # AI/legacy already set it
    p.derive_beat_styling()
    assert p.timeline[1].char_anchor == "right"   # untouched


def test_transition_fade_on_scene_change():
    p = _plan().derive_beat_styling()
    by = {b.id: b for b in p.timeline}
    assert by["b1"].transition_in == "fade"       # first beat = scene start
    assert by["b2"].transition_in == "cut"        # same visual v1
    assert by["b3"].transition_in == "fade"       # v1 → v2 change


def test_bgm_cue_intro_outro_per_scene():
    p = _plan().derive_beat_styling()
    by = {b.id: b for b in p.timeline}
    # scene v1 = b1,b2 → intro,outro ; scene v2 = b3,b4 → intro,outro
    assert by["b1"].bgm_cue == "intro" and by["b2"].bgm_cue == "outro"
    assert by["b3"].bgm_cue == "intro" and by["b4"].bgm_cue == "outro"


def test_bgm_intensity_from_mood_emotion():
    p = _plan()
    p.timeline[1].bgm_mood = "action"
    p.timeline[2].emotion = "sad"
    p.derive_beat_styling()
    assert p.timeline[1].bgm_intensity == "high"  # action mood
    assert p.timeline[2].bgm_intensity == "low"   # sad emotion


def test_motion_variety_but_fill_only():
    p = _plan()
    p.timeline[0].motion = "pan_left"             # explicit → preserved
    p.derive_beat_styling()
    assert p.timeline[0].motion == "pan_left"
    # the rest were default zoom_in → derived to non-default rotation values
    assert any(b.motion != "zoom_in" for b in p.timeline[1:])


def test_idempotent_and_never_raises():
    p = _plan().derive_beat_styling()
    snap = [(b.char_anchor, b.motion, b.transition_in, b.bgm_cue) for b in p.timeline]
    p.derive_beat_styling()                        # second pass = no change
    assert [(b.char_anchor, b.motion, b.transition_in, b.bgm_cue) for b in p.timeline] == snap
    # empty plan is safe
    assert StoryPlan().derive_beat_styling() is not None
