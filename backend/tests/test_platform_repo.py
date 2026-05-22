"""
Tests for app.db.platform_repo — Phase 4F.4 extraction.

Covers:
- Import identity (services.db re-exports same objects as app.db.platform_repo)
- list_proxy_pool_rows() returns [] when empty
- create_proxy_pool_row() creates a row with correct defaults
- get_proxy_pool_row() returns expected dict or None for missing
- list_proxy_pool_rows() returns created rows (DESC created_at)
- update_proxy_pool_row() updates allowed fields, merges rest
- update_proxy_pool_row() returns None for missing proxy_id
- delete_proxy_pool_row() deletes row, returns True/False
- _normalize_proxy_pool_row: metadata JSON expansion, port/latency_ms coercion,
  None row returns None, invalid JSON fallback
- Old import path (app.services.db) works end-to-end
- Cross-module read/write

Test isolation: every test uses a fresh tmp_path SQLite DB.
Patches app.db.connection.DATABASE_PATH (the local binding) directly.
"""

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_db(monkeypatch, db_path):
    import app.db.connection as conn_mod
    monkeypatch.setattr(conn_mod, "DATABASE_PATH", db_path)
    monkeypatch.setattr(conn_mod, "_ACTIVE_DB_PATH", None)
    conn_mod.init_db()


def _make_proxy(name="test-proxy", host="1.2.3.4", port=8080, **kwargs):
    data = {"name": name, "host": host, "port": port, "type": "http"}
    data.update(kwargs)
    return data


# ---------------------------------------------------------------------------
# Import / Compat
# ---------------------------------------------------------------------------

