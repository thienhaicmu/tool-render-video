"""Sprint K-A — DELETE /api/settings/scores/{job_id} endpoint tests.

1. Returns {job_id, deleted} when rows exist.
2. Returns 404 when no rows found for job.
3. delete_job_scores repo swallows DB failure and returns 0.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_delete_returns_count_when_rows_exist():
    with patch("app.db.ab_scores_repo.delete_job_scores", return_value=3):
        resp = _client().delete("/api/settings/scores/job-abc")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == "job-abc"
    assert body["deleted"] == 3


def test_delete_returns_404_when_no_rows():
    with patch("app.db.ab_scores_repo.delete_job_scores", return_value=0):
        resp = _client().delete("/api/settings/scores/job-missing")
    assert resp.status_code == 404


def test_delete_job_scores_swallows_db_failure():
    from app.db.ab_scores_repo import delete_job_scores

    mock_conn = MagicMock()
    mock_conn.__enter__ = lambda s: s
    mock_conn.__exit__ = MagicMock(return_value=False)

    with patch("app.db.connection.db_conn", side_effect=RuntimeError("DB dead")):
        result = delete_job_scores("job-x")

    assert result == 0
