# 04 — User Journey

Reverse-engineered purely from code on branch `feature/ai-workflow-upgrade`. No reliance on README/docs.

---

## Step 1 — App launch

| Aspect | Detail |
|---|---|
| User action | Double-click Electron executable |
| FE | [frontend/src/main.tsx](../../frontend/src/main.tsx) mounts React; `App` defaults `uiStore.activePanel = 'home'` → `HistoryScreen` |
| Electron main | [desktop-shell/main.js](../../desktop-shell/main.js) detects Python, ensures venv, spawns backend `127.0.0.1:8000`, polls `/health`, shows splash |
| BE | FastAPI startup: `init_db`, fallback path probe, default channel `k1`, cleanup prunes, `recover_pending_render_jobs()` ([main.py:227-280](../../backend/app/main.py)) |
| User sees | History list of past jobs (likely empty on first run) |
| DB writes | only schema bootstrap / migrations |

---

## Step 2 — Authentication

**There is none.** Confirmed independently in both Phase 1 and Phase 2.

| Evidence | Where |
|---|---|
| No auth middleware on FastAPI app | [backend/app/main.py:177](../../backend/app/main.py) (only CSP middleware installed) |
| `apiFetch` never sets `Authorization` | [frontend/src/api/client.ts](../../frontend/src/api/client.ts) |
| WS endpoint accepts any `job_id` without validation | [backend/app/routes/jobs.py:644-696](../../backend/app/routes/jobs.py) |
| No `users` / `sessions` table in DB | see [03_database_inventory.md](03_database_inventory.md) |
| `routes/devtools.py` is shell-exec endpoint gated only by `ENABLE_DEVTOOLS=1` env | [main.py:133](../../backend/app/main.py) |

**FINDING-U01 (HIGH if ever exposed publicly):** This is a desktop-bound assumption. The same FastAPI server can be reached on `127.0.0.1:8000` from any process on the host machine. Anything malicious that lands on the user's PC can hit any endpoint, delete jobs, and (if `ENABLE_DEVTOOLS=1`) run arbitrary shell commands. Acceptable for Electron's intended model **only because** the install ships with `ENABLE_DEVTOOLS` unset.

---

## Step 3 — Source selection (Local vs Downloader)

### 3a. Local file
- UI: [frontend/src/features/clip-studio/render/RenderWorkflow.tsx](../../frontend/src/features/clip-studio/render/RenderWorkflow.tsx) line ~194 — `window.electronAPI?.pickVideoFile?.()` opens native picker.
- API: `prepareSource({ source_mode: 'local', source_video_path })` → POST `/api/render/prepare-source`.
- BE handler: [features/render/router.py:263-377](../../backend/app/features/render/router.py) — validates file, probes via ffprobe, transcodes a preview, registers an in-memory session keyed by `session_id`.
- DB: **no writes here.** Preview sessions are in-memory only (kept until pruned by `evict_stale_preview_sessions`).
- WS events emitted: `render.prepare_source.{start,detect_input,validate_input,prepare_paths,select_strategy,success}`.

### 3b. YouTube / TikTok / Instagram (Downloader)
- UI: [frontend/src/features/downloader/DownloaderScreen.tsx](../../frontend/src/features/downloader/DownloaderScreen.tsx) — paste URL, click "Download".
- API: GET info, then POST `/api/downloader/start` (`platformDownloader.ts`).
- BE handler: [features/download/router.py](../../backend/app/features/download/router.py) — `start_download` validates URL + output, generates `job_id`, writes a row in `download_jobs`, submits `_run_download` to a `ThreadPoolExecutor`.
- DB: row in `download_jobs` (separate from `jobs`).
- WS endpoint: `/api/downloader/jobs/{jobId}/ws`. Poll-based, 500 ms cadence.

