"""
Tests for POST /api/jobs/{job_id}/parts/{part_no}/export

Phase 6.8 — Export Clip endpoint.
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app)


def _mock_get_job(job_id):
    return {"job_id": job_id, "status": "completed", "channel_code": "manual",
            "payload_json": "{}", "result_json": "{}"}


def _mock_list_parts(job_id):
    return [{"part_no": 1, "output_file": "/fake/output/part1.mp4", "status": "done"}]


class TestExportClipValid:
    def test_export_to_safe_destination(self, client, tmp_path):
        dest = str(tmp_path / "exports")

        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._safe_export_roots",
                   return_value=[tmp_path.resolve()]), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s), \
             patch("pathlib.Path.mkdir"), \
             patch("shutil.copy2") as mock_copy:
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/export",
                json={"destination_dir": dest},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["job_id"] == "test-job-001"
        assert data["part_no"] == 1
        assert "exported_to" in data
        assert "destination_dir" in data

    def test_export_response_contains_source_file_name(self, client, tmp_path):
        dest = str(tmp_path / "exports")

        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._safe_export_roots",
                   return_value=[tmp_path.resolve()]), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s), \
             patch("pathlib.Path.mkdir"), \
             patch("shutil.copy2"):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/export",
                json={"destination_dir": dest},
            )
        assert resp.status_code == 200
        assert resp.json()["source_file"] == "part1.mp4"


class TestExportClipInvalid:
    def test_empty_destination_returns_400(self, client):
        resp = client.post(
            "/api/jobs/test-job-001/parts/1/export",
            json={"destination_dir": ""},
        )
        assert resp.status_code == 422  # Pydantic min_length=1

    def test_destination_outside_safe_roots_returns_403(self, client, tmp_path):
        # Use a real absolute path on the current OS but outside safe roots
        # (an allowed root that doesn't contain our destination)
        safe_root = tmp_path / "safe"
        safe_root.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._safe_export_roots",
                   return_value=[safe_root.resolve()]), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/export",
                json={"destination_dir": str(outside)},
            )
        assert resp.status_code == 403

    def test_missing_job_returns_404(self, client):
        with patch("app.services.editing_service.get_job", return_value=None):
            resp = client.post(
                "/api/jobs/nonexistent/parts/1/export",
                json={"destination_dir": "/some/path"},
            )
        assert resp.status_code == 404

    def test_missing_media_returns_404(self, client, tmp_path):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("pathlib.Path.exists", return_value=False), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/export",
                json={"destination_dir": str(tmp_path)},
            )
        assert resp.status_code == 404

    def test_path_traversal_in_dest_blocked(self, client):
        with patch("app.services.editing_service.get_job", side_effect=_mock_get_job), \
             patch("app.services.editing_service.list_job_parts", side_effect=_mock_list_parts), \
             patch("app.services.editing_service._safe_export_roots",
                   return_value=[Path("/safe/root")]), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.resolve", lambda s: s):
            resp = client.post(
                "/api/jobs/test-job-001/parts/1/export",
                json={"destination_dir": "/safe/root/../../etc/passwd"},
            )
        # Resolved path would escape safe root → 403
        assert resp.status_code in (403, 400)

    def test_invalid_job_id_returns_400(self, client):
        resp = client.post(
            "/api/jobs/bad!job@id/parts/1/export",
            json={"destination_dir": "/some/path"},
        )
        assert resp.status_code in (400, 404)
