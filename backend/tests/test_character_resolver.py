"""
GĐ3 — deterministic character→asset resolver + identity lock.

Pins: gender hard-filter + VN→EN scoring, UNIQUE assignment (no shared face),
series lock (matched_exact, wins over content), honoring Review/paste picks,
needs_approval / missing states, plan.render.asset_status fill, catalog ``kinds``
gating (resolver on → prompt carries backgrounds only), characters.asset_slug
persistence (migration 0026) + story_series_memory.locked_assets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.db.connection import init_db
from app.db import story_asset_repo as repo
from app.db import story_repo
from app.domain.story_plan_v2 import CharacterDef, StoryPlan
from app.features.render.engine.visual.character_resolver import (
    MATCHED, MATCHED_EXACT, MISSING, NEEDS_APPROVAL, resolve_characters, resolver_enabled,
)


def setup_module(module):  # noqa: D401
    init_db()


@pytest.fixture()
def library(tmp_path):
    """Real on-disk candidate assets (the resolver skips files that don't exist)."""
    made = []

    def _add(slug, name, tags, transparent=True, genre="hiendai"):
        p = tmp_path / f"{slug}.png"
        p.write_bytes(b"png")
        aid = repo.upsert_asset(path=str(p), kind="character", region="us", genre=genre,
                                slug=slug, name=name, tags=tags, transparent=transparent)
        made.append(aid)
        return slug

    _add("g_hoodie_man", "young man in red hoodie",
         "male adult black short hair red hoodie jeans sneakers casual")
    _add("g_dress_woman", "young woman in pink dress",
         "female adult pink long hair dress heels cheerful")
    _add("g_elder_man", "old man with beard",
         "male elder gray hair beard vest cane")
    _add("g_opaque", "opaque asset", "male adult suit", transparent=False)
    yield
    for aid in made:
        repo.delete_asset(aid)


def _plan(*chars) -> StoryPlan:
    return StoryPlan(characters=list(chars))


def test_gender_filter_and_vi_en_scoring(library):
    p = _plan(
        CharacterDef(id="nam1", name="Hùng", gender="male",
                     canonical_desc="chàng trai trẻ tóc đen, áo hoodie đỏ"),
        CharacterDef(id="nu1", name="Lan", gender="female",
                     canonical_desc="cô gái tóc hồng mặc váy"),
    )
    rep = resolve_characters(p, genres=("hiendai",))
    assert rep["assigned"]["nam1"] == "g_hoodie_man"
    assert rep["assigned"]["nu1"] == "g_dress_woman"
    assert rep["statuses"]["nam1"] == MATCHED and rep["statuses"]["nu1"] == MATCHED
    assert p.characters[0].asset == "g_hoodie_man"
    assert p.render.asset_status["nu1"] == MATCHED


def test_unique_assignment_never_shares_a_face(library):
    p = _plan(
        CharacterDef(id="a", gender="male", canonical_desc="áo hoodie đỏ tóc đen"),
        CharacterDef(id="b", gender="male", canonical_desc="áo hoodie đỏ tóc đen"),
    )
    rep = resolve_characters(p, genres=("hiendai",))
    assert rep["assigned"]["a"] and rep["assigned"]["b"]
    assert rep["assigned"]["a"] != rep["assigned"]["b"]      # uniqueness constraint


def test_series_lock_wins_and_is_exact(library):
    p = _plan(CharacterDef(id="hero", gender="male", canonical_desc="áo hoodie đỏ"))
    rep = resolve_characters(p, locked={"hero": "g_dress_woman"}, genres=("hiendai",))
    assert rep["assigned"]["hero"] == "g_dress_woman"        # lock beats content match
    assert rep["statuses"]["hero"] == MATCHED_EXACT
    assert p.characters[0].asset == "g_dress_woman"


def test_existing_pick_honored(library):
    p = _plan(CharacterDef(id="x", gender="female", canonical_desc="váy hồng",
                           asset="g_elder_man"))
    rep = resolve_characters(p, genres=("hiendai",))
    assert rep["statuses"]["x"] == MATCHED_EXACT and p.characters[0].asset == "g_elder_man"


def test_missing_when_hard_filter_leaves_nothing(library):
    # Both female-compatible assets consumed → the third female has no candidate.
    p = _plan(
        CharacterDef(id="f1", gender="female", canonical_desc="váy hồng"),
        CharacterDef(id="f2", gender="female", canonical_desc="tóc hồng"),
    )
    rep = resolve_characters(p, genres=("hiendai",))
    states = set(rep["statuses"].values())
    assert MISSING in states                        # only ONE female asset exists
    missing_cid = rep["missing"][0]
    assert p.character(missing_cid).asset == ""     # no silent substitution


def test_weak_match_flags_needs_approval(library):
    p = _plan(CharacterDef(id="v", gender="", canonical_desc="nhân vật bí ẩn"))
    rep = resolve_characters(p, genres=("hiendai",))
    assert rep["statuses"]["v"] in (NEEDS_APPROVAL, MISSING)
    if rep["statuses"]["v"] == NEEDS_APPROVAL:
        assert rep["assigned"]["v"]                 # assigned but flagged


def test_opaque_assets_excluded(library):
    p = _plan(CharacterDef(id="s", gender="male", canonical_desc="suit"))
    rep = resolve_characters(p, genres=("hiendai",))
    assert rep["assigned"].get("s") != "g_opaque"


def test_resolver_env_gate(monkeypatch):
    monkeypatch.setenv("STORY_CHAR_RESOLVER", "0")
    assert resolver_enabled() is False
    monkeypatch.delenv("STORY_CHAR_RESOLVER", raising=False)
    assert resolver_enabled() is True


def test_catalog_kinds_gating(library):
    both = repo.build_library_catalog(genres=("hiendai",))
    bg_only = repo.build_library_catalog(genres=("hiendai",), kinds=("background",))
    assert "CHARACTERS" in both
    assert "CHARACTERS" not in bg_only


def test_asset_slug_persist_and_locked_assets():
    story_repo.upsert_series("s_test_gd3", language="vi")
    story_repo.upsert_character("han_phong", series_id="s_test_gd3", name="Hàn Phong",
                                asset_slug="g_hoodie_man")
    got = story_repo.get_character("han_phong")
    assert got and got["asset_slug"] == "g_hoodie_man"
    from app.features.render.engine.pipeline.story_series_memory import locked_assets
    locks = locked_assets("s_test_gd3")
    assert locks.get("han_phong") == "g_hoodie_man"
    # upsert with empty slug must NOT clear an existing lock via persist path
    # (persist_series_memory prefers prev_slug) — repo itself overwrites, so check
    # the memory-layer behaviour with a plan carrying no asset:
    from app.features.render.engine.pipeline.story_series_memory import persist_series_memory
    plan = StoryPlan(series_id="s_test_gd3",
                     characters=[CharacterDef(id="han_phong", name="Hàn Phong", asset="")])
    persist_series_memory(plan, "s_test_gd3", 2)
    assert story_repo.get_character("han_phong")["asset_slug"] == "g_hoodie_man"
    story_repo.delete_series("s_test_gd3")
