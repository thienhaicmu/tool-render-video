"""Story Mode v2 — B8 /api/story/plan (super plan, source A/B) + /visual/preview
router logic (offline, monkeypatched)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual, Beat
from app.features.story import router as story_router
from app.features.story.router import (
    StoryPlanRequest, plan_storyboard,
    StoryVisualPreviewRequest, visual_preview,
)


def _plan() -> StoryPlan:
    return StoryPlan(
        language="vi", topic="Kiem The",
        characters=[CharacterDef(id="han", name="Han")],
        settings=[SettingDef(id="s1", name="Hall")],
        visuals=[Visual(id="v1", setting_id="s1", prompt="wide hall", character_ids=["han"])],
        timeline=[
            Beat(id="b1", narration="Đêm lạnh.", speaker_id="", visual_id="v1"),
            Beat(id="b2", narration="Hàn Phong mở mắt.", speaker_id="han", visual_id="v1"),
        ],
    )


# ── /api/story/plan (super plan) ──────────────────────────────────────────────

def test_plan_422_paste_empty_text():
    with pytest.raises(HTTPException) as ei:
        plan_storyboard(StoryPlanRequest(source="paste", chapter_text="   "))
    assert ei.value.status_code == 422


def test_plan_422_idea_empty():
    with pytest.raises(HTTPException) as ei:
        plan_storyboard(StoryPlanRequest(source="idea", idea="  "))
    assert ei.value.status_code == 422


def test_plan_502_when_ai_returns_none(monkeypatch):
    monkeypatch.setattr(story_router, "generate_story_plan_v2", lambda **kw: None)
    with pytest.raises(HTTPException) as ei:
        plan_storyboard(StoryPlanRequest(source="paste", chapter_text="Nội dung chương."))
    assert ei.value.status_code == 502


def test_plan_source_paste_returns_plan_with_counts(monkeypatch):
    captured = {}

    def _fake(**kw):
        captured.update(kw)
        return _plan()
    monkeypatch.setattr(story_router, "generate_story_plan_v2", _fake)
    out = plan_storyboard(StoryPlanRequest(source="paste", chapter_text="Nội dung.", language="vi"))
    assert captured["source"] == "paste" and captured["chapter"] == "Nội dung."
    assert out["image_count"] == 1
    assert out["beat_count"] == 2
    assert out["estimated_total_sec"] > 0
    assert out["plan"]["timeline"][0]["narration"] == "Đêm lạnh."
    assert out["plan"]["schema_version"] == 2


def test_plan_source_idea_passes_idea_and_duration(monkeypatch):
    captured = {}

    def _fake(**kw):
        captured.update(kw)
        return _plan()
    monkeypatch.setattr(story_router, "generate_story_plan_v2", _fake)
    out = plan_storyboard(StoryPlanRequest(
        source="idea", idea="Tiên hiệp báo thù", duration_sec=90, genre="tien-hiep"))
    assert captured["source"] == "idea"
    assert captured["idea"] == "Tiên hiệp báo thù"
    assert captured["duration_sec"] == 90 and captured["genre"] == "tien-hiep"
    assert out["image_count"] == 1 and out["beat_count"] == 2


# ── /api/story/visual/preview ─────────────────────────────────────────────────

def test_visual_preview_422_empty_prompt():
    with pytest.raises(HTTPException) as ei:
        visual_preview(StoryVisualPreviewRequest(prompt="  "))
    assert ei.value.status_code == 422


def test_visual_preview_502_on_failure(monkeypatch):
    monkeypatch.setattr(story_router, "generate_story_plan_v2", lambda **kw: None)  # unrelated guard
    from app.features.render.engine.visual import story_image
    monkeypatch.setattr(story_image, "generate_visual_image", lambda *a, **k: None)
    with pytest.raises(HTTPException) as ei:
        visual_preview(StoryVisualPreviewRequest(prompt="a wide hall"))
    assert ei.value.status_code == 502


def test_visual_preview_success_returns_token(monkeypatch, tmp_path):
    monkeypatch.setattr(story_router, "_VISUAL_DIR", tmp_path)
    from app.features.render.engine.visual import story_image

    def _fake_img(visual, refs, art_style, w, h, out_path, seed=0):
        from pathlib import Path
        Path(out_path).write_bytes(b"\x89PNG_preview")
        return out_path
    monkeypatch.setattr(story_image, "generate_visual_image", _fake_img)
    out = visual_preview(StoryVisualPreviewRequest(prompt="a wide moonlit hall", tier="low"))
    assert out["token"] and out["url"] == f"/api/story/visual/image/{out['token']}"
    assert (tmp_path / f"{out['token']}.png").exists()
