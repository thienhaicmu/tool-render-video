"""
tests/test_phase_s_job_report.py — Phase S: Job Export Report.

GET /api/jobs/{job_id}/report?format=json  (default)
GET /api/jobs/{job_id}/report?format=csv

Tests:
  - 404 when job not found
  - 422 on unknown format
  - JSON response has {job, parts} keys
  - job section has required metadata fields
  - part section has scoring and file fields
  - CSV response has text/csv content-type
  - CSV has header + one row per part
  - file_exists=False when output_file missing
  - file_size_bytes=0 when file missing
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)


_FAKE_JOB = {
    "job_id": "job-report-001",
    "kind": "render",
    "channel_code": "k1",
    "status": "completed",
    "stage": "DONE",
    "progress_percent": 100,
    "message": "Done",
    "payload_json": "{}",
    "result_json": '{"clips": [{"part_no": 1, "ai_title": "Best Moment", "ai_reason": "High energy"}]}',
    "created_at": "2026-06-13 10:00:00",
    "updated_at": "2026-06-13 10:30:00",
    "priority": 0,
    "error_kind": None,
    "asset_id": None,
    "render_plan_json": None,
}

_FAKE_PARTS = [
    {
        "job_id": "job-report-001",
        "part_no": 1,
        "part_name": "clip_001",
        "status": "done",
        "progress_percent": 100,
        "start_sec": 0.0,
        "end_sec": 45.0,
        "duration": 45.0,
        "viral_score": 0.85,
        "motion_score": 0.6,
        "hook_score": 0.9,
        "output_file": "",
        "message": "",
        "created_at": "2026-06-13 10:01:00",
        "updated_at": "2026-06-13 10:15:00",
    },
]

_FAKE_SCORES = {
    1: {
        "viral_score": 0.85,
        "hook_score": 0.90,
        "retention_score": 0.75,
        "output_rank": 1,
        "output_rank_score": 0.88,
        "is_best_output": True,
    }
}


def test_job_report_404_when_not_found(client):
    with patch("app.routes.job_report.get_job", return_value=None):
        resp = client.get("/api/jobs/nonexistent/report")
    assert resp.status_code == 404


def test_job_report_422_on_bad_format(client):
    with patch("app.routes.job_report.get_job", return_value=_FAKE_JOB):
        resp = client.get("/api/jobs/job-report-001/report?format=xml")
    assert resp.status_code == 422


def test_job_report_json_has_job_and_parts_keys(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "job" in data
    assert "parts" in data


def test_job_report_job_section_has_metadata(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report")
    job = resp.json()["job"]
    assert job["job_id"] == "job-report-001"
    assert job["status"] == "completed"
    assert job["channel_code"] == "k1"
    assert "created_at" in job
    assert "updated_at" in job


def test_job_report_parts_list_length(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report")
    assert len(resp.json()["parts"]) == 1


def test_job_report_part_has_scoring_fields(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value=_FAKE_SCORES),
    ):
        resp = client.get("/api/jobs/job-report-001/report")
    part = resp.json()["parts"][0]
    assert "viral_score" in part
    assert "hook_score" in part
    assert "retention_score" in part
    assert "output_rank" in part
    assert "output_rank_score" in part
    assert "is_best_output" in part


def test_job_report_part_has_timing_fields(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report")
    part = resp.json()["parts"][0]
    assert part["start_sec"] == 0.0
    assert part["end_sec"] == 45.0
    assert part["duration"] == 45.0


def test_job_report_part_ai_title_from_result_json(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report")
    part = resp.json()["parts"][0]
    assert part["ai_title"] == "Best Moment"
    assert part["ai_reason"] == "High energy"


def test_job_report_file_not_exists_when_output_empty(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report")
    part = resp.json()["parts"][0]
    assert part["file_exists"] is False
    assert part["file_size_bytes"] == 0


def test_job_report_csv_content_type(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report?format=csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]


def test_job_report_csv_has_header(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=_FAKE_PARTS),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report?format=csv")
    lines = resp.text.strip().splitlines()
    assert len(lines) >= 2
    header = lines[0]
    assert "job_id" in header
    assert "viral_score" in header


def test_job_report_csv_content_disposition(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=[]),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report?format=csv")
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_job_report_json_default_when_no_format_param(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=[]),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report")
    assert resp.status_code == 200
    assert resp.json()["job"]["job_id"] == "job-report-001"


def test_job_report_format_case_insensitive(client):
    with (
        patch("app.routes.job_report.get_job", return_value=_FAKE_JOB),
        patch("app.routes.job_report.list_job_parts", return_value=[]),
        patch("app.routes.job_report.list_ab_scores_for_job", return_value={}),
    ):
        resp = client.get("/api/jobs/job-report-001/report?format=CSV")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
