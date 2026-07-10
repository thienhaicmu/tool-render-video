"""Story-to-Video P3 — gpt-image-1 story_image tests (offline, mocked SDK)."""
from __future__ import annotations

import base64
import uuid
from types import SimpleNamespace

from app.domain.story_plan import Shot, StoryBible, StoryCharacter
from app.features.render.engine.visual import story_image

_PNG = base64.b64encode(b"\x89PNG_fake_image_bytes").decode("ascii")


class _FakeImages:
    def __init__(self, log):
        self.log = log

    def generate(self, **kw):
        self.log.append(("generate", kw))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=_PNG)])

    def edit(self, **kw):
        self.log.append(("edit", kw))
        return SimpleNamespace(data=[SimpleNamespace(b64_json=_PNG)])


class _FakeClient:
    def __init__(self, log):
        self.images = _FakeImages(log)


def test_no_key_returns_none(monkeypatch):
    monkeypatch.setattr(story_image, "_openai_client", lambda: None)
    assert story_image.generate_image_bytes("a prompt", 1024, 1536) is None


def test_generate_bytes_uses_generate_endpoint(monkeypatch):
    log = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    data = story_image.generate_image_bytes("wuxia peak at dawn", 1024, 1536, quality="low")
    assert data == b"\x89PNG_fake_image_bytes"
    assert log[0][0] == "generate"
    assert log[0][1]["quality"] == "low"
    assert log[0][1]["size"] == "1024x1536"  # portrait


def test_reference_paths_use_edit_endpoint(monkeypatch, tmp_path):
    ref = tmp_path / "ref.png"
    ref.write_bytes(b"refbytes")
    log = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    data = story_image.generate_image_bytes("shot", 1024, 1024, reference_paths=[str(ref)])
    assert data is not None
    assert log[0][0] == "edit"  # reference → image-edit endpoint


def test_generate_shot_image_writes_and_caches(monkeypatch, tmp_path):
    log = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    shot = Shot(index=0, visual_prompt=f"cold peak {uuid.uuid4().hex}", quality_tier="medium")
    out = tmp_path / "shot.png"
    p = story_image.generate_shot_image(shot, None, "wuxia", 1024, 1536, str(out))
    assert p == str(out) and out.exists()
    # Second call for the same shot → served from cache, no new API call.
    out2 = tmp_path / "shot2.png"
    story_image.generate_shot_image(shot, None, "wuxia", 1024, 1536, str(out2))
    assert out2.exists()
    assert len(log) == 1  # only the first generation hit the API


def test_generate_shot_image_reference_from_bible(monkeypatch, tmp_path):
    ref = tmp_path / "han.png"
    ref.write_bytes(b"refsheet")
    bible = StoryBible(characters=[
        StoryCharacter(id="han_phong", name="Hàn Phong", description="áo trắng",
                       reference_image_path=str(ref)),
    ])
    log = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    shot = Shot(index=0, visual_prompt=f"ref prompt {uuid.uuid4().hex}", characters=["han_phong"], quality_tier="high")
    out = tmp_path / "s.png"
    story_image.generate_shot_image(shot, bible, "", 1024, 1024, str(out))
    assert log[0][0] == "edit"  # character reference sheet → edit


def test_empty_prompt_returns_none(monkeypatch):
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient([]))
    assert story_image.generate_shot_image(Shot(index=0, visual_prompt="  "), None, "", 1024, 1024, "x.png") is None


def test_generate_visual_image_conditions_on_setting_ref(monkeypatch, tmp_path):
    """G6: generate_visual_image feeds the environment reference (setting_id) to the
    image-edit alongside the character refs, character first."""
    from app.domain.story_plan_v2 import Visual
    cap = {}

    def _fake_bytes(prompt, w, h, quality="medium", reference_paths=None, negative=""):
        cap["refs"] = list(reference_paths or [])
        return b"\x89PNG"
    monkeypatch.setattr(story_image, "generate_image_bytes", _fake_bytes)

    char_ref = tmp_path / "han.png"; char_ref.write_bytes(b"c")
    env_ref = tmp_path / "hall.png"; env_ref.write_bytes(b"e")
    v = Visual(id="v1", prompt=f"wide hall {uuid.uuid4().hex}", setting_id="hall", character_ids=["han"])
    out = tmp_path / "v1.png"
    refs = {"han": str(char_ref), "hall": str(env_ref)}
    p = story_image.generate_visual_image(v, refs, "wuxia", 1024, 1024, str(out), seed=1, provider="gpt_image")
    assert p == str(out)
    assert str(char_ref) in cap["refs"] and str(env_ref) in cap["refs"]
    assert cap["refs"].index(str(char_ref)) < cap["refs"].index(str(env_ref))  # character first
