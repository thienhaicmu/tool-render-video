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
