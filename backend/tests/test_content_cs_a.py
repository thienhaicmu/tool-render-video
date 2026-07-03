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
    assert back.schema_version == 3  # CU-4 bumped v2 → v3 (StoryBible)
    assert back.video_style == "documentary"
    s = back.scenes[0]
    assert s.scene_title == "Mở màn"
    assert s.visual_prompt == "A cinematic Mars at sunrise, 4k"
    assert s.negative_prompt == "blurry, low quality"
    assert s.asset_suggestion == "ai_image"
    assert s.subtitle_style == "word_by_word"


def test_content_plan_cs_e_asset_fields_roundtrip():
    plan = ContentPlan(scenes=[
        ContentScene(index=0, narration="hi", visual_source="image",
                     visual_path="/tmp/pic.png", ken_burns=True),
    ])
    back = ContentPlan.from_json(plan.to_json())
    assert back is not None
    s = back.scenes[0]
    assert s.visual_source == "image" and s.visual_path == "/tmp/pic.png"
    assert s.ken_burns is True
    # ken_burns coerces from strings ("true"/"1") too
    from app.domain.content_plan import _scene_from_dict
    assert _scene_from_dict({"narration": "x", "ken_burns": "true"}, 0).ken_burns is True
    assert _scene_from_dict({"narration": "x", "ken_burns": "0"}, 0).ken_burns is False


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


# ── CS-D: narration preview endpoints ────────────────────────────────────────

def test_narration_preview_and_audio(monkeypatch, tmp_path):
    import app.features.content.router as mod
    # Redirect the preview dir into the test tmp so we don't touch the real cache.
    monkeypatch.setattr(mod, "_PREVIEW_DIR", tmp_path / "content_preview", raising=False)

    def _fake_tts(*, text, language, gender, rate, job_id, output_path, content_type, tts_engine):
        # write a tiny fake mp3 (bytes) to output_path
        from pathlib import Path as _P
        _P(output_path).parent.mkdir(parents=True, exist_ok=True)
        _P(output_path).write_bytes(b"ID3fakeaudio")
        return output_path
    monkeypatch.setattr(
        "app.features.render.engine.audio.tts.generate_narration_audio", _fake_tts,
    )
    monkeypatch.setattr(
        "app.features.render.engine.stages.content_scene_render.probe_audio_duration",
        lambda p: 1.5,
    )

    client = _client()
    r = client.post("/api/content/narration/preview", json={"text": "Xin chao", "voice_language": "vi-VN"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["duration_sec"] == 1.5
    assert body["url"].startswith("/api/content/narration/audio/")
    token = body["token"]

    # The audio GET serves the file.
    a = client.get(f"/api/content/narration/audio/{token}")
    assert a.status_code == 200 and a.content == b"ID3fakeaudio"


def test_narration_preview_empty_text_422():
    r = _client().post("/api/content/narration/preview", json={"text": "  "})
    assert r.status_code == 422


def test_narration_preview_tts_fail_502(monkeypatch, tmp_path):
    import app.features.content.router as mod
    monkeypatch.setattr(mod, "_PREVIEW_DIR", tmp_path / "p", raising=False)

    def _boom(**k):
        raise RuntimeError("no TTS")
    monkeypatch.setattr("app.features.render.engine.audio.tts.generate_narration_audio", _boom)
    r = _client().post("/api/content/narration/preview", json={"text": "hi"})
    assert r.status_code == 502


def test_narration_audio_bad_token_404():
    r = _client().get("/api/content/narration/audio/not-a-valid-token")
    assert r.status_code == 404


# ── CU-1: content project (draft) persistence ────────────────────────────────

def test_content_project_crud(monkeypatch, tmp_path):
    db = tmp_path / "app.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db, close_thread_conn
    init_db()
    try:
        client = _client()
        # create
        r = client.post("/api/content/projects", json={
            "title": "My Project", "script": "hello world",
            "plan": {"topic": "Mars", "scenes": [{"index": 0, "narration": "n"}]},
            "config": {"ratio": "r916"},
        })
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

        # get → JSON columns parsed back to objects
        g = client.get(f"/api/content/projects/{pid}").json()
        assert g["plan"]["topic"] == "Mars"
        assert g["config"]["ratio"] == "r916"
        assert g["status"] == "draft"

        # list → summary carries scene count
        summaries = client.get("/api/content/projects").json()["projects"]
        me = next(p for p in summaries if p["id"] == pid)
        assert me["scenes"] == 1 and me["topic"] == "Mars"

        # autosave / update (idempotent upsert)
        s = client.put(f"/api/content/projects/{pid}", json={
            "title": "Renamed", "script": "v2", "status": "rendered",
        })
        assert s.status_code == 200
        g2 = client.get(f"/api/content/projects/{pid}").json()
        assert g2["title"] == "Renamed" and g2["status"] == "rendered"

        # delete
        assert client.delete(f"/api/content/projects/{pid}").status_code == 200
        assert client.get(f"/api/content/projects/{pid}").status_code == 404
    finally:
        close_thread_conn()


def test_get_missing_project_404(monkeypatch, tmp_path):
    db = tmp_path / "app.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db, close_thread_conn
    init_db()
    try:
        assert _client().get("/api/content/projects/nope").status_code == 404
    finally:
        close_thread_conn()


# ── LOW-1: per-provider key on fallback ──────────────────────────────────────

def test_select_content_plan_resolves_key_per_provider(monkeypatch):
    captured = {}

    def _fake_gemini(**kw):
        captured["api_key"] = kw.get("api_key")
        return ContentPlan(scenes=[ContentScene(index=0, narration="x")])

    import app.features.render.ai.llm.providers.gemini as gem
    monkeypatch.setattr(gem, "select_content_plan", _fake_gemini)

    from app.features.render.ai.llm import select_content_plan
    # primary "openai" has no content impl → skipped; fallback reaches gemini,
    # which must receive the GEMINI key (not openai's).
    plan = select_content_plan(
        provider="openai", script="hello world",
        api_key="wrong-openai-key",
        resolve_key=lambda p: f"key-{p}",
    )
    assert plan is not None
    assert captured["api_key"] == "key-gemini"
