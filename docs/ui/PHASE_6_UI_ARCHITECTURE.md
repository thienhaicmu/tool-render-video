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

## 10. Phase 6.2 Checklist (next steps)

- [ ] History screen (`src/features/jobs/HistoryScreen.tsx`)
  - Paginated list using `/api/jobs/history`
  - Status badges, retry/rerun/cancel actions
- [ ] Job progress panel (`src/features/render/JobProgress.tsx`)
  - Live WebSocket via useRenderSocket hook
  - ProgressBar component for overall %
  - Stage display + Cancel button
- [ ] Quality panel on job detail (on-demand, not polled)
- [ ] Editor screen with preview video and trim controls
