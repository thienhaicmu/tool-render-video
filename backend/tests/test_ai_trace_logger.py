"""
test_ai_trace_logger.py — Tests for AITraceLogger.

Verifies JSONL output format, event types, ID-only logging for knowledge,
and robustness against bad paths.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _read_lines(path: Path) -> list:
    """Read all JSONL lines from a file."""
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            lines.append(json.loads(line))
    return lines


# ---------------------------------------------------------------------------
# 1. Logger writes valid JSONL lines
# ---------------------------------------------------------------------------

def test_writes_valid_jsonl(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_test_001", log_dir=tmp_path)
    logger.log_input_filters({"platform": "tiktok", "style": "viral"})

    log_file = tmp_path / "job_test_001_ai_trace.jsonl"
    assert log_file.exists()
    lines = _read_lines(log_file)
    assert len(lines) == 1
    assert lines[0]["job_id"] == "job_test_001"
    assert lines[0]["event"] == "ai.input_filters"


# ---------------------------------------------------------------------------
# 2. Logger never raises even with bad log path
# ---------------------------------------------------------------------------

def test_never_raises_with_bad_path():
    from app.ai.tracing import AITraceLogger

    # Use a path that is completely non-writable on Windows by pointing into a file
    # (not a directory), or just rely on the logger catching the exception
    logger = AITraceLogger("job_abc", log_dir=Path("/nonexistent/really/deep/path"))
    # Must not raise
    logger.log_input_filters({"platform": "tiktok"})
    logger.log_fallback("no_index")
    logger.log_render_plan_summary({"mode": "viral"})


def test_never_raises_with_none_log_dir():
    """Uses default log_dir — must not crash even if that dir can't be created."""
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("test_job_99")
    # Must not raise
    logger.log_input_filters({})


# ---------------------------------------------------------------------------
# 3. Event JSONL has job_id, event, timestamp
# ---------------------------------------------------------------------------

