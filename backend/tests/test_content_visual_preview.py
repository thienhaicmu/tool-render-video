"""test_content_visual_preview.py — Phase C1 per-scene visual preview endpoints.

POST /api/content/visual/preview resolves a scene's visual via the render seam
and returns a previewable image (token + url) or, on a colour/video fallback,
the background spec. GET /api/content/visual/image/{token} serves the image.
resolve_scene_visual is mocked so the test never touches the network.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

# Module-top import so config's one-time .env load happens at collection.
from app.features.content.router import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_visual_preview_returns_image_token(monkeypatch, tmp_path):
    import app.features.content.router as mod
    from app.features.render.engine.visual import SceneVisualAsset

    monkeypatch.setattr(mod, "_VISUAL_PREVIEW_DIR", tmp_path / "vp", raising=False)
    src = tmp_path / "generated.jpg"
    src.write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
    monkeypatch.setattr(
        "app.features.render.engine.visual.resolve_scene_visual",
        lambda request, provider="": SceneVisualAsset(kind="image", value=str(src), provider="ai_image_free"),
    )

    c = _client()
    r = c.post("/api/content/visual/preview",
               json={"prompt": "a castle at dawn", "provider": "ai_image_free"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "image" and body["provider"] == "ai_image_free"
    assert body["url"].startswith("/api/content/visual/image/")
    token = body["token"]

    g = c.get(f"/api/content/visual/image/{token}")
    assert g.status_code == 200 and g.content == b"\xff\xd8\xff\xe0fakejpeg"
    assert g.headers["content-type"] == "image/jpeg"


def test_visual_preview_colour_fallback_has_no_image(monkeypatch, tmp_path):
    import app.features.content.router as mod
    from app.features.render.engine.visual import SceneVisualAsset

    monkeypatch.setattr(mod, "_VISUAL_PREVIEW_DIR", tmp_path / "vp", raising=False)
    monkeypatch.setattr(
        "app.features.render.engine.visual.resolve_scene_visual",
        lambda request, provider="": SceneVisualAsset(kind="color", value="#101820", provider="local"),
    )
    r = _client().post("/api/content/visual/preview", json={"prompt": "x", "provider": "stock"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "color" and body["value"] == "#101820"
    assert "token" not in body


def test_visual_preview_empty_prompt_422():
    r = _client().post("/api/content/visual/preview", json={"prompt": "   "})
    assert r.status_code == 422


def test_visual_image_bad_token_404():
    r = _client().get("/api/content/visual/image/not-a-valid-token")
    assert r.status_code == 404


def test_visual_image_missing_token_404(monkeypatch, tmp_path):
    import app.features.content.router as mod
    monkeypatch.setattr(mod, "_VISUAL_PREVIEW_DIR", tmp_path / "vp", raising=False)
    (tmp_path / "vp").mkdir(parents=True, exist_ok=True)
    # a well-formed but unknown 32-hex token
    r = _client().get("/api/content/visual/image/" + "a" * 32)
    assert r.status_code == 404