**FINDING-U02 (LOW):** The downloader runs from the same per-process `ThreadPoolExecutor` as renders. No separate pool. A noisy queue of large YouTube downloads can slow render submission. Bounded only by `MAX_CONCURRENT_JOBS`.

---

## Step 4 — Channel / output directory selection

- All inputs on `RenderWorkflow.tsx`. State fields `output_mode` (`'manual' | 'channel'`), `channel_code` (optional), `output_dir`.
- Channel-mode validation: BE [router.py:219-261](../../backend/app/features/render/router.py) requires `output_dir` to live under the channel's path.
- No DB write at this step.

**FINDING-U03 (LOW):** "Channel" concept exists in BE (table `creator_prefs` + `channels/` filesystem) but the FE has no actual channel management screen. `SettingsScreen` only edits a singleton creator-context blob (Sprint 3). Channel selection is currently a string typed by the user.

---

## Step 5 — Configure (Render parameters)

100% client-side. No backend round-trip until "Start".

- UI: [frontend/src/features/clip-studio/render/steps/StepConfigure.tsx](../../frontend/src/features/clip-studio/render/steps/StepConfigure.tsx) (~50+ knobs).
- Knobs include: preset (`viral|balanced|engagement`), aspect (`9:16|1:1|16:9`), min/max clip duration, subtitle/voice/overlay toggles, AI provider+key+model, TTS engine.
- Persistence: select keys like `rw_ai_cloud_provider` go to `localStorage`.

**FINDING-U04 (HIGH — repeat from Phase 1):** Cloud LLM API keys live in `localStorage` and travel in the render payload. Any renderer-process code (XSS, malicious extension if it ever gets installed, debug build with devtools open) can read them in plaintext. No OS keychain integration.

---

## Step 6 — Submit render

- User clicks **Start Render** → `handleStartRender()` ([RenderWorkflow.tsx:199](../../frontend/src/features/clip-studio/render/RenderWorkflow.tsx)).
- FE assembles `RenderRequest` from `cfg + prepareResult + sources`.
- POST `/api/render/process` ([frontend/src/api/render.ts:11-16](../../frontend/src/api/render.ts)).
- BE handler [router.py:584-603](../../backend/app/features/render/router.py): `_coerce_legacy_channel_payload`, `_validate_render_source`, `_validate_text_layers_or_400`, resolves `effective_channel`, generates `job_id = uuid.uuid4()` (unless resume), calls `_queue_render_job` ([router.py:542-581](../../backend/app/features/render/router.py)).
- `_queue_render_job`:
  - Refuses duplicate (409 if running).
  - **DB write:** `upsert_job(job_id, kind='render', channel_code, status='queued', stage=QUEUED, progress_percent=0, payload_json)` — [db/jobs_repo.py:12-33](../../backend/app/db/jobs_repo.py).
  - `submit_job(job_id, process_render, ...)` enqueues in the priority min-heap inside [backend/app/jobs/manager.py](../../backend/app/jobs/manager.py).
- Response: `{ job_id, status: "queued", resume_mode }`.

User sees **Step 3 — Rendering** screen and a WS connection opens to `/api/jobs/{job_id}/ws`.

---

## Step 7 — Watch progress

- UI: [StepRendering.tsx](../../frontend/src/features/clip-studio/render/steps/StepRendering.tsx).
- Subscribes via `useRenderSocket(jobId)` (frontend hook).
- `RenderSocketClient` opens `WS /api/jobs/{jobId}/ws`, reconnects with backoff (20 attempts, 2s → 30s cap), ignores `{type: "ping"}` keepalive.
- BE handler: [routes/jobs.py:644-696](../../backend/app/routes/jobs.py) is a **poll-based push**: every 500 ms it reads `get_job`, `list_job_parts`, computes `_compute_progress_summary`, hashes a fingerprint, sends only when the fingerprint changes.

