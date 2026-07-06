"""test_content_pollinations.py — P3.2-alt free AI image (Pollinations) + wiring.

Covers the new ``ai_image_free`` visual provider end to end at the seam level:
  - schema validator now accepts "ai_image_free" (Sacred Contract #2 additive).
  - registry manifest: online, NO key, free.
  - decision tree: cost 0 + routes an ai_image_free scene through unchanged.
  - resolve_pollinations: sends the scene's story-grounded visual_prompt in the
    URL, returns an image asset; empty prompt / download failure → None.
  - resolve_scene_visual dispatches "ai_image_free" → Pollinations, and falls
    back to local on failure.
"""
from __future__ import annotations

import types
from pathlib import Path

import pytest

import app.features.render.engine.visual.provider_pollinations as poll
from app.features.render.engine.visual import SceneVisualRequest, resolve_scene_visual


def _req(prompt="A photoreal red apple on a table", w=768, h=1344, seed=7,
         kind="color", value="#000000", **kw):
    return SceneVisualRequest(
        scene_index=1, kind=kind, value=value, prompt=prompt,
        width=w, height=h, fps=30.0, duration_sec=3.0, work_dir="/tmp", seed=seed, **kw,
    )


# ── schema / registry / decision ─────────────────────────────────────────────

def test_validator_accepts_ai_image_free():
    from app.models.render import RenderRequest
    r = RenderRequest(output_dir="", content_visual_provider="ai_image_free")
    assert r.content_visual_provider == "ai_image_free"
    # a genuinely unknown value still coerces to local (Sacred Contract #2)
    assert RenderRequest(output_dir="", content_visual_provider="nope").content_visual_provider == "local"


def test_registry_manifest_free_no_key():
    from app.features.render.engine.visual.registry import get_manifest
    m = get_manifest("ai_image_free")
    assert m.name == "ai_image_free" and m.online is True and m.needs_key is False


def test_decision_cost_zero_and_routes():
    from app.features.render.engine.visual.decision import estimate_cost, decide_provider, BudgetTracker
    assert estimate_cost("ai_image_free") == 0.0
    scene = types.SimpleNamespace(visual_source="", visual_prompt="a castle at dawn",
                                  visual_hint="", asset_suggestion="ai_image")
    assert decide_provider(scene, "ai_image_free", BudgetTracker(0), 3.0) == "ai_image_free"


# ── resolve_pollinations ─────────────────────────────────────────────────────

def test_pollinations_sends_story_prompt_and_returns_asset(monkeypatch, tmp_path):
    captured = {}

    def _fake_dl(url, out, timeout=90):
        captured["url"] = url
        Path(out).write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        return True

    monkeypatch.setattr(poll, "visual_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(poll, "download_to", _fake_dl)
    asset = poll.resolve_pollinations(_req(prompt="Napoleon on horseback at Waterloo"))
    assert asset is not None
    assert asset.kind == "image" and asset.provider == "ai_image_free"
    assert Path(asset.value).exists()
    # Story fidelity: the scene's visual_prompt must be in the generated URL.
    assert "Napoleon" in captured["url"] and "Waterloo" in captured["url"]


def test_pollinations_empty_prompt_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(poll, "visual_cache_dir", lambda: tmp_path)
    assert poll.resolve_pollinations(_req(prompt="   ")) is None


def test_pollinations_download_failure_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(poll, "visual_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(poll, "download_to", lambda *a, **k: False)
    assert poll.resolve_pollinations(_req()) is None


# ── seam dispatch ────────────────────────────────────────────────────────────

def test_seam_dispatches_ai_image_free(monkeypatch, tmp_path):
    monkeypatch.setattr(poll, "visual_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(poll, "download_to",
                        lambda url, out, timeout=90: (Path(out).write_bytes(b"\xff\xd8ok") or True))
    asset = resolve_scene_visual(_req(), provider="ai_image_free")
    assert asset is not None and asset.provider == "ai_image_free"


def test_seam_falls_back_to_local_on_pollinations_failure(monkeypatch):
    # Pollinations returns None (e.g. network down) → seam yields the local asset.
    monkeypatch.setattr(poll, "resolve_pollinations", lambda req: None)
    asset = resolve_scene_visual(_req(kind="color", value="#101820"), provider="ai_image_free")
    assert asset is not None and asset.provider == "local"
