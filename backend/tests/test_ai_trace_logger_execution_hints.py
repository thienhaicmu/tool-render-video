"""
test_ai_trace_logger_execution_hints.py — Tests for Phase 5.3 trace logger additions.

Verifies:
- log_execution_hints writes valid JSONL with ai.execution_hints event
- log_validation_fixup writes valid JSONL with fixups
- log_decision_rejected writes valid JSONL
- All methods never raise even with bad path
- Hint payload contains expected keys
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _read_lines(path: Path) -> list:
    """Read all JSONL lines from file."""
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            lines.append(json.loads(line))
    return lines


# ---------------------------------------------------------------------------
# 1. log_execution_hints
# ---------------------------------------------------------------------------

def test_log_execution_hints_writes_jsonl(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_eh_001", log_dir=tmp_path)
    hints = {
        "cut_interval_min": 2.0,
        "cut_interval_max": 4.0,
        "playback_speed_hint": 1.1,
        "subtitle_emphasis_style": "strong",
        "hook_overlay_enabled": True,
    }
    logger.log_execution_hints(hints, ["item_001", "item_002"])

    log_file = tmp_path / "job_eh_001_ai_trace.jsonl"
    assert log_file.exists()
    lines = _read_lines(log_file)
    assert len(lines) == 1
    record = lines[0]
    assert record["event"] == "ai.execution_hints"
    assert record["job_id"] == "job_eh_001"
    assert "timestamp" in record


def test_log_execution_hints_contains_hints_payload(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_eh_002", log_dir=tmp_path)
    hints = {
        "cut_interval_min": 3.0,
        "cut_interval_max": 6.0,
        "subtitle_emphasis_style": "medium",
    }
    logger.log_execution_hints(hints, ["kb_001"])

    lines = _read_lines(tmp_path / "job_eh_002_ai_trace.jsonl")
    assert len(lines) == 1
    record = lines[0]
    assert "hints" in record
    assert record["hints"]["cut_interval_min"] == 3.0
    assert record["hints"]["subtitle_emphasis_style"] == "medium"
    assert "source_knowledge_ids" in record
    assert "kb_001" in record["source_knowledge_ids"]


def test_log_execution_hints_empty_safe(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_eh_003", log_dir=tmp_path)
    logger.log_execution_hints({}, [])

    lines = _read_lines(tmp_path / "job_eh_003_ai_trace.jsonl")
    assert len(lines) == 1
    assert lines[0]["event"] == "ai.execution_hints"
    assert lines[0]["hints"] == {}
    assert lines[0]["source_knowledge_ids"] == []


def test_log_execution_hints_never_raises_bad_path():
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_bad", log_dir=Path("/nonexistent/really/deep"))
    # Must not raise
    logger.log_execution_hints({"speed": 1.1}, ["x"])


def test_log_execution_hints_never_raises_bad_input():
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_bad2", log_dir=Path("/nonexistent"))
    logger.log_execution_hints(None, None)


# ---------------------------------------------------------------------------
# 2. log_validation_fixup
# ---------------------------------------------------------------------------

def test_log_validation_fixup_writes_jsonl(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_vf_001", log_dir=tmp_path)
    fixups = [
        {"field": "playback_speed_hint", "original": 3.0, "action": "clamped", "result": 1.5},
        {"field": "cut_interval_min", "original": "fast", "action": "invalid_cleared", "result": None},
    ]
    logger.log_validation_fixup(fixups)

    log_file = tmp_path / "job_vf_001_ai_trace.jsonl"
    lines = _read_lines(log_file)
    assert len(lines) == 1
    record = lines[0]
    assert record["event"] == "ai.validation_fixup"
    assert "fixups" in record
    assert len(record["fixups"]) == 2
    assert record["fixups"][0]["field"] == "playback_speed_hint"


def test_log_validation_fixup_empty_list(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_vf_002", log_dir=tmp_path)
    logger.log_validation_fixup([])

    lines = _read_lines(tmp_path / "job_vf_002_ai_trace.jsonl")
    assert lines[0]["fixups"] == []


def test_log_validation_fixup_never_raises_bad_path():
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_vf_bad", log_dir=Path("/nonexistent"))
    logger.log_validation_fixup([{"field": "x"}])


# ---------------------------------------------------------------------------
# 3. log_decision_rejected
# ---------------------------------------------------------------------------

def test_log_decision_rejected_writes_jsonl(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_dr_001", log_dir=tmp_path)
    logger.log_decision_rejected(
        "no_compatible_hook",
        detail={"hint": "hook_overlay_enabled", "reason": "no hook gate found"},
    )

    log_file = tmp_path / "job_dr_001_ai_trace.jsonl"
    lines = _read_lines(log_file)
    assert len(lines) == 1
    record = lines[0]
    assert record["event"] == "ai.decision_rejected"
    assert record["reason"] == "no_compatible_hook"
    assert "detail" in record
    assert "hint" in record["detail"]


def test_log_decision_rejected_without_detail(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_dr_002", log_dir=tmp_path)
    logger.log_decision_rejected("advisory_only")

    lines = _read_lines(tmp_path / "job_dr_002_ai_trace.jsonl")
    assert lines[0]["reason"] == "advisory_only"


def test_log_decision_rejected_never_raises_bad_path():
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_dr_bad", log_dir=Path("/nonexistent"))
    logger.log_decision_rejected("test_reason", detail={"x": 1})


def test_log_decision_rejected_never_raises_bad_input():
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_dr_bad2", log_dir=Path("/nonexistent"))
    logger.log_decision_rejected(None, detail=None)


# ---------------------------------------------------------------------------
# 4. All three methods in sequence
# ---------------------------------------------------------------------------

def test_all_three_methods_write_separate_lines(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_all", log_dir=tmp_path)
    logger.log_execution_hints({"cut_interval_min": 2.0}, ["k1"])
    logger.log_validation_fixup([{"field": "speed", "original": 3.0, "action": "clamped", "result": 1.5}])
    logger.log_decision_rejected("pacing_hint_advisory_only", detail={"reason": "no compatible hook"})

    lines = _read_lines(tmp_path / "job_all_ai_trace.jsonl")
    assert len(lines) == 3
    events = {l["event"] for l in lines}
    assert "ai.execution_hints" in events
    assert "ai.validation_fixup" in events
    assert "ai.decision_rejected" in events
