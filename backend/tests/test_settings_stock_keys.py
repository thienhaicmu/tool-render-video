"""test_settings_stock_keys.py — P3.1-C stock API-key settings.

Covers the persist + apply + masked-status contract:
  - creator_repo get/upsert roundtrip.
  - PUT persists + applies to os.environ (provider_stock reads env).
  - GET/PUT return only set/not-set booleans — the RAW key is never exposed.
  - A blank field on PUT keeps the previously-saved key (no accidental wipe).
"""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Module-top import so config's one-time .env load happens at COLLECTION, before
# any per-test env cleanup (a lazy import would re-populate .env keys after we
# cleared them).
from app.routes.settings import router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def _env(tmp_path, monkeypatch):
    db = tmp_path / "app.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db, close_thread_conn
    init_db()
    # The app sets these via os.environ directly (not monkeypatch), so snapshot
    # + restore them ourselves to keep tests isolated.
    saved = {k: os.environ.get(k) for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY")}
    os.environ.pop("PEXELS_API_KEY", None)
    os.environ.pop("PIXABAY_API_KEY", None)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    close_thread_conn()


def test_repo_roundtrip(_env):
    from app.db.creator_repo import get_stock_keys, upsert_stock_keys
    assert get_stock_keys() is None
    upsert_stock_keys("  pex-1  ", "pix-1")   # trimmed on write
    got = get_stock_keys()
    assert got == {"pexels": "pex-1", "pixabay": "pix-1"}


def test_get_unconfigured_is_false(_env):
    body = _client().get("/api/settings/stock-keys").json()
    assert body == {"pexels_set": False, "pixabay_set": False}


def test_put_persists_applies_and_masks(_env):
    secret = "PEXELS-SECRET-abc123"
    r = _client().put("/api/settings/stock-keys", json={"pexels": secret})
    assert r.status_code == 200, r.text
    # Masked: response is booleans only; the raw key never appears.
    assert r.json() == {"pexels_set": True, "pixabay_set": False}
    assert secret not in r.text
    # Applied to the live env so provider_stock picks it up without a restart.
    assert os.environ.get("PEXELS_API_KEY") == secret
    # GET also reflects set=true, still without leaking the key.
    g = _client().get("/api/settings/stock-keys")
    assert g.json()["pexels_set"] is True and secret not in g.text


def test_blank_field_keeps_existing_key(_env):
    from app.db.creator_repo import get_stock_keys
    c = _client()
    c.put("/api/settings/stock-keys", json={"pexels": "keep-me"})
    # A later save of only pixabay (pexels blank) must NOT wipe the saved pexels.
    c.put("/api/settings/stock-keys", json={"pixabay": "pix-2"})
    saved = get_stock_keys()
    assert saved == {"pexels": "keep-me", "pixabay": "pix-2"}
    assert c.get("/api/settings/stock-keys").json() == {"pexels_set": True, "pixabay_set": True}
