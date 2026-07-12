"""Phase B3 — procedural flat scene builder (keyed by scene_kind + tod)."""
from __future__ import annotations

import struct

import pytest

from app.features.render.engine.visual.svg_scene import scene_inner, build_scene
from app.features.render.engine.visual import svg_raster

requires_resvg = pytest.mark.skipif(not svg_raster.available(), reason="resvg-py not installed")


@pytest.mark.parametrize("kind", ["cafe", "classroom", "forest", "mountain", "throne_room",
                                  "bedroom", "living_room", "kitchen", "garden", "street", "castle_hall"])
def test_known_scene_kinds_non_empty(kind):
    s = scene_inner(kind, "cn", "wuxia", "")
    assert s and s.strip().startswith("<")


@pytest.mark.parametrize("kind", ["temple", "shrine", "inn", "market", "library",
                                  "battlefield", "cave", "beach", "snow", "desert",
                                  "rooftop", "office", "hospital", "graveyard", "ruins",
                                  "waterfall", "courtyard"])
def test_new_scene_kinds_non_empty(kind):
    s = scene_inner(kind, "cn", "wuxia", "")
    assert s and s.strip().startswith("<")


@requires_resvg
@pytest.mark.parametrize("kind", ["temple", "rooftop", "graveyard", "beach", "ruins"])
def test_new_scenes_rasterise(kind):
    png = svg_raster.render_svg(build_scene(kind, "us", "hiendai", "night"), 1536, 1024,
                                opaque_bg="#101820")
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_kind_falls_back_to_genre_gradient():
    s = scene_inner("nonexistent_place", "", "horror", "")
    assert s and "linearGradient" in s          # always a background


def test_night_tint_appends_overlay():
    day = scene_inner("cafe", "", "", "")
    night = scene_inner("cafe", "", "", "night")
    assert len(night) > len(day) and "#f4f0d0" in night   # moon added


def test_scene_never_raises():
    assert isinstance(scene_inner(None, None, None, None), str)


@requires_resvg
@pytest.mark.parametrize("kind,tod", [("throne_room", "night"), ("garden", ""), ("forest", "night")])
def test_scene_rasterises_opaque(kind, tod):
    png = svg_raster.render_svg(build_scene(kind, "cn", "codai", tod), 1536, 1024, opaque_bg="#101820")
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", png[16:24])
    assert (w, h) == (1536, 1024)
