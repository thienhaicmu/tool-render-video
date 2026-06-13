"""
tests/test_phase_p_snapshot.py — Phase P: Job Snapshot endpoint.

GET /api/jobs/{job_id}/snapshot
  - 404 when job not found
  - Returns {job, parts, summary} shape mirroring WS event
  - summary always has required keys
  - parts is a list (empty when no parts)
  - job fields passed through unchanged
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
    "job_id": "job-snap-001",
    "kind": "render",
    "channel_code": "k1",
    "status": "running",
    "stage": "RENDERING",
    "progress_percent": 40,
    "message": "Rendering part 2",
    "payload_json": "{}",
    "result_json": None,
    "created_at": "2026-06-13 10:00:00",
    "updated_at": "2026-06-13 10:05:00",
    "priority": 0,
    "error_kind": None,
    "asset_id": None,
    "render_plan_json": None,
}

_FAKE_PARTS = [
    {
        "job_id": "job-snap-001",
        "part_no": 1,
        "part_name": "clip_001",
        "status": "done",
        "progress_percent": 100,
        "start_sec": 0.0,
        "end_sec": 30.0,
        "duration": 30.0,
        "viral_score": 0.8,
        "motion_score": 0.5,
        "hook_score": 0.7,
        "output_file": "/tmp/clip_001.mp4",
        "message": "",
        "created_at": "2026-06-13 10:01:00",
        "updated_at": "2026-06-13 10:04:00",
    },
    {
        "job_id": "job-snap-001",
        "part_no": 2,
        "part_name": "clip_002",
        "status": "rendering",
        "progress_percent": 40,
        "start_sec": 30.0,
        "end_sec": 60.0,
        "duration": 30.0,
        "viral_score": 0.0,
        "motion_score": 0.0,
        "hook_score": 0.0,
        "output_file": "",
        "message": "",
        "created_at": "2026-06-13 10:02:00",
        "updated_at": "2026-06-13 10:05:00",
    },
]


def test_snapshot_404_when_job_not_found(client):
    with patch("app.routes.snapshot.get_job", return_value=None):
        resp = client.get("/api/jobs/nonexistent-job/snapshot")
    assert resp.status_code == 404
    assert "Job not found" in resp.json()["detail"]


def test_snapshot_returns_three_top_level_keys(client):
    with (
        patch("app.routes.snapshot.get_job", return_value=_FAKE_JOB),
        patch("app.routes.snapshot.list_job_parts", return_value=_FAKE_PARTS),
    ):
        resp = client.get("/api/jobs/job-snap-001/snapshot")
    assert resp.status_code == 200
    data = resp.json()
    assert "job" in data
    assert "parts" in data
    assert "summary" in data


def test_snapshot_job_data_passthrough(client):
    with (
        patch("app.routes.snapshot.get_job", return_value=_FAKE_JOB),
        patch("app.routes.snapshot.list_job_parts", return_value=_FAKE_PARTS),
    ):
        resp = client.get("/api/jobs/job-snap-001/snapshot")
    assert resp.status_code == 200
    job = resp.json()["job"]
    assert job["job_id"] == "job-snap-001"
    assert job["status"] == "running"


def test_snapshot_parts_is_list(client):
    with (
        patch("app.routes.snapshot.get_job", return_value=_FAKE_JOB),
        patch("app.routes.snapshot.list_job_parts", return_value=_FAKE_PARTS),
    ):
        resp = client.get("/api/jobs/job-snap-001/snapshot")
    assert resp.status_code == 200
    assert isinstance(resp.json()["parts"], list)
    assert len(resp.json()["parts"]) == 2


def test_snapshot_empty_parts_when_no_parts(client):
    with (
        patch("app.routes.snapshot.get_job", return_value=_FAKE_JOB),
        patch("app.routes.snapshot.list_job_parts", return_value=[]),
    ):
        resp = client.get("/api/jobs/job-snap-001/snapshot")
    assert resp.status_code == 200
    data = resp.json()
    assert data["parts"] == []


def test_snapshot_summary_has_required_keys(client):
    with (
        patch("app.routes.snapshot.get_job", return_value=_FAKE_JOB),
        patch("app.routes.snapshot.list_job_parts", return_value=_FAKE_PARTS),
    ):
        resp = client.get("/api/jobs/job-snap-001/snapshot")
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    required_keys = {
        "total_parts", "completed_parts", "failed_parts", "pending_parts",
        "processing_parts", "in_progress_count", "active_parts",
        "current_part", "current_stage",
        "overall_progress_percent", "parts_percent",
    }
    for key in required_keys:
        assert key in summary, f"summary missing key: {key}"


def test_snapshot_summary_zero_when_no_parts(client):
    with (
        patch("app.routes.snapshot.get_job", return_value=_FAKE_JOB),
        patch("app.routes.snapshot.list_job_parts", return_value=[]),
    ):
        resp = client.get("/api/jobs/job-snap-001/snapshot")
    summary = resp.json()["summary"]
    assert summary["total_parts"] == 0
    assert summary["completed_parts"] == 0
    assert summary["overall_progress_percent"] == 0.0


def test_snapshot_summary_counts_completed_parts(client):
    with (
        patch("app.routes.snapshot.get_job", return_value=_FAKE_JOB),
        patch("app.routes.snapshot.list_job_parts", return_value=_FAKE_PARTS),
    ):
        resp = client.get("/api/jobs/job-snap-001/snapshot")
    summary = resp.json()["summary"]
    assert summary["total_parts"] == 2
    assert summary["completed_parts"] == 1


def test_snapshot_job_id_in_url_not_parts(client):
    """URL job_id is used for lookup — parts are already filtered by DB query."""
    other_job = {**_FAKE_JOB, "job_id": "job-other"}
    with (
        patch("app.routes.snapshot.get_job", return_value=other_job),
        patch("app.routes.snapshot.list_job_parts", return_value=[]),
    ):
        resp = client.get("/api/jobs/job-other/snapshot")
    assert resp.status_code == 200
    assert resp.json()["job"]["job_id"] == "job-other"
