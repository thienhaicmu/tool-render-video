"""test_content_cs_a.py — Content Studio CS-A (plan/render decouple).

Covers:
  - ContentPlan v2: the enriched per-scene fields (scene_title, visual_prompt,
    negative_prompt, per-scene subtitle_style, asset_suggestion) + plan-level
    video_style survive to_json/from_json; a v1 blob still loads (back-compat).
  - RenderRequest.content_plan_override defaults to "" (Sacred Contract #2).
  - POST /api/content/plan — plan-only endpoint (AI mocked): 200 / 422 / 502.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.content_plan import ContentPlan, ContentScene


# ── ContentPlan v2 domain ────────────────────────────────────────────────────

def test_content_plan_v2_roundtrip_preserves_new_fields():
    plan = ContentPlan(
        topic="Sao Hoa", tone="documentary", audience="general", language="vi-VN",
        total_target_sec=8.0, subtitle_style="capcut", bgm_mood="epic",
        video_style="documentary",
        scenes=[
            ContentScene(
                index=0, scene_title="Mở màn", role="hook",
                narration="Ban co biet?", emotion="curious", reading_speed=1.1,
                subtitle_style="word_by_word",
                visual_hint="sao hoa", visual_prompt="A cinematic Mars at sunrise, 4k",
                negative_prompt="blurry, low quality", asset_suggestion="ai_image",
            ),
        ],
    )
    back = ContentPlan.from_json(plan.to_json())
    assert back is not None
    assert back.schema_version == 2
    assert back.video_style == "documentary"
    s = back.scenes[0]
    assert s.scene_title == "Mở màn"
    assert s.visual_prompt == "A cinematic Mars at sunrise, 4k"
    assert s.negative_prompt == "blurry, low quality"
    assert s.asset_suggestion == "ai_image"
    assert s.subtitle_style == "word_by_word"


def test_content_plan_v1_blob_still_loads():
    # A pre-CS-A blob with none of the new keys must load with empty defaults.
    v1 = json.dumps({
        "topic": "x", "scenes": [{"index": 0, "role": "hook", "narration": "hi"}],
    })
    plan = ContentPlan.from_json(v1)
    assert plan is not None and plan.scene_count() == 1
    s = plan.scenes[0]
    assert s.scene_title == "" and s.visual_prompt == "" and s.asset_suggestion == ""
    assert plan.video_style == ""


def test_content_plan_override_defaults_empty():
    from app.models.schemas import RenderRequest
    assert RenderRequest(output_dir="").content_plan_override == ""


# ── plan-only endpoint ───────────────────────────────────────────────────────

def _client() -> TestClient:
    from app.features.content.router import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_plan_endpoint_returns_plan(monkeypatch):
    import app.features.content.router as mod
    monkeypatch.setattr(
        mod, "select_content_plan",
        lambda **k: ContentPlan(topic="T", scenes=[ContentScene(index=0, narration="hi")]),
    )
    r = _client().post("/api/content/plan", json={"script": "hello world", "target_duration": 60})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "plan" in body and body["plan"]["topic"] == "T"
    assert body["plan"]["scenes"][0]["narration"] == "hi"


def test_plan_endpoint_empty_script_422(monkeypatch):
    import app.features.content.router as mod
    monkeypatch.setattr(mod, "select_content_plan", lambda **k: None)
    r = _client().post("/api/content/plan", json={"script": "   "})
    assert r.status_code == 422


def test_plan_endpoint_ai_none_502(monkeypatch):
    import app.features.content.router as mod
    monkeypatch.setattr(mod, "select_content_plan", lambda **k: None)
    r = _client().post("/api/content/plan", json={"script": "real script here"})
    assert r.status_code == 502
