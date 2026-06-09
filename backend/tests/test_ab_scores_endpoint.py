"""Sprint H-1 — GET /api/settings/scores/{channel_code} endpoint tests.

1. Returns list from list_channel_scores.
2. limit is capped at 500.
3. Returns [] when channel has no scores.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_get_channel_scores_returns_list():
    rows = [{"job_id": "j1", "part_no": 1, "channel_code": "vn", "viral_score": 80.0}]
    with patch("app.db.ab_scores_repo.list_channel_scores", return_value=rows) as mock_fn:
        resp = _client().get("/api/settings/scores/vn")
    assert resp.status_code == 200
    assert resp.json() == rows
    mock_fn.assert_called_once_with("vn", limit=100, offset=0)


def test_get_channel_scores_limit_capped_at_500():
    with patch("app.db.ab_scores_repo.list_channel_scores", return_value=[]) as mock_fn:
        _client().get("/api/settings/scores/vn?limit=9999")
    mock_fn.assert_called_once_with("vn", limit=500, offset=0)


def test_get_channel_scores_empty_channel_returns_empty():
    with patch("app.db.ab_scores_repo.list_channel_scores", return_value=[]):
        resp = _client().get("/api/settings/scores/unknown_channel")
    assert resp.status_code == 200
    assert resp.json() == []
