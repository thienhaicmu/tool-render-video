"""Tests for GET/PUT /api/settings/output-dir.

Covers:
1. GET on a fresh DB returns ``{is_configured: False, output_dir: {path: ""}}``.
2. PUT persists the path and the next GET reads it back.
3. PUT with an empty path clears the setting (is_configured → False).
4. Output-dir writes do not clobber other prefs keys (creator_context,
   data_retention).
5. Repo helper returns None when the key has never been written.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _client(tmp_path, monkeypatch):
    """Isolated tmp DB + just the settings router mounted."""
    db_path = tmp_path / "settings.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()

    from fastapi import FastAPI
    from app.routes.settings import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. GET on a fresh DB returns defaults
# ---------------------------------------------------------------------------


def test_get_output_dir_returns_default_on_fresh_db(_client):
    resp = _client.get("/api/settings/output-dir")
    assert resp.status_code == 200
    assert resp.json() == {
        "is_configured": False,
        "output_dir": {"path": ""},
    }


# ---------------------------------------------------------------------------
# 2. Round-trip: PUT then GET
# ---------------------------------------------------------------------------


def test_put_then_get_round_trips_path(_client):
    put_resp = _client.put(
        "/api/settings/output-dir",
        json={"path": "D:/Videos/Output"},
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == {
        "is_configured": True,
        "output_dir": {"path": "D:/Videos/Output"},
    }

    get_resp = _client.get("/api/settings/output-dir")
    assert get_resp.json()["output_dir"]["path"] == "D:/Videos/Output"
    assert get_resp.json()["is_configured"] is True


# ---------------------------------------------------------------------------
# 3. PUT empty path clears the setting
# ---------------------------------------------------------------------------


def test_put_empty_path_clears_setting(_client):
    # First set a value.
    _client.put("/api/settings/output-dir", json={"path": "D:/Videos/Output"})

    # Then clear it.
    resp = _client.put("/api/settings/output-dir", json={"path": ""})
    assert resp.status_code == 200
    assert resp.json() == {
        "is_configured": False,
        "output_dir": {"path": ""},
    }

    get_resp = _client.get("/api/settings/output-dir")
    assert get_resp.json()["is_configured"] is False


# ---------------------------------------------------------------------------
# 4. Coexistence with other prefs keys
# ---------------------------------------------------------------------------


def test_output_dir_does_not_clobber_creator_context(_client):
    """output_dir and creator_context share the same prefs_json blob.
    Writing one must not overwrite the other."""
    _client.put(
        "/api/settings/creator-context",
        json={"channel_name": "MyChannel", "brand_voice": "educational"},
    )
    _client.put("/api/settings/output-dir", json={"path": "D:/Out"})

    cc = _client.get("/api/settings/creator-context").json()
    assert cc["creator_context"]["channel_name"] == "MyChannel"
    assert cc["is_configured"] is True

    od = _client.get("/api/settings/output-dir").json()
    assert od["output_dir"]["path"] == "D:/Out"


def test_output_dir_does_not_clobber_data_retention(_client):
    _client.put("/api/settings/data-retention", json={"job_retention_days": 30})
    _client.put("/api/settings/output-dir", json={"path": "D:/Out"})

    dr = _client.get("/api/settings/data-retention").json()
    assert dr["data_retention"]["job_retention_days"] == 30

    od = _client.get("/api/settings/output-dir").json()
    assert od["output_dir"]["path"] == "D:/Out"


# ---------------------------------------------------------------------------
# 5. Repo helper returns None when not set
# ---------------------------------------------------------------------------


def test_repo_returns_none_when_not_set(_client):
    """Distinguishes 'never configured' from an explicit empty-string path."""
    from app.db.creator_repo import get_default_output_dir

    assert get_default_output_dir() is None
