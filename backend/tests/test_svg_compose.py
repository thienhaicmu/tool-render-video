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


def test_compose_scene_when_no_library(monkeypatch):
    # force library miss -> procedural scene fallback
    monkeypatch.setattr("app.db.story_asset_repo.match_asset", lambda *a, **k: None)
    svg = compose_visual(_plan(), Visual(id="v1", setting_id="s", character_ids=["a"]))
    assert "linearGradient" in svg          # scene_inner gradient present


def test_compose_never_raises_on_bad_input():
    assert isinstance(compose_visual(_plan(), Visual(id="v1")), str)


def test_compose_uses_ai_chosen_library_asset(tmp_path):
    # Library-pick (B4): character.asset / setting.asset slugs → embed the EXACT library
    # file (base64 <image>), not procedural art.
    from app.db import story_asset_repo as R
    from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef
    for slug, kind in (("lib_char_zzz", "character"), ("lib_bg_zzz", "background")):
        f = tmp_path / f"{slug}.png"; f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 512)
        R.upsert_asset(path=str(f), kind=kind, region="cn", genre="wuxia", slug=slug)
    p = StoryPlan(region="cn", genre_key="wuxia",
                  characters=[CharacterDef(id="a", name="A", archetype="swordsman", asset="lib_char_zzz")],
                  settings=[SettingDef(id="s", name="hall", scene_kind="throne_room", asset="lib_bg_zzz")])
    svg = compose_visual(p, Visual(id="v1", setting_id="s", character_ids=["a"]))
    assert svg.count("data:image/png;base64") >= 2       # bg + char both from the library

    # no asset + unknown scene → procedural (no embedded library file)
    p2 = StoryPlan(region="cn", genre_key="wuxia",
                   characters=[CharacterDef(id="a", name="A", archetype="swordsman")],
                   settings=[SettingDef(id="s", name="x", scene_kind="zzz_no_such_scene")])
    svg2 = compose_visual(p2, Visual(id="v1", setting_id="s", character_ids=["a"]))
    assert "data:image" not in svg2 and "linearGradient" in svg2   # procedural scene + chibi


@pytest.mark.parametrize("w,h", [(1536, 1024), (1024, 1536), (1024, 1024)])
def test_compose_aspect_aware(w, h, monkeypatch):
    monkeypatch.setattr("app.db.story_asset_repo.match_asset", lambda *a, **k: None)  # scene path
    svg = compose_visual(_plan(), Visual(id="v1", setting_id="s", character_ids=["a", "b"]), w, h)
    assert f'width="{w}"' in svg and f'height="{h}"' in svg and f'viewBox="0 0 {w} {h}"' in svg


@requires_resvg
@pytest.mark.parametrize("w,h", [(1024, 1536), (1024, 1024)])
def test_compose_non_169_rasterises(w, h, monkeypatch):
    monkeypatch.setattr("app.db.story_asset_repo.match_asset", lambda *a, **k: None)
    svg = compose_visual(_plan(), Visual(id="v1", setting_id="s", character_ids=["a"]), w, h)
    png = svg_raster.render_svg(svg, w, h, opaque_bg="#101820")
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    ww, hh = struct.unpack(">II", png[16:24])
    assert (ww, hh) == (w, h)


@requires_resvg
@pytest.mark.parametrize("cids", [["a"], ["a", "b"], ["a", "b", "c"]])
def test_compose_rasterises(cids, monkeypatch):
    monkeypatch.setattr("app.db.story_asset_repo.match_asset", lambda *a, **k: None)  # scene path
    svg = compose_visual(_plan(), Visual(id="v1", setting_id="s", character_ids=cids))
    png = svg_raster.render_svg(svg, 1536, 1024, opaque_bg="#101820")
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", png[16:24])
    assert (w, h) == (1536, 1024)
