"""
GĐ4 — composition engine (4a) + readiness validator (4b) + targeted reuse (4c).

Pins: layout slots (facing flip + portrait reflow), anchor slots, hook safe-corner
choice, readiness pass/warn/fail matrix (content/continuity/identity/duration/
storage), TTS beat-audio reuse on resume, and cue-clip reuse gating (resume-only).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.domain.story_plan_v2 import (
    Beat, BeatAudio, CharacterDef, SettingDef, StoryPlan, Visual,
)
from app.features.render.engine.pipeline.story_readiness import (
    FAIL, PASS, WARN, evaluate_readiness, gate_enabled,
)
from app.features.render.engine.visual.composition import (
    anchor_slot, choose_hook_anchor, layout_slots, overlay_scale_mult,
)


# ── 4a composition ────────────────────────────────────────────────────────────

def test_layout_slots_two_chars_face_each_other():
    slots = layout_slots(2, 1536, 1024)
    assert slots[0][2] is False and slots[1][2] is True          # right one mirrored
    assert slots[0][0] < 0.5 < slots[1][0]


def test_layout_portrait_reflow_shrinks_and_tightens():
    land = layout_slots(2, 1536, 1024)
    port = layout_slots(2, 1024, 1536)
    assert port[0][1] < land[0][1]                               # smaller figures
    assert port[0][0] < land[0][0]                               # pushed outward less crowding centre
    assert overlay_scale_mult(1024, 1536) < 1.0 == overlay_scale_mult(1536, 1024)


def test_anchor_slot_flip_right_only():
    assert anchor_slot("left", 1536, 1024)[1] is False
    assert anchor_slot("center", 1536, 1024)[1] is False
    assert anchor_slot("right", 1536, 1024)[1] is True
    assert anchor_slot("???", 1536, 1024) == anchor_slot("center", 1536, 1024)


def test_choose_hook_anchor_matrix():
    assert choose_hook_anchor({"left"}) == "top_right"
    assert choose_hook_anchor({"right"}) == "top_left"
    assert choose_hook_anchor({"center"}) == "top"
    assert choose_hook_anchor({"left", "right"}) == "top"
    assert choose_hook_anchor(set()) == "auto"
    assert choose_hook_anchor({"left"}, requested="bottom") == "top_right"  # ground occupied
    assert choose_hook_anchor({"left"}, requested="right") == "right"       # author wins


def test_compose_visual_mirrors_side_character():
    plan = StoryPlan(
        characters=[CharacterDef(id="a", archetype="office_worker"),
                    CharacterDef(id="b", archetype="student")],
        settings=[SettingDef(id="s1", scene_kind="cafe")],
        visuals=[Visual(id="v1", setting_id="s1", character_ids=["a", "b"])],
        timeline=[Beat(id="b1", visual_id="v1", narration="x")],
    )
    from app.features.render.engine.visual.svg_compose import compose_visual
    svg = compose_visual(plan, plan.visuals[0], 1536, 1024)
    assert svg and 'scale(-1,1)' in svg                          # facing flip present


def test_beat_render_overlay_uses_flip_and_safe_hook():
    from app.features.render.engine.stages.story.beat_render import (
        _anchor_xy, _char_overlay_parts,
    )
    cue = SimpleNamespace(char_scale="medium", char_anchor="right", char_motion="static")
    fg, x, y = _char_overlay_parts(cue, 1536, 1024, 3.0)
    assert "hflip" in fg                                          # right-anchored mirrors
    fg2, _, _ = _char_overlay_parts(cue, 1536, 1024, 3.0, anchor="left")
    assert "hflip" not in fg2
    assert _anchor_xy("top_right")[1] == "h*0.08"                 # extended corners exist
    assert _anchor_xy("top_left")[0] == "w*0.05"


# ── 4b readiness ──────────────────────────────────────────────────────────────

def _ready_plan() -> StoryPlan:
    p = StoryPlan(
        language="vi",
        characters=[CharacterDef(id="a", gender="male")],
        settings=[SettingDef(id="s1")],
        visuals=[Visual(id="v1", setting_id="s1", character_ids=["a"])],
        timeline=[Beat(id="b1", visual_id="v1", narration="xin chào " * 5, speaker_id="a")],
    )
    p.render.asset_status = {"a": "matched"}
    return p


def test_readiness_pass(tmp_path):
    r = evaluate_readiness(_ready_plan(), target_sec=0, output_dir=tmp_path)
    assert r["ready"] and not r["fails"]
    assert {c["id"] for c in r["checks"]} >= {"content", "continuity", "identity",
                                              "background", "composition", "tts",
                                              "duration", "storage"}


def test_readiness_fails_on_empty_and_dangling():
    empty = StoryPlan(visuals=[Visual(id="v1")], timeline=[])
    r = evaluate_readiness(empty)
    assert not r["ready"] and any(c["id"] == "content" and c["level"] == FAIL for c in r["checks"])
    dang = _ready_plan()
    dang.timeline[0].visual_id = "ghost"
    r2 = evaluate_readiness(dang)
    assert not r2["ready"] and any(c["id"] == "continuity" and c["level"] == FAIL for c in r2["checks"])


def test_readiness_warns_identity_and_duration():
    p = _ready_plan()
    p.render.asset_status = {"a": "missing"}
    r = evaluate_readiness(p, target_sec=600)
    ids = {c["id"]: c["level"] for c in r["checks"]}
    assert ids["identity"] == WARN
    assert ids["duration"] == WARN                                # ~4s vs 600s target
    assert r["ready"]                                             # warns don't block


def test_readiness_hook_and_crowd_warn():
    p = _ready_plan()
    p.visuals[0].character_ids = ["a", "a2", "a3", "a4"]
    p.timeline[0].hook = True
    p.timeline[0].hook_text = "x" * 80
    r = evaluate_readiness(p)
    assert any(c["id"] == "composition" and c["level"] == WARN for c in r["checks"])


def test_readiness_gate_env(monkeypatch):
    monkeypatch.setenv("STORY_READINESS_GATE", "0")
    assert gate_enabled() is False
    monkeypatch.delenv("STORY_READINESS_GATE", raising=False)
    assert gate_enabled() is True


# ── 4c targeted reuse ─────────────────────────────────────────────────────────

def test_tts_reuse_skips_valid_persisted_audio(tmp_path, monkeypatch):
    from app.features.render.engine.audio import story_narration as sn
    p = _ready_plan()
    p.timeline.append(Beat(id="b2", visual_id="v1", narration="beat hai", speaker_id="a"))
    wav = tmp_path / "b1.mp3"
    wav.write_bytes(b"audio")
    p.render.beat_audio["b1"] = BeatAudio(str(wav), 3.2, [])
    calls = []
    monkeypatch.setattr(sn, "generate_narration_audio",
                        lambda **kw: calls.append(kw.get("job_id")) or None)
    sn.synthesize_timeline(p, job_id="j", audio_dir=tmp_path / "a")
    assert p.render.beat_audio["b1"].path == str(wav)             # kept, not re-synthesized
    assert all("b1" not in (c or "") for c in calls)              # only b2 hit TTS
    assert any("b2" in (c or "") for c in calls)


def test_tts_reuse_ignores_stale_path(tmp_path, monkeypatch):
    from app.features.render.engine.audio import story_narration as sn
    p = _ready_plan()
    p.render.beat_audio["b1"] = BeatAudio(str(tmp_path / "gone.mp3"), 3.2, [])
    calls = []
    monkeypatch.setattr(sn, "generate_narration_audio",
                        lambda **kw: calls.append(1) or None)
    sn.synthesize_timeline(p, job_id="j", audio_dir=tmp_path / "a")
    assert calls                                                  # stale → re-synth attempted


def test_cue_reuse_only_on_resume(tmp_path):
    from app.features.render.engine.stages.story.beat_render import render_one_cue
    out = tmp_path / "cue_0001.mp4"
    out.write_bytes(b"mp4")
    cue = SimpleNamespace(start_sec=0.0, end_sec=2.0, visual_id="v1", audio_path="",
                          hook=False, hook_text="", crop_from=(0, 0, 1, 1),
                          crop_to=(0, 0, 1, 1), char_anchor="none", char_scale="medium",
                          char_motion="fade", emotion="normal", pose="stand",
                          speaker_id="", source_audio="mute", line_overlays=[],
                          text_anchor="auto")
    plan = _ready_plan()
    ctx = SimpleNamespace(shots_dir=tmp_path, width=64, height=64, fps=10,
                          bg_value="#101820", ffmpeg_threads=0, base_video_path="",
                          base_video_dur=0.0, base_video_has_audio=False, resume=True)
    r = render_one_cue(ctx, plan, 1, cue)
    assert r.get("reused") is True and r["clip"] == str(out)      # no ffmpeg run
