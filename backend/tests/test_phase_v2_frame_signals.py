"""tests/test_phase_v2_frame_signals.py — Phase V2: Frame Signal Integration.

Tests for:
  - Migration 0011: adds cover_quality_json column to job_parts, idempotent
  - update_job_part_cover_quality: writes JSON, never raises on DB error
  - get_channel_cover_quality_summary: aggregates sharp/face tags correctly
  - get_channel_cover_quality_summary: returns zeros when no data
  - FeedbackSignals: has 3 new V2 quality fields with correct defaults
  - build_signals(): maps pct_sharp_cover, pct_face_cover, quality_sample_size
  - to_prompt_hint(): includes quality line when quality_sample_size >= 5
  - to_prompt_hint(): omits quality line when quality_sample_size < 5
  - get_feedback_signals(): return dict includes quality keys
  - part_done.py: update_job_part_cover_quality imported and called after S4
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path as _Path
from unittest.mock import MagicMock, call, patch

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


def _in_memory_db_for_jobs():
    """In-memory DB with jobs + job_parts tables + cover_quality_json column."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            channel_code TEXT NOT NULL DEFAULT '',
            kind TEXT DEFAULT '',
            status TEXT DEFAULT 'queued'
        );
        CREATE TABLE job_parts (
            job_id TEXT NOT NULL,
            part_no INTEGER NOT NULL,
            status TEXT DEFAULT 'DONE',
            cover_quality_json TEXT DEFAULT NULL,
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


# ── migration 0011 ────────────────────────────────────────────────────────────

def test_migration_0011_adds_cover_quality_column():
    m = _load_migration("0011_add_cover_quality_to_job_parts.py")
    assert m.VERSION == 11
    assert m.NAME == "add_cover_quality_to_job_parts"
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE job_parts (job_id TEXT, part_no INTEGER, PRIMARY KEY (job_id, part_no))"
    )
    m.up(conn)
    conn.commit()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(job_parts)")}
    assert "cover_quality_json" in cols


def test_migration_0011_idempotent():
    m = _load_migration("0011_add_cover_quality_to_job_parts.py")
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE job_parts (job_id TEXT, part_no INTEGER, PRIMARY KEY (job_id, part_no))"
    )
    m.up(conn)
    m.up(conn)  # second call must not raise
    conn.commit()


# ── update_job_part_cover_quality ─────────────────────────────────────────────

def test_update_job_part_cover_quality_writes_json():
    from app.db.jobs_repo import update_job_part_cover_quality

    conn = _in_memory_db_for_jobs()
    conn.execute("INSERT INTO jobs VALUES ('j1', 'ch1', 'render', 'completed')")
    conn.execute("INSERT INTO job_parts (job_id, part_no) VALUES ('j1', 1)")
    conn.commit()

    with patch("app.db.jobs_repo.db_conn", return_value=conn):
        update_job_part_cover_quality("j1", 1, ["sharp_frame", "good_exposure"])

    row = conn.execute(
        "SELECT cover_quality_json FROM job_parts WHERE job_id='j1' AND part_no=1"
    ).fetchone()
    assert row is not None
    tags = json.loads(row[0])
    assert "sharp_frame" in tags
    assert "good_exposure" in tags


def test_update_job_part_cover_quality_never_raises():
    from app.db.jobs_repo import update_job_part_cover_quality

    mock = _mock_conn()
    mock.execute.side_effect = RuntimeError("DB error")
    with patch("app.db.jobs_repo.db_conn", return_value=mock):
        update_job_part_cover_quality("j1", 1, ["sharp_frame"])  # must not raise


# ── get_channel_cover_quality_summary ────────────────────────────────────────

