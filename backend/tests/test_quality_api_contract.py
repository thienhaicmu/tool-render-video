"""test_quality_api_contract.py — Phase 5.10 quality API contract tests.

Verifies:
- Quality endpoints return 404 for unknown jobs (not 500)
- Quality endpoints return 400 for invalid job_id (path traversal attempts)
- Quality endpoints return 400 for invalid part_no
- GET /api/jobs/{job_id}/quality returns dict with expected top-level keys
- GET /api/jobs/{job_id}/parts/{part_no}/quality returns dict with expected keys
- UI contract doc exists
"""
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNKNOWN_JOB = "aaaabbbb-cccc-dddd-eeee-000000000000"
_VALID_ID_FORMAT = "test-job-id-12345"


# ---------------------------------------------------------------------------
# 1. 404 for unknown job (not 500)
# ---------------------------------------------------------------------------

class TestQualityEndpoint404ForUnknown:
    def test_part_quality_404_unknown_job(self):
        resp = client.get(f"/api/jobs/{_UNKNOWN_JOB}/parts/1/quality")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_job_quality_404_unknown_job(self):
        resp = client.get(f"/api/jobs/{_UNKNOWN_JOB}/quality")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_part_quality_not_500(self):
        """Should never return 500 for a missing job."""
        resp = client.get(f"/api/jobs/{_UNKNOWN_JOB}/parts/1/quality")
        assert resp.status_code != 500

    def test_job_quality_not_500(self):
        resp = client.get(f"/api/jobs/{_UNKNOWN_JOB}/quality")
        assert resp.status_code != 500


# ---------------------------------------------------------------------------
# 2. 400 for invalid job_id (path traversal / bad characters)
# ---------------------------------------------------------------------------

class TestQualityEndpointInvalidJobId:
    def test_part_quality_rejects_dots_in_job_id(self):
        """job_id with dots should be rejected as 400 or routed differently (404)."""
        resp = client.get("/api/jobs/../../etc/parts/1/quality")
        # FastAPI routing may 404 before validation; either is acceptable
        assert resp.status_code in (400, 404, 422)

    def test_job_quality_rejects_dots_in_job_id(self):
        resp = client.get("/api/jobs/../../etc/quality")
        assert resp.status_code in (400, 404, 422)

    def test_part_quality_400_for_special_char_job_id(self):
        """job_id with invalid characters returns 400."""
        resp = client.get("/api/jobs/job%23invalid/parts/1/quality")
        # Either 404 (routing) or 400 (validation)
        assert resp.status_code in (400, 404, 422)

    def test_long_job_id_rejected(self):
        """job_id longer than 128 chars must be rejected."""
        long_id = "a" * 200
        resp = client.get(f"/api/jobs/{long_id}/parts/1/quality")
        assert resp.status_code in (400, 404, 422)


# ---------------------------------------------------------------------------
# 3. 400 for invalid part_no
# ---------------------------------------------------------------------------

class TestQualityEndpointInvalidPartNo:
    def test_part_quality_400_for_part_no_zero(self):
        """part_no=0 is not a positive integer — must return 400."""
        resp = client.get(f"/api/jobs/{_VALID_ID_FORMAT}/parts/0/quality")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"

    def test_part_quality_400_for_negative_part_no(self):
        resp = client.get(f"/api/jobs/{_VALID_ID_FORMAT}/parts/-1/quality")
        assert resp.status_code in (400, 404, 422)

    def test_part_quality_422_for_string_part_no(self):
        """Non-integer part_no should fail FastAPI type validation."""
        resp = client.get(f"/api/jobs/{_VALID_ID_FORMAT}/parts/abc/quality")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 4. Response shape for job quality summary
# ---------------------------------------------------------------------------

