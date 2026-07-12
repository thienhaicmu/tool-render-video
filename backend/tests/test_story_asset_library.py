"""Story asset library (AL0) — migration 0024 + repo CRUD + folder scanner."""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.db.connection import init_db, db_conn
from app.db import story_asset_repo as repo
from app.features.story.router import (
    list_story_assets, get_story_asset, get_story_asset_image,
    scan_story_assets, delete_story_asset,
)


def setup_module(module):  # noqa: D401
    init_db()


def test_migration_created_table():
    with db_conn() as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='story_assets'"
        ).fetchone()
    assert row is not None


def test_upsert_get_delete():
    aid = repo.upsert_asset(path="/lib/character/cn/wuxia/cn_hero.png", kind="character",
                            region="cn", genre="wuxia", slug="cn_hero", name="Hero",
                            transparent=True, license="ai-generated")
    assert aid
    got = repo.get_asset(aid)
    assert got and got["kind"] == "character" and got["region"] == "cn"
    assert got["transparent"] is True
    # upsert same path → same id (idempotent), updated fields
    aid2 = repo.upsert_asset(path="/lib/character/cn/wuxia/cn_hero.png", kind="character",
                             region="cn", genre="wuxia", slug="cn_hero", name="Hero Renamed")
    assert aid2 == aid and repo.get_asset(aid)["name"] == "Hero Renamed"
    assert repo.delete_asset(aid) and repo.get_asset(aid) is None


def test_list_filters():
    a = repo.upsert_asset(path="/lib/character/jp/hiendai/jp_yuki.png", kind="character",
                          region="jp", genre="hiendai", slug="jp_yuki", name="Yuki",
                          tags="cafe,gentle")
    b = repo.upsert_asset(path="/lib/background/jp/hiendai/jp_cafe.png", kind="background",
                          region="jp", genre="hiendai", slug="jp_cafe", name="Cafe")
    try:
        chars = repo.list_assets(kind="character", region="jp")
        assert any(x["id"] == a for x in chars) and all(x["kind"] == "character" for x in chars)
        assert not any(x["id"] == b for x in chars)     # background excluded
        # free-text q hits tags
        assert any(x["id"] == a for x in repo.list_assets(q="cafe"))
    finally:
        repo.delete_asset(a); repo.delete_asset(b)


def test_parse_path_conventions(tmp_path):
    root = tmp_path
    cases = {
        "character/cn/wuxia/cn_hero.png": ("character", "cn", "wuxia", ""),
        "background/jp/hiendai/jp_cafe.png": ("background", "jp", "hiendai", ""),
        "object/vi/vi_nonla.png": ("object", "vi", "", ""),
        "frame/wuxia/ink_corner.png": ("frame", "", "", "wuxia"),
    }
    for rel, (kind, region, genre, style) in cases.items():
        p = root / rel
        m = repo._parse_path(root, p)
        assert m and m["kind"] == kind and m["region"] == region
        assert m["genre"] == genre and m["style"] == style
    # unknown top-level kind → skipped
    assert repo._parse_path(root, root / "misc/foo.png") is None


def test_scan_library_indexes_and_prunes(tmp_path):
    root = tmp_path / "asset_library"
    # a character with a sidecar (license/tags override) + a background
    cdir = root / "character" / "cn" / "wuxia"
    cdir.mkdir(parents=True)
    (cdir / "cn_hero.png").write_bytes(b"\x89PNG")
    (cdir / "cn_hero.json").write_text(json.dumps({"license": "cc0", "tags": "sword,hero"}), encoding="utf-8")
    bdir = root / "background" / "jp" / "hiendai"
    bdir.mkdir(parents=True)
    (bdir / "jp_cafe.png").write_bytes(b"\x89PNG")

    res = repo.scan_library(root)
    assert res["indexed"] == 2
    hero = [a for a in repo.list_assets(kind="character") if a["slug"] == "cn_hero"]
    assert hero and hero[0]["license"] == "cc0" and "sword" in hero[0]["tags"]
    assert hero[0]["transparent"] is True          # character → transparent by convention
    bg = [a for a in repo.list_assets(kind="background") if a["slug"] == "jp_cafe"]
    assert bg and bg[0]["transparent"] is False

    # delete the file → rescan prunes the row
    (cdir / "cn_hero.png").unlink()
    res2 = repo.scan_library(root)
    assert res2["pruned"] >= 1
    assert not [a for a in repo.list_assets(kind="character") if a["slug"] == "cn_hero"]
    # cleanup rows from this test
    for a in repo.list_assets(kind="background"):
        if a["slug"] == "jp_cafe":
            repo.delete_asset(a["id"])


# ── AL2: API endpoints ────────────────────────────────────────────────────────

def test_endpoints_list_get_image_delete(tmp_path):
    f = tmp_path / "cn_hero.png"
    f.write_bytes(b"\x89PNG")
    aid = repo.upsert_asset(path=str(f), kind="character", region="cn", genre="wuxia",
                            slug="cn_hero_api", transparent=True)
    try:
        assert any(a["id"] == aid for a in list_story_assets(kind="character")["assets"])
        assert get_story_asset(aid)["slug"] == "cn_hero_api"
        resp = get_story_asset_image(aid)          # FileResponse over the real file
        assert getattr(resp, "path", "") == str(f)
    finally:
        delete_story_asset(aid)
    with pytest.raises(HTTPException) as ei:
        get_story_asset(aid)
    assert ei.value.status_code == 404