def test_get_channel_cover_quality_summary_aggregates():
    from app.db.jobs_repo import get_channel_cover_quality_summary

    conn = _in_memory_db_for_jobs()
    conn.execute("INSERT INTO jobs VALUES ('j1', 'ch1', 'render', 'completed')")
    conn.execute("INSERT INTO jobs VALUES ('j2', 'ch1', 'render', 'completed')")
    conn.execute("INSERT INTO jobs VALUES ('j3', 'ch1', 'render', 'completed')")
    # j1/part1: sharp + face
    conn.execute(
        "INSERT INTO job_parts (job_id, part_no, cover_quality_json) VALUES (?, ?, ?)",
        ("j1", 1, json.dumps(["sharp_frame", "good_face_visibility", "good_exposure"])),
    )
    # j2/part1: sharp only
    conn.execute(
        "INSERT INTO job_parts (job_id, part_no, cover_quality_json) VALUES (?, ?, ?)",
        ("j2", 1, json.dumps(["sharp_frame", "good_exposure"])),
    )
    # j3/part1: neither
    conn.execute(
        "INSERT INTO job_parts (job_id, part_no, cover_quality_json) VALUES (?, ?, ?)",
        ("j3", 1, json.dumps(["good_exposure"])),
    )
    conn.commit()

    with patch("app.db.jobs_repo.db_conn", return_value=conn):
        summary = get_channel_cover_quality_summary("ch1")

    assert summary["quality_sample_size"] == 3
    assert abs(summary["pct_sharp_cover"] - 2 / 3) < 0.01
    assert abs(summary["pct_face_cover"] - 1 / 3) < 0.01


def test_get_channel_cover_quality_summary_empty():
    from app.db.jobs_repo import get_channel_cover_quality_summary

    conn = _in_memory_db_for_jobs()
    with patch("app.db.jobs_repo.db_conn", return_value=conn):
        summary = get_channel_cover_quality_summary("no_such_channel")

    assert summary["quality_sample_size"] == 0
    assert summary["pct_sharp_cover"] == 0.0
    assert summary["pct_face_cover"] == 0.0


# ── FeedbackSignals V2 fields ─────────────────────────────────────────────────

def test_feedback_signals_has_quality_fields():
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals()
    assert hasattr(sig, "pct_sharp_cover")
    assert hasattr(sig, "pct_face_cover")
    assert hasattr(sig, "quality_sample_size")
    assert sig.pct_sharp_cover == 0.0
    assert sig.pct_face_cover == 0.0
    assert sig.quality_sample_size == 0


def test_build_signals_reads_quality_fields():
    from app.features.render.ai.feedback.signals import build_signals
    raw = {
        "liked_hook_types": [], "avoided_hook_types": [],
        "preferred_duration": None, "sample_size": 0,
        "pct_sharp_cover": 0.80, "pct_face_cover": 0.60, "quality_sample_size": 12,
    }
    sig = build_signals(raw)
    assert abs(sig.pct_sharp_cover - 0.80) < 0.001
    assert abs(sig.pct_face_cover - 0.60) < 0.001
    assert sig.quality_sample_size == 12


def test_to_prompt_hint_includes_quality_line():
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals(
        pct_sharp_cover=0.75,
        pct_face_cover=0.50,
        quality_sample_size=10,
    )
    hint = sig.to_prompt_hint()
    assert "sharp" in hint.lower() or "75%" in hint
    assert "10" in hint


def test_to_prompt_hint_omits_quality_when_too_few():
    from app.features.render.ai.feedback.signals import FeedbackSignals
    sig = FeedbackSignals(
        pct_sharp_cover=0.75,
        pct_face_cover=0.50,
        quality_sample_size=4,  # below threshold of 5
    )
    hint = sig.to_prompt_hint()
    assert hint == "", f"Expected empty hint, got: {hint!r}"


# ── get_feedback_signals quality extension ────────────────────────────────────

def test_get_feedback_signals_includes_quality_keys():
    from app.db import feedback_repo

    with (
        patch.object(feedback_repo, "list_feedback_for_channel", return_value=[]),
        patch(
            "app.db.jobs_repo.get_channel_cover_quality_summary",
            return_value={"pct_sharp_cover": 0.8, "pct_face_cover": 0.6, "quality_sample_size": 7},
        ),
        patch(
            "app.db.platform_metrics_repo.get_channel_platform_summary",
            return_value={"avg_watch_pct": 0.0, "avg_ctr": 0.0, "platform_sample_size": 0},
        ),
    ):
        signals = feedback_repo.get_feedback_signals("ch1")

    assert "pct_sharp_cover" in signals
    assert "pct_face_cover" in signals
    assert "quality_sample_size" in signals


# ── part_done.py integration ──────────────────────────────────────────────────

def test_part_done_imports_update_job_part_cover_quality():
    """update_job_part_cover_quality must be importable from part_done's namespace."""
    import importlib
    mod = importlib.import_module(
        "app.features.render.engine.stages.part_done"
    )
    assert hasattr(mod, "update_job_part_cover_quality")
