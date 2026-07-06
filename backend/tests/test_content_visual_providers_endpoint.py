"""test_content_visual_providers_endpoint.py — P3.1 GET /api/content/visual-providers.

The endpoint reports which Content visual sources are usable from the API keys in
the environment, so the FE can label "free / ready / needs key" and auto-select
the free stock provider when a key is present. Read-only, env-driven.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Import at module load so config's one-time .env load happens at COLLECTION —
# before any test's monkeypatch.delenv. (A lazy import inside the first test
# would re-populate .env keys AFTER we cleared them.)
from app.features.content.router import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


_KEYS = ("PEXELS_API_KEY", "PIXABAY_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEYS",
         "OPENAI_API_KEY", "GOOGLE_API_KEY")


def _clear_keys(monkeypatch):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)


def test_no_keys_only_local_available(monkeypatch):
    _clear_keys(monkeypatch)
    p = _client().get("/api/content/visual-providers").json()["providers"]
    assert p["local"] == {"available": True, "free": True}
    assert p["stock"]["available"] is False and p["stock"]["free"] is True
    assert p["ai_image"]["available"] is False and p["ai_image"]["free"] is False
    assert p["ai_video"]["available"] is False


def test_pexels_key_makes_stock_available(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("PEXELS_API_KEY", "x" * 20)
    p = _client().get("/api/content/visual-providers").json()["providers"]
    assert p["stock"]["available"] is True and p["stock"]["free"] is True
    # A stock key must NOT light up the paid providers.
    assert p["ai_image"]["available"] is False and p["ai_video"]["available"] is False


def test_gemini_key_lights_paid_providers(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "g" * 20)
    p = _client().get("/api/content/visual-providers").json()["providers"]
    assert p["ai_image"]["available"] is True
    assert p["ai_video"]["available"] is True
    assert p["stock"]["available"] is False  # no stock key


def test_blank_key_counts_as_absent(monkeypatch):
    _clear_keys(monkeypatch)
    monkeypatch.setenv("PEXELS_API_KEY", "   ")
    p = _client().get("/api/content/visual-providers").json()["providers"]
    assert p["stock"]["available"] is False
