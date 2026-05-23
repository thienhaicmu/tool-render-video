"""Tests for subtitle density assessment in quality assessor."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.quality.assessor import assess_rendered_part_quality
from app.quality.models import QualityReport


def _make_probe(has_audio=True, duration=30.0):
    return {
        "has_video": True,
        "has_audio": has_audio,
        "duration": duration,
        "fps": 30.0,
        "width": 1080,
        "height": 1920,
    }


def _ts(s: float) -> str:
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02d}:{(ms % 3600000) // 60000:02d}:{(ms % 60000) // 1000:02d},{ms % 1000:03d}"


def _write_srt(path: Path, blocks: list[tuple[float, float, str]]) -> None:
    lines = []
    for idx, (start, end, text) in enumerate(blocks, start=1):
        lines.append(f"{idx}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def _assess(tmp_path: Path, srt_blocks: list[tuple[float, float, str]]) -> QualityReport:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 1000)
    srt = tmp_path / "sub.srt"
    _write_srt(srt, srt_blocks)
    with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
         patch("app.quality.assessor.subprocess"):
        mock_probe.return_value = _make_probe()
        return assess_rendered_part_quality(video, srt_path=srt)


class TestSubtitleDensityDetection:
    def test_normal_subtitle_no_density_issues(self, tmp_path):
        blocks = [
            (0.0, 2.0, "Hello world"),
            (2.5, 4.5, "This is fine"),
        ]
        report = _assess(tmp_path, blocks)
        density_codes = {"subtitle_flash", "subtitle_too_fast", "subtitle_line_too_long",
                         "subtitle_density_overload"}
        found = {i.code for i in report.issues} & density_codes
        assert not found

    def test_flash_block_detected(self, tmp_path):
        """A block with duration < 0.5s triggers subtitle_flash."""
        blocks = [
            (0.0, 0.3, "Flash"),  # 0.3s < 0.5s → flash
            (1.0, 3.0, "Normal block"),
        ]
        report = _assess(tmp_path, blocks)
        codes = [i.code for i in report.issues]
        assert "subtitle_flash" in codes

    def test_flash_block_has_correct_severity(self, tmp_path):
        blocks = [(0.0, 0.2, "Flash")]
        report = _assess(tmp_path, blocks)
        issue = next((i for i in report.issues if i.code == "subtitle_flash"), None)
        assert issue is not None
        assert issue.severity == "warning"
        assert issue.confidence == pytest.approx(0.9)

    def test_subtitle_density_overload_when_30pct_flash(self, tmp_path):
        """More than 30% of blocks being flash triggers density_overload error."""
        # 4 flash out of 10 = 40% → overload
        blocks = []
        for i in range(6):
            blocks.append((i * 2.0, i * 2.0 + 1.5, "Normal text here"))
        for i in range(4):
            blocks.append((20.0 + i * 1.0, 20.0 + i * 1.0 + 0.2, "Flash"))
        report = _assess(tmp_path, blocks)
        codes = [i.code for i in report.issues]
        assert "subtitle_density_overload" in codes
        issue = next(i for i in report.issues if i.code == "subtitle_density_overload")
        assert issue.severity == "error"

    def test_subtitle_density_overload_not_triggered_when_below_threshold(self, tmp_path):
        """Less than 30% flash — density_overload should NOT fire."""
        blocks = []
        for i in range(9):
            blocks.append((i * 2.0, i * 2.0 + 1.5, "Normal text here"))
        # Only 2 out of 11 = ~18% < 30%
        blocks.append((20.0, 20.2, "Flash"))
        blocks.append((21.0, 21.2, "Flash"))
        report = _assess(tmp_path, blocks)
        codes = [i.code for i in report.issues]
        assert "subtitle_density_overload" not in codes

    def test_subtitle_too_fast_detected(self, tmp_path):
        """8 words in 2 seconds = 4 wps > 3.5 → too_fast."""
        blocks = [(0.0, 2.0, "one two three four five six seven eight")]
        report = _assess(tmp_path, blocks)
        codes = [i.code for i in report.issues]
        assert "subtitle_too_fast" in codes

    def test_subtitle_too_fast_below_threshold_no_issue(self, tmp_path):
        """3 words in 2 seconds = 1.5 wps < 3.5 → no issue."""
        blocks = [(0.0, 2.0, "hello world today")]
        report = _assess(tmp_path, blocks)
        codes = [i.code for i in report.issues]
        assert "subtitle_too_fast" not in codes

    def test_subtitle_line_too_long_detected(self, tmp_path):
        """A line with 43+ chars triggers line_too_long."""
        long_line = "a" * 43  # 43 chars > 42 limit
        blocks = [(0.0, 3.0, long_line)]
        report = _assess(tmp_path, blocks)
        codes = [i.code for i in report.issues]
        assert "subtitle_line_too_long" in codes

    def test_subtitle_line_within_limit_no_issue(self, tmp_path):
        """A line with 42 chars or fewer → no line_too_long."""
        line = "a" * 42
        blocks = [(0.0, 3.0, line)]
        report = _assess(tmp_path, blocks)
        codes = [i.code for i in report.issues]
        assert "subtitle_line_too_long" not in codes

    def test_density_metrics_stored_in_report(self, tmp_path):
        blocks = [
            (0.0, 2.0, "Hello world"),
            (2.5, 4.5, "More text"),
        ]
        report = _assess(tmp_path, blocks)
        assert "subtitle_total_blocks" in report.metrics
        assert "subtitle_flash_count" in report.metrics
        assert "subtitle_flash_ratio" in report.metrics
        assert "subtitle_too_fast_count" in report.metrics
        assert "subtitle_line_too_long_count" in report.metrics
        assert report.metrics["subtitle_total_blocks"] == 2

    def test_empty_srt_no_issues_no_crash(self, tmp_path):
        """An empty SRT file must not produce issues and must not crash."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 1000)
        srt = tmp_path / "empty.srt"
        srt.write_text("", encoding="utf-8")
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe()
            report = assess_rendered_part_quality(video, srt_path=srt)
        density_codes = {"subtitle_flash", "subtitle_too_fast", "subtitle_line_too_long",
                         "subtitle_density_overload"}
        found = {i.code for i in report.issues} & density_codes
        assert not found

    def test_malformed_srt_safe_fallback(self, tmp_path):
        """A completely malformed SRT file must not crash."""
        video = tmp_path / "v.mp4"
        video.write_bytes(b"x" * 1000)
        srt = tmp_path / "bad.srt"
        srt.write_text("this is not SRT format at all!!! random garbage", encoding="utf-8")
        with patch("app.quality.assessor.probe_video_metadata") as mock_probe, \
             patch("app.quality.assessor.subprocess"):
            mock_probe.return_value = _make_probe()
            report = assess_rendered_part_quality(video, srt_path=srt)
        assert isinstance(report, QualityReport)

    def test_flash_ratio_computed_correctly(self, tmp_path):
        """flash_ratio stored in metrics is accurate."""
        # 3 flash out of 6 total = 0.5
        blocks = []
        for i in range(3):
            blocks.append((i * 3.0, i * 3.0 + 2.0, "Normal text"))
        for i in range(3):
            blocks.append((10.0 + i * 1.0, 10.0 + i * 1.0 + 0.2, "Flash"))
        report = _assess(tmp_path, blocks)
        ratio = report.metrics.get("subtitle_flash_ratio", 0.0)
        assert abs(ratio - 0.5) < 0.01

    def test_varying_display_durations_parsed_correctly(self, tmp_path):
        """Blocks with various durations are all parsed without error."""
        blocks = [
            (0.0, 0.1, "Very flash"),
            (1.0, 1.4, "Still flash"),
            (2.0, 5.0, "Normal"),
            (6.0, 20.0, "Long block here"),
        ]
        report = _assess(tmp_path, blocks)
        # Should have flash issues for first two but not crash
        assert report.metrics.get("subtitle_total_blocks", 0) == 4
