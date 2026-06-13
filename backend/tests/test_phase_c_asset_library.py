"""Phase C — Asset Library QA tests.

Covers:
  - domain/asset.py: Asset.from_row, to_dict, coercion, missing-key safety
  - db/assets_repo.py: upsert (insert + dedup), get, list, delete
  - routes/assets.py: GET /api/assets, GET /api/assets/{id}, DELETE /api/assets/{id}
  - migration 0007: assets table created + asset_id FK columns added
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch


# ── domain/asset.py ───────────────────────────────────────────────────────────

def test_asset_from_row_full():
    from app.domain.asset import Asset

    row = {
        "asset_id": "abc", "file_path": "/tmp/v.mp4",
        "original_url": "https://yt.com/x", "title": "MyVid",
        "duration_sec": "120.5", "width": "1920", "height": "1080",
        "fps": "30.0", "file_size_bytes": "1048576",
        "language": "vi", "content_type": "vlog",
        "transcription_cache_path": "/tmp/t.json",
        "thumbnail_path": "/tmp/thumb.jpg",
        "created_at": "2026-01-01T00:00:00Z",
        "enriched_at": "2026-01-02T00:00:00Z",
    }
    a = Asset.from_row(row)
    assert a.asset_id == "abc"
    assert a.duration_sec == 120.5
    assert a.width == 1920
    assert a.fps == 30.0
    assert a.file_size_bytes == 1048576
    assert a.transcription_cache_path == "/tmp/t.json"
    assert a.thumbnail_path == "/tmp/thumb.jpg"


def test_asset_from_row_empty_dict():
    from app.domain.asset import Asset

    a = Asset.from_row({})
    assert a.asset_id == ""
    assert a.duration_sec == 0.0
    assert a.width == 0
    assert a.transcription_cache_path is None


def test_asset_from_row_non_dict_returns_default():
    from app.domain.asset import Asset

    a = Asset.from_row("not a dict")  # type: ignore[arg-type]
    assert a.asset_id == ""


def test_asset_to_dict_has_expected_keys():
    from app.domain.asset import Asset

    a = Asset(asset_id="x", file_path="/f.mp4", title="T")
    d = a.to_dict()
    for key in ("asset_id", "file_path", "title", "duration_sec", "width",
                "height", "fps", "file_size_bytes", "language", "content_type",
                "transcription_cache_path", "thumbnail_path", "created_at", "enriched_at"):
        assert key in d


def test_asset_coerce_bad_float_falls_back():
    from app.domain.asset import Asset

    a = Asset.from_row({"duration_sec": "not_a_number"})
    assert a.duration_sec == 0.0


def test_asset_coerce_bad_int_falls_back():
    from app.domain.asset import Asset

    a = Asset.from_row({"width": "???"})
    assert a.width == 0


# ── db/assets_repo.py ─────────────────────────────────────────────────────────

def _mock_conn():
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def test_upsert_asset_inserts_new_row():
    from app.db.assets_repo import upsert_asset

    mock = _mock_conn()
    mock.execute.return_value.fetchone.return_value = None  # no existing row

    with patch("app.db.assets_repo.db_conn", return_value=mock):
        returned_id = upsert_asset("aid1", "/v.mp4", "https://yt.com", "Test")

    assert returned_id == "aid1"
    # INSERT should be called (second execute after the SELECT)
    assert mock.execute.call_count >= 2


def test_upsert_asset_returns_existing_id_on_dup():
    from app.db.assets_repo import upsert_asset

    mock = _mock_conn()
    existing = {"asset_id": "existing_aid"}
    mock.execute.return_value.fetchone.return_value = existing

    with patch("app.db.assets_repo.db_conn", return_value=mock):
        returned_id = upsert_asset("new_aid", "/v.mp4")

    # Must return the pre-existing ID, not the new one
    assert returned_id == "existing_aid"
    # Only the SELECT should run — no INSERT
    mock.execute.assert_called_once()


def test_get_asset_returns_none_when_missing():
    from app.db.assets_repo import get_asset

    mock = _mock_conn()
    mock.execute.return_value.fetchone.return_value = None

    with patch("app.db.assets_repo.db_conn", return_value=mock):
        result = get_asset("nonexistent")

    assert result is None


def test_get_asset_returns_asset_object():
    from app.db.assets_repo import get_asset

    mock = _mock_conn()
    mock.execute.return_value.fetchone.return_value = {
        "asset_id": "aid1", "file_path": "/v.mp4",
        "original_url": "", "title": "T",
        "duration_sec": 0, "width": 0, "height": 0, "fps": 0,
        "file_size_bytes": 0, "language": "", "content_type": "",
        "transcription_cache_path": None, "thumbnail_path": None,
        "created_at": "", "enriched_at": None,
    }

    with patch("app.db.assets_repo.db_conn", return_value=mock):
        result = get_asset("aid1")

    assert result is not None
    assert result.asset_id == "aid1"


def test_list_assets_returns_list():
    from app.db.assets_repo import list_assets

    row = {
        "asset_id": "aid1", "file_path": "/v.mp4",
        "original_url": "", "title": "",
        "duration_sec": 0, "width": 0, "height": 0, "fps": 0,
        "file_size_bytes": 0, "language": "", "content_type": "",
        "transcription_cache_path": None, "thumbnail_path": None,
        "created_at": "2026-01-01", "enriched_at": None,
    }
    mock = _mock_conn()
    mock.execute.return_value.fetchall.return_value = [row]

    with patch("app.db.assets_repo.db_conn", return_value=mock):
        result = list_assets(limit=10, offset=0)

    assert len(result) == 1
    assert result[0].asset_id == "aid1"


def test_delete_asset_calls_delete_sql():
    from app.db.assets_repo import delete_asset

    mock = _mock_conn()

    with patch("app.db.assets_repo.db_conn", return_value=mock):
        delete_asset("aid1")

    sql = mock.execute.call_args[0][0]
    assert "DELETE" in sql.upper()


# ── routes/assets.py ─────────────────────────────────────────────────────────

def _client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_get_assets_returns_list():
    from app.domain.asset import Asset

    assets = [Asset(asset_id="a1", file_path="/v.mp4", title="V")]
    with patch("app.routes.assets.list_assets", return_value=assets):
        resp = _client().get("/api/assets")

    assert resp.status_code == 200
    body = resp.json()
    assert "assets" in body
    assert body["assets"][0]["asset_id"] == "a1"


def test_get_assets_pagination_out_of_range_returns_422():
    # Phase Q added Query(ge=1, le=500) validation — invalid params return 422
    with patch("app.routes.assets.list_assets", return_value=[]):
        resp_limit = _client().get("/api/assets?limit=9999")
        resp_offset = _client().get("/api/assets?offset=-5")

    assert resp_limit.status_code == 422
    assert resp_offset.status_code == 422


def test_get_asset_by_id_found():
    from app.domain.asset import Asset

    asset = Asset(asset_id="a1", file_path="/v.mp4")
    with patch("app.routes.assets.get_asset", return_value=asset):
        resp = _client().get("/api/assets/a1")

    assert resp.status_code == 200
    assert resp.json()["asset_id"] == "a1"


def test_get_asset_by_id_not_found():
    with patch("app.routes.assets.get_asset", return_value=None):
        resp = _client().get("/api/assets/missing")

    assert resp.status_code == 404


def test_delete_asset_found():
    from app.domain.asset import Asset

    asset = Asset(asset_id="a1", file_path="/v.mp4")
    with patch("app.routes.assets.get_asset", return_value=asset), \
         patch("app.routes.assets.delete_asset") as mock_del:
        resp = _client().delete("/api/assets/a1")

    assert resp.status_code == 200
    assert resp.json()["deleted"] == "a1"
    mock_del.assert_called_once_with("a1")


def test_delete_asset_not_found():
    with patch("app.routes.assets.get_asset", return_value=None):
        resp = _client().delete("/api/assets/missing")

    assert resp.status_code == 404


# ── migration 0007 ────────────────────────────────────────────────────────────

import importlib.util
from pathlib import Path as _Path

_MIG_0007 = (
    _Path(__file__).resolve().parent.parent
    / "app" / "db" / "migration_steps" / "0007_add_assets_table.py"
)


def _load_0007():
    spec = importlib.util.spec_from_file_location("_mig_0007", _MIG_0007)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0007_creates_assets_table():
    m = _load_0007()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE download_jobs (job_id TEXT PRIMARY KEY, status TEXT)")
    conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, status TEXT)")
    m.up(conn)
    conn.commit()

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "assets" in tables

    dj_cols = {r[1] for r in conn.execute("PRAGMA table_info(download_jobs)")}
    j_cols  = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    assert "asset_id" in dj_cols
    assert "asset_id" in j_cols


def test_migration_0007_idempotent():
    m = _load_0007()
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE download_jobs (job_id TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY)")
    m.up(conn)
    m.up(conn)  # second call must not raise
    conn.commit()
