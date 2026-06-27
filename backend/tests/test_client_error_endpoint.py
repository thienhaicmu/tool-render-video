"""B2 follow-up — POST /api/client/error intake.

Pins that client (Electron renderer / main) error reports are accepted and
re-emitted through the ``app`` logger at ERROR level with namespaced
context, so they flow into the structured errors.jsonl sink. The endpoint
must always return 200 — it is a fire-and-forget reporter and must never
cascade a failure back to the client.
"""
from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_minimal_report_accepted():
    r = client.post("/api/client/error", json={"message": "boom"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_empty_body_uses_defaults():
    # All fields optional → defaults apply, still 200.
    r = client.post("/api/client/error", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_report_is_logged_at_error_with_namespaced_kind(caplog):
    with caplog.at_level(logging.ERROR, logger="app.client"):
        r = client.post(
            "/api/client/error",
            json={
                "source": "renderer",
                "kind": "unhandledrejection",
                "message": "Cannot read properties of undefined",
                "stack": "at foo (app.js:1:1)",
                "url": "http://127.0.0.1:8000/",
            },
        )
    assert r.status_code == 200

    rec = next((x for x in caplog.records if x.name == "app.client"), None)
    assert rec is not None
    assert rec.levelno == logging.ERROR
    # Namespaced so client reports are filterable from backend errors.
    assert getattr(rec, "error_kind", "") == "client.unhandledrejection"
    assert getattr(rec, "client_source", "") == "renderer"


def test_oversized_fields_are_rejected_by_validation():
    # Field length caps protect the JSONL line size — over-cap → 422.
    r = client.post("/api/client/error", json={"message": "x" * 20_000})
    assert r.status_code == 422
