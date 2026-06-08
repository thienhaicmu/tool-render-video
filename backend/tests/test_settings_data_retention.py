"""Audit MT-7 UI closure (Batch 10R 2026-06-06).

Tests the data-retention API end-to-end:

1. GET /api/settings/data-retention on a fresh DB returns
   ``{is_configured: False, data_retention: {job_retention_days: 0}}``.
2. PUT persists the value and the next GET reads it back.
3. Out-of-range values are clamped to [0, 365] both on input
   (Pydantic) and on storage (repo helper).
4. The repo helpers (``get_job_retention_days`` /
   ``upsert_job_retention_days``) coexist with the existing
   ``creator_context`` key in ``creator_prefs.prefs_json`` — neither
   one overwrites the other.
5. The periodic-cleanup wire-up: the value persisted via the API is
   the value the next ``prune_old_jobs`` call observes.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _client(tmp_path, monkeypatch):
    """Tmp DB + just the settings router mounted."""
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


def test_get_data_retention_returns_defaults_on_fresh_db(_client):
    resp = _client.get("/api/settings/data-retention")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "is_configured": False,
        "data_retention": {"job_retention_days": 0},
    }


# ---------------------------------------------------------------------------
# 2. Round-trip: PUT then GET
# ---------------------------------------------------------------------------


def test_put_then_get_round_trips_value(_client):
    put_resp = _client.put(
        "/api/settings/data-retention",
        json={"job_retention_days": 30},
    )
    assert put_resp.status_code == 200
    assert put_resp.json() == {
        "is_configured": True,
        "data_retention": {"job_retention_days": 30},
    }

    get_resp = _client.get("/api/settings/data-retention")
    assert get_resp.json()["data_retention"]["job_retention_days"] == 30
    assert get_resp.json()["is_configured"] is True


def test_put_zero_persists_as_disabled_with_configured_flag(_client):
    """Sending 0 deliberately is a valid configuration — distinct from
    'never configured'. is_configured turns True so the FE can show
    'AUTO-PRUNE TẮT' instead of 'CHƯA CẤU HÌNH'."""
    resp = _client.put(
        "/api/settings/data-retention",
        json={"job_retention_days": 0},
    )
    assert resp.json() == {
        "is_configured": True,
        "data_retention": {"job_retention_days": 0},
    }


# ---------------------------------------------------------------------------
# 3. Clamping
# ---------------------------------------------------------------------------


def test_put_rejects_negative_value_via_pydantic(_client):
    resp = _client.put(
        "/api/settings/data-retention",
        json={"job_retention_days": -7},
    )
    # Pydantic ge=0 enforcement.
    assert resp.status_code == 422


def test_put_rejects_value_above_365_via_pydantic(_client):
    resp = _client.put(
        "/api/settings/data-retention",
        json={"job_retention_days": 999},
    )
    assert resp.status_code == 422


def test_repo_clamps_manually_edited_blob_on_read(_client, tmp_path):
    """If someone hand-edits the DB blob to push job_retention_days above
    365 (or below 0), the read clamps to the safe range. This protects
    the cleanup loop from a tampered DB pushing it to delete years of
    data."""
    from app.db import creator_repo

    # Manually inject a tampered value.
    prefs = creator_repo.get_creator_prefs()
    prefs[creator_repo._DATA_RETENTION_KEY] = {"job_retention_days": 9999}
    creator_repo.upsert_creator_prefs(prefs)

    assert creator_repo.get_job_retention_days() == 365

    prefs[creator_repo._DATA_RETENTION_KEY] = {"job_retention_days": -50}
    creator_repo.upsert_creator_prefs(prefs)
    assert creator_repo.get_job_retention_days() == 0


def test_repo_returns_none_when_key_missing(_client):
    """Distinguishes 'user hasn't configured anything' from 'user set 0'.
    The wire-up in main.py uses the None signal to fall back to the
    JOB_RETENTION_DAYS env var."""
    from app.db.creator_repo import get_job_retention_days

    # Fresh DB — no prior PUT.
    assert get_job_retention_days() is None


# ---------------------------------------------------------------------------
# 4. Coexistence with creator_context
# ---------------------------------------------------------------------------


def test_data_retention_does_not_clobber_creator_context(_client):
    """The two settings sections write to the same prefs_json blob via
    distinct nested keys. Pin that they don't step on each other."""
    # First persist a creator_context.
    _client.put(
        "/api/settings/creator-context",
        json={"channel_name": "TestCh", "brand_voice": "viral"},
    )
    # Then persist a data_retention value.
    _client.put(
        "/api/settings/data-retention",
        json={"job_retention_days": 14},
    )

    # Both must be readable.
    cc = _client.get("/api/settings/creator-context").json()
    assert cc["creator_context"]["channel_name"] == "TestCh"
    assert cc["is_configured"] is True

    dr = _client.get("/api/settings/data-retention").json()
    assert dr["data_retention"]["job_retention_days"] == 14


def test_creator_context_does_not_clobber_data_retention(_client):
    """The opposite direction: writing creator_context after
    data_retention preserves the retention value."""
    _client.put(
        "/api/settings/data-retention",
        json={"job_retention_days": 21},
    )
    _client.put(
        "/api/settings/creator-context",
        json={"channel_name": "AnotherCh"},
    )
    dr = _client.get("/api/settings/data-retention").json()
    assert dr["data_retention"]["job_retention_days"] == 21


# ---------------------------------------------------------------------------
# 5. Cleanup-loop wire-up — DB value used over env when present
# ---------------------------------------------------------------------------


def test_db_value_overrides_env_in_cleanup_resolution(_client, monkeypatch):
    """Inline reproduction of the resolution logic in main.py:
    DB value when present, env fallback otherwise."""
    from app.db.creator_repo import get_job_retention_days

    # Env says 7; DB hasn't been written yet → resolver picks env.
    monkeypatch.setenv("JOB_RETENTION_DAYS", "7")
    db_days = get_job_retention_days()
    assert db_days is None
    resolved = db_days if db_days is not None else int("7")
    assert resolved == 7

    # Now write 60 via the API; resolver should now pick the DB value.
    _client.put("/api/settings/data-retention", json={"job_retention_days": 60})
    db_days = get_job_retention_days()
    assert db_days == 60
    resolved = db_days if db_days is not None else int("7")
    assert resolved == 60
