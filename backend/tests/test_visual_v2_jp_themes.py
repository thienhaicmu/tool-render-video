from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET

from app.features.render.engine.visual.v2.anime_char import build_anime_char
from app.features.render.engine.visual.v2.anime_scene import build_anime_scene
from app.features.render.engine.visual.v2.look_spec import derive_look
from app.features.render.engine.visual.v2.styles import list_styles, render_character
from app.features.render.engine.visual.v2.jp_catalog import (
    JP_BACKGROUNDS, JP_ROLES, background_for_role, role_look, search_roles,
)
from app.features.render.engine.visual.v2.theme_pack import (
    JP_STYLE_PACKS, STYLE_CINEMATIC, STYLE_CLEAN, STYLE_SOFT_DRAMA,
    STYLE_US_CINEMATIC, STYLE_US_EDITORIAL, STYLE_US_STORYBOOK,
    resolve_style,
)


def _digest(value: str) -> str:
    ET.fromstring(value)
    return hashlib.sha256(value.encode()).hexdigest()


def test_three_japanese_styles_preserve_identity_and_render_differently():
    look = derive_look("jp_doctor_aiko", gender="female", outfit="doctor_coat")
    identity = look.to_dict().copy()
    svgs = [build_anime_char(look, style_id=sid) for sid in JP_STYLE_PACKS]
    assert len({_digest(svg) for svg in svgs}) == 3
    assert look.to_dict() == identity
    assert all(f'data-style-id="{sid}"' in svg for sid, svg in zip(JP_STYLE_PACKS, svgs))
    assert all("<svg" in svg and "<rect width=\"1024\" height=\"1536\"" not in svg for svg in svgs)


def test_three_japanese_scene_styles_are_well_formed_and_distinct():
    svgs = [build_anime_scene("office", "night", sid) for sid in JP_STYLE_PACKS]
    assert len({_digest(svg) for svg in svgs}) == 3
    assert all(f'data-style-id="{sid}"' in svg for sid, svg in zip(JP_STYLE_PACKS, svgs))


def test_every_scene_renders_in_every_japanese_theme():
    from app.features.render.engine.visual.v2.anime_scene import SCENES
    for scene in SCENES:
        for sid in JP_STYLE_PACKS:
            assert _digest(build_anime_scene(scene, "sunset", sid))


def test_profession_outfits_render_in_every_theme():
    for outfit in ("doctor_coat", "police_uniform", "engineer_workwear"):
        look = derive_look(outfit, gender="female", outfit=outfit)
        for sid in (STYLE_CLEAN, STYLE_CINEMATIC, STYLE_SOFT_DRAMA):
            assert _digest(build_anime_char(look, style_id=sid))


def test_us_style_packs_preserve_identity_and_render_distinct_treatments():
    look = derive_look("us-style-proof", gender="female", outfit="tee_casual")
    styles = (STYLE_US_EDITORIAL, STYLE_US_CINEMATIC, STYLE_US_STORYBOOK)
    svgs = [build_anime_char(look, style_id=sid) for sid in styles]
    assert len({_digest(svg) for svg in svgs}) == len(styles)
    assert all(f'data-style-id="{sid}"' in svg for sid, svg in zip(styles, svgs))
    assert all(resolve_style(sid) == sid for sid in styles)


def test_style_registry_exposes_three_japanese_styles():
    ids = {item["id"] for item in list_styles()}
    assert set(JP_STYLE_PACKS).issubset(ids)
    look = derive_look("jp_police", gender="male", outfit="police_uniform")
    assert 'data-style-id="jp_anime_cinematic_v1"' in render_character(
        "jp_anime_cinematic_v1", look
    )


def test_japanese_catalog_has_stable_roles_and_matching_backgrounds():
    assert len(JP_ROLES) == 24
    assert len({r["id"] for r in JP_ROLES}) == 24
    assert {r["era"] for r in JP_ROLES} == {"modern", "historical"}
    known_scenes = {bg["scene"] for bg in JP_BACKGROUNDS}
    for role in JP_ROLES:
        assert role["scene_id"] in known_scenes or role["scene_id"] in {"castle_hall", "forest", "street"}
        assert _digest(build_anime_char(role_look(role["id"]), style_id=STYLE_CLEAN))
        assert background_for_role(role["id"])


def test_japanese_catalog_searches_ja_en_zh_offline():
    assert search_roles("医師")[0]["outfit"] == "doctor_coat"
    assert search_roles("engineer")[0]["outfit"] == "engineer_workwear"
    assert search_roles("女总裁")[0]["id"] == "jp_ceo_woman"
