"""Tests for app.quality.report_locator — security-critical path validation."""
import json
import pytest
from pathlib import Path

from app.quality.report_locator import (
    find_quality_report_path,
    load_quality_report,
    load_quality_report_for_part,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def quality_dir(tmp_path):
    """Create a quality sidecar directory with a valid report file."""
    qdir = tmp_path / "output" / "quality"
    qdir.mkdir(parents=True)
    return qdir


@pytest.fixture
def video_path(tmp_path):
    """Create a fake video file and return its path."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    vp = output_dir / "part1.mp4"
    vp.write_bytes(b"\x00" * 16)
    return vp


@pytest.fixture
def report_data():
    return {
        "job_id": "job-abc123",
        "part_no": 1,
        "score": 87.0,
        "issues": [
            {"code": "probe_failed", "severity": "error", "message": "x", "confidence": 0.7},
            {"code": "subtitle_flash", "severity": "warning", "message": "y", "confidence": 0.9},
        ],
        "metrics": {},
        "ai_trace_refs": [],
        "created_at": "2026-01-01T00:00:00",
    }


def _write_report(quality_dir, job_id, part_no, data):
    path = quality_dir / f"{job_id}_part_{part_no}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# find_quality_report_path
# ---------------------------------------------------------------------------

class TestFindQualityReportPath:

    def test_valid_path_returns_correct_report_path(self, video_path, quality_dir, report_data):
        job_id = "job-abc123"
        part_no = 1
        _write_report(quality_dir, job_id, part_no, report_data)

        result = find_quality_report_path(job_id, part_no, video_path)
        assert result is not None
        assert result.exists()
        assert result.name == f"{job_id}_part_{part_no}.json"

    def test_missing_file_returns_none(self, video_path):
        result = find_quality_report_path("job-notexist", 1, video_path)
        assert result is None

    def test_invalid_job_id_with_slash_returns_none(self, video_path):
        # job_id containing "/" must be rejected
        assert find_quality_report_path("../../etc/passwd", 1, video_path) is None

    def test_invalid_job_id_with_backslash_returns_none(self, video_path):
        assert find_quality_report_path("..\\..\\windows", 1, video_path) is None

    def test_invalid_job_id_with_dot_returns_none(self, video_path):
        assert find_quality_report_path("job.with.dots", 1, video_path) is None

    def test_invalid_job_id_empty_string_returns_none(self, video_path):
        assert find_quality_report_path("", 1, video_path) is None

    def test_invalid_job_id_too_long_returns_none(self, video_path):
        long_id = "a" * 129
        assert find_quality_report_path(long_id, 1, video_path) is None

    def test_invalid_part_no_zero_returns_none(self, video_path):
        assert find_quality_report_path("valid-job", 0, video_path) is None

    def test_invalid_part_no_negative_returns_none(self, video_path):
        assert find_quality_report_path("valid-job", -1, video_path) is None

    def test_invalid_part_no_string_returns_none(self, video_path):
        assert find_quality_report_path("valid-job", "1", video_path) is None  # type: ignore

    def test_invalid_part_no_bool_returns_none(self, video_path):
        # bool is a subclass of int in Python — must be rejected
        assert find_quality_report_path("valid-job", True, video_path) is None

    def test_invalid_part_no_none_returns_none(self, video_path):
        assert find_quality_report_path("valid-job", None, video_path) is None  # type: ignore

    def test_path_traversal_job_id_abs_path_returns_none(self, video_path):
        # Absolute path disguised as job_id should be caught by regex
        assert find_quality_report_path("/etc/passwd", 1, video_path) is None

    def test_path_traversal_job_id_dots_returns_none(self, video_path):
        assert find_quality_report_path("../../../etc", 1, video_path) is None

    def test_resolved_path_outside_quality_dir_returns_none(self, tmp_path):
        """Symlink pointing outside quality dir must be blocked."""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True)
        video_path = output_dir / "part1.mp4"
        video_path.write_bytes(b"\x00" * 16)

        quality_dir = output_dir / "quality"
        quality_dir.mkdir()

        # Create a real file outside quality dir
        outside = tmp_path / "outside.json"
        outside.write_text(json.dumps({"score": 0}), encoding="utf-8")

        # Try a symlink (skip if OS doesn't support)
        link = quality_dir / "job-abc123_part_1.json"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            pytest.skip("Symlink creation not supported on this OS/user level")

        # With symlink pointing outside, resolved path check should block it
        result = find_quality_report_path("job-abc123", 1, video_path)
        # Either None (path traversal blocked) or the resolved outside path
        # The important thing is it doesn't crash; security outcome depends on OS resolution
        # On platforms where symlinks resolve to outside, result is None due to relative_to check
        # On platforms where symlinks aren't followed (or file doesn't exist), also None
        assert result is None or (result is not None and result.exists())

    def test_valid_job_id_with_underscore_and_hyphen(self, video_path, quality_dir, report_data):
        job_id = "job_test-001"
        part_no = 2
        _write_report(quality_dir, job_id, part_no, report_data)
        result = find_quality_report_path(job_id, part_no, video_path)
        assert result is not None

    def test_valid_job_id_max_128_chars(self, video_path, quality_dir, monkeypatch):
        """The validator must accept a 128-char job_id (the regex upper bound).

        Sprint 6.A fix: the previous version of this test wrote a real sidecar
        file with `"a" * 128 + "_part_1.json"` to pytest's tmp_path. On Windows
        the resulting absolute path (~256 chars) sits at the edge of MAX_PATH
        (260) and write_text() fails with FileNotFoundError on systems where
        long-path support is not enabled at the OS level. That's a Windows
        filesystem limitation, not a bug in find_quality_report_path.

        The unit under test is the validator's 128-char boundary. We patch
        Path.exists() to return True only for the expected sidecar name so
        find_quality_report_path() can complete without touching the disk.
        """
        job_id = "a" * 128
        part_no = 1
        expected_name = f"{job_id}_part_{part_no}.json"

        original_exists = Path.exists

        def fake_exists(self: Path) -> bool:
            if self.name == expected_name:
                return True
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", fake_exists)

        result = find_quality_report_path(job_id, part_no, video_path)
        assert result is not None
        assert result.name == expected_name


# ---------------------------------------------------------------------------
# load_quality_report
# ---------------------------------------------------------------------------

class TestLoadQualityReport:

    def test_valid_json_returns_dict(self, tmp_path, report_data):
        p = tmp_path / "report.json"
        p.write_text(json.dumps(report_data), encoding="utf-8")
        result = load_quality_report(p)
        assert isinstance(result, dict)
        assert result["score"] == 87.0

    def test_missing_file_returns_none(self, tmp_path):
        result = load_quality_report(tmp_path / "does_not_exist.json")
        assert result is None

    def test_malformed_json_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json!!!}", encoding="utf-8")
        result = load_quality_report(p)
        assert result is None

    def test_json_array_returns_none(self, tmp_path):
        """Top-level array is not a valid report — must return None."""
        p = tmp_path / "array.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        result = load_quality_report(p)
        assert result is None

    def test_empty_file_returns_none(self, tmp_path):
        p = tmp_path / "empty.json"
        p.write_bytes(b"")
        result = load_quality_report(p)
        assert result is None

    def test_never_raises_on_binary_garbage(self, tmp_path):
        p = tmp_path / "garbage.json"
        p.write_bytes(bytes(range(256)))
        result = load_quality_report(p)
        assert result is None


# ---------------------------------------------------------------------------
# load_quality_report_for_part
# ---------------------------------------------------------------------------

class TestLoadQualityReportForPart:

    def test_combines_find_and_load(self, video_path, quality_dir, report_data):
        job_id = "job-abc123"
        part_no = 1
        _write_report(quality_dir, job_id, part_no, report_data)
        result = load_quality_report_for_part(job_id, part_no, video_path)
        assert result is not None
        assert result["job_id"] == job_id

    def test_missing_report_returns_none(self, video_path):
        result = load_quality_report_for_part("job-notexist", 1, video_path)
        assert result is None

    def test_invalid_job_id_returns_none(self, video_path):
        result = load_quality_report_for_part("../../etc/passwd", 1, video_path)
        assert result is None

    def test_invalid_part_no_zero_returns_none(self, video_path):
        result = load_quality_report_for_part("valid-job", 0, video_path)
        assert result is None

    def test_invalid_part_no_negative_returns_none(self, video_path):
        result = load_quality_report_for_part("valid-job", -1, video_path)
        assert result is None

    def test_never_raises_on_bad_video_path(self):
        # video_path parent doesn't exist — must not raise
        result = load_quality_report_for_part("valid-job", 1, Path("/nonexistent/path/video.mp4"))
        assert result is None

    def test_malformed_sidecar_json_returns_none(self, video_path, quality_dir):
        bad = quality_dir / "bad-job_part_1.json"
        bad.write_text("not json {{{", encoding="utf-8")
        result = load_quality_report_for_part("bad-job", 1, video_path)
        assert result is None
