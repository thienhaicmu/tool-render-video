"""Tests for the Imagen 4 tier selection + Gemini key-pool rotation upgrade
(2026-07-04). Content-mode AI-image generation now:
  · defaults to Imagen 4 (standard), selectable via CONTENT_IMAGEN_TIER
    (fast|standard|ultra) or overridden by CONTENT_IMAGEN_MODEL, and
  · fans each request across the whole GEMINI_API_KEYS pool (rotates on 429),
    instead of using a single GEMINI_API_KEY.
"""
from __future__ import annotations

import pytest

import app.features.render.engine.visual.provider_ai_image as ai


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("CONTENT_IMAGEN_MODEL", "CONTENT_IMAGEN_TIER"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_tier_maps_to_models(monkeypatch):
    # Default "standard" = Imagen 3 (broadly available so AI images work OOTB).
    assert ai._imagen_model() == "imagen-3.0-generate-002"
    monkeypatch.setenv("CONTENT_IMAGEN_TIER", "fast")
    assert ai._imagen_model() == "imagen-4.0-fast-generate-001"      # Imagen 4 (opt-in)
    monkeypatch.setenv("CONTENT_IMAGEN_TIER", "ultra")
    assert ai._imagen_model() == "imagen-4.0-ultra-generate-001"     # Imagen 4 (opt-in)
    monkeypatch.setenv("CONTENT_IMAGEN_TIER", "nonsense")
    assert ai._imagen_model() == "imagen-3.0-generate-002"           # unknown → standard


def test_explicit_model_overrides_tier(monkeypatch):
    monkeypatch.setenv("CONTENT_IMAGEN_TIER", "fast")
    monkeypatch.setenv("CONTENT_IMAGEN_MODEL", "imagen-custom-x")
    assert ai._imagen_model() == "imagen-custom-x"


def test_per_request_tier_overrides_env(monkeypatch):
    # A payload/scene tier beats the env default (but not an explicit model id).
    monkeypatch.setenv("CONTENT_IMAGEN_TIER", "fast")
    assert ai._imagen_model("ultra") == "imagen-4.0-ultra-generate-001"
    # Empty override → fall back to the env tier.
    assert ai._imagen_model("") == "imagen-4.0-fast-generate-001"


def test_render_request_imagen_tier_default_inert():
    # Sacred Contract #2: new field defaults to "" (inert → env/standard).
    from app.models.render import RenderRequest
    assert RenderRequest().content_imagen_tier == ""
    from app.models.render_public import FE_FACING_FIELDS
    assert "content_imagen_tier" in FE_FACING_FIELDS  # user-selectable on the wire


def test_scene_visual_request_carries_tier():
    from app.features.render.engine.visual import SceneVisualRequest
    r = SceneVisualRequest(scene_index=0, kind="color", value="#000", prompt="x",
                           width=1080, height=1920, fps=30, duration_sec=3, work_dir=".",
                           imagen_tier="ultra")
    assert r.imagen_tier == "ultra"
    # default is inert
    r2 = SceneVisualRequest(scene_index=0, kind="color", value="#000", prompt="x",
                            width=1080, height=1920, fps=30, duration_sec=3, work_dir=".")
    assert r2.imagen_tier == ""


def test_aspect_ratio_from_canvas():
    assert ai._imagen_aspect_ratio(1080, 1920) == "9:16"
    assert ai._imagen_aspect_ratio(1920, 1080) == "16:9"
    assert ai._imagen_aspect_ratio(1024, 1024) == "1:1"
    assert ai._imagen_aspect_ratio(0, 0) == "1:1"


def test_gemini_image_uses_key_rotation(monkeypatch):
    """_gemini_image must route through the key-pool rotation, not a single key."""
    monkeypatch.setenv("GEMINI_API_KEY", "seed-key")
    from app.features.render.ai.llm import key_pool

    seen = {}

    def _fake_rotation(once_factory, *, label, seed_key):
        seen["label"] = label
        seen["seed_key"] = seed_key
        # Exercise the factory with one key so it builds the SDK call path.
        return b"IMGBYTES"

    monkeypatch.setattr(key_pool, "call_gemini_with_rotation", _fake_rotation)
    # genai import inside _gemini_image is lazy; stub sys.modules so it imports.
    import sys
    import types as _t
    monkeypatch.setitem(sys.modules, "google", _t.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.genai", _t.ModuleType("google.genai"))

    out = ai._gemini_image("a red planet", "", "", 0, 1080, 1920)
    assert out == b"IMGBYTES"
    assert seen["label"] == "imagen"
    assert seen["seed_key"] == "seed-key"


def test_gemini_image_no_keys_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from app.features.render.ai.llm import key_pool
    monkeypatch.setattr(key_pool, "pool", lambda: [])
    import sys
    import types as _t
    monkeypatch.setitem(sys.modules, "google", _t.ModuleType("google"))
    monkeypatch.setitem(sys.modules, "google.genai", _t.ModuleType("google.genai"))
    assert ai._gemini_image("x", width=1080, height=1920) is None
