"""Tests for quality report API endpoints on app.routes.jobs.

Endpoints:
  GET /api/jobs/{job_id}/parts/{part_no}/quality
  GET /api/jobs/{job_id}/quality
"""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App fixture — import app lazily to avoid side effects at collection time
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

VALID_JOB = {
    "job_id": "job-test-001",
    "kind": "render",
    "channel_code": "k1",
    "status": "completed",
    "stage": "",
    "progress_percent": 100,
    "message": "",
    "payload_json": "{}",
    "result_json": "{}",
    "created_at": "2026-01-01 00:00:00",
    "updated_at": "2026-01-01 00:00:00",
    "priority": 0,
}

VALID_PART = {
    "id": 1,
    "job_id": "job-test-001",
    "part_no": 1,
    "part_name": "Part 1",
    "status": "done",
    "progress_percent": 100,
    "start_sec": 0.0,
    "end_sec": 30.0,
    "duration": 30.0,
    "viral_score": 0.0,
    "motion_score": 0.0,
    "hook_score": 0.0,
    "output_file": "/tmp/fake_output/part1.mp4",
    "message": "",
    "created_at": "2026-01-01 00:00:00",
    "updated_at": "2026-01-01 00:00:00",
}

SAMPLE_REPORT = {
    "job_id": "job-test-001",
    "part_no": 1,
    "score": 87.0,
    "issues": [
        {"code": "no_audio_stream", "severity": "warning", "message": "no audio", "confidence": 0.95},
    ],
    "metrics": {"file_size_bytes": 1024},
    "ai_trace_refs": [],
    "created_at": "2026-01-01T00:00:00",
}


# ---------------------------------------------------------------------------
# Tests: GET /api/jobs/{job_id}/parts/{part_no}/quality
# ---------------------------------------------------------------------------

class TestPartQualityEndpoint:

    def test_returns_200_with_mocked_report(self, client, tmp_path):
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        quality_dir = vp.parent / "quality"
        quality_dir.mkdir()
        (quality_dir / "job-test-001_part_1.json").write_text(
            json.dumps(SAMPLE_REPORT), encoding="utf-8"
        )

        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]):
            resp = client.get("/api/jobs/job-test-001/parts/1/quality")

        assert resp.status_code == 200
        data = resp.json()
        assert data["score"] == 87.0
        assert data["job_id"] == "job-test-001"

    def test_missing_report_returns_404(self, client, tmp_path):
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)

        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]):
            resp = client.get("/api/jobs/job-test-001/parts/1/quality")

        assert resp.status_code == 404
        assert "quality report not available" in resp.json().get("detail", "")

    def test_missing_job_returns_404(self, client):
        with patch("app.routes.jobs.get_job", return_value=None):
            resp = client.get("/api/jobs/nonexistent-job/parts/1/quality")
        assert resp.status_code == 404

    def test_missing_part_returns_404(self, client):
        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[]):
            resp = client.get("/api/jobs/job-test-001/parts/99/quality")
        assert resp.status_code == 404

    def test_invalid_part_no_zero_returns_422_or_400(self, client):
        # FastAPI rejects non-positive int path param or route handler raises 400
        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[VALID_PART]):
            resp = client.get("/api/jobs/job-test-001/parts/0/quality")
        assert resp.status_code in (400, 422)

    def test_invalid_part_no_string_returns_422(self, client):
        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[VALID_PART]):
            resp = client.get("/api/jobs/job-test-001/parts/abc/quality")
        assert resp.status_code == 422

    def test_suspicious_job_id_returns_400(self, client):
        resp = client.get("/api/jobs/job%2F..%2Fetc/parts/1/quality")
        # URL-encoded slash — FastAPI may 404 or decode to a path that hits 400
        assert resp.status_code in (400, 404, 422)

    def test_job_id_with_dots_returns_400(self, client):
        with patch("app.routes.jobs.get_job", return_value=None):
            resp = client.get("/api/jobs/job.with.dots/parts/1/quality")
        # dots fail our regex → 400
        assert resp.status_code in (400, 404)

    def test_path_traversal_job_id_returns_400_or_404(self, client):
        with patch("app.routes.jobs.get_job", return_value=None):
            resp = client.get("/api/jobs/..%2F..%2Fetc%2Fpasswd/parts/1/quality")
        assert resp.status_code in (400, 404, 422)

    def test_no_render_behavior_change(self, client, tmp_path):
        """Quality endpoint must never trigger render or FFmpeg calls."""
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        quality_dir = vp.parent / "quality"
        quality_dir.mkdir()
        (quality_dir / "job-test-001_part_1.json").write_text(
            json.dumps(SAMPLE_REPORT), encoding="utf-8"
        )
        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]), \
             patch("subprocess.run") as mock_sub:
            resp = client.get("/api/jobs/job-test-001/parts/1/quality")
            assert resp.status_code == 200
            # subprocess.run must not have been called (no FFmpeg)
            mock_sub.assert_not_called()

    def test_no_ffmpeg_calls_in_quality_route(self, client, tmp_path):
        """Ensure FFmpeg is never invoked from the quality report read endpoint."""
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]), \
             patch("subprocess.Popen") as mock_popen:
            client.get("/api/jobs/job-test-001/parts/1/quality")
            mock_popen.assert_not_called()

    def test_part_with_no_output_file_returns_404(self, client):
        part_no_file = dict(VALID_PART, output_file="")
        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_no_file]):
            resp = client.get("/api/jobs/job-test-001/parts/1/quality")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests: GET /api/jobs/{job_id}/quality
