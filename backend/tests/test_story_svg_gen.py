"""Story Mode is SVG-only: _generate_images composes procedural SVG per Visual, with a
solid-background fallback on raster failure (no AI provider)."""
from __future__ import annotations

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual
import app.features.render.engine.stages.story.visuals_stage as vs
import app.features.render.engine.visual.svg_compose as sc
import app.features.render.engine.visual.svg_raster as sr


def _patch_io(mp):
    mp.setattr(vs, "update_story_plan", lambda *a, **k: None)
    mp.setattr(vs, "_emit_render_event", lambda *a, **k: None)


def _plan():
    return StoryPlan(region="cn", genre_key="wuxia",
                     characters=[CharacterDef(id="a", name="Han", archetype="swordsman")],
                     settings=[SettingDef(id="s", name="hall", scene_kind="throne_room")],
                     visuals=[Visual(id="v1", setting_id="s", character_ids=["a"])])


def test_composes_procedural_svg(monkeypatch, tmp_path):
    _patch_io(monkeypatch)
    monkeypatch.setattr(sc, "compose_visual", lambda plan, v, w, h, chars=True: "<svg/>")
    monkeypatch.setattr(sr, "save_svg_png", lambda svg, out, w, h, opaque_bg="": str(out))
    p = _plan()
    fb = vs._generate_images(p, tmp_path, "wuxia", 1536, 1024, job_id="j", effective_channel="c")
    assert p.render.visual_assets["v1"].endswith("v1.png")   # composed via svg save
    assert fb == []


def test_svg_failure_falls_back_to_solid(monkeypatch, tmp_path):
    _patch_io(monkeypatch)
    monkeypatch.setattr(sc, "compose_visual", lambda plan, v, w, h, chars=True: "<svg/>")
    monkeypatch.setattr(sr, "save_svg_png", lambda *a, **k: None)   # raster fails
    p = _plan()
    fb = vs._generate_images(p, tmp_path, "wuxia", 1536, 1024, job_id="j", effective_channel="c")
    assert fb == ["v1"]                        # no AI fallback — a solid background is used
    assert "v1" not in p.render.visual_assets


def test_provider_arg_ignored_still_svg(monkeypatch, tmp_path):
    """provider is accepted for call-site parity but Story Mode is always SVG."""
    _patch_io(monkeypatch)
    monkeypatch.setattr(sc, "compose_visual", lambda plan, v, w, h, chars=True: "<svg/>")
    monkeypatch.setattr(sr, "save_svg_png", lambda svg, out, w, h, opaque_bg="": str(out))
    p = _plan()
    vs._generate_images(p, tmp_path, "wuxia", 1536, 1024,
                        job_id="j", effective_channel="c", provider="anything")
    assert p.render.visual_assets["v1"].endswith("v1.png")
