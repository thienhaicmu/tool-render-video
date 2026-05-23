# Phase 6.0 — UI Foundation Architecture

**Status**: Scaffolded
**Date**: 2026-05-23
**Branch**: `restructure/output-timeline-architecture`
**Contract reference**: `docs/ui/UI_BACKEND_CONTRACT.md` (Phase 5.10 freeze)

---

## 1. Tech Stack Choices and Rationale

| Technology | Version | Rationale |
|---|---|---|
| React 18 | 18.3.x | Component model + hooks; concurrent features for responsive UI |
| TypeScript | 5.5.x | Full type safety from API contract to component props |
| Vite | 5.3.x | Fast dev server with proxy; ESM-native build pipeline |
| Zustand | 4.5.x | Minimal state management, no boilerplate, easy testing |
| Vitest | 1.6.x | Native Vite-integrated test runner; no Jest config overhead |
| @testing-library/react | 16.x | Component tests without implementation details |
| CSS custom properties | N/A | Design tokens without a CSS framework; full control, zero dependency |

**No CSS framework**: The cinematic dark theme requires precise control over colors, spacing,
and motion. CSS custom properties (design tokens) give us that without framework overrides.

---

## 2. Directory Structure Overview

```
frontend/
  src/
    api/           typed API client modules (one per domain)
    components/    shared UI atoms (Button, Badge, ProgressBar)
                   quality/ sub-folder for quality-specific components
    features/      feature modules — Phase 6.1+ (render, jobs, quality, editor)
    layouts/       AppShell, Sidebar, Topbar
    hooks/         useRenderSocket (WebSocket hook)
    stores/        renderStore, qualityStore, uiStore (Zustand)
    websocket/     RenderSocketClient, events
    styles/        tokens.css (design tokens), global.css (reset)
    lib/           constants.ts (option enums, helpers)
    pages/         page-level components — Phase 6.1+
    types/         api.ts (API interfaces), enums.ts (enum types + values)
  tests/
    api.test.ts
    constants.test.ts
    stores.test.ts
    setup.ts
  index.html
  vite.config.ts
  tsconfig.json
  tsconfig.app.json
  tsconfig.node.json
  package.json
  .gitignore
```

---

## 3. State Management Flow

```
User Action
    │
    ▼
React Component
    │ calls store action
    ▼
Zustand Store (renderStore / qualityStore / uiStore)
    │ calls API function
    ▼
API Layer (src/api/*.ts)
    │ fetch() with typed response
    ▼
FastAPI Backend (http://127.0.0.1:8000)
    │ returns JSON
    ▼
API Layer (typed response or ApiError)
    │
    ▼
Zustand Store (state update)
    │
    ▼
React Component (re-render)
```

### Store responsibilities

| Store | Owns |
|---|---|
| `renderStore` | Active job tracking, job submission, job status cache |
| `qualityStore` | On-demand quality reports and summaries (never polled) |
| `uiStore` | Sidebar open/close, active panel, notification queue |

---

## 4. WebSocket Event Flow

```
useRenderSocket(jobId)
    │ creates RenderSocketClient
    ▼
RenderSocketClient.connect(jobId)
    │ new WebSocket(ws://127.0.0.1:8000/api/jobs/{jobId}/ws)
    ▼
Backend pushes JSON every 500ms or on state change
    │ {job, parts, summary}
    ▼
RenderSocketClient.onmessage
    │ parse + type-check
    ▼
Handlers:
  onStageChange(stage, message)  → setStage()
  onProgress(summary)            → setProgress()
  onComplete(event)              → setIsConnected(false) on terminal status
  onError(error)                 → setError()

Reconnect policy: up to 3 attempts, 2s base backoff (exponential)
Terminal status: WebSocket closes; NO reconnect for terminal states
```

---

## 5. Design Token System

Location: `frontend/src/styles/tokens.css`

