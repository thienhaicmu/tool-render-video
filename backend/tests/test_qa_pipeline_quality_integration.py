"""Tests for quality intelligence integration with qa_pipeline.

Verifies that _assess_render_quality_intelligence is non-blocking and
does not affect existing _validate_render_output results.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.orchestration.qa_pipeline import (
    _assess_render_quality_intelligence,
    _validate_render_output,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _probe_ok(path: str, timeout: int = 15) -> dict:
    """Mock probe result for a valid video."""
    return {
        "has_video": True,
        "has_audio": True,
        "duration": 30.0,
        "fps": 30.0,
        "width": 1080,
        "height": 1920,
    }


# ---------------------------------------------------------------------------
# _assess_render_quality_intelligence tests
# ---------------------------------------------------------------------------

class TestQualityIntelligenceIntegration:
    def test_quality_intelligence_does_not_affect_qa_success(self, tmp_path):
        """Quality intelligence result is separate from _validate_render_output ok/error."""
        # We can call _validate_render_output with a missing file — it returns ok=False
        # regardless of what quality intelligence does.
        video = tmp_path / "missing.mp4"
        qa_result = _validate_render_output(video)
        assert qa_result["ok"] is False
        # Now call quality intelligence on the same missing file — should not raise
        qi_result = _assess_render_quality_intelligence(
            video_path=video, part_no=1, job_id="test_job"
        )
        # QI returns a dict or None — either is fine
        assert qi_result is None or isinstance(qi_result, dict)
        # validate result unchanged
        assert qa_result["ok"] is False

    def test_quality_report_json_written_to_sidecar(self, tmp_path):
        """When video exists, a sidecar quality JSON is written."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 1000)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _probe_ok(str(video))
            qi_result = _assess_render_quality_intelligence(
                video_path=video,
                part_no=1,
                job_id="myjob",
            )
        assert qi_result is not None
        sidecar = tmp_path / "quality" / "myjob_part_1.json"
        assert sidecar.exists()
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert "score" in data
        assert "issues" in data

    def test_warnings_do_not_make_qi_return_false(self, tmp_path):
        """Quality intelligence with warnings returns a report dict, not None."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 1000)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = {
                "has_video": True,
                "has_audio": False,  # will produce a warning
                "duration": 2.0,
                "fps": 30.0,
                "width": 1080,
                "height": 1920,
            }
            qi_result = _assess_render_quality_intelligence(
                video_path=video,
                part_no=1,
                job_id="myjob",
            )
        assert qi_result is not None
        # Score may be reduced but report still returned
        assert "score" in qi_result
        assert isinstance(qi_result["issues"], list)

    def test_missing_video_qa_returns_ok_false_unchanged(self, tmp_path):
        """Missing video → _validate_render_output returns ok=False (unchanged by QI)."""
        video = tmp_path / "missing.mp4"
        qa_result = _validate_render_output(video)
        assert qa_result["ok"] is False
        assert qa_result["error"] is not None

    def test_quality_intelligence_failure_does_not_propagate(self, tmp_path):
        """Even if quality assessment raises internally, _assess_render_quality_intelligence returns None."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 1000)
        with patch("app.quality.assessor.assess_rendered_part_quality",
                   side_effect=RuntimeError("boom")):
            result = _assess_render_quality_intelligence(
                video_path=video, part_no=1, job_id="job1"
            )
        assert result is None

    def test_quality_report_json_structure(self, tmp_path):
        """Sidecar JSON contains expected top-level keys."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 1000)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _probe_ok(str(video))
            _assess_render_quality_intelligence(
                video_path=video, part_no=2, job_id="jobX"
            )
        sidecar = tmp_path / "quality" / "jobX_part_2.json"
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        for key in ("score", "issues", "metrics", "ai_trace_refs", "created_at"):
            assert key in data, f"Missing key: {key}"

    def test_no_job_id_no_part_no_does_not_crash(self, tmp_path):
        """Calling without job_id/part_no uses fallback path and does not raise."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 1000)
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _probe_ok(str(video))
            result = _assess_render_quality_intelligence(video_path=video)
        assert result is None or isinstance(result, dict)

    def test_sidecar_path_pattern(self, tmp_path):
        """Sidecar file follows <job_id>_part_<part_no>.json naming."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 1000)
        job_id = "abc123"
        part_no = 5
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _probe_ok(str(video))
            _assess_render_quality_intelligence(
                video_path=video, part_no=part_no, job_id=job_id
            )
        expected = tmp_path / "quality" / f"{job_id}_part_{part_no}.json"
        assert expected.exists()
