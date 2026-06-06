# 01 — Frontend Inventory

Branch `feature/ai-workflow-upgrade`. Source of truth: `frontend/**`, `desktop-shell/**`, top-level HTML prototypes. Build artifacts (`node_modules/`, `dist/`, `out/`, `portable_build/`, `win-unpacked/`) excluded.

---

## A. Stack

| Layer | Tech | Evidence |
|---|---|---|
| Framework | React 18.3.1 + React DOM 18.3.1 | [frontend/package.json](../../frontend/package.json) (deps) |
| Build tool | Vite 5.3.4 | [frontend/package.json](../../frontend/package.json) `devDependencies` |
| Language | TypeScript 5.5.3, strict mode | [frontend/tsconfig.app.json](../../frontend/tsconfig.app.json) |
| State | Zustand 4.5.2 | [frontend/package.json](../../frontend/package.json) |
| Testing | Vitest 1.6.0 (deps only — see Phase 9) | [frontend/package.json](../../frontend/package.json) |
| Codegen | `openapi-typescript` 7.4.4 → `src/types/openapi-generated.ts` | [frontend/package.json](../../frontend/package.json) scripts |
| Path alias | `@/*` → `src/*` | [frontend/vite.config.ts:6](../../frontend/vite.config.ts) |
| Build output | `../backend/static-v2` (consumed by FastAPI) | [frontend/vite.config.ts](../../frontend/vite.config.ts) |
| Dev proxy | `/api/*` → `http://127.0.0.1:8000` | [frontend/vite.config.ts:21](../../frontend/vite.config.ts) |

**FINDING-F01 (LOW):** OpenAPI generation pipeline exists (`openapi-typescript`), but contract sync is _not enforced_ by CI/git hooks. If backend changes a schema, FE compiles against stale types until someone reruns the generator. Phase 7 will audit drift.

---

## B. Routing

Routing is **panel-based**, not URL-based. There is no React Router. The single entry [frontend/src/App.tsx](../../frontend/src/App.tsx) reads `useUIStore().activePanel` and switches on a discriminated union.

| Panel value | Mounted component | File |
|---|---|---|
| `clip-studio` | `ClipStudio` (fullscreen) | `src/features/clip-studio/ClipStudio.tsx` |
| `home` | `HistoryScreen` | `src/features/jobs/HistoryScreen.tsx` |
| `library` | `HistoryScreen` | (same) |
| `download` | `DownloaderScreen` | `src/features/downloader/DownloaderScreen.tsx` |
| `settings` | `SettingsScreen` | `src/features/settings/SettingsScreen.tsx` |
| `publish` | `PublishPlaceholder` (TBD) | (stub) |
| `render`, `history`, `editor` (deprecated aliases) | mapped to existing screens | App.tsx backward-compat block |

Within `clip-studio`, sub-tabs `RENDER | DOWNLOAD | HISTORY` are client-side switches inside `ClipStudio.tsx`.

**FINDING-F02 (LOW):** Deep linking impossible — there is no URL routing; the active panel is purely in Zustand state, so refreshing always lands on the default. Acceptable for an Electron desktop app, **but** the SPA is _also_ served by FastAPI at `static-v2/` (Vite outDir) where browser refresh **does** matter. Cross-check in Phase 7.

---

## C. State Management

Zustand stores live in [frontend/src/stores/](../../frontend/src/stores/):

| Store | Purpose | File |
|---|---|---|
| `useUIStore` | active panel, sidebar, notifications, language | `uiStore.ts` |
| `useRenderStore` | jobs map, activeJobId, `submitRender()` | `renderStore.ts` |
| `useQualityStore` | quality panel cache | `qualityStore.ts` |
| `useEditorStore` | trim/effects editor state | `editorStore.ts` |

**FINDING-F03 (MEDIUM):** No auth/session store and no auth tokens anywhere in `src/api/**`. Either auth is delegated to Electron's same-origin trust model or there is genuinely no auth surface. The backend has `routes/devtools.py` which CLAUDE.md flags as "unauthenticated shell execution". Phase 12 (security) will follow up.

---

## D. API clients

Base wrapper: [frontend/src/api/client.ts](../../frontend/src/api/client.ts) (~76 LOC).

- HTTP via native `fetch`, wrappers `apiFetch<T>()` + `apiFetchFormData<T>()`.
- Base URL from `VITE_API_BASE_URL` (default empty → same-origin).
- FastAPI-style `{detail}` error parsing, throws structured `ApiError`.

WebSocket via hand-rolled `RenderSocketClient` ([frontend/src/websocket/RenderSocketClient.ts](../../frontend/src/websocket/RenderSocketClient.ts)):
- Endpoint: `WS /api/jobs/{jobId}/ws`
- Up to 20 reconnect attempts, exponential backoff (2s → 30s cap).
- Backend sends `{"type":"ping"}` every 25s; client ignores (TCP keep-alive only).

Module breakdown ([frontend/src/api/](../../frontend/src/api/)):

