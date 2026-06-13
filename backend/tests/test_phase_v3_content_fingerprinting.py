"""tests/test_phase_v3_content_fingerprinting.py — Phase V3: Content Fingerprinting.

Tests for:
  - get_channel_segment_repeat_rate: detects repeated (asset, start, end) tuples
  - get_channel_segment_repeat_rate: returns zero when all segments are unique
  - get_channel_segment_repeat_rate: returns zeros for channel with no data
  - get_channel_segment_repeat_rate: ignores parts with NULL/empty asset_id
  - get_channel_segment_repeat_rate: never raises on DB error
  - FeedbackSignals: has segment_repeat_pct and repeat_sample_size fields
  - build_signals(): maps both repeat fields from raw dict
  - to_prompt_hint(): warns about high repeat rate (> 30%, sample >= 5)
  - to_prompt_hint(): omits repeat warning when rate is low (≤ 30%)
  - to_prompt_hint(): omits repeat warning when sample too small (< 5)
  - get_feedback_signals(): return dict includes segment_repeat_pct key
"""
from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE jobs (
            job_id       TEXT PRIMARY KEY,
            channel_code TEXT NOT NULL DEFAULT '',
            asset_id     TEXT DEFAULT NULL,
            kind         TEXT DEFAULT 'render',
            status       TEXT DEFAULT 'completed'
        );
        CREATE TABLE job_parts (
            job_id    TEXT NOT NULL,
            part_no   INTEGER NOT NULL,
            start_sec REAL NOT NULL DEFAULT 0.0,
            end_sec   REAL NOT NULL DEFAULT 0.0,
            status    TEXT DEFAULT 'DONE',
            updated_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (job_id, part_no)
        );
    """)
    conn.commit()
    return conn


def _mock_conn():
    conn = MagicMock()
    conn.__enter__ = lambda s: s
    conn.__exit__ = MagicMock(return_value=False)
    return conn


def _insert_job(conn, job_id, channel_code, asset_id="asset_A"):
    conn.execute(
        "INSERT INTO jobs (job_id, channel_code, asset_id) VALUES (?, ?, ?)",
        (job_id, channel_code, asset_id),
    )


def _insert_part(conn, job_id, part_no, start_sec, end_sec):
    conn.execute(
        "INSERT INTO job_parts (job_id, part_no, start_sec, end_sec) VALUES (?, ?, ?, ?)",
        (job_id, part_no, start_sec, end_sec),
    )


# ── get_channel_segment_repeat_rate ──────────────────────────────────────────

def test_segment_repeat_rate_detects_repeats():
    """Same (asset, start, end) across two renders → repeat_pct > 0."""
    from app.db.jobs_repo import get_channel_segment_repeat_rate

    conn = _in_memory_db()
    # Job 1 and Job 2 both render segments at the same times from the same asset
    _insert_job(conn, "j1", "ch1", "asset_A")
    _insert_job(conn, "j2", "ch1", "asset_A")
    _insert_part(conn, "j1", 1, 10.0, 40.0)   # repeated in j2
    _insert_part(conn, "j1", 2, 60.0, 90.0)   # unique
    _insert_part(conn, "j2", 1, 10.0, 40.0)   # same as j1/part1 → repeat
    _insert_part(conn, "j2", 2, 95.0, 125.0)  # unique
    conn.commit()

    with patch("app.db.jobs_repo.db_conn", return_value=conn):
        result = get_channel_segment_repeat_rate("ch1")

    # 3 unique (asset, start, end) groups: (A,10,40) x2, (A,60,90) x1, (A,95,125) x1
    # repeated_groups = 1  (only (A,10,40) has cnt > 1)
    # total_groups = 3
    assert result["repeat_sample_size"] == 3
    assert abs(result["segment_repeat_pct"] - 1 / 3) < 0.01


def test_segment_repeat_rate_zero_when_all_unique():
    """All distinct segments → segment_repeat_pct == 0.0."""
    from app.db.jobs_repo import get_channel_segment_repeat_rate

    conn = _in_memory_db()
    _insert_job(conn, "j1", "ch1", "asset_A")
    _insert_job(conn, "j2", "ch1", "asset_A")
    _insert_part(conn, "j1", 1, 0.0, 30.0)
    _insert_part(conn, "j2", 1, 50.0, 80.0)  # different time range
    conn.commit()

    with patch("app.db.jobs_repo.db_conn", return_value=conn):
        result = get_channel_segment_repeat_rate("ch1")

    assert result["segment_repeat_pct"] == 0.0
    assert result["repeat_sample_size"] == 2


def test_segment_repeat_rate_empty_channel():
    """No data for channel → returns zeros."""
    from app.db.jobs_repo import get_channel_segment_repeat_rate

    conn = _in_memory_db()
    with patch("app.db.jobs_repo.db_conn", return_value=conn):
        result = get_channel_segment_repeat_rate("nonexistent")

    assert result["segment_repeat_pct"] == 0.0
    assert result["repeat_sample_size"] == 0


def test_segment_repeat_rate_ignores_null_asset_id():
    """Parts with NULL or empty asset_id are excluded from fingerprinting."""
    from app.db.jobs_repo import get_channel_segment_repeat_rate

    conn = _in_memory_db()
    # Job with NULL asset_id
    conn.execute(
        "INSERT INTO jobs (job_id, channel_code, asset_id) VALUES ('j1', 'ch1', NULL)"
    )
    _insert_part(conn, "j1", 1, 10.0, 40.0)
    # Job with empty string asset_id
    conn.execute(
        "INSERT INTO jobs (job_id, channel_code, asset_id) VALUES ('j2', 'ch1', '')"
    )
    _insert_part(conn, "j2", 1, 10.0, 40.0)
    conn.commit()

    with patch("app.db.jobs_repo.db_conn", return_value=conn):
        result = get_channel_segment_repeat_rate("ch1")

    assert result["repeat_sample_size"] == 0


def test_segment_repeat_rate_never_raises():
    """DB error → returns zeros, does not propagate."""
    from app.db.jobs_repo import get_channel_segment_repeat_rate

    mock = _mock_conn()
    mock.execute.side_effect = RuntimeError("DB exploded")
    with patch("app.db.jobs_repo.db_conn", return_value=mock):
        result = get_channel_segment_repeat_rate("ch1")

    assert result == {"segment_repeat_pct": 0.0, "repeat_sample_size": 0}


# ── FeedbackSignals V3 fields ─────────────────────────────────────────────────

def test_feedback_signals_has_repeat_fields():
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals()
    assert hasattr(sig, "segment_repeat_pct")
    assert hasattr(sig, "repeat_sample_size")
    assert sig.segment_repeat_pct == 0.0
    assert sig.repeat_sample_size == 0


def test_build_signals_reads_repeat_fields():
    from app.features.render.ai.feedback.signals import build_signals
    raw = {
        "liked_hook_types": [], "avoided_hook_types": [],
        "preferred_duration": None, "sample_size": 0,
        "segment_repeat_pct": 0.55, "repeat_sample_size": 12,
    }
    sig = build_signals(raw)
    assert abs(sig.segment_repeat_pct - 0.55) < 0.001
    assert sig.repeat_sample_size == 12


def test_to_prompt_hint_warns_high_repeat():
    """Emits diversity warning when repeat_pct > 30% and sample >= 5."""
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals(segment_repeat_pct=0.60, repeat_sample_size=10)
    hint = sig.to_prompt_hint()
    assert "60%" in hint or "divers" in hint.lower()
    assert "10" in hint


def test_to_prompt_hint_omits_repeat_when_low_rate():
    """No warning when repeat rate is ≤ 30% (good diversity)."""
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals(segment_repeat_pct=0.20, repeat_sample_size=10)
    hint = sig.to_prompt_hint()
    assert hint == "", f"Expected no hint for low repeat rate, got: {hint!r}"


def test_to_prompt_hint_omits_repeat_when_too_few_samples():
    """No warning when repeat_sample_size < 5 (insufficient data)."""
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals(segment_repeat_pct=0.80, repeat_sample_size=4)
    hint = sig.to_prompt_hint()
    assert hint == "", f"Expected no hint for small sample, got: {hint!r}"


# ── get_feedback_signals dict extension ──────────────────────────────────────

def test_get_feedback_signals_includes_repeat_keys():
    from app.db import feedback_repo

    with (
        patch.object(feedback_repo, "list_feedback_for_channel", return_value=[]),
        patch(
            "app.db.platform_metrics_repo.get_channel_platform_summary",
            return_value={"avg_watch_pct": 0.0, "avg_ctr": 0.0, "platform_sample_size": 0},
        ),
        patch(
            "app.db.jobs_repo.get_channel_cover_quality_summary",
            return_value={"pct_sharp_cover": 0.0, "pct_face_cover": 0.0, "quality_sample_size": 0},
        ),
        patch(
            "app.db.jobs_repo.get_channel_segment_repeat_rate",
            return_value={"segment_repeat_pct": 0.45, "repeat_sample_size": 8},
        ),
    ):
        signals = feedback_repo.get_feedback_signals("ch1")

    assert "segment_repeat_pct" in signals
    assert "repeat_sample_size" in signals
    assert abs(signals["segment_repeat_pct"] - 0.45) < 0.001
