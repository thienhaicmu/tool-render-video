"""Sprint F-1 — output_dir persistence in /resume and /retry endpoints.

1. /resume calls upsert_default_output_dir with the stored payload's output_dir.
2. /retry  calls upsert_default_output_dir with the stored payload's output_dir.
3. If upsert raises the endpoint still succeeds (exception swallowed).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def _make_job_row(output_dir: str = "/video/out") -> dict:
    payload = {
        "source_mode": "local",
        "source_video_path": "/tmp/v.mp4",
        "output_dir": output_dir,
    }
    return {
        "job_id": "test-job-id",
        "status": "interrupted",
        "stage": "DONE",
        "kind": "render",
        "channel_code": "manual",
        "progress_percent": 50,
        "message": "interrupted",
        "payload_json": json.dumps(payload),
        "result_json": "{}",
    }


def _make_part_row(status: str = "failed") -> dict:
    return {"part_no": 1, "status": status}


def test_resume_upserts_output_dir(monkeypatch):
    job_row = _make_job_row("/video/out")
    monkeypatch.setattr("app.features.render.routers.lifecycle.get_job", lambda jid: job_row)
    monkeypatch.setattr("app.features.render.routers.lifecycle._validate_render_source", lambda p: None)
    monkeypatch.setattr("app.features.render.routers.lifecycle._queue_render_job", lambda *a, **kw: None)

    upserted = []
    with patch("app.db.creator_repo.upsert_default_output_dir", side_effect=lambda p: upserted.append(p)):
        from app.features.render.routers.lifecycle import resume_render_job
        resume_render_job("test-job-id")

    assert upserted == ["/video/out"]


def test_retry_upserts_output_dir(monkeypatch):
    job_row = _make_job_row("/retry/out")
    monkeypatch.setattr("app.features.render.routers.lifecycle.get_job", lambda jid: job_row)
    monkeypatch.setattr("app.features.render.routers.lifecycle.list_job_parts", lambda jid: [_make_part_row()])
    monkeypatch.setattr("app.features.render.routers.lifecycle._validate_render_source", lambda p: None)
    monkeypatch.setattr("app.features.render.routers.lifecycle._queue_render_job", lambda *a, **kw: None)

    upserted = []
    with patch("app.db.creator_repo.upsert_default_output_dir", side_effect=lambda p: upserted.append(p)):
        from app.features.render.routers.lifecycle import retry_failed_parts
        retry_failed_parts("test-job-id")

    assert upserted == ["/retry/out"]


def test_resume_upsert_failure_does_not_fail_endpoint(monkeypatch):
    job_row = _make_job_row("/video/out")
    monkeypatch.setattr("app.features.render.routers.lifecycle.get_job", lambda jid: job_row)
    monkeypatch.setattr("app.features.render.routers.lifecycle._validate_render_source", lambda p: None)
    monkeypatch.setattr("app.features.render.routers.lifecycle._queue_render_job", lambda *a, **kw: None)

    with patch("app.db.creator_repo.upsert_default_output_dir", side_effect=RuntimeError("DB dead")):
        from app.features.render.routers.lifecycle import resume_render_job
        result = resume_render_job("test-job-id")

    assert result["status"] == "queued"
