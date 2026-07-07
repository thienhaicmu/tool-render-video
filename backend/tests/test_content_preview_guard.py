"""test_content_preview_guard.py — CM-1 preview cost / abuse guard.

The /visual/preview + /narration/preview endpoints are unauthenticated (loopback)
and a visual preview can trigger a PAID provider call (Imagen/Veo). CM-1 adds:
  1. a shared per-minute rate limit (abuse / runaway loops),
  2. a per-day cap on PAID visual previews (accidental spend),
  3. a hard off-switch for paid previews.
These tests drive the guard through the real endpoints (resolve_scene_visual is
mocked so the network is never touched).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.features.content.router as mod
from app.features.content.router import router
from app.features.render.engine.visual import SceneVisualAsset


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _fresh_guard(monkeypatch):
    """Replace the module-level guard with a pristine one so per-test counters
    don't leak across tests (the guard is process-global by design)."""
    monkeypatch.setattr(mod, "_preview_guard", mod._PreviewGuard(), raising=True)


def _mock_visual(monkeypatch, tmp_path, provider="ai_image"):
    # ``provider`` here is the RESOLVED asset's provider (what actually produced
    # it) — pinned in a distinct name so the mock ignores the request's provider
    # kwarg and can simulate a silent fallback (request ai_image → asset local).
    asset_provider = provider
    monkeypatch.setattr(mod, "_VISUAL_PREVIEW_DIR", tmp_path / "vp", raising=False)
    src = tmp_path / "gen.jpg"
    src.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    monkeypatch.setattr(
        "app.features.render.engine.visual.resolve_scene_visual",
        lambda request, provider="": SceneVisualAsset(kind="image", value=str(src), provider=asset_provider),
    )


def test_rate_limit_blocks_after_cap(monkeypatch, tmp_path):
    _fresh_guard(monkeypatch)
    _mock_visual(monkeypatch, tmp_path, provider="ai_image_free")
    monkeypatch.setattr(mod, "_PREVIEW_RATE_PER_MIN", 3, raising=True)
    monkeypatch.setattr(mod, "_PREVIEW_DAILY_CAP", 0, raising=True)  # cap off
    c = _client()
    body = {"prompt": "a castle", "provider": "ai_image_free"}
    for _ in range(3):
        assert c.post("/api/content/visual/preview", json=body).status_code == 200
    # 4th call in the same minute is rejected.
    r = c.post("/api/content/visual/preview", json=body)
    assert r.status_code == 429
    assert "rate limit" in r.json()["detail"].lower()


def test_rate_limit_disabled_when_zero(monkeypatch, tmp_path):
    _fresh_guard(monkeypatch)
    _mock_visual(monkeypatch, tmp_path, provider="ai_image_free")
    monkeypatch.setattr(mod, "_PREVIEW_RATE_PER_MIN", 0, raising=True)  # unlimited
    monkeypatch.setattr(mod, "_PREVIEW_DAILY_CAP", 0, raising=True)
    c = _client()
    body = {"prompt": "x", "provider": "ai_image_free"}
    for _ in range(10):
        assert c.post("/api/content/visual/preview", json=body).status_code == 200


def test_paid_daily_cap_blocks(monkeypatch, tmp_path):
    _fresh_guard(monkeypatch)
    _mock_visual(monkeypatch, tmp_path, provider="ai_image")  # PAID asset produced
    monkeypatch.setattr(mod, "_PREVIEW_RATE_PER_MIN", 0, raising=True)  # isolate the paid cap
    monkeypatch.setattr(mod, "_PREVIEW_DAILY_CAP", 2, raising=True)
    c = _client()
    body = {"prompt": "a castle", "provider": "ai_image"}
    assert c.post("/api/content/visual/preview", json=body).status_code == 200
    assert c.post("/api/content/visual/preview", json=body).status_code == 200
    r = c.post("/api/content/visual/preview", json=body)
    assert r.status_code == 429
    assert "cap" in r.json()["detail"].lower()


def test_paid_cap_not_charged_on_free_fallback(monkeypatch, tmp_path):
    """A requested paid provider that SILENTLY falls back to local (provider=
    'local') must NOT consume the paid daily budget."""
    _fresh_guard(monkeypatch)
    _mock_visual(monkeypatch, tmp_path, provider="local")  # fell back to local
    monkeypatch.setattr(mod, "_PREVIEW_RATE_PER_MIN", 0, raising=True)
    monkeypatch.setattr(mod, "_PREVIEW_DAILY_CAP", 1, raising=True)
    c = _client()
    body = {"prompt": "a castle", "provider": "ai_image"}
    # Both succeed because neither actually produced a paid asset.
    assert c.post("/api/content/visual/preview", json=body).status_code == 200
    assert c.post("/api/content/visual/preview", json=body).status_code == 200


def test_paid_disabled_off_switch(monkeypatch, tmp_path):
    _fresh_guard(monkeypatch)
    _mock_visual(monkeypatch, tmp_path, provider="ai_image")
    monkeypatch.setattr(mod, "_PREVIEW_RATE_PER_MIN", 0, raising=True)
    monkeypatch.setattr(mod, "_PREVIEW_PAID_DISABLED", True, raising=True)
    r = _client().post("/api/content/visual/preview", json={"prompt": "x", "provider": "ai_video"})
    assert r.status_code == 403
    assert "disabled" in r.json()["detail"].lower()
    # A free source is unaffected by the off-switch.
    _mock_visual(monkeypatch, tmp_path, provider="ai_image_free")
    r2 = _client().post("/api/content/visual/preview", json={"prompt": "x", "provider": "ai_image_free"})
    assert r2.status_code == 200


def test_free_provider_never_hits_paid_cap(monkeypatch, tmp_path):
    _fresh_guard(monkeypatch)
    _mock_visual(monkeypatch, tmp_path, provider="ai_image_free")
    monkeypatch.setattr(mod, "_PREVIEW_RATE_PER_MIN", 0, raising=True)
    monkeypatch.setattr(mod, "_PREVIEW_DAILY_CAP", 1, raising=True)
    c = _client()
    body = {"prompt": "x", "provider": "stock"}
    for _ in range(5):
        assert c.post("/api/content/visual/preview", json=body).status_code == 200


def test_empty_prompt_still_422_before_guard(monkeypatch):
    _fresh_guard(monkeypatch)
    r = _client().post("/api/content/visual/preview", json={"prompt": "   "})
    assert r.status_code == 422
