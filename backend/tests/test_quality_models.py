"""Tests for app.quality.models — QualityIssue and QualityReport dataclasses."""
import pytest
from app.quality.models import QualityIssue, QualityReport


class TestQualityIssue:
    def _make(self, **kwargs):
        defaults = {
            "code": "test_code",
            "severity": "warning",
            "message": "Test message",
            "confidence": 0.8,
        }
        defaults.update(kwargs)
        return QualityIssue(**defaults)

    def test_confidence_clamps_above_one(self):
        issue = self._make(confidence=1.5)
        assert issue.confidence == 1.0

    def test_confidence_clamps_below_zero(self):
        issue = self._make(confidence=-0.5)
        assert issue.confidence == 0.0

    def test_confidence_at_boundaries(self):
        assert self._make(confidence=0.0).confidence == 0.0
        assert self._make(confidence=1.0).confidence == 1.0

    def test_to_dict_includes_all_expected_keys(self):
        issue = self._make(part_no=2, recommended_action="Fix it")
        d = issue.to_dict()
        assert "code" in d
        assert "severity" in d
        assert "message" in d
        assert "confidence" in d
        assert "part_no" in d
        assert "evidence" in d
        assert "recommended_action" in d

    def test_to_dict_values_correct(self):
        issue = self._make(code="my_code", severity="error", message="hello", confidence=0.7)
        d = issue.to_dict()
        assert d["code"] == "my_code"
        assert d["severity"] == "error"
        assert d["message"] == "hello"
        assert d["confidence"] == pytest.approx(0.7)

    def test_invalid_severity_normalised_to_warning(self):
        issue = self._make(severity="banana")
        assert issue.severity == "warning"

    def test_evidence_defaults_to_empty_dict(self):
        issue = self._make()
        assert issue.evidence == {}

    def test_to_dict_safe_with_all_defaults(self):
        issue = QualityIssue(code="x", severity="info", message="y", confidence=0.5)
        d = issue.to_dict()
        assert d["part_no"] is None
        assert d["recommended_action"] is None


class TestQualityReport:
    def test_empty_report_serializes_safely(self):
        report = QualityReport()
        d = report.to_dict()
        assert d["score"] == pytest.approx(100.0)
        assert d["issues"] == []
        assert d["metrics"] == {}
        assert d["ai_trace_refs"] == []
        assert "created_at" in d

    def test_score_clamps_to_100_on_init(self):
        report = QualityReport(score=150.0)
        assert report.score == pytest.approx(100.0)

    def test_score_clamps_to_0_on_init(self):
        report = QualityReport(score=-50.0)
        assert report.score == pytest.approx(0.0)

    def test_score_clamps_to_zero_on_critical_issue(self):
        report = QualityReport()
        issue = QualityIssue(code="c", severity="critical", message="bad", confidence=1.0)
        report.add_issue(issue)
        assert report.score == pytest.approx(0.0)

    def test_score_deducted_by_error(self):
        report = QualityReport()
        issue = QualityIssue(code="e", severity="error", message="err", confidence=0.9)
        report.add_issue(issue)
        assert report.score == pytest.approx(75.0)

    def test_score_deducted_by_warning(self):
        report = QualityReport()
        issue = QualityIssue(code="w", severity="warning", message="warn", confidence=0.8)
        report.add_issue(issue)
        assert report.score == pytest.approx(90.0)

    def test_score_deducted_by_info(self):
        report = QualityReport()
        issue = QualityIssue(code="i", severity="info", message="info", confidence=0.5)
        report.add_issue(issue)
        assert report.score == pytest.approx(98.0)

    def test_score_clamps_to_zero_not_negative(self):
        report = QualityReport()
        for _ in range(10):
            report.add_issue(QualityIssue(code="e", severity="error", message="e", confidence=0.9))
        assert report.score == pytest.approx(0.0)

    def test_add_issue_appends_to_list(self):
        report = QualityReport()
        issue = QualityIssue(code="x", severity="info", message="m", confidence=0.5)
        report.add_issue(issue)
        assert len(report.issues) == 1
        assert report.issues[0].code == "x"

    def test_issue_list_preserved_in_to_dict(self):
        report = QualityReport()
        report.add_issue(QualityIssue(code="a", severity="warning", message="A", confidence=0.8))
        report.add_issue(QualityIssue(code="b", severity="info", message="B", confidence=0.5))
        d = report.to_dict()
        assert len(d["issues"]) == 2
        assert d["issues"][0]["code"] == "a"
        assert d["issues"][1]["code"] == "b"

    def test_multiple_issues_accumulate_penalties(self):
        report = QualityReport()
        report.add_issue(QualityIssue(code="w1", severity="warning", message="1", confidence=0.8))
        report.add_issue(QualityIssue(code="w2", severity="warning", message="2", confidence=0.8))
        # 100 - 10 - 10 = 80
        assert report.score == pytest.approx(80.0)

    def test_to_dict_includes_job_id_and_part_no(self):
        report = QualityReport(job_id="job123", part_no=2)
        d = report.to_dict()
        assert d["job_id"] == "job123"
        assert d["part_no"] == 2

    def test_ai_trace_refs_in_to_dict(self):
        report = QualityReport()
        report.ai_trace_refs.append("ai.pacing_applied")
        d = report.to_dict()
        assert "ai.pacing_applied" in d["ai_trace_refs"]
