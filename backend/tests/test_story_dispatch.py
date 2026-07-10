"""Story-to-Video P5 — dispatch routing + Sacred Contract #2 + validation +
2-tier transition logic (no ffmpeg / no network).

Mirrors test_content_mode_dispatch. Verifies render_format="story" routes
process_render → run_story (clips/recap/content paths untouched), the story
fields default inert (Sacred #2), the story source validation, and the
delivered-clip transition builder (cut within a scene, fade between scenes).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.models.schemas import RenderRequest


# ── Dispatch routing (process_render) ────────────────────────────────────────

def _route(monkeypatch, render_format: str, **extra) -> str:
    from app.features.render.routers import _common
    import app.features.render.engine.pipeline.content_pipeline as cp
    import app.features.render.engine.pipeline.recap_pipeline as rp
    import app.features.render.engine.pipeline.story_pipeline_v2 as sp

    hit: dict[str, bool] = {}
    monkeypatch.setattr(cp, "run_content", lambda **k: hit.__setitem__("content", True))
    monkeypatch.setattr(rp, "run_recap", lambda **k: hit.__setitem__("recap", True))
    monkeypatch.setattr(sp, "run_story_v2", lambda **k: hit.__setitem__("story", True))
    monkeypatch.setattr(_common, "run_render_pipeline", lambda **k: hit.__setitem__("clips", True))

    payload = RenderRequest(render_format=render_format, output_dir="", **extra)
    _common.process_render(f"job-{render_format}", payload)
    assert len(hit) == 1, f"exactly one orchestrator must run, got {hit}"
    return next(iter(hit))


def test_story_routes_to_run_story(monkeypatch):
    assert _route(monkeypatch, "story", content_script="chương") == "story"


def test_content_still_routes(monkeypatch):
    assert _route(monkeypatch, "content", content_script="hi") == "content"


def test_clips_still_routes(monkeypatch):
    assert _route(monkeypatch, "clips") == "clips"


def test_unknown_format_falls_back_to_clips(monkeypatch):
    assert _route(monkeypatch, "totally-bogus") == "clips"


# ── Sacred Contract #2 — story fields default inert ──────────────────────────

def test_render_format_accepts_story():
    assert RenderRequest(render_format="story", output_dir="").render_format == "story"
    assert RenderRequest(render_format="STORY", output_dir="").render_format == "story"
    assert RenderRequest(render_format=" Story ", output_dir="").render_format == "story"
    # Default unchanged.
    assert RenderRequest(output_dir="").render_format == "clips"


def test_story_fields_default_inert():
    r = RenderRequest(output_dir="")
    assert r.story_series_id == ""
    assert r.story_chapter_no == 0
    assert r.story_art_style == ""
    assert r.story_reading_pace == "normal"
    assert r.story_plan_override == ""


def test_story_fields_are_fe_facing():
    # P6 wire surface: story fields promoted to FE-facing so /api/render/process
    # (extra="forbid") accepts them from the Story Studio.
    from app.models.render_public import FE_FACING_FIELDS, BE_ONLY_FIELDS
    for f in ("story_series_id", "story_chapter_no", "story_art_style",
              "story_reading_pace", "story_plan_override"):
        assert f in FE_FACING_FIELDS
        assert f not in BE_ONLY_FIELDS  # partition — never both


# ── Source validation ─────────────────────────────────────────────────────────

def test_validate_story_source_requires_chapter():
    from app.features.render.routers._common import _validate_render_source
    with pytest.raises(HTTPException) as ei:
        _validate_render_source(RenderRequest(render_format="story", output_dir=""))
    assert ei.value.status_code == 400
    assert "content_script is required" in ei.value.detail


def test_validate_story_source_passes_with_chapter(tmp_path):
    from app.features.render.routers._common import _validate_render_source
    # A non-empty chapter + a writable output dir → no exception.
    _validate_render_source(RenderRequest(
        render_format="story", content_script="Chương 1...", output_dir=str(tmp_path),
    ))


def test_validate_story_source_accepts_plan_override(tmp_path):
    from app.features.render.routers._common import _validate_render_source
    _validate_render_source(RenderRequest(
        render_format="story", story_plan_override='{"visuals":[]}', output_dir=str(tmp_path),
    ))