| Category | Token prefix | Count |
|---|---|---|
| Background colors | `--color-bg-*` | 5 |
| Accent colors | `--color-accent*` | 4 |
| Text colors | `--color-text-*` | 4 |
| Border colors | `--color-border*` | 3 |
| Status colors | `--color-success/warning/error/info` | 8 (with muted variants) |
| Spacing | `--space-1` … `--space-12` | 12 (4px scale) |
| Font size | `--font-size-xs` … `--font-size-3xl` | 8 |
| Font weight | `--font-weight-*` | 4 |
| Line height | `--line-height-*` | 3 |
| Border radius | `--radius-sm` … `--radius-full` | 6 |
| Shadows | `--shadow-sm` … `--shadow-xl`, `--shadow-accent` | 5 |
| Motion | `--duration-fast/normal/slow`, `--ease-*` | 7 |
| Layout | `--sidebar-width`, `--topbar-height`, etc. | 5 |
| Z-index | `--z-base` … `--z-toast` | 5 |

Total: ~79 design tokens

Theme palette:
- Dark backgrounds: `#0A0A0F`, `#111118`, `#18181F`
- Accent: electric purple `#6C63FF`
- Text: `#E8E8F0` (primary), `#8888A0` (secondary)

---

## 6. API Layer Architecture

Location: `frontend/src/api/`

| File | Exports | Endpoints covered |
|---|---|---|
| `client.ts` | `ApiError`, `apiFetch`, `apiFetchFormData`, `BASE_URL` | Base wrapper |
| `render.ts` | `submitRender`, `getRenderStatus`, `cancelRender`, `resumeRender`, `retryRender` | POST /api/render/process, GET /api/render/jobs/{id}, POST cancel/resume/retry |
| `jobs.ts` | `getJob`, `getJobHistory`, `getQueueStatus`, `getJobPartQuality`, `getJobQualitySummary`, `deleteJob` | GET /api/jobs/{id}, /api/jobs/history, /api/jobs/{id}/quality, /api/jobs/{id}/parts/{n}/quality |
| `upload.ts` | `uploadFile` | POST /api/upload-file |
| `index.ts` | Re-exports all | — |

**ApiError class**: `status: number`, `detail: unknown`, `message: string`. Thrown on any non-2xx
response. The `detail` field preserves the raw FastAPI `{detail: ...}` payload for display.

---

## 7. Component Strategy

### Shared UI (`src/components/ui/`)
Purely presentational atoms with no backend dependencies. Props-driven. Used anywhere.
- `Button` — variant + size + loading state
- `Badge` — semantic color variants (success/warning/error/info/neutral)
- `ProgressBar` — 0–100 fill, 3 color variants

### Quality components (`src/components/quality/`)
Domain-specific UI using shared atoms + quality business logic from `lib/constants.ts`.
- `QualityBadge` — score → label + color using §8.3 thresholds
- `QualityIssueList` — grouped by severity, with confidence + action display

### Feature components (`src/features/`) — Phase 6.1+
Self-contained feature modules that own their own API calls via stores.

---

## 8. Migration Strategy

### Coexistence rule
The legacy frontend at `backend/static/` must remain fully operational throughout Phase 6.
It is served via `STATIC_UI_VERSION=legacy` (the default). The new React frontend lives at
`frontend/` and is completely independent.

### Phase 6.x migration path

| Phase | Action |
|---|---|
| 6.0 (this) | Foundation scaffolded. `backend/static/` untouched. |
| 6.1 | Build Render form screen. New build goes to `backend/static-new/`. |
| 6.2 | Build History screen with paginated `/api/jobs/history`. |
| 6.3 | Build Quality panel — per-part quality badges + issue list. |
| 6.4 | Build Editor screen with WebSocket progress. |
| 6.5 | Integration testing with Electron shell. |
| Cut-over | Set `STATIC_UI_VERSION=v2`, mount `backend/static-new/` as `/assets`. |

### Build output
`vite.config.ts` sets `build.outDir = '../backend/static-new'`. This does NOT overwrite the
current `backend/static/` directory. Only after full screen completion and QA should the
cut-over happen via `STATIC_UI_VERSION`.

---

## 9. Phase 6.1 — Render Setup Screen (SHIPPED 2026-05-23)

All items completed:

