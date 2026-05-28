# Frontend Architecture

Source: `frontend/src/`  
Build output: `backend/static-v2/` (served by FastAPI via `ui_gate.py`)  
Stack: React 18, TypeScript, Vite, Zustand

---

## System Diagram

```
Electron shell / Browser
        |
        v
backend/static-v2/index.html   ← built from frontend/src/
        |
        v
App.tsx  (panel router — no React Router, Zustand activePanel)
        |
        +── ClipStudio          ← primary workflow (fullscreen)
        |       |
        |       +── RenderWorkflow   ← 4-step render UI
        |       +── DownloadTab      ← YouTube/platform download
        |       └── HistoryTab       ← job history inline
        |
        +── HistoryScreen        ← full history view (home/library panel)
        |       |
        |       +── JobFilters
        |       +── JobList → JobListItem → JobActionsMenu
        |       └── JobDetailDrawer
        |
        +── DownloaderScreen     ← standalone download panel
        +── StudioScreen         ← source hero → routes to ClipStudio
        +── SettingsScreen
        └── RenderSetupScreen    ← DEPRECATED (local file only)

API layer: frontend/src/api/
  render.ts   → POST /api/render/* (submit, prepare-source, cancel, retry, resume)
  jobs.ts     → GET /api/jobs/* (history, parts, quality, ranking, AI summary)
  client.ts   → base fetch wrapper, ApiError class

State: frontend/src/stores/
  uiStore.ts     → activePanel, notifications, studioStep
  renderStore.ts → activeJobId, submitRender() action

Types: frontend/src/types/api.ts   ← manually maintained (not generated)
Hooks: frontend/src/hooks/useRenderSocket.ts
```

---

## ClipStudio — 4-Step Render Workflow

File: `frontend/src/features/clip-studio/render/RenderWorkflow.tsx` (~2500 lines)  
CSS:  `frontend/src/features/clip-studio/render/RenderWorkflow.css`

### Step 0 — Source

User picks a local video file. File goes through `prepareSource()`:

```
User selects file
      |
      v
prepareSource({ source_mode: 'local', source_video_path: path })
      |
      v
POST /api/render/prepare-source
      |
      v
Backend: validate file → run Whisper-tiny preview → return session_id + duration + title
      |
      v
Frontend: stores session_id, shows video preview + transcript preview
      |
      v
"CONFIGURE →" button enabled
```

**State written**: `preparedSource` (session_id, title, duration, outputDir)

---

### Step 1 — Configure

User sets render options. No API call until "START RENDER".

```
Config sections:
  ├── Quick presets (Shorts / TikTok / Reels)
  ├── Frame: aspect ratio, 60fps toggle
  ├── Duration: min clip, max clip, clip count
  ├── Motion crop toggle
  ├── Visual style: subtitle style, effect preset
  ├── AI tab: AI Director, mode (local/cloud/hybrid), provider, API key
  ├── Subtitles tab: enable, style, highlight word, font size, translate
  ├── Narration tab: voice enable, engine, language, gender
  └── Output tab: output dir, ranking, part order

Transcript preview (load on demand):
  GET /api/render/preview-transcript/{session_id}
```

**Config type**: `RenderConfig` (line 252 in RenderWorkflow.tsx)  
**Default config**: line 378 — all features conservative/off by default

---

### Step 2 — Rendering

"START RENDER" button submits job. WebSocket connects for live progress.

```
handleStartRender()
      |
      v
POST /api/render/process  →  { job_id }
      |
      v
useRenderSocket(job_id)   →  WS /api/jobs/{job_id}/ws
      |
      v
WebSocket emits every 500ms:
  {
    job: { job_id, status, stage, progress_percent, message },
    parts: [{ part_no, status, progress_percent, duration, output_file, ... }],
    summary: { total_parts, completed_parts, failed_parts, active_parts, stuck_parts }
  }
      |
      v
UI renders:
  - Stage progress bar (DOWNLOAD → ANALYZE → TRANSCRIBE → RENDER → DONE)
  - Per-clip cards (rnd-clip-card): status, progress bar, error label
  - Overall completed/failed counters
  - CANCEL RENDER button (POST /api/render/{job_id}/cancel)
```

**Terminal statuses**: `completed`, `completed_with_errors`, `failed`, `interrupted`, `cancelled`  
On terminal: WebSocket closes; "VIEW RESULTS →" button appears.

---

### Step 3 — Results

Job complete. Results loaded from API.

