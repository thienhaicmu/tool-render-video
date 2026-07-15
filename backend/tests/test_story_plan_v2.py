"""Story Mode v2 — B1 domain: contract + RenderState + cue sheet + INVARIANTS."""
from __future__ import annotations

import json

from app.domain.story_plan_v2 import (
    StoryPlan, CharacterDef, SettingDef, Visual, Beat, BeatAudio, Word,
    RelationshipDef, Sequence, Scene, Shot, CharacterState,
    SCHEMA_VERSION, CROP_RECT,
)


def _plan() -> StoryPlan:
    return StoryPlan(
        seed=42, language="vi", art_style="wuxia", aspect_ratio="16:9",
        characters=[CharacterDef(id="han", name="Hàn Phong", canonical_desc="áo trắng", gender="male", voice_gender="male")],
        settings=[SettingDef(id="hall", name="Đại điện", canonical_desc="đá lạnh")],
        visuals=[
            Visual(id="v1", setting_id="hall", prompt="cold hall wide", character_ids=["han"], tier="low"),
            Visual(id="v2", setting_id="hall", prompt="close youth face", character_ids=["han"], tier="high"),
        ],
        timeline=[
            Beat(id="b1", narration="Đêm lạnh buông.", visual_id="v1", focus="left", motion="pan_left", speaker_id=""),
            Beat(id="b2", narration="Hàn Phong bước tới.", visual_id="v1", focus="center", speaker_id="han"),
            Beat(id="b3", narration="Ấn ký bạc phát sáng.", visual_id="v2", focus="close", motion="zoom_in",
                 transition_in="fade", hook=True, hook_text="ẤN KÝ THỨC TỈNH"),
        ],
    )


# ── serialisation ─────────────────────────────────────────────────────────────

def test_roundtrip_stable():
    p = _plan()
    # seed render state (dur) so cues survive round-trip.
    p.render.beat_audio = {"b1": BeatAudio("a1.mp3", 3.0, [Word("Đêm", 0.0, 0.5)]),
                           "b2": BeatAudio("a2.mp3", 2.0), "b3": BeatAudio("a3.mp3", 2.5)}
    p.build_cues()
    j1 = p.to_json()
    j2 = StoryPlan.from_json(j1).to_json()
    assert j1 == j2                       # deterministic round-trip (tuple↔list stable)


def test_phase05_library_hint_fields():
    """region/genre_key/archetype/scene_kind: roundtrip, enum-norm, old-blob defaults,
    and NO effect on the deterministic cue sheet (Phase 0.5 — Sacred #2 spirit)."""
    p = _plan()
    p.region = "cn"; p.genre_key = "wuxia"
    p.characters[0].archetype = "swordsman"
    p.settings[0].scene_kind = "throne_room"
    p.render.beat_audio = {"b1": BeatAudio("a1.mp3", 3.0), "b2": BeatAudio("a2.mp3", 2.0),
                           "b3": BeatAudio("a3.mp3", 2.5)}
    p.build_cues()
    r = StoryPlan.from_json(p.to_json())
    assert r.region == "cn" and r.genre_key == "wuxia"
    assert r.characters[0].archetype == "swordsman"
    assert r.settings[0].scene_kind == "throne_room"
    # cue sheet identical with vs without the hints (hints never touch render state)
    p2 = _plan()
    p2.render.beat_audio = dict(p.render.beat_audio); p2.build_cues()
    assert [(c.beat_id, c.start_sec, c.end_sec) for c in r.render.cues] == \
           [(c.beat_id, c.start_sec, c.end_sec) for c in p2.render.cues]
    # bad region value drops to "" ; old blob (no keys) defaults to ""
    bad = StoryPlan.from_json('{"schema_version":2,"region":"mars","characters":[{"id":"x","name":"X"}]}')
    assert bad.region == "" and bad.genre_key == ""
    assert bad.characters[0].archetype == "" and StoryPlan().settings == []


