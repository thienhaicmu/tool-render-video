"""Story v2 — quality-tier clamp (clamp_tier) tests (pure, offline)."""
from __future__ import annotations

from app.features.render.engine.visual.story_decision import clamp_tier


def test_clamp_defaults_to_env_max_medium(monkeypatch):
    monkeypatch.delenv("STORY_IMAGE_MAX_TIER", raising=False)
    assert clamp_tier("high") == "medium"      # default cap = medium
    assert clamp_tier("low") == "low"
    assert clamp_tier("medium") == "medium"


def test_clamp_respects_env_max(monkeypatch):
    monkeypatch.setenv("STORY_IMAGE_MAX_TIER", "high")
    assert clamp_tier("high") == "high"
    assert clamp_tier("low") == "low"


def test_clamp_explicit_max_arg():
    assert clamp_tier("high", max_tier="low") == "low"
    assert clamp_tier("medium", max_tier="high") == "medium"


def test_clamp_unknown_coerced_medium(monkeypatch):
    monkeypatch.setenv("STORY_IMAGE_MAX_TIER", "high")
    assert clamp_tier("banana") == "medium"
    assert clamp_tier("") == "medium"