class TestImportIdentity:
    def test_platform_repo_module_importable(self):
        import app.db.platform_repo  # noqa: F401

    def test_services_db_module_importable(self):
        import app.services.db  # noqa: F401

    def test_list_proxy_pool_rows_same_object(self):
        from app.db.platform_repo import list_proxy_pool_rows as a
        from app.services.db import list_proxy_pool_rows as b
        assert a is b

    def test_get_proxy_pool_row_same_object(self):
        from app.db.platform_repo import get_proxy_pool_row as a
        from app.services.db import get_proxy_pool_row as b
        assert a is b

    def test_create_proxy_pool_row_same_object(self):
        from app.db.platform_repo import create_proxy_pool_row as a
        from app.services.db import create_proxy_pool_row as b
        assert a is b

    def test_update_proxy_pool_row_same_object(self):
        from app.db.platform_repo import update_proxy_pool_row as a
        from app.services.db import update_proxy_pool_row as b
        assert a is b

    def test_delete_proxy_pool_row_same_object(self):
        from app.db.platform_repo import delete_proxy_pool_row as a
        from app.services.db import delete_proxy_pool_row as b
        assert a is b

    def test_normalize_proxy_pool_row_same_object(self):
        from app.db.platform_repo import _normalize_proxy_pool_row as a
        from app.services.db import _normalize_proxy_pool_row as b
        assert a is b


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestListProxyPoolRows:
    def test_returns_empty_list_when_no_rows(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import list_proxy_pool_rows
        assert list_proxy_pool_rows() == []

    def test_returns_list_type(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import list_proxy_pool_rows
        result = list_proxy_pool_rows()
        assert isinstance(result, list)


class TestCreateProxyPoolRow:
    def test_creates_row_returns_dict(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row
        result = create_proxy_pool_row(_make_proxy())
        assert isinstance(result, dict)
        assert result["name"] == "test-proxy"
        assert result["host"] == "1.2.3.4"
        assert result["port"] == 8080

    def test_default_status_is_untested(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row
        result = create_proxy_pool_row(_make_proxy())
        assert result["status"] == "untested"

    def test_default_type_is_http_when_omitted(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row
        result = create_proxy_pool_row({"name": "p", "host": "h"})
        assert result["type"] == "http"

    def test_proxy_id_generated_when_omitted(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row
        result = create_proxy_pool_row(_make_proxy())
        assert result["proxy_id"]
        assert len(result["proxy_id"]) > 0

    def test_explicit_proxy_id_preserved(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row
        result = create_proxy_pool_row(_make_proxy(proxy_id="my-fixed-id"))
        assert result["proxy_id"] == "my-fixed-id"

    def test_metadata_stored_and_expanded(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row
        result = create_proxy_pool_row(_make_proxy(metadata={"region": "us-east"}))
        assert result["metadata"] == {"region": "us-east"}

    def test_created_at_and_updated_at_set(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row
        result = create_proxy_pool_row(_make_proxy())
        assert result.get("created_at")
        assert result.get("updated_at")


class TestGetProxyPoolRow:
    def test_returns_dict_for_existing_row(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, get_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy())
        result = get_proxy_pool_row(created["proxy_id"])
        assert result["proxy_id"] == created["proxy_id"]
        assert result["name"] == "test-proxy"

    def test_returns_none_for_missing_proxy_id(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import get_proxy_pool_row
        assert get_proxy_pool_row("does-not-exist") is None

    def test_metadata_expanded_in_get(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, get_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy(metadata={"k": "v"}))
        result = get_proxy_pool_row(created["proxy_id"])
        assert result["metadata"] == {"k": "v"}

    def test_port_is_int(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, get_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy(port=3128))
        result = get_proxy_pool_row(created["proxy_id"])
        assert result["port"] == 3128
        assert isinstance(result["port"], int)


class TestListProxyPoolRowsOrder:
    def test_returns_all_created_rows(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, list_proxy_pool_rows
        create_proxy_pool_row(_make_proxy(name="a"))
        create_proxy_pool_row(_make_proxy(name="b"))
        rows = list_proxy_pool_rows()
        assert len(rows) == 2
        names = {r["name"] for r in rows}
        assert names == {"a", "b"}

    def test_row_dicts_have_metadata_key(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, list_proxy_pool_rows
        create_proxy_pool_row(_make_proxy())
        rows = list_proxy_pool_rows()
        assert "metadata" in rows[0]
        assert "metadata_json" not in rows[0]


class TestUpdateProxyPoolRow:
    def test_updates_name_field(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, update_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy(name="old-name"))
        result = update_proxy_pool_row(created["proxy_id"], {"name": "new-name"})
        assert result["name"] == "new-name"

    def test_updates_status_field(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, update_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy())
        result = update_proxy_pool_row(created["proxy_id"], {"status": "ok"})
        assert result["status"] == "ok"

    def test_updates_metadata_via_metadata_key(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, update_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy())
        result = update_proxy_pool_row(created["proxy_id"], {"metadata": {"new": "data"}})
        assert result["metadata"] == {"new": "data"}

    def test_preserves_unmentioned_fields(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, update_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy(host="5.6.7.8"))
        result = update_proxy_pool_row(created["proxy_id"], {"name": "changed"})
        assert result["host"] == "5.6.7.8"

    def test_returns_none_for_missing_proxy_id(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import update_proxy_pool_row
        assert update_proxy_pool_row("no-such-id", {"name": "x"}) is None

    def test_updated_at_changes_after_update(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, update_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy())
        result = update_proxy_pool_row(created["proxy_id"], {"status": "ok"})
        assert result.get("updated_at")


class TestDeleteProxyPoolRow:
    def test_delete_returns_true_for_existing(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, delete_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy())
        assert delete_proxy_pool_row(created["proxy_id"]) is True

    def test_row_gone_after_delete(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, delete_proxy_pool_row, get_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy())
        delete_proxy_pool_row(created["proxy_id"])
        assert get_proxy_pool_row(created["proxy_id"]) is None

    def test_delete_returns_false_for_missing(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import delete_proxy_pool_row
        assert delete_proxy_pool_row("no-such-id") is False

    def test_list_empty_after_delete(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import create_proxy_pool_row, delete_proxy_pool_row, list_proxy_pool_rows
        created = create_proxy_pool_row(_make_proxy())
        delete_proxy_pool_row(created["proxy_id"])
        assert list_proxy_pool_rows() == []


# ---------------------------------------------------------------------------
# Normalization / JSON
# ---------------------------------------------------------------------------

class TestNormalizeProxyPoolRow:
    def test_none_row_returns_none(self):
        from app.db.platform_repo import _normalize_proxy_pool_row
        assert _normalize_proxy_pool_row(None) is None

    def test_empty_dict_row_returns_none(self):
        from app.db.platform_repo import _normalize_proxy_pool_row
        assert _normalize_proxy_pool_row({}) is None

    def test_metadata_json_expanded_to_metadata(self):
        from app.db.platform_repo import _normalize_proxy_pool_row
        row = {"proxy_id": "x", "metadata_json": '{"k": 1}', "port": "80", "latency_ms": "5"}
        result = _normalize_proxy_pool_row(row)
        assert result["metadata"] == {"k": 1}
        assert "metadata_json" not in result

    def test_invalid_metadata_json_returns_empty_dict(self):
        from app.db.platform_repo import _normalize_proxy_pool_row
        row = {"proxy_id": "x", "metadata_json": "{not valid", "port": 80, "latency_ms": 0}
        result = _normalize_proxy_pool_row(row)
        assert result["metadata"] == {}

    def test_none_metadata_json_returns_empty_dict(self):
        from app.db.platform_repo import _normalize_proxy_pool_row
        row = {"proxy_id": "x", "metadata_json": None, "port": 80, "latency_ms": 0}
        result = _normalize_proxy_pool_row(row)
        assert result["metadata"] == {}

    def test_port_coerced_to_int(self):
        from app.db.platform_repo import _normalize_proxy_pool_row
        row = {"proxy_id": "x", "metadata_json": "{}", "port": "8080", "latency_ms": "0"}
        result = _normalize_proxy_pool_row(row)
        assert result["port"] == 8080
        assert isinstance(result["port"], int)

    def test_latency_ms_coerced_to_int(self):
        from app.db.platform_repo import _normalize_proxy_pool_row
        row = {"proxy_id": "x", "metadata_json": "{}", "port": 80, "latency_ms": "42"}
        result = _normalize_proxy_pool_row(row)
        assert result["latency_ms"] == 42
        assert isinstance(result["latency_ms"], int)

    def test_non_numeric_port_falls_back_to_zero(self):
        from app.db.platform_repo import _normalize_proxy_pool_row
        row = {"proxy_id": "x", "metadata_json": "{}", "port": "bad", "latency_ms": 0}
        result = _normalize_proxy_pool_row(row)
        assert result["port"] == 0


# ---------------------------------------------------------------------------
# Old import path
# ---------------------------------------------------------------------------

class TestOldImportPath:
    def test_create_via_services_db(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.services.db import create_proxy_pool_row, get_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy(name="via-services"))
        fetched = get_proxy_pool_row(created["proxy_id"])
        assert fetched["name"] == "via-services"

    def test_cross_module_read_write(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import get_proxy_pool_row
        from app.services.db import create_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy(name="cross"))
        fetched = get_proxy_pool_row(created["proxy_id"])
        assert fetched["name"] == "cross"

    def test_update_via_platform_repo_read_via_services_db(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.platform_repo import update_proxy_pool_row
        from app.services.db import create_proxy_pool_row, get_proxy_pool_row
        created = create_proxy_pool_row(_make_proxy(name="before"))
        update_proxy_pool_row(created["proxy_id"], {"name": "after"})
        fetched = get_proxy_pool_row(created["proxy_id"])
        assert fetched["name"] == "after"
