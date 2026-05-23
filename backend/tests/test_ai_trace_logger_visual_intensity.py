"""
test_ai_trace_logger_visual_intensity.py — Tests for Phase 5.6 trace logging.

Verifies:
- log_visual_intensity_applied writes JSONL with "ai.visual_intensity_applied"
- payload has applied, visual_intensity, source_knowledge_ids, render_overrides, reason
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
    return AITraceLogger("test_job_vis_001", log_dir=tmp_dir)


def _read_jsonl(path: Path) -> list[dict]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# log_visual_intensity_applied — basic event written
# ---------------------------------------------------------------------------

def test_log_visual_intensity_applied_writes_event():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": "high",
            "source_knowledge_ids": ["kb_001"],
            "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })
        log_file = tmp_path / "test_job_vis_001_ai_trace.jsonl"
        assert log_file.exists()
        records = _read_jsonl(log_file)
        assert len(records) == 1
        assert records[0]["event"] == "ai.visual_intensity_applied"


def test_log_visual_intensity_applied_payload_keys():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": "medium",
            "source_knowledge_ids": ["kb_x"],
            "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })
        log_file = tmp_path / "test_job_vis_001_ai_trace.jsonl"
        record = _read_jsonl(log_file)[0]
        assert "applied" in record
        assert "visual_intensity" in record
        assert "source_knowledge_ids" in record
        assert "render_overrides" in record
        assert "reason" in record


def test_log_visual_intensity_applied_values_correct():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": "high",
            "source_knowledge_ids": ["kb_a", "kb_b"],
            "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })
        record = _read_jsonl(tmp_path / "test_job_vis_001_ai_trace.jsonl")[0]
        assert record["applied"] is False
        assert record["visual_intensity"] == "high"
        assert record["source_knowledge_ids"] == ["kb_a", "kb_b"]
        assert record["render_overrides"] == {}
        assert record["reason"] == "no_safe_visual_injection_point"


def test_log_visual_intensity_applied_false_no_injection():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": None,
            "source_knowledge_ids": [],
            "render_overrides": {},
            "reason": "no_visual_intensity_hint",
        })
        record = _read_jsonl(tmp_path / "test_job_vis_001_ai_trace.jsonl")[0]
        assert record["applied"] is False
        assert record["visual_intensity"] is None
        assert record["reason"] == "no_visual_intensity_hint"


def test_log_visual_intensity_rejected_invalid():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": None,
            "source_knowledge_ids": [],
            "render_overrides": {},
            "reason": "invalid_visual_intensity",
        })
        record = _read_jsonl(tmp_path / "test_job_vis_001_ai_trace.jsonl")[0]
        assert record["applied"] is False
        assert record["reason"] == "invalid_visual_intensity"


# ---------------------------------------------------------------------------
# source_knowledge_ids in payload
# ---------------------------------------------------------------------------

def test_source_knowledge_ids_in_payload():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": "low",
            "source_knowledge_ids": ["a", "b", "c"],
            "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })
        record = _read_jsonl(tmp_path / "test_job_vis_001_ai_trace.jsonl")[0]
        assert record["source_knowledge_ids"] == ["a", "b", "c"]


def test_render_overrides_in_payload():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": "medium",
            "source_knowledge_ids": [],
            "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })
        record = _read_jsonl(tmp_path / "test_job_vis_001_ai_trace.jsonl")[0]
        assert isinstance(record["render_overrides"], dict)


# ---------------------------------------------------------------------------
# Never raises — bad inputs
# ---------------------------------------------------------------------------

def test_never_raises_with_none_config():
    with tempfile.TemporaryDirectory() as tmp:
        from app.ai.tracing import AITraceLogger
        tracer = AITraceLogger("bad_job", log_dir=Path(tmp))
        # Should not raise
        tracer.log_visual_intensity_applied(None)


def test_never_raises_with_empty_dict():
    with tempfile.TemporaryDirectory() as tmp:
        from app.ai.tracing import AITraceLogger
        tracer = AITraceLogger("bad_job", log_dir=Path(tmp))
        tracer.log_visual_intensity_applied({})


def test_never_raises_with_bad_path():
    from app.ai.tracing import AITraceLogger
    # Use a non-existent directory path; logger must create or silently fail
    tracer = AITraceLogger("job_x", log_dir=Path("/nonexistent/path/xyz_abc_visual_def"))
    # Should not raise — tracing must never crash
    tracer.log_visual_intensity_applied({
        "applied": False,
        "visual_intensity": "high",
        "source_knowledge_ids": [],
        "render_overrides": {},
        "reason": "no_safe_visual_injection_point",
    })


def test_never_raises_with_garbage_config():
    with tempfile.TemporaryDirectory() as tmp:
        from app.ai.tracing import AITraceLogger
        tracer = AITraceLogger("bad_job", log_dir=Path(tmp))
        tracer.log_visual_intensity_applied("not_a_dict")
        tracer.log_visual_intensity_applied(42)
        tracer.log_visual_intensity_applied([1, 2, 3])


# ---------------------------------------------------------------------------
# Valid JSON
# ---------------------------------------------------------------------------

def test_writes_valid_json():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": "low",
            "source_knowledge_ids": ["id_001"],
            "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })
        log_file = tmp_path / "test_job_vis_001_ai_trace.jsonl"
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
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": "medium",
            "source_knowledge_ids": [],
            "render_overrides": {},
        })
        record = _read_jsonl(tmp_path / "test_job_vis_001_ai_trace.jsonl")[0]
        assert record["job_id"] == "test_job_vis_001"
        assert "timestamp" in record


# ---------------------------------------------------------------------------
# Multiple events
# ---------------------------------------------------------------------------

def test_multiple_events_appended():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tracer = _make_tracer(tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False, "visual_intensity": "low",
            "source_knowledge_ids": [], "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })
        tracer.log_visual_intensity_applied({
            "applied": False, "visual_intensity": "high",
            "source_knowledge_ids": [], "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })
        log_file = tmp_path / "test_job_vis_001_ai_trace.jsonl"
        records = _read_jsonl(log_file)
        assert len(records) == 2
        assert all(r["event"] == "ai.visual_intensity_applied" for r in records)
