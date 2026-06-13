"""tests/test_phase_u2_asset_lifecycle.py — Phase U2: Asset Lifecycle State Machine.

Covers:
  - Asset.from_row reads status field (defaults 'pending')
  - Asset.to_dict includes status key
  - upsert_asset inserts with status='pending'
  - update_asset_status sets correct value
  - update_asset_enrichment sets status='ready'
  - Migration 0009: adds column, backfills ready, idempotent
  - GET /api/assets response includes status field
  - enrich_asset exception path → update_asset_status('failed') called
  - _run_download → update_asset_status('enriching') called before submit
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path as _Path
from unittest.mock import MagicMock, call, patch

import pytest


# ── domain/asset.py ──────────────────────────────────────────────────────────

def test_asset_from_row_reads_status():
    from app.domain.asset import Asset
    a = Asset.from_row({"asset_id": "x", "file_path": "/f.mp4", "status": "ready"})
    assert a.status == "ready"


def test_asset_from_row_defaults_status_pending():
    from app.domain.asset import Asset
    a = Asset.from_row({"asset_id": "x", "file_path": "/f.mp4"})
    assert a.status == "pending"


def test_asset_from_row_null_status_defaults_pending():
    from app.domain.asset import Asset
    a = Asset.from_row({"asset_id": "x", "file_path": "/f.mp4", "status": None})
    assert a.status == "pending"


def test_asset_to_dict_includes_status():
    from app.domain.asset import Asset
    a = Asset(asset_id="x", file_path="/f.mp4", status="enriching")
    assert "status" in a.to_dict()
    assert a.to_dict()["status"] == "enriching"


def test_asset_default_status_is_pending():
    from app.domain.asset import Asset
    a = Asset()
    assert a.status == "pending"


# ── db/assets_repo.py ────────────────────────────────────────────────────────

def _mock_conn():
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def test_upsert_asset_inserts_with_pending_status():
    from app.db.assets_repo import upsert_asset

    mock = _mock_conn()
    mock.execute.return_value.fetchone.return_value = None  # no existing row

    with patch("app.db.assets_repo.db_conn", return_value=mock):
        upsert_asset("aid1", "/v.mp4", "https://yt.com", "Test")

    # Find the INSERT call
    insert_calls = [
        c for c in mock.execute.call_args_list
        if "INSERT" in str(c).upper()
    ]
    assert len(insert_calls) >= 1
    insert_sql = insert_calls[0][0][0]
    assert "status" in insert_sql
    assert "'pending'" in insert_sql


def test_update_asset_status_executes_update():
    from app.db.assets_repo import update_asset_status

    mock = _mock_conn()
    with patch("app.db.assets_repo.db_conn", return_value=mock):
        update_asset_status("aid1", "enriching")

    sql = mock.execute.call_args[0][0]
    assert "UPDATE" in sql.upper()
    assert "status" in sql
    args = mock.execute.call_args[0][1]
    assert args[0] == "enriching"
    assert args[1] == "aid1"


def test_update_asset_enrichment_sets_status_ready():
    from app.db.assets_repo import update_asset_enrichment

    mock = _mock_conn()
    with patch("app.db.assets_repo.db_conn", return_value=mock):
        update_asset_enrichment("aid1")

    sql = mock.execute.call_args[0][0]
    assert "status" in sql
    assert "'ready'" in sql


def test_update_asset_status_never_raises():
    from app.db.assets_repo import update_asset_status

    mock = _mock_conn()
    mock.execute.side_effect = RuntimeError("DB error")
    with patch("app.db.assets_repo.db_conn", return_value=mock):
        # Should not raise
        update_asset_status("aid1", "failed")


# ── migration 0009 ───────────────────────────────────────────────────────────

_MIG_0009 = (
    _Path(__file__).resolve().parent.parent
    / "app" / "db" / "migration_steps" / "0009_add_asset_status.py"
)


def _load_0009():
    spec = importlib.util.spec_from_file_location("_mig_0009", _MIG_0009)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0009_adds_status_column():
    m = _load_0009()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE assets (asset_id TEXT PRIMARY KEY, file_path TEXT, enriched_at TEXT)"
    )
    m.up(conn)
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(assets)")}
    assert "status" in cols


def test_migration_0009_backfills_ready():
    m = _load_0009()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE assets (asset_id TEXT PRIMARY KEY, file_path TEXT, enriched_at TEXT)"
    )
    conn.execute("INSERT INTO assets VALUES ('a1', '/f1.mp4', '2026-01-01T00:00:00Z')")
    conn.execute("INSERT INTO assets VALUES ('a2', '/f2.mp4', NULL)")
    conn.commit()
    m.up(conn)
    conn.commit()
    rows = {r["asset_id"]: r["status"] for r in conn.execute("SELECT asset_id, status FROM assets")}
    assert rows["a1"] == "ready"
    assert rows["a2"] == "pending"


def test_migration_0009_idempotent():
    m = _load_0009()
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE assets (asset_id TEXT PRIMARY KEY, file_path TEXT, enriched_at TEXT)"
    )
    m.up(conn)
    m.up(conn)  # second call must not raise
    conn.commit()


# ── routes/assets.py ─────────────────────────────────────────────────────────

def test_get_assets_response_includes_status():
    from app.domain.asset import Asset
    from fastapi.testclient import TestClient
    from app.main import app

    assets = [Asset(asset_id="a1", file_path="/v.mp4", status="ready")]
    with patch("app.routes.assets.list_assets", return_value=assets):
        resp = TestClient(app).get("/api/assets")

    assert resp.status_code == 200
    first = resp.json()["assets"][0]
    assert "status" in first
    assert first["status"] == "ready"


# ── enrichment.py failure path ───────────────────────────────────────────────

def test_enrich_asset_exception_sets_failed_status():
    from app.features.download.engine import enrichment

    with (
        patch.object(enrichment, "_do_enrich", side_effect=RuntimeError("probe error")),
        patch("app.db.assets_repo.update_asset_status") as mock_status,
    ):
        enrichment.enrich_asset("aid1", "/v.mp4")

    # Should have been called with 'failed'
    calls = [c[0] for c in mock_status.call_args_list]
    assert ("aid1", "failed") in calls


# ── download router enriching status ─────────────────────────────────────────

def test_run_download_sets_enriching_before_submit():
    """update_asset_status('enriching') is called before _EXECUTOR.submit."""
    from app.features.download import router as dl_router

    call_order = []

    def fake_upsert(*a, **kw):
        call_order.append("upsert")
        return "aid1"

    def fake_update_status(asset_id, status):
        call_order.append(f"status:{status}")

    def fake_submit(fn, *a, **kw):
        call_order.append("submit")

    fake_executor = MagicMock()
    fake_executor.submit.side_effect = lambda fn, *a, **kw: call_order.append("submit")

    fake_result = {
        "output_path": "/v.mp4", "title": "T", "filename": "v.mp4",
        "height": 1080, "fps": 30.0, "duration": 60.0, "filesize": 1000,
    }

    with (
        patch.object(dl_router, "_EXECUTOR", fake_executor),
        patch("app.db.assets_repo.upsert_asset", side_effect=fake_upsert),
        patch("app.db.assets_repo.update_asset_status", side_effect=fake_update_status),
        patch.object(dl_router, "download_video", return_value=fake_result),
        patch.object(dl_router, "update_download_job"),
        patch("app.core.tracing.dl_job_start"),
        patch("app.core.tracing.dl_job_done"),
    ):
        dl_router._run_download("job1", "https://example.com/v", _Path("/tmp"), "youtube")

    assert "status:enriching" in call_order
    submit_idx = call_order.index("submit")
    enriching_idx = call_order.index("status:enriching")
    assert enriching_idx < submit_idx, "update_asset_status('enriching') must come before submit"