WS event shape (Sacred Contract #6):
```json
{ "job": {…}, "parts": [{…}], "summary": {…} }
```

DB writes during this stage are emitted by the render pipeline (`_emit_render_event`, `update_job_progress`, `upsert_job_part`) — covered in [05_workflow_system.md](05_workflow_system.md) and [07_workflow_render.md](07_workflow_render.md).

**FINDING-U05 (MED):** The "WebSocket" connection is actually **polling 500 ms against the DB and pushing diffs over the WS frame**. There is no in-process pub/sub from the pipeline to the WS handler. Pros: dead simple, naturally survives reconnects. Cons: every connected viewer adds 2 QPS of read load to SQLite. With a single user this is fine; if the desktop UI ever opens two windows it doubles. The WS event log emitted by `_emit_render_event` is **logged to file**, never sent on the WS frame.

---

## Step 8 — Inspect / export results

- UI: [StepResults.tsx](../../frontend/src/features/clip-studio/render/steps/StepResults.tsx).
- FE fetches: `getJobParts`, `getJobQualitySummary`, `getJobRanking`, `getAiSummary` from `frontend/src/api/jobs.ts`.
- For preview/download: `GET /api/jobs/{job_id}/parts/{part_no}/stream` ([routes/jobs.py](../../backend/app/routes/jobs.py)) streams the rendered MP4 with HTTP range support.
- Per-clip actions reachable from this screen:
  - Trim → `POST /api/jobs/{id}/parts/{n}/trim` ([features/render/editing/router.py](../../backend/app/features/render/editing/router.py))
  - Re-render → `POST /api/jobs/{id}/parts/{n}/rerender`
  - Export to user's filesystem → `POST /api/jobs/{id}/parts/{n}/export`
  - Rate `+1/-1` → `POST /api/feedback/jobs/{id}/parts/{n}` (writes `clip_feedback`)
  - Delete → `DELETE /api/jobs/{id}/parts/{n}/output`
  - Retry failed parts → `POST /api/render/retry/{job_id}`

---

## Sub-flow A — Downloader (full)

See Step 3b above. Distinct from render jobs:
- Uses table `download_jobs` (not `jobs`).
- Backed by yt-dlp; per-platform adapters in `features/download/adapters/`.
- Cookie extraction for YouTube via `features/download/engine/cookie_extractor.py` (reads Chrome cookies DB at startup).

**FINDING-U06 (MED):** Cookie extractor reads from the user's local Chrome profile at startup ([main.py:280](../../backend/app/main.py) daemon thread). This is *necessary* for age-gated YouTube content but is also a **data-handling event** worth documenting in user-facing docs. No consent prompt is shown in the FE.

---

## Sub-flow B — Editor (trim within a finished job)

- UI: [frontend/src/features/editor/EditorScreen.tsx](../../frontend/src/features/editor/EditorScreen.tsx) plus the trim modal inside the clip-studio results step.
- The standalone `EditorScreen` is largely UI-only: it loads a clip via the streaming endpoint, lets the user drag handles, mutates `editorStore` state. Submitting a real trim/re-render goes through `POST /api/jobs/{id}/parts/{n}/trim` or `…/rerender` ([features/render/editing/router.py](../../backend/app/features/render/editing/router.py)).
- Re-render reuses the render pipeline through `edit_session_id`.

**FINDING-U07 (MED — repeat of F06):** Two surfaces (`editor/` and the trim modal in `clip-studio/`) overlap. Likely candidate for retirement in Phase 11 roadmap.

---

## DB writes recap by step

| Step | Tables written |
|---|---|
| 1 | (schema bootstrap) |
| 2 | – |
| 3a | – (in-memory preview) |
| 3b | `download_jobs` |
| 4 | – |
| 5 | – |
| 6 | `jobs` (insert) |
| 7 | `jobs` (progress updates), `job_parts` (per-part transitions) |
| 8 | `clip_feedback` (rating), `jobs.result_json` (on edit/rerender), `job_parts` (on trim) |

End of 04_workflow_user.md.
