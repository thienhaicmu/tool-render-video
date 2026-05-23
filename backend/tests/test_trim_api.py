"""
Tests for POST /api/jobs/{job_id}/parts/{part_no}/trim

Phase 6.8 — Apply Trim backend endpoint.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


# ── Helper stubs ───────────────────────────────────────────────────────────────

def _mock_get_job(job_id):
    return {"job_id": job_id, "status": "completed", "channel_code": "manual",
            "payload_json": "{}", "result_json": "{}"}


def _mock_list_parts(job_id):
    return [{"part_no": 1, "output_file": "/fake/output/part1.mp4", "status": "done"}]


def _mock_probe(path):
    return {"duration": 30.0, "fps": 30.0, "has_audio": True, "has_video": True, "width": 1080, "height": 1920}


# ── Valid trim ─────────────────────────────────────────────────────────────────

class TestTrimValid:
    def test_valid_trim_returns_200(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service.probe_video_metadata", side_effect=_mock_probe), \
             patch("app.services.editing_service.cut_video") as mock_cut, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            mock_cut.return_value = None
            # Patch probe again for the output file duration check
            with patch("app.services.editing_service._probe_duration", return_value=10.0), \
                 patch("pathlib.Path.mkdir"):
                resp = client.post(
                    "/api/jobs/test-job-001/parts/1/trim",
                    json={"start_sec": 5.0, "end_sec": 15.0, "output_mode": "new_job"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["job_id"] == "test-job-001"
        assert data["part_no"] == 1
        assert data["output_mode"] == "new_job"

    def test_trim_result_contains_expected_fields(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", side_effect=[30.0, 10.0]), \
             patch("app.services.editing_service.cut_video"), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s), \
             patch("pathlib.Path.mkdir"):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/trim",
                json={"start_sec": 2.0, "end_sec": 12.0},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "output_file" in data
        assert "duration_sec" in data
        assert "trim_start_sec" in data
        assert "trim_end_sec" in data

    def test_default_output_mode_is_new_job(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", side_effect=[30.0, 8.0]), \
             patch("app.services.editing_service.cut_video"), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s), \
             patch("pathlib.Path.mkdir"):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/trim",
                json={"start_sec": 0.0, "end_sec": 8.0},
            )
        assert resp.status_code == 200
        assert resp.json()["output_mode"] == "new_job"


# ── Invalid trim ───────────────────────────────────────────────────────────────

class TestTrimInvalid:
    def test_invalid_job_id_returns_400(self, client):
        resp = client.post(
            "/api/jobs/../etc/passwd/parts/1/trim",
            json={"start_sec": 0.0, "end_sec": 5.0},
        )
        # FastAPI normalises the path — job_id will fail validation or route won't match
        assert resp.status_code in (400, 404, 422)

    def test_bad_job_id_chars_returns_400(self, client):
        with patch("app.services.editing_service.get_job", return_value=None):
            resp = client.post(
                "/api/jobs/bad!job@id/parts/1/trim",
                json={"start_sec": 0.0, "end_sec": 5.0},
            )
        assert resp.status_code in (400, 404)

    def test_end_before_start_returns_400(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/trim",
                json={"start_sec": 15.0, "end_sec": 5.0},
            )
        assert resp.status_code == 400

    def test_duration_below_minimum_returns_400(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=30.0), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/trim",
                json={"start_sec": 5.0, "end_sec": 5.5},  # 0.5s < 1s minimum
            )
        assert resp.status_code == 400

    def test_missing_media_returns_404(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("pathlib.Path.exists", return_value=False), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/trim",
                json={"start_sec": 0.0, "end_sec": 5.0},
            )
        assert resp.status_code == 404

    def test_missing_job_returns_404(self, client):
        with patch("app.services.editing_service.get_job", return_value=None):
            resp = client.post(
                "/api/jobs/nonexistent/parts/1/trim",
                json={"start_sec": 0.0, "end_sec": 5.0},
            )
        assert resp.status_code == 404

    def test_missing_part_returns_404(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", return_value=[]):
            resp = client.post(
                "/api/jobs/test-job-001/parts/99/trim",
                json={"start_sec": 0.0, "end_sec": 5.0},
            )
        assert resp.status_code == 404

    def test_clamp_start_beyond_duration(self, client):
        """start_sec > duration gets clamped — end > clamped_start required."""
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._probe_duration", return_value=10.0), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/trim",
                json={"start_sec": 100.0, "end_sec": 200.0},
            )
        # Both clamped to 10.0 → clamped_end <= clamped_start → 400
        assert resp.status_code == 400

    def test_part_no_zero_returns_400(self, client):
        resp = client.post(
            "/api/jobs/test-job-001/parts/0/trim",
            json={"start_sec": 0.0, "end_sec": 5.0},
        )
        assert resp.status_code == 400

    def test_negative_end_sec_rejected_by_schema(self, client):
        resp = client.post(
            "/api/jobs/test-job-001/parts/1/trim",
            json={"start_sec": 0.0, "end_sec": -1.0},
        )
        assert resp.status_code == 422
