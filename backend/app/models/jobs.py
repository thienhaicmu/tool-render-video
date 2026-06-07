"""Job API schemas.

Split out of ``app.models.schemas`` in the MT-2 schemas decomposition
(audit-2026-06-06 MT-2, 2026-06-06). Existing callers continue to work
via the re-export shim in ``app.models.schemas``.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict


# ── Job status response (GET /api/jobs/{job_id}) ─────────────────────────────
# Mirrors frontend/src/types/api.ts:JobStatus and the day-1 columns of the
# `jobs` table in app.db. Wired as response_model on routes/jobs.py so the
# field set is documented and enforced by Pydantic. extra="allow" preserves
# additive forward-compatibility: future columns reach the wire without
# breaking the contract, but the documented fields are guaranteed present.
class JobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    kind: str
    status: str
    stage: str = ""
    progress_percent: int = 0
    message: str = ""
    payload_json: Optional[str] = None
    result_json: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # error_kind is populated by the handler when status == "failed" — Optional
    # so non-failed responses (where the field may be NULL in DB) still validate.
    error_kind: Optional[str] = None
