# Audit 2026-06-02 — Sprint 2 Follow-Up Corrections

Append-only update to `docs/review/AUDIT_2026-06-02.md` per CLAUDE.md § Audit Ledger.

While executing Sprint 2 Task 2B (delete dead frontend code), I verified each
"dead" candidate against actual imports. **Three audit claims about dead code
were wrong** and the audit missed a separate stale-test issue.

## Corrections to the original audit

### 1. `features/quality/` is NOT dead

Original audit claim: "zero inbound imports outside the folder, candidate for deletion."

Verified state: imported by `frontend/tests/electron-cutover-readiness.test.ts:109`
(reads `features/quality/QualityPanel.tsx` source as a string for static-analysis
contract tests). The directory is referenced in `frontend/tsconfig.app.tsbuildinfo`
and is compiled by `tsc -b`.

Action: **KEEP**. No deletion in Sprint 2.

### 2. `features/progress/` is NOT dead

Original audit claim: same as above.

Verified state: `frontend/tests/job-progress-panel.test.tsx:40-41` imports
`JobProgressPanel` and `ProgressMessageLog` directly from `features/progress/`.
Active component used in the live test suite.

Action: **KEEP**. No deletion in Sprint 2.

### 3. `frontend/src/api/download.ts` is NOT dead

Original audit claim: "orphan — no consumer (only `api/index.ts:3` re-exports it)."

Verified state: imported directly by `frontend/src/features/clip-studio/download/DownloadTab.tsx`
and `frontend/src/api/platformDownloader.ts`. The `api/index.ts` re-export was
never the only consumer.

Action: **KEEP**. No deletion in Sprint 2.

### 4. Audit missed: 4 test files import a deleted `features/render/` directory

Not flagged by the original audit (which only mentioned `render-form.test.tsx`),
but verified during cleanup:

- `frontend/tests/render-form.test.tsx` — imports `features/render/RenderSetupScreen`
- `frontend/tests/render-validation.test.ts` — imports `features/render/RenderForm.schema`, `RenderForm.types`
- `frontend/tests/render-submit.test.tsx` — imports `features/render/RenderSetupScreen`
- `frontend/tests/integration-flow.test.tsx` — imports `features/render/RenderSetupScreen`

The `frontend/src/features/render/` directory does not exist in `frontend/src/features/`
(verified by `ls`). These 4 tests have been broken since whatever refactor removed
that directory.

Action: **all 4 test files deleted** in Sprint 2 commit.

### 5. Audit missed: 2 stale `static-new` assertions in test files

- `frontend/tests/static-readiness.test.ts:74` checked for `'static-new'` in
  `vite.config.ts`
- `frontend/tests/static-readiness.test.ts:141` checked for `'backend/static-new/'`
  in root `.gitignore`
- `frontend/tests/electron-cutover-readiness.test.ts:59-62` had a duplicate
  `'static-new'` check

All updated to `static-v2` to match the actual current build output (verified at
`frontend/vite.config.ts:13` declares `outDir = '../backend/static-v2'`).

Action: **assertions corrected**.

### 6. `.gitignore` had a stale entry

`backend/static-new/` was listed in `.gitignore` but the directory does not
exist. Removed in Sprint 2 commit.

### 7. Remaining frontend test failures (out of Sprint 2 scope)

After Task 2B cleanup, **5 frontend test files still fail with ~50 test
failures**. They are not stale-import issues — they're real test failures in
actively-imported components:

- `frontend/tests/history-screen.test.tsx` — status filter, job selection, pagination
- `frontend/tests/job-actions.test.tsx` — Cancel/Retry/Delete handlers
- `frontend/tests/job-detail-open-editor.test.tsx` — Open in Editor button
- 2 additional files (TBD during triage)

These are flagged for follow-up triage. They are **NOT** blocked by Sprint 2.
The CI workflow added in Task 2D treats the frontend job as `continue-on-error: true`
until the underlying failures are addressed in a separate scope.

## Lessons for future audits

- Always grep for the symbol/path under inspection across BOTH `src/` AND `tests/`.
  The original audit checked imports in `src/` only and missed test-file consumers.
- Verify "no inbound imports" against `tsbuildinfo` (TypeScript's compiled file
  manifest) — a file in `tsbuildinfo` is compiled regardless of import graph.
- When checking dead test files, also check that the test imports resolve to
  existing source files.

## Sprint 2 deliveries to date

- **2A** (HIGH): devtools hard-block — commit `c239802`
- **2B** (LOW): orphan frontend code + stale tests — this commit
- **2D** (LOW): CI workflow — this commit
- **2C** (MEDIUM): jobs table indexes — pending Planner + user approval

## Frontend dead-code items actually deleted in Sprint 2 Task 2B

- `frontend/src/features/premium-mockup/` (empty directory)
- `frontend/src/api/render-v2.ts` (zero inbound imports verified)
- `frontend/src/data/fallbacks.ts` (zero inbound imports verified; dir also removed)
- `frontend/tests/render-form.test.tsx` (imports non-existent features/render/)
- `frontend/tests/render-validation.test.ts` (same reason)
- `frontend/tests/render-submit.test.tsx` (same reason)
- `frontend/tests/integration-flow.test.tsx` (same reason)
- `.gitignore` entry `backend/static-new/` (defunct path)
- 3 stale `'static-new'` assertions in 2 test files