| Module | Endpoints touched |
|---|---|
| `render.ts` | POST `/api/render/process`, `/api/render/prepare-source`, `/api/render/resume/{jobId}`, `/api/render/retry/{jobId}`, `/api/render/{jobId}/cancel`, GET `/api/render/preview-video/{sessionId}`, `/api/render/preview-transcript/{sessionId}`, POST `/api/render/test-cloud-ai` |
| `jobs.ts` | GET `/api/jobs/history`, `/api/jobs/{jobId}`, `/api/jobs/{jobId}/parts`, `/api/jobs/{jobId}/quality`, `/api/jobs/{jobId}/ai-summary`; DELETE `/api/jobs/{jobId}`, `/api/jobs/{jobId}/parts/{partNo}/output` |
| `upload.ts` | POST `/api/upload-file` (BGM/audio assets) |
| `editing.ts` | POST `/api/jobs/{jobId}/parts/{partNo}/{trim,rerender,export}` |
| `feedback.ts` | POST/GET/DELETE `/api/feedback/jobs/{jobId}/parts/{partNo}` |
| `creatorContext.ts` | GET/PUT `/api/settings/creator-context` |
| `platformDownloader.ts` | (used by DownloaderScreen) |

**FINDING-F04 (LOW):** `jobs.ts:184` explicitly bans `GET /api/jobs` (unbounded) and forces `getJobHistory(limit, offset)` for pagination. Healthy guard.

**FINDING-F05 (LOW):** `upload.ts:21-29` documents 7 removed endpoints (`/api/upload/accounts/ensure`, `/api/upload/login/check`, `/api/upload/queue/*`, …). Phase 6 should confirm none of these return 200 by accident.

---

## E. Feature modules

[frontend/src/features/](../../frontend/src/features/):

