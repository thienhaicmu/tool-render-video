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

    def _fake_dl(url, out, timeout=90, cancel_check=None):
        captured["url"] = url
        Path(out).write_bytes(b"\xff\xd8\xff\xe0fakejpeg")
        return True

    monkeypatch.setattr(poll, "visual_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(poll, "_download_with_retry", _fake_dl)
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
    monkeypatch.setattr(poll, "_download_with_retry", lambda *a, **k: False)
    assert poll.resolve_pollinations(_req()) is None


# ── seam dispatch ────────────────────────────────────────────────────────────

def test_seam_dispatches_ai_image_free(monkeypatch, tmp_path):
    monkeypatch.setattr(poll, "visual_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(poll, "_download_with_retry",
                        lambda url, out, timeout=90, cancel_check=None: (Path(out).write_bytes(b"\xff\xd8ok") or True))
    asset = resolve_scene_visual(_req(), provider="ai_image_free")
    assert asset is not None and asset.provider == "ai_image_free"


def test_seam_falls_back_to_local_on_pollinations_failure(monkeypatch):
    # Pollinations returns None (e.g. network down) → seam yields the local asset.
    monkeypatch.setattr(poll, "resolve_pollinations", lambda req: None)
    asset = resolve_scene_visual(_req(kind="color", value="#101820"), provider="ai_image_free")
    assert asset is not None and asset.provider == "local"


# ── retry / backoff (429) ────────────────────────────────────────────────────

import urllib.error  # noqa: E402


class _FakeResp:
    def __init__(self, data, headers=None):
        self._data = data
        self.headers = headers or {}

    def read(self, n=-1):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen_seq(*outcomes):
    """Fake urlopen yielding each outcome in turn (Exception → raised, bytes →
    a fake 200 response). Records the call count on ``.calls``."""
    state = {"n": 0}

    def _fn(req, timeout=None):
        i = state["n"]
        state["n"] += 1
        o = outcomes[min(i, len(outcomes) - 1)]
        if isinstance(o, Exception):
            raise o
        return _FakeResp(o)

    _fn.calls = state
    return _fn


def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


def test_download_retries_on_429_then_succeeds(monkeypatch, tmp_path):
    monkeypatch.setattr(poll.time, "sleep", lambda s: None)
    fake = _urlopen_seq(_http_error(429), b"\xff\xd8imagebytes")
    monkeypatch.setattr(poll.urllib.request, "urlopen", fake)
    out = tmp_path / "o.jpg"
    assert poll._download_with_retry("http://x", str(out), timeout=5) is True
    assert out.read_bytes() == b"\xff\xd8imagebytes"
    assert fake.calls["n"] == 2   # one 429 + one success


def test_download_gives_up_on_persistent_429(monkeypatch, tmp_path):
    monkeypatch.setattr(poll.time, "sleep", lambda s: None)
    monkeypatch.setattr(poll, "_RETRIES", 2)
    fake = _urlopen_seq(_http_error(429), _http_error(429), _http_error(429), _http_error(429))
    monkeypatch.setattr(poll.urllib.request, "urlopen", fake)
    assert poll._download_with_retry("http://x", str(tmp_path / "o.jpg"), timeout=5) is False
    assert fake.calls["n"] == 3   # initial + 2 retries


def test_download_no_retry_on_404(monkeypatch, tmp_path):
    slept = {"n": 0}
    monkeypatch.setattr(poll.time, "sleep", lambda s: slept.__setitem__("n", slept["n"] + 1))
    fake = _urlopen_seq(_http_error(404), _http_error(404))
    monkeypatch.setattr(poll.urllib.request, "urlopen", fake)
    assert poll._download_with_retry("http://x", str(tmp_path / "o.jpg"), timeout=5) is False
    assert fake.calls["n"] == 1 and slept["n"] == 0   # non-retryable → one attempt, no sleep


def test_download_stops_on_cancel(monkeypatch, tmp_path):
    fake = _urlopen_seq(b"should-not-be-read")
    monkeypatch.setattr(poll.urllib.request, "urlopen", fake)
    assert poll._download_with_retry("http://x", str(tmp_path / "o.jpg"), timeout=5,
                                     cancel_check=lambda: True) is False
    assert fake.calls["n"] == 0   # cancelled before any request
