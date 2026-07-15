"""
Kiến trúc thư viện STYLE-AWARE (JP three-style set):
    {kind}/{region}/{genre}/{style}/{slug}.png

Pins: scanner nhận tầng style thứ 3 (path 2 tầng cũ giữ style ""), list_assets
lọc style (active ∪ styleless), get_by_slug ưu tiên đúng biến thể style,
active_library_style chuẩn hoá + validate, catalog theo style, và resolver
dedupe slug đa-style khi không có style hoạt động.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.db.connection import init_db
from app.db import story_asset_repo as repo
from app.domain.story_plan_v2 import CharacterDef, StoryPlan
from app.features.render.engine.visual.character_resolver import resolve_characters


def setup_module(module):  # noqa: D401
    init_db()


def test_parse_path_third_level_is_style(tmp_path):
    root = tmp_path
    p3 = root / "character" / "jp" / "codai" / "style_x" / "jp_samurai.png"
    p2 = root / "character" / "us" / "hiendai" / "geeme_001.png"
    meta3 = repo._parse_path(root, p3)
    meta2 = repo._parse_path(root, p2)
    assert meta3 == {"kind": "character", "region": "jp", "genre": "codai",
                     "style": "style_x", "slug": "jp_samurai"}
    assert meta2["style"] == "" and meta2["slug"] == "geeme_001"


@pytest.fixture()
def styled_lib(tmp_path):
    made = []

    def _add(slug, style, tags="male adult samurai warrior", genre="codai"):
        p = tmp_path / f"{style or 'plain'}_{slug}.png"
        p.write_bytes(b"png")
        made.append(repo.upsert_asset(path=str(p), kind="character", region="jp",
                                      genre=genre, slug=slug, name=slug.replace("_", " "),
                                      tags=tags, style=style, transparent=True))
        return str(p)

    paths = {
        "clean": _add("t_samurai", "style_clean"),
        "cine": _add("t_samurai", "style_cine"),
        "plain": _add("t_ronin", "", tags="male adult ronin swordsman"),
    }
    yield paths
    for aid in made:
        repo.delete_asset(aid)


def test_list_assets_style_filter(styled_lib):
    all_rows = repo.list_assets(kind="character", q="t_samurai")
    assert len([a for a in all_rows if a["slug"] == "t_samurai"]) == 2       # None = mọi style
    clean = repo.list_assets(kind="character", q="t_", style="style_clean")
    styles = {a["style"] for a in clean}
    assert styles <= {"style_clean", ""}                                      # active ∪ styleless
    plain_only = repo.list_assets(kind="character", q="t_", style="")
    assert {a["style"] for a in plain_only} == {""}


def test_get_by_slug_style_precedence(styled_lib):
    assert repo.get_by_slug("t_samurai", "character", style="style_cine") == styled_lib["cine"]
    assert repo.get_by_slug("t_samurai", "character", style="style_clean") == styled_lib["clean"]
    # style lạ → vẫn trả được một biến thể (không chết render)
    assert repo.get_by_slug("t_samurai", "character", style="style_zzz") in styled_lib.values()
    # styleless asset luôn resolve bất kể style hoạt động
    assert repo.get_by_slug("t_ronin", "character", style="style_clean") == styled_lib["plain"]


def test_active_library_style_normalizes(styled_lib):
    assert repo.active_library_style("STYLE_CLEAN") == "style_clean"
    assert repo.active_library_style("Style-Clean") == "style_clean"
    assert repo.active_library_style("wuxia") == ""                           # chưa cài → ""
    assert repo.active_library_style("") == ""


def test_catalog_dedupes_multi_style_slug(styled_lib):
    cat = repo.build_library_catalog(genres=("codai",), style="style_clean")
    assert cat.count("t_samurai |") == 1                                       # một dòng một vai


def test_resolver_dedupes_twins_without_active_style(styled_lib):
    p = StoryPlan(characters=[
        CharacterDef(id="a", gender="male", canonical_desc="samurai warrior"),
        CharacterDef(id="b", gender="male", canonical_desc="samurai warrior"),
    ])
    rep = resolve_characters(p, genres=("codai",), style=None)
    # KHÔNG được gán cùng slug t_samurai 2 style cho 2 nhân vật (cùng mặt)
    assert rep["assigned"].get("a") != rep["assigned"].get("b")
    assert {rep["assigned"].get("a"), rep["assigned"].get("b")} <= {"t_samurai", "t_ronin"}


def test_resolver_respects_active_style(styled_lib):
    p = StoryPlan(art_style="style_cine",
                  characters=[CharacterDef(id="a", gender="male",
                                           canonical_desc="samurai warrior")])
    rep = resolve_characters(p, genres=("codai",))
    assert rep["assigned"]["a"] == "t_samurai"
    # và render-path lấy đúng biến thể style đó
    assert repo.get_by_slug(rep["assigned"]["a"], "character",
                            style=repo.active_library_style(p.art_style)) == styled_lib["cine"]
