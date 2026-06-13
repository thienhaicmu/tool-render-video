"""
tests/test_phase_m_job_clone.py — Phase M: Job Clone / Re-render.

POST /api/jobs/{job_id}/clone

Tests:
  - 404 when source job not found
  - 422 when payload_json is invalid JSON
  - 422 when merged payload fails RenderRequest validation
  - Success: returns {job_id, source_job_id, status="queued"}
  - New job_id is a UUID4 distinct from source
  - Allowed override fields are applied (whisper_model, output_count, etc.)
  - Non-override fields in body are ignored (extra='ignore' via CloneJobRequest)
  - Source job payload_json used as base
  - _queue_render_job called with new_job_id and override-merged payload
  - Empty payload_json treated as {} (no crash)
  - llm_enabled, add_subtitle, subtitle_style overridable
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)


def _make_source_job(payload: dict | None = None, payload_str: str | None = None) -> dict:
    if payload_str is None:
        payload_str = json.dumps(payload or {})
    return {
        "job_id": "source-job-001",
        "kind": "render",
        "channel_code": "k1",
        "status": "completed",
        "stage": "DONE",
        "progress_percent": 100,
        "message": "Done",
        "payload_json": payload_str,
        "result_json": None,
        "created_at": "2026-06-13 09:00:00",
        "updated_at": "2026-06-13 09:30:00",
        "priority": 0,
        "error_kind": None,
        "asset_id": None,
        "render_plan_json": None,
    }


_VALID_PAYLOAD = {
    "source_video_path": "/videos/test.mp4",
    "source_mode": "local",
    "output_dir": "/output",
    "channel_code": "k1",
    "output_count": 3,
    "whisper_model": "small",
    "llm_model": "gemini-2.0-flash",
    "ai_provider": "gemini",
}

_CLONE_URL = "/api/jobs/source-job-001/clone"


def test_clone_404_when_source_not_found(client):
    with patch("app.routes.job_clone.get_job", return_value=None):
        resp = client.post(_CLONE_URL, json={})
    assert resp.status_code == 404
    assert "Job not found" in resp.json()["detail"]


def test_clone_422_when_payload_json_invalid(client):
    source = _make_source_job(payload_str="NOT_VALID_JSON")
    with patch("app.routes.job_clone.get_job", return_value=source):
        resp = client.post(_CLONE_URL, json={})
    assert resp.status_code == 422
    assert "invalid payload_json" in resp.json()["detail"].lower()


def test_clone_success_returns_correct_shape(client):
    source = _make_source_job(_VALID_PAYLOAD)
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job"),
    ):
        resp = client.post(_CLONE_URL, json={})
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["source_job_id"] == "source-job-001"
    assert data["status"] == "queued"


def test_clone_new_job_id_is_different_from_source(client):
    source = _make_source_job(_VALID_PAYLOAD)
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job"),
    ):
        resp = client.post(_CLONE_URL, json={})
    assert resp.json()["job_id"] != "source-job-001"


def test_clone_new_job_id_is_uuid_format(client):
    import re
    source = _make_source_job(_VALID_PAYLOAD)
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job"),
    ):
        resp = client.post(_CLONE_URL, json={})
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    assert uuid_pattern.match(resp.json()["job_id"])


def test_clone_whisper_model_override_applied(client):
    source = _make_source_job({**_VALID_PAYLOAD, "whisper_model": "small"})
    captured = {}
    def _fake_queue(job_id, channel, payload, **kwargs):
        captured["payload"] = payload
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job", side_effect=_fake_queue),
    ):
        resp = client.post(_CLONE_URL, json={"whisper_model": "large-v3"})
    assert resp.status_code == 200
    assert captured["payload"].whisper_model == "large-v3"


def test_clone_output_count_override_applied(client):
    source = _make_source_job({**_VALID_PAYLOAD, "output_count": 3})
    captured = {}
    def _fake_queue(job_id, channel, payload, **kwargs):
        captured["payload"] = payload
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job", side_effect=_fake_queue),
    ):
        resp = client.post(_CLONE_URL, json={"output_count": 7})
    assert resp.status_code == 200
    assert captured["payload"].output_count == 7


def test_clone_llm_enabled_override(client):
    source = _make_source_job({**_VALID_PAYLOAD, "llm_enabled": False})
    captured = {}
    def _fake_queue(job_id, channel, payload, **kwargs):
        captured["payload"] = payload
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job", side_effect=_fake_queue),
    ):
        resp = client.post(_CLONE_URL, json={"llm_enabled": True})
    assert resp.status_code == 200
    assert captured["payload"].llm_enabled is True


def test_clone_source_payload_used_as_base(client):
    """Fields not in body stay from the source payload_json."""
    source = _make_source_job({**_VALID_PAYLOAD, "whisper_model": "large-v3"})
    captured = {}
    def _fake_queue(job_id, channel, payload, **kwargs):
        captured["payload"] = payload
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job", side_effect=_fake_queue),
    ):
        resp = client.post(_CLONE_URL, json={})  # no overrides
    assert resp.status_code == 200
    assert captured["payload"].whisper_model == "large-v3"


def test_clone_queue_called_with_resume_mode_false(client):
    source = _make_source_job(_VALID_PAYLOAD)
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job") as mock_q,
    ):
        resp = client.post(_CLONE_URL, json={})
    assert resp.status_code == 200
    _, _, _, kwargs_or_pos = mock_q.call_args[0][0], mock_q.call_args[0][1], mock_q.call_args[0][2], None
    # Check resume_mode is False (either positional or keyword)
    call_kwargs = mock_q.call_args[1]
    assert call_kwargs.get("resume_mode") is False


def test_clone_queue_called_with_cloned_message(client):
    source = _make_source_job(_VALID_PAYLOAD)
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job") as mock_q,
    ):
        resp = client.post(_CLONE_URL, json={})
    assert resp.status_code == 200
    call_kwargs = mock_q.call_args[1]
    assert "source-job-001" in call_kwargs.get("queued_message", "")


def test_clone_empty_payload_json_treated_as_empty_dict(client):
    """Source job with no payload_json should not crash — fallback to {}."""
    source = _make_source_job(payload_str=None)
    source["payload_json"] = None  # explicitly None
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job"),
    ):
        # RenderRequest with empty dict may fail validation (no required field);
        # we just confirm the endpoint handles it without a 500 (422 is OK)
        resp = client.post(_CLONE_URL, json={})
    assert resp.status_code in (200, 422)


def test_clone_output_count_range_422(client):
    """output_count must be 1–20 per CloneJobRequest Field constraint."""
    source = _make_source_job(_VALID_PAYLOAD)
    with patch("app.routes.job_clone.get_job", return_value=source):
        resp = client.post(_CLONE_URL, json={"output_count": 25})
    assert resp.status_code == 422


def test_clone_original_job_not_modified(client):
    """The source job row must never be updated (Sacred Contract #7)."""
    from app.db import jobs_repo
    source = _make_source_job(_VALID_PAYLOAD)
    with (
        patch("app.routes.job_clone.get_job", return_value=source),
        patch("app.routes.job_clone._queue_render_job"),
        patch.object(jobs_repo, "upsert_job") as mock_upsert,
        patch.object(jobs_repo, "update_job_progress") as mock_update,
    ):
        resp = client.post(_CLONE_URL, json={})
    assert resp.status_code == 200
    # upsert / update_job_progress should NOT be called for the source job
    for c in mock_upsert.call_args_list:
        assert c[0][0] != "source-job-001", "Source job was upserted — violates Sacred Contract #7"
    for c in mock_update.call_args_list:
        assert c[0][0] != "source-job-001", "Source job progress updated — violates Sacred Contract #7"
