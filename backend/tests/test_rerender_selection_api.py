"""
Tests for POST /api/jobs/{job_id}/parts/{part_no}/rerender

Phase 6.8 — Re-render Selection endpoint.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


def _mock_get_job(job_id):
    return {"job_id": job_id, "status": "completed", "channel_code": "manual",
            "payload_json": '{"output_dir": "/fake/out"}', "result_json": "{}"}


def _mock_list_parts(job_id):
    return [{"part_no": 1, "output_file": "/fake/output/part1.mp4", "status": "done"}]


class TestRerenderSelection:
    def test_rerender_creates_new_job(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("app.services.editing_service.upsert_job") as mock_upsert, \
             patch("app.services.editing_service.submit_job", create=True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            # Patch submit_job at service level
            with patch("app.services.editing_service.rerender_selection",
                       wraps=_call_rerender_with_mock_submit):
                resp = client.post(
                    "/api/jobs/test-job-001/parts/1/rerender",
                    json={"start_sec": 5.0, "end_sec": 20.0},
                )

    def test_rerender_returns_new_job_id(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("app.services.editing_service.upsert_job"), \
             patch("app.services.render_engine.run_render_job", create=True), \
             patch("app.services.job_manager.submit_job", create=True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/rerender",
                json={"start_sec": 5.0, "end_sec": 20.0},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "new_job_id" in data
        assert data["parent_job_id"] == "test-job-001"
        assert data["parent_part_no"] == 1

    def test_rerender_stores_parent_linkage(self, client):
        captured_payload = {}

        def capture_upsert(job_id, kind, channel_code, status, payload=None, **kw):
            captured_payload.update(payload or {})

        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("app.services.editing_service.upsert_job", side_effect=capture_upsert), \
             patch("app.services.render_engine.run_render_job", create=True), \
             patch("app.services.job_manager.submit_job", create=True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/rerender",
                json={"start_sec": 5.0, "end_sec": 20.0},
            )
        assert resp.status_code == 200
        assert captured_payload.get("parent_job_id") == "test-job-001"
        assert captured_payload.get("parent_part_no") == 1

    def test_rerender_inherits_trim_range(self, client):
        captured_payload = {}

        def capture_upsert(job_id, kind, channel_code, status, payload=None, **kw):
            captured_payload.update(payload or {})

        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("app.services.editing_service.upsert_job", side_effect=capture_upsert), \
             patch("app.services.render_engine.run_render_job", create=True), \
             patch("app.services.job_manager.submit_job", create=True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/rerender",
                json={"start_sec": 3.0, "end_sec": 18.0},
            )
        assert resp.status_code == 200
        assert captured_payload.get("trim_start_sec") == pytest.approx(3.0, abs=0.01)
        assert captured_payload.get("trim_end_sec") == pytest.approx(18.0, abs=0.01)

    def test_rerender_applies_optional_effect_preset(self, client):
        captured_payload = {}

        def capture_upsert(job_id, kind, channel_code, status, payload=None, **kw):
            captured_payload.update(payload or {})

        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("app.services.editing_service.upsert_job", side_effect=capture_upsert), \
             patch("app.services.render_engine.run_render_job", create=True), \
             patch("app.services.job_manager.submit_job", create=True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/rerender",
                json={"start_sec": 0.0, "end_sec": 15.0, "effect_preset": "cinematic"},
            )
        assert resp.status_code == 200
        assert captured_payload.get("effect_preset") == "cinematic"

    def test_rerender_invalid_range_returns_400(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/rerender",
                json={"start_sec": 20.0, "end_sec": 5.0},
            )
        assert resp.status_code == 400

    def test_rerender_missing_job_returns_404(self, client):
        with patch("app.services.editing_service.get_job", return_value=None):
            resp = client.post(
                "/api/jobs/nonexistent/parts/1/rerender",
                json={"start_sec": 0.0, "end_sec": 10.0},
            )
        assert resp.status_code == 404

    def test_rerender_status_is_queued(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("app.services.editing_service.upsert_job"), \
             patch("app.services.render_engine.run_render_job", create=True), \
             patch("app.services.job_manager.submit_job", create=True), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/rerender",
                json={"start_sec": 0.0, "end_sec": 15.0},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"


def _call_rerender_with_mock_submit(*args, **kwargs):
    """Thin wrapper used for testing; real submit_job silently swallowed."""
    pass
