"""test_content_visual_fallback.py — Phase B2 stepped visual fallback + B1 seed.

B2: when the chosen image provider yields nothing, resolve_scene_visual tries the
other FREE real-image providers (Pollinations / stock) BEFORE the plain local
background — so a 429 / missing key / error keeps a real image. ai_video is
excluded (video failure → local). A kill-switch restores the old behaviour.

B1: the per-scene seed always resolves to a non-zero, stable value (character →
video_style → topic) so a character-less scene still has a coherent look.
"""
from __future__ import annotations

import app.features.render.engine.visual as visual
from app.features.render.engine.visual import (
    SceneVisualAsset, SceneVisualRequest, resolve_scene_visual,
)


def _req(kind="color", value="#101820", prompt="a castle at dawn"):
    return SceneVisualRequest(
        scene_index=1, kind=kind, value=value, prompt=prompt,
        width=768, height=1344, fps=30.0, duration_sec=3.0, work_dir="/tmp",
    )


# ── B2 stepped fallback ──────────────────────────────────────────────────────

def test_fallback_primary_fails_uses_free_pool(monkeypatch):
    calls = []

    def _stub(provider, request):
        calls.append(provider)
        if provider == "stock":
            return SceneVisualAsset(kind="image", value="/x.jpg", provider="stock")
        return None  # ai_image_free (primary + pool) fails

    monkeypatch.setattr(visual, "_resolve_one", _stub)
    asset = resolve_scene_visual(_req(), provider="ai_image_free")
    assert asset is not None and asset.provider == "stock"
    # primary ai_image_free (None) → pool skips itself → stock (ok)
    assert calls == ["ai_image_free", "stock"], calls


def test_paid_provider_falls_back_to_free(monkeypatch):
    # Option (1): a paid Imagen failure still tries the free real-image pool.
    calls = []

    def _stub(provider, request):
        calls.append(provider)
        if provider == "ai_image_free":
            return SceneVisualAsset(kind="image", value="/p.jpg", provider="ai_image_free")
        return None

    monkeypatch.setattr(visual, "_resolve_one", _stub)
    asset = resolve_scene_visual(_req(), provider="ai_image")
    assert asset is not None and asset.provider == "ai_image_free"
    assert calls == ["ai_image", "ai_image_free"], calls


def test_all_fail_returns_local(monkeypatch):
    monkeypatch.setattr(visual, "_resolve_one", lambda p, r: None)
    asset = resolve_scene_visual(_req(), provider="ai_image")
    assert asset is not None and asset.provider == "local"


def test_ai_video_failure_skips_image_pool(monkeypatch):
    calls = []

    def _stub(provider, request):
        calls.append(provider)
        return None

    monkeypatch.setattr(visual, "_resolve_one", _stub)
    asset = resolve_scene_visual(_req(), provider="ai_video")
    assert asset is not None and asset.provider == "local"
    assert calls == ["ai_video"], calls   # video → straight to local, no image pool


def test_fallback_kill_switch(monkeypatch):
    calls = []

    def _stub(provider, request):
        calls.append(provider)
        return None

    monkeypatch.setattr(visual, "_resolve_one", _stub)
    monkeypatch.setattr(visual, "_CONTENT_VISUAL_FALLBACK", False)
    asset = resolve_scene_visual(_req(), provider="ai_image_free")
    assert asset is not None and asset.provider == "local"
    assert calls == ["ai_image_free"], calls   # no pool when disabled


def test_resolve_one_routes_to_provider(monkeypatch):
    import app.features.render.engine.visual.provider_pollinations as poll
    monkeypatch.setattr(
        poll, "resolve_pollinations",
        lambda req: SceneVisualAsset(kind="image", value="/p.jpg", provider="ai_image_free"),
    )
    got = visual._resolve_one("ai_image_free", _req())
    assert got is not None and got.provider == "ai_image_free"
    assert visual._resolve_one("unknown_provider", _req()) is None


# ── B1 seed coherence ────────────────────────────────────────────────────────

def test_seed_stable_and_nonzero_from_topic():
    from app.features.render.engine.pipeline.content_pipeline import _stable_seed
    s = _stable_seed("Ancient Rome")
    assert s > 0
    assert _stable_seed("Ancient Rome") == s   # deterministic
    assert _stable_seed("") == 0               # empty → 0 (provider random)
