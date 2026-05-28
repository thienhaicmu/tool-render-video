# Senior Architecture Review — 2026-05-28

Scope: Full codebase survey, backend + frontend, conducted after C-2 refactor and render-YouTube-source cleanup.

Prior review files: BACKEND_REVIEW.md, FRONTEND_REVIEW.md, BRUTAL_REVIEW_SUMMARY.md

---

## Summary

System is production-ready with accumulated debt. Core orchestration is solid. Weak points are data-contract versioning, frontend state management, and cloud AI credential handling.

---

## Backend Findings

### CRITICAL — Security

**Issue**: Cloud API key stored globally in `.env`, shared across all render jobs. No per-user isolation.
- `backend/app/ai/director/ai_director.py:211` — `_CFG_KEY` used as fallback for all jobs
- If API key leaked, all jobs are compromised simultaneously
- No audit trail of which job consumed which key slot
- **Recommendation**: Per-session key storage with job-level audit log

---

### HIGH — Data Contract

**Issue**: `result_json` has no version field. Schema changes silently break frontend consumers.
- `backend/app/orchestration/render_pipeline.py` — writes `result_json` as freeform dict
- Frontend parses directly without validation
- Breaking changes cause silent `undefined` in UI — no exception thrown
- **Recommendation**: Add `schema_version: int` field; migrate old records

**Issue**: `error_kind` added only in WebSocket on terminal+failed status. HTTP GET on same job does NOT include it.
- `backend/app/routes/jobs.py:639` — WS adds `error_kind` to payload
- `GET /api/jobs/{id}` response never includes `error_kind`
- Frontend must always use `error_kind ?? null` — defensive but fragile
- **Recommendation**: Store `error_kind` in DB on job failure; include in all GET responses

---

### HIGH — Frontend State

**Issue**: `renderStore` (Zustand) is write-only — populated on submit, never updated from WebSocket.
- `frontend/src/stores/renderStore.ts` — writes job on submit only
- WebSocket updates only flow to component-local state via `useRenderSocket`
- If any component reads from store after submission, it sees stale data
- **Recommendation**: Update store from WebSocket terminal events

---

### MEDIUM — Performance

**Issue**: `GET /api/jobs` returns all jobs, unbounded.
- `backend/app/routes/jobs.py:89–99` — no limit/offset in list_jobs()
- `GET /api/jobs/history` (paginated) exists and should be the only path
- On large installs (1000+ jobs), full table scan
- **Recommendation**: Deprecate unbounded endpoint; enforce pagination

**Issue**: `useRenderSocket` triggers full component re-render every 500ms.
- `frontend/src/hooks/useRenderSocket.ts` — no memoization on progress events
- Parent components re-render on every WebSocket tick
- **Recommendation**: Memoize progress data; only trigger re-render on material state change

---

### MEDIUM — Reliability

**Issue**: FFmpeg process has no explicit timeout.
- `backend/app/services/render_engine.py` — spawns FFmpeg without timeout
- Wall-clock stall detection in QA pipeline delays kill by 2–3 hours on hang
- **Recommendation**: Add `timeout` param to FFmpeg subprocess calls; kill after stall threshold

**Issue**: Thread cancel does not guarantee FFmpeg subprocess termination.
- `backend/app/orchestration/render_pipeline.py` — sets `cancel_event` flag
- FFmpeg subprocess runs independently; may not stop for minutes
- **Recommendation**: Store FFmpeg PID per part; send SIGTERM/SIGKILL on cancel

**Issue**: Pending job queue not persisted to disk.
- `backend/app/services/job_manager.py` — in-memory min-heap
- Server restart loses all queued (not yet running) jobs
- By design, but surprising to users who submit then restart backend
- **Recommendation**: Document this behavior explicitly in startup logs

---

### MEDIUM — Observability