```
On mount (job_id available):
  getJobParts(job_id)          → parts[]  (status, scores, output_file)
  getJobQualitySummary(job_id) → QualityReport
  getJobRanking(job_id)        → PartRankResult[]
  getJobAiSummary(job_id)      → JobAiSummary

UI renders:
  - Hero banner: job title, total duration, score badge
  - Clip card row (horizontal scroll): clip-card2
      ├── Thumbnail (9:16 or configured ratio)
      ├── Rank badge (#1, ★ BEST)
      ├── AI score badge (colored by tier)
      ├── Duration badge
      ├── Info section: clip number, AI tier label, score bar, ranking reason
      ├── Dominant signal / suppressed signals
      └── Action buttons: SAVE (download), ⋯ (delete/open)
  - Player panel (right): video playback + quality detail + AI signals
  - Failed clips section (if any)
  - NEW RENDER + button
```

**Clip score tiers**: `VIRAL (≥70)`, `GOOD (≥50)`, `WEAK (<50)`  
**Best clip**: `is_best_clip === true` → gold gradient rank badge + `is-top` CSS class

---

## History Screen

File: `frontend/src/features/jobs/HistoryScreen.tsx`

```
HistoryScreen
  ├── Header: job counts, refresh button, active badge
  ├── JobFilters: text search, status filter (all/running/completed/failed/cancelled)
  ├── JobList: paginated (20/page), grouped by date
  │     └── JobListItem: status bar, title, time, clip count, error count, progress bar (active only)
  │           └── JobActionsMenu: cancel / retry / re-run / delete (context-sensitive)
  └── JobDetailDrawer: full job detail (right pane when item selected)
```

**Auto-refresh**: every 5s if any item has active status.  
**Pagination**: `GET /api/jobs/history?limit=20&offset=N`  
**Status filter mapping**:
- `running` → `isActiveStatus()` (queued, running, cancelling)
- `completed` → status === 'completed' || 'partial'
- `failed` → status === 'failed'
- `cancelled` → status === 'cancelled' || 'interrupted'

---

## API Client

### render.ts

| Function | Endpoint | Notes |
|---|---|---|
| `prepareSource(body, signal?)` | `POST /api/render/prepare-source` | Returns `PrepareSourceResponse`: session_id, title, duration, export_dir |
| `cancelPrepareSource(session_id)` | `DELETE /api/render/prepare-source/{id}` | Cancel ongoing YouTube download |
| `getPreviewVideoUrl(session_id)` | — | Returns URL string (no fetch) |
| `getPreviewTranscript(session_id)` | `GET /api/render/preview-transcript/{id}` | Returns `TranscriptSegment[]` |
| `cancelRender(job_id)` | `POST /api/render/{id}/cancel` | |
| `retryRender(job_id)` | `POST /api/render/retry/{id}` | Retry failed parts only |
| `resumeRender(job_id)` | `POST /api/render/resume/{id}` | Resume from interruption |

### jobs.ts

| Function | Endpoint | Notes |
|---|---|---|
| `getJobHistory(limit, offset)` | `GET /api/jobs/history` | Returns `{ items, has_more }` |
| `getJob(job_id)` | `GET /api/jobs/{id}` | Single job status |
| `getJobParts(job_id)` | `GET /api/jobs/{id}/parts` | All parts |
| `getJobQualitySummary(job_id)` | `GET /api/jobs/{id}/quality` | Aggregated quality |
| `getJobRanking(job_id)` | `GET /api/jobs/{id}/ranking` | Per-part ranking |
| `getJobAiSummary(job_id)` | `GET /api/jobs/{id}/ai-summary` | AI Director plan summary |
| `deleteJob(job_id, delete_files)` | `DELETE /api/jobs/{id}` | |
| `deletePartOutput(job_id, part_no)` | `DELETE /api/jobs/{id}/parts/{no}/output` | Delete single clip |

---

## useRenderSocket Hook

File: `frontend/src/hooks/useRenderSocket.ts`

```typescript
useRenderSocket(jobId: string | null) → {
  stage: string
  jobStatus: string | null     // set only on terminal event
  progress: WsProgressSummary
  liveParts: JobPart[]
  wsError: string | null
  isConnected: boolean
  isTerminal: boolean          // derived from jobStatus
  errorKind: JobErrorKind | null
}
```

**Reconnect strategy**: up to 3 attempts, exponential backoff (2s, 4s, 8s).  
**No reconnect after**: terminal status received.  
**Known issue**: No heartbeat — silent network drop triggers false disconnect + reconnect.

---

## Stores