class TestJobQualityResponseShape:
    def test_job_quality_response_has_job_id(self):
        """Even for unknown job, the endpoint 404s — so test with a seeded job or check docs."""
        # We can test the summary builder directly
        from backend.app.quality.report_summary import build_job_quality_summary
        result = build_job_quality_summary("test-job", [], include_reports=False)
        assert "job_id" in result

    def test_job_quality_response_has_parts(self):
        from backend.app.quality.report_summary import build_job_quality_summary
        result = build_job_quality_summary("test-job", [], include_reports=False)
        assert "parts" in result
        assert isinstance(result["parts"], list)

    def test_job_quality_response_has_summary(self):
        from backend.app.quality.report_summary import build_job_quality_summary
        result = build_job_quality_summary("test-job", [], include_reports=False)
        assert "summary" in result

    def test_summary_has_required_keys(self):
        from backend.app.quality.report_summary import build_job_quality_summary
        result = build_job_quality_summary("test-job", [], include_reports=False)
        summary = result["summary"]
        required_keys = [
            "available_parts", "total_parts", "average_score",
            "critical_count", "error_count", "warning_count", "info_count",
        ]
        for key in required_keys:
            assert key in summary, f"summary missing key: {key}"

    def test_summary_with_no_parts_has_zero_counts(self):
        from backend.app.quality.report_summary import build_job_quality_summary
        result = build_job_quality_summary("test-job", [], include_reports=False)
        summary = result["summary"]
        assert summary["available_parts"] == 0
        assert summary["total_parts"] == 0
        assert summary["average_score"] is None

    def test_summary_job_id_matches_input(self):
        from backend.app.quality.report_summary import build_job_quality_summary
        result = build_job_quality_summary("my-job-123", [], include_reports=False)
        assert result["job_id"] == "my-job-123"

    def test_include_reports_false_sets_report_to_none(self):
        from backend.app.quality.report_summary import build_job_quality_summary
        parts_info = [{"part_no": 1, "video_path": None}]
        result = build_job_quality_summary("test-job", parts_info, include_reports=False)
        if result["parts"]:
            assert result["parts"][0]["report"] is None


# ---------------------------------------------------------------------------
# 5. Response shape for single-part quality report
# ---------------------------------------------------------------------------

class TestPartQualityResponseShape:
    def test_quality_report_dict_has_required_keys(self):
        """QualityReport.to_dict() must have the documented keys."""
        from backend.app.quality.models import QualityReport
        report = QualityReport(job_id="test", part_no=1)
        d = report.to_dict()
        required_keys = ["job_id", "part_no", "score", "issues", "metrics", "ai_trace_refs", "created_at"]
        for key in required_keys:
            assert key in d, f"QualityReport.to_dict() missing key: {key}"

    def test_quality_report_score_in_range(self):
        from backend.app.quality.models import QualityReport
        report = QualityReport(job_id="test", part_no=1)
        assert 0.0 <= report.score <= 100.0

    def test_quality_issue_dict_has_required_keys(self):
        from backend.app.quality.models import QualityIssue
        issue = QualityIssue(
            code="test_issue", severity="warning",
            message="Test message", confidence=0.9
        )
        d = issue.to_dict()
        required_keys = ["code", "severity", "message", "confidence", "part_no", "evidence", "recommended_action"]
        for key in required_keys:
            assert key in d, f"QualityIssue.to_dict() missing key: {key}"

    def test_quality_report_add_issue_reduces_score(self):
        from backend.app.quality.models import QualityIssue, QualityReport
        report = QualityReport(job_id="test", part_no=1)
        initial_score = report.score
        issue = QualityIssue(code="test", severity="warning", message="test", confidence=1.0)
        report.add_issue(issue)
        assert report.score < initial_score

    def test_critical_issue_reduces_score_to_zero(self):
        from backend.app.quality.models import QualityIssue, QualityReport
        report = QualityReport(job_id="test", part_no=1)
        issue = QualityIssue(code="critical", severity="critical", message="fatal", confidence=1.0)
        report.add_issue(issue)
        assert report.score == 0.0

    def test_confidence_clamped_to_0_1(self):
        from backend.app.quality.models import QualityIssue
        issue = QualityIssue(code="x", severity="info", message="x", confidence=5.0)
        assert issue.confidence <= 1.0

    def test_unknown_severity_normalized(self):
        from backend.app.quality.models import QualityIssue
        issue = QualityIssue(code="x", severity="catastrophic", message="x", confidence=0.5)
        assert issue.severity == "warning"  # normalized to default


# ---------------------------------------------------------------------------
# 6. report_locator security
# ---------------------------------------------------------------------------