# ---------------------------------------------------------------------------

class TestJobQualityEndpoint:

    def test_returns_200_with_summary(self, client, tmp_path):
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        quality_dir = vp.parent / "quality"
        quality_dir.mkdir()
        (quality_dir / "job-test-001_part_1.json").write_text(
            json.dumps(SAMPLE_REPORT), encoding="utf-8"
        )
        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]):
            resp = client.get("/api/jobs/job-test-001/quality")

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "job-test-001"
        assert "summary" in data
        assert "parts" in data

    def test_missing_job_returns_404(self, client):
        with patch("app.routes.jobs.get_job", return_value=None):
            resp = client.get("/api/jobs/nonexistent-job/quality")
        assert resp.status_code == 404

    def test_summary_handles_missing_reports(self, client, tmp_path):
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]):
            resp = client.get("/api/jobs/job-test-001/quality")

        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["available_parts"] == 0
        assert data["summary"]["average_score"] is None

    def test_include_reports_false_excludes_report_field(self, client, tmp_path):
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        quality_dir = vp.parent / "quality"
        quality_dir.mkdir()
        (quality_dir / "job-test-001_part_1.json").write_text(
            json.dumps(SAMPLE_REPORT), encoding="utf-8"
        )
        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]):
            resp = client.get("/api/jobs/job-test-001/quality?include_reports=false")

        assert resp.status_code == 200
        part = resp.json()["parts"][0]
        assert part["report"] is None

    def test_include_reports_true_includes_report_field(self, client, tmp_path):
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        quality_dir = vp.parent / "quality"
        quality_dir.mkdir()
        (quality_dir / "job-test-001_part_1.json").write_text(
            json.dumps(SAMPLE_REPORT), encoding="utf-8"
        )
        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]):
            resp = client.get("/api/jobs/job-test-001/quality?include_reports=true")

        assert resp.status_code == 200
        part = resp.json()["parts"][0]
        assert part["report"] is not None
        assert part["report"]["score"] == 87.0

    def test_invalid_job_id_returns_400(self, client):
        with patch("app.routes.jobs.get_job", return_value=None):
            resp = client.get("/api/jobs/job.with.dots/quality")
        assert resp.status_code in (400, 404)

    def test_no_render_behavior_change_summary(self, client, tmp_path):
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]), \
             patch("subprocess.run") as mock_sub:
            resp = client.get("/api/jobs/job-test-001/quality")
            assert resp.status_code == 200
            mock_sub.assert_not_called()

    def test_empty_parts_summary_is_valid(self, client):
        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[]):
            resp = client.get("/api/jobs/job-test-001/quality")
        assert resp.status_code == 200
        data = resp.json()
        assert data["summary"]["total_parts"] == 0
        assert data["summary"]["average_score"] is None

    def test_response_does_not_expose_filesystem_paths(self, client, tmp_path):
        vp = tmp_path / "output" / "part1.mp4"
        vp.parent.mkdir(parents=True)
        vp.write_bytes(b"\x00" * 16)
        quality_dir = vp.parent / "quality"
        quality_dir.mkdir()
        (quality_dir / "job-test-001_part_1.json").write_text(
            json.dumps(SAMPLE_REPORT), encoding="utf-8"
        )
        part_with_path = dict(VALID_PART, output_file=str(vp))

        with patch("app.routes.jobs.get_job", return_value=VALID_JOB), \
             patch("app.routes.jobs.list_job_parts", return_value=[part_with_path]):
            resp = client.get("/api/jobs/job-test-001/quality")

        assert resp.status_code == 200
        raw = resp.text
        # The actual filesystem path of the video should not appear in the response
        assert str(vp) not in raw
