"""Phase B4 — compose a wide key-visual (background + characters in L/C/R zones)."""
from __future__ import annotations

import struct

import pytest

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual
from app.features.render.engine.visual.svg_compose import compose_visual
from app.features.render.engine.visual import svg_raster

requires_resvg = pytest.mark.skipif(not svg_raster.available(), reason="resvg-py not installed")


def _plan():
    return StoryPlan(
        region="cn", genre_key="wuxia",
        characters=[CharacterDef(id="a", name="Han", archetype="swordsman", gender="male"),
                    CharacterDef(id="b", name="Ly", archetype="heroine", gender="female"),
                    CharacterDef(id="c", name="Vua", archetype="emperor", gender="male")],
        settings=[SettingDef(id="s", name="dai dien", scene_kind="throne_room")],
    )


@pytest.mark.parametrize("cids", [[], ["a"], ["a", "b"], ["a", "b", "c"]])
def test_compose_shape(cids):
    p = _plan()
    svg = compose_visual(p, Visual(id="v1", setting_id="s", character_ids=cids))
    assert svg.startswith("<svg") and 'width="1536"' in svg and svg.endswith("</svg>")
    # a <g transform> per placed character
    assert svg.count("<g transform=") >= len(cids)


def test_compose_scene_when_no_identity(monkeypatch):
    # no V3 scene identity → the v2 anime scene fallback generates the background
    svg = compose_visual(_plan(), Visual(id="v1", setting_id="s", character_ids=["a"]))
    assert "linearGradient" in svg          # generated scene gradient present


def test_compose_never_raises_on_bad_input():
    assert isinstance(compose_visual(_plan(), Visual(id="v1")), str)


def test_v3_procedural_character_without_identity():
    plan = StoryPlan(
        characters=[CharacterDef(id="a", archetype="unknown")],
        settings=[SettingDef(id="s", scene_kind="unknown")],
    )
    svg = compose_visual(plan, Visual(id="v1", setting_id="s", character_ids=["a"]))
    assert svg.startswith("<svg") and "data-character" not in svg
    assert "<g transform=" in svg


def test_compose_procedural_when_nothing_matches():
    # Safety: gibberish archetype/scene → generated procedural art (a library asset
    # is never substituted for an unknown identity).
    from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef
    p = StoryPlan(region="cn", genre_key="wuxia",
                  characters=[CharacterDef(id="a", name="", archetype="qwzzxvorp", gender="")],
                  settings=[SettingDef(id="s", name="", scene_kind="qwzzxvorp")])
    svg = compose_visual(p, Visual(id="v1", setting_id="s", character_ids=["a"]))
    assert "data:image" not in svg and "linearGradient" in svg   # generated scene + character


@pytest.mark.parametrize("w,h", [(1536, 1024), (1024, 1536), (1024, 1024)])
def test_compose_aspect_aware(w, h):
    svg = compose_visual(_plan(), Visual(id="v1", setting_id="s", character_ids=["a", "b"]), w, h)
    assert f'width="{w}"' in svg and f'height="{h}"' in svg and f'viewBox="0 0 {w} {h}"' in svg


@requires_resvg
@pytest.mark.parametrize("w,h", [(1024, 1536), (1024, 1024)])
def test_compose_non_169_rasterises(w, h):
    svg = compose_visual(_plan(), Visual(id="v1", setting_id="s", character_ids=["a"]), w, h)
    png = svg_raster.render_svg(svg, w, h, opaque_bg="#101820")
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    ww, hh = struct.unpack(">II", png[16:24])
    assert (ww, hh) == (w, h)


@requires_resvg
@pytest.mark.parametrize("cids", [["a"], ["a", "b"], ["a", "b", "c"]])
def test_compose_rasterises(cids):
    svg = compose_visual(_plan(), Visual(id="v1", setting_id="s", character_ids=cids))
    png = svg_raster.render_svg(svg, 1536, 1024, opaque_bg="#101820")
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", png[16:24])
    assert (w, h) == (1536, 1024)
