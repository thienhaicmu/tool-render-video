"""Sprint J-B — GET /api/settings/channels endpoint tests.

1. Returns list from list_channels.
2. Returns [] when no channels have score data.
3. list_channels repo function is called (no query params needed).
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_get_channels_returns_list():
    rows = [
        {"channel_code": "vn", "score_count": 12, "last_scored_at": "2026-06-09 10:00:00"},
        {"channel_code": "en", "score_count": 5,  "last_scored_at": "2026-06-08 09:00:00"},
    ]
    with patch("app.db.ab_scores_repo.list_channels", return_value=rows):
        resp = _client().get("/api/settings/channels")
    assert resp.status_code == 200
    assert resp.json() == rows


def test_get_channels_empty_when_no_data():
    with patch("app.db.ab_scores_repo.list_channels", return_value=[]):
        resp = _client().get("/api/settings/channels")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_channels_calls_repo():
    with patch("app.db.ab_scores_repo.list_channels", return_value=[]) as mock_fn:
        _client().get("/api/settings/channels")
    mock_fn.assert_called_once_with()
