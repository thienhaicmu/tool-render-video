"""Story-to-Video P3 — Character Reference Sheet module + endpoint tests (offline)."""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.db.connection import init_db
from app.db import story_repo
from app.domain.story_plan import StoryCharacter
from app.features.render.engine.visual import story_reference_sheet as rs
from app.features.story import router as story_router
from app.features.story.router import ReferenceSheetRequest, character_reference_sheet


def setup_module(module):  # noqa: D401
    init_db()


# ── module ────────────────────────────────────────────────────────────────────

def test_generate_writes_durable_path(monkeypatch):
    monkeypatch.setattr(rs, "generate_image_bytes", lambda *a, **k: b"\x89PNG_sheet")
    char = StoryCharacter(id="han_phong", name="Hàn Phong", description="áo trắng, kiếm bạc")
    path = rs.generate_character_reference_sheet(char, art_style="wuxia")
    assert path and path.endswith(".png")
    from pathlib import Path
    assert Path(path).exists() and Path(path).read_bytes() == b"\x89PNG_sheet"


def test_generate_none_when_no_data(monkeypatch):
    monkeypatch.setattr(rs, "generate_image_bytes", lambda *a, **k: None)
    assert rs.generate_character_reference_sheet(
        StoryCharacter(id="x", description="desc")) is None


def test_generate_none_when_no_description():
    assert rs.generate_character_reference_sheet(StoryCharacter(id="x")) is None


# ── C3 cost knob: STORY_REFSHEET_QUALITY ──────────────────────────────────────

def test_refsheet_quality_default_and_override(monkeypatch):
    monkeypatch.delenv("STORY_REFSHEET_QUALITY", raising=False)
    assert rs._refsheet_quality() == "high"          # historical default
    monkeypatch.setenv("STORY_REFSHEET_QUALITY", "medium")
    assert rs._refsheet_quality() == "medium"
    monkeypatch.setenv("STORY_REFSHEET_QUALITY", "bogus")
    assert rs._refsheet_quality() == "high"          # invalid → default


def test_refsheet_quality_passed_and_cache_namespaced(monkeypatch):
    cap = {}

    def _gen(*a, **k):
        cap["q"] = k.get("quality")
        return b"\x89PNG_sheet"
    monkeypatch.setattr(rs, "generate_image_bytes", _gen)
    # Unique subject so we never collide with a sheet cached by another run.
    char = StoryCharacter(id="cost_knob_" + uuid.uuid4().hex[:8],
                          name="X", description="unique-" + uuid.uuid4().hex)

    monkeypatch.setenv("STORY_REFSHEET_QUALITY", "medium")
    p_med = rs.generate_character_reference_sheet(char, art_style="wuxia")
    assert cap["q"] == "medium"

    monkeypatch.setenv("STORY_REFSHEET_QUALITY", "high")
    p_high = rs.generate_character_reference_sheet(char, art_style="wuxia")
    assert cap["q"] == "high"

    # Same subject, different tier → different cache file (no cross-tier reuse).
    assert p_med and p_high and p_med != p_high


# ── G6: environment reference sheet ───────────────────────────────────────────

def test_env_reference_sheet_writes_durable_path(monkeypatch):
    from app.domain.story_plan_v2 import SettingDef
    monkeypatch.setattr(rs, "generate_image_bytes", lambda *a, **k: b"\x89PNG_env")
    s = SettingDef(id="hall_" + uuid.uuid4().hex[:6], name="Cloud Hall",
                   canonical_desc="cold stone hall, tall pillars")
    path = rs.generate_environment_reference_sheet(s, art_style="wuxia")
    assert path and path.endswith(".png") and "envsheet_" in path
    from pathlib import Path
    assert Path(path).exists() and Path(path).read_bytes() == b"\x89PNG_env"


def test_env_reference_sheet_none_without_desc():
    from app.domain.story_plan_v2 import SettingDef
    assert rs.generate_environment_reference_sheet(SettingDef(id="x")) is None


# ── endpoint ──────────────────────────────────────────────────────────────────

def test_endpoint_422_without_description():
    with pytest.raises(HTTPException) as ei:
        character_reference_sheet(ReferenceSheetRequest())
    assert ei.value.status_code == 422


