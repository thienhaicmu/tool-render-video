"""Story-to-Video P3 — Vision QA tests (offline, fail-open, Sacred Contract #3)."""
from __future__ import annotations

from types import SimpleNamespace

from app.domain.story_plan import Shot, StoryBible, StoryCharacter
from app.features.render.ai.vision import qa


def _fake_vision_client(text):
    def create(**kw):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])
    completions = SimpleNamespace(create=create)
    chat = SimpleNamespace(completions=completions)
    return SimpleNamespace(chat=chat)


def _img(tmp_path):
    p = tmp_path / "shot.png"
    p.write_bytes(b"\x89PNG_bytes")
    return str(p)


def test_disabled_by_default_returns_ok_skipped(tmp_path):
    # STORY_VISION_QA off by default → skipped, fail-open ok.
    out = qa.qa_shot_image(_img(tmp_path), Shot(index=0, visual_prompt="x"))
    assert out["ok"] is True and out["verdict"] == "skipped"


def test_enabled_no_client_fails_open(monkeypatch, tmp_path):
    monkeypatch.setattr(qa, "_QA_ON", True)
    monkeypatch.setattr(qa, "_openai_client", lambda: None)
    out = qa.qa_shot_image(_img(tmp_path), Shot(index=0, visual_prompt="x"))
    assert out["ok"] is True  # unavailable → accept


def test_enabled_yes_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(qa, "_QA_ON", True)
    monkeypatch.setattr(qa, "_openai_client", lambda: _fake_vision_client("YES\nlooks right"))
    out = qa.qa_shot_image(_img(tmp_path), Shot(index=0, visual_prompt="a hero"))
    assert out["ok"] is True and out["verdict"] == "pass"


def test_enabled_no_rejects(monkeypatch, tmp_path):
    monkeypatch.setattr(qa, "_QA_ON", True)
    monkeypatch.setattr(qa, "_openai_client", lambda: _fake_vision_client("NO\nwrong character face"))
    bible = StoryBible(characters=[StoryCharacter(id="h", name="Hero", description="áo trắng")])
    shot = Shot(index=0, visual_prompt="a hero", characters=["h"], emotion="epic", shot_type="close_up")
    out = qa.qa_shot_image(_img(tmp_path), shot, bible)
    assert out["ok"] is False and out["verdict"] == "reject"


def test_missing_image_fails_open(monkeypatch):
    monkeypatch.setattr(qa, "_QA_ON", True)
    out = qa.qa_shot_image("/no/such/file.png", Shot(index=0, visual_prompt="x"))
    assert out["ok"] is True


def test_client_raising_fails_open(monkeypatch, tmp_path):
    monkeypatch.setattr(qa, "_QA_ON", True)

    def boom():
        raise RuntimeError("vision exploded")
    monkeypatch.setattr(qa, "_openai_client", boom)
    out = qa.qa_shot_image(_img(tmp_path), Shot(index=0, visual_prompt="x"))
    assert out["ok"] is True  # Sacred Contract #3 — never blocks a render
