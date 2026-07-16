"""N4 — per-(speaker, emotion) overlay masters + background-only key-visual (gated)."""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual, Beat
import app.features.render.engine.stages.story.visuals_stage as vs
from app.features.render.engine.visual.svg_compose import compose_visual


def _plan(asset=""):
    return StoryPlan(region="cn", genre_key="wuxia",
                     characters=[CharacterDef(id="han", name="H", archetype="swordsman", gender="male", asset=asset)],
                     settings=[SettingDef(id="s", name="hall", scene_kind="throne_room")],
                     visuals=[Visual(id="v1", setting_id="s", character_ids=["han"])],
                     timeline=[Beat(id="b1", narration="a", visual_id="v1", speaker_id="han", emotion="angry"),
                               Beat(id="b2", narration="b", visual_id="v1", speaker_id="han", emotion="sad")])


def test_overlay_masters_gate_off(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_CHAR_OVERLAY", "0")        # P4: default is now ON — off needs =0
    monkeypatch.setattr(vs, "update_story_plan", lambda *a, **k: None)
    p = _plan()
    vs._generate_overlay_masters(p, tmp_path, job_id="j", effective_channel="c")
    assert p.render.masters == {}                       # explicit off → no masters


def test_overlay_masters_default_on(monkeypatch, tmp_path):
    # P4: STORY_CHAR_OVERLAY default ON — an unset env now generates overlay masters.
    monkeypatch.delenv("STORY_CHAR_OVERLAY", raising=False)
    monkeypatch.setattr(vs, "update_story_plan", lambda *a, **k: None)
    p = _plan()
    vs._generate_overlay_masters(p, tmp_path, job_id="j", effective_channel="c")
    assert set(p.render.masters.keys()) == {"han:angry:stand", "han:sad:stand"}


def test_overlay_masters_procedural_per_emotion(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_CHAR_OVERLAY", "1")
    monkeypatch.setattr(vs, "update_story_plan", lambda *a, **k: None)
    p = _plan()                                          # no asset → procedural svg_char masters
    vs._generate_overlay_masters(p, tmp_path, job_id="j", effective_channel="c")
    assert set(p.render.masters.keys()) == {"han:angry:stand", "han:sad:stand"}   # cid:emotion:pose
    for path in p.render.masters.values():
        assert path.endswith(".png")


def test_overlay_masters_pose(monkeypatch, tmp_path):
    # N4+ per-beat POSE — the master key includes the pose; the V3 procedural
    # renderer generates the per-(emotion, pose) master.
    monkeypatch.setenv("STORY_CHAR_OVERLAY", "1")
    monkeypatch.setattr(vs, "update_story_plan", lambda *a, **k: None)
    p = StoryPlan(region="cn", genre_key="wuxia",
                  characters=[CharacterDef(id="han", name="H", archetype="swordsman")],
                  visuals=[Visual(id="v1", prompt="x")],
                  timeline=[Beat(id="b1", narration="a", visual_id="v1", speaker_id="han", pose="wave")])
    vs._generate_overlay_masters(p, tmp_path, job_id="j", effective_channel="c")
    assert p.render.masters["han:normal:wave"].endswith(".png")


def test_overlay_masters_emotion_plus_pose(monkeypatch, tmp_path):
    # BOTH emotion AND pose non-default → one combined-axis V3 procedural master.
    monkeypatch.setenv("STORY_CHAR_OVERLAY", "1")
    monkeypatch.setattr(vs, "update_story_plan", lambda *a, **k: None)
    p = StoryPlan(region="cn", genre_key="wuxia",
                  characters=[CharacterDef(id="han", name="H", archetype="swordsman")],
                  visuals=[Visual(id="v1", prompt="x")],
                  timeline=[Beat(id="b1", narration="a", visual_id="v1", speaker_id="han",
                                 emotion="angry", pose="point")])
    vs._generate_overlay_masters(p, tmp_path, job_id="j", effective_channel="c")
    assert p.render.masters["han:angry:point"].endswith(".png")


def test_compose_chars_false_is_background_only():
    v = Visual(id="v1", setting_id="s", character_ids=["han"])
    with_ch = compose_visual(_plan(), v, chars=True)
    no_ch = compose_visual(_plan(), v, chars=False)
    # chars=False drops the character placement group(s) → strictly fewer transformed groups
    assert with_ch.count("<g transform=") > no_ch.count("<g transform=")
