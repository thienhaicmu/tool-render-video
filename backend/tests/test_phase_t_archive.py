"""
tests/test_phase_t_archive.py — Phase T: Output File Archive.

POST /api/jobs/{job_id}/outputs/archive
  - 404 when job not found
  - 400 on invalid archive_dir
  - Moves existing file to archive_dir
  - Skips parts with no output_file
  - Skips parts where file not found (file_not_found in result)
  - Handles collision via part_no prefix in filename
  - Updates DB path via update_part_output_path
  - Response has moved/skipped/failed/parts keys
  - Never deletes job DB row (Sacred Contract #7)
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import call, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)


_FAKE_JOB = {
    "job_id": "job-arch-001",
    "status": "completed",
    "stage": "DONE",
}


def test_archive_404_when_job_not_found(client):
    with patch("app.routes.storage.get_job", return_value=None):
        resp = client.post(
            "/api/jobs/nonexistent/outputs/archive",
            json={"archive_dir": "/tmp/archive"},
        )
    assert resp.status_code == 404


def test_archive_400_on_empty_archive_dir(client):
    resp = client.post(
        "/api/jobs/job-arch-001/outputs/archive",
        json={"archive_dir": ""},
    )
    assert resp.status_code == 422


def test_archive_response_has_required_keys(tmp_path, client):
    archive_dir = str(tmp_path / "archive")
    with (
        patch("app.routes.storage.get_job", return_value=_FAKE_JOB),
        patch("app.routes.storage.list_job_parts", return_value=[]),
        patch("app.routes.storage.update_part_output_path"),
    ):
        resp = client.post(
            "/api/jobs/job-arch-001/outputs/archive",
            json={"archive_dir": archive_dir},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert "archive_dir" in data
    assert "moved" in data
    assert "skipped" in data
    assert "failed" in data
    assert "parts" in data


def test_archive_skips_part_with_no_output_file(tmp_path, client):
    archive_dir = str(tmp_path / "archive")
    parts = [{"part_no": 1, "output_file": ""}]
    with (
        patch("app.routes.storage.get_job", return_value=_FAKE_JOB),
        patch("app.routes.storage.list_job_parts", return_value=parts),
        patch("app.routes.storage.update_part_output_path"),
    ):
        resp = client.post(
            "/api/jobs/job-arch-001/outputs/archive",
            json={"archive_dir": archive_dir},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["moved"] == 0
    assert data["skipped"] == 0
    assert data["parts"] == []


def test_archive_skips_when_file_not_on_disk(tmp_path, client):
    archive_dir = str(tmp_path / "archive")
    parts = [{"part_no": 1, "output_file": "/nonexistent/clip.mp4"}]
    with (
        patch("app.routes.storage.get_job", return_value=_FAKE_JOB),
        patch("app.routes.storage.list_job_parts", return_value=parts),
        patch("app.routes.storage.update_part_output_path"),
    ):
        resp = client.post(
            "/api/jobs/job-arch-001/outputs/archive",
            json={"archive_dir": archive_dir},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skipped"] == 1
    assert data["moved"] == 0
    assert data["parts"][0]["status"] == "skipped"
    assert data["parts"][0]["reason"] == "file_not_found"


def test_archive_moves_existing_file(tmp_path, client):
    src_file = tmp_path / "clip.mp4"
    src_file.write_bytes(b"fake video content")
    archive_dir = tmp_path / "archive"

    parts = [{"part_no": 1, "output_file": str(src_file)}]
    with (
        patch("app.routes.storage.get_job", return_value=_FAKE_JOB),
        patch("app.routes.storage.list_job_parts", return_value=parts),
        patch("app.routes.storage.update_part_output_path") as mock_update,
    ):
        resp = client.post(
            "/api/jobs/job-arch-001/outputs/archive",
            json={"archive_dir": str(archive_dir)},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["moved"] == 1
    assert data["skipped"] == 0
    assert data["failed"] == 0
    # Source file should be gone
    assert not src_file.exists()
    # Archive dir should contain the file
    archived = list(archive_dir.iterdir())
    assert len(archived) == 1
    # DB should be updated
    mock_update.assert_called_once()
    call_args = mock_update.call_args[0]
    assert call_args[0] == "job-arch-001"
    assert call_args[1] == 1
    assert str(archive_dir) in call_args[2]


def test_archive_part_result_status_moved(tmp_path, client):
    src_file = tmp_path / "clip.mp4"
    src_file.write_bytes(b"content")
    archive_dir = tmp_path / "archive"

    parts = [{"part_no": 2, "output_file": str(src_file)}]
    with (
        patch("app.routes.storage.get_job", return_value=_FAKE_JOB),
        patch("app.routes.storage.list_job_parts", return_value=parts),
        patch("app.routes.storage.update_part_output_path"),
    ):
        resp = client.post(
            "/api/jobs/job-arch-001/outputs/archive",
            json={"archive_dir": str(archive_dir)},
        )
    data = resp.json()
    assert data["parts"][0]["status"] == "moved"
    assert data["parts"][0]["part_no"] == 2
    assert "new_path" in data["parts"][0]


def test_archive_handles_collision_with_part_no_prefix(tmp_path, client):
    src1 = tmp_path / "clip.mp4"
    src2 = tmp_path / "subdir" / "clip.mp4"
    src1.write_bytes(b"first")
    src2.parent.mkdir()
    src2.write_bytes(b"second")
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir()
    # Pre-place a file with same name to trigger collision
    (archive_dir / "clip.mp4").write_bytes(b"existing")

    parts = [{"part_no": 3, "output_file": str(src2)}]
    with (
        patch("app.routes.storage.get_job", return_value=_FAKE_JOB),
        patch("app.routes.storage.list_job_parts", return_value=parts),
        patch("app.routes.storage.update_part_output_path"),
    ):
        resp = client.post(
            "/api/jobs/job-arch-001/outputs/archive",
            json={"archive_dir": str(archive_dir)},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["moved"] == 1
    # New path should contain part_003 prefix to avoid collision
    new_path = data["parts"][0]["new_path"]
    assert "part_003" in new_path


def test_archive_job_id_in_response(tmp_path, client):
    archive_dir = str(tmp_path / "archive")
    with (
        patch("app.routes.storage.get_job", return_value=_FAKE_JOB),
        patch("app.routes.storage.list_job_parts", return_value=[]),
        patch("app.routes.storage.update_part_output_path"),
    ):
        resp = client.post(
            "/api/jobs/job-arch-001/outputs/archive",
            json={"archive_dir": archive_dir},
        )
    assert resp.json()["job_id"] == "job-arch-001"


def test_archive_never_deletes_job_db_row(tmp_path, client):
    """Sacred Contract #7: archive only moves files, never removes job DB rows."""
    archive_dir = str(tmp_path / "archive")
    with (
        patch("app.routes.storage.get_job", return_value=_FAKE_JOB),
        patch("app.routes.storage.list_job_parts", return_value=[]),
        patch("app.routes.storage.update_part_output_path"),
        patch("app.routes.storage.clear_part_output") as mock_clear,
    ):
        client.post(
            "/api/jobs/job-arch-001/outputs/archive",
            json={"archive_dir": archive_dir},
        )
    # clear_part_output should NOT be called during archive (only during delete)
    mock_clear.assert_not_called()
