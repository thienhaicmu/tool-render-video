"""test_content_pin_asset.py — CM-12 pin a previewed image as a durable asset.

POST /api/content/visual/pin {token} copies the pruneable preview image to
APP_DATA_DIR/content_assets (never pruned) and returns its local path, which the
FE stores in scene.visual_path so the render uses that exact image.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.features.content.router as mod
from app.features.content.router import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_preview(monkeypatch, tmp_path) -> str:
    """Create a preview image under a sandboxed preview dir; return its token."""
    prev = tmp_path / "preview"
    assets = tmp_path / "assets"
    monkeypatch.setattr(mod, "_VISUAL_PREVIEW_DIR", prev, raising=False)
    monkeypatch.setattr(mod, "_CONTENT_ASSETS_DIR", assets, raising=False)
    prev.mkdir(parents=True, exist_ok=True)
    token = "a" * 32
    (prev / f"{token}.jpg").write_bytes(b"\xff\xd8\xff\xe0jpegbytes")
    return token


def test_pin_copies_to_durable_dir(monkeypatch, tmp_path):
    token = _seed_preview(monkeypatch, tmp_path)
    r = _client().post("/api/content/visual/pin", json={"token": token})
    assert r.status_code == 200, r.text
    path = r.json()["path"]
    p = Path(path)
    assert p.exists() and p.read_bytes() == b"\xff\xd8\xff\xe0jpegbytes"
    # Durable: lives under the (sandboxed) content_assets dir, not the preview cache.
    assert p.parent == (tmp_path / "assets")
    assert p.suffix == ".jpg"


def test_pin_malformed_token_404():
    r = _client().post("/api/content/visual/pin", json={"token": "not-a-token"})
    assert r.status_code == 404


def test_pin_missing_preview_404(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "_VISUAL_PREVIEW_DIR", tmp_path / "preview", raising=False)
    monkeypatch.setattr(mod, "_CONTENT_ASSETS_DIR", tmp_path / "assets", raising=False)
    (tmp_path / "preview").mkdir(parents=True, exist_ok=True)
    # well-formed token, but no file on disk (expired / never created)
    r = _client().post("/api/content/visual/pin", json={"token": "b" * 32})
    assert r.status_code == 404
