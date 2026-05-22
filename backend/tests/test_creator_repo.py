"""
Tests for app.db.creator_repo — Phase 4F.3 extraction.

Covers:
- Import identity (services.db re-exports same objects as app.db.creator_repo)
- get_creator_prefs() returns {} when no row exists
- upsert_creator_prefs() creates a row, returns updated dict
- upsert_creator_prefs() overwrites existing row
- Nested JSON roundtrip
- Empty dict roundtrip
- Invalid JSON fallback (returns {})
- Old import path (app.services.db) works end-to-end

Test isolation: every test uses a fresh tmp_path SQLite DB.
Patches app.db.connection.DATABASE_PATH (the local binding) directly —
patching app.core.config.DATABASE_PATH is NOT sufficient because
connection.py uses a from-import binding.
"""

import json

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_db(monkeypatch, db_path):
    import app.db.connection as conn_mod
    monkeypatch.setattr(conn_mod, "DATABASE_PATH", db_path)
    monkeypatch.setattr(conn_mod, "_ACTIVE_DB_PATH", None)
    conn_mod.init_db()


# ---------------------------------------------------------------------------
# Import / Compat
# ---------------------------------------------------------------------------

class TestImportIdentity:
    def test_creator_repo_module_importable(self):
        import app.db.creator_repo  # noqa: F401

    def test_services_db_module_importable(self):
        import app.services.db  # noqa: F401

    def test_get_creator_prefs_same_object(self):
        from app.db.creator_repo import get_creator_prefs as a
        from app.services.db import get_creator_prefs as b
        assert a is b

    def test_upsert_creator_prefs_same_object(self):
        from app.db.creator_repo import upsert_creator_prefs as a
        from app.services.db import upsert_creator_prefs as b
        assert a is b


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

class TestGetCreatorPrefs:
    def test_returns_empty_dict_when_no_row(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import get_creator_prefs
        result = get_creator_prefs()
        assert result == {}

    def test_returns_dict_type(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import get_creator_prefs
        result = get_creator_prefs()
        assert isinstance(result, dict)


class TestUpsertCreatorPrefs:
    def test_creates_row_and_returns_dict(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import upsert_creator_prefs
        result = upsert_creator_prefs({"theme": "dark"})
        assert result == {"theme": "dark"}

    def test_roundtrip_via_get(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import get_creator_prefs, upsert_creator_prefs
        upsert_creator_prefs({"theme": "dark", "lang": "en"})
        result = get_creator_prefs()
        assert result == {"theme": "dark", "lang": "en"}

    def test_overwrites_existing_row(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import get_creator_prefs, upsert_creator_prefs
        upsert_creator_prefs({"theme": "dark"})
        upsert_creator_prefs({"theme": "light", "sound": True})
        result = get_creator_prefs()
        assert result == {"theme": "light", "sound": True}

    def test_nested_json_roundtrip(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import get_creator_prefs, upsert_creator_prefs
        payload = {"config": {"speed": 1.2, "tags": ["viral", "hook"]}, "enabled": True}
        upsert_creator_prefs(payload)
        assert get_creator_prefs() == payload

    def test_empty_dict_roundtrip(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import get_creator_prefs, upsert_creator_prefs
        upsert_creator_prefs({})
        assert get_creator_prefs() == {}

    def test_return_value_equals_persisted_state(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import get_creator_prefs, upsert_creator_prefs
        data = {"foo": "bar", "count": 42}
        returned = upsert_creator_prefs(data)
        fetched = get_creator_prefs()
        assert returned == fetched


class TestInvalidJsonFallback:
    def test_invalid_json_in_db_returns_empty_dict(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        import app.db.connection as conn_mod
        # Manually write invalid JSON directly to the DB to test fallback
        conn = conn_mod.get_conn()
        conn.execute(
            "INSERT INTO creator_prefs (id, prefs_json, updated_at) "
            "VALUES (1, ?, CURRENT_TIMESTAMP) "
            "ON CONFLICT(id) DO UPDATE SET prefs_json = excluded.prefs_json",
            ("{not valid json",),
        )
        conn.commit()
        conn.close()
        from app.db.creator_repo import get_creator_prefs
        result = get_creator_prefs()
        assert result == {}

    def test_null_prefs_json_returns_empty_dict(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        import app.db.connection as conn_mod
        conn = conn_mod.get_conn()
        conn.execute(
            "INSERT INTO creator_prefs (id, prefs_json, updated_at) "
            "VALUES (1, NULL, CURRENT_TIMESTAMP) "
            "ON CONFLICT(id) DO UPDATE SET prefs_json = excluded.prefs_json",
        )
        conn.commit()
        conn.close()
        from app.db.creator_repo import get_creator_prefs
        result = get_creator_prefs()
        assert result == {}


class TestOldImportPath:
    def test_get_creator_prefs_via_services_db(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.services.db import get_creator_prefs, upsert_creator_prefs
        upsert_creator_prefs({"via": "services_db"})
        assert get_creator_prefs() == {"via": "services_db"}

    def test_upsert_creator_prefs_via_services_db(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.services.db import upsert_creator_prefs
        result = upsert_creator_prefs({"key": "value"})
        assert result == {"key": "value"}

    def test_cross_module_read_write(self, tmp_path, monkeypatch):
        """Write via creator_repo, read via services.db — same DB, same objects."""
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.creator_repo import upsert_creator_prefs
        from app.services.db import get_creator_prefs
        upsert_creator_prefs({"cross": True})
        assert get_creator_prefs() == {"cross": True}
