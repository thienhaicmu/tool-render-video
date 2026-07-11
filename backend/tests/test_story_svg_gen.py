"""Phase B5 — STORY_SVG_GEN gate wires procedural SVG into _generate_images."""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual
import app.features.render.engine.stages.story.visuals_stage as vs
import app.features.render.engine.visual.svg_compose as sc
import app.features.render.engine.visual.svg_raster as sr


def _patch_io(mp):
    mp.setattr(vs, "update_story_plan", lambda *a, **k: None)
    mp.setattr(vs, "_emit_render_event", lambda *a, **k: None)
    mp.delenv("STORY_LIBRARY_FIRST", raising=False)   # keep Phase A off


def _plan():
    return StoryPlan(region="cn", genre_key="wuxia",
                     characters=[CharacterDef(id="a", name="Han", archetype="swordsman")],
                     settings=[SettingDef(id="s", name="hall", scene_kind="throne_room")],
                     visuals=[Visual(id="v1", setting_id="s", character_ids=["a"])])


def test_gate_on_uses_svg_not_ai(monkeypatch, tmp_path):
    _patch_io(monkeypatch)
    monkeypatch.setenv("STORY_SVG_GEN", "1")
    monkeypatch.setattr(sc, "compose_visual", lambda plan, v, w, h: "<svg/>")
    monkeypatch.setattr(sr, "save_svg_png", lambda svg, out, w, h, opaque_bg="": str(out))
    ai = []
    monkeypatch.setattr(vs, "generate_visual_image", lambda v, *a, **k: ai.append(v.id) or "ai.png")
    p = _plan()
    fb = vs._generate_images(p, tmp_path, "wuxia", 1536, 1024, job_id="j", effective_channel="c")
    assert ai == []                                   # AI never called
    assert p.render.visual_assets["v1"].endswith("v1.png")   # from svg save
    assert fb == []


def test_gate_on_falls_back_to_ai_on_svg_failure(monkeypatch, tmp_path):
    _patch_io(monkeypatch)
    monkeypatch.setenv("STORY_SVG_GEN", "1")
    monkeypatch.setattr(sc, "compose_visual", lambda plan, v, w, h: "<svg/>")
    monkeypatch.setattr(sr, "save_svg_png", lambda *a, **k: None)   # svg raster fails
    ai = []
    monkeypatch.setattr(vs, "generate_visual_image",
                        lambda v, *a, **k: ai.append(v.id) or "ai.png")
    p = _plan()
    vs._generate_images(p, tmp_path, "wuxia", 1536, 1024, job_id="j", effective_channel="c")
    assert ai == ["v1"]                               # degraded to gpt-image
    assert p.render.visual_assets["v1"] == "ai.png"


def test_provider_svg_uses_compose_without_env(monkeypatch, tmp_path):
    # Phase C: provider="svg" (no STORY_SVG_GEN) → procedural path.
    _patch_io(monkeypatch)
    monkeypatch.delenv("STORY_SVG_GEN", raising=False)
    monkeypatch.setattr(sc, "compose_visual", lambda plan, v, w, h: "<svg/>")
    monkeypatch.setattr(sr, "save_svg_png", lambda svg, out, w, h, opaque_bg="": str(out))
    ai = []
    monkeypatch.setattr(vs, "generate_visual_image", lambda v, *a, **k: ai.append(v.id) or "ai.png")
    p = _plan()
    vs._generate_images(p, tmp_path, "wuxia", 1536, 1024, job_id="j", effective_channel="c", provider="svg")
    assert ai == []
    assert p.render.visual_assets["v1"].endswith("v1.png")


def test_gate_off_uses_ai(monkeypatch, tmp_path):
    _patch_io(monkeypatch)
    monkeypatch.delenv("STORY_SVG_GEN", raising=False)
    called = {"svg": 0}
    monkeypatch.setattr(sc, "compose_visual", lambda *a, **k: called.__setitem__("svg", 1) or "<svg/>")
    monkeypatch.setattr(vs, "generate_visual_image", lambda v, *a, **k: "ai.png")
    p = _plan()
    vs._generate_images(p, tmp_path, "wuxia", 1536, 1024, job_id="j", effective_channel="c")
    assert called["svg"] == 0                          # svg path not taken
    assert p.render.visual_assets["v1"] == "ai.png"
