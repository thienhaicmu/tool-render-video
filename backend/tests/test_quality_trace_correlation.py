"""Tests for AI trace correlation in quality assessor."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.quality.assessor import assess_rendered_part_quality, _AI_TRACE_RELEVANT_EVENTS
from app.quality.models import QualityReport


def _make_probe():
    return {
        "has_video": True,
        "has_audio": True,
        "duration": 30.0,
        "fps": 30.0,
        "width": 1080,
        "height": 1920,
    }


def _assess(tmp_path: Path, trace_path: Path | None = None) -> QualityReport:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
         patch("app.quality.assessor.subprocess"):
        mock_probe.return_value = _make_probe()
        return assess_rendered_part_quality(video, ai_trace_path=trace_path)


class TestAiTraceCorrelation:
    def test_valid_jsonl_with_known_events_populates_refs(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        lines = [
            json.dumps({"event": "ai.pacing_applied", "job_id": "j1"}),
            json.dumps({"event": "ai.execution_hints", "job_id": "j1"}),
            json.dumps({"event": "ai.validation_fixup", "job_id": "j1"}),
        ]
        trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = _assess(tmp_path, trace)
        assert "ai.pacing_applied" in report.ai_trace_refs
        assert "ai.execution_hints" in report.ai_trace_refs
        assert "ai.validation_fixup" in report.ai_trace_refs

    def test_unrelated_events_ignored(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        lines = [
            json.dumps({"event": "ai.knowledge_retrieved", "job_id": "j1"}),
            json.dumps({"event": "ai.input_filters", "job_id": "j1"}),
            json.dumps({"event": "ai.rules_selected", "job_id": "j1"}),
            json.dumps({"event": "ai.render_plan_summary", "job_id": "j1"}),
            json.dumps({"event": "ai.fallback", "job_id": "j1"}),
        ]
        trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = _assess(tmp_path, trace)
        assert report.ai_trace_refs == []

    def test_file_not_found_ai_trace_refs_empty_no_crash(self, tmp_path):
        trace = tmp_path / "nonexistent.jsonl"
        report = _assess(tmp_path, trace)
        assert report.ai_trace_refs == []

    def test_none_ai_trace_path_ai_trace_refs_empty(self, tmp_path):
        report = _assess(tmp_path, trace_path=None)
        assert report.ai_trace_refs == []

    def test_malformed_jsonl_lines_skipped_continue(self, tmp_path):
        trace = tmp_path / "trace.jsonl"
        trace.write_text(
            "not json\n"
            + json.dumps({"event": "ai.pacing_applied"}) + "\n"
            + "{ bad json }\n"
            + json.dumps({"event": "ai.decision_rejected"}) + "\n",
            encoding="utf-8",
        )
        report = _assess(tmp_path, trace)
        assert "ai.pacing_applied" in report.ai_trace_refs
        assert "ai.decision_rejected" in report.ai_trace_refs

    def test_empty_file_ai_trace_refs_empty_no_crash(self, tmp_path):
        trace = tmp_path / "empty.jsonl"
        trace.write_text("", encoding="utf-8")
        report = _assess(tmp_path, trace)
        assert report.ai_trace_refs == []

    def test_mixed_valid_invalid_lines_only_valid_collected(self, tmp_path):
        trace = tmp_path / "mixed.jsonl"
        trace.write_text(
            "GARBAGE LINE\n"
            + json.dumps({"event": "ai.subtitle_emphasis_applied"}) + "\n"
            + "{ incomplete\n"
            + json.dumps({"event": "ai.visual_intensity_applied"}) + "\n"
            + "\n"  # blank line
            + json.dumps({"no_event_key": True}) + "\n",
            encoding="utf-8",
        )
        report = _assess(tmp_path, trace)
        assert "ai.subtitle_emphasis_applied" in report.ai_trace_refs
        assert "ai.visual_intensity_applied" in report.ai_trace_refs
        # no duplicates, no unrelated items
        assert len(report.ai_trace_refs) == 2

    def test_missing_events_filtered_correctly(self, tmp_path):
        """Events that lack the 'event' key are filtered out."""
        trace = tmp_path / "trace.jsonl"
        lines = [
            json.dumps({"message": "no event key", "job_id": "j1"}),
            json.dumps({"event": "ai.pacing_applied", "job_id": "j1"}),
            json.dumps({"event": None}),  # None event
        ]
        trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = _assess(tmp_path, trace)
        assert "ai.pacing_applied" in report.ai_trace_refs
        assert len(report.ai_trace_refs) == 1

    def test_all_relevant_events_collected(self, tmp_path):
        """All events from _AI_TRACE_RELEVANT_EVENTS are collected when present."""
        trace = tmp_path / "trace.jsonl"
        lines = [
            json.dumps({"event": evt}) for evt in sorted(_AI_TRACE_RELEVANT_EVENTS)
        ]
        trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = _assess(tmp_path, trace)
        for evt in _AI_TRACE_RELEVANT_EVENTS:
            assert evt in report.ai_trace_refs

    def test_duplicate_events_not_repeated(self, tmp_path):
        """The same event appearing multiple times is only added once."""
        trace = tmp_path / "trace.jsonl"
        lines = [
            json.dumps({"event": "ai.pacing_applied"}),
            json.dumps({"event": "ai.pacing_applied"}),
            json.dumps({"event": "ai.pacing_applied"}),
        ]
        trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = _assess(tmp_path, trace)
        assert report.ai_trace_refs.count("ai.pacing_applied") == 1
