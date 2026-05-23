"""
test_ai_trace_logger_pacing.py — Tests for Phase 5.4 trace logger additions.

Covers:
- log_pacing_applied writes valid JSONL with "ai.pacing_applied" event
- payload contains applied, cut_interval_min/max, source_knowledge_ids
- never raises even with bad path
- log_pacing_applied with applied=False still writes a record
- event shape matches spec
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from app.ai.tracing import AITraceLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracer(tmp_dir):
    """Create an AITraceLogger writing to tmp_dir."""
    return AITraceLogger("test-pacing-job-001", log_dir=Path(tmp_dir))


def _read_lines(tmp_dir, job_id="test-pacing-job-001"):
    """Read all JSONL lines from the trace log."""
    path = Path(tmp_dir) / f"{job_id}_ai_trace.jsonl"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# 1. log_pacing_applied writes valid JSONL with "ai.pacing_applied"
# ---------------------------------------------------------------------------

def test_log_pacing_applied_writes_event():
    """log_pacing_applied writes a line with event=ai.pacing_applied."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({
            "applied": True,
            "cut_interval_min": 3.0,
            "cut_interval_max": 5.0,
            "source_knowledge_ids": ["k1", "k2"],
            "reason": "valid_ai_pacing_hint",
        })
        lines = _read_lines(tmp)

    assert len(lines) == 1
    rec = lines[0]
    assert rec["event"] == "ai.pacing_applied"


def test_log_pacing_applied_contains_required_fields():
    """log_pacing_applied output has all required payload fields."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({
            "applied": True,
            "cut_interval_min": 3.0,
            "cut_interval_max": 5.0,
            "source_knowledge_ids": ["p1"],
            "reason": "valid_ai_pacing_hint",
        })
        lines = _read_lines(tmp)

    rec = lines[0]
    assert rec["applied"] is True
    assert rec["cut_interval_min"] == 3.0
    assert rec["cut_interval_max"] == 5.0
    assert rec["source_knowledge_ids"] == ["p1"]
    assert rec["target"] == "segment_selection"
    assert rec["reason"] == "valid_ai_pacing_hint"


def test_log_pacing_applied_has_job_id_and_timestamp():
    """log_pacing_applied output has job_id and timestamp fields."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({"applied": True})
        lines = _read_lines(tmp)

    rec = lines[0]
    assert rec["job_id"] == "test-pacing-job-001"
    assert "timestamp" in rec


def test_log_pacing_applied_false():
    """log_pacing_applied with applied=False writes the event correctly."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({
            "applied": False,
            "cut_interval_min": None,
            "cut_interval_max": None,
            "source_knowledge_ids": [],
            "reason": "no_pacing_hint",
        })
        lines = _read_lines(tmp)

    assert len(lines) == 1
    rec = lines[0]
    assert rec["event"] == "ai.pacing_applied"
    assert rec["applied"] is False
    assert rec["cut_interval_min"] is None
    assert rec["cut_interval_max"] is None
    assert rec["reason"] == "no_pacing_hint"


# ---------------------------------------------------------------------------
# 2. Valid JSONL — parseable JSON on every line
# ---------------------------------------------------------------------------

def test_log_pacing_applied_valid_jsonl():
    """Each written line is valid JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({
            "applied": True,
            "cut_interval_min": 2.5,
            "cut_interval_max": 7.0,
            "source_knowledge_ids": ["x"],
        })
        path = Path(tmp) / "test-pacing-job-001_ai_trace.jsonl"
        with open(path, encoding="utf-8") as fh:
            content = fh.read()

    for line in content.strip().split("\n"):
        parsed = json.loads(line)  # must not raise
        assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# 3. Never raises even with bad path
# ---------------------------------------------------------------------------

def test_log_pacing_applied_bad_path_no_raise():
    """log_pacing_applied never raises even if log dir is not writable."""
    tracer = AITraceLogger("test-pacing-bad", log_dir=Path("/nonexistent/path/xyz"))
    # Must not raise
    tracer.log_pacing_applied({
        "applied": True,
        "cut_interval_min": 3.0,
        "cut_interval_max": 5.0,
        "source_knowledge_ids": [],
    })


def test_log_pacing_applied_empty_config_no_raise():
    """log_pacing_applied with empty dict does not raise."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({})  # must not raise
        lines = _read_lines(tmp)

    assert len(lines) == 1
    rec = lines[0]
    assert rec["event"] == "ai.pacing_applied"
    assert rec["applied"] is False  # default when not specified


def test_log_pacing_applied_none_config_no_raise():
    """log_pacing_applied with None config does not raise."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied(None)  # must not raise
        lines = _read_lines(tmp)

    assert len(lines) == 1


def test_log_pacing_applied_garbage_config_no_raise():
    """log_pacing_applied with garbage config does not raise."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied("this_is_not_a_dict")  # must not raise
        lines = _read_lines(tmp)

    # May produce a record or not, but must not raise
    assert isinstance(lines, list)


# ---------------------------------------------------------------------------
# 4. Multiple writes → multiple lines
# ---------------------------------------------------------------------------

def test_multiple_pacing_events_written():
    """Multiple log_pacing_applied calls produce multiple JSONL lines."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({"applied": True, "cut_interval_min": 2.0, "cut_interval_max": 4.0})
        tracer.log_pacing_applied({"applied": False, "reason": "user_duration_override"})
        lines = _read_lines(tmp)

    assert len(lines) == 2
    assert all(line["event"] == "ai.pacing_applied" for line in lines)


# ---------------------------------------------------------------------------
# 5. target field is always "segment_selection"
# ---------------------------------------------------------------------------

def test_target_field_is_segment_selection():
    """target field is always 'segment_selection'."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({"applied": True})
        lines = _read_lines(tmp)

    assert lines[0]["target"] == "segment_selection"


# ---------------------------------------------------------------------------
# 6. source_knowledge_ids is always a list
# ---------------------------------------------------------------------------

def test_source_knowledge_ids_always_list():
    """source_knowledge_ids is always a list even if not provided."""
    with tempfile.TemporaryDirectory() as tmp:
        tracer = _make_tracer(tmp)
        tracer.log_pacing_applied({"applied": True})
        lines = _read_lines(tmp)

    assert isinstance(lines[0]["source_knowledge_ids"], list)