| Feature | Purpose | Representative file |
|---|---|---|
| `clip-studio/` | Primary 3-step render workflow (Source → Configure → Results) + Download + History sub-tabs | `clip-studio/render/RenderWorkflow.tsx` |
| `editor/` | Legacy trim/effects editor (separate from clip-studio) | `editor/EditorScreen.tsx` |
| `downloader/` | Standalone YT/platform downloader (separate from clip-studio's download tab) | `downloader/DownloaderScreen.tsx` |
| `jobs/` | Job history list + detail drawer + AI summary card + output gallery | `jobs/HistoryScreen.tsx`, `jobs/AiSummaryCard.tsx` |
| `progress/` | Live job progress (parts grid, stage timeline, message log) | `progress/JobProgressPanel.tsx` |
| `quality/` | Quality reports per-part | `quality/QualityPanel.tsx` |
| `settings/` | Creator context + cleanup + system info | `settings/SettingsScreen.tsx` |

**FINDING-F06 (MEDIUM):** Two parallel surface areas for the same data:
- `editor/` vs the trim modal inside `clip-studio/`'s results step
- `downloader/` (sidebar panel) vs `clip-studio/`'s DOWNLOAD sub-tab

This is the symptom of an incomplete unification toward `clip-studio`. Phase 4 (dead code) + Phase 3 (architecture violations) should decide what to retire.

---

## F. Reusable components

Top-level [frontend/src/components/ui/](../../frontend/src/components/ui/): `Button`, `Card`, `Badge`, `StatusPill`, `ScoreBadge`, `ProgressBar`, `Notifications`, `ErrorBoundary`, `EmptyState`, `AIChip`. Quality-specific reusables under `components/quality/`: `QualityBadge`, `QualityIssueList`.

---

## G. Upload / Source flow

1. UI: `RenderWorkflow.tsx` Step 1 — paste URL OR pick local file via `window.electronAPI?.pickVideoFile?.()` ([frontend/src/features/clip-studio/render/RenderWorkflow.tsx:194](../../frontend/src/features/clip-studio/render/RenderWorkflow.tsx)).
2. `prepareSource()` → POST `/api/render/prepare-source` (line 156). Payload: `{source_mode: 'local', source_video_path}`. **YouTube ingest was removed in Phase 4F.5A** — verify in Phase 6.
3. Response: `PrepareSourceResponse` (`session_id`, `duration`, `title`, `export_dir`).
4. Preview: GET `/api/render/preview-video/{sessionId}` (line 75 of `render.ts`).
5. Transcript: GET `/api/render/preview-transcript/{sessionId}` for subtitle preview.

BGM/audio upload uses POST `/api/upload-file` (form-data, single `file` field, returns `{path}`).

---

## H. Render flow

[frontend/src/features/clip-studio/render/RenderWorkflow.tsx](../../frontend/src/features/clip-studio/render/RenderWorkflow.tsx) (~700 LOC) is the central component. Four steps:

1. **Source** — see G above.
2. **Configure** — 50+ render params (preset, clip count, duration bounds, AI settings, subtitle style, narration, effects). Persisted to component state; selected items (e.g. `rw_ai_cloud_provider`) go to `localStorage`.
3. **Rendering** — `handleStartRender` calls `submitRender(payload)` → POST `/api/render/process` → returns `{ job_id }`. WS opens at `/api/jobs/{jobId}/ws`.
   - Handlers: `onStageChange`, `onProgress`, `onComplete`, `onReconnecting`, `onError`.
4. **Results** — parts grid (thumbnail, score, delete, download), AI Summary card (`AiSummaryCard.tsx`), quality panel (on-demand via `getJobQuality`). Per-clip feedback `+1/-1`, trim, re-render, export, retry-failed all reachable from this screen.

---

## I. AI interaction

- **Creator context** managed in `settings/SettingsScreen.tsx`: GET/PUT `/api/settings/creator-context`.
- **AI Director knobs** in StepConfigure: `aiAnalysisMode` (`local|cloud|hybrid`), `aiCloudProvider` (`gemini|openai|claude`), API key (localStorage).
- **AI summary** in `jobs/AiSummaryCard.tsx`: GET `/api/jobs/{jobId}/ai-summary` → `JobAiSummary` ([frontend/src/api/jobs.ts:147-164](../../frontend/src/api/jobs.ts)) with fields `best_part_no`, `best_score`, `best_reason`, `ranking_summary[]`, `rejected_segments[]`, `hybrid_analysis`.
- Model strings exposed to user: `gemini-2.0-flash`, `gpt-4o`, `claude-sonnet-4-6` ([frontend/src/features/jobs/AiSummaryCard.tsx](../../frontend/src/features/jobs/AiSummaryCard.tsx) ~lines 12-16). Phase 5 will cross-check actual backend model strings.

**FINDING-F07 (HIGH):** Cloud API keys are kept in `localStorage` (per `RenderWorkflow.tsx`) and shipped to the backend in the render payload. For an Electron app this is acceptable, but: any code running in the renderer process (XSS, malicious extension in dev mode, third-party iframes) reads them in plaintext. Phase 12 will follow up. No keychain integration found.

---

## J. Desktop shell (Electron)

| Concern | Evidence |
|---|---|
| Electron version | 31.0.2 — [desktop-shell/package.json](../../desktop-shell/package.json) |
| Main process | [desktop-shell/main.js](../../desktop-shell/main.js) (~600 LOC) |
| Backend bootstrap (Python detect, venv create, pip install, Playwright install) | main.js:191-237 |
| Backend spawn (`backend-bin/render-backend.exe` packaged, else venv Python) | main.js:~240 |
| Health check polls `http://127.0.0.1:8000/health` | main.js |
| State cache | `{userData}/data/state/bootstrap-state.json` |
| Logs | `{userData}/data/logs/desktop-backend.log` |
| Preload bridge (context-isolated) | [desktop-shell/preload.js](../../desktop-shell/preload.js) (~89 LOC) |
| Exposed API | `pickDirectory`, `pickVideoFile`, `pickCookiesFile`, `openPath`, `onJobProgress`, `onBootStatus`, `onBootVersion`, `getAppVersion` |
| IPC handlers | `dialog:pickDirectory`, `pick-video-file`, `open-folder-picker`, `pick-cookies-file`, `shell:openPath`, `path:exists`, `open-browser-profile` (Playwright launch) |
| Bundled resources | `backend/`, `backend-bin/render-backend.exe`, `ffmpeg-bin/{ffmpeg.exe,ffprobe.exe}`, frontend `dist` → `backend/static-v2` |

**FINDING-F08 (MEDIUM):** `open-browser-profile` IPC handler launches Playwright Chromium from the main process. This is a fairly large attack surface (browser automation) for what appears to be a niche TikTok/Instagram login helper. Phase 12 should check whether `nodeIntegration` is disabled and the preload is the only renderer↔main channel.

---

## K. Standalone HTML prototypes

- [render-flow.html](../../render-flow.html) (144 KB, "AI Clip Studio — Render Flow")
- [prototype.html](../../prototype.html) (96 KB)

Neither is imported by any `frontend/src/**` file (verified — no `index.html` references either). Pure design prototypes.

**FINDING-F09 (LOW, CLAUDE.md disagrees):** CLAUDE.md has an entire dedicated section reminding agents that `render-flow.html` is "prototype only, never done until ported". CLAUDE.md keeps treating it as canonical, but it isn't referenced anywhere in source. Either delete the prototypes or move them to `docs/design/`.

---

## L. Dead / retired surface

| Symbol | Evidence |
|---|---|
| `features/studio/` (older 6-step flow) | Retired in Sprint 5.6; commented in App.tsx |
| `'studio'` panel value | Removed from `ActivePanel` enum |
| `'render' \| 'history' \| 'editor'` panel aliases | Kept as backward-compat re-mappings |
| Bulk `/api/upload/*` endpoints | Removed Phase 4F.5A; only `/api/upload-file` survives |
| `GET /api/jobs` (unbounded) | Banned via comment in `jobs.ts:184`, FE forces `getJobHistory` |

---

## Summary stats

| Metric | Count |
|---|---|
| Top-level feature dirs in `frontend/src/features/` | 7 |
| Zustand stores | 4 |
| API client modules | 7 |
| Distinct REST endpoints called by FE | ~25 (Phase 6 will catalog) |
| WebSocket endpoints | 1 (`/api/jobs/{id}/ws`) |
| Standalone HTML prototypes (unused) | 2 |
| Electron preload exposed methods | 8 |

End of 01_frontend_inventory.md.
