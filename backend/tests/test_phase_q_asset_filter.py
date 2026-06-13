"""
tests/test_phase_q_asset_filter.py — Phase Q: Asset Search & Filter.

Tests for the extended list_assets() signature and the updated
GET /api/assets endpoint with optional filter params.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.assets_repo import list_assets
from app.domain.asset import Asset


@pytest.fixture()
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=True)


def _make_asset(**kwargs) -> Asset:
    defaults = {
        "asset_id": "asset-q-001",
        "file_path": "/videos/test.mp4",
        "original_url": "",
        "title": "Test Video",
        "duration_sec": 120.0,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "file_size_bytes": 500_000_000,
        "language": "en",
        "content_type": "vlog",
        "transcription_cache_path": None,
        "thumbnail_path": None,
        "created_at": "2026-06-13 10:00:00",
        "enriched_at": None,
    }
    defaults.update(kwargs)
    return Asset.from_row(defaults)


# ── list_assets() unit tests ───────────────────────────────────────────────────

def test_list_assets_no_filters_builds_no_where(tmp_path):
    """Calling list_assets() with no filters returns results without WHERE clause."""
    fake_asset = _make_asset()
    with patch("app.db.assets_repo.db_conn") as mock_ctx:
        conn = MagicMock()
        mock_ctx.return_value.__enter__ = lambda s: conn
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchall.return_value = []
        result = list_assets()
    assert isinstance(result, list)
    # Verify no WHERE clause injected when all filters are empty/zero
    call_sql = conn.execute.call_args[0][0]
    assert "WHERE" not in call_sql


def test_list_assets_content_type_filter_adds_where(tmp_path):
    with patch("app.db.assets_repo.db_conn") as mock_ctx:
        conn = MagicMock()
        mock_ctx.return_value.__enter__ = lambda s: conn
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchall.return_value = []
        list_assets(content_type="vlog")
    call_sql = conn.execute.call_args[0][0]
    call_params = conn.execute.call_args[0][1]
    assert "content_type = ?" in call_sql
    assert "vlog" in call_params


def test_list_assets_language_filter(tmp_path):
    with patch("app.db.assets_repo.db_conn") as mock_ctx:
        conn = MagicMock()
        mock_ctx.return_value.__enter__ = lambda s: conn
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchall.return_value = []
        list_assets(language="vi")
    call_sql = conn.execute.call_args[0][0]
    call_params = conn.execute.call_args[0][1]
    assert "language = ?" in call_sql
    assert "vi" in call_params


def test_list_assets_min_duration_filter(tmp_path):
    with patch("app.db.assets_repo.db_conn") as mock_ctx:
        conn = MagicMock()
        mock_ctx.return_value.__enter__ = lambda s: conn
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchall.return_value = []
        list_assets(min_duration=60.0)
    call_sql = conn.execute.call_args[0][0]
    call_params = conn.execute.call_args[0][1]
    assert "duration_sec >= ?" in call_sql
    assert 60.0 in call_params


def test_list_assets_max_duration_filter(tmp_path):
    with patch("app.db.assets_repo.db_conn") as mock_ctx:
        conn = MagicMock()
        mock_ctx.return_value.__enter__ = lambda s: conn
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchall.return_value = []
        list_assets(max_duration=300.0)
    call_sql = conn.execute.call_args[0][0]
    call_params = conn.execute.call_args[0][1]
    assert "duration_sec <= ?" in call_sql
    assert 300.0 in call_params


def test_list_assets_q_filter_uses_like(tmp_path):
    with patch("app.db.assets_repo.db_conn") as mock_ctx:
        conn = MagicMock()
        mock_ctx.return_value.__enter__ = lambda s: conn
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchall.return_value = []
        list_assets(q="cooking")
    call_sql = conn.execute.call_args[0][0]
    call_params = conn.execute.call_args[0][1]
    assert "title LIKE ?" in call_sql
    assert "%cooking%" in call_params


def test_list_assets_zero_min_duration_ignored(tmp_path):
    """min_duration=0 should NOT add a WHERE clause."""
    with patch("app.db.assets_repo.db_conn") as mock_ctx:
        conn = MagicMock()
        mock_ctx.return_value.__enter__ = lambda s: conn
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchall.return_value = []
        list_assets(min_duration=0.0)
    call_sql = conn.execute.call_args[0][0]
    assert "duration_sec >=" not in call_sql


def test_list_assets_combined_filters(tmp_path):
    with patch("app.db.assets_repo.db_conn") as mock_ctx:
        conn = MagicMock()
        mock_ctx.return_value.__enter__ = lambda s: conn
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        conn.execute.return_value.fetchall.return_value = []
        list_assets(content_type="interview", language="en", min_duration=30.0)
    call_sql = conn.execute.call_args[0][0]
    assert "content_type = ?" in call_sql
    assert "language = ?" in call_sql
    assert "duration_sec >= ?" in call_sql


# ── Route endpoint tests ───────────────────────────────────────────────────────

def test_get_assets_response_includes_filters_key(client):
    with patch("app.routes.assets.list_assets", return_value=[]):
        resp = client.get("/api/assets")
    assert resp.status_code == 200
    data = resp.json()
    assert "filters" in data
    assert "assets" in data


def test_get_assets_filters_echo_back_query_params(client):
    with patch("app.routes.assets.list_assets", return_value=[]):
        resp = client.get("/api/assets?content_type=vlog&language=vi&min_duration=30&q=cooking")
    assert resp.status_code == 200
    filters = resp.json()["filters"]
    assert filters["content_type"] == "vlog"
    assert filters["language"] == "vi"
    assert filters["min_duration"] == 30.0
    assert filters["q"] == "cooking"


def test_get_assets_limit_offset_echoed(client):
    with patch("app.routes.assets.list_assets", return_value=[]):
        resp = client.get("/api/assets?limit=50&offset=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["limit"] == 50
    assert data["offset"] == 10


def test_get_assets_limit_too_high_returns_422(client):
    resp = client.get("/api/assets?limit=501")
    assert resp.status_code == 422


def test_get_assets_limit_zero_returns_422(client):
    resp = client.get("/api/assets?limit=0")
    assert resp.status_code == 422


def test_get_assets_offset_negative_returns_422(client):
    resp = client.get("/api/assets?offset=-1")
    assert resp.status_code == 422


def test_get_assets_passes_filters_to_list_assets(client):
    with patch("app.routes.assets.list_assets", return_value=[]) as mock_list:
        client.get("/api/assets?content_type=tutorial&language=en&min_duration=60&max_duration=300&q=python")
    mock_list.assert_called_once_with(
        limit=100,
        offset=0,
        content_type="tutorial",
        language="en",
        min_duration=60.0,
        max_duration=300.0,
        q="python",
    )


def test_get_assets_returns_asset_list(client):
    fake = _make_asset(asset_id="asset-r1", title="My Video")
    with patch("app.routes.assets.list_assets", return_value=[fake]):
        resp = client.get("/api/assets")
    assert resp.status_code == 200
    assets = resp.json()["assets"]
    assert len(assets) == 1
    assert assets[0]["asset_id"] == "asset-r1"
    assert assets[0]["title"] == "My Video"
