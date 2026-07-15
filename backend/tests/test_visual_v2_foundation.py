"""
GĐ2 Visual Foundation — parts-based anime character + layered scene factories.

Pins (no raster needed — pure SVG structure checks, fast + resvg-free):
  * derive_look is DETERMINISTIC per seed and respects explicit/base overrides.
  * every EMOTION × POSE × OUTFIT builds a non-empty, well-formed SVG.
  * facing mirror / age scaling apply their transforms.
  * every SCENE × TOD builds well-formed opaque SVG; gradient ids are UNIQUE per
    instance (two scenes concatenated share no id — the contact-sheet night-sky bug).
  * v2 modules are NOT imported by the render pipeline (GĐ2 gate: approval first).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from app.features.render.engine.visual.v2.anime_char import (
    build_anime_char, anime_char_inner, EMOTIONS, POSES,
)
from app.features.render.engine.visual.v2.anime_scene import (
    build_anime_scene, anime_scene_inner, SCENES, TODS,
)
from app.features.render.engine.visual.v2.look_spec import (
    derive_look, shade, OUTFITS,
)


def _well_formed(svg: str) -> bool:
    assert svg and svg.startswith("<svg")
    ET.fromstring(svg)          # raises on malformed XML
    return True


# ── look_spec ─────────────────────────────────────────────────────────────────

def test_derive_look_deterministic():
    a = derive_look("han_phong", gender="male", outfit="hanfu_robe")
    b = derive_look("han_phong", gender="male", outfit="hanfu_robe")
    assert a.to_dict() == b.to_dict()
    c = derive_look("tuyet_nhi", gender="female")
    assert c.to_dict() != a.to_dict()


def test_derive_look_respects_overrides():
    base = {"hair_color": "#123456", "skin": "#ffe3c9", "accessories": ["glasses"]}
    lk = derive_look("x", gender="female", age="elder", outfit="kimono", base=base)
    assert lk.hair_color == "#123456" and lk.skin == "#ffe3c9"
    assert lk.gender == "female" and lk.age == "elder" and lk.outfit == "kimono"
    assert "glasses" in lk.accessories


def test_shade_defensive():
    assert shade("#808080", 0.5) == "#404040"
    assert shade("junk", 0.5) == "junk"


# ── character builder ─────────────────────────────────────────────────────────

def test_all_emotions_build():
    lk = derive_look("emo", gender="female", outfit="school_uniform")
    for e in EMOTIONS:
        assert _well_formed(build_anime_char(lk, emotion=e)), e


def test_all_poses_build():
    lk = derive_look("pose", gender="male", outfit="office_suit")
    for p in POSES:
        assert _well_formed(build_anime_char(lk, pose=p)), p


def test_all_outfits_and_ages_build():
    for outfit in OUTFITS:
        for gender in ("male", "female"):
            lk = derive_look(f"{outfit}_{gender}", gender=gender, outfit=outfit)
            assert _well_formed(build_anime_char(lk)), (outfit, gender)
    for age in ("child", "adult", "elder"):
        lk = derive_look(f"age_{age}", age=age)
        assert _well_formed(build_anime_char(lk)), age


def test_facing_mirror_and_child_scale():
    lk = derive_look("face", gender="female")
    left = anime_char_inner(lk, facing="left")
    assert "scale(-1,1)" in left
    child = anime_char_inner(derive_look("kid", age="child"))
    assert "scale(0.72)" in child


def test_char_never_raises_on_junk():
    assert anime_char_inner({}, emotion="???", pose="???", facing="???") != ""
    assert build_anime_char(None) != ""


# ── scene builder ─────────────────────────────────────────────────────────────

def test_all_scenes_and_tods_build():
    for kind in SCENES:
        for tod in TODS:
            assert _well_formed(build_anime_scene(kind, tod)), (kind, tod)
    assert _well_formed(build_anime_scene("unknown_place", "night"))   # fallback stage


def test_scene_gradient_ids_unique_per_instance():
    import re
    a = anime_scene_inner("street", "night")
    b = anime_scene_inner("shrine", "sunset")
    ids_a = set(re.findall(r'id="([^"]+)"', a))
    ids_b = set(re.findall(r'id="([^"]+)"', b))
    assert ids_a and ids_b and not (ids_a & ids_b)   # no collision when concatenated


def test_scene_aliases_route():
    assert anime_scene_inner("throne_room", "day")   # → castle_hall
    assert anime_scene_inner("coffee_shop", "night")


# ── GĐ2 gate: not wired into the pipeline yet ────────────────────────────────

def test_v2_not_imported_by_render_paths():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app" / "features" / "render" / "engine"
    hits = []
    for p in root.rglob("*.py"):
        if "visual" + "\\" + "v2" in str(p) or "visual/v2" in str(p).replace("\\", "/"):
            continue
        if "visual.v2" in p.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(p))
    assert not hits, f"v2 must stay unwired until the sheets are approved: {hits}"
