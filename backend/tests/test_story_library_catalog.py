"""Library-pick B1 — get_by_slug + build_library_catalog (AI chooses assets by slug)."""
from __future__ import annotations

from app.db import story_asset_repo as R


def _png(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 512)
    return str(p)


def _seed(tmp_path):
    # base + an emotion variant + a background with a night variant
    R.upsert_asset(path=_png(tmp_path, "sw.png"), kind="character", region="cn", genre="wuxia",
                   slug="cn_wuxia_swordsman_male_young")
    R.upsert_asset(path=_png(tmp_path, "sw_angry.png"), kind="character", region="cn", genre="wuxia",
                   slug="cn_wuxia_swordsman_male_young_angry")
    R.upsert_asset(path=_png(tmp_path, "forest.png"), kind="background", region="cn", genre="wuxia",
                   slug="cn_wuxia_bamboo_forest")
    R.upsert_asset(path=_png(tmp_path, "forest_night.png"), kind="background", region="cn", genre="wuxia",
                   slug="cn_wuxia_bamboo_forest_night")


def test_get_by_slug_exact_and_scope(tmp_path):
    _seed(tmp_path)
    assert R.get_by_slug("cn_wuxia_swordsman_male_young", "character")
    assert R.get_by_slug("cn_wuxia_bamboo_forest", "background")
    assert R.get_by_slug("cn_wuxia_swordsman_male_young", "background") is None   # kind scope
    assert R.get_by_slug("does_not_exist") is None
    assert R.get_by_slug("") is None


def test_get_by_slug_none_when_file_gone(tmp_path):
    p = _png(tmp_path, "gone.png")
    R.upsert_asset(path=p, kind="character", region="jp", genre="hiendai", slug="jp_hiendai_ghost_x")
    import os; os.remove(p)
    assert R.get_by_slug("jp_hiendai_ghost_x", "character") is None               # file removed → None


def test_build_catalog_groups_variants(tmp_path):
    _seed(tmp_path)
    cat = R.build_library_catalog()
    assert "CHARACTERS" in cat and "BACKGROUNDS" in cat
    # base slug present ONCE with its emotions collapsed (no separate _angry line)
    assert "cn_wuxia_swordsman_male_young " in cat
    assert "cn_wuxia_swordsman_male_young_angry" not in cat
    assert "emotions:angry" in cat
    assert "cn_wuxia_bamboo_forest " in cat and "night" in cat
    # readable role tokens (region/genre stripped)
    assert "swordsman male young" in cat


def test_build_catalog_empty_when_no_assets(monkeypatch):
    monkeypatch.setattr(R, "list_assets", lambda **k: [])
    assert R.build_library_catalog() == ""


def test_catalog_uses_authored_description(monkeypatch, tmp_path):
    # A sidecar/authored description is shown verbatim in the catalog (beats slug tokens).
    monkeypatch.setattr(R, "list_assets", lambda kind="", **k: (
        [{"slug": "cn_wuxia_swordsman_male_young", "region": "cn", "genre": "wuxia", "style": "",
          "description": "young hero in a white robe with a jade jian"}] if kind == "character" else []))
    cat = R.build_library_catalog()
    assert "young hero in a white robe with a jade jian" in cat


def test_catalog_derives_readable_desc(monkeypatch):
    # No authored desc → region/genre expanded to readable words + role tokens.
    monkeypatch.setattr(R, "list_assets", lambda kind="", **k: (
        [{"slug": "cn_wuxia_swordsman_male_young", "region": "cn", "genre": "wuxia", "style": "",
          "description": ""}] if kind == "character" else []))
    cat = R.build_library_catalog()
    assert "Chinese wuxia swordsman male young" in cat


def test_scan_reads_sidecar_desc(tmp_path):
    # end-to-end: a {file}.json sidecar with "desc" lands in the DB + catalog.
    import json
    d = tmp_path / "character" / "cn" / "wuxia"
    d.mkdir(parents=True)
    (d / "cn_wuxia_hero_x.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 256)
    (d / "cn_wuxia_hero_x.png.json").write_text(json.dumps({"desc": "a lone masked ronin"}), encoding="utf-8")
    R.scan_library(root=tmp_path)
    assert "a lone masked ronin" in R.build_library_catalog(region="cn", genre="wuxia")


def test_migration_0025_adds_description_column():
    from app.db.connection import db_conn
    with db_conn() as c:
        cols = {row[1] for row in c.execute("PRAGMA table_info(story_assets)").fetchall()}
    assert "description" in cols                          # additive migration applied