def test_cue_carries_beat_emotion():
    """N4 — build_cues copies beat.emotion onto the Cue (default 'normal'); roundtrips."""
    p = StoryPlan(seed=1, language="vi", visuals=[Visual(id="v1", prompt="x")],
                  characters=[CharacterDef(id="han", name="H")],
                  timeline=[Beat(id="b1", narration="a", visual_id="v1", speaker_id="han", emotion="angry", pose="point"),
                            Beat(id="b2", narration="b", visual_id="v1", speaker_id="han")])  # no emotion/pose
    p.render.beat_audio = {"b1": BeatAudio("a.mp3", 2.0), "b2": BeatAudio("b.mp3", 2.0)}
    p.build_cues()
    assert p.render.cues[0].emotion == "angry" and p.render.cues[1].emotion == "normal"
    assert p.render.cues[0].pose == "point" and p.render.cues[1].pose == "stand"
    r = StoryPlan.from_json(p.to_json())
    assert r.render.cues[0].emotion == "angry" and r.render.cues[0].pose == "point"


def test_from_json_none_and_garbage():
    assert StoryPlan.from_json(None) is None
    assert StoryPlan.from_json("") is None
    assert StoryPlan.from_json("nope{") is None
    assert StoryPlan.from_json("[1,2]") is None


def test_unknown_keys_dropped_defaults():
    p = StoryPlan.from_json(json.dumps({"bogus": 1, "timeline": [{"id": "b1", "narration": "hi", "visual_id": "v1"}],
                                        "visuals": [{"id": "v1", "prompt": "x"}]}))
    assert p is not None and p.schema_version == SCHEMA_VERSION
    assert p.beat_count() == 1


def test_scene_shot_grammar_is_derived_and_roundtrips():
    p = _plan()
    p.derive_scene_shot_grammar()
    assert p.sequences and p.scenes and len(p.shots) == p.beat_count()
    assert all(beat.shot_id for beat in p.timeline)
    assert p.scenes[0].shot_ids
    assert p.shots[0].shot_size == "wide"
    assert p.timeline[0].focus == "wide"
    restored = StoryPlan.from_json(p.to_json())
    assert restored is not None
    assert restored.shots[0].id == p.shots[0].id
    assert restored.timeline[0].shot_id == p.timeline[0].shot_id


def test_authored_shot_controls_render_focus_and_motion():
    p = _plan().derive_scene_shot_grammar()
    first = p.shot(p.timeline[0].shot_id)
    assert first is not None
    first.shot_size = "extreme_close"
    first.motion_intent = "pull_out"
    p.apply_shot_grammar()
    assert p.timeline[0].focus == "close"
    assert p.timeline[0].motion == "zoom_out"


def test_scene_shot_refs_and_relationships_are_validated():
    p = _plan().derive_scene_shot_grammar()
    p.relationships = [RelationshipDef("han", "missing", "enemy"),
                       RelationshipDef("han", "han", "self")]
    p.shots[0].angle = "impossible"
    p.character_states.append(CharacterState("missing", p.scenes[0].id))
    p.validate_refs()
    assert p.relationships == []
    assert p.shots[0].angle == "eye_level"
    assert all(state.character_id != "missing" for state in p.character_states)


# ── INVARIANTS ─────────────────────────────────────────────────────────────────

def test_validate_refs_enforces_integrity():
    p = StoryPlan(
        characters=[CharacterDef(id="han", name="H")],
        visuals=[Visual(id="v1", prompt="x", character_ids=["han", "ghost"], setting_id="nope", tier="ultra")],
        timeline=[
            Beat(id="b1", narration="ok", visual_id="v1", speaker_id="ghost", focus="banana", motion="fly", transition_in="warp"),
            Beat(id="b2", narration="dangling", visual_id="MISSING"),   # INV1 → drop
            Beat(id="b3", narration="", hold_sec=0.0, visual_id="v1"),  # INV8 → drop (no narration/hold)
        ],
    )
    p.validate_refs()
    assert [b.id for b in p.timeline] == ["b1"]                 # b2 (dangling) + b3 (empty) dropped
    b = p.timeline[0]
    assert b.speaker_id == ""                                  # INV2 ghost cleared
    assert b.focus == "center" and b.motion == "zoom_in" and b.transition_in == "cut"  # INV5
    v = p.visuals[0]
    assert v.character_ids == ["han"]                          # INV4 ghost filtered
    assert v.setting_id == "" and v.tier == "medium"           # INV3/INV5