- [x] Render form screen (`src/features/render/RenderSetupScreen.tsx` + `RenderForm.tsx`)
  - Source group: source_mode toggle (YouTube/Local), youtube_url input, source_video_path
  - Output group: output_dir (required), max_export_parts
  - Creative group: target_platform (3), aspect_ratio (5), effect_preset (6)
  - Subtitle group: add_subtitle toggle, subtitle_style SelectCardGroup (10 canonical presets only)
  - Advanced group: ai_director_enabled, hook_overlay_enabled, remotion_hook_intro, render_profile, min/max_part_sec, title_overlay_text
  - Default subtitle: `tiktok_bounce_v1` (never `pro_karaoke`)
  - Submit → submitRender() → success notification → redirect to history panel
- [x] Notification system (`src/components/ui/Notifications.tsx`)
  - Fixed-position toasts at bottom-right
  - Auto-dismiss after 5 seconds
  - Type-appropriate colors: success/error/info/warning
  - Integrated into AppShell
- [x] Validation schema (`src/features/render/RenderForm.schema.ts`)
  - Pure functions: validateRenderForm, isFormValid, buildRenderPayload
  - All business rules enforced: output_dir required, URL format, part duration ranges, playback speed [0.5, 1.5]
- [x] Feature component decomposition
  - FormField, SelectCardGroup, SourceSection, OutputSection, CreativeSection, SubtitleSection, AdvancedSection, SummaryCard
- [x] Tests: 109/109 passing (6 test files)

---

## 10. Phase 6.2 — History Screen + Job Actions (SHIPPED 2026-05-23)

All items completed:

- [x] History screen (`src/features/jobs/HistoryScreen.tsx`)
  - Paginated list using `getJobHistory(20, offset)` → `/api/jobs/history`
  - Local search filtering: by title, source_hint, job_id
  - Local status filtering: All | Rendering | Complete | Failed | Canceled
  - Pagination: Previous / Next with `has_more` guard
  - Detail drawer panel (380px right rail) for selected job
  - Refresh button
- [x] Job actions (`src/features/jobs/JobActionsMenu.tsx`)
  - Cancel (running/queued) → `cancelRender(jobId)`
  - Retry (can_retry=true) → `retryRender(jobId)`
  - Re-run (can_rerun=true) → `resumeRender(jobId)`
  - Delete (terminal) → `window.confirm()` → `deleteJob(jobId, true)`
  - Details → opens `JobDetailDrawer`
  - Per-job action loading state via `Set<string>`
  - Success/error notifications via `uiStore.addNotification`
- [x] Status badges (`src/features/jobs/JobStatusBadge.tsx`)
  - All 9 status values mapped: completed/partial/running/queued/failed/interrupted/cancelled/canceled/cancelling
- [x] Job detail drawer (`src/features/jobs/JobDetailDrawer.tsx`)
  - Full `JobStatus` loaded via `getJob(jobId)` on open
  - job_id (monospace + copy button), kind badge, status badge, stage, dates, progress bar
  - Payload section (collapsible): source, URL/path, platform, aspect ratio, subtitle style, effect preset
  - Placeholders for live progress, quality report, AI trace (Phase 6.3)
  - Close button
- [x] Supporting components
  - `JobList.tsx` — rendered list with pagination controls
  - `JobListItem.tsx` — card with title, source, badge, progress bar (active jobs), counts, timestamp
  - `JobFilters.tsx` — search input + status dropdown
  - `JobEmptyState.tsx` — "No render jobs yet" + CTA to render panel
  - `JobLoadingState.tsx` — 3-row skeleton placeholder
  - `JobErrorState.tsx` — error message + retry button
- [x] Utility functions (`src/features/jobs/jobs.utils.ts`)
  - `formatRelativeTime`, `formatDateTime`, `isTerminalStatus`, `isActiveStatus`
  - `canCancel`, `canRetry`, `canRerun`, `canDelete`
- [x] Local types (`src/features/jobs/jobs.types.ts`)
  - `StatusFilter`, `JobActionState`
- [x] App.tsx wired: `history: HistoryScreen` replaces placeholder
- [x] Tests: 64 new tests across 4 test files (173 total, all passing)

