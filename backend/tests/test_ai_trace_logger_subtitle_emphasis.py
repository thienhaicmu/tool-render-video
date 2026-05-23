"""
test_ai_trace_logger_subtitle_emphasis.py — Tests for Phase 5.5 trace logging.

Verifies:
- log_subtitle_emphasis_applied writes JSONL with "ai.subtitle_emphasis_applied"
- payload has applied, emphasis_style, source_knowledge_ids, target, reason
- never raises even with bad path or None config
- writes valid JSON (parseable)
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tracer(tmp_dir: Path):
    from app.ai.tracing import AITraceLogger
    return AITraceLogger("test_job_001", log_dir=tmp_dir)


def _read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# log_subtitle_emphasis_applied — basic event written
# ---------------------------------------------------------------------------

def test_log_subtitle_emphasis_applied_writes_event():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_subtitle_emphasis_applied({
            "applied": True,
            "emphasis_style": "strong",
            "source_knowledge_ids": ["kb_001"],
            "reason": "valid_ai_subtitle_hint",
        })
        log_file = tmp_path / "test_job_001_ai_trace.jsonl"
        assert log_file.exists()
        records = _read_jsonl(log_file)
        assert len(records) == 1
        assert records[0]["event"] == "ai.subtitle_emphasis_applied"


def test_log_subtitle_emphasis_applied_payload_keys():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_subtitle_emphasis_applied({
            "applied": True,
            "emphasis_style": "medium",
            "source_knowledge_ids": ["kb_x"],
            "reason": "valid_ai_subtitle_hint",
        })
        log_file = tmp_path / "test_job_001_ai_trace.jsonl"
        record = _read_jsonl(log_file)[0]
        assert "applied" in record
        assert "emphasis_style" in record
        assert "source_knowledge_ids" in record
        assert "target" in record
        assert "reason" in record


def test_log_subtitle_emphasis_applied_applied_true():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_subtitle_emphasis_applied({
            "applied": True,
            "emphasis_style": "strong",
            "source_knowledge_ids": [],
            "reason": "valid_ai_subtitle_hint",
        })
        record = _read_jsonl(tmp_path / "test_job_001_ai_trace.jsonl")[0]
        assert record["applied"] is True
        assert record["emphasis_style"] == "strong"
        assert record["target"] == "subtitle_emphasis_pass"


def test_log_subtitle_emphasis_applied_applied_false():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_subtitle_emphasis_applied({
            "applied": False,
            "emphasis_style": None,
            "source_knowledge_ids": [],
            "reason": "no_subtitle_emphasis_hint",
        })
        record = _read_jsonl(tmp_path / "test_job_001_ai_trace.jsonl")[0]
        assert record["applied"] is False
        assert record["emphasis_style"] is None
        assert record["reason"] == "no_subtitle_emphasis_hint"


# ---------------------------------------------------------------------------
# source_knowledge_ids in payload
# ---------------------------------------------------------------------------

def test_source_knowledge_ids_in_payload():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_subtitle_emphasis_applied({
            "applied": True,
            "emphasis_style": "subtle",
            "source_knowledge_ids": ["a", "b", "c"],
            "reason": "valid_ai_subtitle_hint",
        })
        record = _read_jsonl(tmp_path / "test_job_001_ai_trace.jsonl")[0]
        assert record["source_knowledge_ids"] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Never raises — bad inputs
# ---------------------------------------------------------------------------

def test_never_raises_with_none_config():
    with tempfile.TemporaryDirectory() as tmp:
        from app.ai.tracing import AITraceLogger
        tracer = AITraceLogger("bad_job", log_dir=Path(tmp))
        # Should not raise
        tracer.log_subtitle_emphasis_applied(None)


def test_never_raises_with_empty_dict():
    with tempfile.TemporaryDirectory() as tmp:
        from app.ai.tracing import AITraceLogger
        tracer = AITraceLogger("bad_job", log_dir=Path(tmp))
        tracer.log_subtitle_emphasis_applied({})


def test_never_raises_with_bad_path():
    from app.ai.tracing import AITraceLogger
    # Use a non-existent directory path; logger must create or silently fail
    tracer = AITraceLogger("job_x", log_dir=Path("/nonexistent/path/xyz_abc_def"))
    # Should not raise — tracing must never crash
    tracer.log_subtitle_emphasis_applied({
        "applied": True,
        "emphasis_style": "strong",
        "source_knowledge_ids": [],
    })


def test_never_raises_with_garbage_config():
    with tempfile.TemporaryDirectory() as tmp:
        from app.ai.tracing import AITraceLogger
        tracer = AITraceLogger("bad_job", log_dir=Path(tmp))
        tracer.log_subtitle_emphasis_applied("not_a_dict")
        tracer.log_subtitle_emphasis_applied(42)
        tracer.log_subtitle_emphasis_applied([1, 2, 3])


# ---------------------------------------------------------------------------
# Valid JSON
# ---------------------------------------------------------------------------

def test_writes_valid_json():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_subtitle_emphasis_applied({
            "applied": True,
            "emphasis_style": "word_only",
            "source_knowledge_ids": ["id_001"],
            "reason": "valid_ai_subtitle_hint",
        })
        log_file = tmp_path / "test_job_001_ai_trace.jsonl"
        raw_lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        for line in raw_lines:
            # Must not raise
            parsed = json.loads(line)
            assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# job_id in every record
# ---------------------------------------------------------------------------

def test_job_id_in_record():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_subtitle_emphasis_applied({
            "applied": True,
            "emphasis_style": "medium",
            "source_knowledge_ids": [],
        })
        record = _read_jsonl(tmp_path / "test_job_001_ai_trace.jsonl")[0]
        assert record["job_id"] == "test_job_001"
        assert "timestamp" in record