def test_cap_visuals_keeps_referenced():
    p = StoryPlan(
        visuals=[Visual(id=f"v{i}", prompt="x") for i in range(5)],
        timeline=[Beat(id="b1", narration="a", visual_id="v3"), Beat(id="b2", narration="b", visual_id="v1")],
    )
    p.cap_visuals(2)
    assert p.image_count() == 2
    assert {v.id for v in p.visuals} == {"v3", "v1"}           # referenced kept
    assert all(b.visual_id in {"v3", "v1"} for b in p.timeline)


def test_reindex_seeds_ids():
    p = StoryPlan(visuals=[Visual(id="v1", prompt="x")],
                  timeline=[Beat(narration="a", visual_id="v1"), Beat(narration="b", visual_id="v1")])
    p.reindex()
    assert [b.id for b in p.timeline] == ["b1", "b2"]


# ── timing / cue sheet ─────────────────────────────────────────────────────────

def test_est_and_total_sec():
    p = _plan()
    assert p.beat_est_sec(p.timeline[0]) > 0
    assert p.estimated_total_sec() > 0


def test_build_cues_deterministic_and_invariants():
    p = _plan()
    p.render.beat_audio = {"b1": BeatAudio("a1", 3.0), "b2": BeatAudio("a2", 2.0), "b3": BeatAudio("a3", 2.5)}
    p.build_cues()
    cues = p.render.cues
    assert len(cues) == 3
    # INV14: start < end, chain contiguous-ish.
    assert all(c.start_sec < c.end_sec for c in cues)
    # INV13: same visual (b1→b2 both v1) → crop_from == prev crop_to.
    assert cues[1].crop_from == cues[0].crop_to
    # Visual change b2→b3 → its declared transition resolved.
    assert cues[2].transition == "fade" and cues[2].transition_sec > 0
    assert cues[0].transition == "cut"                        # first beat / cut
    # total_sec == last cue end.
    assert abs(p.render.total_sec - cues[-1].end_sec) < 1e-6
    # hook carried.
    assert cues[2].hook and cues[2].hook_text == "ẤN KÝ THỨC TỈNH"
    # Deterministic: rebuild → identical.
    j = p.to_json()
    p2 = StoryPlan.from_json(j)
    p2.render.cues = []
    p2.build_cues()
    assert [c.crop_to for c in p2.render.cues] == [c.crop_to for c in cues]


def test_random_transition_deterministic_by_seed():
    def mk(seed):
        pp = StoryPlan(seed=seed, visuals=[Visual(id="v1", prompt="x"), Visual(id="v2", prompt="y")],
                       timeline=[Beat(id="b1", narration="a", visual_id="v1"),
                                 Beat(id="b2", narration="b", visual_id="v2", transition_in="random")])
        pp.render.beat_audio = {"b1": BeatAudio("a", 2.0), "b2": BeatAudio("b", 2.0)}
        pp.build_cues(); return pp.render.cues[1].transition
    assert mk(7) == mk(7)                                       # same seed → same
    assert mk(7) in ("fade", "slide", "zoom", "flash")


def test_image_timeline_and_voice_runs():
    p = _plan()
    p.render.beat_audio = {"b1": BeatAudio("a1", 3.0), "b2": BeatAudio("a2", 2.0), "b3": BeatAudio("a3", 2.5)}
    p.build_cues()
    it = p.image_timeline()
    assert it[0][0] == "v1" and it[2][0] == "v2"
    # voice runs: b1(narrator "") | b2(han) | b3(narrator "")
    runs = p.voice_runs()
    assert [r[0] for r in runs] == ["", "han", ""]


def test_is_empty():
    assert StoryPlan().is_empty() is True
    assert _plan().is_empty() is False


def test_crop_rect_focus_regions():
    # left region is left-biased, right region right-biased (sanity of constants).
    assert CROP_RECT["left"][0] < CROP_RECT["right"][0]
    assert CROP_RECT["close"][2] < CROP_RECT["wide"][2]