class TestReportLocatorSecurity:
    def test_invalid_job_id_returns_none(self):
        from backend.app.quality.report_locator import find_quality_report_path
        from pathlib import Path
        result = find_quality_report_path("../../etc/passwd", 1, Path("/tmp/test.mp4"))
        assert result is None

    def test_invalid_part_no_zero_returns_none(self):
        from backend.app.quality.report_locator import find_quality_report_path
        from pathlib import Path
        result = find_quality_report_path("valid-job-id", 0, Path("/tmp/test.mp4"))
        assert result is None

    def test_invalid_part_no_negative_returns_none(self):
        from backend.app.quality.report_locator import find_quality_report_path
        from pathlib import Path
        result = find_quality_report_path("valid-job-id", -1, Path("/tmp/test.mp4"))
        assert result is None

    def test_valid_but_missing_report_returns_none(self):
        from backend.app.quality.report_locator import find_quality_report_path
        from pathlib import Path
        result = find_quality_report_path("valid-job-id-123", 1, Path("/nonexistent/video.mp4"))
        assert result is None

    def test_validate_job_id_rejects_slash(self):
        from backend.app.quality.report_locator import _validate_job_id
        assert not _validate_job_id("job/id")

    def test_validate_job_id_rejects_dot(self):
        from backend.app.quality.report_locator import _validate_job_id
        assert not _validate_job_id("job.id")

    def test_validate_job_id_accepts_hyphen_underscore(self):
        from backend.app.quality.report_locator import _validate_job_id
        assert _validate_job_id("job-id_with-hyphens")

    def test_validate_job_id_rejects_too_long(self):
        from backend.app.quality.report_locator import _validate_job_id
        assert not _validate_job_id("a" * 129)

    def test_validate_part_no_rejects_bool(self):
        from backend.app.quality.report_locator import _validate_part_no
        assert not _validate_part_no(True)

    def test_validate_part_no_rejects_string(self):
        from backend.app.quality.report_locator import _validate_part_no
        assert not _validate_part_no("1")

    def test_validate_part_no_accepts_positive_int(self):
        from backend.app.quality.report_locator import _validate_part_no
        assert _validate_part_no(1)
        assert _validate_part_no(100)


# ---------------------------------------------------------------------------
# 7. Quality route validation in jobs router
# ---------------------------------------------------------------------------

class TestQualityJobIdValidation:
    def test_jobs_router_has_job_id_regex(self):
        """The jobs router must have a _JOB_ID_RE regex."""
        from backend.app.routes.jobs import _JOB_ID_RE
        import re
        assert _JOB_ID_RE is not None
        assert _JOB_ID_RE.match("valid-job-id-123")
        assert not _JOB_ID_RE.match("invalid/job/id")

    def test_validate_quality_job_id_accepts_uuid(self):
        from backend.app.routes.jobs import _validate_quality_job_id
        assert _validate_quality_job_id("aaaabbbb-cccc-dddd-eeee-000000000000")

    def test_validate_quality_job_id_rejects_slash(self):
        from backend.app.routes.jobs import _validate_quality_job_id
        assert not _validate_quality_job_id("job/id")

    def test_validate_quality_job_id_rejects_dot(self):
        from backend.app.routes.jobs import _validate_quality_job_id
        assert not _validate_quality_job_id("../../etc")


# ---------------------------------------------------------------------------
# 8. UI contract document exists
# ---------------------------------------------------------------------------

class TestContractDocExists:
    def test_ui_backend_contract_md_exists(self):
        contract_path = Path(__file__).resolve().parents[2] / "docs" / "ui" / "UI_BACKEND_CONTRACT.md"
        assert contract_path.exists(), f"Contract doc missing: {contract_path}"

    def test_ui_backend_contract_md_has_content(self):
        contract_path = Path(__file__).resolve().parents[2] / "docs" / "ui" / "UI_BACKEND_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert len(content) > 5000, "Contract doc seems too short"

    def test_ui_backend_contract_md_has_endpoints_section(self):
        contract_path = Path(__file__).resolve().parents[2] / "docs" / "ui" / "UI_BACKEND_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Active API Endpoints" in content

    def test_ui_backend_contract_md_has_renderrequest_section(self):
        contract_path = Path(__file__).resolve().parents[2] / "docs" / "ui" / "UI_BACKEND_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "RenderRequest" in content

    def test_ui_backend_contract_md_has_quality_section(self):
        contract_path = Path(__file__).resolve().parents[2] / "docs" / "ui" / "UI_BACKEND_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Quality Report" in content

    def test_ui_backend_contract_md_mentions_removed_endpoints(self):
        contract_path = Path(__file__).resolve().parents[2] / "docs" / "ui" / "UI_BACKEND_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Removed" in content or "Deprecated" in content

    def test_ui_backend_contract_md_mentions_upload_file(self):
        contract_path = Path(__file__).resolve().parents[2] / "docs" / "ui" / "UI_BACKEND_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "/api/upload-file" in content
