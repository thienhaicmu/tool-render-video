"""test_db_fallback_signal.py — Sprint 4.4.

Verifies the new fallback-detection helpers:
- is_fallback_active() reflects whether _resolve_db_path() picked a
  path different from the configured DATABASE_PATH.
- get_active_db_path() returns the resolved path.
- The /health endpoint exposes db_path and db_fallback_active.

Audit reference: docs/review/AUDIT_2026-06-02.md P2-B4.
"""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app)


def _reset_db_path(monkeypatch, db_path):
    """Force connection.py to use db_path instead of the real DATABASE_PATH."""
    import app.db.connection as conn
    monkeypatch.setattr(conn, "DATABASE_PATH", db_path)
    monkeypatch.setattr(conn, "_ACTIVE_DB_PATH", None)


class TestFallbackHelpers:
    def test_get_active_db_path_returns_path(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_active_db_path
        active = get_active_db_path()
        assert str(active).endswith("test.db")

    def test_is_fallback_active_false_when_primary_writable(self, tmp_path, monkeypatch):
        """Primary path is writable → no fallback engaged."""
        db_file = tmp_path / "primary.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import is_fallback_active, get_active_db_path
        # Trigger resolution
        _ = get_active_db_path()
        assert is_fallback_active() is False


class TestHealthEndpointDbFields:
    def test_health_exposes_db_path(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "db_path" in body, f"/health response missing db_path: {body}"
        assert isinstance(body["db_path"], str)

    def test_health_exposes_db_fallback_active(self):
        resp = client.get("/health")
        body = resp.json()
        assert "db_fallback_active" in body, (
            f"/health response missing db_fallback_active: {body}"
        )
        assert isinstance(body["db_fallback_active"], bool)

    def test_health_status_still_ok(self):
        """Additive enrichment must not break the existing 'status' contract."""
        resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"
        assert "ui_version" in body
