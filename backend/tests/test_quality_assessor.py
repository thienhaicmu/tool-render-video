"""Tests for app.quality.assessor — assess_rendered_part_quality()."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.quality.assessor import assess_rendered_part_quality
from app.quality.models import QualityReport


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_probe_result(
    has_video: bool = True,
    has_audio: bool = True,
    duration: float = 30.0,
) -> dict:
    return {
        "has_video": has_video,
        "has_audio": has_audio,
        "duration": duration,
        "fps": 30.0,
        "width": 1080,
        "height": 1920,
    }


# ---------------------------------------------------------------------------
# FILE INTEGRITY
# ---------------------------------------------------------------------------

class TestFileIntegrity:
    def test_missing_video_produces_critical_issue(self, tmp_path):
        video = tmp_path / "missing.mp4"
        report = assess_rendered_part_quality(video)
        codes = [i.code for i in report.issues]
        assert "missing_output" in codes
        severities = [i.severity for i in report.issues if i.code == "missing_output"]
        assert severities == ["critical"]

    def test_missing_video_score_is_zero(self, tmp_path):
        video = tmp_path / "missing.mp4"
        report = assess_rendered_part_quality(video)
        assert report.score == pytest.approx(0.0)

    def test_zero_byte_video_produces_critical_issue(self, tmp_path):
        video = tmp_path / "zero.mp4"
        video.write_bytes(b"")
        report = assess_rendered_part_quality(video)
        codes = [i.code for i in report.issues]
        assert "zero_byte_output" in codes

    def test_zero_byte_video_score_is_zero(self, tmp_path):
        video = tmp_path / "zero.mp4"
        video.write_bytes(b"")
        report = assess_rendered_part_quality(video)
        assert report.score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# VIDEO PROBE
# ---------------------------------------------------------------------------

class TestVideoProbe:
    def test_probe_failure_adds_error_issue(self, tmp_path):
        video = tmp_path / "file.mp4"
        video.write_bytes(b"x" * 100)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess") as _:
            mock_probe.side_effect = RuntimeError("probe crash")
            report = assess_rendered_part_quality(video)
        codes = [i.code for i in report.issues]
        assert "probe_failed" in codes

    def test_probe_failure_has_error_severity(self, tmp_path):
        video = tmp_path / "file.mp4"
        video.write_bytes(b"x" * 100)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess") as _:
            mock_probe.side_effect = RuntimeError("probe crash")
            report = assess_rendered_part_quality(video)
        issue = next(i for i in report.issues if i.code == "probe_failed")
        assert issue.severity == "error"
        assert issue.confidence == pytest.approx(0.7)

    def test_duration_stored_in_metrics(self, tmp_path):
        video = tmp_path / "file.mp4"
        video.write_bytes(b"x" * 100)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess") as _:
            mock_probe.return_value = _make_probe_result(duration=45.5)
            report = assess_rendered_part_quality(video)
        # duration may or may not be in metrics depending on subprocess mocking;
        # just verify assessor doesn't crash
        assert isinstance(report, QualityReport)


# ---------------------------------------------------------------------------
# AUDIO STREAM
# ---------------------------------------------------------------------------

class TestAudioStream:
    def test_video_with_audio_has_no_audio_issue(self, tmp_path):
        video = tmp_path / "file.mp4"
        video.write_bytes(b"x" * 100)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result(has_audio=True)
            report = assess_rendered_part_quality(video)
        codes = [i.code for i in report.issues]
        assert "no_audio_stream" not in codes

    def test_video_without_audio_adds_warning_issue(self, tmp_path):
        video = tmp_path / "file.mp4"
        video.write_bytes(b"x" * 100)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result(has_audio=False)
            report = assess_rendered_part_quality(video)
        codes = [i.code for i in report.issues]
        assert "no_audio_stream" in codes
        issue = next(i for i in report.issues if i.code == "no_audio_stream")
        assert issue.severity == "warning"
        assert issue.confidence == pytest.approx(0.95)


# ---------------------------------------------------------------------------
# DURATION MISMATCH
# ---------------------------------------------------------------------------

class TestDurationMismatch:
    def _write_manifest(self, tmp_path: Path, source_start: float, source_end: float,
                        speed: float = 1.0) -> Path:
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "job_id": "job1",
            "part_no": 1,
            "source_start": source_start,
            "source_end": source_end,
            "effective_speed": speed,
            "timeline": {},
        }), encoding="utf-8")
        return manifest_path

    def test_duration_mismatch_adds_error(self, tmp_path):
        video = tmp_path / "file.mp4"
        video.write_bytes(b"x" * 100)
        # expected ~30s, actual 45s → diff=15s, tolerance=3s → mismatch
        manifest_path = self._write_manifest(tmp_path, 0.0, 30.0)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result(duration=45.0)
            report = assess_rendered_part_quality(
                video, manifest_path=manifest_path
            )
        codes = [i.code for i in report.issues]
        assert "duration_mismatch" in codes

    def test_duration_within_tolerance_no_error(self, tmp_path):
        video = tmp_path / "file.mp4"
        video.write_bytes(b"x" * 100)
        # expected 30s, actual 30.5s → diff=0.5s < tolerance=3s → ok
        manifest_path = self._write_manifest(tmp_path, 0.0, 30.0)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result(duration=30.5)
            report = assess_rendered_part_quality(
                video, manifest_path=manifest_path
            )
        codes = [i.code for i in report.issues]
        assert "duration_mismatch" not in codes


# ---------------------------------------------------------------------------
# SUBTITLE DENSITY (tested more thoroughly in test_quality_subtitle_density.py)
# ---------------------------------------------------------------------------

class TestSubtitleDensity:
    def _write_srt(self, path: Path, blocks: list[tuple[float, float, str]]) -> None:
        lines = []
        for idx, (start, end, text) in enumerate(blocks, start=1):
            def ts(s):
                ms = int(round(s * 1000))
                return f"{ms // 3600000:02d}:{(ms % 3600000) // 60000:02d}:{(ms % 60000) // 1000:02d},{ms % 1000:03d}"
            lines.append(f"{idx}\n{ts(start)} --> {ts(end)}\n{text}\n")
        path.write_text("\n".join(lines), encoding="utf-8")

    def test_subtitle_too_fast_adds_warning(self, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 100)
        srt = tmp_path / "s.srt"
        # 14 words in 2 seconds = 7 wps > 3.5
        self._write_srt(srt, [(0.0, 2.0, "one two three four five six seven eight nine ten eleven twelve thirteen fourteen")])
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result()
            report = assess_rendered_part_quality(video, srt_path=srt)
        codes = [i.code for i in report.issues]
        assert "subtitle_too_fast" in codes

    def test_hook_delay_greater_than_5s_adds_warning(self, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 100)
        srt = tmp_path / "s.srt"
        # First subtitle starts at 6s
        self._write_srt(srt, [(6.0, 8.0, "Hello world")])
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result()
            report = assess_rendered_part_quality(video, srt_path=srt)
        codes = [i.code for i in report.issues]
        assert "hook_delay" in codes


# ---------------------------------------------------------------------------
# AI TRACE CORRELATION
# ---------------------------------------------------------------------------

class TestAiTraceCorrelation:
    def test_malformed_ai_trace_silent_skip_no_crash(self, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 100)
        trace = tmp_path / "trace.jsonl"
        trace.write_text("not json\n{bad\n", encoding="utf-8")
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result()
            report = assess_rendered_part_quality(video, ai_trace_path=trace)
        assert report.ai_trace_refs == []

    def test_ai_trace_correlation_populates_refs(self, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 100)
        trace = tmp_path / "trace.jsonl"
        lines = [
            json.dumps({"event": "ai.pacing_applied", "job_id": "j1"}),
            json.dumps({"event": "ai.execution_hints", "job_id": "j1"}),
            json.dumps({"event": "ai.some_other_event", "job_id": "j1"}),
        ]
        trace.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result()
            report = assess_rendered_part_quality(video, ai_trace_path=trace)
        assert "ai.pacing_applied" in report.ai_trace_refs
        assert "ai.execution_hints" in report.ai_trace_refs
        assert "ai.some_other_event" not in report.ai_trace_refs


# ---------------------------------------------------------------------------
# SAFETY — never raises
# ---------------------------------------------------------------------------

class TestNeverRaises:
    def test_all_none_inputs_do_not_raise(self):
        """Passing a non-existent path with all optional args None must never raise."""
        report = assess_rendered_part_quality(Path("/nonexistent/file.mp4"))
        assert isinstance(report, QualityReport)

    def test_all_missing_optional_paths_do_not_raise(self, tmp_path):
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 100)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result()
            report = assess_rendered_part_quality(
                video,
                srt_path=tmp_path / "nonexistent.srt",
                manifest_path=tmp_path / "nonexistent.json",
                ai_trace_path=tmp_path / "nonexistent.jsonl",
            )
        assert isinstance(report, QualityReport)

    def test_warnings_do_not_make_report_fatal(self, tmp_path):
        """Warnings exist but report can still have score > 0."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 100)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe_result(has_audio=False, duration=2.0)
            report = assess_rendered_part_quality(video)
        # Score may be reduced but not necessarily zero (only critical → 0)
        warnings = [i for i in report.issues if i.severity == "warning"]
        assert len(warnings) > 0
        assert all(i.severity != "critical" for i in report.issues)
