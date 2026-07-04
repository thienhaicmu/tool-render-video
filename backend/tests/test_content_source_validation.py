"""Route-level validation tests for Content-mode renders (2026-07-04).

Closes the test gap behind BUG-1: the existing content tests call ``run_content``
/ ``process_render`` DIRECTLY, bypassing the ``/api/render/process`` route's
``_validate_render_source``. That validator required ``source_video_path``
UNCONDITIONALLY, so every real Content-mode HTTP request failed with
``400 "source_video_path is required when source_mode='local'"`` — Content mode
has no source video (its "source" is the script). These tests exercise the REAL
validator through the route (only the queue submit is stubbed), so the bug can
never regress, and assert the case-aware branches:

  · content + script + no video   → accepted (BUG-1 regression)
  · content + empty script/plan   → 400 (needs a script)
  · content + image bg, no path   → 400 (pick a file / use Color)
  · content + image bg, bad path  → 400 (not found on disk)
  · clips + no source video       → 400 (unchanged — didn't break clips/recap)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _client(tmp_path, monkeypatch):
    """Mount only the render router with a temp DB + writable output dir, and
    stub the queue submit so a passing request never starts a real render. The
    source validator is DELIBERATELY NOT patched — it is the unit under test."""
    db_path = tmp_path / "content_val.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()

    monkeypatch.setattr("app.core.config.CHANNELS_DIR", tmp_path / "channels", raising=False)
    monkeypatch.setattr("app.core.config.TEMP_DIR", tmp_path / "tmp", raising=False)
    (tmp_path / "channels").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tmp").mkdir(parents=True, exist_ok=True)

    from fastapi import FastAPI
    from app.features.render.router import router as render_router

    app = FastAPI()
    app.include_router(render_router)

    # Stub the enqueue so we validate the wire+source layer WITHOUT rendering.
    from app.features.render.routers import lifecycle, _common as common_mod

    def _no_op_enqueue(job_id, channel, payload, resume_mode=False, queued_message=""):
        return None

    monkeypatch.setattr(lifecycle, "_queue_render_job", _no_op_enqueue)
    monkeypatch.setattr(common_mod, "_queue_render_job", _no_op_enqueue)
    monkeypatch.setattr(lifecycle, "_validate_text_layers_or_400", lambda p: [])

    return TestClient(app), tmp_path


def _content_payload(out_dir, **over):
    body = {
        "source_mode": "local",
        "source_video_path": "",            # content has NO source video
        "render_format": "content",
        "content_script": "Một câu chuyện ngắn về lòng biết ơn với mẹ.",
        "content_background_kind": "color",
        "content_background_value": "#101820",
        "content_visual_provider": "local",
        "output_dir": str(out_dir),
        "aspect_ratio": "9:16",
        "target_duration": 60,
        "add_subtitle": True,
    }
    body.update(over)
    return body


def test_content_render_without_source_video_is_accepted(_client):
    """BUG-1 regression: a content render with no source_video_path must NOT be
    rejected — the script is the source."""
    client, tmp = _client
    resp = client.post("/api/render/process", json=_content_payload(tmp / "out"))
    assert resp.status_code == 200, f"content render rejected: {resp.status_code} {resp.text}"
    body = resp.json()
    assert "job_id" in body and body["status"] == "queued"


def test_content_empty_script_and_plan_rejected(_client):
    client, tmp = _client
    resp = client.post("/api/render/process",
                       json=_content_payload(tmp / "out", content_script="   "))
    assert resp.status_code == 400
    assert "content_script is required" in resp.text


def test_content_image_background_without_path_rejected(_client):
    client, tmp = _client
    resp = client.post("/api/render/process", json=_content_payload(
        tmp / "out", content_background_kind="image", content_background_value=""))
    assert resp.status_code == 400
    assert "background" in resp.text.lower()


def test_content_image_background_missing_file_rejected(_client):
    client, tmp = _client
    resp = client.post("/api/render/process", json=_content_payload(
        tmp / "out", content_background_kind="image",
        content_background_value=str(tmp / "nope" / "missing.png")))
    assert resp.status_code == 400
    assert "not found" in resp.text.lower()


def test_clips_still_requires_source_video(_client):
    """Guard: the case-aware split must NOT loosen clips/recap validation."""
    client, tmp = _client
    body = _content_payload(tmp / "out")
    body["render_format"] = "clips"
    body["source_video_path"] = ""
    resp = client.post("/api/render/process", json=body)
    assert resp.status_code == 400
    assert "source_video_path is required" in resp.text