---

## 11. Phase 6.3 — Quality Panel + Job Detail Intelligence (SHIPPED 2026-05-23)

All items completed:

- [x] Quality feature module (`src/features/quality/`)
  - `QualityPanel.tsx` — main entry point; fetch-on-open, never polled
  - `QualitySummaryCard.tsx` — aggregate score + issue counts row
  - `QualityPartList.tsx` — list of expandable QualityPartCard components
  - `QualityPartCard.tsx` — per-part score badge + on-demand report fetch on expand
  - `QualityTraceRefs.tsx` — AI trace ref pills with friendly labels, no raw event strings
  - `QualityLoadingState.tsx` — 3-row skeleton (compact, drawer-width)
  - `QualityEmptyState.tsx` — shown for 404 / no report
  - `QualityErrorState.tsx` — shown for API errors, has Retry button
  - `QualityPanel.css` — CSS token-based styles for all quality components
  - `quality.types.ts` — QualityLoadState, AI_TRACE_FRIENDLY map
  - `quality.utils.ts` — getFriendlyTraceLabel, getSeverityIcon, formatScore
- [x] qualityStore extended
  - `refreshJobSummary(jobId)` — clears cache + loading guard, re-fetches
  - `refreshPartQuality(jobId, partNo)` — clears cached report + loading guard, re-fetches
- [x] JobDetailDrawer updated
  - Placeholder "coming in Phase 6.3" div replaced with QualityPanel
  - Live progress notice kept as a static text line
  - QualityPanel receives `job.job_id` and `job.status`
- [x] QualityPanel behaviour
  - Does NOT fetch for queued/running status (shows "will be available after render")
  - Fetches once on open (guarded by loading key in store)
  - Refresh button triggers refreshJobSummary
  - Per-part reports fetched on-demand when card is expanded (only if not already cached)
  - 404 errors → QualityEmptyState; other errors → QualityErrorState with retry
- [x] Tests: 38 new tests across 2 test files (211 total, all passing)
  - `tests/quality-utils.test.ts` — 17 pure logic tests
  - `tests/quality-panel.test.tsx` — 21 rendering + behaviour tests

---

## 12. Phase 6.4 — Live Job Progress Panel (SHIPPED 2026-05-23)

All items completed:

- [x] `useRenderSocket` hook extended (backward compatible)
  - Added `jobStatus: string | null` — set from `event.job.status` on terminal events
  - Added `jobMessage: string | null` — captured from `onStageChange(stage, message)` second arg
  - Added `isTerminal: boolean` — derived from `isTerminalStatus(jobStatus ?? '')`
  - Existing callers using `{ stage, progress, isConnected, error }` still work unchanged
- [x] Progress feature module (`src/features/progress/`)
  - `progress.types.ts` — `ConnectionStatus` type + `MAX_LOG_MESSAGES = 5`
  - `progress.utils.ts` — `normalizeProgressPercent`, `getStageLabel`, `getStatusLabel`, `deriveConnectionStatus`, `extractLatestMessage`, `getPartLabel` (all pure functions)
  - `ConnectionStatusBadge.tsx` — connecting/live/reconnecting/disconnected/terminal variants
  - `ProgressStageTimeline.tsx` — 5-stage linear indicator (Queued→Analyzing→Rendering→Finalizing→Complete)
  - `ProgressPartList.tsx` — active parts with per-part progress bars (capped at 5 shown)
  - `ProgressPartItem.tsx` — compact card: part label, status, small progress bar
  - `ProgressMessageLog.tsx` — collapsible log (max 5 entries, toggle at >2)
  - `JobProgressPanel.tsx` — main panel; active vs terminal routing; cancel action with double-click guard
  - `JobProgressPanel.css` — CSS token-based compact styles for 380px drawer
- [x] JobDetailDrawer updated
  - Static "Live progress — available when running" notice replaced with live `JobProgressPanel`
  - `JobProgressPanel` receives `job.job_id`, `job.status`, `job.progress_percent` with `compact` flag
  - `QualityPanel` preserved below the progress panel
