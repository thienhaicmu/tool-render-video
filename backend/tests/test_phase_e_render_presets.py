"""Phase E — Smart Render Presets QA tests.

Covers:
  - domain/render_preset.py: RenderPreset.from_row, to_dict, PRESET_ALLOWED_PARAMS filtering
  - db/presets_repo.py: create/get/list/update/delete + builtin guards
  - routes/presets.py: CRUD HTTP surface
  - migration 0008: render_presets table created
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch


# ── domain/render_preset.py ───────────────────────────────────────────────────

def test_render_preset_from_row_full():
    from app.domain.render_preset import RenderPreset

    row = {
        "preset_id": "p1", "name": "My Preset", "description": "desc",
        "channel_code": "vn", "platform": "tiktok",
        "params_json": '{"output_count": 3, "target_platform": "tiktok"}',
        "is_builtin": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }
    p = RenderPreset.from_row(row)
    assert p.preset_id == "p1"
    assert p.name == "My Preset"
    assert p.is_builtin is True
    assert p.params["output_count"] == 3
    assert p.params["target_platform"] == "tiktok"


def test_render_preset_from_row_strips_disallowed_params():
    from app.domain.render_preset import RenderPreset

    row = {
        "preset_id": "p1", "name": "N",
        "params_json": '{"output_count": 2, "SECRET_KEY": "bad", "source_mode": "evil"}',
        "is_builtin": 0, "created_at": "", "updated_at": "",
        "description": "", "channel_code": "", "platform": "",
    }
    p = RenderPreset.from_row(row)
    assert "SECRET_KEY" not in p.params
    assert "source_mode" not in p.params
    assert p.params.get("output_count") == 2


def test_render_preset_from_row_bad_json_returns_empty_params():
    from app.domain.render_preset import RenderPreset

    row = {
        "preset_id": "p1", "name": "N", "params_json": "not json",
        "is_builtin": 0, "created_at": "", "updated_at": "",
        "description": "", "channel_code": "", "platform": "",
    }
    p = RenderPreset.from_row(row)
    assert p.params == {}


def test_render_preset_from_row_non_dict_returns_default():
    from app.domain.render_preset import RenderPreset

    p = RenderPreset.from_row("bad")  # type: ignore[arg-type]
    assert p.preset_id == ""


def test_render_preset_to_dict_keys():
    from app.domain.render_preset import RenderPreset

    p = RenderPreset(preset_id="p1", name="N")
    d = p.to_dict()
    for key in ("preset_id", "name", "description", "channel_code", "platform",
                "params", "is_builtin", "created_at", "updated_at"):
        assert key in d


def test_preset_allowed_params_contains_expected():
    from app.domain.render_preset import PRESET_ALLOWED_PARAMS

    expected = {"output_count", "target_platform", "target_duration",
                "video_type", "hook_strength", "add_subtitle",
                "subtitle_style", "llm_enabled", "ai_provider",
                "ai_clip_min_duration_sec", "ai_clip_max_duration_sec"}
    assert expected.issubset(PRESET_ALLOWED_PARAMS)


# ── db/presets_repo.py ────────────────────────────────────────────────────────

def _mock_conn():
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def test_create_preset_calls_upsert_non_builtin():
    from app.db.presets_repo import create_preset

    mock = _mock_conn()
    with patch("app.db.presets_repo.db_conn", return_value=mock):
        create_preset("p1", "My Preset", {"output_count": 2})

    sql = mock.execute.call_args[0][0]
    assert "INSERT INTO render_presets" in sql


def test_get_preset_returns_none_when_missing():
    from app.db.presets_repo import get_preset

    mock = _mock_conn()
    mock.execute.return_value.fetchone.return_value = None

    with patch("app.db.presets_repo.db_conn", return_value=mock):
        result = get_preset("nonexistent")

    assert result is None


def test_get_preset_returns_object():
    from app.db.presets_repo import get_preset

    row = {
        "preset_id": "p1", "name": "N", "description": "",
        "channel_code": "", "platform": "", "params_json": "{}",
        "is_builtin": 0, "created_at": "", "updated_at": "",
    }
    mock = _mock_conn()
    mock.execute.return_value.fetchone.return_value = row

    with patch("app.db.presets_repo.db_conn", return_value=mock):
        result = get_preset("p1")

    assert result is not None
    assert result.preset_id == "p1"


def test_update_preset_returns_false_when_not_found():
    from app.db.presets_repo import update_preset

    with patch("app.db.presets_repo.get_preset", return_value=None):
        ok = update_preset("missing", "N", {})

    assert ok is False


def test_update_preset_returns_false_for_builtin():
    from app.db.presets_repo import update_preset
    from app.domain.render_preset import RenderPreset

    builtin = RenderPreset(preset_id="p1", name="B", is_builtin=True)
    with patch("app.db.presets_repo.get_preset", return_value=builtin):
        ok = update_preset("p1", "New Name", {})

    assert ok is False


def test_update_preset_returns_true_for_custom():
    from app.db.presets_repo import update_preset
    from app.domain.render_preset import RenderPreset

    custom = RenderPreset(preset_id="p1", name="C", is_builtin=False)
    mock = _mock_conn()
    with patch("app.db.presets_repo.get_preset", return_value=custom), \
         patch("app.db.presets_repo.db_conn", return_value=mock):
        ok = update_preset("p1", "New Name", {"output_count": 3})

    assert ok is True


def test_delete_preset_returns_false_for_builtin():
    from app.db.presets_repo import delete_preset
    from app.domain.render_preset import RenderPreset

    builtin = RenderPreset(preset_id="p1", is_builtin=True)
    with patch("app.db.presets_repo.get_preset", return_value=builtin):
        ok = delete_preset("p1")

    assert ok is False


def test_delete_preset_returns_false_when_not_found():
    from app.db.presets_repo import delete_preset

    with patch("app.db.presets_repo.get_preset", return_value=None):
        ok = delete_preset("nonexistent")

    assert ok is False


def test_delete_preset_returns_true_for_custom():
    from app.db.presets_repo import delete_preset
    from app.domain.render_preset import RenderPreset

    custom = RenderPreset(preset_id="p1", is_builtin=False)
    mock = _mock_conn()
    with patch("app.db.presets_repo.get_preset", return_value=custom), \
         patch("app.db.presets_repo.db_conn", return_value=mock):
        ok = delete_preset("p1")

    assert ok is True


# ── routes/presets.py ─────────────────────────────────────────────────────────

def _client():
    from app.main import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_get_presets_returns_list():
    from app.domain.render_preset import RenderPreset

    presets = [RenderPreset(preset_id="p1", name="N", is_builtin=True)]
    with patch("app.routes.presets.list_presets", return_value=presets):
        resp = _client().get("/api/presets")

    assert resp.status_code == 200
    assert resp.json()["presets"][0]["preset_id"] == "p1"


def test_get_preset_by_id_found():
    from app.domain.render_preset import RenderPreset

    preset = RenderPreset(preset_id="p1", name="N")
    with patch("app.routes.presets.get_preset", return_value=preset):
        resp = _client().get("/api/presets/p1")

    assert resp.status_code == 200
    assert resp.json()["preset_id"] == "p1"


def test_get_preset_by_id_not_found():
    with patch("app.routes.presets.get_preset", return_value=None):
        resp = _client().get("/api/presets/missing")

    assert resp.status_code == 404


def test_create_preset_endpoint():
    with patch("app.routes.presets.create_preset") as mock_create, \
         patch("app.routes.presets.get_preset", return_value=None), \
         patch("app.routes.presets.list_presets", return_value=[]):
        # We patch get_preset to None to avoid the 409 conflict check if any
        resp = _client().post("/api/presets", json={
            "name": "My Preset",
            "params": {"output_count": 2},
        })

    # May be 200 or 201 depending on implementation
    assert resp.status_code in (200, 201)


def test_delete_builtin_preset_returns_403():
    from app.domain.render_preset import RenderPreset

    builtin = RenderPreset(preset_id="p1", name="Builtin", is_builtin=True)
    with patch("app.routes.presets.get_preset", return_value=builtin):
        resp = _client().delete("/api/presets/p1")

    assert resp.status_code == 403


def test_delete_custom_preset_returns_2xx():
    from app.domain.render_preset import RenderPreset

    custom = RenderPreset(preset_id="p1", name="Custom", is_builtin=False)
    with patch("app.routes.presets.get_preset", return_value=custom), \
         patch("app.routes.presets.delete_preset", return_value=True):
        resp = _client().delete("/api/presets/p1")

    assert resp.status_code in (200, 204)


def test_delete_preset_not_found_returns_404():
    with patch("app.routes.presets.get_preset", return_value=None):
        resp = _client().delete("/api/presets/missing")

    assert resp.status_code == 404


# ── migration 0008 ────────────────────────────────────────────────────────────

import importlib.util
from pathlib import Path as _Path

_MIG_0008 = (
    _Path(__file__).resolve().parent.parent
    / "app" / "db" / "migration_steps" / "0008_add_render_presets_table.py"
)


def _load_0008():
    spec = importlib.util.spec_from_file_location("_mig_0008", _MIG_0008)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_0008_creates_render_presets_table():
    m = _load_0008()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    m.up(conn)
    conn.commit()

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "render_presets" in tables

    cols = {r[1] for r in conn.execute("PRAGMA table_info(render_presets)")}
    assert "preset_id" in cols
    assert "params_json" in cols
    assert "is_builtin" in cols


def test_migration_0008_idempotent():
    m = _load_0008()
    conn = sqlite3.connect(":memory:")
    m.up(conn)
    m.up(conn)  # must not raise
    conn.commit()