def test_event_has_required_fields(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_field_check", log_dir=tmp_path)
    logger.log_input_filters({"platform": "tiktok"})

    lines = _read_lines(tmp_path / "job_field_check_ai_trace.jsonl")
    assert len(lines) == 1
    record = lines[0]
    assert "job_id" in record
    assert "event" in record
    assert "timestamp" in record
    assert record["job_id"] == "job_field_check"
    # Timestamp should be ISO 8601 format
    ts = record["timestamp"]
    assert "T" in ts or "t" in ts


# ---------------------------------------------------------------------------
# 4. log_knowledge_retrieved logs IDs (not full rule text)
# ---------------------------------------------------------------------------

def test_knowledge_retrieved_logs_ids_not_rule(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_kr_test", log_dir=tmp_path)
    results = [
        {
            "id": "tiktok_hook_001",
            "type": "hook_pattern",
            "rule": "This is a very long rule text that should NOT appear in the log.",
            "weight": 0.9,
            "match_score": 0.8,
            "match_reason": ["platform:tiktok"],
        },
        {
            "id": "pacing_001",
            "type": "pacing_rule",
            "rule": "Another long rule text.",
            "weight": 0.7,
            "match_score": 0.6,
            "match_reason": ["style:viral"],
        },
    ]
    logger.log_knowledge_retrieved(results)

    lines = _read_lines(tmp_path / "job_kr_test_ai_trace.jsonl")
    assert len(lines) == 1
    record = lines[0]
    assert record["event"] == "ai.knowledge_retrieved"

    # IDs must be present
    candidates = record["candidates"]
    ids = [c["id"] for c in candidates]
    assert "tiktok_hook_001" in ids
    assert "pacing_001" in ids

    # Rule text must NOT be present
    raw_text = json.dumps(record)
    assert "very long rule text" not in raw_text
    assert "Another long rule text" not in raw_text


def test_knowledge_retrieved_empty_list(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_empty", log_dir=tmp_path)
    logger.log_knowledge_retrieved([])

    lines = _read_lines(tmp_path / "job_empty_ai_trace.jsonl")
    assert len(lines) == 1
    assert lines[0]["candidates"] == []
    assert lines[0]["total_candidates"] == 0


# ---------------------------------------------------------------------------
# 5. log_fallback writes reason
# ---------------------------------------------------------------------------

def test_log_fallback_writes_reason(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_fallback", log_dir=tmp_path)
    logger.log_fallback("no_knowledge_files", detail="knowledge/processed/ is empty")

    lines = _read_lines(tmp_path / "job_fallback_ai_trace.jsonl")
    assert len(lines) == 1
    record = lines[0]
    assert record["event"] == "ai.fallback"
    assert record["reason"] == "no_knowledge_files"
    assert "detail" in record
    assert "empty" in record["detail"]


def test_log_fallback_without_detail(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_fb2", log_dir=tmp_path)
    logger.log_fallback("no_matching_rules")

    lines = _read_lines(tmp_path / "job_fb2_ai_trace.jsonl")
    assert lines[0]["reason"] == "no_matching_rules"


# ---------------------------------------------------------------------------
# 6. Log dir is created if missing
# ---------------------------------------------------------------------------

def test_log_dir_created_if_missing(tmp_path):
    from app.ai.tracing import AITraceLogger

    new_dir = tmp_path / "new" / "deep" / "dir"
    assert not new_dir.exists()

    logger = AITraceLogger("job_newdir", log_dir=new_dir)
    logger.log_input_filters({"platform": "tiktok"})

    assert new_dir.exists()
    assert (new_dir / "job_newdir_ai_trace.jsonl").exists()


# ---------------------------------------------------------------------------
# 7. Multiple events write multiple lines
# ---------------------------------------------------------------------------

def test_multiple_events_multiple_lines(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_multi", log_dir=tmp_path)
    logger.log_input_filters({"platform": "tiktok"})
    logger.log_knowledge_retrieved([])
    logger.log_fallback("no_matching_rules")
    logger.log_render_plan_summary({"mode": "viral", "segments": 3})

    lines = _read_lines(tmp_path / "job_multi_ai_trace.jsonl")
    assert len(lines) == 4
    events = [l["event"] for l in lines]
    assert "ai.input_filters" in events
    assert "ai.knowledge_retrieved" in events
    assert "ai.fallback" in events
    assert "ai.render_plan_summary" in events


# ---------------------------------------------------------------------------
# 8. log_rules_selected
# ---------------------------------------------------------------------------

def test_log_rules_selected(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_rules", log_dir=tmp_path)
    rules = [
        {"id": "hook_001", "type": "hook_pattern", "reason": "highest weight"},
        {"id": "pacing_001", "type": "pacing_rule", "reason": "best match"},
    ]
    logger.log_rules_selected(rules)

    lines = _read_lines(tmp_path / "job_rules_ai_trace.jsonl")
    assert len(lines) == 1
    assert lines[0]["event"] == "ai.rules_selected"
    selected = lines[0]["selected"]
    assert len(selected) == 2
    assert selected[0]["id"] == "hook_001"


# ---------------------------------------------------------------------------
# 9. log_render_plan_summary
# ---------------------------------------------------------------------------

def test_log_render_plan_summary(tmp_path):
    from app.ai.tracing import AITraceLogger

    logger = AITraceLogger("job_plan", log_dir=tmp_path)
    summary = {
        "mode": "viral_tiktok",
        "segments": 5,
        "fallback_used": False,
        "knowledge_items_used": 3,
    }
    logger.log_render_plan_summary(summary)

    lines = _read_lines(tmp_path / "job_plan_ai_trace.jsonl")
    assert len(lines) == 1
    record = lines[0]
    assert record["event"] == "ai.render_plan_summary"
    assert record["plan"]["mode"] == "viral_tiktok"
    assert record["plan"]["segments"] == 5
