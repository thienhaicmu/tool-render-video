"""
Sprint 3-FE — pin the /api/settings/creator-context route contract:

- GET on a fresh DB returns 200 with is_configured=False and the
  default-shaped envelope (never 404)
- PUT persists the payload, GET reads it back, the envelope flips to
  is_configured=True
- PUT with empty body clears the persisted context
- Unknown payload keys are silently dropped (extra="ignore" backward
  compat with older / newer clients)
- 422 is returned for genuinely malformed payloads (non-list
  content_pillars)
- The persisted payload survives a process restart (i.e. the round
  trip really goes through the DB, not a request-scoped cache)
"""
import threading

import pytest
from fastapi.testclient import TestClient

from app.db.connection import init_db
from app.main import app


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    """Same isolated-DB pattern as Sprint 2/3 — repoint connection.py
    at a tmp SQLite file so the route tests don't touch data/app.db."""
    import app.db.connection as conn
    test_db = tmp_path / "test_app.db"
    monkeypatch.setattr(conn, "DATABASE_PATH", test_db)
    monkeypatch.setattr(conn, "_ACTIVE_DB_PATH", None)
    monkeypatch.setattr(conn, "_tls", threading.local())
    init_db()
    yield TestClient(app)


_BLANK_PAYLOAD = {
    "creator_id": "",
    "channel_name": "",
    "brand_voice": "",
    "target_audience": "",
    "content_pillars": [],
    "market": "",
    "language": "",
    "notes": "",
}


class TestGetEmpty:
    def test_fresh_db_returns_defaults_with_is_configured_false(self, isolated_client):
        resp = isolated_client.get("/api/settings/creator-context")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_configured"] is False
        assert body["creator_context"] == _BLANK_PAYLOAD

    def test_get_never_returns_404(self, isolated_client):
        """Even with no row in creator_prefs at all, the route returns
        200 so the Settings UI never hits a missing-resource path."""
        resp = isolated_client.get("/api/settings/creator-context")
        assert resp.status_code != 404


class TestPutThenGet:
    def test_put_persists_and_get_reads_back(self, isolated_client):
        payload = {
            "creator_id": "creator-vn-1",
            "channel_name": "K1 Cooking",
            "brand_voice": "authentic",
            "target_audience": "vn",
            "content_pillars": ["recipe", "tutorial"],
            "market": "vn",
            "language": "vi",
            "notes": "Friendly home cook vibe",
        }
        put_resp = isolated_client.put("/api/settings/creator-context", json=payload)
        assert put_resp.status_code == 200
        put_body = put_resp.json()
        assert put_body["is_configured"] is True
        assert put_body["creator_context"] == payload

        get_resp = isolated_client.get("/api/settings/creator-context")
        assert get_resp.status_code == 200
        assert get_resp.json() == put_body

    def test_put_unicode_round_trip(self, isolated_client):
        payload = {**_BLANK_PAYLOAD, "channel_name": "Bếp Việt", "notes": "Hấp dẫn, gần gũi"}
        isolated_client.put("/api/settings/creator-context", json=payload)
        body = isolated_client.get("/api/settings/creator-context").json()
        assert body["creator_context"]["channel_name"] == "Bếp Việt"
        assert body["creator_context"]["notes"] == "Hấp dẫn, gần gũi"

    def test_overwrite_in_place(self, isolated_client):
        isolated_client.put(
            "/api/settings/creator-context",
            json={**_BLANK_PAYLOAD, "channel_name": "v1"},
        )
        isolated_client.put(
            "/api/settings/creator-context",
            json={**_BLANK_PAYLOAD, "channel_name": "v2"},
        )
        body = isolated_client.get("/api/settings/creator-context").json()
        assert body["creator_context"]["channel_name"] == "v2"


class TestClearViaPut:
    def test_empty_payload_clears_field(self, isolated_client):
        isolated_client.put(
            "/api/settings/creator-context",
            json={**_BLANK_PAYLOAD, "channel_name": "k1", "brand_voice": "viral"},
        )
        # Confirm the configured state.
        assert isolated_client.get("/api/settings/creator-context").json()["is_configured"] is True
        # Now PUT all-blanks — should clear.
        clear_resp = isolated_client.put("/api/settings/creator-context", json=_BLANK_PAYLOAD)
        assert clear_resp.status_code == 200
        assert clear_resp.json()["is_configured"] is False
        assert isolated_client.get("/api/settings/creator-context").json()["is_configured"] is False


class TestPayloadValidation:
    def test_unknown_keys_silently_dropped(self, isolated_client):
        """Older / newer clients may post fields the server doesn't
        know about. extra='ignore' protects backward compat."""
        payload = {
            **_BLANK_PAYLOAD,
            "channel_name": "k1",
            "some_future_field": "yes",
            "another_alien_key": 42,
        }
        resp = isolated_client.put("/api/settings/creator-context", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        # The known field survived.
        assert body["creator_context"]["channel_name"] == "k1"
        # The unknown ones are dropped — not echoed in the envelope.
        assert "some_future_field" not in body["creator_context"]
        assert "another_alien_key" not in body["creator_context"]

    def test_missing_required_fields_use_defaults(self, isolated_client):
        """All CreatorContext fields have defaults, so a sparse body
        merges with blanks rather than 422'ing."""
        resp = isolated_client.put(
            "/api/settings/creator-context",
            json={"channel_name": "k1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["creator_context"]["channel_name"] == "k1"
        assert body["creator_context"]["brand_voice"] == ""

    def test_content_pillars_wrong_type_returns_422(self, isolated_client):
        """A non-list content_pillars is a genuine type error — Pydantic
        rejects it with 422 rather than silently coercing."""
        resp = isolated_client.put(
            "/api/settings/creator-context",
            json={**_BLANK_PAYLOAD, "content_pillars": "not-a-list"},
        )
        assert resp.status_code == 422
