"""Sprint K-A — score endpoint pagination tests.

1. offset param is forwarded to list_channel_scores.
2. limit is still capped at 500.
3. Negative offset is clamped to 0.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_offset_forwarded_to_repo():
    with patch("app.db.ab_scores_repo.list_channel_scores", return_value=[]) as mock_fn:
        _client().get("/api/settings/scores/vn?limit=10&offset=20")
    mock_fn.assert_called_once_with("vn", limit=10, offset=20)


def test_limit_still_capped_at_500():
    with patch("app.db.ab_scores_repo.list_channel_scores", return_value=[]) as mock_fn:
        _client().get("/api/settings/scores/vn?limit=9999&offset=0")
    mock_fn.assert_called_once_with("vn", limit=500, offset=0)


def test_negative_offset_clamped_to_zero():
    with patch("app.db.ab_scores_repo.list_channel_scores", return_value=[]) as mock_fn:
        _client().get("/api/settings/scores/vn?offset=-5")
    mock_fn.assert_called_once_with("vn", limit=100, offset=0)