- [x] Cancel behavior
  - `window.confirm()` guard before issuing cancel
  - `isCanceling` state guard prevents double-fire
  - Error notification via `uiStore.addNotification` on failure
  - Cancel button visible for `running`/`queued`/`cancelling` statuses only
- [x] No polling — purely event-driven via WebSocket (onProgress, onStageChange, onComplete)
- [x] Tests: 63 new tests across 2 test files (280 total, all passing)
  - `tests/progress-utils.test.ts` — 36 pure logic tests
  - `tests/job-progress-panel.test.tsx` — 27 rendering + behaviour tests

---

## 13. Phase 6.5 — Editor Screen with Preview Video + Trim Controls (SHIPPED 2026-05-23)

All items completed:

- [x] Editor feature module (`src/features/editor/`)
  - `EditorScreen.tsx` — top-level screen; fetches parts, routes to empty/loading/error/preview
  - `VideoPreview.tsx` — native HTML5 `<video controls>` with onDuration/onTimeUpdate/onError callbacks; error overlay on load failure
  - `TrimControls.tsx` — two number inputs (start/end in seconds) with mm:ss labels, trim duration display, inline validation, reset button
  - `EditorMetadataPanel.tsx` — right-rail panel: job ID (monospace + copy), part, status, duration, trim summary, copy media URL, disabled future actions (Phase 6.6+)
  - `EditorEmptyState.tsx` — shown when no job selected; "Go to History" CTA
  - `EditorLoadingState.tsx` — skeleton for parts fetch
  - `EditorErrorState.tsx` — error + optional retry button
  - `EditorScreen.css` — editor layout tokens (flex, rail, video frame)
  - `editor.types.ts` — `EditorMediaInfo` interface
  - `editor.utils.ts` — `buildMediaUrl`, `buildThumbnailUrl`, `formatTime`, `clamp`, `validateTrim` (all pure)
- [x] editorStore (`src/stores/editorStore.ts`)
  - Fields: `selectedJobId`, `selectedPartNo`, `mediaUrl`, `durationSec`, `trimStartSec`, `trimEndSec`, `isDirty`
  - Actions: `openEditor`, `setDuration`, `setTrim`, `resetTrim`, `closeEditor`
  - Trim is UI-only — no backend mutations
- [x] stores/index.ts updated to export `useEditorStore` and `EditorStore`
- [x] api/jobs.ts: added `getJobParts(jobId)` → `GET /api/jobs/{jobId}/parts`
- [x] App.tsx: `editor: EditorScreen` replaces placeholder `EditorPanel`
- [x] JobDetailDrawer updated
  - "Open in Editor" button added between progress and payload sections
  - Enabled for: `completed`, `partial`, `completed_with_errors` statuses
  - Disabled for: `queued`, `running`, `failed`, `interrupted`, `cancelled`, etc.
  - On click: `openEditor(job.job_id, 1)` + `setActivePanel('editor')` — no backend call
- [x] Part selector shown only when job has multiple parts
- [x] Video preview triggers `editorStore.setDuration()` on metadata load
- [x] Tests: 55 new tests across 4 test files (335 total, all passing)
  - `tests/editor-utils.test.ts` — 18 pure logic tests
  - `tests/editor-screen.test.tsx` — 11 rendering + behaviour tests
  - `tests/trim-controls.test.tsx` — 13 trim controls tests
  - `tests/job-detail-open-editor.test.tsx` — 9 open-in-editor integration tests

---

## 14. Phase 6.6 — Frontend Integration Polish + Shell Readiness (SHIPPED 2026-05-23)

All items completed:

- [x] `vite-env.d.ts` added (`/// <reference types="vite/client" />`) — was missing, caused `import.meta.env` TypeScript error
- [x] `BASE_URL` made environment-aware: `import.meta.env.VITE_API_BASE_URL ?? ''`
  - Empty string = same-origin = works in Electron (FastAPI serves at `http://127.0.0.1:8000`)
  - Works with Vite dev proxy (intercepts `/api/*` → `127.0.0.1:8000`)
  - Override via `VITE_API_BASE_URL` env var for custom setups
