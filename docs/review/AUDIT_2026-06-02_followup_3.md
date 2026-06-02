# Audit 2026-06-02 — Sprint 5.1 Follow-Up: OpenAPI Codegen Drift Detection

Third append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

## What this closes

The audit's P1 "TypeScript drift" finding noted that the frontend
`types/api.ts` was hand-maintained against `backend/app/models/schemas.py`
with no enforcement of sync. This was deferred from Sprint 5 (DX scope)
and showed up directly as a concrete bug in Sprint 3 3E Subset B / P3:
the `ai_provider` field plus 4 Subset B fields were sent by the frontend
buildPayload but missing from `types/api.ts:RenderRequest` — a TS error
went undetected for an unknown amount of time.

Sprint 5.1 adds **drift detection** without forcing the frontend to
migrate off the curated hand-maintained types.

## Architecture

Two-file model for frontend API types:

| File | Role | Source |
|---|---|---|
| `frontend/src/types/api.ts` | Curated, readable surface that frontend code imports | Hand-maintained |
| `frontend/src/types/openapi-generated.ts` | Auto-generated TypeScript declarations from the FastAPI OpenAPI schema | `npm run gen:openapi` |

Frontend application code continues to import from `api.ts`. The generated
file is treated as a **drift signal** — if it changes between commits, the
backend route or Pydantic surface changed and the engineer must consider
whether `api.ts` needs an update too.

## Pipeline

1. `backend/scripts/dump_openapi.py` imports `app.main:app` and writes
   `app.openapi()` to `backend/openapi.json` (gitignored — temp artifact).
2. `frontend/scripts/run-python.mjs` bridges the local venv vs the CI
   system Python — prefers `backend/.venv/Scripts/python.exe`, falls back
   to `python` on PATH.
3. `npm run gen:openapi` invokes the dump script then runs
   `openapi-typescript` on the JSON, writing
   `frontend/src/types/openapi-generated.ts` (4091 lines, committed).
4. `npm run check:openapi-drift` is the CI hook — regenerates + uses
   `git diff --exit-code` on the generated file to detect drift.

## CI job

`.github/workflows/test.yml` gains an `openapi-drift` job that:

- Installs backend `requirements.txt` (for `fastapi`/`pydantic`)
- Installs frontend `npm ci`
- Runs `npm run gen:openapi`
- Diffs the regenerated `openapi-generated.ts` against the committed file
- Fails with a clear `::error::` message instructing the engineer to run
  `npm run gen:openapi` locally and commit the diff

## What this does NOT do

- Does not auto-migrate consumers to the generated types. `api.ts` remains
  the import surface. Generated file is reference + drift signal.
- Does not enforce parity at compile time. Drift detection runs in CI, not
  in `tsc`. A backend field rename without UI update would still
  type-check locally — CI catches it.
- Does not check for semantic equivalence between hand and generated
  types. Comparing two completely different TS shapes is impractical;
  the value is the "API surface changed" signal, not field-by-field
  validation.

## Developer workflow

When a backend Pydantic field is added/renamed:

```
$ cd frontend
$ npm run gen:openapi
# review the diff in src/types/openapi-generated.ts
# update src/types/api.ts to expose the new field (if appropriate)
$ git add src/types/openapi-generated.ts src/types/api.ts
$ git commit -m "feat(api): add new_field to RenderRequest"
```

If a developer forgets step `gen:openapi`, the CI `openapi-drift` job
fails on their PR with instructions.

## Out-of-scope follow-ups

- **Migrate consumers to generated types.** Would replace ~hundreds of
  `api.ts` imports with paths like `paths['/api/render/process']['post']['requestBody']`.
  Verbose; low immediate value while the codebase is small.
- **Type-equivalence enforcement.** Compare each `api.ts` interface
  against the corresponding generated `components.schemas.*` — would catch
  hand-curated types that lag behind generated ones. Requires custom
  tooling; defer.
- **Schema-first contract testing.** Validate live API responses against
  the generated OpenAPI schema. Backend Pydantic already does runtime
  validation; this would be a defense-in-depth layer for very large API
  surfaces.

## State after this entry

- Frontend deps: `openapi-typescript@^7.4.4` added to `devDependencies`
- New scripts: `gen:openapi`, `check:openapi-drift` in `frontend/package.json`
- New tooling: `backend/scripts/dump_openapi.py`, `frontend/scripts/run-python.mjs`
- New artifact: `frontend/src/types/openapi-generated.ts` (committed,
  ~4100 lines)
- `.gitignore`: `backend/openapi.json` (temp artifact)
- CI: new `openapi-drift` job in `.github/workflows/test.yml`
- `frontend/src/types/api.ts` header updated to point at the new flow
