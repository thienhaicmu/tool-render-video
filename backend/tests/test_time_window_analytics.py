"""Sprint L-C — Time-window analytics tests.

1. Migration 0006 adds created_at column to render_ab_scores.
2. Migration 0006 is idempotent (safe to run twice).
3. Summary endpoint without ?since — repo called with since=None.
4. Summary endpoint with ?since=2026-06-01 — repo called with that value.
5. Summary endpoint returns [] when since filter excludes all rows.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sqlite3
from unittest.mock import patch

from fastapi.testclient import TestClient

_STEP_PATH = (
    pathlib.Path(__file__).parent.parent
    / "app" / "db" / "migration_steps"
    / "0006_add_created_at_to_render_ab_scores.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_0006", _STEP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fresh_db_with_ab_scores_table():
    """In-memory DB with render_ab_scores table but WITHOUT created_at column."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE render_ab_scores (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id            TEXT    NOT NULL,
            part_no           INTEGER NOT NULL,
            channel_code      TEXT    NOT NULL DEFAULT '',
            structure_bias    TEXT    NOT NULL DEFAULT 'balanced',
            viral_score       REAL    NOT NULL DEFAULT 50.0,
            hook_score        REAL    NOT NULL DEFAULT 50.0,
            retention_score   REAL    NOT NULL DEFAULT 50.0,
            output_rank_score REAL    NOT NULL DEFAULT 50.0,
            output_rank       INTEGER NOT NULL DEFAULT 0,
            is_best_output    INTEGER NOT NULL DEFAULT 0,
            feedback_rating   INTEGER NOT NULL DEFAULT 0,
            scored_at         TEXT    NOT NULL DEFAULT (datetime('now')),
            UNIQUE(job_id, part_no)
        )
    """)
    return conn


def _client():
    from app.main import app
    return TestClient(app)


def test_migration_0006_adds_created_at_column():
    mig = _load_migration()
    conn = _fresh_db_with_ab_scores_table()
    mig.up(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(render_ab_scores)").fetchall()}
    assert "created_at" in cols


def test_migration_0006_is_idempotent():
    mig = _load_migration()
    conn = _fresh_db_with_ab_scores_table()
    mig.up(conn)
    # Running a second time must not raise
    mig.up(conn)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(render_ab_scores)").fetchall()}
    assert "created_at" in cols


def test_summary_without_since_calls_repo_with_none():
    with patch("app.db.ab_scores_repo.channel_score_summary", return_value=[]) as mock_fn:
        resp = _client().get("/api/settings/scores/vn/summary")
    assert resp.status_code == 200
    mock_fn.assert_called_once_with("vn", since=None)


def test_summary_with_since_forwards_value():
    with patch("app.db.ab_scores_repo.channel_score_summary", return_value=[]) as mock_fn:
        resp = _client().get("/api/settings/scores/vn/summary?since=2026-06-01")
    assert resp.status_code == 200
    mock_fn.assert_called_once_with("vn", since="2026-06-01")


def test_summary_returns_empty_when_since_filters_all():
    with patch("app.db.ab_scores_repo.channel_score_summary", return_value=[]):
        resp = _client().get("/api/settings/scores/vn/summary?since=2099-01-01")
    assert resp.status_code == 200
    assert resp.json() == []
