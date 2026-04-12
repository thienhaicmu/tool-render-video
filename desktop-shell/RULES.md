# Non-Negotiable Rules

## Do
- Keep route handlers thin; place logic in `services/`.
- Validate input via `schemas.py` or explicit route checks.
- Update job state (`jobs` + `job_parts`) for long-running render work.
- Keep backward compatibility for channel paths and status values.
- Prefer deterministic, idempotent operations for retries.
- Fail with explicit, actionable errors.

## Don't
- Don't bypass `job_manager` for render tasks.
- Don't block request threads with full render/upload workflows.
- Don't change DB schema or status enums without migration/update path.
- Don't hardcode machine-specific absolute paths.
- Don't disable Electron isolation (`contextIsolation`, `nodeIntegration`).
- Don't silently swallow exceptions that affect pipeline correctness.

## Change Gate
- API contract change requires synchronized update: schema + route + caller.
- `channels/<code>/` contract must remain readable.
- Reject performance regressions (extra transcodes/probes/write churn).
