"""Sprint K-B — Whisper per-channel tests.

1. get_whisper_model_for_channel returns None when no row exists.
2. get_whisper_model_for_channel returns model when row exists.
3. upsert_whisper_model_for_channel writes model into prefs_json.
4. GET /api/settings/whisper/{channel_code} returns model or null.
5. PUT /api/settings/whisper/{channel_code} saves and returns model.

Note: creator_repo.py imports db_conn at the module level, so tests must
patch at app.db.creator_repo.db_conn (not app.db.connection.db_conn).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_conn(row=None):
    """Return a context-manager mock for db_conn().

    row: None → fetchone() returns None; dict → fetchone() returns that dict.
    """
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.fetchone.return_value = row
    return conn


def _client():
    from app.main import app
    return TestClient(app)


# 1. No row → None
def test_get_whisper_model_no_row_returns_none():
    from app.db.creator_repo import get_whisper_model_for_channel
    with patch("app.db.creator_repo.db_conn", return_value=_make_conn(None)):
        result = get_whisper_model_for_channel("vn")
    assert result is None


# 2. Row with model → returns model string
def test_get_whisper_model_row_exists_returns_model():
    from app.db.creator_repo import get_whisper_model_for_channel
    row = {"prefs_json": json.dumps({"whisper_model": "small"})}
    with patch("app.db.creator_repo.db_conn", return_value=_make_conn(row)):
        result = get_whisper_model_for_channel("vn")
    assert result == "small"


# 3. upsert writes model into prefs_json — verify INSERT params contain it
def test_upsert_whisper_model_writes_model():
    from app.db.creator_repo import upsert_whisper_model_for_channel
    written = []

    def _fake_conn():
        conn = MagicMock()
        conn.__enter__ = lambda s: s
        conn.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchone.return_value = None

        def _capture(sql, params=None):
            if params and len(params) >= 2:
                try:
                    data = json.loads(params[1])
                    if "whisper_model" in data:
                        written.append(data["whisper_model"])
                except Exception:
                    pass
            return conn.execute.return_value

        conn.execute.side_effect = _capture
        return conn

    with patch("app.db.creator_repo.db_conn", side_effect=_fake_conn):
        upsert_whisper_model_for_channel("vn", "large-v3")

    assert "large-v3" in written


# 4. GET endpoint returns model or null
def test_get_endpoint_returns_model():
    with patch("app.db.creator_repo.get_whisper_model_for_channel", return_value="medium"):
        resp = _client().get("/api/settings/whisper/vn")
    assert resp.status_code == 200
    body = resp.json()
    assert body["channel_code"] == "vn"
    assert body["whisper_model"] == "medium"


# 5. PUT endpoint saves and returns model
def test_put_endpoint_saves_model():
    with patch("app.db.creator_repo.upsert_whisper_model_for_channel") as mock_upsert, \
         patch("app.db.creator_repo.get_whisper_model_for_channel", return_value="small"):
        resp = _client().put(
            "/api/settings/whisper/vn",
            json={"whisper_model": "small"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["whisper_model"] == "small"
    mock_upsert.assert_called_once_with("vn", "small")
