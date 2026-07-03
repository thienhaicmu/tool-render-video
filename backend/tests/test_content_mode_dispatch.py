"""test_content_mode_dispatch.py — Content Mode wiring (Phase 3, no ffmpeg/DB).

Covers the additive surface that ACTIVATES Content Mode:
  - render_format="content" routes process_render → run_content (clips/recap
    paths untouched) — Sacred Contract #4 discriminator.
  - RenderRequest backward-compat + Sacred Contract #2: content fields default
    to an inert state; render_format + content field validators coerce (never
    raise) so stored payloads replay cleanly.
  - engine.visual provider seam: resolve_scene_visual('local') + fallbacks.
"""
from __future__ import annotations

import pytest

from app.models.schemas import RenderRequest


# ── Dispatch routing (process_render) ────────────────────────────────────────

def _route(monkeypatch, render_format: str, **extra) -> str:
    """Run process_render with the three orchestrators stubbed; return which one
    was invoked ('content' | 'recap' | 'clips')."""
    from app.features.render.routers import _common
    import app.features.render.engine.pipeline.content_pipeline as cp
    import app.features.render.engine.pipeline.recap_pipeline as rp

    hit: dict[str, bool] = {}
    monkeypatch.setattr(cp, "run_content", lambda **k: hit.__setitem__("content", True))
    monkeypatch.setattr(rp, "run_recap", lambda **k: hit.__setitem__("recap", True))
    monkeypatch.setattr(_common, "run_render_pipeline", lambda **k: hit.__setitem__("clips", True))

    payload = RenderRequest(render_format=render_format, output_dir="", **extra)
    _common.process_render(f"job-{render_format}", payload)
    assert len(hit) == 1, f"exactly one orchestrator must run, got {hit}"
    return next(iter(hit))


def test_content_routes_to_run_content(monkeypatch):
    assert _route(monkeypatch, "content", content_script="hello") == "content"


def test_recap_still_routes_to_run_recap(monkeypatch):
    assert _route(monkeypatch, "recap") == "recap"


def test_clips_still_routes_to_run_render_pipeline(monkeypatch):
    assert _route(monkeypatch, "clips") == "clips"


def test_unknown_format_falls_back_to_clips(monkeypatch):
    # Sacred Contract #2: an unknown/stale render_format coerces to "clips".
    assert _route(monkeypatch, "totally-bogus") == "clips"


# ── RenderRequest backward-compat + Sacred Contract #2 ───────────────────────

def test_render_format_normalisation():
    assert RenderRequest(output_dir="").render_format == "clips"            # default
    assert RenderRequest(render_format="content", output_dir="").render_format == "content"
    assert RenderRequest(render_format="CONTENT", output_dir="").render_format == "content"
    assert RenderRequest(render_format=" Content ", output_dir="").render_format == "content"
    assert RenderRequest(render_format="bogus", output_dir="").render_format == "clips"
    assert RenderRequest(render_format=None, output_dir="").render_format == "clips"


def test_content_fields_default_inert():
    r = RenderRequest(output_dir="")
    assert r.content_script == ""
    assert r.content_background_kind == "color"
    assert r.content_background_value == "#000000"
    assert r.content_bgm_path == ""
    assert r.content_visual_provider == "local"


def test_content_field_validators_coerce():
    assert RenderRequest(content_background_kind="IMAGE", output_dir="").content_background_kind == "image"
    assert RenderRequest(content_background_kind="Video", output_dir="").content_background_kind == "video"
    assert RenderRequest(content_background_kind="bogus", output_dir="").content_background_kind == "color"
    assert RenderRequest(content_background_kind=None, output_dir="").content_background_kind == "color"
    # engine.visual providers: local (offline) | stock | ai_image (CS-G, online).
    assert RenderRequest(content_visual_provider="ai_image", output_dir="").content_visual_provider == "ai_image"
    assert RenderRequest(content_visual_provider="STOCK", output_dir="").content_visual_provider == "stock"
    assert RenderRequest(content_visual_provider="LOCAL", output_dir="").content_visual_provider == "local"
    # Unknown/future provider still coerces to local (never raises).
    assert RenderRequest(content_visual_provider="midjourney", output_dir="").content_visual_provider == "local"


def test_content_fields_are_fe_facing():
    # Phase 4 (MT-3 coordinated migration): the 5 content fields are promoted to
    # the FE wire surface together with api.ts so the Content tab can send them.
    from app.models.render_public import FE_FACING_FIELDS, BE_ONLY_FIELDS
    for f in ("content_script", "content_background_kind", "content_background_value",
              "content_bgm_path", "content_visual_provider"):
        assert f in FE_FACING_FIELDS, f"{f} must be FE-facing after Phase 4"
        assert f not in BE_ONLY_FIELDS, f"{f} must NOT also be BE-only (partition)"


# ── engine.visual provider seam ──────────────────────────────────────────────

def _req(**kw):
    from app.features.render.engine.visual import SceneVisualRequest
    base = dict(scene_index=0, kind="color", value="#123456", prompt="",
                width=320, height=568, fps=30.0, duration_sec=3.0, work_dir=".")
    base.update(kw)
    return SceneVisualRequest(**base)


def test_visual_local_passthrough():
    from app.features.render.engine.visual import resolve_scene_visual
    a = resolve_scene_visual(_req(kind="color", value="#123456"), provider="local")
    assert a is not None and a.kind == "color" and a.value == "#123456" and a.provider == "local"


def test_visual_missing_image_degrades_to_color(tmp_path):
    from app.features.render.engine.visual import resolve_scene_visual
    a = resolve_scene_visual(
        _req(kind="image", value=str(tmp_path / "nope.png"), work_dir=str(tmp_path)),
        provider="local",
    )
    assert a is not None and a.kind == "color" and a.value == "#000000"


def test_visual_unknown_provider_falls_back_to_local():
    from app.features.render.engine.visual import resolve_scene_visual
    a = resolve_scene_visual(_req(), provider="ai_image")  # not shipped in v1
    assert a is not None and a.provider == "local"
