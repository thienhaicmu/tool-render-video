"""Phase B2 — chibi SVG char builder + archetype presets (pure, defensive)."""
from __future__ import annotations

import struct

import pytest

from app.features.render.engine.visual.svg_char import build_char, emotion_expr
from app.features.render.engine.visual.svg_presets import preset
from app.features.render.engine.visual import svg_raster

requires_resvg = pytest.mark.skipif(not svg_raster.available(), reason="resvg-py not installed")


def test_build_char_returns_svg():
    s = build_char(preset("office_worker", "jp", "hiendai", "male"))
    assert s.startswith("<svg") and s.endswith("</svg>") and 'width="1024"' in s


def test_emotion_mapping():
    assert emotion_expr("normal") == "smile"
    assert emotion_expr("surprised") == "open"
    assert emotion_expr("ANGRY") == "angry"
    assert emotion_expr("nonsense") == "smile"


def test_preset_unknown_falls_back_to_everyman():
    o = preset("totally_unknown_role", "xx", "yy", "")
    assert o.get("bottom", {}).get("kind") == "shorts" and o.get("top")


def test_preset_female_tweak_gives_dress():
    o = preset("student", "jp", "hiendai", "female")
    assert o["bottom"]["kind"] == "dress" and o["hair_style"] == "long"


def test_preset_region_skin():
    assert preset("student", "vi", "", "male")["skin"] == "#e6b58a"   # region tint applied


@requires_resvg
@pytest.mark.parametrize("arch", ["office_worker", "swordsman", "princess", "emperor",
                                  "witch", "ghost", "child", "knight"])
def test_every_archetype_rasterises(arch, tmp_path):
    o = preset(arch, "cn", "wuxia", "female" if arch in ("princess", "witch") else "male")
    png = svg_raster.render_svg(build_char(o), 1024, 1536)
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", png[16:24])
    assert (w, h) == (1024, 1536)


@requires_resvg
@pytest.mark.parametrize("arch", ["monk", "assassin", "merchant", "archer", "ranger",
                                  "orc", "demon", "angel", "fairy", "pirate", "bard",
                                  "doctor", "police", "firefighter", "farmer", "detective",
                                  "maid", "robot", "monk_warrior"])
def test_new_archetypes_rasterise(arch, tmp_path):
    # each new archetype (incl. its new prop: halo / horns / antenna / bow / hood…) must
    # build valid, rasterisable chibi art.
    png = svg_raster.render_svg(build_char(preset(arch, "eu", "fantasy", "male")), 1024, 1536)
    assert png and png[:8] == b"\x89PNG\r\n\x1a\n"


@requires_resvg
@pytest.mark.parametrize("expr", ["smile", "open", "angry", "sad", "stern"])
@pytest.mark.parametrize("pose", ["stand", "wave", "cheer", "point", "hip"])
def test_emotions_and_poses_render(expr, pose, tmp_path):
    o = preset("child", "jp", "hiendai", ""); o["expr"] = expr; o["pose"] = pose
    assert svg_raster.render_svg(build_char(o), 1024, 1536) is not None


def test_build_char_never_raises_on_bad_opts():
    assert build_char(None) == "" or build_char(None).startswith("<svg")
    assert isinstance(build_char({"bottom": "not a dict"}), str)
