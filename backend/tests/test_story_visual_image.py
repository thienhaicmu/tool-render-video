"""Story Mode v2 — B5 generate_visual_image + clamp_tier (offline, mocked SDK)."""
from __future__ import annotations

import base64
import uuid
from types import SimpleNamespace

from app.domain.story_plan_v2 import Visual
from app.features.render.engine.visual import story_image
from app.features.render.engine.visual.story_decision import clamp_tier

_PNG = base64.b64encode(b"\x89PNG_visual").decode("ascii")


class _FakeImages:
    def __init__(self, log): self.log = log
    def generate(self, **kw):
        self.log.append(("generate", kw)); return SimpleNamespace(data=[SimpleNamespace(b64_json=_PNG)])
    def edit(self, **kw):
        self.log.append(("edit", kw)); return SimpleNamespace(data=[SimpleNamespace(b64_json=_PNG)])


class _FakeClient:
    def __init__(self, log): self.images = _FakeImages(log)


def _vis(**kw):
    base = dict(id="v1", prompt=f"wide hall {uuid.uuid4().hex}", character_ids=[], tier="medium")
    base.update(kw); return Visual(**base)


# ── clamp_tier ────────────────────────────────────────────────────────────────

def test_clamp_tier(monkeypatch):
    monkeypatch.setenv("STORY_IMAGE_MAX_TIER", "medium")
    assert clamp_tier("high") == "medium"
    assert clamp_tier("low") == "low"
    assert clamp_tier("medium") == "medium"
    assert clamp_tier("bogus") == "medium"
    monkeypatch.setenv("STORY_IMAGE_MAX_TIER", "high")
    assert clamp_tier("high") == "high"


# ── generate_visual_image ─────────────────────────────────────────────────────

def test_no_key_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr(story_image, "_openai_client", lambda: None)
    assert story_image.generate_visual_image(_vis(), {}, "wuxia", 1536, 1024, str(tmp_path / "a.png")) is None


def test_generate_endpoint_no_refs(monkeypatch, tmp_path):
    log = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    out = tmp_path / "a.png"
    p = story_image.generate_visual_image(_vis(tier="low"), {}, "wuxia", 1536, 1024, str(out))
    assert p == str(out) and out.exists()
    assert log[0][0] == "generate" and log[0][1]["quality"] == "low" and log[0][1]["size"] == "1536x1024"


def test_reference_uses_edit(monkeypatch, tmp_path):
    ref = tmp_path / "han.png"; ref.write_bytes(b"refsheet")
    log = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    v = _vis(character_ids=["han"])
    story_image.generate_visual_image(v, {"han": str(ref)}, "", 1536, 1024, str(tmp_path / "a.png"))
    assert log[0][0] == "edit"


def test_tier_clamped(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_IMAGE_MAX_TIER", "medium")
    log = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    story_image.generate_visual_image(_vis(tier="high"), {}, "", 1536, 1024, str(tmp_path / "a.png"))
    assert log[0][1]["quality"] == "medium"   # high capped to medium


def test_cache_second_call(monkeypatch, tmp_path):
    log = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    v = _vis()  # unique prompt
    story_image.generate_visual_image(v, {}, "", 1536, 1024, str(tmp_path / "a.png"))
    story_image.generate_visual_image(v, {}, "", 1536, 1024, str(tmp_path / "b.png"))
    assert len(log) == 1   # second served from cache
    assert (tmp_path / "b.png").exists()


def test_empty_prompt_none(monkeypatch, tmp_path):
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient([]))
    assert story_image.generate_visual_image(_vis(prompt="  "), {}, "", 1536, 1024, str(tmp_path / "x.png")) is None
