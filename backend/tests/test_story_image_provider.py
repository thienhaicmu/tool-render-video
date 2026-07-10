"""Story Mode v2 — Phase 2: image provider dispatch (gpt_image | pollinations).

Covers the draft/final split: the FINAL provider comes from the validated
RenderRequest field (default gpt_image = paid, Sacred #2), the Storyboard preview
defaults to the FREE provider, and generate_visual_image routes to the right backend.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain.story_plan_v2 import Visual


# ── field default + validator (Sacred #2) ────────────────────────────────────

def test_render_request_field_default_and_coercion():
    from app.models.render import RenderRequest
    assert RenderRequest().story_image_provider == "gpt_image"          # default = paid = replay-safe
    assert RenderRequest(story_image_provider="pollinations").story_image_provider == "pollinations"
    assert RenderRequest(story_image_provider="BANANA").story_image_provider == "gpt_image"  # unknown → default
    assert RenderRequest(story_image_provider="").story_image_provider == "gpt_image"


# ── generate_visual_image dispatch ───────────────────────────────────────────

def test_generate_visual_image_routes_to_pollinations(monkeypatch, tmp_path):
    from app.features.render.engine.visual import story_image
    import app.features.render.engine.visual.provider_pollinations as poll

    src = tmp_path / "free.jpg"
    src.write_bytes(b"\xff\xd8\xff" + b"0" * 2048)   # non-empty fake jpg
    calls = {}

    def fake_resolve(req):
        calls["prompt"] = req.prompt
        calls["seed"] = req.seed
        return SimpleNamespace(value=str(src), kind="image", provider="ai_image_free")

    monkeypatch.setattr(poll, "resolve_pollinations", fake_resolve)
    out = tmp_path / "v1.png"
    v = Visual(id="v1", prompt="a wide cold hall", tier="high")
    res = story_image.generate_visual_image(v, {}, "wuxia", 1536, 1024, str(out),
                                            seed=7, provider="pollinations")
    assert res == str(out)
    assert out.exists() and out.stat().st_size > 0
    assert calls["prompt"] == "a wide cold hall"       # raw prompt handed to the free provider
    assert calls["seed"] == 7


def test_generate_visual_image_routes_to_gpt_image(monkeypatch, tmp_path):
    from app.features.render.engine.visual import story_image

    seen = {}

    def fake_bytes(prompt, w, h, quality="medium", reference_paths=None, negative=""):
        seen["called"] = True
        return b"PNGDATA" * 500

    # gpt path calls generate_image_bytes; pollinations must NOT be touched here.
    monkeypatch.setattr(story_image, "generate_image_bytes", fake_bytes)
    out = tmp_path / "v2.png"
    import uuid
    v = Visual(id="v2", prompt=f"hero portrait {uuid.uuid4().hex}", tier="medium")  # unique → no cache hit
    res = story_image.generate_visual_image(v, {}, "", 1024, 1024, str(out),
                                            seed=0, provider="gpt_image")
    assert seen.get("called") is True
    assert res == str(out) and out.exists()


def test_pollinations_none_when_provider_returns_nothing(monkeypatch, tmp_path):
    from app.features.render.engine.visual import story_image
    import app.features.render.engine.visual.provider_pollinations as poll
    monkeypatch.setattr(poll, "resolve_pollinations", lambda req: None)  # network fail → None
    v = Visual(id="v3", prompt="x", tier="low")
    res = story_image.generate_visual_image(v, {}, "", 1024, 1024, str(tmp_path / "v3.png"),
                                            provider="pollinations")
    assert res is None   # → caller falls back to a solid background (Sacred #3)


# ── preview endpoint defaults to the FREE provider ───────────────────────────

def test_preview_endpoint_defaults_to_free_provider(monkeypatch):
    from app.features.story import router as story_router
    from app.features.render.engine.visual import story_image

    captured = {}

    def fake_gen(visual, refs, art_style, w, h, out_path, provider="gpt_image", **kw):
        captured["provider"] = provider
        from pathlib import Path
        Path(out_path).write_bytes(b"0" * 4096)
        return out_path

    # The handler does a call-time `from ...story_image import generate_visual_image`,
    # so patch the source symbol.
    monkeypatch.setattr(story_image, "generate_visual_image", fake_gen)
    req = story_router.StoryVisualPreviewRequest(prompt="a scene")
    assert req.provider == "pollinations"                 # default = free
    resp = story_router.visual_preview(req)
    assert "token" in resp and "url" in resp
    assert captured["provider"] == "pollinations"


def test_preview_endpoint_rejects_empty_prompt():
    from fastapi import HTTPException
    from app.features.story import router as story_router
    with pytest.raises(HTTPException) as ei:
        story_router.visual_preview(story_router.StoryVisualPreviewRequest(prompt="  "))
    assert ei.value.status_code == 422