- [x] WebSocket URL fixed: `computeWsBase()` function handles empty `BASE_URL`
  - When `BASE_URL = ''`: derives from `window.location.origin` → `ws://127.0.0.1:8000`
  - Test/SSR fallback: hardcoded `ws://127.0.0.1:8000`
- [x] `backend/static-new/` confirmed in root `.gitignore` (build artifact not committed)
- [x] `*.tsbuildinfo` added to `frontend/.gitignore`
- [x] Topbar panel title: now shows `PANEL_TITLES[activePanel]` — dynamic per panel
  - `render→"New Render"`, `history→"History"`, `editor→"Editor"`, `settings→"Settings"`
- [x] Sidebar verified: all 4 panels present, correct labels, `aria-current="page"` on active, no stale text
- [x] Notifications: verified fixed-position bottom-right, `z-toast=300` (above all layers)
- [x] `EditorEmptyState`: verified "Go to History" calls `setActivePanel('history')` (correct)
- [x] `HistoryScreen.handleDelete`: verified drawer clears when selected job is deleted (correct)
- [x] Responsive CSS:
  - `RenderForm.css`: `@media (max-width: 1100px)` stacks to 1-column grid
  - `EditorScreen.css`: `@media (max-width: 1100px)` stacks editor layout + full-width rail
  - `HistoryScreen.css`: `@media (max-width: 1100px)` shrinks detail pane to 320px
- [x] Build: `vite build` succeeds; `backend/static-new/index.html` uses `/assets/…` paths
- [x] Electron readiness audit documented in `docs/ui/PHASE_6_6_FRONTEND_READINESS_REPORT.md`
  - Cut-over plan: rename `static-new` → `static-v2`, set `STATIC_UI_VERSION=v2`
  - CSP: not set (Phase 6.7 task)
  - WS compatibility: confirmed (same-origin derivation)
- [x] Tests: 3 new test files added
  - `tests/integration-flow.test.tsx` — E2E flow tests
  - `tests/static-readiness.test.ts` — build artifact + config checks
  - `tests/navigation-polish.test.tsx` — navigation + topbar + notifications tests

---

## 15. Phase 6.7 — Electron Cut-over + Static v2 Activation (SHIPPED 2026-05-23)

All items completed:

- [x] `backend/static-v2/` created from `vite build` output (tracked by git, not gitignored)
- [x] `STATIC_UI_VERSION=v2` activates `backend/static-v2/` via `ui_gate.py` + `main.py`
- [x] `run-desktop-v2.ps1` — launches Electron with `STATIC_UI_VERSION=v2`
- [x] `run-backend-v2.ps1` — launches FastAPI backend with `STATIC_UI_VERSION=v2`
- [x] Electron env passthrough confirmed: `...process.env` in `startBackendWithCommand()` auto-passes `STATIC_UI_VERSION`
- [x] `index.html` verified: uses `/assets/...` absolute paths (correct for FastAPI `/assets` mount)
- [x] SPA routing confirmed: panel-based only, no URL changes, `GET /` is sufficient (no catch-all needed)
- [x] `GET /health` reports `{"status": "ok", "ui_version": "v2"}` when v2 active
- [x] CSP deferred — same-origin local serving, not needed for Phase 6.7
- [x] Backend tests: `test_ui_static_v2_gate.py` — 21 tests, all pass
- [x] Frontend tests: `electron-cutover-readiness.test.ts` — 20 tests, all pass
- [x] Full test suite: 399 frontend tests pass, 49 backend contract tests pass
- [x] Rollback: set `STATIC_UI_VERSION=legacy` or unset; delete `backend/static-v2/` to force legacy

Full report: `docs/ui/PHASE_6_7_ELECTRON_CUTOVER_REPORT.md`

---

## 16. Phase 6.8 Checklist (next steps)

- [ ] Apply Trim — submit trim range to backend for re-render
- [ ] Re-render Selection — re-render a specific clip segment
- [ ] Export Clip — export trimmed clip to output directory
- [ ] Resolve `tsc -b` errors in test files (`api.test.ts`, `vite.config.ts`)
- [ ] CSP header on FastAPI index response (hardening phase)
