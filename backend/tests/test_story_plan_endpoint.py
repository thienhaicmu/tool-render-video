"""Story-to-Video P2 — /api/story/plan router logic tests (offline, monkeypatched)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domain.story_plan import StoryPlan, StoryScene, Shot
from app.features.story import router as story_router
from app.features.story.router import StoryPlanRequest, plan_storyboard


def _plan() -> StoryPlan:
    return StoryPlan(language="vi", scenes=[StoryScene(index=0, shots=[
        Shot(index=0, sid="a", narration="Đêm lạnh.", est_duration_sec=3.0),
        Shot(index=1, sid="b", narration="Hàn Phong mở mắt.", est_duration_sec=2.0),
    ])])


def test_plan_422_on_empty_text():
    with pytest.raises(HTTPException) as ei:
        plan_storyboard(StoryPlanRequest(chapter_text="   "))
    assert ei.value.status_code == 422


def test_plan_502_when_ai_returns_none(monkeypatch):
    monkeypatch.setattr(story_router, "generate_story_plan", lambda **kw: None)
    with pytest.raises(HTTPException) as ei:
        plan_storyboard(StoryPlanRequest(chapter_text="Nội dung chương."))
    assert ei.value.status_code == 502


def test_plan_returns_plan_with_counts(monkeypatch):
    monkeypatch.setattr(story_router, "generate_story_plan", lambda **kw: _plan())
    out = plan_storyboard(StoryPlanRequest(chapter_text="Nội dung.", language="vi"))
    assert out["scene_count"] == 1
    assert out["shot_count"] == 2
    assert out["estimated_total_sec"] > 0
    assert "narration_audit" in out
    assert out["plan"]["scenes"][0]["shots"][0]["narration"] == "Đêm lạnh."
