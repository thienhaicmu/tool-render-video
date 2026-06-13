"""tests/test_phase_v1_platform_metrics.py — Phase V1: Platform Performance Ingestion.

Tests for:
  - Migration 0010: creates platform_metrics table and indexes, idempotent
  - upsert_platform_metric: inserts row, returns True; returns False on DB error
  - upsert_platform_metric: re-posting same post_id with non-empty post updates row
  - get_channel_platform_summary: averages watch_pct/ctr correctly
  - get_channel_platform_summary: returns zeros when no data
  - list_platform_metrics: returns rows ordered by recorded_at DESC
  - FeedbackSignals: has 3 new platform fields (avg_watch_pct, avg_ctr, platform_sample_size)
  - build_signals(): maps new platform fields from raw dict
  - to_prompt_hint(): includes platform performance line when platform_sample_size >= 3
  - to_prompt_hint(): omits platform line when platform_sample_size < 3
  - get_feedback_signals(): return dict now includes avg_watch_pct/avg_ctr keys
  - POST /api/feedback/platform-metrics endpoint returns 201
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path as _Path
from unittest.mock import MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

_MIG_DIR = (
    _Path(__file__).resolve().parent.parent
    / "app" / "db" / "migration_steps"
)


def _load_migration(filename: str):
    path = _MIG_DIR / filename
    spec = importlib.util.spec_from_file_location(f"_mig_{filename}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _in_memory_db_with_migration_0010():
    m = _load_migration("0010_add_platform_metrics_table.py")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    m.up(conn)
    conn.commit()
    return conn


def _mock_conn():
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


# ── migration 0010 ────────────────────────────────────────────────────────────

def test_migration_0010_creates_table():
    m = _load_migration("0010_add_platform_metrics_table.py")
    assert m.VERSION == 10
    assert m.NAME == "add_platform_metrics_table"
    conn = sqlite3.connect(":memory:")
    m.up(conn)
    conn.commit()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "platform_metrics" in tables


def test_migration_0010_idempotent():
    m = _load_migration("0010_add_platform_metrics_table.py")
    conn = sqlite3.connect(":memory:")
    m.up(conn)
    m.up(conn)  # second run must not raise
    conn.commit()


# ── upsert_platform_metric ────────────────────────────────────────────────────

def test_upsert_platform_metric_inserts_row():
    from app.db.platform_metrics_repo import upsert_platform_metric

    conn = _in_memory_db_with_migration_0010()
    with patch("app.db.platform_metrics_repo.db_conn", return_value=conn):
        ok = upsert_platform_metric(
            channel_code="chan1",
            platform="tiktok",
            post_id="post123",
            watch_pct=0.72,
            ctr=0.05,
            impressions=10000,
            recorded_at="2026-06-01T00:00:00Z",
        )
    assert ok is True
    row = conn.execute(
        "SELECT watch_pct, ctr FROM platform_metrics WHERE post_id='post123'"
    ).fetchone()
    assert row is not None
    assert abs(row[0] - 0.72) < 0.001


def test_upsert_platform_metric_returns_false_on_error():
    from app.db.platform_metrics_repo import upsert_platform_metric

    mock = _mock_conn()
    mock.execute.side_effect = RuntimeError("DB unavailable")
    with patch("app.db.platform_metrics_repo.db_conn", return_value=mock):
        result = upsert_platform_metric(channel_code="c", platform="tt")
    assert result is False


def test_upsert_platform_metric_updates_existing_post():
    """Re-posting same (channel, platform, post_id) updates, not duplicates."""
    from app.db.platform_metrics_repo import upsert_platform_metric

    conn = _in_memory_db_with_migration_0010()
    with patch("app.db.platform_metrics_repo.db_conn", return_value=conn):
        upsert_platform_metric(
            channel_code="ch", platform="tiktok", post_id="p1",
            watch_pct=0.5, ctr=0.02, recorded_at="2026-01-01",
        )
        upsert_platform_metric(
            channel_code="ch", platform="tiktok", post_id="p1",
            watch_pct=0.8, ctr=0.06, recorded_at="2026-01-02",
        )
    count = conn.execute(
        "SELECT COUNT(*) FROM platform_metrics WHERE post_id='p1'"
    ).fetchone()[0]
    assert count == 1, "Re-posting same post_id must update, not duplicate"
    watch = conn.execute(
        "SELECT watch_pct FROM platform_metrics WHERE post_id='p1'"
    ).fetchone()[0]
    assert abs(watch - 0.8) < 0.001, "Updated value expected"


# ── get_channel_platform_summary ──────────────────────────────────────────────

def test_get_channel_platform_summary_averages():
    from app.db.platform_metrics_repo import (
        get_channel_platform_summary,
        upsert_platform_metric,
    )

    conn = _in_memory_db_with_migration_0010()
    with patch("app.db.platform_metrics_repo.db_conn", return_value=conn):
        upsert_platform_metric(
            channel_code="ch", platform="tiktok", post_id="a",
            watch_pct=0.60, ctr=0.04, recorded_at="2026-01-01",
        )
        upsert_platform_metric(
            channel_code="ch", platform="tiktok", post_id="b",
            watch_pct=0.80, ctr=0.06, recorded_at="2026-01-02",
        )
        summary = get_channel_platform_summary("ch", platform="tiktok")

    assert summary["platform_sample_size"] == 2
    assert abs(summary["avg_watch_pct"] - 0.70) < 0.01
    assert abs(summary["avg_ctr"] - 0.05) < 0.01


def test_get_channel_platform_summary_empty():
    from app.db.platform_metrics_repo import get_channel_platform_summary

    conn = _in_memory_db_with_migration_0010()
    with patch("app.db.platform_metrics_repo.db_conn", return_value=conn):
        summary = get_channel_platform_summary("nonexistent_channel")

    assert summary["platform_sample_size"] == 0
    assert summary["avg_watch_pct"] == 0.0
    assert summary["avg_ctr"] == 0.0


# ── FeedbackSignals + build_signals ──────────────────────────────────────────

def test_feedback_signals_has_platform_fields():
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals()
    assert hasattr(sig, "avg_watch_pct")
    assert hasattr(sig, "avg_ctr")
    assert hasattr(sig, "platform_sample_size")
    assert sig.avg_watch_pct is None
    assert sig.platform_sample_size == 0


def test_build_signals_reads_platform_fields():
    from app.features.render.ai.feedback.signals import build_signals
    raw = {
        "liked_hook_types": [],
        "avoided_hook_types": [],
        "preferred_duration": None,
        "sample_size": 5,
        "avg_watch_pct": 0.65,
        "avg_ctr": 0.03,
        "platform_sample_size": 10,
    }
    sig = build_signals(raw)
    assert abs(sig.avg_watch_pct - 0.65) < 0.001
    assert abs(sig.avg_ctr - 0.03) < 0.001
    assert sig.platform_sample_size == 10


def test_to_prompt_hint_includes_platform_line():
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals(
        avg_watch_pct=0.72,
        avg_ctr=0.045,
        platform_sample_size=20,
        sample_size=0,
    )
    hint = sig.to_prompt_hint()
    assert "72%" in hint or "watch" in hint.lower()
    assert "20" in hint


def test_to_prompt_hint_omits_platform_line_when_too_few_samples():
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals(
        avg_watch_pct=0.72,
        avg_ctr=0.045,
        platform_sample_size=2,  # below threshold of 3
        sample_size=0,
    )
    hint = sig.to_prompt_hint()
    assert hint == "", f"Expected empty hint, got: {hint!r}"


# ── get_feedback_signals dict extension ──────────────────────────────────────

def test_get_feedback_signals_includes_platform_keys():
    """get_feedback_signals() return dict includes avg_watch_pct, avg_ctr, platform_sample_size."""
    from app.db import feedback_repo

    with (
        patch.object(
            feedback_repo,
            "list_feedback_for_channel",
            return_value=[
                {
                    "hook_type": "question", "rating": 1,
                    "duration_sec": 30.0, "start_sec": 5.0,
                    "end_sec": 35.0, "channel_code": "ch",
                    "goal": "", "job_id": "j1", "part_no": 1,
                    "clip_type": "hook", "rated_at": "2026-01-01",
                }
            ] * 5,
        ),
        patch(
            "app.db.platform_metrics_repo.get_channel_platform_summary",
            return_value={"avg_watch_pct": 0.68, "avg_ctr": 0.04, "platform_sample_size": 8},
        ),
    ):
        signals = feedback_repo.get_feedback_signals("ch")

    assert "avg_watch_pct" in signals
    assert "avg_ctr" in signals
    assert "platform_sample_size" in signals
    assert abs(signals["avg_watch_pct"] - 0.68) < 0.001


# ── POST /api/feedback/platform-metrics endpoint ─────────────────────────────

def test_post_platform_metrics_endpoint_returns_201():
    from fastapi.testclient import TestClient
    from app.main import app

    with patch("app.routes.feedback.upsert_platform_metric", return_value=True) as mock_upsert:
        resp = TestClient(app).post(
            "/api/feedback/platform-metrics",
            json={
                "metrics": [
                    {
                        "channel_code": "ch1",
                        "platform": "tiktok",
                        "post_id": "vid_001",
                        "watch_pct": 0.75,
                        "ctr": 0.05,
                        "impressions": 50000,
                        "recorded_at": "2026-06-01T00:00:00Z",
                    }
                ]
            },
        )

    assert resp.status_code == 201
    body = resp.json()
    assert body["ingested"] == 1
    assert body["failed"] == 0
    mock_upsert.assert_called_once()