**Issue**: AI Director cloud failures logged at DEBUG level only.
- `backend/app/ai/analysis/cloud/base.py:43` — `cloud_analyzer_failed` at DEBUG
- **Fixed in this session**: elevated to WARNING
- `backend/app/ai/director/ai_director.py:228` — cloud=None fallthrough still has no log
- **Recommendation**: Add WARNING log at ai_director.py:228 when mode=cloud but cloud is None

**Issue**: Progress estimate is linear, not real.
- `backend/app/orchestration/render_events.py:138–230` — background thread emits 70–99% linearly
- On variable-bitrate files, estimate can be wrong by 30+ minutes
- Frontend shows percentage users interpret as real progress
- **Recommendation**: Document that percentage is estimated; add "(estimated)" label in UI

---

### LOW — Validation

**Issue**: Quick Process endpoint accepts resize dimensions without bounds.
- `backend/app/routes/render.py:1174–1281` — no max for resize_width/resize_height
- User can send 99999x99999 → OOM on FFmpeg
- **Recommendation**: Add validation: max 7680x4320 (8K)

**Issue**: Fuzzy error classification via substring matching.
- `backend/app/routes/jobs.py:27–50` — `"ffmpeg" in message.lower()` → `FFMPEG_FAILED`
- User-provided title containing "ffmpeg" would trigger false classification
- **Recommendation**: Classify by pipeline stage, not message content

---

## Frontend Findings

### HIGH — Component Size

**Issue**: `RenderWorkflow.tsx` is ~2500 lines — monolithic.
- `frontend/src/features/clip-studio/render/RenderWorkflow.tsx`
- Contains 4 steps (Source, Configure, Rendering, Results) in one component
- Multiple `useEffect` hooks create stale closure risk
- Step 4 (Results) alone is ~800 lines
- **Recommendation**: Split into Step1Source, Step2Configure, Step3Monitor, Step4Results

---

### MEDIUM — Type Safety

**Issue**: TypeScript types for backend responses are manually maintained.
- `frontend/src/types/api.ts` — hand-written, not generated from Pydantic schemas
- Any backend field rename or add/remove requires manual frontend sync
- No automated check that types match
- **Recommendation**: Generate TypeScript types from OpenAPI schema (FastAPI exports `/openapi.json`)

**Issue**: `RenderRequest` has 100+ fields — most not exposed in any UI.
- `frontend/src/types/api.ts` — imports RenderRequest with all fields
- Many fields are legacy, internal, or placeholder
- **Recommendation**: Split into `RenderRequestPublic` (UI-facing) and `RenderRequestFull` (internal)

---

### MEDIUM — Navigation

**Issue**: No route guards — user can navigate away mid-render.
- `frontend/src/App.tsx:27–40` — panel switching has no confirmation
- WebSocket disconnects on navigate; component state lost
- **Recommendation**: Show confirmation dialog if active render job exists

---

### LOW — Naming

**Issue**: `features/render/RenderForm.tsx` is deprecated but still mounted in App.tsx.
- Marked as deprecated (PANEL_MAP comment), but still accessible via `render` panel
- Source_mode YouTube removed in this session, but form is otherwise dead code
- **Recommendation**: Remove `render` panel entry from App.tsx PANEL_MAP; delete `features/render/`

---

## What Was Fixed In This Session

| Fix | File | Severity |
|-----|------|----------|
| Cloud AI log elevated to WARNING | `ai/analysis/cloud/base.py` | MEDIUM |
| YouTube source removed from render feature | `features/render/*` | MEDIUM |
| C-2: 19 creator functions extracted to creator_context.py | `ai/director/creator_context.py` | Refactor |
| clip-card2 width increased 155→200px | `RenderWorkflow.css` | UX |
| base.py cloud log DEBUG→WARNING | `ai/analysis/cloud/base.py` | Observability |

---

## Unchanged Issues (Carry Forward)

- result_json versioning: no schema_version field
- error_kind: not stored in DB, only in WS event
- renderStore: stale after submit
- list_jobs(): unbounded endpoint still accessible
- RenderWorkflow.tsx: monolithic, needs decomposition
- Quick Process: no resize dimension bounds
- Thread cancellation: FFmpeg PID not tracked
