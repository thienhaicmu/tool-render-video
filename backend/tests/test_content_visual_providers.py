"""test_content_visual_providers.py — CS-G Visual Generator providers.

The online providers (stock / ai_image) are opt-in and ALWAYS fall back to the
local provider when their API key / network / SDK is unavailable. These tests run
fully offline: no key set (→ None → local fallback), plus a mocked-API success
path for the stock provider. No live network.
"""
from __future__ import annotations

from pathlib import Path

from app.features.render.engine.visual import (
    SceneVisualRequest, resolve_scene_visual, cache_key, download_to,
)


def _req(prompt="a cat on mars", kind="color", value="#000000", tmp="."):
    return SceneVisualRequest(
        scene_index=0, kind=kind, value=value, prompt=prompt,
        width=1080, height=1920, fps=30, duration_sec=3, work_dir=tmp,
    )


def test_cache_key_stable_and_distinct():
    assert cache_key("a", "b", 1) == cache_key("a", "b", 1)
    assert cache_key("a", "b", 1) != cache_key("a", "b", 2)


def test_download_to_bad_url_returns_false(tmp_path):
    assert download_to("http://127.0.0.1:1/nope.jpg", str(tmp_path / "x.jpg"), timeout=1) is False


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body
        self.headers = {}

    def read(self, n: int = -1) -> bytes:
        return self._body if n < 0 else self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_to_size_cap_rejects_oversized(monkeypatch, tmp_path):
    # LOW-3: cap at 10 bytes; an 11-byte body must be rejected.
    monkeypatch.setenv("CONTENT_MAX_ASSET_BYTES", "10")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(b"x" * 11))
    out = tmp_path / "big.jpg"
    assert download_to("http://example/big.jpg", str(out), timeout=1) is False
    assert not out.exists()


def test_download_to_under_cap_succeeds(monkeypatch, tmp_path):
    monkeypatch.setenv("CONTENT_MAX_ASSET_BYTES", "1000")
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp(b"okbytes"))
    out = tmp_path / "ok.jpg"
    assert download_to("http://example/ok.jpg", str(out), timeout=1) is True
    assert out.read_bytes() == b"okbytes"


def test_stock_no_keys_returns_none(monkeypatch):
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    from app.features.render.engine.visual.provider_stock import resolve_stock
    assert resolve_stock(_req()) is None


def test_ai_image_no_keys_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.features.render.engine.visual.provider_ai_image import resolve_ai_image
    assert resolve_ai_image(_req()) is None


def test_ai_image_forwards_negative_and_style(monkeypatch, tmp_path):
    # CU-3: negative_prompt + style must reach the image generator.
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("CONTENT_AI_IMAGE_PROVIDER", raising=False)  # default gemini
    import app.features.render.engine.visual.provider_ai_image as ai
    monkeypatch.setattr(ai, "visual_cache_dir", lambda: tmp_path)
    captured: dict = {}

    def _fake_gemini(prompt, negative="", style="", seed=0, width=0, height=0, imagen_tier=""):
        captured.update(prompt=prompt, negative=negative, style=style, seed=seed,
                        width=width, height=height)
        return b"PNGDATA"
    monkeypatch.setattr(ai, "_gemini_image", _fake_gemini)

    req = _req(prompt="a battlefield at dawn")
    req.negative_prompt = "blurry, cartoon"
    req.style = "cinematic"
    req.seed = 12345
    a = ai.resolve_ai_image(req)
    assert a is not None and a.kind == "image"
    assert captured["negative"] == "blurry, cartoon"
    assert captured["style"] == "cinematic"
    assert captured["seed"] == 12345          # CU-11 seed forwarded
    # Canvas dimensions now reach the generator (Imagen aspect_ratio derivation).
    assert captured["width"] > 0 and captured["height"] > 0


def test_apply_style_helper():
    from app.features.render.engine.visual.provider_ai_image import _apply_style
    assert _apply_style("a cat", "cinematic") == "a cat, cinematic style"
    assert _apply_style("a cat", "") == "a cat"


