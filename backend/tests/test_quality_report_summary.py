"""Tests for app.quality.report_summary — build_job_quality_summary()."""
import json
import pytest
from pathlib import Path

from app.quality.report_summary import build_job_quality_summary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(score, issues=None):
    return {
        "job_id": "job1",
        "part_no": 1,
        "score": score,
        "issues": issues or [],
        "metrics": {},
        "ai_trace_refs": [],
        "created_at": "2026-01-01T00:00:00",
    }


def _write_report(quality_dir, job_id, part_no, data):
    path = quality_dir / f"{job_id}_part_{part_no}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _video_path(tmp_path, name="part1.mp4"):
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    vp = output_dir / name
    vp.write_bytes(b"\x00" * 16)
    return vp


def _quality_dir(video_path):
    qdir = video_path.parent / "quality"
    qdir.mkdir(parents=True, exist_ok=True)
    return qdir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildJobQualitySummary:

    def test_empty_parts_list_returns_valid_summary(self):
        result = build_job_quality_summary("job1", [])
        assert result["job_id"] == "job1"
        assert result["parts"] == []
        assert result["summary"]["total_parts"] == 0
        assert result["summary"]["available_parts"] == 0
        assert result["summary"]["average_score"] is None

    def test_all_reports_available_correct_summary(self, tmp_path):
        vp1 = _video_path(tmp_path, "part1.mp4")
        vp2 = _video_path(tmp_path, "part2.mp4")
        qd1 = _quality_dir(vp1)
        qd2 = _quality_dir(vp2)

        issues1 = [
            {"code": "x", "severity": "error", "message": "e", "confidence": 0.9},
            {"code": "y", "severity": "warning", "message": "w", "confidence": 0.8},
        ]
        issues2 = [
            {"code": "z", "severity": "warning", "message": "w2", "confidence": 0.7},
        ]

        _write_report(qd1, "job1", 1, _make_report(90.0, issues1))
        _write_report(qd2, "job1", 2, _make_report(80.0, issues2))

        parts_info = [
            {"part_no": 1, "video_path": str(vp1)},
            {"part_no": 2, "video_path": str(vp2)},
        ]

        result = build_job_quality_summary("job1", parts_info)

        assert result["summary"]["total_parts"] == 2
        assert result["summary"]["available_parts"] == 2
        assert result["summary"]["average_score"] == 85.0
        assert result["summary"]["error_count"] == 1
        assert result["summary"]["warning_count"] == 2
        assert result["summary"]["critical_count"] == 0
        assert result["summary"]["info_count"] == 0

        part1 = next(p for p in result["parts"] if p["part_no"] == 1)
        assert part1["available"] is True
        assert part1["score"] == 90.0
        assert part1["error_count"] == 1
        assert part1["warning_count"] == 1

    def test_mix_available_and_missing_correct_counts(self, tmp_path):
        vp1 = _video_path(tmp_path, "part1.mp4")
        vp2 = _video_path(tmp_path, "part2.mp4")
        qd1 = _quality_dir(vp1)
        # no report for part2

        _write_report(qd1, "job1", 1, _make_report(70.0, []))

        parts_info = [
            {"part_no": 1, "video_path": str(vp1)},
            {"part_no": 2, "video_path": str(vp2)},
        ]

        result = build_job_quality_summary("job1", parts_info)

        assert result["summary"]["total_parts"] == 2
        assert result["summary"]["available_parts"] == 1
        assert result["summary"]["average_score"] == 70.0

        part2 = next(p for p in result["parts"] if p["part_no"] == 2)
        assert part2["available"] is False
        assert part2["score"] is None

    def test_average_score_computed_from_available_only(self, tmp_path):
        vp1 = _video_path(tmp_path, "part1.mp4")
        vp2 = _video_path(tmp_path, "part2.mp4")
        vp3 = _video_path(tmp_path, "part3.mp4")
        qd1 = _quality_dir(vp1)
        qd3 = _quality_dir(vp3)

        _write_report(qd1, "job1", 1, _make_report(60.0, []))
        # part2 has no report
        _write_report(qd3, "job1", 3, _make_report(80.0, []))

        parts_info = [
            {"part_no": 1, "video_path": str(vp1)},
            {"part_no": 2, "video_path": str(vp2)},
            {"part_no": 3, "video_path": str(vp3)},
        ]

        result = build_job_quality_summary("job1", parts_info)
        assert result["summary"]["available_parts"] == 2
        assert result["summary"]["average_score"] == 70.0  # (60+80)/2

    def test_all_missing_average_score_is_none(self, tmp_path):
        vp1 = _video_path(tmp_path, "part1.mp4")
        vp2 = _video_path(tmp_path, "part2.mp4")

        parts_info = [
            {"part_no": 1, "video_path": str(vp1)},
            {"part_no": 2, "video_path": str(vp2)},
        ]

        result = build_job_quality_summary("job1", parts_info)
        assert result["summary"]["average_score"] is None
        assert result["summary"]["available_parts"] == 0

    def test_include_reports_true_embeds_report_dicts(self, tmp_path):
        vp = _video_path(tmp_path)
        qd = _quality_dir(vp)
        report_data = _make_report(95.0, [])
        _write_report(qd, "job1", 1, report_data)

        parts_info = [{"part_no": 1, "video_path": str(vp)}]
        result = build_job_quality_summary("job1", parts_info, include_reports=True)

        part = result["parts"][0]
        assert part["report"] is not None
        assert isinstance(part["report"], dict)
        assert part["report"]["score"] == 95.0

    def test_include_reports_false_excludes_report_dicts(self, tmp_path):
        vp = _video_path(tmp_path)
        qd = _quality_dir(vp)
        _write_report(qd, "job1", 1, _make_report(95.0, []))

        parts_info = [{"part_no": 1, "video_path": str(vp)}]
        result = build_job_quality_summary("job1", parts_info, include_reports=False)

        part = result["parts"][0]
        assert part["report"] is None

    def test_severity_counts_correct(self, tmp_path):
        vp = _video_path(tmp_path)
        qd = _quality_dir(vp)
        issues = [
            {"code": "a", "severity": "critical", "message": "c", "confidence": 1.0},
            {"code": "b", "severity": "critical", "message": "c", "confidence": 1.0},
            {"code": "c", "severity": "error", "message": "e", "confidence": 0.9},
            {"code": "d", "severity": "warning", "message": "w", "confidence": 0.8},
            {"code": "e", "severity": "warning", "message": "w", "confidence": 0.7},
            {"code": "f", "severity": "warning", "message": "w", "confidence": 0.6},
            {"code": "g", "severity": "info", "message": "i", "confidence": 0.5},
        ]
        _write_report(qd, "job1", 1, _make_report(50.0, issues))

        parts_info = [{"part_no": 1, "video_path": str(vp)}]
        result = build_job_quality_summary("job1", parts_info)

        part = result["parts"][0]
        assert part["critical_count"] == 2
        assert part["error_count"] == 1
        assert part["warning_count"] == 3
        assert part["info_count"] == 1
        assert part["issue_count"] == 7

        s = result["summary"]
        assert s["critical_count"] == 2
        assert s["error_count"] == 1
        assert s["warning_count"] == 3
        assert s["info_count"] == 1

    def test_never_raises_on_garbage_parts_info(self):
        garbage = [None, 42, "str", {}, {"part_no": "abc", "video_path": None}]
        result = build_job_quality_summary("job1", garbage)
        assert isinstance(result, dict)
        assert "parts" in result
        assert "summary" in result

    def test_never_raises_on_none_parts_info(self):
        result = build_job_quality_summary("job1", None)  # type: ignore
        assert isinstance(result, dict)

    def test_missing_video_path_part_is_unavailable(self):
        parts_info = [{"part_no": 1, "video_path": None}]
        result = build_job_quality_summary("job1", parts_info)
        assert result["parts"][0]["available"] is False

    def test_aggregate_counts_across_multiple_parts(self, tmp_path):
        vp1 = _video_path(tmp_path, "part1.mp4")
        vp2 = _video_path(tmp_path, "part2.mp4")
        qd1 = _quality_dir(vp1)
        qd2 = _quality_dir(vp2)

        issues1 = [
            {"code": "a", "severity": "error", "message": "e", "confidence": 0.9},
            {"code": "b", "severity": "warning", "message": "w", "confidence": 0.8},
        ]
        issues2 = [
            {"code": "c", "severity": "error", "message": "e2", "confidence": 0.9},
            {"code": "d", "severity": "warning", "message": "w2", "confidence": 0.8},
            {"code": "e", "severity": "warning", "message": "w3", "confidence": 0.7},
        ]

        _write_report(qd1, "job1", 1, _make_report(80.0, issues1))
        _write_report(qd2, "job1", 2, _make_report(60.0, issues2))

        parts_info = [
            {"part_no": 1, "video_path": str(vp1)},
            {"part_no": 2, "video_path": str(vp2)},
        ]

        result = build_job_quality_summary("job1", parts_info)
        s = result["summary"]
        assert s["error_count"] == 2
        assert s["warning_count"] == 3
        assert s["average_score"] == 70.0