### uiStore (`frontend/src/stores/uiStore.ts`)

```typescript
{
  activePanel: PanelKey           // current screen
  notifications: Notification[]   // toast queue
  addNotification(n)              // push toast
  removeNotification(id)
  setActivePanel(panel)
}
```

### renderStore (`frontend/src/stores/renderStore.ts`)

```typescript
{
  activeJobId: string | null
  submitRender(payload: RenderRequest): Promise<string>  // returns job_id
}
```

**Known debt**: `renderStore` is write-only. It stores `activeJobId` on submit but never updates job state from WebSocket. All live state flows through `useRenderSocket` hook, not the store. Any component that reads job data from the store after submission sees the initial stub only.

---

## Types

File: `frontend/src/types/api.ts`

**Manually maintained** — not generated from backend OpenAPI schema. Any field added/renamed in backend `schemas.py` must be manually synced here.

### Key types

| Type | Purpose |
|---|---|
| `RenderRequest` | Full payload for POST /api/render/process (100+ fields) |
| `HistoryItem` | Row in job history list |
| `JobPart` | Per-clip state (status, scores, output_file) |
| `WsProgressSummary` | Summary block in WebSocket event |
| `QualityReport` | Aggregated quality from /quality endpoint |
| `PartRankResult` | Per-clip ranking with is_best_clip, output_rank_score |
| `JobAiSummary` | AI Director plan summary |
| `JobErrorKind` | Error classification enum (string literal union) |

### JobErrorKind values

```typescript
'DOWNLOAD_FAILED' | 'WHISPER_FAILED' | 'SOURCE_NOT_FOUND' |
'FFMPEG_FAILED' | 'QA_FAILED' | 'VOICE_FAILED' | 'CANCELLED' | 'RENDER_FAILED'
```

**Risk**: Backend generates this as a plain string via substring matching. Type mismatch causes TypeScript assumption violations at runtime if backend string changes.

---

## End-to-End Data Flow

```
User clicks START RENDER
        |
        v
handleStartRender() builds RenderRequest from cfg + preparedSource
  {
    source_mode: 'local',
    source_video_path: src.value,
    session_id: preparedSource.session_id,
    output_dir: cfg.outputDir,
    ai_director_enabled: cfg.aiEnabled,
    ai_analysis_mode: cfg.aiAnalysisMode,         // 'local' | 'cloud' | 'hybrid'
    ai_cloud_enabled: !!cfg.aiCloudApiKey,
    ai_cloud_provider: cfg.aiCloudProvider,
    ai_cloud_api_key: cfg.aiCloudApiKey || undefined,
    ... (40+ other fields)
  }
        |
        v
POST /api/render/process
        |
        v
Backend: _validate_render_request() → upsert_job() → submit_job() → queue
        |
        v
Response: { job_id, status: 'queued' }
        |
        v
Frontend: setStep(2), connect useRenderSocket(job_id)
        |
        v
WS /api/jobs/{job_id}/ws  →  events every 500ms
        |
        v
liveParts, progress, stage update component state
        |
        v
On terminal status: setStep(3)
        |
        v
Step 3 mounts → parallel API calls:
  getJobParts() + getJobQualitySummary() + getJobRanking() + getJobAiSummary()
        |
        v
Results rendered in clip-card2 grid
```

---

## Known Issues (Active Debt)

| Issue | Location | Severity |
|-------|----------|----------|
| renderStore never updated from WS | `stores/renderStore.ts` | HIGH |
| RenderWorkflow.tsx ~2500 lines | `features/clip-studio/render/RenderWorkflow.tsx` | MEDIUM |
| Types not generated from OpenAPI | `types/api.ts` | MEDIUM |
| No navigation guards mid-render | `App.tsx` | MEDIUM |
| useRenderSocket re-renders every 500ms | `hooks/useRenderSocket.ts` | MEDIUM |
| No WS heartbeat — false disconnect risk | `hooks/useRenderSocket.ts` | LOW |
| RenderSetupScreen deprecated but still mounted | `App.tsx:37` | LOW |

---

## Build & Serve

```powershell
# Build React → backend/static-new/ (NOT the served path)
cd frontend && npm run build

# The served path is backend/static-v2/
# To update served UI: copy build output to static-v2/ manually
# OR: update vite.config.ts outDir to backend/static-v2/
```

**Known gap**: `vite.config.ts` builds to `backend/static-new/` but `ui_gate.py` serves from `backend/static-v2/`. Running `npm run build` does NOT update the live UI. This is a known issue (CLAUDE.md Issue 1).