def test_stable_seed_deterministic_and_distinct():
    from app.features.render.engine.stages.content.context import stable_seed as _stable_seed
    assert _stable_seed("napoleon") == _stable_seed("napoleon")
    assert _stable_seed("napoleon") != _stable_seed("caesar")
    assert _stable_seed("") == 0
    assert _stable_seed("x") > 0


def test_ai_image_verify_regenerates_on_mismatch(monkeypatch, tmp_path):
    # CU-10: with verify on, a rejected image triggers one regenerate.
    import app.features.render.engine.visual.provider_ai_image as ai
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(ai, "visual_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(ai, "_VERIFY_ON", True, raising=False)
    monkeypatch.setattr(ai, "_VERIFY_RETRY", 1, raising=False)

    gen_calls = {"n": 0}

    def _fake_gemini(prompt, negative="", style="", seed=0, width=0, height=0, imagen_tier=""):
        gen_calls["n"] += 1
        return b"PNGDATA"
    monkeypatch.setattr(ai, "_gemini_image", _fake_gemini)

    verdicts = iter([False, True])  # first image rejected, second accepted

    def _fake_verify(path, prompt):
        return next(verdicts, True)
    monkeypatch.setattr(ai, "_verify_image", _fake_verify)

    a = ai.resolve_ai_image(_req(prompt="a red planet", tmp=str(tmp_path)))
    assert a is not None and a.kind == "image"
    assert gen_calls["n"] == 2   # regenerated once after the rejection


def test_verify_image_fail_open_without_key(monkeypatch):
    import app.features.render.engine.visual.provider_ai_image as ai
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert ai._verify_image("/nope.png", "anything") is True  # fail-open


def test_seam_stock_falls_back_to_local(monkeypatch, tmp_path):
    # B2 adds a stepped free-image fallback; disable it here to exercise the
    # terminal local path (the fallback itself is covered in
    # test_content_visual_fallback.py).
    import app.features.render.engine.visual as _v
    monkeypatch.setattr(_v, "_CONTENT_VISUAL_FALLBACK", False)
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    a = resolve_scene_visual(_req(kind="color", value="#123456", tmp=str(tmp_path)), provider="stock")
    assert a is not None and a.provider == "local"
    assert a.kind == "color" and a.value == "#123456"


def test_seam_ai_image_falls_back_to_local(monkeypatch, tmp_path):
    import app.features.render.engine.visual as _v
    monkeypatch.setattr(_v, "_CONTENT_VISUAL_FALLBACK", False)   # B2: terminal-local path
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    a = resolve_scene_visual(_req(kind="color", value="#abcdef", tmp=str(tmp_path)), provider="ai_image")
    assert a is not None and a.provider == "local" and a.value == "#abcdef"


def test_ai_video_no_keys_returns_none(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from app.features.render.engine.visual.provider_ai_video import resolve_ai_video
    assert resolve_ai_video(_req()) is None


def test_seam_ai_video_falls_back_to_local(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    a = resolve_scene_visual(_req(kind="color", value="#010203", tmp=str(tmp_path)), provider="ai_video")
    assert a is not None and a.provider == "local" and a.value == "#010203"


def test_seam_unknown_provider_falls_back_to_local(tmp_path):
    a = resolve_scene_visual(_req(tmp=str(tmp_path)), provider="midjourney")
    assert a is not None and a.provider == "local"


def test_stock_success_with_mocked_api(monkeypatch, tmp_path):
    monkeypatch.setenv("PEXELS_API_KEY", "fake-key")
    import app.features.render.engine.visual.provider_stock as ps
    monkeypatch.setattr(ps, "_pexels_search", lambda q, k, w, h: "http://example/img.jpg")
    monkeypatch.setattr(ps, "visual_cache_dir", lambda: tmp_path)

    def _fake_dl(url, out, timeout=30):
        Path(out).write_bytes(b"JPEGDATA")
        return True
    monkeypatch.setattr(ps, "download_to", _fake_dl)

    a = ps.resolve_stock(_req(prompt="mars surface", tmp=str(tmp_path)))
    assert a is not None and a.kind == "image" and a.provider == "stock"
    assert Path(a.value).exists() and Path(a.value).read_bytes() == b"JPEGDATA"