def test_endpoint_502_when_generation_fails(monkeypatch):
    monkeypatch.setattr(rs, "generate_character_reference_sheet", lambda *a, **k: None)
    with pytest.raises(HTTPException) as ei:
        character_reference_sheet(ReferenceSheetRequest(description="áo trắng"))
    assert ei.value.status_code == 502


# ── Phase 5: cutout-ready character master (transparent) ──────────────────────

def test_master_writes_durable_transparent(monkeypatch):
    cap = {}

    def _gen(*a, **k):
        cap["bg"] = k.get("background")
        return b"\x89PNG_master"
    monkeypatch.setattr(rs, "generate_image_bytes", _gen)
    char = StoryCharacter(id="mst_" + uuid.uuid4().hex[:8], name="X",
                          description="unique-" + uuid.uuid4().hex)
    path = rs.generate_character_master(char, art_style="wuxia")
    assert path and "master_" in path and path.endswith(".png")
    assert cap["bg"] == "transparent"          # cutout handled at the generation call
    from pathlib import Path
    assert Path(path).read_bytes() == b"\x89PNG_master"


def test_master_none_when_no_description():
    assert rs.generate_character_master(StoryCharacter(id="x")) is None


def test_master_cache_hit_second_call(monkeypatch):
    calls = {"n": 0}

    def _gen(*a, **k):
        calls["n"] += 1
        return b"\x89PNG_master"
    monkeypatch.setattr(rs, "generate_image_bytes", _gen)
    char = StoryCharacter(id="c", name="X", description="cache-" + uuid.uuid4().hex)
    p1 = rs.generate_character_master(char)
    p2 = rs.generate_character_master(char)
    assert p1 == p2 and calls["n"] == 1        # second call served from cache (no API)


def test_master_variant_busts_cache(monkeypatch):
    calls = {"n": 0}

    def _gen(*a, **k):
        calls["n"] += 1
        return b"\x89PNG_master"
    monkeypatch.setattr(rs, "generate_image_bytes", _gen)
    char = StoryCharacter(id="v", name="X", description="variant-" + uuid.uuid4().hex)
    p0 = rs.generate_character_master(char)               # variant 0 (canonical)
    p1 = rs.generate_character_master(char, variant=1)    # A5: a different look
    assert p0 and p1 and p0 != p1 and calls["n"] == 2     # variant busts the cache
    rs.generate_character_master(char)                    # variant 0 again → cache hit
    assert calls["n"] == 2


def test_endpoint_transparent_passes_variant(monkeypatch, tmp_path):
    src = tmp_path / "m.png"
    src.write_bytes(b"\x89PNG")
    cap = {}

    def _fake(character, art_style="", variant=0):
        cap["variant"] = variant
        return str(src)
    monkeypatch.setattr(rs, "generate_character_master", _fake)
    character_reference_sheet(ReferenceSheetRequest(description="áo trắng", transparent=True, variant=3))
    assert cap["variant"] == 3


def test_endpoint_transparent_returns_url(monkeypatch, tmp_path):
    src = tmp_path / "m.png"
    src.write_bytes(b"\x89PNG")                 # real file so the preview copy succeeds
    monkeypatch.setattr(rs, "generate_character_master", lambda *a, **k: str(src))
    out = character_reference_sheet(ReferenceSheetRequest(description="áo trắng", transparent=True))
    assert out["path"] == str(src)
    assert out["url"].startswith("/api/story/character/master/")


def test_endpoint_generates_and_pins_to_character(monkeypatch):
    sid = "test-story-rs-" + uuid.uuid4().hex[:8]
    cid = sid + "-c"
    fake_path = f"/fake/assets/{cid}.png"
    monkeypatch.setattr(rs, "generate_character_reference_sheet", lambda *a, **k: fake_path)
    try:
        story_repo.upsert_series(sid, title="S")
        story_repo.upsert_character(cid, series_id=sid, name="Hàn Phong", canonical_desc="áo trắng")
        out = character_reference_sheet(ReferenceSheetRequest(
            series_id=sid, character_id=cid, art_style="wuxia",
        ))
        assert out["path"] == fake_path
        # Pinned on the character.
        row = story_repo.get_character(cid)
        assert row["reference_image_path"] == fake_path
    finally:
        story_repo.delete_series(sid)
