"""B3 (2026-06-27) — preset adoption analytics (/api/analytics/presets).

Closes the F2 loop: how often is each preset picked? Pins the Python-side
aggregation (robust to malformed result_json) and the endpoint shape.
DB is mocked — no real seeding needed (mirrors test_phase_g_analytics).
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.routes.analytics import _query_preset_usage


def _conn_with_rows(rows):
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    conn.execute.return_value.fetchall.return_value = rows
    return conn


def _row(result_json, status="completed"):
    return {"result_json": result_json, "status": status}


def test_groups_counts_and_completed():
    rows = [
        _row(json.dumps({"render_preset_id": "builtin-tiktok-viral", "render_preset": "TikTok Viral"}), "completed"),
        _row(json.dumps({"render_preset_id": "builtin-tiktok-viral", "render_preset": "TikTok Viral"}), "failed"),
        _row(json.dumps({"render_preset_id": "custom", "render_preset": "custom"}), "completed"),
    ]
    with patch("app.routes.analytics.db_conn", return_value=_conn_with_rows(rows)):
        usage = _query_preset_usage()

    by_id = {e["preset_id"]: e for e in usage}
    assert by_id["builtin-tiktok-viral"]["count"] == 2
    assert by_id["builtin-tiktok-viral"]["completed"] == 1
    assert by_id["builtin-tiktok-viral"]["preset_name"] == "TikTok Viral"
    assert by_id["custom"]["count"] == 1
    # sorted by count desc — the viral preset (2) leads
    assert usage[0]["preset_id"] == "builtin-tiktok-viral"


def test_skips_empty_and_malformed_result_json():
    rows = [
        _row(None),
        _row(""),
        _row("not json {"),
        _row(json.dumps(["a", "list"])),  # valid JSON but not a dict
        _row(json.dumps({"render_preset_id": "builtin-x", "render_preset": "X"})),
    ]
    with patch("app.routes.analytics.db_conn", return_value=_conn_with_rows(rows)):
        usage = _query_preset_usage()

    assert len(usage) == 1
    assert usage[0]["preset_id"] == "builtin-x"
    assert usage[0]["count"] == 1


def test_missing_preset_id_defaults_to_custom():
    rows = [_row(json.dumps({"foo": "bar"}))]
    with patch("app.routes.analytics.db_conn", return_value=_conn_with_rows(rows)):
        usage = _query_preset_usage()
    assert usage[0]["preset_id"] == "custom"


def test_db_error_returns_empty():
    with patch("app.routes.analytics.db_conn", side_effect=RuntimeError("db down")):
        assert _query_preset_usage() == []


def test_endpoint_shape():
    from fastapi.testclient import TestClient
    from app.main import app

    with patch(
        "app.routes.analytics._query_preset_usage",
        return_value=[{"preset_id": "builtin-x", "preset_name": "X", "count": 3, "completed": 2}],
    ):
        resp = TestClient(app).get("/api/analytics/presets")

    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 0
    assert body["total_jobs"] == 3
    assert body["presets"][0]["preset_id"] == "builtin-x"
