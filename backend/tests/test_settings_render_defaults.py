"""Tests for GET/PUT /api/settings/render-defaults (S2.1).

Covers:
1. GET on a fresh DB returns an empty envelope (is_configured=False).
2. Round-trip: PUT persists, next GET reads back.
3. PUT with `{}` clears every field.
4. PUT with every field null clears (extra='ignore' tolerance check).
5. Unknown keys are silently dropped (extra='ignore').
6. Render defaults coexist with creator_context, output_dir, and
   data_retention without clobbering them — Sacred Contract is the
   shared prefs_json blob.
7. Repo helper returns None when never written, dict when written.
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
# 1. GET on fresh DB returns empty envelope
# ---------------------------------------------------------------------------


def test_get_render_defaults_returns_empty_on_fresh_db(_client):
    resp = _client.get("/api/settings/render-defaults")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_configured"] is False
    rd = body["render_defaults"]
    # Every field should be None
    assert rd["aspect_ratio"] is None
    assert rd["preset"] is None
    assert rd["voice_provider"] is None
    assert rd["voice_id"] is None
    assert rd["subtitle_style"] is None
    assert rd["llm_provider"] is None


# ---------------------------------------------------------------------------
# 2. Round-trip: PUT then GET
# ---------------------------------------------------------------------------


def test_put_then_get_round_trips_fields(_client):
    payload = {
        "aspect_ratio": "9:16",
        "preset": "viral",
        "voice_provider": "elevenlabs",
        "voice_id": "rachel_v2",
        "subtitle_style": "bold-yellow",
        "llm_provider": "claude",
    }
    put_resp = _client.put("/api/settings/render-defaults", json=payload)
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert body["is_configured"] is True
    for k, v in payload.items():
        assert body["render_defaults"][k] == v

    get_resp = _client.get("/api/settings/render-defaults")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["is_configured"] is True
    for k, v in payload.items():
        assert body["render_defaults"][k] == v


def test_partial_put_preserves_only_provided_fields(_client):
    """A PUT with a subset of fields only persists what was sent. Fields
    not in the payload come back as None — consistent with the wire
    contract that null = "no preference"."""
    _client.put(
        "/api/settings/render-defaults",
        json={"aspect_ratio": "1:1", "preset": "story"},
    )
    body = _client.get("/api/settings/render-defaults").json()
    assert body["is_configured"] is True
    assert body["render_defaults"]["aspect_ratio"] == "1:1"
    assert body["render_defaults"]["preset"] == "story"
    # Other fields remain null
    assert body["render_defaults"]["voice_id"] is None
    assert body["render_defaults"]["llm_provider"] is None


# ---------------------------------------------------------------------------
# 3 & 4. PUT clears
# ---------------------------------------------------------------------------


def test_put_empty_body_clears_setting(_client):
    # First set a value.
    _client.put(
        "/api/settings/render-defaults",
        json={"aspect_ratio": "9:16", "preset": "viral"},
    )
    # Then clear it.
    resp = _client.put("/api/settings/render-defaults", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_configured"] is False
    assert body["render_defaults"]["aspect_ratio"] is None
    assert body["render_defaults"]["preset"] is None


def test_put_all_nulls_clears_setting(_client):
    _client.put(
        "/api/settings/render-defaults",
        json={"aspect_ratio": "9:16"},
    )
    resp = _client.put(
        "/api/settings/render-defaults",
        json={
            "aspect_ratio": None,
            "preset": None,
            "voice_provider": None,
            "voice_id": None,
            "subtitle_style": None,
            "llm_provider": None,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["is_configured"] is False


def test_put_all_empty_strings_clears_setting(_client):
    """Empty strings are treated the same as None (forgiving wire surface)."""
    _client.put(
        "/api/settings/render-defaults",
        json={"aspect_ratio": "9:16"},
    )
    resp = _client.put(
        "/api/settings/render-defaults",
        json={"aspect_ratio": "", "preset": ""},
    )
    assert resp.status_code == 200
    assert resp.json()["is_configured"] is False


# ---------------------------------------------------------------------------
# 5. Unknown fields ignored
# ---------------------------------------------------------------------------


def test_unknown_fields_are_silently_dropped(_client):
    resp = _client.put(
        "/api/settings/render-defaults",
        json={
            "aspect_ratio": "9:16",
            "future_field_we_havent_invented_yet": "ignore-me",
            "another_unknown": 123,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_configured"] is True
    assert body["render_defaults"]["aspect_ratio"] == "9:16"
    # Unknown keys must not leak into the response
    assert "future_field_we_havent_invented_yet" not in body["render_defaults"]
    assert "another_unknown" not in body["render_defaults"]


# ---------------------------------------------------------------------------
# 6. Coexistence with other prefs keys
# ---------------------------------------------------------------------------


def test_render_defaults_does_not_clobber_creator_context(_client):
    _client.put(
        "/api/settings/creator-context",
        json={"channel_name": "MyChannel", "brand_voice": "educational"},
    )
    _client.put("/api/settings/render-defaults", json={"aspect_ratio": "9:16"})

    cc = _client.get("/api/settings/creator-context").json()
    assert cc["creator_context"]["channel_name"] == "MyChannel"
    assert cc["is_configured"] is True

    rd = _client.get("/api/settings/render-defaults").json()
    assert rd["render_defaults"]["aspect_ratio"] == "9:16"


def test_render_defaults_does_not_clobber_output_dir(_client):
    _client.put("/api/settings/output-dir", json={"path": "D:/Out"})
    _client.put("/api/settings/render-defaults", json={"preset": "viral"})

    od = _client.get("/api/settings/output-dir").json()
    assert od["output_dir"]["path"] == "D:/Out"

    rd = _client.get("/api/settings/render-defaults").json()
    assert rd["render_defaults"]["preset"] == "viral"


def test_render_defaults_does_not_clobber_data_retention(_client):
    _client.put("/api/settings/data-retention", json={"job_retention_days": 30})
    _client.put("/api/settings/render-defaults", json={"llm_provider": "claude"})

    dr = _client.get("/api/settings/data-retention").json()
    assert dr["data_retention"]["job_retention_days"] == 30

    rd = _client.get("/api/settings/render-defaults").json()
    assert rd["render_defaults"]["llm_provider"] == "claude"


def test_clearing_render_defaults_preserves_other_keys(_client):
    _client.put("/api/settings/output-dir", json={"path": "D:/Out"})
    _client.put(
        "/api/settings/creator-context",
        json={"channel_name": "MyChannel"},
    )
    _client.put("/api/settings/render-defaults", json={"aspect_ratio": "9:16"})

    # Clear render_defaults specifically.
    _client.put("/api/settings/render-defaults", json={})

    # Output dir and creator context survive.
    assert _client.get("/api/settings/output-dir").json()["output_dir"]["path"] == "D:/Out"
    assert _client.get(
        "/api/settings/creator-context"
    ).json()["creator_context"]["channel_name"] == "MyChannel"


# ---------------------------------------------------------------------------
# 7. Repo helper return semantics
# ---------------------------------------------------------------------------


def test_repo_returns_none_when_not_set(_client):
    from app.db.creator_repo import get_render_defaults
    assert get_render_defaults() is None


def test_repo_returns_dict_when_set(_client):
    from app.db.creator_repo import get_render_defaults
    _client.put(
        "/api/settings/render-defaults",
        json={"aspect_ratio": "9:16", "preset": "viral"},
    )
    stored = get_render_defaults()
    assert isinstance(stored, dict)
    assert stored["aspect_ratio"] == "9:16"
    assert stored["preset"] == "viral"
    # Only non-null fields are persisted in storage (cleaning happens in
    # upsert_render_defaults). The wire surface adds nulls for missing
    # fields on read; storage stays compact.
    assert "voice_id" not in stored
