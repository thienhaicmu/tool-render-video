"""Sprint H-3 — update_feedback_rating repo + PATCH endpoint tests.

1. update_feedback_rating returns True when row exists (rowcount > 0).
2. update_feedback_rating returns False on DB failure (exception swallowed).
3. PATCH /api/settings/scores/{job_id}/{part_no}/rating returns 404 when row absent.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_mock_conn():
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def test_update_feedback_rating_returns_true_when_row_exists():
    from app.db.ab_scores_repo import update_feedback_rating

    mock_conn = _make_mock_conn()
    mock_conn.execute.return_value.rowcount = 1

    with patch("app.db.connection.db_conn", return_value=mock_conn):
        result = update_feedback_rating(job_id="j1", part_no=1, rating=4)

    assert result is True


def test_update_feedback_rating_returns_false_on_db_failure():
    from app.db.ab_scores_repo import update_feedback_rating

    with patch("app.db.connection.db_conn", side_effect=RuntimeError("DB dead")):
        result = update_feedback_rating(job_id="j1", part_no=1, rating=3)

    assert result is False


def test_patch_rating_returns_404_when_row_absent():
    from app.main import app

    with patch("app.db.ab_scores_repo.update_feedback_rating", return_value=False):
        resp = TestClient(app).patch(
            "/api/settings/scores/j1/1/rating",
            json={"rating": 5},
        )
    assert resp.status_code == 404
