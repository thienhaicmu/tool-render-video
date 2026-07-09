"""Story-to-Video P8 — Vision-QA regen support: image variant + retry cap."""
from __future__ import annotations

import base64
import uuid
from types import SimpleNamespace

from app.domain.story_plan import Shot
from app.features.render.engine.visual import story_image
from app.features.render.engine.stages.story.shot_stage import _story_qa_max_retry

_PNG = base64.b64encode(b"\x89PNG_variant").decode("ascii")


class _FakeImages:
    def __init__(self, log):
        self.log = log

    def generate(self, **kw):
        self.log.append(kw)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=_PNG)])

    def edit(self, **kw):
        self.log.append(kw)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=_PNG)])


class _FakeClient:
    def __init__(self, log):
        self.images = _FakeImages(log)


def test_variant_zero_vs_one_regenerate_distinct(monkeypatch, tmp_path):
    log: list = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    base = f"cold peak {uuid.uuid4().hex}"
    shot = Shot(index=0, visual_prompt=base, quality_tier="medium")
    story_image.generate_shot_image(shot, None, "", 1024, 1024, str(tmp_path / "a.png"), variant=0)
    story_image.generate_shot_image(shot, None, "", 1024, 1024, str(tmp_path / "b.png"), variant=1)
    # Two DISTINCT API calls — variant busts the cache.
    assert len(log) == 2
    # variant>0 folds an "alternative composition" nudge into the prompt.
    prompts = [c.get("prompt", "") for c in log]
    assert any("alternative composition 1" in p for p in prompts)
    assert not any("alternative composition" in p for p in [prompts[0]])  # variant 0 unchanged


def test_same_variant_served_from_cache(monkeypatch, tmp_path):
    log: list = []
    monkeypatch.setattr(story_image, "_openai_client", lambda: _FakeClient(log))
    shot = Shot(index=0, visual_prompt=f"peak {uuid.uuid4().hex}", quality_tier="low")
    story_image.generate_shot_image(shot, None, "", 1024, 1024, str(tmp_path / "a.png"), variant=2)
    story_image.generate_shot_image(shot, None, "", 1024, 1024, str(tmp_path / "b.png"), variant=2)
    assert len(log) == 1  # same variant → cache hit, one API call


def test_qa_max_retry_env(monkeypatch):
    monkeypatch.delenv("STORY_QA_MAX_RETRY", raising=False)
    assert _story_qa_max_retry() == 2
    monkeypatch.setenv("STORY_QA_MAX_RETRY", "4")
    assert _story_qa_max_retry() == 4
    monkeypatch.setenv("STORY_QA_MAX_RETRY", "bogus")
    assert _story_qa_max_retry() == 2  # defensive default