def test_scan_endpoint_indexes(tmp_path, monkeypatch):
    root = tmp_path / "asset_library"
    d = root / "character" / "jp" / "hiendai"
    d.mkdir(parents=True)
    (d / "jp_scan_test.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr("app.core.config.ASSET_LIBRARY_DIR", root, raising=False)
    res = scan_story_assets()
    assert res["indexed"] >= 1
    hit = [a for a in list_story_assets(kind="character")["assets"] if a["slug"] == "jp_scan_test"]
    assert hit
    repo.delete_asset(hit[0]["id"])


# ── AL5: match_asset (auto-assign) + asset_sources.json provenance manifest ────

def test_match_asset_ranks_by_name(tmp_path):
    f1 = tmp_path / "jp_haruto.png"; f1.write_bytes(b"\x89PNG")
    f2 = tmp_path / "jp_yuki.png"; f2.write_bytes(b"\x89PNG")
    a = repo.upsert_asset(path=str(f1), kind="character", region="jp", slug="jp_haruto",
                          name="Haruto", transparent=True)
    b = repo.upsert_asset(path=str(f2), kind="character", region="jp", slug="jp_yuki",
                          name="Yuki", transparent=True)
    try:
        assert repo.match_asset("character", "Haruto") == str(f1)     # exact name → that file
        assert repo.match_asset("character", "Yuki", transparent_only=True) == str(f2)
        assert repo.match_asset("character", "Nobody") is None        # no signal → None (no random sub)
        # kind scoping: a background never matches a character lookup
        assert repo.match_asset("background", "Haruto") is None
    finally:
        repo.delete_asset(a); repo.delete_asset(b)


def test_match_asset_scores_on_description(tmp_path):
    # F2 — the rich `description` field feeds ranking (a slug with no token overlap but a
    # descriptive phrase still matches). best_asset returns the row.
    f = tmp_path / "cn_wx_001.png"; f.write_bytes(b"\x89PNG")
    a = repo.upsert_asset(path=str(f), kind="character", region="cn", genre="wuxia",
                          slug="cn_wx_001", name="", transparent=True,
                          description="Chinese wuxia zephyrblade paladin young")  # unique token
    try:
        # "zephyrblade" appears ONLY in the description, not the slug/name.
        assert repo.match_asset("character", "zephyrblade", region="cn", genre="wuxia") == str(f)
        row = repo.best_asset("character", "young zephyrblade", region="cn", genre="wuxia")
        assert row is not None and row["slug"] == "cn_wx_001"
        # a token that matches nothing → None (no substitution)
        assert repo.match_asset("character", "qwzzxvorp", region="cn", genre="wuxia") is None
    finally:
        repo.delete_asset(a)


def test_match_asset_widens_scope(tmp_path):
    # F3 — a slightly-off region/genre no longer drops the only candidate: matching widens
    # region+genre → region → unscoped WHEN a name signal exists.
    f = tmp_path / "cn_hero_widen.png"; f.write_bytes(b"\x89PNG")
    a = repo.upsert_asset(path=str(f), kind="character", region="cn", genre="wuxia",
                          slug="cn_hero_widen", name="Widenhero", transparent=True)
    try:
        # asked for genre=xianxia (no candidate there) → widens to region cn → unscoped.
        assert repo.match_asset("character", "Widenhero", region="cn", genre="xianxia") == str(f)
        assert repo.match_asset("character", "Widenhero", region="zz", genre="zz") == str(f)
        # but a BLANK name stays strictly in scope (never cross-region substitutes).
        assert repo.match_asset("character", "", region="zz", genre="zz") is None
    finally:
        repo.delete_asset(a)


def test_match_asset_skips_missing_file(tmp_path):
    gone = tmp_path / "ghost.png"; gone.write_bytes(b"\x89PNG")
    a = repo.upsert_asset(path=str(gone), kind="character", slug="ghost", name="Ghost",
                          transparent=True)
    try:
        gone.unlink()                                    # row exists but file is gone
        assert repo.match_asset("character", "Ghost") is None
    finally:
        repo.delete_asset(a)


def test_scan_applies_sources_manifest(tmp_path):
    root = tmp_path / "asset_library"
    d = root / "background" / "jp" / "hiendai"
    d.mkdir(parents=True)
    (d / "jp_cafe.png").write_bytes(b"\x89PNG")          # no per-file sidecar
    cd = root / "character" / "cn" / "wuxia"
    cd.mkdir(parents=True)
    (cd / "cn_hero.png").write_bytes(b"\x89PNG")
    (cd / "cn_hero.json").write_text(json.dumps({"license": "cc0"}), encoding="utf-8")
    manifest = {"families": [
        {"match": {"kind": "background"}, "license": "cc0-openverse", "source": "openverse"},
    ]}
    (root / "asset_sources.json").write_text(json.dumps(manifest), encoding="utf-8")

    repo.scan_library(root)
    try:
        bg = [a for a in repo.list_assets(kind="background") if a["slug"] == "jp_cafe"][0]
        assert bg["license"] == "cc0-openverse" and bg["source"] == "openverse"   # manifest default
        hero = [a for a in repo.list_assets(kind="character") if a["slug"] == "cn_hero"][0]
        assert hero["license"] == "cc0"                  # sidecar still wins over manifest
    finally:
        for a in repo.list_assets():
            if a["slug"] in ("jp_cafe", "cn_hero"):
                repo.delete_asset(a["id"])
