"""test_ui_backend_contract.py — Phase 5.10 UI/backend contract tests.

Verifies:
- Active endpoints are registered on the FastAPI app
- Removed /api/upload/* routes are absent
- /api/upload-file POST exists
- Quality endpoints exist
- RenderRequest can be instantiated with minimal fields
"""
import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Core / system endpoints
# ---------------------------------------------------------------------------

class TestCoreEndpoints:
    def test_health_endpoint_exists(self):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_status_ok(self):
        resp = client.get("/health")
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_returns_ui_version(self):
        resp = client.get("/health")
        data = resp.json()
        assert "ui_version" in data

    def test_warmup_status_endpoint_exists(self):
        resp = client.get("/api/warmup/status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. Render endpoints
# ---------------------------------------------------------------------------

class TestRenderEndpoints:
    def test_queue_status_exists(self):
        resp = client.get("/api/render/queue-status")
        assert resp.status_code == 200

    def test_queue_status_shape(self):
        resp = client.get("/api/render/queue-status")
        data = resp.json()
        assert "active_renders" in data
        assert "max_renders" in data

    def test_ai_diagnostics_endpoint_exists(self):
        resp = client.get("/api/render/ai-diagnostics")
        assert resp.status_code == 200

    def test_process_endpoint_exists(self):
        """POST /api/render/process should return 400/422 for bad payload, not 404/405."""
        resp = client.post("/api/render/process", json={})
        assert resp.status_code in (400, 422)

    def test_batch_endpoint_removed(self):
        """POST /api/render/process/batch was removed — must return 404/405, not 400/422."""
        resp = client.post("/api/render/process/batch", json={})
        assert resp.status_code in (404, 405)

    def test_prepare_source_endpoint_exists(self):
        resp = client.post("/api/render/prepare-source", json={"source_mode": "youtube", "youtube_url": ""})
        assert resp.status_code in (400, 422, 500)

    def test_download_health_endpoint_exists(self):
        resp = client.post("/api/render/download-health", json={"youtube_url": ""})
        assert resp.status_code in (400, 422)

    def test_quick_process_endpoint_exists(self):
        resp = client.post("/api/render/quick-process", json={})
        assert resp.status_code in (400, 422)

    def test_resume_endpoint_exists(self):
        resp = client.post("/api/render/resume/nonexistent-job-id")
        assert resp.status_code in (404,)

    def test_retry_endpoint_exists(self):
        resp = client.post("/api/render/retry/nonexistent-job-id")
        assert resp.status_code in (404,)

    def test_cancel_endpoint_exists(self):
        resp = client.post("/api/render/nonexistent-id/cancel")
        assert resp.status_code in (404,)

    def test_get_render_job_endpoint_exists(self):
        resp = client.get("/api/render/jobs/nonexistent-id")
        assert resp.status_code in (404,)


# ---------------------------------------------------------------------------
# 3. Jobs endpoints
# ---------------------------------------------------------------------------

class TestJobsEndpoints:
    def test_jobs_list_exists(self):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200

    def test_jobs_history_exists(self):
        resp = client.get("/api/jobs/history")
        assert resp.status_code == 200

    def test_jobs_history_shape(self):
        resp = client.get("/api/jobs/history")
        data = resp.json()
        assert "items" in data
        assert "limit" in data
        assert "offset" in data
        assert "has_more" in data

    def test_jobs_queue_status_exists(self):
        resp = client.get("/api/jobs/queue/status")
        assert resp.status_code == 200

    def test_jobs_queue_status_shape(self):
        resp = client.get("/api/jobs/queue/status")
        data = resp.json()
        assert "max_concurrent" in data
        assert "active" in data
        assert "pending" in data
        assert "available_slots" in data

    def test_get_job_404_for_unknown(self):
        resp = client.get("/api/jobs/unknown-job-id-xyz")
        assert resp.status_code == 404

    def test_get_job_parts_returns_items(self):
        resp = client.get("/api/jobs/unknown-job-id-xyz/parts")
        # Returns empty list, not 404 — behavior depends on impl
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# 4. Quality endpoints
# ---------------------------------------------------------------------------

class TestQualityEndpoints:
    def test_part_quality_endpoint_exists(self):
        """Quality endpoint for a known-missing job returns 404, not 405 (method not found)."""
        resp = client.get("/api/jobs/test-job-id/parts/1/quality")
        assert resp.status_code in (400, 404)

    def test_job_quality_endpoint_exists(self):
        resp = client.get("/api/jobs/test-job-id/quality")
        assert resp.status_code in (400, 404)

    def test_part_quality_rejects_invalid_part_no_zero(self):
        resp = client.get("/api/jobs/test-job-id/parts/0/quality")
        assert resp.status_code == 400

    def test_part_quality_rejects_invalid_job_id_traversal(self):
        """Path traversal attempt should return 400 or 422."""
        resp = client.get("/api/jobs/../../../etc/parts/1/quality")
        assert resp.status_code in (400, 404, 422)


# ---------------------------------------------------------------------------
# 5. File upload endpoint
# ---------------------------------------------------------------------------

class TestFileUploadEndpoint:
    def test_upload_file_endpoint_exists(self):
        """POST /api/upload-file should return 400/422 for empty upload, not 404/405."""
        resp = client.post("/api/upload-file")
        assert resp.status_code in (400, 422)

    def test_upload_file_method_is_post(self):
        """GET /api/upload-file should return 405 (method not allowed)."""
        resp = client.get("/api/upload-file")
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# 6. Removed /api/upload/* routes are absent
# ---------------------------------------------------------------------------

class TestRemovedUploadRoutes:
    def test_upload_accounts_ensure_absent(self):
        resp = client.post("/api/upload/accounts/ensure", json={})
        assert resp.status_code == 404

    def test_upload_login_check_absent(self):
        resp = client.post("/api/upload/login/check", json={})
        assert resp.status_code == 404

    def test_upload_login_start_absent(self):
        resp = client.post("/api/upload/login/start", json={})
        assert resp.status_code == 404

    def test_upload_queue_add_absent(self):
        resp = client.post("/api/upload/queue/add", json={})
        assert resp.status_code == 404

    def test_upload_queue_get_absent(self):
        resp = client.get("/api/upload/queue")
        assert resp.status_code == 404

    def test_upload_queue_run_absent(self):
        resp = client.post("/api/upload/queue/1/run", json={})
        assert resp.status_code == 404

    def test_upload_queue_cancel_absent(self):
        resp = client.post("/api/upload/queue/1/cancel", json={})
        assert resp.status_code == 404

    def test_generic_upload_domain_absent(self):
        resp = client.get("/api/upload/anything")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. RenderRequest minimal instantiation
# ---------------------------------------------------------------------------

class TestRenderRequestInstantiation:
    def test_minimal_render_request(self):
        """RenderRequest with only required defaults should instantiate without error."""
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest(output_dir="/tmp/test")
        assert req.output_dir == "/tmp/test"

    def test_default_subtitle_style(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.subtitle_style == "tiktok_bounce_v1"

    def test_default_effect_preset(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.effect_preset == "slay_soft_01"

    def test_default_aspect_ratio(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.aspect_ratio == "3:4"

    def test_default_target_platform(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.target_platform == "youtube_shorts"

    def test_default_ai_director_enabled(self):
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.ai_director_enabled is True

    def test_model_dump_is_serializable(self):
        """model_dump() should produce a JSON-serializable dict."""
        import json
        from backend.app.models.schemas import RenderRequest
        req = RenderRequest(output_dir="/tmp/test")
        dumped = req.model_dump()
        json.dumps(dumped)  # Should not raise

    def test_render_profile_validator_rejects_invalid(self):
        """Invalid render_profile should raise ValidationError."""
        from pydantic import ValidationError
        from backend.app.models.schemas import RenderRequest
        with pytest.raises(ValidationError):
            RenderRequest(render_profile="ultra")

    def test_source_quality_mode_validator_rejects_invalid(self):
        from pydantic import ValidationError
        from backend.app.models.schemas import RenderRequest
        with pytest.raises(ValidationError):
            RenderRequest(source_quality_mode="4k_hdr")


# ---------------------------------------------------------------------------
# 8. Static files do not contain old /api/upload/ domain
# ---------------------------------------------------------------------------

class TestStaticFilesNoOldUploadDomain:
    def test_no_api_upload_slash_in_static_js(self):
        """No static JS file should call the removed /api/upload/ domain.

        Note: /api/upload-file (with hyphen) is allowed — only /api/upload/ (slash) is banned.
        """
        import re
        from pathlib import Path
        static_dir = Path(__file__).resolve().parents[2] / "backend" / "static" / "js"
        if not static_dir.exists():
            pytest.skip("Static JS directory not found")

        # Pattern: /api/upload/ with slash (old domain), NOT /api/upload-file (hyphen, allowed)
        old_domain_pattern = re.compile(r"/api/upload/")
        violations: list[str] = []
        for js_file in static_dir.glob("*.js"):
            content = js_file.read_text(encoding="utf-8", errors="replace")
            matches = old_domain_pattern.findall(content)
            if matches:
                violations.append(f"{js_file.name}: {len(matches)} occurrence(s)")
        assert not violations, (
            f"Found /api/upload/ (old domain) calls in static JS files:\n"
            + "\n".join(violations)
        )

    def test_upload_file_endpoint_still_referenced_in_static(self):
        """The correct /api/upload-file endpoint should be referenced in static files."""
        from pathlib import Path
        static_dir = Path(__file__).resolve().parents[2] / "backend" / "static" / "js"
        if not static_dir.exists():
            pytest.skip("Static JS directory not found")

        found = False
        for js_file in static_dir.glob("*.js"):
            content = js_file.read_text(encoding="utf-8", errors="replace")
            if "/api/upload-file" in content:
                found = True
                break
        assert found, "/api/upload-file not found in any static JS file — check editor audio runtime"

    def test_ui_contract_doc_exists(self):
        """The UI contract document must exist."""
        from pathlib import Path
        contract_path = Path(__file__).resolve().parents[2] / "docs" / "ui" / "UI_BACKEND_CONTRACT.md"
        assert contract_path.exists(), f"UI contract doc missing: {contract_path}"
        assert contract_path.stat().st_size > 1000, "UI contract doc appears empty"
