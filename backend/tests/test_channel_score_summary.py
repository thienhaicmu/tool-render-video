"""Sprint J-A — GET /api/settings/scores/{channel_code}/summary endpoint tests.

1. Returns aggregate list from channel_score_summary.
2. Returns [] when channel has no score data.
3. channel_code path param is forwarded to repo.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_get_summary_returns_aggregates():
    rows = [
        {"structure_bias": "hook", "clip_count": 8, "avg_viral": 82.0,
         "avg_hook": 78.5, "avg_retention": 71.0, "avg_rank_score": 79.1,
         "best_output_count": 3},
        {"structure_bias": "balanced", "clip_count": 6, "avg_viral": 70.0,
         "avg_hook": 65.0, "avg_retention": 68.0, "avg_rank_score": 68.5,
         "best_output_count": 1},
    ]
    with patch("app.db.ab_scores_repo.channel_score_summary", return_value=rows):
        resp = _client().get("/api/settings/scores/vn/summary")
    assert resp.status_code == 200
    assert resp.json() == rows


def test_get_summary_empty_channel_returns_empty():
    with patch("app.db.ab_scores_repo.channel_score_summary", return_value=[]):
        resp = _client().get("/api/settings/scores/unknown/summary")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_summary_forwards_channel_code():
    with patch("app.db.ab_scores_repo.channel_score_summary", return_value=[]) as mock_fn:
        _client().get("/api/settings/scores/vn_edu/summary")
    mock_fn.assert_called_once_with("vn_edu", since=None)
