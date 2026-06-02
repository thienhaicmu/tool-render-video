"""test_jobs_api_contract.py — Sprint 3 3D contract test.

Verifies that GET /api/jobs/{job_id}:
- Returns 200 with a payload that satisfies JobStatusResponse (frontend contract)
- Returns 404 for unknown job_id
- Preserves additive forward-compat: extra DB columns (e.g., channel_code,
  priority) still reach the client even though they're not in the typed model

Audit reference: docs/review/AUDIT_2026-06-02.md P2 finding —
"GET /api/jobs/{id} returns untyped dict from raw DB row".
"""
from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from app.db.jobs_repo import upsert_job, delete_job

client = TestClient(app)


_REQUIRED_FIELDS = {
    "job_id",
    "kind",
    "status",
    "stage",
    "progress_percent",
    "message",
    "payload_json",
    "result_json",
    "created_at",
    "updated_at",
    "error_kind",
}


@pytest.fixture
def temp_job():
    """Insert a temporary job row, yield its id, then clean up."""
    job_id = f"test-jobs-api-{uuid.uuid4().hex[:8]}"
    upsert_job(
        job_id=job_id,
        kind="render",
        channel_code="test-channel",
        status="queued",
        stage="queued",
        progress_percent=0,
        message="",
        payload={},
        result={},
    )
    try:
        yield job_id
    finally:
        try:
            delete_job(job_id)
        except Exception:
            pass


class TestGetJobResponseShape:
    def test_returns_200_for_known_job(self, temp_job):
        resp = client.get(f"/api/jobs/{temp_job}")
        assert resp.status_code == 200, resp.text

    def test_response_contains_all_required_fields(self, temp_job):
        resp = client.get(f"/api/jobs/{temp_job}")
        body = resp.json()
        missing = _REQUIRED_FIELDS - set(body.keys())
        assert not missing, f"JobStatusResponse missing fields: {missing}"

    def test_job_id_matches_request(self, temp_job):
        resp = client.get(f"/api/jobs/{temp_job}")
        assert resp.json()["job_id"] == temp_job

    def test_extra_db_columns_pass_through(self, temp_job):
        """extra='allow' on the Pydantic model preserves additive columns.

        channel_code is in the DB schema but NOT in JobStatusResponse; the
        client must still see it for backward compatibility with consumers
        that depend on day-1 row shape.
        """
        resp = client.get(f"/api/jobs/{temp_job}")
        body = resp.json()
        assert "channel_code" in body, (
            "additive column channel_code was filtered out — "
            "extra='allow' is not configured"
        )
        assert body["channel_code"] == "test-channel"


class TestGetJobNotFound:
    def test_returns_404_for_unknown_job(self):
        unknown = f"nonexistent-{uuid.uuid4().hex}"
        resp = client.get(f"/api/jobs/{unknown}")
        assert resp.status_code == 404


class TestRenderRequestContractTwo:
    """Sprint 3 3E Subsets A + B — Sacred Contract 2 compliance for
    RenderRequest bool fields that were defaulting True.

    Subset A (Sprint 3): ai_director_enabled, ai_use_rag_memory — both
    represent modules removed in Phase G, now no-ops.

    Subset B (current commit): hook_apply_enabled, ai_auto_cut,
    ai_use_semantic_hooks, ai_render_influence_enabled, ai_beat_pulse_enabled
    — live phase features. New-job behavior preserved by UI explicit-True in
    RenderWorkflow.buildPayload; stored historical payloads missing these
    fields no longer silently activate the features on Resume/Retry.
    """

    # ── Subset A (Phase G removed modules) ──────────────────────────────

    def test_ai_director_enabled_defaults_false(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.ai_director_enabled is False, (
            "ai_director_enabled must default to False — the AI Director "
            "module was removed in Phase G; defaulting True would have "
            "stored payloads falsely claim the feature was on."
        )

    def test_ai_use_rag_memory_defaults_false(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.ai_use_rag_memory is False, (
            "ai_use_rag_memory must default to False — RAG memory was "
            "removed in Phase G; defaulting True would have stored payloads "
            "falsely claim the feature was on."
        )

    # ── Subset B (live phase features) ──────────────────────────────────

    def test_hook_apply_enabled_defaults_false(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.hook_apply_enabled is False

    def test_ai_auto_cut_defaults_false(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.ai_auto_cut is False

    def test_ai_use_semantic_hooks_defaults_false(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.ai_use_semantic_hooks is False

    def test_ai_render_influence_enabled_defaults_false(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.ai_render_influence_enabled is False

    def test_ai_beat_pulse_enabled_defaults_false(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest()
        assert req.ai_beat_pulse_enabled is False

    # ── Backward compat: explicit True still accepted ───────────────────

    def test_subset_a_explicit_true_still_accepted(self):
        """Stored historical payloads that explicitly set True still load."""
        from app.models.schemas import RenderRequest
        req = RenderRequest(ai_director_enabled=True, ai_use_rag_memory=True)
        assert req.ai_director_enabled is True
        assert req.ai_use_rag_memory is True

    def test_subset_b_explicit_true_still_accepted(self):
        """Same backward-compat guarantee for the 5 phase-feature fields."""
        from app.models.schemas import RenderRequest
        req = RenderRequest(
            hook_apply_enabled=True,
            ai_auto_cut=True,
            ai_use_semantic_hooks=True,
            ai_render_influence_enabled=True,
            ai_beat_pulse_enabled=True,
        )
        assert req.hook_apply_enabled is True
        assert req.ai_auto_cut is True
        assert req.ai_use_semantic_hooks is True
        assert req.ai_render_influence_enabled is True
        assert req.ai_beat_pulse_enabled is True
