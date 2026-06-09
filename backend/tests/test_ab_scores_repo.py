"""Sprint G-3 — render_ab_scores repo unit tests.

All tests monkeypatch db_conn — no real DB required.

1. upsert_ab_score executes the INSERT SQL.
2. upsert_ab_score swallows DB failure (no raise).
3. list_channel_scores returns rows as dicts.
4. list_channel_scores returns [] on DB failure.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_mock_conn():
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def test_upsert_ab_score_executes_sql():
    from app.db.ab_scores_repo import upsert_ab_score

    mock_conn = _make_mock_conn()
    with patch("app.db.connection.db_conn", return_value=mock_conn):
        upsert_ab_score(
            job_id="j1", part_no=1, channel_code="manual",
            structure_bias="balanced",
            viral_score=75.0, hook_score=80.0, retention_score=70.0,
            output_rank_score=78.0, output_rank=1, is_best_output=True,
        )
    mock_conn.execute.assert_called_once()
    sql = mock_conn.execute.call_args[0][0]
    assert "INSERT INTO render_ab_scores" in sql


def test_upsert_ab_score_swallows_db_failure():
    from app.db.ab_scores_repo import upsert_ab_score

    with patch("app.db.connection.db_conn", side_effect=RuntimeError("DB dead")):
        # Must not raise
        upsert_ab_score(
            job_id="j1", part_no=1, channel_code="manual",
            structure_bias="balanced",
            viral_score=50.0, hook_score=50.0, retention_score=50.0,
            output_rank_score=50.0, output_rank=0, is_best_output=False,
        )


def test_list_channel_scores_returns_dicts():
    from app.db.ab_scores_repo import list_channel_scores

    row = {"job_id": "j1", "part_no": 1, "channel_code": "manual",
           "viral_score": 75.0, "hook_score": 80.0}
    mock_conn = _make_mock_conn()
    mock_conn.execute.return_value.fetchall.return_value = [row]

    with patch("app.db.connection.db_conn", return_value=mock_conn):
        result = list_channel_scores("manual")

    assert result == [dict(row)]


def test_list_channel_scores_returns_empty_on_failure():
    from app.db.ab_scores_repo import list_channel_scores

    with patch("app.db.connection.db_conn", side_effect=RuntimeError("DB dead")):
        result = list_channel_scores("manual")

    assert result == []
