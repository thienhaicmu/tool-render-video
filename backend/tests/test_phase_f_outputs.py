"""Phase F — Multi-Output Compare & Export QA tests.

Covers:
  - routes/outputs.py: _build_output_item, GET /api/jobs/{id}/outputs,
    GET /api/jobs/{id}/outputs/best, GET /api/jobs/{id}/outputs/export
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock


# ── _build_output_item ────────────────────────────────────────────────────────

def test_build_output_item_basic():
    from app.routes.outputs import _build_output_item

    part = {"part_no": 1, "part_name": "clip_001", "status": "DONE",
            "output_file": "", "start_sec": 0.0, "end_sec": 30.0,
            "duration": 30.0, "viral_score": 0.0, "hook_score": 0.0}
    scores: dict = {}

    item = _build_output_item(part, scores)
    assert item["part_no"] == 1
    assert item["status"] == "DONE"
    assert item["file_exists"] is False
    assert item["file_size_bytes"] == 0


def test_build_output_item_merges_scores():
    from app.routes.outputs import _build_output_item

    part = {"part_no": 2, "part_name": "clip_002", "status": "DONE",
            "output_file": "", "start_sec": 0.0, "end_sec": 10.0,
            "duration": 10.0, "viral_score": 50.0, "hook_score": 60.0}
    scores = {2: {"output_rank": 1, "output_rank_score": 78.5,
                  "is_best_output": True, "viral_score": 80.0,
                  "hook_score": 90.0, "retention_score": 70.0}}

    item = _build_output_item(part, scores)
    assert item["output_rank"] == 1
    assert item["output_rank_score"] == 78.5
    assert item["is_best_output"] is True
    assert item["viral_score"] == 80.0   # score row wins over part row


def test_build_output_item_file_exists(tmp_path):
    from app.routes.outputs import _build_output_item

    f = tmp_path / "out.mp4"
    f.write_bytes(b"x" * 1024)

    part = {"part_no": 1, "part_name": "", "status": "DONE",
            "output_file": str(f), "start_sec": 0.0, "end_sec": 5.0,
            "duration": 5.0, "viral_score": 0.0, "hook_score": 0.0}

    item = _build_output_item(part, {})
    assert item["file_exists"] is True
    assert item["file_size_bytes"] == 1024


# ── FastAPI route tests ───────────────────────────────────────────────────────

def _client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def _job_dict(job_id="j1"):
    return {"job_id": job_id, "status": "completed", "updated_at": "2026-01-01"}


def test_get_outputs_404_when_job_missing():
    with patch("app.routes.outputs.get_job", return_value=None):
        resp = _client().get("/api/jobs/missing/outputs")
    assert resp.status_code == 404


def test_get_outputs_200_with_empty_parts():
    with patch("app.routes.outputs.get_job", return_value=_job_dict()), \
         patch("app.routes.outputs.list_job_parts", return_value=[]), \
         patch("app.routes.outputs.list_ab_scores_for_job", return_value={}):
        resp = _client().get("/api/jobs/j1/outputs")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_parts"] == 0
    assert body["outputs"] == []


def test_get_outputs_sorted_ranked_first():
    with patch("app.routes.outputs.get_job", return_value=_job_dict()), \
         patch("app.routes.outputs.list_job_parts", return_value=[
             {"part_no": 1, "part_name": "", "status": "DONE",
              "output_file": "", "start_sec": 0, "end_sec": 10, "duration": 10,
              "viral_score": 0, "hook_score": 0},
             {"part_no": 2, "part_name": "", "status": "DONE",
              "output_file": "", "start_sec": 10, "end_sec": 20, "duration": 10,
              "viral_score": 0, "hook_score": 0},
         ]), \
         patch("app.routes.outputs.list_ab_scores_for_job", return_value={
             2: {"output_rank": 1, "output_rank_score": 90.0,
                 "is_best_output": True, "viral_score": 90.0,
                 "hook_score": 90.0, "retention_score": 80.0},
         }):
        resp = _client().get("/api/jobs/j1/outputs")

    assert resp.status_code == 200
    outputs = resp.json()["outputs"]
    # Part 2 has rank=1 so it should appear before part 1 (unranked)
    assert outputs[0]["part_no"] == 2


def test_get_best_output_404_when_no_ranked():
    with patch("app.routes.outputs.get_job", return_value=_job_dict()), \
         patch("app.routes.outputs.list_job_parts", return_value=[
             {"part_no": 1, "part_name": "", "status": "DONE",
              "output_file": "", "start_sec": 0, "end_sec": 10, "duration": 10,
              "viral_score": 0, "hook_score": 0},
         ]), \
         patch("app.routes.outputs.list_ab_scores_for_job", return_value={}):
        resp = _client().get("/api/jobs/j1/outputs/best")

    assert resp.status_code == 404


def test_get_best_output_returns_best_flagged_item():
    with patch("app.routes.outputs.get_job", return_value=_job_dict()), \
         patch("app.routes.outputs.list_job_parts", return_value=[
             {"part_no": 1, "part_name": "", "status": "DONE",
              "output_file": "", "start_sec": 0, "end_sec": 10, "duration": 10,
              "viral_score": 0, "hook_score": 0},
         ]), \
         patch("app.routes.outputs.list_ab_scores_for_job", return_value={
             1: {"output_rank": 1, "output_rank_score": 88.0,
                 "is_best_output": True, "viral_score": 80.0,
                 "hook_score": 85.0, "retention_score": 75.0},
         }):
        resp = _client().get("/api/jobs/j1/outputs/best")

    assert resp.status_code == 200
    assert resp.json()["is_best_output"] is True


def test_export_outputs_404_no_files():
    with patch("app.routes.outputs.get_job", return_value=_job_dict()), \
         patch("app.routes.outputs.list_job_parts", return_value=[
             {"part_no": 1, "part_name": "", "status": "DONE",
              "output_file": "/nonexistent/file.mp4",
              "start_sec": 0, "end_sec": 10, "duration": 10,
              "viral_score": 0, "hook_score": 0},
         ]), \
         patch("app.routes.outputs.list_ab_scores_for_job", return_value={}):
        resp = _client().get("/api/jobs/j1/outputs/export")

    assert resp.status_code == 404


def test_export_outputs_422_on_bad_part_nos():
    with patch("app.routes.outputs.get_job", return_value=_job_dict()), \
         patch("app.routes.outputs.list_job_parts", return_value=[]), \
         patch("app.routes.outputs.list_ab_scores_for_job", return_value={}):
        resp = _client().get("/api/jobs/j1/outputs/export?part_nos=abc,xyz")

    assert resp.status_code == 422


def test_export_outputs_streams_zip(tmp_path):
    f = tmp_path / "out.mp4"
    f.write_bytes(b"fake-mp4-content")

    with patch("app.routes.outputs.get_job", return_value=_job_dict()), \
         patch("app.routes.outputs.list_job_parts", return_value=[
             {"part_no": 1, "part_name": "", "status": "DONE",
              "output_file": str(f),
              "start_sec": 0, "end_sec": 10, "duration": 10,
              "viral_score": 0, "hook_score": 0},
         ]), \
         patch("app.routes.outputs.list_ab_scores_for_job", return_value={}):
        resp = _client().get("/api/jobs/j1/outputs/export")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers.get("content-disposition", "")
