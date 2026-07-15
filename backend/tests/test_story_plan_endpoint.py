"""Story Mode v2 — /api/story/plan (super plan, source A/B) + /visual/svg-preview
router logic (offline, monkeypatched). Story Mode is SVG-only, so the preview composes
procedural SVG (no paid provider)."""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app.domain.story_plan_v2 import StoryPlan, CharacterDef, SettingDef, Visual, Beat
from app.features.story import router as story_router
from app.features.story.router import (
    StoryPlanRequest, plan_storyboard,
    SvgPreviewRequest, svg_visual_preview,
)
from app.features.render.engine.visual import svg_raster

_resvg = pytest.mark.skipif(not svg_raster.available(),
                            reason="resvg-py not installed (SVG raster unavailable)")


def _plan() -> StoryPlan:
    return StoryPlan(
        language="vi", topic="Kiem The", region="cn", genre_key="wuxia",
        characters=[CharacterDef(id="han", name="Han", archetype="swordsman", gender="male")],
        settings=[SettingDef(id="s1", name="Hall", scene_kind="palace")],
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


def test_plan_cost_preflight_image_free_llm_surfaced(monkeypatch):
    """Story imagery is SVG-only → procedural + offline ($0). But the super-plan
    LLM is NOT free — F-08 surfaces its estimated cost so the pre-flight no longer
    reports a misleading $0 total."""
    monkeypatch.setattr(story_router, "generate_story_plan_v2", lambda **kw: _plan())
    out = plan_storyboard(StoryPlanRequest(source="paste", chapter_text="Nội dung.", language="vi"))
    assert out["character_count"] == 1
    cp = out["cost_preflight"]
    assert cp["visual_count"] == 1
    assert cp["character_count"] == 1
    assert cp["premium_image_count"] == 0
    # Imagery is always free (procedural SVG).
    assert cp["image_cost_usd"] == 0.0
    # The LLM cost is an estimate that is surfaced (non-negative; total == LLM).
    assert cp["estimated_llm_cost_usd"] >= 0.0
    assert cp["estimated_llm_input_tokens"] > 0
    assert cp["estimated_cost_usd"] == cp["estimated_llm_cost_usd"]


def test_plan_persists_trace_and_reports_actual_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(story_router, "_PLAN_RUN_DIR", tmp_path)

    def _fake(**kwargs):
        observe = kwargs["observer"]
        observe({"event": "call_started", "stage": "writer", "provider": "openai",
                 "system": "system", "user": "user"})
        observe({"event": "call_completed", "stage": "writer", "provider": "openai",
                 "status": "success", "latency_ms": 12.0, "output": "script"})
        observe({"event": "authoring_selected", "mode": "compiler", "provider": "openai"})
        observe({"event": "provider_selected", "provider": "openai", "model": "gpt-4o"})
        return _plan()

    monkeypatch.setattr(story_router, "generate_story_plan_v2", _fake)
    out = plan_storyboard(StoryPlanRequest(source="idea", idea="A complete idea"))
    trace = out["planning_trace"]
    run_dir = tmp_path / trace["run_id"]
    assert out["authoring_mode"] == "compiler"
    assert out["cost_preflight"]["actual_llm_calls"] == 1
    assert trace["selected_provider"] == "openai" and trace["selected_model"] == "gpt-4o"
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "01_writer_input.json").exists()
    assert (run_dir / "01_writer_output.txt").read_text(encoding="utf-8") == "script"


# ── /api/story/visual/svg-preview ─────────────────────────────────────────────

def test_svg_preview_422_empty_plan():
    with pytest.raises(HTTPException) as ei:
        svg_visual_preview(SvgPreviewRequest(plan={}))
    assert ei.value.status_code == 422


def test_svg_preview_502_when_raster_unavailable(monkeypatch):
    monkeypatch.setattr(
        "app.features.render.engine.visual.svg_raster.available", lambda: False)
    plan_dict = json.loads(_plan().to_json())
    with pytest.raises(HTTPException) as ei:
        svg_visual_preview(SvgPreviewRequest(plan=plan_dict))
    assert ei.value.status_code == 502


@_resvg
def test_svg_preview_success_returns_items(monkeypatch, tmp_path):
    monkeypatch.setattr(story_router, "_VISUAL_DIR", tmp_path)
    plan_dict = json.loads(_plan().to_json())
    out = svg_visual_preview(SvgPreviewRequest(plan=plan_dict))
    items = out["items"]
    assert items and items[0]["visual_id"] == "v1"
    tok = items[0]["token"]
    assert items[0]["url"] == f"/api/story/visual/image/{tok}"
    assert (tmp_path / f"{tok}.png").exists()


@_resvg
def test_svg_preview_subset_by_visual_ids(monkeypatch, tmp_path):
    monkeypatch.setattr(story_router, "_VISUAL_DIR", tmp_path)
    plan = _plan()
    plan.visuals.append(Visual(id="v2", setting_id="s1", prompt="courtyard"))
    out = svg_visual_preview(SvgPreviewRequest(plan=json.loads(plan.to_json()), visual_ids=["v2"]))
    ids = {it["visual_id"] for it in out["items"]}
    assert ids == {"v2"}
