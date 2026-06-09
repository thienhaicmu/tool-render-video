"""Sprint L-B — channel creator-context CRUD endpoint tests.

1. GET /api/settings/channels/creator-context returns list.
2. GET returns [] when none configured.
3. DELETE /api/settings/creator-context/{channel_code} returns 200 when found.
4. DELETE returns 404 when channel not found.
"""
from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def test_get_creator_context_channels_returns_list():
    with patch("app.db.creator_repo.list_creator_context_channels", return_value=["vn", "en"]):
        resp = _client().get("/api/settings/channels/creator-context")
    assert resp.status_code == 200
    assert resp.json() == ["vn", "en"]


def test_get_creator_context_channels_empty():
    with patch("app.db.creator_repo.list_creator_context_channels", return_value=[]):
        resp = _client().get("/api/settings/channels/creator-context")
    assert resp.status_code == 200
    assert resp.json() == []


def test_delete_creator_context_channel_found():
    with patch("app.db.creator_repo.delete_creator_context_for_channel", return_value=True):
        resp = _client().delete("/api/settings/creator-context/vn")
    assert resp.status_code == 200
    body = resp.json()
    assert body["channel_code"] == "vn"
    assert body["deleted"] is True


def test_delete_creator_context_channel_not_found():
    with patch("app.db.creator_repo.delete_creator_context_for_channel", return_value=False):
        resp = _client().delete("/api/settings/creator-context/unknown")
    assert resp.status_code == 404
