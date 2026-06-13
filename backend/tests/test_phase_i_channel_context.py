"""Phase I — Per-Channel Creator Context API QA tests.

Covers:
  - routes/channels_context.py:
    GET  /api/channels/{code}/context  — never 404, defaults when no row
    PUT  /api/channels/{code}/context  — persists and echoes back
    DELETE /api/channels/{code}/context — 200 when found, 404 when missing
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _empty_ctx():
    """Return a CreatorContext-like object that is_empty() returns True."""
    from app.domain.creator_context import CreatorContext
    return CreatorContext()


def _non_empty_ctx():
    from app.domain.creator_context import CreatorContext
    ctx = CreatorContext()
    ctx.channel_name = "Test Channel"  # channel_name is checked by is_empty()
    return ctx


# ── GET /api/channels/{code}/context ─────────────────────────────────────────

def test_get_channel_context_no_row_returns_200_not_configured():
    with patch("app.routes.channels_context.get_creator_context_for_channel",
               return_value=None):
        resp = _client().get("/api/channels/vn/context")

    assert resp.status_code == 200
    body = resp.json()
    assert "is_configured" in body
    assert body["is_configured"] is False


def test_get_channel_context_empty_row_returns_not_configured():
    ctx = _empty_ctx()
    with patch("app.routes.channels_context.get_creator_context_for_channel",
               return_value=ctx):
        resp = _client().get("/api/channels/vn/context")

    assert resp.status_code == 200
    assert resp.json()["is_configured"] is False


def test_get_channel_context_configured_row_returns_is_configured_true():
    ctx = _non_empty_ctx()
    with patch("app.routes.channels_context.get_creator_context_for_channel",
               return_value=ctx):
        resp = _client().get("/api/channels/vn/context")

    assert resp.status_code == 200
    assert resp.json()["is_configured"] is True


def test_get_channel_context_never_404():
    # Even for a channel that has never been configured — must return 200
    with patch("app.routes.channels_context.get_creator_context_for_channel",
               return_value=None):
        resp = _client().get("/api/channels/totally_new_channel/context")

    assert resp.status_code != 404
    assert resp.status_code == 200


def test_get_channel_context_has_creator_context_key():
    with patch("app.routes.channels_context.get_creator_context_for_channel",
               return_value=None):
        resp = _client().get("/api/channels/vn/context")

    body = resp.json()
    assert "creator_context" in body


# ── PUT /api/channels/{code}/context ─────────────────────────────────────────

def test_put_channel_context_persists_and_returns_envelope():
    ctx = _non_empty_ctx()
    with patch("app.routes.channels_context.upsert_creator_context_for_channel") as mock_upsert, \
         patch("app.routes.channels_context.get_creator_context_for_channel",
               return_value=ctx):
        resp = _client().put(
            "/api/channels/vn/context",
            json={"creator_name": "Test Creator"},
        )

    assert resp.status_code == 200
    mock_upsert.assert_called_once()
    body = resp.json()
    assert "is_configured" in body
    assert "creator_context" in body


def test_put_channel_context_empty_code_returns_422():
    # PUT to /api/channels/ %20 /context (whitespace only channel_code)
    with patch("app.routes.channels_context.upsert_creator_context_for_channel"):
        resp = _client().put(
            "/api/channels/   /context",
            json={},
        )

    assert resp.status_code == 422


# ── DELETE /api/channels/{code}/context ──────────────────────────────────────

def test_delete_channel_context_found_returns_200():
    with patch("app.routes.channels_context.delete_creator_context_for_channel",
               return_value=True):
        resp = _client().delete("/api/channels/vn/context")

    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["channel_code"] == "vn"


def test_delete_channel_context_not_found_returns_404():
    with patch("app.routes.channels_context.delete_creator_context_for_channel",
               return_value=False):
        resp = _client().delete("/api/channels/nonexistent/context")

    assert resp.status_code == 404


def test_delete_does_not_affect_global_singleton():
    """DELETE on channel context must not call the global singleton delete."""
    global_delete_called = []

    def mock_delete(code):
        global_delete_called.append(code)
        return True

    with patch("app.routes.channels_context.delete_creator_context_for_channel",
               side_effect=mock_delete):
        _client().delete("/api/channels/vn/context")

    # Only the per-channel delete should be invoked, not a global singleton path
    assert global_delete_called == ["vn"]
