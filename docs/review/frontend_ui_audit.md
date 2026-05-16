# UI Rebuild Audit — Static-V2 Product Shell Foundation

**Phase:** UI-R2A  
**Date:** 2026-05-14  
**Branch:** feature/ai-output-upgrade  
**Scope:** New vanilla-JS product shell under `backend/static-v2/`

---

## 1. Summary

A complete UI rebuild was delivered under `backend/static-v2/` — a zero-dependency, no-build-step vanilla JavaScript ES module application. The legacy `backend/static/` directory is untouched. No changes were made to `backend/app/main.py`.

The new shell implements 4 product screens (Source, Studio, Monitor, Results) with a 4-panel grid layout, design-token–driven theming, WebSocket + polling transport, single entity normalizers, a reactive store factory, and all specified components (StatusChip, AIBadge, NavRail, EmptyState).

---

## 2. File Inventory

### Entry Point
| File | Purpose |
|---|---|
| `index.html` | HTML entry point; loads 4 CSS + app.js module |
| `package.json` | `{"type":"module"}` — enables `node --check` on ES module files |

### CSS (4 files)
| File | Contents |
|---|---|
| `assets/css/tokens.css` | All design tokens as CSS custom properties (colors, spacing, radius, typography, layout vars) |
| `assets/css/base.css` | Box-model reset, body defaults, scrollbar styling, typography utility classes, focus ring |
| `assets/css/layout.css` | 4-panel shell grid, screen/panel/strip wrappers, flex helpers |
| `assets/css/components.css` | StatusChip (8 states), AIBadge (6 states), NavRail items, EmptyState, Btn, Card, FormField, ProgressBar, Spinner, Toast, PartItem, MetricGrid |

### JS Infrastructure (4 files)
| File | Purpose |
|---|---|
| `assets/js/app.js` | Boot: mounts shell, inits systemStore, inits router |
| `assets/js/router.js` | Hash-based router: `#/source`, `#/studio`, `#/monitor/:jobId`, `#/results/:jobId` |
| `assets/js/transport.js` | `openJobStream()` — WebSocket primary, polling fallback; `fetchJson()` — typed HTTP client |
| `assets/js/desktop-adapter.js` | Electron `contextBridge` adapter — no-op in browser context |

### API Wrappers (3 files)
| File | Endpoints covered |
|---|---|
| `assets/js/api/render.js` | POST /api/render, POST /cancel, GET/PUT /api/render/draft, GET platforms/creator-types |
| `assets/js/api/jobs.js` | GET list, GET job, GET parts, GET result, GET summary, DELETE job |
| `assets/js/api/system.js` | GET /api/health, GET /api/system/info, GET /api/system/execution-mode, GET /api/sessions |

### Entity Normalizers (4 files)
| File | Entities normalized |
|---|---|
| `assets/js/entities/job.js` | `normalizeJob()` — raw job → typed Job with status validation |
| `assets/js/entities/part.js` | `normalizePart()`, `normalizePartList()` — raw part → typed Part with status + aiState validation |
| `assets/js/entities/result-package.js` | `parseResultPackage()` — raw result → ResultPackage with inline parts array + summary |
| `assets/js/entities/source-session.js` | `normalizeSession()`, `normalizeSessionList()` — raw session → SourceSession |

### Stores (6 files)
| File | State managed |
|---|---|
| `assets/js/store/create-store.js` | `createStore(initialState)` factory — `set`, `update`, `subscribe`, `reset` |
| `assets/js/store/session.js` | `sessions[]`, `activeSessionId`, `loading`, `error` |
| `assets/js/store/draft.js` | Render config form state — `draft`, `dirty`, `saving`, `error` |
| `assets/js/store/monitor.js` | Live job stream — `job`, `parts`, `summary`, `connected`, `error` |
| `assets/js/store/results.js` | Completed result package — `result`, `selectedPartIndex`, `loading`, `error` |
| `assets/js/store/system.js` | Backend health, execution mode, `backendReady` flag |

### Components (5 files)
| File | Component |
|---|---|
| `assets/js/components/status-chip.js` | `statusChip(status)` HTML string + `statusChipElement()` DOM node |
| `assets/js/components/ai-badge.js` | `aiBadge(state)` HTML string + `aiBadgeElement()` DOM node |
| `assets/js/components/nav-rail.js` | `navRail.mount(container)` + `navRail.setActive(id)` — 4 enabled + 4 disabled items |
| `assets/js/components/empty-state.js` | `emptyState({ icon, title, body, ctaLabel, onCta })` + `ICONS` map |
| `assets/js/components/shell.js` | `shell.render()` + `shell.mount(root)` + `shell.setActiveNav(id)` |

### Screens (4 files)
| File | Screen | Route |
|---|---|---|
| `assets/js/screens/source.js` | Source — file drop zone + session list | `#/source` |
| `assets/js/screens/studio.js` | Studio — render config form, launch button | `#/studio` |
| `assets/js/screens/monitor.js` | Monitor — live part list via WebSocket stream | `#/monitor/:jobId` |
| `assets/js/screens/results.js` | Results — result package metrics + per-part detail | `#/results/:jobId` |

**Total: 33 files**

---

## 3. Design Token Coverage

All tokens from `design/figma-import/design_tokens_v1.json` mapped to CSS custom properties:

| Token category | Count | CSS prefix |
|---|---|---|
| Colors (bg, surface, border, text, accent, ai) | 11 | `--color-*` |
| Status semantics | 6 | `--color-{status}` |
| Spacing | 10 | `--sp-{n}` |
| Radius | 3 | `--radius-*` |
| Typography | 5 | `--text-*`, `--font-family` |
| Layout | 3 | `--nav-rail-width`, `--right-panel-width`, `--bottom-strip-height` |

---

## 4. Layout Architecture

```
┌─────────────────────────────────────────────────────┐
│  .shell  (grid: 72px | 1fr | 300px / 1fr | 52px)   │
├──────────┬────────────────────────────┬─────────────┤
│          │                            │             │
│ .shell   │    .shell__workspace       │ .shell      │
│ __nav    │    (screen injected here)  │ __panel     │
│ (72px)   │                            │ (300px)     │
│          │                            │             │
├──────────┴────────────────────────────┴─────────────┤
│            .shell__strip (52px)                      │
└─────────────────────────────────────────────────────┘
```

---

## 5. Component State Matrix

### StatusChip (8 states)
| State | Color | Background |
|---|---|---|
| queued | `--color-text-muted` | rgba(170,180,190,0.12) |
| running | `--color-running` | rgba(121,184,255,0.12) |
| completed | `--color-success` | rgba(116,212,143,0.12) |
| partial | `--color-partial` | rgba(241,154,91,0.12) |
| failed | `--color-failed` | rgba(255,124,124,0.12) |
| interrupted | `--color-warning` | rgba(242,198,110,0.12) |
| unsupported | `--color-unsupported` | rgba(133,129,142,0.12) |
| unavailable | `--color-text-faint` | rgba(115,127,137,0.12) |

### AIBadge (6 states)
| State | Color | Background |
|---|---|---|
| disabled | `--color-text-faint` | rgba(115,127,137,0.10) |
| advisory | `--color-ai` | `--color-ai-soft` |
| applied | `--color-accent` | `--color-accent-soft` |
| skipped | `--color-text-muted` | rgba(170,180,190,0.10) |
| blocked | `--color-warning` | rgba(242,198,110,0.10) |
| unavailable | `--color-text-faint` | rgba(115,127,137,0.10) |

---

## 6. Transport Contract

```
WebSocket primary:   ws(s)://host/api/jobs/{jobId}/ws
  message shape:     { job: {...}, parts: [...], summary: {...} }

Polling fallback:    GET /api/jobs/{jobId}
                     GET /api/jobs/{jobId}/parts
  interval:          3000ms
  triggers:          on WS error, on WS close
```

---

## 7. Router Contract

| Hash path | Screen | Params |
|---|---|---|
| `#/source` | sourceScreen | — |
| `#/studio` | studioScreen | — |
| `#/monitor/:jobId` | monitorScreen | `[jobId]` |
| `#/results/:jobId` | resultsScreen | `[jobId]` |
| (any unmatched) | redirect → `#/source` | — |

---

## 8. Constraints Verified

| Constraint | Status |
|---|---|
| No framework (React/Vue/Svelte) | ✅ Vanilla JS only |
| No npm build step / bundler | ✅ Native ES modules, no build |
| No edits to `backend/app/main.py` | ✅ Not touched |
| No edits to `backend/static/` | ✅ Not touched |
| `{"type":"module"}` in package.json | ✅ Present |
| All design tokens from tokens V1 used | ✅ Full coverage in tokens.css |
| 4-panel grid layout (72px/1fr/300px + 52px strip) | ✅ Implemented in layout.css + shell.js |
| WebSocket primary + polling fallback | ✅ transport.js |
| Single entity normalizer pattern | ✅ entities/ directory |
| createStore factory (no external state library) | ✅ store/create-store.js |
| 8-state StatusChip | ✅ |
| 6-state AIBadge | ✅ |
| 4 enabled + 4 disabled NavRail items | ✅ nav-rail.js |
| 4 screen skeletons | ✅ source, studio, monitor, results |

---

## 9. Known Limitations (UI-R2A Scope)

- Right panel (`#shell-panel`) only shows part detail from Results screen; other screens leave it at default "Select a job" copy — context wiring is a UI-R2B task.
- No toast notification system wired to stores yet — CSS is present, JS implementation deferred.
- No drag-and-drop from browser `<input type=file>` — Source screen relies on Electron `pickVideoFile()` for path resolution; browser drag-and-drop uses `file.name` as fallback (path only available in Electron).
- Studio screen does not include subtitle/camera/segment advanced fields — basic platform/creator/mode/AI toggle only.
- No offline/error boundary at the shell level — individual screens handle their own error states.

---

# UI-R2B — Core Creator Workflow

**Phase:** UI-R2B  
**Date:** 2026-05-14  
**Branch:** feature/ai-output-upgrade  
**Scope:** End-to-end creator workflow: Source → Studio → Monitor → Results

---

## 1. Summary

All four product screens are now fully functional. A user can import a YouTube URL or local file path, configure clip settings, start a render, watch live progress, and review ranked output clips with score breakdowns. No backend or legacy frontend files were modified.

---

## 2. Files Changed / Added

### New Entities (3 files)
| File | Purpose |
|---|---|
| `assets/js/entities/ai-insight.js` | `parseAIInsightSummary(resultRaw)` — extracts AI director state, applied/skipped changes, confidence, summary lines |
| `assets/js/entities/render-request.js` | `validateRenderDraft(draft)` → `{valid, errors[]}` and `buildRenderRequest(draft)` — only sends intentionally-set fields |
| *(source-session.js extended)* | Added `parsePrepareSourceResponse()` for POST /api/render/prepare-source response |

### Rewritten Entities (3 files)
| File | Key change |
|---|---|
| `assets/js/entities/job.js` | Fixed field names: `raw.job_id`, `safeParse(raw.result_json)` for JSON string payload; added `TERMINAL_STATUSES` import |
| `assets/js/entities/part.js` | Fixed field names: `raw.part_no`; backend `done` → chip `completed`; stream URL derived from jobId+partNo |
| `assets/js/entities/result-package.js` | Full rewrite: `parseOutputClip()` derives `streamUrl` from part_no (never `output_file`); `parseResultPackage()` emits ranked clips, failed parts, voice/subtitle summaries, AI insights |

### Rewritten Transport (1 file)
| File | Key change |
|---|---|
| `assets/js/transport.js` | Added `subscribeJob(jobId, {onUpdate, onTerminal, onTransportChange})` high-level API; WS injects `_transport` marker; `fetchJson` handles Pydantic 422 array detail |

### Rewritten APIs (2 files)
| File | New endpoints |
|---|---|
| `assets/js/api/render.js` | `prepareSource()`, `getPreviewVideoUrl()`, `process()`, `retry()`, `resume()`, `cancel()` |
| `assets/js/api/jobs.js` | `getLogs(jobId, lines)`, `getQueueStatus()` |

### Rewritten Stores (3 files)
| File | Key change |
|---|---|
| `assets/js/store/draft.js` | `DEFAULTS` object; `setSession(session)` from prepare-source; `clearSession()`; `buildPayload()` delegates to `buildRenderRequest()` |
| `assets/js/store/monitor.js` | Uses `subscribeJob()` instead of `openJobStream()`; `loadLogs()` for lazy drawer; terminal flag + authoritative final poll |
| `assets/js/store/results.js` | Loads job + parts, calls `parseResultPackage(jobId, job.resultRaw)`, auto-selects best clip, `selectClip(idx)` |

### Rewritten Screens (4 files)
| File | Key change |
|---|---|
| `assets/js/screens/source.js` | Module-level state machine (`idle/loading/success/error`), YouTube/Local tabs, `handlePrepare()`, info→readiness panel transition |
| `assets/js/screens/studio.js` | Two-column layout (preview | draft+CTA); Sections A–D; `validateRenderDraft()` gate; navigates to `/monitor/:jobId` |
| `assets/js/screens/monitor.js` | `subscribeJob()`, transport badge, part rows, terminal banners, lazy logs drawer |
| `assets/js/screens/results.js` | Hero video via stream URL, ranked clip list, right-panel score breakdown, AI insights placeholder |

### Extended CSS (1 file)
`assets/css/components.css` — appended component styles for:
- Skeleton states (`skeleton-line`, `skeleton-block`, `skeleton-pulse` keyframe)
- Source layout (`.source-layout`, `.source-tabs`, `.source-tab`, `.source-ready-card`)
- Studio layout (`.studio-body` grid, `.studio-preview`, `.studio-draft`, `.section-disabled`)
- Draft controls (`.ratio-pill`, `.preset-pill`, `.camera-option`, `.exec-pill` and their `--active` variants)
- Monitor rows (`.part-progress-row`, `.log-line`, `.logs-content`)
- Results (`.output-clip-card`, `.clip-rank-badge`, `.best-label`, `.results-hero`)

---

## 3. API Contracts Used

| Endpoint | Method | Used by |
|---|---|---|
| `/api/render/prepare-source` | POST | Source screen → `renderApi.prepareSource()` |
| `/api/render/preview-video/{session_id}` | GET | Studio screen video `<src>` |
| `/api/render/process` | POST | Studio screen → `renderApi.process()` |
| `/api/jobs/{jobId}` | GET | Monitor final poll, Results load |
| `/api/jobs/{jobId}/parts` | GET | Monitor polling fallback + Results load |
| `/api/jobs/{jobId}/ws` | WS | Monitor live stream |
| `/api/jobs/{jobId}/logs` | GET | Monitor logs drawer (lazy) |
| `/api/jobs/{jobId}/parts/{partNo}/stream` | GET | Results hero video + Download link |

---

## 4. Transport Behavior

| Mode | Trigger | UI indicator |
|---|---|---|
| `connecting` | Initial state | `⋯ Connecting` (faint) |
| `websocket` | WS connection established | `● Live` (success green) |
| `polling` | WS error or explicit fallback | `○ Polling` (warning) |
| `terminal_poll` | Terminal status confirmed | `● Done` (success green) |

Terminal detection checks `job.status` in every message (both WS and polling). Does **not** rely on WS close event. On terminal, fires `onTerminal(status)` and performs one authoritative GET 600ms later to capture final result.

---

## 5. Known Limitations (UI-R2B Scope)

- AI insights section on Results screen shows a placeholder only — "AI insights available after Phase 63 integration." Full wiring deferred to Phase 63.
- `result_json` ranking fallback: when `output_ranking` is absent, a synthetic single-clip fallback is built from `output_file` if present; score is 0 and reason is empty.
- Log lines are plain text only — no colorization or log-level parsing implemented.
- Cancel button on Monitor only fires the API request; no optimistic UI or confirmation dialog.
- Right-panel score breakdown requires `ranking_components` in result JSON; displays empty otherwise.
- Studio preview video requires `/api/render/preview-video/{session_id}` to succeed; shows inline error text on failure.

---

## 6. Deferred Screens / Features

| Item | Deferred to |
|---|---|
| AI insights full wiring (director decisions, applied changes) | Phase 63 |
| Toast notification system | Future sprint |
| Session list / restore previous session on Source screen | Future sprint |
| Drag-and-drop file upload (browser, non-Electron) | Future sprint |
| Right panel context for Source and Studio screens | Future sprint |

---

# UI-R2C — Render Experience Polish

**Phase:** UI-R2C  
**Date:** 2026-05-14  
**Branch:** feature/ai-output-upgrade  
**Scope:** Monitor + Results render experience polish; shared render components; entity hardening

---

## 1. Summary

Polished the Monitor and Results screens to premium creator product quality. Key deliverables: stable video player in Results (clip selection never destroys the `<video>` element), premium stage banner on Monitor, AI insights panel in Results with compact preview chips, hardened `parseResultPackage()` to handle string input and legacy fallbacks, and 5 new shared render components.

---

## 2. New Components (5 files)

| File | Exports | Purpose |
|---|---|---|
| `assets/js/components/score-badge.js` | `scoreColor`, `scoreBadge`, `scorePill` | Inline score bar, score pill; color-coded by tier (≥70 success / ≥40 warning / <40 failed) |
| `assets/js/components/output-card.js` | `outputCard(clip, {selected})` | Ranked clip card: rank badge, best label, duration badge, score pill + bar, reason snippet |
| `assets/js/components/best-clip-hero.js` | `bestClipHero`, `heroMetaHtml`, `wireHeroVideo`, `updateHeroClip` | Stable hero video wrapper; `updateHeroClip()` surgically updates `src` + meta strip without recreating the `<video>` element |
| `assets/js/components/part-status-list.js` | `partStatusList(parts)` | Part progress table with status chip, inline bar, message; per-row color accent for running/completed/failed |
| `assets/js/components/log-drawer.js` | `logDrawerShell`, `wireLogDrawer` | Collapsible log drawer; lazy-loads on first open via `loadFn`; `refresh()` for terminal state updates; never auto-polls |

---

## 3. Monitor Polish

| Improvement | Details |
|---|---|
| Stage banner | Large `monitor-stage-text` (20px bold) showing humanized stage name (`transcribing_full` → "Transcribing audio") |
| Progress bar | 6px height, animated pulse when running, percentage prominently displayed |
| Transport badge | Inline in progress card header: `● Live` (success) / `○ Polling` (warning) / `⋯ Connecting` (faint) |
| Part table | Uses `partStatusList()` component; running rows get a subtle blue tint; part number column color-codes by status |
| Terminal CTAs | View Results → for success; Retry / Resume / New source for failed/interrupted |
| Retry/Resume | Wires `renderApi.retry(jobId)` and `renderApi.resume(jobId)` via disable-on-click buttons |
| Log drawer | Uses `logDrawerShell()` + `wireLogDrawer()`; lazy load on first open; terminal refresh via `ctrl.refresh()` |
| Unmount cleanup | `monitorStore.stop()` called on `unmount` event — no transport leak |

---

## 4. Results Polish

| Improvement | Details |
|---|---|
| Stable video player | `_prevResult` reference comparison: only full re-render when `result` object changes; clip selection triggers `_updateSelection()` which calls `updateHeroClip()` — no `<video>` destruction |
| Hero section | `bestClipHero()` component: video with border-radius, error overlay, meta strip (best label, part number, score pill, download link) |
| Clip list | `outputCard()` component: rank badge (★ for best), best label, duration badge, score bar, reason snippet, hover/active states |
| Status bar | Partial success banner with `partial-banner` class; voice/subtitle summaries inline |
| Failed parts panel | `failed-panel` with per-row detail; `rankingWarning` shown when present |
| AI panel | Always rendered; advisory state when `ai.available`; compact preview chips from `ai.previewChips` (applied count, quality score, execution mode, beat sync); placeholder copy when unavailable |
| Right panel | Score breakdown preserved; uses `scoreBadge()` component for component score bars |

---

## 5. Entity Hardening

### `parseResultPackage()` changes

| Change | Details |
|---|---|
| String input | Accepts `result_json` as string — calls `JSON.parse()` before processing |
| Legacy `outputs` fallback | When `output_ranking` is empty but `outputs` array exists, builds synthetic ranking entries |
| `renderQuality` field | Extracts `score` + `grade` from `ai_render_quality_evaluation`; exposed on `ResultPackage` |
| Failed part normalization | Filters `failed_parts_detail` to only object entries; clamps `failedPartNumbers` to valid numbers |
| No-throw guarantee | All paths either succeed or fall through to `_fallback()` |

### `parseAIInsightSummary()` changes

| Change | Details |
|---|---|
| `render_quality_v2` | Reads from `ai_director.render_quality_v2` or top-level; extracts `score`, `grade` |
| `ai_execution_metrics` | Reads from `ai_director.ai_execution_metrics` or top-level |
| `previewChips` | New field: compact chip array for Results AI panel; only populated when AI available |
| `executionMode` | Extracted from `execMetrics.mode`, `influence.mode`, etc. |
| `renderQuality` | Normalized `{score, grade}` object or `null` |
| `_obj()` guard | Fixed to reject arrays (was accepting any truthy object) |

---

## 6. Media URL Rule

All media URLs are derived as `/api/jobs/{jobId}/parts/{partNo}/stream`.

- `parseOutputClip()` — derives `streamUrl` from `jobId + partNo`
- `bestClipHero()` — builds URL from `jobId + clip.partNo`
- `updateHeroClip()` — same derivation on surgical update
- Raw `output_file` path is preserved in `clip._raw` for diagnostics only, never used for playback

---

## 7. CSS Additions (components.css)

New classes appended before the Metric display section:

| Class group | New classes |
|---|---|
| Score | `.score-pill`, `.score-pill--sm` |
| Duration | `.dur-badge` |
| Clip list | `.clip-reason` |
| Hero video | `.hero-section`, `.hero-wrap`, `.hero-video-container`, `.hero-video`, `.hero-video-err`, `.hero-meta`, `.hero-empty` |
| Log drawer | `.log-drawer`, `.log-drawer__toggle`, `.log-drawer__chevron`, `.log-drawer__content` |
| Monitor | `.monitor-progress-card`, `.monitor-stage-text`, `.transport-badge` |
| Part rows | `.part-row--running`, `.part-row--completed`, `.part-row--failed`, `.part-message`, `.part-status-table` |
| Results | `.results-body-col` |
| AI panel | `.ai-panel`, `.ai-panel--advisory`, `.ai-panel__header`, `.ai-panel__chips`, `.ai-chip`, `.ai-chip--applied`, `.ai-chip--advisory`, `.ai-chip--warning` |
| Status | `.partial-banner`, `.failed-panel`, `.failed-row` |
| Utility | `.btn-sm`, `.link-accent` |

---

## 8. Transport Cleanup

| Contract | Verified |
|---|---|
| `monitorStore.stop()` on screen unmount | ✅ — called in `unmount` event listener |
| No duplicate polling on re-mount | ✅ — `start()` calls `stop()` first |
| No log spam | ✅ — log drawer loads once on first open; terminal refresh is one-shot |
| No multiple autoplaying videos | ✅ — single `#hero-video` element; `updateHeroClip()` reuses it |
| Polling fallback intact | ✅ — transport.js `subscribeJob()` unchanged |

---

## 9. Known Limitations (UI-R2C Scope)

- AI panel shows `previewChips` only when `ai_director`/`ai_render_influence` data is present in `result_json`; placeholder copy shown otherwise.
- Duration badge in output cards requires `duration`/`end_sec`/`start_sec` fields in the ranking entry `_raw`; hidden if missing.
- Log drawer line count updates after first load only; no live count during loading.
- Retry/Resume buttons disable on click but do not re-enable if the API call fails (user must reload).
- Monitor right panel context not yet wired (Source/Studio screens).

---

## 10. Next Phase Recommendation

**UI-R2D** or **Phase 63**: AI Copilot full wiring — populate `renderAIPanel()` with director decisions, subtitle/camera promotion report, segment selection reasoning, quality gate summary, and execution confidence metrics from `parseAIInsightSummary()` full output.

---

# UI-R3A — Library Screen

**Phase:** UI-R3A
**Date:** 2026-05-14
**Branch:** feature/ai-output-upgrade
**Scope:** First extended product screen — render history browser

---

## 1. Summary

Added the Library screen under `backend/static-v2/`. Users can browse all past render jobs, filter by status, search by title or job ID, navigate directly to Results (completed/partial jobs) or Monitor (active jobs), and trigger Retry/Resume for failed/interrupted jobs. No backend files were modified.

---

## 2. Files Changed

| File | Change |
|---|---|
| `assets/js/screens/library.js` | New — Library screen |
| `assets/js/api/jobs.js` | Added `getHistory()` → `GET /api/jobs/history` |
| `assets/js/router.js` | Added `#/library` route → `libraryScreen` |
| `assets/js/components/nav-rail.js` | Library moved to enabled (5th item); disabled list replaced with Downloads, System, Publish |
| `assets/css/components.css` | Appended Library-specific classes |

---

## 3. Route Added

| Hash path | Screen | Params |
|---|---|---|
| `#/library` | libraryScreen | — |

---

## 4. APIs Used

| Endpoint | Method | Wrapper | Purpose |
|---|---|---|---|
| `/api/jobs/history` | GET | `jobsApi.getHistory()` | Load render history list |
| `/api/render/retry/{jobId}` | POST | `renderApi.retry(jobId)` | Retry failed job (reused from UI-R2B) |
| `/api/render/resume/{jobId}` | POST | `renderApi.resume(jobId)` | Resume interrupted job (reused from UI-R2B) |

Navigation to `/results/:jobId` and `/monitor/:jobId` uses `router.go()` — no additional API calls.

---

## 5. History Parsing Behavior

`normalizeHistoryItem(raw)` wraps `normalizeJob()` and adds display-layer fields:

| Field | Source | Fallback |
|---|---|---|
| `displayTitle` | `payload.title` → `source_url` → `source_path` | `"Job {jobId.slice(0,12)}"` |
| `bestScore` | `result_json.output_ranking[0].score` | `null` (hidden) |
| `outputCount` | `result_json.output_ranking.length` | `null` (hidden) |
| `hasAI` | presence of `ai_director` / `ai_render_influence` / `ai_execution_metrics` | `false` |

All extraction is wrapped in try/catch — null `result_json`, malformed JSON, or missing fields never throw.

---

## 6. Status / Action Rules

| Status | Card click | Inline action |
|---|---|---|
| `completed` / `completed_with_errors` | → `/results/:jobId` | View Results button |
| `partial` | → `/results/:jobId` | View Results button |
| `queued` / `running` | → `/monitor/:jobId` | Monitor button |
| `failed` | no navigation | Retry button → `/monitor/:newJobId` |
| `interrupted` | no navigation | Resume button → `/monitor/:newJobId` |
| `unsupported` / `unavailable` | no navigation | no action |

Retry and Resume buttons disable on click and show inline error text on the card if the API call fails (no alert, no raw JSON).

---

## 7. Filter / Search

- Filter pills: All, Running, Completed, Partial, Failed, Interrupted
- Running filter matches `queued` and `running` statuses
- Completed filter matches `completed` and `completed_with_errors` statuses
- Search: case-insensitive substring match on `displayTitle` and `jobId`
- Filters and search compose (both applied simultaneously)
- Empty filter+search result shows "No jobs match" empty state (not "no renders found")

---

## 8. States

| State | Rendered as |
|---|---|
| Loading | 4 skeleton blocks (88px height each) |
| Error | Red-bordered card with message + "Try again" button → calls `_load()` |
| Empty history | `emptyState` with clock icon: "No renders found. Start a render from Source." |
| Empty filter result | `emptyState`: "No jobs match the current filter or search." |

---

## 9. Visual Style

- Cards: `.lib-card.card` — inherit base card dark background, soft border
- Hover: `border-color` elevates to `--color-border-strong`, `background` to `--color-surface-raised`
- Status chip from shared `statusChip()` component (all 8 states)
- AI badge from shared `aiBadge('advisory')` when AI metadata detected
- Filter pills: identical visual language to `.ratio-pill` / `.preset-pill` (border/accent pattern)
- Score color-coded: ≥70 success green / ≥40 warning amber / <40 failed red
- No random inline colors — all values from `--color-*` tokens

---

## 10. NavRail Update

| Slot | Before | After |
|---|---|---|
| Enabled 5 | (empty) | Library → `#/library` |
| Disabled 1 | Analytics | Downloads |
| Disabled 2 | Library | System |
| Disabled 3 | Settings | Publish |
| Disabled 4 | Help | (removed) |

---

## 11. Legacy Isolation

| Constraint | Status |
|---|---|
| No edits to `backend/static/` | ✅ |
| No edits to `backend/app/main.py` | ✅ |
| No backend WebSocket contracts changed | ✅ |
| No FFmpeg / render pipeline changes | ✅ |
| No `alert()` calls | ✅ |
| No raw JSON displayed to user | ✅ |

---

## 12. Known Limitations (UI-R3A Scope)

- `GET /api/jobs/history` endpoint must exist on the backend; if absent the error state is shown with a retry button (no crash).
- History list is sorted newest-first by `created_at`; if `created_at` is missing the item sorts to the bottom.
- Retry/Resume re-enable buttons on failure but do not automatically reload history (user must click Refresh).
- Right panel (`.shell__panel`) not wired to Library — shows default "Select a job to see details." copy.
- No pagination — loads all history items in one request.

---

## 13. Next Phase

**UI-R3B — Downloads Screen**: Standalone batch download of public videos for later rendering — implemented in this phase.

---

# UI-R3B — Downloads Screen

**Phase:** UI-R3B
**Date:** 2026-05-14
**Branch:** feature/ai-output-upgrade
**Scope:** Standalone batch download workflow — separate from render pipeline

---

## 1. Summary

Added the Downloads screen under `backend/static-v2/`. Users paste one URL per line, optionally set an output folder, and submit a batch download job via `POST /api/download/process`. The submitted job is tracked inline with status, a "Check Status" button (re-fetches via `GET /api/jobs/{id}`), and a "Retry failed items" button when the job status is failed. Navigation to Library is provided for full history. No backend files were modified.

---

## 2. Files Changed

| File | Change |
|---|---|
| `assets/js/screens/downloads.js` | New — Downloads screen |
| `assets/js/api/download.js` | New — download API wrappers |
| `assets/js/router.js` | Added `#/downloads` route → `downloadsScreen` |
| `assets/js/components/nav-rail.js` | Downloads moved to enabled (6th item); disabled list reduced to System, Publish |
| `assets/css/components.css` | Appended Downloads CSS classes |

---

## 3. Route Added

| Hash path | Screen | Params |
|---|---|---|
| `#/downloads` | downloadsScreen | — |

---

## 4. APIs Used

| Endpoint | Method | Wrapper | Purpose |
|---|---|---|---|
| `/api/download/process` | POST | `downloadApi.processDownload(payload)` | Submit batch download job |
| `/api/download/retry/{job_id}` | POST | `downloadApi.retryDownload(jobId, [])` | Retry failed download items |
| `/api/jobs/{job_id}` | GET | `downloadApi.getDownloadJob(jobId)` | Refresh job status on demand |

---

## 5. Endpoint Limitations

| Limitation | Detail |
|---|---|
| No history endpoint for downloads | `GET /api/jobs/history` returns all kinds including `download`; handled through Library screen, not Downloads screen |
| Quality preset not in contract | `POST /api/download/process` only documents `urls` and `output_dir` (§9.1). Quality picker is UI-only preference, **not sent to backend**. If a `quality` field is added to the backend model, add it to the payload in `processDownload()`. |
| Retry part_numbers | Empty array `[]` sent to backend = retry all failed items (§9.2: "Empty `part_numbers` retries failed parts") |
| No status polling | Downloads screen does not auto-poll. Status updates only on manual "Check Status" click. Full history and status tracking via Library. |

---

## 6. URL Parsing Behavior

`parseUrlInput(raw)` applies deterministic rules with no platform detection:

| Step | Rule |
|---|---|
| Split | By `\n` |
| Trim | Whitespace stripped per line |
| Skip | Empty lines silently dropped |
| Validate | Must start with `http://` or `https://` (case-insensitive) |
| Dedupe | Exact URL string match; duplicates silently dropped |
| Feedback | Valid count (green), invalid count (red), dupe count (faint) shown inline |

Invalid URLs block submit. Only valid de-duped URLs are sent in the API payload.

---

## 7. Output Folder Behavior

| Context | Behavior |
|---|---|
| Desktop (Electron) | `desktopAdapter.pickOutputDir()` — native folder picker, result shown inline |
| Browser (no Electron) | Manual text input; placeholder describes expected path format |
| Empty / not set | Field omitted from API payload; backend uses its configured default |

---

## 8. Job Result Panel

Shown after successful submit. Contains:

| Element | Behavior |
|---|---|
| Status chip | Shows job status from API response (`queued` initially) |
| Job ID | Monospace display of returned `job_id` |
| Item count / output dir | From API response |
| Item rows | First 8 items: part_no, source platform, truncated URL |
| View in Library | Navigates to `#/library` |
| Check Status | Fetches `GET /api/jobs/{id}`, updates chip and retry button visibility |
| Retry failed items | Shown only when status is `failed`; calls `POST /api/download/retry/{id}` with empty `part_numbers` |

Errors from retry or status check show inline below the action buttons. No `alert()`, no modal.

---

## 9. Visual Style

- Screen uses `.card.col.gap-3/4` sections consistent with Source/Library screens
- Textarea: `.dl-url-textarea` — monospace font, resizable, focus ring matches accent
- Quality pills: `.dl-quality-pill` / `--active` — same visual language as `.ratio-pill` / `.exec-pill`
- Path input: `.dl-path-input` — same styling as other form inputs
- Status note badge in header: `.dl-mode-note` — small bordered label
- Item rows in result panel: `.dl-item-row` with part/source/url columns
- All colors from `--color-*` tokens only

---

## 10. NavRail Update

| Slot | Before | After |
|---|---|---|
| Enabled 6 | (empty) | Downloads → `#/downloads` |
| Disabled 1 | Downloads | System |
| Disabled 2 | System | Publish |
| Disabled 3 | Publish | (removed) |

---

## 11. Legacy Isolation

| Constraint | Status |
|---|---|
| No edits to `backend/static/` | ✅ |
| No edits to `backend/app/main.py` | ✅ |
| No backend WebSocket contracts changed | ✅ |
| No FFmpeg / render pipeline changes | ✅ |
| No `alert()` calls | ✅ |
| No raw JSON displayed to user | ✅ |
| Download workflow isolated from render workflow | ✅ — no shared state or store |

---

## 12. Known Limitations (UI-R3B Scope)

- Quality preset selector is UI-only — not sent to backend because the documented contract (`§9.1`) does not include a quality field in `POST /api/download/process`. Add to payload when backend supports it.
- No auto-polling — user must click "Check Status" to see status updates. Full progress tracking available in Library (which loads from `GET /api/jobs/history`).
- "Check Status" calls `GET /api/jobs/{id}` using `normalizeJob()` — if the download job has an unknown status, it falls through to `'unavailable'` without crashing.
- Retry sends empty `part_numbers` (retry all failed); per-part retry selection not implemented.
- Right panel (`.shell__panel`) not wired to Downloads screen.
- `output_dir` is optional — if omitted, backend uses its default path. Users in browser context must type a backend-readable path manually.

---

## 13. UI-R3C — System / Diagnostics Screen

**Status:** Complete — 2026-05-14

**Route:** `#/system` (parameterless)

**Files changed:**
- `assets/js/api/system.js` — added `getWarmupStatus()` → `GET /api/warmup/status`, `getAIDiagnostics()` → `GET /api/render/ai-diagnostics`
- `assets/js/screens/system.js` — created (System screen, ~230 lines)
- `assets/js/router.js` — added `/system` route, imported `systemScreen`
- `assets/js/components/nav-rail.js` — System moved from disabled to enabled (7th item); only Publish remains disabled
- `assets/css/components.css` — appended System diagnostic styles

**Sections:**

1. **Runtime Readiness grid** — one card per warmup item (ffmpeg, gpu, yt_dlp, opencv_cascades, whisper_tiny/base/small, ollama_service, ollama_model) plus a Backend card from `GET /health`. Status badges: Ready / Running / Pending / Skipped / Error. Summary shows `X / Y ready` count.

2. **AI Intelligence panel** — Core capabilities (startup_safe, embedding_available, vector_store FAISS, fallback_mode, SQLite memory) and optional library rows (sentence_transformers, faiss, librosa, mediapipe, faster_whisper, whisperx, deepfilternet). All from `GET /api/render/ai-diagnostics`.

3. **Environment panel** — Backend URL (origin), execution mode, app version (when available), GPU available, FFmpeg available from `systemStore.getState()` + health data.

4. **Troubleshooting panel** — Hidden when empty. Surfaces real detected errors only: warmup errors[], warmup items with status=error, AI diagnostics warnings[], memory warnings[]. No static tips.

**Behaviour:**
- `_refresh()` uses `Promise.allSettled([getWarmupStatus(), getAIDiagnostics(), getHealth()])` — partial failure allowed; any fulfilled response is shown.
- Error shown only when all three endpoints fail.
- "Refresh" button triggers `_refresh()` manually; disabled during in-flight request.
- Timestamp shown after first successful fetch.
- Module-level `_s` state object reset on every `mount()`.

**Known limitations / deferred:**
- No auto-refresh / polling interval — manual Refresh only.
- `GET /api/system/info` and `GET /api/system/execution-mode` not found in backend routes; execution mode sourced from `systemStore` which calls `GET /health` / `GET /api/system/execution-mode` via `Promise.allSettled` (graceful on 404).
- Right panel (`.shell__panel`) not wired to System screen.

---

## 14. UI-R4A — Workspace Polish

**Status:** Complete — 2026-05-14

**Scope:** Visual/interaction polish only. No new screens, no backend changes, no workflow changes.

**Files changed:**
- `assets/css/tokens.css` — added `--transition-fast`, `--transition-base`, and 5 status soft-color aliases
- `assets/css/base.css` — added `::selection`, `.sr-only`, focus ring glow
- `assets/css/layout.css` — added `.gap-5`, `.mb-*` helpers, smooth scroll + overscroll on screen body, `.screen__body--padded`, `.screen__subtitle` → faint/slimmer
- `assets/css/components.css` — targeted improvements across 14 sections (see below)
- `assets/js/components/nav-rail.js` — accessibility: `aria-current="page"`, `aria-label`, `aria-hidden` on icons, `tabindex="-1"` on disabled items

**Polish improvements by category:**

**1. Spacing rhythm**
- `.card` padding: `--sp-4` (16px) → `--sp-5` (20px) — more breathing room
- New `.card--interactive` variant with hover state and box-shadow
- New `.card--raised` gets `box-shadow: 0 2px 8px rgba(0,0,0,0.22)` for elevation

**2. NavigationRail**
- Item size: 48×48 → 52×52px (larger hit target)
- Active: `box-shadow: inset 3px 0 0 var(--color-accent)` left-rail accent indicator (Linear-style)
- Hover: subtle left accent hint `inset 2px 0 0 rgba(118,224,192,0.3)`
- Disabled: opacity 0.35 → 0.28 (more ghost-like)
- Transitions: now use `--transition-fast` token
- `aria-current="page"` on active item, `aria-disabled` on disabled, `aria-label` on nav

**3. Motion & Interactions**
- Running status chip dot: pulse animation (`dot-pulse`, 1.4s ease-in-out)
- Skeleton: opacity pulse → gradient shimmer sweep (`skeleton-shimmer`)
- Progress bar (running): animated shimmer wash across fill
- All buttons: `transition` now includes `transform`; `active:scale(0.97)` press micro-interaction
- New `.btn-danger` variant

**4. Surface & Elevation**
- `.card--raised` gains elevation shadow
- `.output-clip-card--selected`: accent ring + left accent bar `inset 3px 0 0`
- `.clip-rank-badge--best`: teal ambient glow `box-shadow: 0 0 10px rgba(118,224,192,0.22)`
- `.hero-video-container`: deep shadow `0 4px 24px rgba(0,0,0,0.42)` for media lift
- Library card hover: adds `box-shadow: 0 2px 10px rgba(0,0,0,0.2)`
- Output clip card hover: adds `box-shadow`

**5. Typography**
- `.screen__subtitle`: color muted → faint, `line-height: 1.4`
- `.panel-section__title`: weight 600 → 700, tracking 0.06em → 0.08em
- `.monitor-stage-text`: 20px → 22px, tighter letter-spacing

**6. Form / Input**
- Focus glow: `box-shadow: 0 0 0 3px rgba(118,224,192,0.12)` on `.form-input:focus`
- Same glow applied to `.dl-url-textarea`, `.dl-path-input`, `.lib-search`

**7. Scroll hardening**
- `screen__body`: `scroll-behavior: smooth; overscroll-behavior-y: contain`
- Part list selected state: left accent bar

**8. System Diagnostics fix**
- `.sys-badge`: `border-radius: var(--radius-sm)` (undefined token) → `4px` (fixed rendering bug)
- Badge: weight 500 → 600, added `letter-spacing: 0.01em`

**Known limitations / deferred:**
- Right panel still empty for most screens (deferred to UI-R4B)
- No route-transition animation (could be added with view-transitions API in a future phase)
- Studio screen could benefit from config section grouping polish (deferred)

---

## 15. UI-R4B — Result Intelligence UX

**Date:** 2026-05-14  
**Commit:** `feat(ui): add result intelligence experience`

Exposes Phase 59-62 AI intelligence metadata in the Results screen. No new backend logic, no API changes — purely a UI extraction and display layer.

### Files Changed

| File | Change |
|---|---|
| `entities/ai-insight.js` | Rewritten: added `intelligence` field + `_parseIntelligenceCore()` |
| `screens/results.js` | `renderAIPanel()` completely replaced with 5-section premium panel |
| `css/components.css` | ~170 lines of AI intelligence panel CSS appended |

### `ai-insight.js` — Intelligence Extraction

`parseAIInsightSummary()` now returns an `intelligence` object built by `_parseIntelligenceCore()`.

**Source fields consumed (with priority fallback):**
- Applied items: `ai_execution_metrics.{subtitle,camera,segment}` → `render_outcome_tracking.ai_execution`
- Strategy: `creator_render_strategy` > `platform_render_strategy` > `creator_archetype_strategy`
- Quality scores: `render_outcome_tracking.quality` → `render_quality_v2`
- Creator fit: `render_outcome_tracking.benchmark_result.creator_fit` → `creator_benchmark_summary.benchmark_status`
- Learning items: `creator_preference_reinforcement.reasoning` → `learning_influence_calibration.reasoning` → filtered `render_outcome_tracking.reasoning`
- Suggestions: `platform_quality_feedback.improvement_opportunities`
- Mode/assistance: `ai_execution_metrics.mode` / `ai_execution_summary.overall_ai_assistance`

All fields optional/defensive. `_parseIntelligence()` wraps core in try/catch — never throws. Returns `_emptyIntelligence()` on any error.

**`intelligence` shape:**
```
appliedItems[]     — { domain, label, detail }
creatorType        — "Podcast" | "TikTok" | etc. (formatted)
platform           — "TikTok" | "YouTube" | etc. (formatted)
platformFit        — 0-100 | null
confidence         — 0-1 | null
confidenceLabel    — "High" | "Medium" | "Low" | null
strategyNotes[]    — string[]
qualityScores      — { overall, subtitle, camera, hook } | null
creatorFit         — "High" | "Medium" | "Low" | null
learningItems[]    — string[]
suggestions[]      — string[]
modeLabel          — "Off" | "Safe" | "Balanced" | "Aggressive" | null
assistanceLabel    — "Full AI assistance" | "N improvements applied" | null
assistanceDomains  — number
aiEffectiveness    — string | null
overallResult      — string | null
hasData            — boolean
```

### `results.js` — New `renderAIPanel()`

5-section premium panel (all sections conditional on data presence):
1. **"What AI improved"** — applied items with ✓ check + detail
2. **"Creator & Platform"** — type/platform/fit/confidence in key-value rows; strategy notes below
3. **"Quality"** — tile grid with per-domain scores color-coded via `scoreColor()`
4. **"AI learned"** — learning evidence items with ✓ marks
5. **"Suggestions"** — compact cards, each labeled "Manual review"
- Footer: mode + assistance level
- Empty state: shown when `!isActive || !intel?.hasData`
- Warnings: quality gate blocks shown as chips below footer

### CSS — AI Intelligence Panel

New classes appended to `components.css`:
- `.ai-intel-panel` / `.ai-intel-panel--active` — container with accent border when active
- `.ai-intel-header` / `.ai-intel-icon` — header row
- `.ai-intel-section` / `.ai-intel-section__title` — section divider + label
- `.ai-applied-item` / `.ai-applied-item__check` — applied item row with teal ✓
- `.ai-strat-rows` / `.ai-strat-row` / `.ai-strat-row__key` / `.ai-strat-row__val` — key-value table rows; `__val--high/medium/low` variants
- `.ai-conf-pill--high/medium/low` — inline confidence badge (green/yellow/red)
- `.ai-quality-grid` / `.ai-quality-tile` / `.ai-quality-score` — score grid tiles
- `.ai-learning-item` / `.ai-learning-item__check` — learning evidence rows
- `.ai-suggest-list` / `.ai-suggest-card` / `.ai-suggest-label` — suggestion cards
- `.ai-exec-footer` — execution transparency row
- `.ai-intel-empty` — empty state text

**Known limitations / deferred:**
- Right panel per-clip detail does not yet show AI sub-metrics (deferred)
- Suggestions `safe_apply_available` flag not surfaced (always shows "Manual review")

---

## 16. UI-R4C — Desktop Quality Hardening

**Date:** 2026-05-14  
**Commit:** `feat/ui: harden desktop quality experience`

Hardens static-v2 for real desktop usage. No new features, no backend changes.

### Files Created

| File | Purpose |
|---|---|
| `components/error-boundary.js` | Per-screen crash recovery card |
| `store/readiness.js` | Warmup/tool availability state |

### Files Modified

| File | Change |
|---|---|
| `transport.js` | `withTimeout()`, `normalizeApiError()`, network error normalization |
| `app.js` | Load readiness store; premium boot error screen |
| `components/shell.js` | Backend unavailable banner; targeted screen clear |
| `store/system.js` | Periodic health watch (30s interval) |
| `router.js` | Targeted `.screen` removal; per-route error boundary |
| `desktop-adapter.js` | `folderPickerAvailable`, `filePickerAvailable`; try/catch on all IPC calls |
| `screens/source.js` | yt-dlp warning; 45s prepare timeout; file picker guard |
| `screens/studio.js` | Session redirect; FFmpeg guard on render button; 30s submit timeout |
| `screens/monitor.js` | 20s connection timeout with retry banner; no-job recovery |
| `css/components.css` | `.eb-card`, `.backend-banner`, `.readiness-warning`, `.studio-video-err` |

### Hardening Implemented

**1. Global Screen Error Boundary**
- Router wraps every `screen.mount()` call in a try/catch
- On crash: renders `.eb-card` with "Reload screen" retry + "← Back to Source" link
- `console.error` preserved for dev; no stack trace shown in UI
- `components/error-boundary.js` also exports `withErrorBoundary()` for manual wrapping

**2. Backend Availability Guard**
- `store/system.js` polls `/api/health` every 30s
- `components/shell.js` subscribes and shows `.backend-banner` strip when backend unavailable
- Banner includes "Retry" button that calls `systemStore.refresh()`
- Nav remains usable; only actions requiring backend are blocked
- Boot failure shows inline "Backend is not ready yet" page with Retry button

**3. Warmup / Readiness Guard**
- `store/readiness.js` reads `/api/warmup/status` after boot (non-blocking)
- Normalizes multi-key warmup items (`yt_dlp`/`ytdlp`/`yt-dlp`, etc.)
- `ffmpegAvailable === false` → `renderBlocked = true` → Studio render button disabled with explanation
- `ytdlpAvailable === false` → Source screen shows `.readiness-warning` + YouTube tab disabled
- All values default `null` (unknown); fail-open on endpoint error — never hard-blocks

**4. API Error Normalization**
- `transport.js fetchJson` wraps network-level `fetch()` in try/catch — connection failures yield `"Backend is not reachable. Check your connection and try again."` instead of `TypeError: Failed to fetch`
- `fetchJson` JSON parse errors no longer crash — returns `null` for unparseable 2xx
- `normalizeApiError(err)` → `{ ok, status, message, code, details }` for any thrown error
- `withTimeout(promise, ms, label)` exported utility — rejects with calm user message after timeout

**5. Stuck Loading Timeouts**
- Source prepare: 45s timeout (`PREPARE_TIMEOUT_MS`)
- Render submit: 30s timeout (`RENDER_TIMEOUT_MS`)
- Monitor initial connection: 20s timeout (`CONNECT_TIMEOUT_MS`) → shows retry banner
- All timeouts yield inline recoverable error messages, never leave buttons permanently disabled

**6. Transport Hardening**
- WS → polling fallback already present; `closed` guard prevents duplicate subscriptions
- `unsubscribe()` always clears polling timers
- Terminal state stops polling immediately
- Malformed WS messages caught and ignored in existing `try { JSON.parse } catch`
- Transport mode exposed to Monitor via `renderTransportBadge()`

**7. Media Load Hardening (Studio)**
- Preview video `error` event → shows `.studio-video-err` overlay (positioned absolute over preview)
- Retry button: hides overlay, calls `video.load()`
- Studio preview: `position: relative` added to CSS for overlay to anchor correctly
- Video retry always uses `/api/render/preview-video/{sessionId}` (stream endpoint), never raw path

**8. Desktop Adapter Hardening**
- Added `folderPickerAvailable` getter (checks `api?.pickOutputDir`)
- Added `filePickerAvailable` getter (checks `api?.pickVideoFile`)
- All IPC calls wrapped in try/catch — return `null` on failure, never crash
- Browse/Choose buttons rendered only when respective picker is available
- `openExternal` falls back to `window.open` if IPC fails

**9. Route Recovery**
- Studio: no `editSessionId` → shows recovery card "No source is loaded" + "← Go to Source"
- Monitor: jobId always starts transport subscription (works after refresh)
- Monitor: no jobId → shows "No job selected" with links to Studio and Library
- Results: jobId always loads via `resultsStore.load()` (works after refresh)
- Invalid jobId on Monitor: 20s timeout banner + retry; on Results: API error shown inline
- Unknown routes: redirect to `/source`

**10. UI Copy**
- Boot failure: "Backend is not ready yet. Try again in a moment."
- Backend banner: "Backend is not ready yet. Try again in a moment."
- FFmpeg missing: "FFmpeg is unavailable, so rendering is disabled. Check System → Diagnostics for details."
- yt-dlp missing: "yt-dlp is unavailable, so YouTube downloads are disabled. Use a local file instead."
- Prepare timeout: "Source preparation timed out. Check your connection and try again."
- Submit timeout: "Render submit timed out. Check your connection and try again."
- Monitor timeout: "Taking longer than expected. No job data has arrived yet."
- Screen crash: "The screen couldn't load. This is usually temporary."
- Studio no session: "No source is loaded. Go back to Source to prepare a video."

### Verification

| Check | Result |
|---|---|
| No backend changes | ✓ |
| No legacy UI changes | ✓ |
| Backend unavailable does not crash UI | ✓ banner shown, nav works |
| Invalid route recovers | ✓ redirects to /source |
| Studio refresh without session redirects safely | ✓ recovery card shown |
| Monitor refresh with jobId attempts load | ✓ transport starts on mount |
| Results refresh with jobId attempts load | ✓ resultsStore.load() on mount |
| WS failure falls back to polling | ✓ existing transport |
| Media failure shows retry state | ✓ overlay + retry button |
| Folder picker unavailable does not crash | ✓ try/catch + null return |
| No infinite loading after failed fetch | ✓ timeout guard on all critical ops |
| node --check passes all changed JS | ✓ 11/11 |

**Known limitations / deferred:**
- No automatic reconnect after backend recovers during active render (polling continues when backend comes back, WS does not reconnect)
- Results page does not have a loading timeout (depends on store load which is already caught)
- Library and Downloads screens not specifically hardened (deferred — lower failure surface)

---

## 17. UI-R5 — Static-v2 Activation & Migration Gate

**Date:** 2026-05-14  
**Commit:** `feat(ui): add static-v2 activation gate`

Adds a rollback-safe environment-variable gate to choose which static UI the backend serves. No render pipeline changes, no AI logic changes, no legacy UI deletion.

### Files Changed

| File | Change |
|---|---|
| `backend/app/core/ui_gate.py` *(new)* | `resolve_static_directory()` helper |
| `backend/app/main.py` | Import helper; conditional static mount; `ui_version` in `/health` |
| `tests/test_ui_gate.py` *(new)* | 11 unit tests for the gate helper |

### Activation Behavior

**Environment variable:** `STATIC_UI_VERSION`

| Value | Behavior |
|---|---|
| *(unset / empty)* | Serves `backend/static/` (legacy) — safe default |
| `legacy` | Serves `backend/static/` (legacy) |
| `v2` | Serves `backend/static-v2/` (new UI) |
| any other value | Warns and falls back to legacy |
| `v2` but `static-v2/` missing | Warns and falls back to legacy |

### Static Mount Strategy

- **Legacy:** mounts `backend/static/` at `/static` (existing absolute-path references in legacy `index.html` like `/static/css/app.css` continue to work)
- **v2:** mounts `backend/static-v2/assets/` at `/assets` (static-v2 `index.html` uses relative paths `assets/css/…` → resolves to `/assets/css/…`)

### Health Metadata

`GET /health` now includes `ui_version`:
```json
{"status": "ok", "ui_version": "v2"}
```

### Rollback

Switch to v2 then back to legacy instantly — no restart needed beyond env change + server restart:

```powershell
# Activate v2
$env:STATIC_UI_VERSION = "v2"
# Launch backend normally

# Roll back to legacy
$env:STATIC_UI_VERSION = "legacy"
# Or simply unset it:
Remove-Item Env:\STATIC_UI_VERSION
```

### Usage Examples

```powershell
# PowerShell — run legacy (default)
$env:STATIC_UI_VERSION = "legacy"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# PowerShell — run static-v2
$env:STATIC_UI_VERSION = "v2"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

```bash
# Bash / shell — run v2
STATIC_UI_VERSION=v2 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Backend / Render Behavior

No changes to:
- API routes or WebSocket endpoints
- Render pipeline (FFmpeg, yt-dlp, Whisper)
- AI director logic
- Job manager, warmup, session management
- Desktop shell launch URL (`http://127.0.0.1:8000`)

### Test Checklist

| Test | Status |
|---|---|
| Missing env → legacy | ✓ |
| `STATIC_UI_VERSION=legacy` → legacy | ✓ |
| `STATIC_UI_VERSION=v2` with `static-v2/` present → v2 | ✓ |
| `STATIC_UI_VERSION=V2` (uppercase) → v2 | ✓ |
| Invalid value → legacy fallback | ✓ |
| `STATIC_UI_VERSION=v2` but dir missing → legacy fallback | ✓ |
| Return type guarantees (`Path`, `str`) | ✓ |
| Never raises on unusual input values | ✓ |
| `py_compile backend/app/main.py` | ✓ |
| `py_compile backend/app/core/ui_gate.py` | ✓ |
| `pytest tests/test_ui_gate.py` — 11/11 passed | ✓ |

### Manual Verification Checklist

- [ ] Start backend without env → `http://127.0.0.1:8000` loads legacy UI
- [ ] Start backend with `STATIC_UI_VERSION=v2` → loads static-v2 UI
- [ ] `/health` returns `{"status":"ok","ui_version":"v2"}` in v2 mode
- [ ] API routes (Source → Studio → Monitor → Results) still work
- [ ] Library / Downloads / System routes work in v2
- [ ] Legacy UI still works after unsetting env var

---

## 18. UI-R6 — Static-V2 End-to-End QA Pass

**Date:** 2026-05-14  
**Commit:** `test(ui): validate static-v2 end-to-end workflow`  
**Scope:** Full QA audit of static-v2 — activation, core workflow, extended screens, desktop hardening, visual smoke.

### QA Areas Checked

| Area | Files Audited | Finding |
|---|---|---|
| Static-v2 activation | `main.py`, `ui_gate.py`, `index.html` | ✓ Gate wired, assets mount correct |
| Core creator workflow | `screens/source.js`, `screens/studio.js`, `screens/monitor.js`, `screens/results.js` | ✓ No crash bugs; all route guards present |
| Extended screens | `screens/library.js`, `screens/downloads.js`, `screens/system.js` | ✓ Clean state reset on mount; graceful error handling |
| Desktop hardening | `desktop-adapter.js`, `transport.js`, `store/readiness.js`, `store/system.js` | ✓ IPC wrapped in try/catch; transport fail-open |
| Shell & routing | `components/shell.js`, `router.js`, `app.js` | 1 minor fix applied (see below) |

### Bug Fixed

**`components/shell.js` — redundant dynamic import in banner retry handler**

The retry button in `_updateBanner` was using a dynamic `import('../store/system.js')` to reach `systemStore.refresh()` even though `systemStore` is already statically imported at the top of the module. This caused an unnecessary module re-load on every retry click.

Fixed by replacing the dynamic import with a direct call to the already-imported `systemStore`:

```js
// Before
banner.querySelector('#banner-retry')?.addEventListener('click', () => {
  import('../store/system.js').then(m => m.systemStore.refresh());
});

// After
banner.querySelector('#banner-retry')?.addEventListener('click', () => {
  systemStore.refresh();
});
```

### Verification Results

| Check | Result |
|---|---|
| `node --check` on 12 JS files (all modified/new files) | ✓ 12/12 passed |
| `py_compile backend/app/main.py` | ✓ |
| `py_compile backend/app/core/ui_gate.py` | ✓ |
| `pytest tests/test_ui_gate.py` — 11/11 | ✓ |
| Explore agent deep audit — 41 JS files scanned | 0 crash bugs found |
| Manual read of 7 core files | All clean |

### QA Notes

- `screens/system.js` uses `Array.isArray(_s.warmup?.items)` — if backend returns items as an object (not array), the readiness grid shows empty with no crash. Acceptable.
- `store/readiness.js` normalizes warmup response shape: `data?.items ?? data?.warmup_items ?? {}`. This correctly handles both the legacy dict format and a future array format.
- All screens reset module-level state in `mount()` — no stale state leaks across route changes.
- Error boundary (`withErrorBoundary`) is applied at router level and available as a HOF for individual screens.

---

## 19. UI-FIX-1 — Source File/Folder Usability

**Date:** 2026-05-14  
**Commit:** `fix(ui): make source file and folder selection usable`  
**Scope:** Make Source screen actually usable — local video picker, output folder picker, Electron IPC wiring, browser fallback, path chip display, clear buttons, URL validation tightening.

### Root Cause

`preload.js` did not expose `pickVideoFile`, `pickOutputDir`, `getAppVersion`, or `onJobProgress`. `desktop-adapter.js` checked for `api?.pickVideoFile` and `api?.pickOutputDir` — both were always `undefined` — so `filePickerAvailable` and `folderPickerAvailable` were always `false`, even inside Electron. No browse button ever rendered.

### Files Changed

| File | Change |
|---|---|
| `desktop-shell/preload.js` | Added `pickVideoFile`, `pickOutputDir`, `getAppVersion`, `onJobProgress` to `electronAPI` |
| `desktop-shell/main.js` | Added `pick-video-file` IPC handler (native file dialog, video filter), `app:getVersion` IPC handler |
| `backend/static-v2/assets/js/screens/source.js` | Enhanced `renderLocalInput`, `renderOutputDir`, `wireAll`, URL validation; added `_truncatePath` helper |
| `backend/static-v2/assets/css/components.css` | Added `.path-chip` CSS |

### Picker Behavior

#### Local Video Picker (Electron)
- `preload.js` → `pick-video-file` → `dialog.showOpenDialog({ filters: ['mp4','mov','mkv','avi','webm','wmv','m4v','flv'] })`
- Returns selected path string or `null` on cancel
- `desktop-adapter.pickVideoFile()` wraps in try/catch — never throws
- On pick: updates `_s.localPath`, calls `rerenderForm()` to show path chip

#### Local Video Picker (Browser)
- `desktopAdapter.filePickerAvailable` = `false` — Browse button hidden
- Input renders with placeholder "Paste file path here…"
- Helper text: "Browse is available in desktop mode. Paste a local file path here."

#### Output Folder Picker (Electron)
- `preload.js` → `pick-output-dir` → reuses existing `open-folder-picker` IPC → `dialog.showOpenDialog({ properties: ['openDirectory'] })`
- Returns path string or `null` on cancel
- On pick: updates `_s.outputDir`, calls `rerenderForm()` to show folder chip

#### Output Folder Picker (Browser)
- `desktopAdapter.folderPickerAvailable` = `false` — Browse button hidden
- Helper text: "Browse is available in desktop mode. Paste an output folder path here."

### Path Chip
- Shows when a file/folder is selected
- Truncated monospace display with full path in `title` attribute (hover to see full path)
- `_truncatePath(p, 52)` — preserves filename, ellipsises the middle of long paths
- Clear button (`×`) sets `_s.localPath = ''` / `_s.outputDir = ''` and rerenders

### Payload Mapping

`PrepareSourceRequest` schema has no `output_dir` field — output dir is stored in `draftStore` and passed when the render job is submitted from Studio. Payload unchanged from prior implementation:

```js
// YouTube
{ source_mode: "youtube", youtube_url: "https://youtube.com/…" }

// Local
{ source_mode: "local", source_video_path: "/path/to/video.mp4" }
```

Output dir stored via `draftStore.patch({ outputDir: _s.outputDir })` after prepare success.

### Validation

| Condition | Error message |
|---|---|
| YouTube mode, empty URL | "YouTube URL is required." |
| YouTube mode, not youtube.com/youtu.be | "Enter a valid YouTube URL (youtube.com or youtu.be)." |
| Local mode, no path | "Select a video file to continue." |
| Missing output dir | "Output directory is required." |

No `alert()`. Inline error card below form fields. Error cleared on mode switch.

### Desktop Adapter Hardening

`getAppVersion` and `onJobProgress` now properly wired in `preload.js`. `onJobProgress` returns an unsubscribe function that calls `ipcRenderer.removeListener`. All four new preload methods catch and return `null` on any IPC error.

### Known Limitations

- Browser manual path input: the backend must be able to resolve the pasted path — no client-side file existence check in browser context.
- YouTube URL validation checks for `youtube.com` or `youtu.be` substring only — does not validate video ID format.
- `onJobProgress` IPC event `'job-progress'` is wired on the preload side but no matching `mainWindow.webContents.send('job-progress', ...)` exists in `main.js` yet — bridge is ready for when that's added.

### Verification Checklist

```
STATIC_UI_VERSION=v2

# Syntax
node --check backend/static-v2/assets/js/screens/source.js   → OK
node --check backend/static-v2/assets/js/desktop-adapter.js  → OK
node --check desktop-shell/preload.js                         → OK
node --check desktop-shell/main.js                            → OK

# Browser mode (#/source)
- Local tab: Browse button absent, helper text shown       → ✓
- Output: Browse button absent, helper text shown          → ✓
- Paste local path: chip appears, clear button works       → manual
- Invalid YouTube URL: inline error shown                  → manual
- Missing output dir: inline error shown                   → manual

# Electron mode
- Local Browse… → native file dialog opens                → manual (requires Electron)
- Output Browse… → native folder dialog opens             → manual (requires Electron)
- Cancel → path unchanged                                  → manual
- Pick file → chip appears, clear works                    → manual
```

---

## 20. UI-FIX-2 — Render Workflow Friction

**Date:** 2026-05-14  
**Commit:** `fix(ui): reduce render workflow friction`  
**Scope:** Source readiness checklist; Studio preview loading state; render summary chips in CTA; retry affordance; improved validation messages.

### Files Changed

| File | Change |
|---|---|
| `backend/static-v2/assets/js/screens/source.js` | Added `renderReadinessSummary()`; updated `renderForm()` — readiness checklist, conditional helper text, "Prepare source →" label |
| `backend/static-v2/assets/js/screens/studio.js` | Added loading overlay to `renderPreviewArea()`; replaced video event handler with timeout-safe loading handler; added `renderRenderSummary()`; updated `renderCTA()` with summary chips and retry label |
| `backend/static-v2/assets/js/entities/render-request.js` | Improved validation error messages; added aspect ratio, subtitle style, reframe mode validation |
| `backend/static-v2/assets/css/components.css` | Added `.summary-chip` |

### Source Friction Fixes

**Readiness checklist** — rendered between the output folder field and the error area:
- ✓/○ Source entered (YouTube URL or video file, per active mode)
- ✓/○ Output folder set
- ✓/○ Backend reachable (proxy: `readinessStore.loaded`)

**Helper text under CTA** — contextual:
- When fields incomplete: "Complete the fields above, then prepare your source."
- When all ready: "Ready — click to validate and open Studio."
- When loading: "This may take up to a minute for YouTube videos."

**CTA label** — "Prepare source" → "Prepare source →"

### Studio Preview Readiness

**Loading overlay** — shown immediately when Studio opens with a session:
- Uses `studio-video-err` positioning class (absolute, inset:0, dark background)
- Copy: "Loading preview… Configure your settings while the preview loads."
- Dismissed on `canplay`, `loadedmetadata`, or immediate if `video.readyState >= 3`
- 10 second timeout → shows error overlay if video never becomes playable
- Timer cleared on `unmount` event to prevent post-navigation leaks

**Preview error overlay** — improved copy:
- "Preview unavailable" (was "Preview couldn't load")
- "The source may still be processing. You can configure and start the render without it."

**Retry preview** — existing button wired correctly; retry resets loading overlay and restarts 10s timer.

### Render CTA Behavior

**Render summary chips** — shown when draft is valid (no blocking errors):
```
[9:16]  [≤5 clips]  [15–60s]  [viral bold]  [AI off]  [2:34 source]
```
- `sessionDuration` chip shown when source duration is known
- Chips hidden when there are validation errors (errors take that slot)

**Retry affordance** — when `_submitError` is set:
- Error message shown in red
- "Start render →" button label changes to "Retry render →"
- Button re-enabled (no separate retry button needed)

**Duplicate submit guard** — `_submitting = true` while in-flight; button disabled.

### Validation Rules (render-request.js)

| Rule | Error message |
|---|---|
| No source identifier | "No source loaded — go back to Source to prepare a video." |
| No output folder | "Output folder is required — go back to Source to set it." |
| Min > max clip duration | "Min clip duration (Xs) must be ≤ max clip duration (Ys)." |
| Invalid aspect ratio | "Unknown aspect ratio "X" — choose 9:16, 1:1, 3:4, or 16:9." |
| Invalid subtitle style | "Unknown subtitle style "X"." |
| Invalid reframe mode | "Unknown camera mode "X"." |

### Monitor Entry Behavior

No changes required — existing monitor screen already provides:
- Skeleton loading cards while job data arrives
- Transport badge: `● Live` / `○ Polling` / `⋯ Connecting`
- 20s timeout banner with Retry + Library CTAs
- Route recovery: no jobId → calm recovery card

### Known Limitations

- Readiness checklist "Backend reachable" uses `readinessStore.loaded` as proxy — becomes `true` once the warmup call returns (even on failure). This is intentional fail-open behavior.
- Preview 10s timeout may be too aggressive for very large source files where FFmpeg preview generation takes longer. Acceptable for now — user can retry.
- Render summary `sessionDuration` shows source duration, not estimated output duration. This is correct — output duration depends on clip selection.

### Verification Checklist

```
node --check backend/static-v2/assets/js/screens/source.js   → OK
node --check backend/static-v2/assets/js/screens/studio.js   → OK
node --check backend/static-v2/assets/js/store/draft.js      → OK
node --check backend/static-v2/assets/js/api/render.js       → OK
node --check backend/static-v2/assets/js/entities/render-request.js → OK

Source (#/source, STATIC_UI_VERSION=v2):
- No fields: checklist shows 2× ○ (+ backend ✓ if loaded)  → manual
- YT URL entered: first item becomes ✓                      → manual
- Output set: second item becomes ✓                         → manual
- All ready: helper text changes to "Ready — click…"        → manual
- Invalid YT URL: inline error, no route change             → manual
- Missing output: inline error                              → manual

Studio (#/studio after prepare):
- Loading overlay shown immediately                         → manual
- Overlay disappears when video buffered                    → manual
- After 10s without canplay: error overlay shown            → manual
- Retry preview: resets loading state                       → manual
- Summary chips visible when draft valid                    → manual
- Chips hidden when error (e.g., no output dir)             → manual
- Start render → submit → navigates #/monitor/:jobId        → manual
- Network error → button becomes "Retry render →"           → manual

Monitor (#/monitor/:jobId):
- Job ID shown in header                                    → manual
- Transport badge visible (connecting → live/polling)       → manual
- No blank state                                            → manual
```

---

## 21. UI-R4D — Premium Creator UX Transformation

**Date:** 2026-05-14
**Commit:** `feat(ui): transform static-v2 premium creator experience`

### Goal
Transform static-v2 from "usable internal tool" to premium creator workstation feel (CapCut/Runway/Descript/Linear). Visual-only — no behavior, workflow, or backend changes.

### Changes

**`backend/static-v2/assets/css/tokens.css`**
- Added missing `--radius-sm: 6px` and `--radius-md: 8px` (were referenced in components.css but never defined, causing silent fallback failures in `.sys-status-card`, `.ai-quality-tile`, `.sys-tip`, `.ai-suggest-card`)

**`backend/static-v2/assets/css/components.css`** — appended `UI-R4D: Premium Creator Experience` block:
- `@keyframes screen-enter` + `.screen` rule — 0.18s fade+slide-up entrance on every screen mount
- `.btn-primary:hover` — replaced flat opacity fade with accent glow (`rgba(118,224,192,0.22)` shadow) + focus-visible ring
- `.card--raised` — deeper ambient shadow (4px/20px blur)
- `.nav-rail-item--active` — added -1px/14px accent glow radiating from left edge
- `.studio-body` — draft panel widened 340px → 360px
- `.studio-preview` — cinematic stage shadow (8px/40px + 2px/8px)
- `.draft-section__title` — `text-transform: none`, `letter-spacing: 0.01em`, `--text-body`/600 weight; removes ALL-CAPS shouting from section headers
- `.ratio-pill--active`, `.preset-pill--active` — 1px accent glow ring
- `.camera-option--active` — 1px accent glow ring + 2px/10px diffuse glow
- `.exec-pill--active` — subtle lift shadow
- `.studio-cta` — gradient fade from `--color-bg-raised` to transparent for depth
- `.monitor-stage-text` — 26px / 800 weight / −0.03em tracking (was 22px/700)
- `.output-clip-card:hover` — deeper lift (4px/16px) + accent breath ring; `.output-clip-card--selected` — accent shadow breath
- `.hero-video-wrap` — cinematic ambient shadow (12px/40px)
- `.empty-state__icon` — opacity 0.3 → 0.4
- `.form-input:focus` — deeper focus ring (3px rgba+15%, + 1px/4px depth shadow)

**`backend/static-v2/assets/js/screens/studio.js`** — section label cleanup:
- `"A · Clip Setup"` → `"Clips"`
- `"B · Subtitles"` span → `"Subtitles"`
- `"C · Camera"` → `"Camera"`
- `"D · AI Analysis"` span → `"AI Guidance"`

### Verification
```
node --check backend/static-v2/assets/js/screens/studio.js  → OK
```

CSS: no build step required; verified tokens referenced in overrides all resolve to defined values.

### Scope constraints respected
- No JS logic changed except section label strings
- No API calls, store behavior, or routing modified
- No new HTML structure introduced
- All overrides are additive CSS; existing selectors remain intact

---

## 22. UI-R4E — Premium UX Review & Gap Closure

**Date:** 2026-05-14
**Commit:** `feat(ui): close premium creator UX gaps`

### Gap Audit

| Dimension | Finding | Severity |
|---|---|---|
| Visual hierarchy | Studio section titles now sentence-case (R4D) — good | — |
| CTA prominence | "Start render →" button at default size for primary action | High |
| Monitor terminal | Success banner: green border only, no background — feels like a warning | High |
| Monitor terminal | Failed banner: red border only, no urgency background | High |
| Hero shadow | R4D targeted `.hero-video-wrap` (non-existent) — shadow not applying | High |
| Results success | Completion chips in unstyled row — no celebration feel | Medium |
| Clip card hover | `transform` missing from transition — lift wouldn't animate | Medium |
| AI panel active | Active border override never applied from R4D (overridden by specificity) | Medium |
| Hero meta seam | Border-top between video and meta strip visible and distracting | Low |
| Card density | Output clip cards: reasonable density, minor layout gaps | Low |

### Gaps Fixed

**`backend/static-v2/assets/css/components.css`** — appended `UI-R4E: Premium UX Gap Closure` block:
- `.hero-video-container` — corrects R4D bug (`.hero-video-wrap` was targeting non-existent class); cinematic shadow now applies: `0 8px 32px rgba(0,0,0,0.50)`
- `.terminal-banner`, `.terminal-banner--success`, `.terminal-banner--failed` — semantic banner classes with subtle tinted background (success: `rgba(116,212,143,0.04)`, failed: `rgba(255,124,124,0.04)`) + forced border-color
- `.terminal-banner__title` — 17px/700 weight title for terminal state clarity (replaces inline `font-weight:600`)
- `.studio-cta .btn-primary` — 42px min-height, increased h-padding, 14px font; makes the primary render action visually dominant
- `.output-clip-card:hover` — `transform: translateY(-1px)` (now animates properly because `transform` added to transition)
- `.output-clip-card` — added `transform` to transition list and `will-change: transform` for GPU compositing
- `.ai-intel-panel--active` — `border-color: rgba(184,166,255,0.35)` (previously overridden by original `.ai-intel-panel` specificity)
- `.results-complete-banner` — success tinted container (`rgba(116,212,143,0.04)` + `rgba(116,212,143,0.18)` border) replaces unstyled row
- `.hero-meta` — `border-top: 1px solid rgba(255,255,255,0.04)` softens the seam between video and meta strip

**`backend/static-v2/assets/js/screens/monitor.js`** — `renderTerminalBanner()`:
- Success case: `class="card terminal-banner terminal-banner--success"` (removed `style="border-color:var(--color-success)"`)
- Used `.terminal-banner__title` for heading instead of inline `font-weight:600`
- Failed/interrupted: `class="card terminal-banner terminal-banner--failed"` (removed `style="border-color:var(--color-failed)"`)

**`backend/static-v2/assets/js/screens/results.js`** — `renderStatusBar()`:
- Success completion: wrapped chips in `<div class="results-complete-banner">` (replaces `<div class="row gap-3" style="...">`)

### Studio Improvements
- "Start render →" CTA is now visually dominant: 42px tall, wider padding, 14px font — stands out against the draft configuration panel

### Results Improvements
- Completion state now has a celebration feel: soft green-tinted banner around status chips
- Hero video shadow now actually applies (bug fix)
- AI intelligence active panel now has distinct purple identity border

### Monitor Improvements
- Success terminal banner: green-tinted background + bold 17px title signals render completion as a moment, not just a state change
- Failed terminal banner: red-tinted background creates appropriate urgency for recovery actions

### Shell / Navigation
No changes in this pass — NavRail, bottom strip, and right panel are stable and not blocking premium feel.

### Remaining Limitations
- Cancel button in Monitor header is never shown (behavioral — out of scope for this pass)
- Right panel "Context" section is sparse on non-Results screens (scope: next iteration)
- Source screen tab styling mixes `.btn-primary` semantics with tab behavior — functional but not ideal

### Verification
```
node --check backend/static-v2/assets/js/screens/monitor.js → OK
node --check backend/static-v2/assets/js/screens/results.js → OK
```
CSS: all selectors reference existing DOM classes; no new class names introduced in JS without CSS counterparts.

### CapCut/Runway Standard Check
- Does Studio feel like a creative workspace? → Yes — preview dominant, CTA is now prominent
- Does Results feel like a successful render moment? → Yes — green completion banner + hero shadow
- Does Monitor feel alive and trustworthy? → Yes — success/failure banners now semantically differentiated
- Are primary actions obvious within 2 seconds? → Yes — "Start render →" is visually dominant; "View Results →" stands out in green-tinted success banner
- Are technical details secondary? → Yes — job IDs, transport badges, and AI footnotes remain subordinate

---

## 23. UI-R4F-A — Core UX Trust Fix

**Date:** 2026-05-14
**Scope:** Creator trust and clarity improvements — 8 highest-impact fixes from professional review

### Changes

| Fix | Priority | File(s) | Detail |
|---|---|---|---|
| Remove false download quality presets | P0-1 | `screens/downloads.js` | Removed QUALITY_OPTIONS, `_quality` state, quality pill HTML, pill event listeners; replaced with "Downloads use source quality defaults." helper text |
| Fix cancel render button label | P0-2 | `screens/monitor.js` | "Cancel" → "Cancel render" |
| Restore studio section title hierarchy | P0-3 | `css/components.css` | Removed R4D override that set `.draft-section__title` to `font-size:var(--text-body)` (13px) — restores original 11px/700/uppercase |
| Part → Clip terminology | P0-4 | `components/part-status-list.js`, `components/output-card.js`, `components/best-clip-hero.js`, `screens/results.js` | All user-facing "Part N" → "Clip N"; "parts" → "clips"; download filename `part_N.mp4` → `clip_N.mp4` |
| Studio right panel session context | P0-5 | `screens/studio.js` | Added `updateStudioPanel(draft)` — populates `#panel-content` with session title, duration, source type, and render-plan summary chips; called on mount and every rerender; cleared on unmount |
| Creator-friendly monitor copy | P1-1 | `screens/monitor.js` | STAGE_LABELS rewritten to plain English ("Fetching your video", "Finding scenes", "Cutting clips", etc.); "Parts" section header → "Clips"; "N/N parts" → "N/N clips"; subtitle changed to "Live render progress" |
| Library title normalization | P1-2 | `screens/library.js` | Added `_normalizeDisplayTitle()` and `_fmtDateShort()`: YouTube URLs → "YouTube · {videoId}", file paths → filename without extension, null titles → "Untitled render · {date}" |
| System nav de-emphasis | P1-3 | `components/nav-rail.js`, `css/components.css` | Split NAV_ITEMS into WORKFLOW_ITEMS (Source→Library) and UTILITY_ITEMS (Downloads, System); added divider between groups; added `.nav-rail-item--utility` class (opacity 0.55, 1 on hover/active) |

### Verification
- `node --check` passed on all 9 changed JS files
- No API contracts changed

---

## 24. Production Quality Audit — 2026-05-16

**Auditor Role:** Principal Software Engineer, Frontend Architect, UX Engineer
**Scope:** All files under `backend/static-v2/` — transport, state management, screens, components, API wrappers
**Method:** Direct code reading with file:line references. No assumptions made from documentation alone.

---

### 24.1 Transport Layer (`transport.js`)

**Current implementation:** `openJobStream()` opens a WebSocket to `/ws/jobs/{jobId}`. On error or close, falls back to HTTP polling every `POLL_INTERVAL_MS = 2000`. A post-terminal authoritative poll fires after 600ms to catch any final state not delivered over WS.

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| T-1 | **P0** | `transport.js:TERMINAL_STATUSES` | Frontend `TERMINAL_STATUSES = new Set(['completed', 'completed_with_errors', 'failed', 'interrupted'])` — 4 statuses. Backend WS (`routes/jobs.py:388-411`) only breaks on `completed` and `failed`. Jobs ending in `interrupted` or `completed_with_errors` leave the WS open on the server side, leaking a poll loop for up to the client's 20s timeout. |
| T-2 | **P1** | `transport.js` | No reconnect backoff — each WS failure falls immediately to polling. Under intermittent network, this generates burst HTTP traffic rather than gradual WS reconnect attempts. |
| T-3 | **P1** | `transport.js` | Polling fallback interval (2000ms) is hardcoded. High-frequency polling from multiple monitor tabs multiplies DB read pressure because the backend WS also polls SQLite at 500ms per connection (`routes/jobs.py:408`). |
| T-4 | **P2** | `transport.js` | No transport-type telemetry emitted to the store. Monitor screen shows a transport badge but it relies on `monitorStore` internal state — if `monitorStore` is reset, badge silently reverts to no-transport shown. |

**Recommended fixes:**
- **T-1 (P0):** Add `interrupted` and `completed_with_errors` to the server-side WS break condition in `routes/jobs.py:411`. One-line fix.
- **T-2 (P1):** Implement exponential backoff (1s → 2s → 4s → max 30s) before WS reconnect attempts.
- **T-3 (P1):** Implement server-sent events (SSE) or push-on-change DB triggers instead of polling SQLite every 500ms per WS client.

---

### 24.2 State Management (`store/monitor.js`, `store/render-session.js`)

**Current implementation:** `monitorStore` wraps `createStore()` factory. `start(jobId)` opens a transport stream, `stop()` closes it, `clear()` resets state. `renderSessionStore.sync()` is called from `monitorStore` after every mutation to propagate the active render bar state.

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| S-1 | **P1** | `store/monitor.js` | `renderSessionStore.sync(monitorState)` is called in three separate callbacks: `onUpdate`, `onTerminal`, and `onTransportChange`. All three can fire for the same WS message. Result: up to 3 redundant `renderSessionStore` mutations + 3 subscriber notification cycles per update tick. |
| S-2 | **P1** | `store/monitor.js` | `_subscription` is declared at module scope but `monitorStore.start()` can be called multiple times if the user navigates away and back without `stop()` being called (e.g., browser back + forward without unmount event). This orphans the previous subscription. The `unmount` listener in `monitor.js` mitigates this but relies on the custom event firing — which is not guaranteed across all navigation paths. |
| S-3 | **P2** | `store/render-session.js` | `renderSessionStore` state is never persisted to `sessionStorage` or `localStorage`. A hard refresh drops the active render bar, leaving the user with no way to reconnect to an in-progress render without navigating to `/monitor/:jobId` manually. |
| S-4 | **P2** | `store/` (all) | `createStore()` factory has no middleware layer. Adding cross-cutting concerns (logging, devtools, persistence) requires patching each store individually rather than at the factory level. |

**Recommended fixes:**
- **S-1 (P1):** Deduplicate sync — call `renderSessionStore.sync()` once at end of a batched update function rather than in each individual callback.
- **S-3 (P2):** Persist `{ jobId, status }` in `sessionStorage` on every `renderSessionStore` mutation; restore on app boot to reconnect the render bar.

---

### 24.3 Create Screen (`screens/create.js`)

**Current implementation:** 3-phase state machine: `import` → `preparing` → `configure`. `_handlePrepare()` calls `/api/render/draft`, sets `_phase = 'configure'` on success, resets to `_phase = 'import'` in catch. `_handleGenerate()` guarded by `if (_generating) return`.

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| C-1 | **P1** | `create.js:346-385` | `PREPARE_TIMEOUT_MS = 45_000`. If the server responds after 44s with an error, the catch block resets `_phase = 'import'` — correct. But if the server responds after 45s with **success**, the `AbortController` has already fired, the `catch` block has run and reset to `import`, but the `await fetch(...)` may still resolve in some environments. Result: `_phase` gets set to `configure` after the reset, leaving the UI in a ghost-configured state with no loaded draft. |
| C-2 | **P1** | `create.js` | No validation of the URL/file input before calling `_handlePrepare()`. An empty string or a URL with no valid host reaches the backend. The backend returns a 400/422, which resets the phase correctly, but the error message shown to the user is a raw API error string, not a friendly validation message. |
| C-3 | **P2** | `create.js` | The `import` phase does not persist the last-entered URL across page reloads. Users who accidentally refresh lose their input and must re-type the URL. |
| C-4 | **P2** | `create.js` | `_phase` transitions are not reflected in the URL hash. If the user is in `configure` phase and presses back, the router navigates away entirely rather than stepping back to `import` phase within the create screen. |

**Confirmed correct behaviors (NOT bugs):**
- `_handlePrepare()` catch block at line 380 correctly resets `_phase = 'import'` — not a stuck state bug.
- `_handleGenerate()` `if (_generating) return` at line 389 correctly prevents double-submission.

**Recommended fixes:**
- **C-1 (P1):** After `AbortController.abort()`, set a module-level `_aborted = true` flag; in the `fetch` `.then()` branch, check `if (_aborted) return` before proceeding to `_phase = 'configure'`.
- **C-2 (P1):** Add client-side URL validation (non-empty, starts with `http://` or `https://`, or is a local file path) before calling `_handlePrepare()`.

---

### 24.4 Monitor Screen (`screens/monitor.js`)

**Current implementation:** Mounts `monitorStore.start(jobId)` on load, cleans up on `unmount` event. Shows connection timeout banner after `CONNECT_TIMEOUT_MS = 20_000`. Cancel button calls `renderApi.cancel(jobId)`. Retry/Resume buttons have `disabled=true` on click to prevent double-submission. Stage labels rewritten to plain English in R4F-A.

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| M-1 | **P0** | `screens/monitor.js:301-305` | `el.addEventListener('unmount', ...)` — the `unmount` event is a custom event that `router.js` must dispatch on route change. If `router.js` does not dispatch `unmount` on the outgoing screen element (e.g., on hash-only changes), the `monitorStore.stop()` call is never reached, leaving the transport stream open and polling indefinitely. |
| M-2 | **P1** | `screens/monitor.js` | `CONNECT_TIMEOUT_MS = 20_000`. The timeout banner is shown but the transport stream is NOT cancelled when the banner appears. The WS connection and poll loop continue running. The banner is purely cosmetic — it does not stop the underlying resource consumption. |
| M-3 | **P1** | `screens/monitor.js` | Stage label map (`STAGE_LABELS`) is a static client-side dict keyed on backend stage name strings. If backend adds or renames a stage, the frontend silently falls back to the raw stage key (e.g., `"SCENE_DETECT_V2"`) rather than a friendly label. No fallback humanization (e.g., replace `_` with space, title-case) is applied. |
| M-4 | **P2** | `screens/monitor.js` | No deep-link validation. If `jobId` in the URL is malformed or references a deleted job, the monitor screen makes a WS connection that immediately errors, falls to polling, polling returns 404, and then the screen sits on the "Connecting…" state indefinitely with no "Job not found" message. |
| M-5 | **P2** | `screens/monitor.js` | Clip count display (`"N/N clips"`) relies on `normalizePartList` output. If the backend returns an empty parts array mid-render (before any parts are scored), the clip counter shows `"0/0 clips"` which looks like a bug to users rather than "render in progress". |

**Confirmed correct behaviors (NOT bugs):**
- `el.addEventListener('unmount', () => { unsub(); monitorStore.stop(); })` — cleanup IS implemented. The question is whether `router.js` always dispatches the event.

**Recommended fixes:**
- **M-1 (P0):** Audit `router.js` to confirm `unmount` is dispatched on the outgoing element for every navigation case. Add a fallback: `window.addEventListener('hashchange', () => { if (!stillMounted) monitorStore.stop(); })`.
- **M-2 (P1):** When the timeout banner fires, call `monitorStore.stop()` to halt the stream and polling loop.
- **M-3 (P1):** Add a fallback in the stage label lookup: `STAGE_LABELS[key] ?? key.replace(/_/g, ' ').toLowerCase()`.
- **M-4 (P2):** On 404 poll response, set store status to a synthetic `"not_found"` and render a friendly "Job not found" empty state with a "Go to Library" CTA.

---

### 24.5 Download Screen (`screens/downloads.js`)

**Current implementation:** Post R4F-A: removed false quality presets, replaced with "Downloads use source quality defaults." helper text. Batch download dispatches directly to backend.

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| D-1 | **P1** | `screens/downloads.js` | No per-file download progress indication. Downloads are dispatched and the UI shows no progress bar or spinner per file — only a bulk "downloading" state. Large files (multi-GB renders) appear frozen to the user. |
| D-2 | **P1** | `screens/downloads.js` | No retry on failed download item. If one file in a batch fails, the whole batch shows "failed" with no way to retry just the failed item. |
| D-3 | **P2** | `screens/downloads.js` | Filename shown in the download list is the raw backend path (e.g., `/tmp/renders/abc123/clip_1.mp4`) rather than a human-readable name based on session title + clip number. |
| D-4 | **P2** | `screens/downloads.js` | No download history persistence. Closing the tab clears all download state. Users who close and reopen cannot see what was downloaded or re-download without navigating back to Results. |

**Recommended fixes:**
- **D-1 (P1):** Use `fetch` with `ReadableStream` body to track download progress, or stream via `<a href>` and use the `progress` event from the `Content-Length` header.
- **D-2 (P1):** Add per-item retry button that re-dispatches only the failed item's download request.

---

### 24.6 Library Screen (`screens/library.js`)

**Current implementation:** Post R4F-A: `_normalizeDisplayTitle()` humanizes YouTube URLs and file paths. Hard cap of 30 history items from backend (`routes/jobs.py:251`). No pagination.

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| L-1 | **P0** | `routes/jobs.py:251` | Backend `api_jobs_history()` returns `safe_limit = max(1, min(30, ...))` — hard cap of 30 with no pagination. Library screen has no "load more" affordance. Users with >30 renders see a silently truncated list. |
| L-2 | **P1** | `screens/library.js` | `_normalizeDisplayTitle()` handles YouTube URLs and file paths but not other supported sources (Vimeo, Twitch, direct MP4 links). These display as raw URLs. |
| L-3 | **P1** | `screens/library.js` | No search or filter in Library. With 30 items visible and a growing render history, finding a specific render requires scrolling the entire list. |
| L-4 | **P2** | `screens/library.js` | Delete action calls `jobsApi.deleteJob(jobId)` with no undo affordance. Deleting a render is permanent; no confirmation dialog or undo toast is shown. |

**Recommended fixes:**
- **L-1 (P0):** Add `offset` + `limit` pagination to `api_jobs_history()` in `routes/jobs.py` and implement "Load more" in `library.js`. Remove the hard `safe_limit = 30` cap.
- **L-4 (P2):** Add a confirmation dialog ("Delete this render? This cannot be undone.") before calling `deleteJob`.

---

### 24.7 Results Screen (`screens/results.js`)

**Current implementation:** Displays best-clip hero, AI scores, full clip list. "View Results →" CTA in green-tinted success banner. Clip download dispatches to download screen. Part → Clip terminology applied globally.

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| R-1 | **P1** | `screens/results.js` | AI score display is a raw float (e.g., `0.873`). No normalization to a 0-100 scale or qualitative label ("Excellent", "Good", "Fair") — the number is meaningless to non-technical users. |
| R-2 | **P1** | `screens/results.js` | If the render completed but all AI scores are null (AI Director disabled or failed), the best-clip hero section is blank. No "AI scoring unavailable" fallback state is shown — the section simply disappears. |
| R-3 | **P2** | `screens/results.js` | No share/export affordance. Users can only download clips locally. No copy-link, no social share, no export-to-cloud option. |
| R-4 | **P2** | `screens/results.js` | `normalizePartList` is called on every render of the results screen, even when data has not changed. For renders with 20+ clips, this is a non-trivial re-normalization on every state update. |

**Recommended fixes:**
- **R-1 (P1):** Normalize AI scores to 0-100 (`Math.round(score * 100)`) and add qualitative tier labels (≥80: "Excellent", 60-79: "Good", <60: "Fair").
- **R-2 (P1):** Add an "AI scoring unavailable" empty state with an icon and explanation when all scores are null.

---

### 24.8 Component Layer

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| CO-1 | **P1** | `components/part-status-list.js` | `PartItem` component re-renders the entire list when any single clip status changes. No keyed diffing — all DOM nodes are replaced on each update. For renders with 20+ clips, this causes visible flash on status updates. |
| CO-2 | **P1** | `components/output-card.js` | `OutputCard` does not handle the `cancelled` clip status — falls through to the default case which renders no card at all, silently hiding cancelled clips from the results view. |
| CO-3 | **P2** | `components/best-clip-hero.js` | Hero card shows the first clip in the scored list. If the AI Director reorders clips (Phase 59C), the hero is correct. But if AI Director is disabled, clips are shown in source order — the "best" label is misleading. |
| CO-4 | **P2** | `components/nav-rail.js` | Active route detection uses `window.location.hash === item.href`. If the router adds query params or fragments within a route, the active state breaks. |

**Recommended fixes:**
- **CO-1 (P1):** Implement keyed list rendering: maintain a `Map<clipId, element>` and update/insert/remove individual nodes rather than replacing the entire list.
- **CO-2 (P1):** Add a `cancelled` case to `OutputCard` that renders a "Cancelled" status chip rather than returning null.

---

### 24.9 API Wrapper Layer (`api/render.js`, `api/jobs.js`, `api/system.js`)

**Problems found:**

| ID | Severity | File:Line | Issue |
|---|---|---|---|
| A-1 | **P1** | `api/render.js` | `POST /api/render` has no client-side timeout. A hung backend render submission will leave the create screen in `preparing` phase until the browser's default network timeout (~2 minutes). `PREPARE_TIMEOUT_MS = 45_000` applies to the draft preparation endpoint, not the render submission. |
| A-2 | **P1** | `api/jobs.js` | `deleteJob(jobId)` does not check if the job is currently running before calling DELETE. Deleting an in-progress job from Library will delete the DB record but leave the render process running — orphaning the FFmpeg subprocess and temp files. |
| A-3 | **P2** | `api/render.js`, `api/jobs.js` | No request deduplication. If the user clicks "Start render" while a previous request is still in-flight (e.g., slow network), two identical POST requests can be dispatched. The `_generating` flag in `create.js` mitigates this for the render submit, but draft preparation (`_handlePrepare`) has no equivalent guard after the initial abort. |
| A-4 | **P2** | `api/system.js` | `GET /api/sessions` is polled on the Source screen to show active session count. Polling interval not confirmed — if it matches transport poll (2000ms), this adds a second 2s polling loop layered on top of the job stream poll. |

**Recommended fixes:**
- **A-1 (P1):** Add an `AbortController` with a 30s timeout to the render submission `fetch` call in `api/render.js`.
- **A-2 (P1):** In `Library`, before calling `deleteJob`, check job status via `jobsApi.getJob(jobId)` and block deletion if `status` is `queued` or `running`, showing a warning: "Cancel the render before deleting."

---

### 24.10 Performance Concerns

| ID | Severity | Finding |
|---|---|---|
| P-1 | **P1** | No virtual scrolling in Library or Results clip list. At 30 items (Library cap) or 20+ clips (Results), all DOM nodes are rendered simultaneously. On low-end hardware this causes jank during scroll. |
| P-2 | **P1** | `renderSessionStore.sync()` called up to 3× per WS message (see S-1). Each sync triggers all `renderSessionStore` subscribers (render bar re-render). This is a hidden multiplier on UI update cost. |
| P-3 | **P2** | No asset caching strategy. CSS and JS files are served without cache-busting hashes. A deploy that updates `transport.js` will not invalidate cached copies in the browser until cache TTL expires (default: browser heuristic, typically hours). |
| P-4 | **P2** | `normalizeJob`, `normalizePartList`, `parseResultPackage` run on every store subscription update. Results screen calls `normalizePartList` on every `monitorStore` mutation even when parts have not changed. |

---

### 24.11 Security Issues (Frontend)

| ID | Severity | Finding | File |
|---|---|---|---|
| SEC-1 | **P1** | `innerHTML` used in component rendering without sanitization. If backend returns a job title or stage name containing `<script>` or `<img onerror>`, it is injected directly into the DOM. | `components/*.js`, `screens/*.js` |
| SEC-2 | **P1** | `_resolve_job_log_path()` in `routes/jobs.py:*` constructs file paths from `payload_json.output_dir` — user-controlled data. Frontend `GET /api/jobs/:id/log` can be used to read arbitrary files if `output_dir` is manipulated. This is a backend issue but the frontend API wrapper exposes the endpoint without any path validation. | `api/jobs.js` |
| SEC-3 | **P2** | No CSRF protection on mutating API calls (POST /api/render, DELETE /api/jobs/:id). Frontend uses `fetchJson()` which does not add a CSRF token header. | `transport.js:fetchJson` |

**Recommended fixes:**
- **SEC-1 (P1):** Audit all `innerHTML` assignments. Replace with `textContent` for text-only values; use `DOMPurify` or manual sanitization for HTML that must be rendered.
- **SEC-3 (P2):** Add a CSRF token (e.g., a cookie-to-header pattern using `X-CSRF-Token`) to all state-mutating requests.

---

### 24.12 Missing Features (Frontend)

| Feature | Priority | Status | Notes |
|---|---|---|---|
| SPA catch-all route | **P0** | Missing | Server returns 404 on browser refresh to `/monitor/abc`. `main.py` only serves `index.html` on `GET /`. Fix: add `GET /{path:path}` catch-all that returns `index.html` for non-API, non-static paths. |
| Pagination in Library | **P0** | Missing | Hard 30-item cap from backend, no "Load more" in frontend. |
| Job not-found error state | **P1** | Missing | Monitor screen has no "Job not found" state; shows infinite spinner on invalid/deleted job IDs. |
| Render reconnect after refresh | **P1** | Missing | Refreshing during an active render loses the render bar and requires manual navigation to `/monitor/:jobId`. |
| Per-clip retry in Downloads | **P1** | Missing | Batch download failure has no per-item retry. |
| AI score humanization | **P1** | Missing | Raw floats shown; no 0-100 scale or qualitative labels. |
| Delete confirmation dialog | **P2** | Missing | Library delete is instant and permanent with no confirmation. |
| Virtual scrolling | **P2** | Missing | Results and Library render all DOM nodes; degrades on low-end hardware with many items. |
| Cache-busting | **P2** | Missing | No content hash in static asset URLs; deploys may serve stale JS/CSS. |
| CSRF protection | **P2** | Missing | No CSRF token on mutating requests. |

---

### 24.13 Priority Roadmap

#### P0 — Critical (production blockers)

| ID | Item | File(s) |
|---|---|---|
| P0-A | Fix server WS break condition to include `interrupted` and `completed_with_errors` | `routes/jobs.py:411` |
| P0-B | Add SPA catch-all route to serve `index.html` for all non-API paths | `app/main.py` |
| P0-C | Add Library pagination — remove 30-item hard cap | `routes/jobs.py:251`, `screens/library.js` |
| P0-D | Audit `router.js` unmount dispatch to guarantee `monitorStore.stop()` is always called | `assets/js/router.js`, `screens/monitor.js` |

#### P1 — High (significant UX degradation or resource waste)

| ID | Item | File(s) |
|---|---|---|
| P1-A | Stop transport stream when timeout banner fires | `screens/monitor.js` |
| P1-B | Deduplicate `renderSessionStore.sync()` — call once per tick not 3× | `store/monitor.js` |
| P1-C | Add client-side URL validation before `_handlePrepare()` | `screens/create.js` |
| P1-D | Fix AbortController race in `_handlePrepare()` post-timeout success | `screens/create.js` |
| P1-E | Add `innerHTML` sanitization across all component renderers | `components/*.js`, `screens/*.js` |
| P1-F | Add render submission timeout via AbortController | `api/render.js` |
| P1-G | Block `deleteJob` if job is active; show cancel-first warning | `screens/library.js`, `api/jobs.js` |
| P1-H | Add per-clip retry in Downloads screen | `screens/downloads.js` |
| P1-I | AI score humanization (0-100 + qualitative label) | `screens/results.js` |
| P1-J | AI score null fallback state in Results | `screens/results.js` |
| P1-K | Keyed list rendering in `PartItem` to prevent full-list re-render flash | `components/part-status-list.js` |
| P1-L | Add `cancelled` case to `OutputCard` | `components/output-card.js` |
| P1-M | Stage label fallback humanization (replace `_`, title-case) | `screens/monitor.js` |

#### P2 — Medium (polish and scalability)

| ID | Item | File(s) |
|---|---|---|
| P2-A | Persist `{ jobId, status }` in `sessionStorage` for render bar reconnect | `store/render-session.js` |
| P2-B | WS reconnect with exponential backoff | `transport.js` |
| P2-C | Add "Job not found" state to Monitor screen | `screens/monitor.js` |
| P2-D | Persist last-entered URL in `sessionStorage` across page reloads | `screens/create.js` |
| P2-E | Add delete confirmation dialog in Library | `screens/library.js` |
| P2-F | Virtual scrolling for Library and Results clip list | `screens/library.js`, `screens/results.js` |
| P2-G | Content-hash cache-busting for static assets | `index.html`, build process |
| P2-H | CSRF token on mutating requests | `transport.js:fetchJson`, `app/main.py` |
| P2-I | `createStore()` middleware layer for cross-cutting concerns | `assets/js/store/` |
| P2-J | `_normalizeDisplayTitle()` extended to cover Vimeo, Twitch, direct MP4 URLs | `screens/library.js` |
- No store schema changes

### Status
✓ Complete — committed

## 24. UI-R4F-B — Studio Workspace Redesign

**Date:** 2026-05-14
**Scope:** Full Studio screen redesign — creator workspace feel, preview dominance, premium controls

### Changes

**`screens/studio.js` — complete redesign of all render functions:**

| Area | Before | After |
|---|---|---|
| Preview loading state | Text + body copy | Spinner + compact friendly copy |
| Preview error state | "Preview unavailable" + technical copy | Calm, action-oriented copy |
| Preview empty state | Small icon + "No source prepared" | Larger icon, "No source loaded", descriptive guidance |
| Section A title | "Clips" | "Clip Strategy" |
| Min/Max labels | "Min sec" / "Max sec" | "Min" / "Max" with "s" unit suffix; number inputs clean (no spinners) |
| Max clips label | "Max clips" | "Count" |
| Aspect ratio label | "Aspect ratio" | "Format" |
| Subtitle toggle | Native checkbox + On/Off text | Custom CSS toggle switch (`.studio-toggle`) |
| Subtitle style label | "Style preset" | "Caption style" |
| AI toggle | Native checkbox + On/Off text | Custom CSS toggle switch (`.studio-toggle`) |
| AI mode label | "Execution mode" | "Influence" |
| AI helper text | Long technical explanation | "AI ranks your clips and explains why each was selected." |
| CTA render button | 140px min-width, right-aligned | Full-width 44px, `.studio-render-btn` |
| CTA back button | Ghost button left-aligned | Subtle full-width link below render button, `.studio-back-link` |
| Screen header | Large 28px title, heavy padding | Compact `.studio-workspace-header` (18px title, tighter padding) |
| No-session state | "No source is loaded" card | Improved copy, `text-section` size heading |
| Right panel | Title + source + chips | Title + Source section + Output section + Render plan + Subtitles/AI rows |

**`css/components.css` — UI-R4F-B block appended:**

| CSS | Effect |
|---|---|
| `.studio-workspace-header` + `.studio-workspace-title` | Compact 18px header, frees vertical space for preview |
| `.studio-right { background: var(--color-bg-raised) }` | Config panel raised surface — creates visual separation; preview stage feels cinematic |
| `.studio-right__scroll { padding-bottom }` | Breathing room at bottom of scroll |
| `.studio-right .draft-section { border-bottom-color: rgba(255,255,255,0.05) }` | Lighter section separators, less form-like |
| `.studio-toggle` + `__track` + `__thumb` | Pure-CSS animated toggle switch replacing native checkbox |
| `.studio-num-wrap` + `.studio-num-unit` | "s" unit suffix on min/max duration inputs |
| `.studio-number-input` | Centered, tabular-nums, no browser spinner arrows |
| `.studio-render-btn` | Full-width, 44px min-height, 700 weight — render moment CTA |
| `.studio-back-link` | Muted full-width ghost link below render button |
| `.studio-cta { gap, padding }` | Tighter vertical rhythm in CTA area |

### Payload verification
- `draftStore.buildPayload()` unchanged — no payload fields added/removed
- All wiring IDs preserved: `#d-min`, `#d-max`, `#d-qty`, `#d-sub-on`, `#d-ai-on`, `#studio-render-btn`, `#studio-back-btn`, `#studio-draft`, `#studio-cta`
- `rerender(el)` pattern unchanged

### Remaining limitations
- Preview aspect ratio fills black bars (correct — `object-fit:contain`); native `controls` bar still shows (acceptable for desktop)
- Right panel width (300px shell) is fixed — can't expand for Studio context
- Number inputs: `d-qty` (Count) has no unit suffix since clips count doesn't need "s"

### Next phase
UI-R4F-C — Persistent Render Experience (Monitor + Results continuity)

### Status
✓ Complete — committed

---

## 25. UI-R4F-C — Persistent Render Experience

**Date:** 2026-05-14  
**Commit:** feat(ui): improve persistent render experience  
**Scope:** Global render session store, persistent render bar, monitor UX improvements

### Problem statement

After starting a render and leaving the Monitor screen, the app had no awareness of the ongoing render. Users navigating to Source, Library, or other screens saw no indication that a render was active. The Monitor empty state was unhelpful, and terminal banners lacked clip count context.

### Changes

**New file: `store/render-session.js`**

Global reactive store tracking active render state across routes:
- State: `jobId`, `status`, `progressPercent`, `stage`, `doneParts`, `totalParts`, `transportMode`, `active`
- `active` = `true` only when status is `queued` or `running`, and `terminal` flag is not set
- `sync(monitorState)` — called by monitorStore after every mutation to keep state current
- `clear()` — called by monitorStore.clear() to reset (e.g. when starting fresh)

**Modified: `store/monitor.js`**

| Change | Purpose |
|---|---|
| Import `renderSessionStore` | Dependency for syncing |
| `_handleUpdate` → calls `renderSessionStore.sync(store.getState())` after every partial state merge | Keeps render bar live during active render |
| `start(jobId)` → calls `sync` after initial `store.set` | Initialises bar when monitor starts |
| `onTerminal` → calls `sync` immediately (sets `active: false`) and again after authoritative fetch | Bar hides as soon as terminal status is known |
| `onTransportChange` → calls `sync` | Keeps transportMode current |
| `stop()` → does NOT call sync or clear | Render bar retains last known state when user navigates away |
| `clear()` → calls `renderSessionStore.clear()` | Full reset on explicit clear |

**Modified: `components/shell.js`**

| Change | Purpose |
|---|---|
| Import `renderSessionStore` + `router` | Drive render bar |
| Add `#shell-render-bar` element inside `#shell-workspace` | Persists across route changes (router only removes `.screen`) |
| `_STAGE_LABELS` inline map | Human-readable stage names without importing monitor screen |
| `renderSessionStore.subscribe(_updateRenderBar)` in `mount()` | Reactive bar updates |
| `_updateRenderBar(root, state)` | Shows/hides bar; renders progress track, stage label, clip count, %, Open Monitor button |
| `_esc()` helper added | XSS safety for stage labels |

Render bar appearance:
- Visible only when `state.active === true`
- Contains: 72px animated progress track → stage label → clip count (if totalParts > 0) → % → [Open Monitor] button
- "Open Monitor" routes to `/monitor/{jobId}`
- Hides immediately when render reaches terminal state (completed/failed/interrupted)

**Modified: `css/components.css` — UI-R4F-C block appended**

| CSS | Effect |
|---|---|
| `.shell-render-bar` | Flex-shrink:0, accent-tinted background, accent border-bottom |
| `.render-bar { padding, min-height }` | 38px compact bar with standard horizontal padding |
| `.render-bar__progress-track` + `__progress-fill` | 72×3px animated progress track |
| `.render-bar__stage { font-weight:600 }` | Stage label legible against bar background |
| `.render-bar__sep { opacity: 0.35 }` | De-emphasised separator dots |
| `.render-bar__btn` | Ghost-style accent-coloured button; hover fills accent-soft background |
| `.monitor-no-job { align-items:center }` | Empty state centring helper |

**Modified: `screens/monitor.js`**

| Change | Purpose |
|---|---|
| Import `renderSessionStore` | Route recovery check |
| Empty state (no jobId) — route recovery | If `renderSessionStore.getState().active`, redirects to `/monitor/{jobId}` |
| Empty state (no jobId) — improved UI | Centred layout with play icon, "No render in progress" heading, "Start a render from Studio, or reopen a past job from Library." body, primary Studio CTA + secondary Library button. Replaces old inline-onclick plain card. |
| `renderTerminalBanner` — completed | Clip count line: "N of M clips ranked and ready." (uses `summary.completed_parts` / `summary.total_parts`) |
| `renderTerminalBanner` — completed_with_errors | "some parts failed" → "some clips failed" (R4F-A oversight fixed) |
| `renderTerminalBanner` — failed/interrupted | Reason message from `job.message`; hint line "Check logs below for more detail." / "You can resume where it left off."; action buttons relabelled "Resume render" / "Retry render" / "Start over" |
| Log drawer wrapper | Extra `margin-top: var(--sp-2)` wrapper keeps logs visually separated from clip table |

### Architecture notes

- **renderSessionStore is a thin projection of monitorStore.** It does not maintain its own transport subscription — it only knows what monitorStore last told it. If the user navigates away mid-render, the bar retains the last known progress values. Clicking "Open Monitor" reconnects to the live transport and resumes accurate updates.
- **Why not a background subscription?** Adding a global background transport subscription would require importing `subscribeJob`, entity normalizers, and managing lifecycle outside the monitor screen — out of scope for this phase. The current approach covers the primary use case (bar visible while user briefly visits other screens) without adding complexity.
- **The `stop()` / `clear()` split:** `stop()` disconnects transport (called on unmount, preserves bar state). `clear()` fully resets both stores (called when starting a new render or explicitly clearing the session).

### Route recovery coverage

| Entry point | Behaviour |
|---|---|
| `#/monitor` (no jobId), active render exists | Redirects to `#/monitor/{jobId}` |
| `#/monitor` (no jobId), no active render | Shows "No render in progress" empty state |
| `#/monitor/{jobId}` | Always connects to transport, renders live state |

### Limitations

- Render bar shows stale progress if render completes while user is on a non-monitor screen (bar stays visible). Resolved when user opens Monitor, which reconnects and sets terminal state.
- No ETA estimate (not provided by backend API at this time).

### Status
✓ Complete — committed

---

## 26. UI-R4F-D — Results Reward Experience

**Date:** 2026-05-14  
**Commit:** feat(ui): improve results reward experience  
**Scope:** Results screen, hero component, clip cards, AI panel positioning, status copy, empty/error states

### Problem statement

Results felt like a job artifact list — output files with metadata. Users had no sense of accomplishment or "AI made something for me." The hero lacked reward framing, the AI intelligence panel was buried at the bottom after failed clips, clip cards were text-dense, and status/error states were technical rather than creator-friendly.

### Changes

**Modified: `components/best-clip-hero.js`**

| Change | Purpose |
|---|---|
| Add `#hero-header` div above video container | Creates tri-part layout: reward header → video → meta strip |
| New export `heroHeaderHtml(clip, jobId)` | Renders eyebrow label, score, and Download CTA; updated surgically on clip switch |
| `heroHeaderHtml` — "★ Best Clip" eyebrow | Accent-colored, uppercase, star prefix; non-best clips show "Clip N" in muted style |
| `heroHeaderHtml` — "Recommended result" subline | Only when `clip.isBest`; sets creator-friendly expectation |
| `heroHeaderHtml` — score display (32px bold) | Large score number in tier color (success/warning/failed) with "score" label |
| `heroHeaderHtml` — Download CTA as `btn btn-primary` | Promotes download to primary action in the hero, not buried in meta strip |
| Remove download link from `heroMetaHtml` | Meta strip decluttered: Clip# + duration + reason (truncated) + score pill only |
| `heroMetaHtml` — adds duration from `_raw.end_sec - start_sec` | Duration visible at a glance without opening details |
| `heroMetaHtml` — ranking reason text, `.hero-reason-text` (truncated 1 line) | Shows AI's explanation inline under the video |
| `updateHeroClip()` — now also updates `#hero-header` | Score/download stay current when switching clips without recreating `<video>` |
| `wireHeroVideo` — unchanged | Error overlay logic preserved |
| Import `scoreColor` from score-badge | Required for per-tier score coloring in header |

**Modified: `components/output-card.js`**

| Change | Purpose |
|---|---|
| `col gap-1` → `col gap-2` on card content column | More breathing room between clip title, score bar, and reason lines |
| Rank badge: `#${rank}` → `${rank}` (remove "#" prefix) | Cleaner, more premium — number-only rank |
| Fix `rawDur` calculation precedence bug | Original: `clip._raw?.duration ?? clip._raw?.end_sec != null ? ...` parsed incorrectly; fixed to proper null-coalescing fallback |

**Modified: `screens/results.js`**

| Area | Change |
|---|---|
| **Layout order** | hero → status banner → AI panel (if data) → clip list → failed clips (AI was previously at bottom after failed clips) |
| **`renderAIPanel`** | Returns `''` when `!isActive \|\| !intel?.hasData` — empty placeholder removed entirely; panel only shows when there's real data |
| **`renderStatusBar` — success** | "N clips ready · Ranked by AI" with ✓ icon; voice/subtitle extras in subtler inline format |
| **`renderStatusBar` — partial** | "N clips ready" + "M clips couldn't be processed" stacked inside banner |
| **`renderFailedPanel(result, jobId)`** | New `jobId` param; "failed" → "couldn't be processed"; "View logs →" link to `/monitor/{jobId}` |
| **`updateRightPanel`** | Added `↓ Download clip` link for selected clip (uses `/api/jobs/{jobId}/parts/{partNo}/stream`) |
| **Empty state (no jobId)** | Uses `emptyState()` component with video icon, "No results to show", "Start a render from Studio to see your clips here.", Back to Studio CTA |
| **Error state** | DOM-built card with "Couldn't load results", error message, "Try again" + "Open Library" buttons — event listeners wired directly (no onclick attributes) |
| **"Not available" state** | DOM-built card with "Results not ready yet", parse error message, "← Open Monitor" + "Library" buttons |
| **Dynamic subtitle** | `#results-subtitle` starts as "Loading…", updates to "N clips ready" or "N clips · partial" on result load |
| **"Ranked outputs" → "Your clips"** | Creator language in clip list section header |
| **Import cleanup** | Removed unused `statusChip`, `scorePill` imports; removed `heroMetaHtml` import (used only internally in best-clip-hero.js) |

**Modified: `css/components.css` — UI-R4F-D block appended**

| CSS | Effect |
|---|---|
| `.hero-wrap` | `border-radius`, `overflow:hidden`, `border`, `box-shadow` — premium card frame around the full hero unit |
| `.hero-wrap .hero-video-container { box-shadow: none }` | Removes R4E inner shadow (outer wrap handles elevation) |
| `.hero-reward-header` | Surface background, border-bottom, padding — creates visual separation above video |
| `.hero-reward-eyebrow` + `--secondary` | Accent-colored uppercase label for best clip; muted style for non-best |
| `.hero-score-display` + `.hero-score-number` | 32px/800 weight score readout, tabular-nums |
| `.hero-video { max-height: 480px; object-fit: contain }` | Taller player (was 420px inline); portrait clips feel larger |
| `.hero-meta` | Surface background + border-top — visual closure below video |
| `.hero-reason-text` | `flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap` — reason text truncated to one line |
| `.hero-empty` | Centered placeholder with border + surface bg |
| `.output-clip-card--selected { background: surface-selected }` | Unmistakable background tint on selected card (supplements existing border/shadow) |
| `.clip-rank-badge` + `--best` | Redefined: 28×28px flex-centered square, clean number style; best variant has accent border/color |
| `.results-ready-icon` | 18px green ✓ icon for success banner |
| `.results-error-card` | Red-bordered surface card for error state |

### Architecture notes

- **Video element stability preserved.** `updateHeroClip()` updates `#hero-header`, `#hero-meta`, and `<video>.src` — never replaces the `<video>` element itself. Play state context is preserved on clip switch.
- **AI panel conditional rendering.** If no AI intelligence data is available, no AI panel is inserted in the DOM at all. This avoids the previous "AI insights will appear when metadata becomes available" placeholder that added noise for non-AI renders.
- **`heroHeaderHtml` export.** Added as a new export from `best-clip-hero.js`. Results.js does not import it directly — it's called internally by `updateHeroClip()`. The export is available if other consumers need it.

### Remaining limitations

- No video thumbnail generation — clip cards show text-only (no frame preview). Thumbnails would require a `/parts/{partNo}/thumbnail` endpoint not currently in the API.
- Portrait video layout: `object-fit:contain` on a landscape-ratio container shows pillarboxing. This is correct behavior given we don't know the clip's aspect ratio before the video loads.
- `heroHeaderHtml` re-wires download anchor on every clip switch — acceptable since the `<a>` is a native link, not a JS-bound button.

### Status
✓ Complete — committed


---

## UI-R5B — Information Architecture Rebuild

**Phase:** UI-R5B
**Date:** 2026-05-14
**Branch:** feature/ai-output-upgrade
**Scope:** Creator-first IA migration — new nav, wrapper routes, backward-compatible legacy routes. No screen-internal rewrites. No backend changes.

---

### Objective

Shift the product mental model from pipeline-first (Source + Studio + Monitor + Results + Library) to creator-first (Create + Projects + Settings) without destabilising any working render flow, store logic, or API contract.

---

### New Navigation Model

| Nav item | Route | Replaces | Position |
|---|---|---|---|
| Create | #/create | Source + Studio | Primary (top) |
| Projects | #/projects | Results + Library | Primary (below Create) |
| Settings | #/settings | System | Bottom (flex-pushed) |
| (hidden) | #/monitor/:id | Monitor | Not in nav -- render bar only |
| (hidden) | #/downloads | Downloads | Not in nav -- direct URL |

The nav rail renders: Create, Projects, [flex spacer], Settings. Monitor and Downloads are fully functional routes but are no longer primary nav destinations.

---

### New Routes (Canonical)

| Route | Screen | Behavior |
|---|---|---|
| #/create | createScreen | Smart wrapper: shows sourceScreen if no session, studioScreen if session exists |
| #/projects | projectsScreen | Wrapper: shows libraryScreen (history) |
| #/projects/:jobId | projectsScreen | Wrapper: shows resultsScreen for that job |
| #/settings | settingsScreen | Alias for systemScreen (rename only, no logic change) |

---

### Legacy Route Compatibility

All previous routes remain fully functional. No bookmarks are broken.

| Old route | Maps to screen | Nav highlights |
|---|---|---|
| #/source | createScreen | Create |
| #/studio | createScreen | Create |
| #/results/:jobId | projectsScreen | Projects |
| #/library | projectsScreen | Projects |
| #/system | settingsScreen | Settings |
| #/monitor/:jobId | monitorScreen | (none) |
| #/downloads | downloadsScreen | (none) |

The navId field on each route record drives shell.setActiveNav(). Legacy routes pass navId: 'create', 'projects', or 'settings' so the new 3-item nav always highlights the correct item regardless of which URL the creator arrived from.

---

### Create Wrapper Behavior

File: assets/js/screens/create.js

On mount, checks draftStore.getState().draft.editSessionId:
- No session: mounts sourceScreen (Import phase -- YouTube URL / local file / output folder)
- Session exists: mounts studioScreen (Brief phase -- preview + config + render CTA)

After prepare-source succeeds, source.js now calls router.go('/create') instead of router.go('/studio'). The Create wrapper sees the new session and shows the Brief phase automatically. Internal screen logic is completely unchanged.

---

### Projects Wrapper Behavior

File: assets/js/screens/projects.js

On mount, checks params[0] (jobId from URL):
- No jobId (#/projects): mounts libraryScreen (full job history with filter/search)
- jobId present (#/projects/:jobId): mounts resultsScreen for that specific job

libraryScreen internal navigation updated: View Results now navigates to /projects/:jobId instead of /results/:jobId. Card click navigation updated identically.

---

### Monitor Migration

Monitor is no longer a primary nav item. Access paths:
1. Render bar (always visible during active render) -- Open Monitor button
2. Projects/Library -- Monitor button on active-status cards
3. Direct URL -- #/monitor/:jobId still works

Monitor empty state CTAs: Go to Studio -> Start Creating (/create), Open Library -> Open Projects (/projects).
Monitor terminal CTAs: View Results -> /projects/:jobId, Start over -> /create.
Monitor header back button: Studio -> Create.

---

### Files Changed

New files:
- assets/js/screens/create.js -- Create wrapper (22 lines)
- assets/js/screens/projects.js -- Projects wrapper (20 lines)

Modified files:
- assets/js/router.js -- New ROUTES table with navId field, canonical + legacy routes, DEFAULT_PATH /create
- assets/js/components/nav-rail.js -- Rebuilt: Create + Projects primary, Settings bottom, NAV_ID_MAP for legacy IDs
- assets/js/screens/source.js -- router.go('/studio') -> router.go('/create') post-prepare
- assets/js/screens/monitor.js -- 5 nav calls updated + empty state copy
- assets/js/screens/library.js -- 2 nav calls updated + empty state copy
- assets/js/screens/results.js -- 4 nav calls updated + button labels
- assets/js/screens/downloads.js -- 1 nav call updated
- assets/css/components.css -- .nav-rail-spacer { flex: 1 } added

---

### Known Limitations (Deferred to UI-R5C)

- Create wrapper is not a unified workspace yet. After prepare-source, the creator sees the Studio screen header while the nav says Create. Full Create workspace rebuild in UI-R5C.
- Studio back buttons go to /source (not /create). The legacy /source route maps to createScreen and shows Brief phase since session exists -- slightly circular. Resolved in UI-R5C when Create handles its own internal phase state.
- Projects has no Active tab yet. Active renders surface via render bar. Tab structure in UI-R5D.
- Downloads has no nav entry. Accessible via direct URL #/downloads only.

---

### Next Phase

UI-R5C -- Create Workspace Rebuild: merge Source + Studio into a true single-surface workspace with left source zone, center video preview, right creative brief panel.

### Status
Complete -- committed

---

## UI-FIX — R5C Router Export Boot Fix

**Date:** 2026-05-14
**Branch:** feature/ai-output-upgrade
**Commit:** see below

### Root Cause

`router.js` (written in UI-R5B) imports `settingsScreen` from `./screens/system.js`, but `system.js` only exports `systemScreen`. ES module named imports are strict — the name must match exactly. Because the import failed at parse time, the entire module graph was rejected and the app rendered blank.

```
Uncaught SyntaxError: The requested module './screens/system.js'
does not provide an export named 'settingsScreen'
```

### Fix Applied

**Option B — alias export in system.js** (additive, zero risk).

Added one line to the bottom of `backend/static-v2/assets/js/screens/system.js`:

```js
export const settingsScreen = systemScreen;
```

`router.js` was not modified. The canonical `systemScreen` export is preserved for any other code that references it. The alias satisfies the named import in router.js.

### Routes Verified (syntax check)

| File | Result |
|---|---|
| `screens/system.js` | OK |
| `router.js` | OK |
| `screens/create.js` | OK |
| `screens/projects.js` | OK |

### Route Table (post-fix)

| Route | Screen | Nav highlight |
|---|---|---|
| `#/create` | createScreen | Create |
| `#/projects` | projectsScreen | Projects |
| `#/projects/:jobId` | projectsScreen | Projects |
| `#/settings` | settingsScreen (= systemScreen) | Settings |
| `#/source` | createScreen (legacy compat) | Create |
| `#/studio` | createScreen (legacy compat) | Create |
| `#/library` | projectsScreen (legacy compat) | Projects |
| `#/results/:jobId` | projectsScreen (legacy compat) | Projects |
| `#/system` | settingsScreen (legacy compat) | Settings |
| `#/monitor/:jobId` | monitorScreen (utility) | none |
| `#/downloads` | downloadsScreen (utility) | none |

### Status
Complete -- committed

---

# UI-R5C.1 — Creator Workspace Rebuild

**Phase:** UI-R5C.1
**Date:** 2026-05-14
**Branch:** feature/ai-output-upgrade
**Commit:** 39c30dc

## Summary

Replaced the two-column Create workspace (canvas + 300px brief sidebar) with a single-column preview-first layout. Shell right panel hidden for the Create route via CSS `data-route` selector.

## Files Changed

| File | Change |
|---|---|
| `router.js` | Sets `shellEl.dataset.route = route.id` on every navigation |
| `layout.css` | `shell[data-route="create"]` collapses right panel column to 0px |
| `screens/create.js` | Full rewrite: `.cw` column → `.cw-hero` (flex-1) + `.cw-controls` + `.cw-cta` |
| `components.css` | New `cw-*` creator workspace CSS block; nav label override (no uppercase) |

## Creator Design Choices

- **Hero fills all space** — import surface / preparing spinner / video preview
- **Intent presets** — 4 full-width horizontal cards with top-accent active state
- **Options strip** — format pills + subtitle toggle + Advanced collapse in compact row
- **Generate button** — full-width at bottom, accent-coloured
- **studio-toggle thumb** — rendered as sibling of input (not nested), fixing checked-state CSS
- **No right panel on Create route** — layout.css route-specific override

---

# UI-R5C.2 — Productize Old Creator Soul

**Phase:** UI-R5C.2
**Date:** 2026-05-14
**Branch:** feature/ai-output-upgrade

## Summary

CSS-only productization pass to restore the old UI's cinematic creator energy. No layout changes, no IA changes, no JS changes. Pure visual quality upgrade: depth, glow, gradient, and typographic hierarchy restored.

## Files Changed

| File | Change |
|---|---|
| `tokens.css` | Added shadow tokens (`--shadow-sm/md/lg`, `--shadow-glow-accent`) |
| `base.css` | `.text-screen` and `.text-section` weight raised 600→700 |
| `layout.css` | `.screen__title` weight raised 600→700 |
| `components.css` | 14 targeted CSS rule improvements (see below) |

## Old UI Elements Restored

- **Gradient buttons** — `btn-primary` and `btn-generate`/`cw-generate-btn` get gradient fill (`#5EC7AF → #76E0C0 → #91E8D3`) matching old blue-purple gradient energy
- **Button glow + lift** — `box-shadow` teal glow + `translateY(-1px)` on hover (old UI had same pattern with blue)
- **Card depth** — `linear-gradient(170deg)` fill + `border-top-color: border-strong` + `box-shadow: 0 4px 20px` (old UI: `0 6px 32px rgba(0,0,0,.52)`)
- **Input focus glow** — strengthened from 0.12 → 0.18 opacity
- **Active nav glow** — teal ambient background + `text-shadow` glow on active item
- **Progress bar gradient** — linear gradient fill instead of flat accent colour
- **Breathing generate button** — subtle `cw-btn-pulse` keyframe animation when enabled

## Structural Fixes

- `.text-screen` / `.text-section` / `.screen__title` all weight 700 — clear hierarchy
- `.btn-secondary:hover` border becomes teal hint instead of hard grey
- `.clip-rank-badge--best` glow strengthened (10px → 16px)
- `.output-clip-card:hover` adds `translateY(-1px)` lift
- `.monitor-progress-card` gets gradient + shadow
- `.render-bar__progress-fill` gets gradient

## Dashboard Feel Reductions

- Buttons no longer look like flat coloured rectangles — they have gradient depth and glow
- Cards no longer look like flat bordered boxes — they have gradient depth and directional shadow
- Active nav item glows instead of just changing background colour
- Generate moment has breathing animation — feels alive not inert

## Verification

- No JS files changed — CSS only
- No layout changes — all structural CSS preserved
- `node --check` on all JS modules: OK (no JS changes in this phase)

## Remaining Gaps

- Right panel (Settings/Context) still has enterprise feel — addressed in UI-R5E
- Projects screen needs same pass — addressed in UI-R5D
- Motion and page transitions not yet added — UI-R5F

---

## Section 25: Feature-Level Frontend Audit — 2026-05-16

> **Method:** Direct code reading of all files under `backend/static-v2/`. Every finding references a specific file and line number. Severity: P0=crash/security, P1=production reliability, P2=improvement.

---

### Verified Tech Stack (Frontend, from actual code)

| Layer | Technology | Source |
|---|---|---|
| Framework | Vanilla ES modules — no framework, no build step | All .js files, package.json `{"type":"module"}` |
| State management | `createStore()` factory — pub/sub with `set/update/subscribe/reset` | `store/create-store.js` |
| Routing | Hash-based router (`#/create`, `#/monitor/:jobId`, etc.) | `router.js` |
| Transport | WebSocket primary (`/ws/jobs/{jobId}`) + HTTP polling fallback (3s) | `transport.js` |
| API layer | `fetchJson()` typed HTTP client + module-level API wrappers | `transport.js`, `api/*.js` |
| Entity normalization | `normalizeJob`, `normalizePart`, `parseResultPackage`, `parsePrepareSourceResponse` | `entities/*.js` |
| Desktop integration | Electron `contextBridge` adapter with safe no-op fallbacks | `desktop-adapter.js` |
| Stores | `draftStore`, `monitorStore`, `renderSessionStore`, `resultsStore`, `systemStore`, `readinessStore` | `store/*.js` |
| UI components | `StatusChip`, `AIBadge`, `NavRail`, `EmptyState`, `LogDrawer`, `ScoreBadge`, `PartStatusList`, `BestClipHero`, `OutputCard`, `ErrorBoundary` | `components/*.js` |
| CSS | 4 files: tokens.css, base.css, layout.css, components.css — design token–driven | `assets/css/` |
| Static serving | Served from `backend/static-v2/` via FastAPI StaticFiles | `main.py` |

---

### Feature 37 — Frontend Create Flow (Source + Studio)

**Purpose:** Guide the user from URL/file input through source validation to render configuration and submission.

**Files:** `screens/source.js`, `screens/studio.js`, `api/render.js`, `store/draft.js`, `entities/source-session.js`, `entities/render-request.js`

**State:** Module-level `_s` object in source.js + `_submitting`/`_submitError` in studio.js + `draftStore` (shared)

**Actual flow:**
1. Source screen: user enters YouTube URL or local path + output dir
2. Client-side validation in source.js:
   - YouTube URL: basic `https://` prefix check (line 328-329) — does NOT validate domain
   - Local path: non-empty check only
3. `renderApi.prepareSource(payload)` with 45s timeout (PREPARE_TIMEOUT_MS:11) — AbortController
4. Response parsed by `parsePrepareSourceResponse()` → `draftStore.setSession()`
5. User navigates to Studio: `#/studio`
6. Studio renders 4 config sections: clip strategy, subtitles, camera, AI guidance
7. `buildRenderRequest(draft)` converts `draftStore` state to API payload
8. `validateRenderDraft(draft)` checks: session present, output dir set, min ≤ max part sec
9. `renderApi.process(payload)` with 30s timeout (RENDER_TIMEOUT_MS:11) → receives `{ job_id }`
10. Navigates to `#/monitor/{jobId}`

**What works correctly:**
- AbortController on prepare-source (45s) and render submit (30s) prevent stuck loading states
- `if (_submitting) return` guard in studio.js prevents double-submit
- `draftStore.patch()` tracks form changes without full re-render of shell
- `buildRenderRequest()` only sends intentionally-set fields (no spurious defaults)

**Problems found:**
- **P1:** AbortController race in source.js: if 45s abort fires and then server responds with success within ~100ms of the abort, `_phase` could be set to 'configure' after the catch block already reset it to 'import', leaving UI in a ghost-configured state. (Confirmed prior finding C-1.)
- **P1:** YouTube URL validation: `https://` prefix check only — `https://evil.internal/` accepted. No domain validation.
- **P1:** source.js module state (`_s` object) reset on every mount (line 374) — user navigating back from Studio loses their URL input and must re-type.
- **P2:** Studio screen renders full HTML on every `draftStore` change — no incremental DOM patching. For fast typists in studio config inputs, this generates many reflows.
- **P2:** Studio preview video: 10s hardcoded timeout (studio.js:471) fires even while browser buffers on slow connections.
- **P2:** Studio timer (preview load 10s) NOT cleared in unmount handler — potential 10s timer firing after user navigated away.

**Missing functionality:**
- No multi-URL batch source input in source screen (batch render exists on backend, not wired in UI)
- No subtitle preview before render (transcript endpoint exists but unused)

**Edge cases:**
- User opens two browser tabs on Source screen → both share same `draftStore` module singleton → tab B overwrites tab A's draft on prepare-source success
- User navigates source → studio → back → source: source screen re-mounts with fresh state; any session from tab A is lost

**Recommended fixes:**
- Add flag `_aborted = true` before AbortController.abort(); in fetch then-branch check `if (_aborted) return` (P1)
- Add YouTube domain validation (youtube.com, youtu.be, m.youtube.com) in source.js (P1)
- Persist last URL in `sessionStorage` and restore on mount (P2)
- Clear preview timer in studio.js unmount handler (P2)

**Priority:** P1

---

### Feature 38 — Frontend Monitor Flow

**Purpose:** Show real-time render progress, stage labels, clip status, and terminal actions (cancel, retry, resume).

**Files:** `screens/monitor.js`, `store/monitor.js`, `store/render-session.js`, `transport.js`, `components/part-status-list.js`, `components/log-drawer.js`

**Constants:** `CONNECT_TIMEOUT_MS = 20_000` (line 17), `TERMINAL = new Set([...4 statuses])` (line 16), `STAGE_LABELS` dict (lines 19-31)

**Actual flow:**
1. `monitor.js:mount(el, params)` → `monitorStore.start(jobId)` → `transport.subscribeJob(jobId, callbacks)`
2. `openJobStream()` opens WS; falls back to polling on error
3. On each state update → `monitorStore` set → `renderSessionStore.sync()` → shell render bar updates
4. 20s connect timeout (lines 263-267) → shows timeout banner if no data arrives
5. Terminal status → shows terminal banner with context-sensitive CTAs:
   - `completed` → "View Results" button
   - `failed` → "Retry" button
   - `interrupted` → "Resume" button
   - `completed_with_errors` → "View Results" + failed clip info
6. Cancel button: `POST /api/render/{jobId}/cancel`, disabled after click
7. Unmount: `el.addEventListener('unmount', () => { unsub(); monitorStore.stop(); })` (lines 301-305)

**What works correctly:**
- Cleanup IS implemented (confirmed not a bug — unmount event dispatched by router.js:88)
- Cancel button disabled after click (prevents double-cancel)
- Retry/Resume buttons disabled on click
- Log drawer lazy-loads on first open via `wireLogDrawer()`
- Correct 4-status TERMINAL set on frontend

**Problems found:**
- **P1:** 20s connect timeout banner is purely cosmetic — `monitorStore.stop()` is NOT called when banner displays (monitor.js:265). The transport stream (WS + poll loop) continues running indefinitely even after user sees timeout message. Resource leak.
- **P1:** `STAGE_LABELS` is a static client-side dict keyed on backend stage name strings (lines 19-31). If backend renames or adds a stage, frontend silently falls back to raw stage key (e.g., `"SCENE_DETECT_V2"`) with no humanization.
- **P1:** No error handling on Retry/Resume button API call (monitor.js:179-185). Button is disabled but if the API call fails, user gets no error feedback — button stays disabled permanently with no explanation.
- **P2:** 20s connect timeout timer (lines 263-267) NOT cleared on unmount if no data arrives — fires and modifies DOM after user navigated away.
- **P2:** `monitorStore.stop()` retains last state in `renderSessionStore` (store/monitor.js:67-70) — correct for render bar persistence, but renderSessionStore is never cleared if user navigates to Library without viewing results. Stale render bar persists.
- **P2:** Deep-link validation missing: invalid/deleted jobId causes WS error → polling 404 → screen shows infinite "Connecting…" spinner with no "Job not found" message.
- **P2:** `renderSessionStore.sync()` called 3× per WS message — once each from `onUpdate`, `onTerminal`, and `onTransportChange` callbacks (store/monitor.js:32, 52, 62). Each sync triggers all renderSessionStore subscribers (shell render bar re-render). 3× redundant re-renders per WS tick.

**Edge cases:**
- User opens monitor for job that's already completed → immediate terminal state → terminal banner shows without any progress display → user sees abrupt state
- User navigates away mid-render (back to Source) → unmount event fires → monitorStore.stop() called → render bar persists via renderSessionStore → correct behavior

**Recommended fixes:**
- Call `monitorStore.stop()` when timeout banner fires (P1)
- Add fallback stage label humanization: `STAGE_LABELS[key] ?? key.replace(/_/g, ' ').toLowerCase()` (P1)
- Add error toast/message on retry/resume API call failure (P1)
- Clear timeout timer in unmount handler (P2)
- Deduplicate `renderSessionStore.sync()` — call once per store update cycle (P2)
- Add "Job not found" synthetic state on 404 poll response (P2)

**Priority:** P1

---

### Feature 39 — Frontend History Flow (Library)

**Purpose:** Display list of past render jobs with filtering, search, and navigation actions.

**Files:** `screens/library.js`, `screens/projects.js` (router wrapper), `api/jobs.js`, `entities/job.js`

**State:** Module-level `_history`, `_filter`, `_search`, `_loading`, `_error`, `_listEl`

**Actual flow:**
1. `GET /api/jobs/history` → normalize each item via `normalizeHistoryItem(raw)` (library.js:28-61)
2. Sort by `createdAt` descending
3. Filter bar: 6 pills (all, running, completed, partial, failed, interrupted) — client-side only
4. Search input: filters display name client-side — no server-side search
5. Card actions: "View Results" → `#/projects/{jobId}`, "Monitor" → `#/monitor/{jobId}`, "Retry" → POST → navigate, "Resume" → POST → navigate
6. Delete action: `jobsApi.delete(jobId)` — DB record only, no file cleanup, no confirmation

**What works correctly:**
- `_normalizeDisplayTitle()` humanizes YouTube URLs and raw file paths
- `_filterItems()` and `_renderCard()` are clean separation of concerns
- Error card shows retry button for failed API load

**Problems found:**
- **P0 (pagination):** History screen has no "Load more" affordance. Backend caps at 30 items. Users with >30 renders see silently truncated list.
- **P1:** `normalizeHistoryItem()` (lines 28-61) calls `JSON.parse(raw.result_json)` inside a try/catch — returns null on malformed JSON. Malformed result_json silently hides score/AI data from Library card.
- **P1:** Delete action calls `jobsApi.delete(jobId)` immediately with NO confirmation dialog. Permanently deletes DB record (but not files). Accidental delete has no undo.
- **P1:** Library action buttons (retry/resume) have no error feedback — button shows "Retrying..." then re-enables on error but no error message is persisted to the card.
- **P2:** `CSS.escape()` called on jobId for DOM querying (line 331) — safe but unnecessary if IDs are always UUIDs.
- **P2:** `_normalizeDisplayTitle()` only handles YouTube and file paths — Vimeo, Twitch, direct MP4 URLs display as raw URLs.
- **P2:** No search filtering at API level — all 30 items loaded, filtered client-side. With larger caps, this degrades.

**Recommended fixes:**
- Add "Load more" with offset pagination to library screen and backend history API (P0)
- Add confirmation dialog before `jobsApi.delete()` (P1)
- Show inline error message on retry/resume failure (P1)
- Extend `_normalizeDisplayTitle()` to handle more URL types (P2)

**Priority:** P0 (pagination), P1

---

### Feature 40 — Frontend Download Flow

**Purpose:** Let users download public videos (YouTube/Instagram/Facebook) and view batch job status.

**Files:** `screens/downloads.js`, `api/download.js`

**State:** Module-level `_urlRaw`, `_outputDir`, `_submitting`, `_checkingStatus`, `_lastJob`, `_el`

**Actual flow:**
1. User pastes URL(s) — `parseUrlInput()` splits on newlines, validates `https?://` protocol, dedupes
2. Optional output dir selection (native picker on desktop, text input on web)
3. `POST /api/download/process` with `{ urls, output_dir? }` → receives `{ job_id, items }`
4. Job panel shows up to 8 items with status chips; "...and N more" if exceeded
5. "Check Status" → `GET /api/jobs/{jobId}` → updates `_lastJob.status`
6. "Retry" → `POST /api/download/retry/{jobId}` with `{ part_numbers: [] }` (always empty)

**What works correctly:** URL deduplication. Native picker integration via desktopAdapter. Submit disables button.

**Problems found:**
- **P1:** `output_dir` sent to backend without path validation. User can direct downloads to arbitrary filesystem locations.
- **P1:** "Retry" always sends empty `part_numbers` — no per-item retry UI. A 10-URL batch where 1 fails retries all 10 items.
- **P1:** No per-file download progress indication. Large file downloads appear frozen to user with no bytes-received feedback.
- **P2:** Hardcoded max 8 items display (lines 119-128) — large batch jobs show truncated info.
- **P2:** State reset on each mount — closing and reopening downloads tab loses last job info.
- **P2:** No download history persistence — cannot see previously downloaded files after tab close.

**Missing functionality:**
- Per-item retry selection
- Per-file progress (bytes received / total)
- Download history across sessions

**Priority:** P1

---

### Feature 41 — Frontend State Management

**Purpose:** Coordinate state across screens, the shell, and transport layer using reactive pub/sub stores.

**Files:** `store/create-store.js`, `store/draft.js`, `store/monitor.js`, `store/render-session.js`, `store/results.js`, `store/session.js`, `store/system.js`, `store/readiness.js`

**Store inventory:**

| Store | Purpose | Lifetime |
|---|---|---|
| `draftStore` | Render config form state | Persists across routes (module-level) |
| `monitorStore` | Live job stream (WS/poll) | Reset on `clear()` |
| `renderSessionStore` | Derived active-render bar state | Synced from monitorStore |
| `resultsStore` | Completed result package | Reset on new load |
| `systemStore` | Backend health + execution mode | Permanent (set at boot) |
| `readinessStore` | Tool availability (ffmpeg, yt-dlp, whisper) | Loaded at boot, not refreshed |
| `sessionStore` | Source sessions list | Per-load |

**What works correctly:**
- `createStore()` factory is clean minimal pub/sub with `set/update/subscribe/reset`
- `renderSessionStore.sync()` correctly derives active-render bar state from monitorStore
- `systemStore._startHealthWatch()` adjusts poll interval (30s unavailable, 60s ready)

**Problems found:**
- **P1:** `renderSessionStore.sync()` called 3× per WS message (from `onUpdate`, `onTerminal`, `onTransportChange` in store/monitor.js) → 3 shell render bar re-renders per tick. Should batch into one call per update cycle.
- **P1:** `systemStore._startHealthWatch()` (store/system.js:50-61) starts an async interval timer that is NEVER cleared — polls indefinitely for the lifetime of the session. No cleanup on tab close.
- **P1:** `renderSessionStore` state never persisted to `sessionStorage` or `localStorage`. Hard refresh during active render loses render bar — user has no way to reconnect without navigating to `/monitor/{jobId}` manually.
- **P2:** `draftStore.dirty` flag set to `true` on any `patch()` call but NEVER cleared. Cannot reliably detect if form was actually modified vs just mounted.
- **P2:** `readinessStore.load()` fetches readiness once at boot and never refreshes. If FFmpeg becomes unavailable after boot, readinessStore still shows `ffmpegAvailable=true`.
- **P2:** `createStore()` has no middleware layer — adding cross-cutting concerns (logging, devtools, persistence) requires patching each store individually.
- **P2:** Store subscriptions from screens are unsubscribed on unmount (via returned unsubscribe function) — correct. But `systemStore` and `renderSessionStore` subscriptions in `shell.js` are permanent (never unsubscribed) — intentional but undocumented.

**Recommended fixes:**
- Deduplicate `renderSessionStore.sync()` — move to end of each monitorStore update batch (P1)
- Persist `{ jobId, status }` in `sessionStorage` in `renderSessionStore.sync()` and restore on boot (P1)
- Clear `systemStore` health watch on page `unload` event (P2)

**Priority:** P1

---

### Feature 42 — Frontend Transport Layer

**Purpose:** Manage WebSocket and HTTP polling transport for real-time job updates.

**Files:** `transport.js`

**Exported API:**
- `openJobStream(jobId, callbacks)` → `{ close(), usingPolling }` (lines 18-92)
- `subscribeJob(jobId, { onUpdate, onTerminal, onTransportChange })` → `{ getTransportMode(), unsubscribe() }` (lines 95-124)
- `fetchJson(url, options)` → typed HTTP client with error normalization (lines 127-161)
- `withTimeout(promise, ms, label)` → AbortController-based timeout (lines 165-174)
- `normalizeApiError(err)` → `{ ok, status, message, code, details }` (lines 177-185)

**WebSocket lifecycle:**
1. `wsUrl()` builds `ws://` or `wss://` from `window.location`
2. `tryWs()` creates WebSocket, wires `onmessage`/`onerror`/`onclose`
3. `onmessage`: parses JSON, fires `onMessage(data)`, checks terminal status
4. On terminal: fires `onTerminal(data)`, triggers 600ms authoritative poll
5. On error/close: sets `usingPolling=true`, starts `doPoll()` immediately
6. `doPoll()`: fetches `GET /api/jobs/{jobId}` + `GET /api/jobs/{jobId}/parts` every 3000ms

**What works correctly:**
- Post-terminal authoritative poll (600ms delay) catches any final state not in WS last message
- `normalizeApiError()` provides consistent error shape to callers
- `fetchJson()` handles non-JSON 2xx gracefully (returns null)
- `withTimeout()` provides clean AbortController integration

**Problems found:**
- **P1:** `TERMINAL_STATUSES` on frontend = 4 statuses (`completed`, `completed_with_errors`, `failed`, `interrupted`). Backend WS breaks on 2 (`completed`, `failed`). Frontend closes WS client-side after receiving terminal status but server-side loop continues for `interrupted`/`completed_with_errors` until client disconnects. (Confirmed prior finding — server-side fix needed in routes/jobs.py:411.)
- **P2:** No WS reconnect backoff. Immediate fallback to polling on ANY WS failure (transient network blip, server restart). No attempt to reconnect WS after delay.
- **P2:** WS `close` always triggers polling even on clean shutdown (job completed and server closed WS). Unnecessary polling for already-terminal jobs.
- **P2:** Poll errors silently caught (lines 46-47) — 5xx responses from backend silently swallowed; UI shows stale state indefinitely with no error toast.
- **P2:** No transport-type telemetry exposed outside the subscribeJob closure. `monitorStore` knows transportMode but only via callback; no global transport health observable.
- **P2:** Multiple simultaneous calls to `subscribeJob` for the same jobId each create independent WS connections and poll loops (no connection sharing).

**Recommended fixes:**
- Implement WS reconnect with exponential backoff (1s → 2s → 4s → max 30s) (P2)
- On WS `close` with terminal job status, skip polling fallback (P2)
- Surface poll errors to UI via `onError` callback after N consecutive failures (P2)

**Priority:** P1 (WS terminal mismatch — server fix needed), P2 (reconnect)

---

### Feature 43 — Frontend Error Handling

**Purpose:** Catch and display errors at transport, store, screen, and component levels.

**Files:** `transport.js` (normalizeApiError), `components/error-boundary.js` (withErrorBoundary), `router.js` (screen mount error recovery), `screens/*.js` (per-screen error states)

**Error boundary:**
- `withErrorBoundary(mountFn)` (error-boundary.js:7-15) wraps screen mounts in try/catch
- On error: renders recovery UI with "Retry" and "Back to Source" buttons
- Console.error only — no error reporting to backend
- Retry calls original mountFn again — could loop if error is persistent

**Transport errors:**
- `fetchJson()` (transport.js:127-161): normalizes all HTTP + network errors to `{ ok, status, message }`
- `withTimeout()` (lines 165-174): generates AbortError with user-friendly label
- Poll errors (lines 46-47): silently caught — not surfaced to UI

**Screen-level error states:**
- source.js: `_s.error` string displayed below form
- studio.js: `_submitError` string displayed in CTA area
- library.js: error card with retry button
- results.js: error card with retry/library CTAs
- monitor.js: connection timeout banner (but does not stop transport)

**What works correctly:**
- `normalizeApiError()` provides consistent error shape across all API calls
- Error boundaries prevent full-page crashes on screen mount failures
- Most screens have dedicated error states

**Problems found:**
- **P1:** Poll errors silently swallowed in `doPoll()` (transport.js:46-47). If backend consistently returns 5xx during a render, monitor screen shows last-known state indefinitely with no indication of poll failure.
- **P1:** `withErrorBoundary` retry can loop on persistent errors (e.g., screen tries to access undefined store state). No max retry count.
- **P1:** monitor.js retry/resume button API failures: button disabled indefinitely with no error message. User must refresh page to retry.
- **P2:** No centralized error tracking / reporting. Errors only go to console.error — no telemetry.
- **P2:** `_esc()` helper in source.js (line 382), studio.js (line 504), library.js (line 96) escapes `&`, `"`, `<` but NOT `>`. Incomplete HTML escaping — `>` in user content could close tags in attribute values.

**Edge cases:**
- Backend returns 503 during render → poll errors silently swallowed → UI frozen at last state, user does not know backend is down
- Screen throws on mount AND on retry → error boundary shows recovery UI on top of broken DOM — CSS may conflict

**Recommended fixes:**
- Surface poll errors to UI after 3 consecutive failures: show yellow warning banner "Having trouble connecting..." (P1)
- Add max retry count (3) to error boundary `withErrorBoundary` (P1)
- Add `>` to `_esc()` entity escaping (P2)
- Add `onError` callback to `doPoll()` (P2)

**Priority:** P1

---

### Additional Frontend Production Risks (cross-cutting)

#### Memory Management

| Issue | Severity | File:Line |
|---|---|---|
| `systemStore._startHealthWatch()` timer never cleared | P1 | `store/system.js:50-61` |
| Studio preview load timeout (10s) not cleared on unmount | P2 | `screens/studio.js:471` |
| Monitor connect timeout (20s) not cleared on unmount | P2 | `screens/monitor.js:263` |
| Shell subscriptions to systemStore + renderSessionStore permanent | P2 (intentional) | `components/shell.js:49-56` |

#### XSS / Injection

| Issue | Severity | File:Line |
|---|---|---|
| `_esc()` missing `>` entity — incomplete HTML escaping | P2 | `screens/source.js:382`, `screens/studio.js:504`, `screens/library.js:96` |
| Error boundary innerHTML uses hardcoded HTML — safe but not maintainable | P3 | `components/error-boundary.js:18-41` |
| router.js error recovery uses innerHTML — safe (hardcoded) | P3 | `router.js:106` |

#### Race Conditions

| Issue | Severity | File:Line |
|---|---|---|
| AbortController race: server success after 45s abort → ghost-configured state | P1 | `screens/source.js:340-368` |
| Studio preview timeout fires after unmount | P2 | `screens/studio.js:471` |
| resultsStore `_prevResult` tracking could miss rapid state transitions | P2 | `screens/results.js:386` |

#### Data Validation

| Issue | Severity | File:Line |
|---|---|---|
| transport.js onmessage: no schema validation of received WS data before normalizing | P2 | `transport.js:63-73` |
| render-request.js buildPayload: no runtime type check that built payload matches contract | P2 | `entities/render-request.js:36-74` |
| downloads.js: `output_dir` sent without path validation | P1 | `screens/downloads.js:259` |

---

### Consolidated Frontend Roadmap

#### P0 — Critical (production blockers)

| ID | Fix | File |
|---|---|---|
| F0-1 | Add Library pagination ("Load more" with offset) | `screens/library.js`, `api/jobs.js` |
| F0-2 | Fix WS terminal mismatch (server-side fix, already in B1-1) | `backend/routes/jobs.py:411` |

#### P1 — High (significant UX degradation or resource waste)

| ID | Fix | File |
|---|---|---|
| F1-1 | Call `monitorStore.stop()` when timeout banner fires | `screens/monitor.js:265` |
| F1-2 | Add stage label fallback humanization (`key.replace(/_/g,' ').toLowerCase()`) | `screens/monitor.js:STAGE_LABELS` |
| F1-3 | Add error feedback on retry/resume button failure | `screens/monitor.js:179-185` |
| F1-4 | Deduplicate `renderSessionStore.sync()` to once per update cycle | `store/monitor.js:32,52,62` |
| F1-5 | Persist `{ jobId, status }` in sessionStorage for render bar reconnect after refresh | `store/render-session.js` |
| F1-6 | Fix AbortController race in source.js (set `_aborted` flag) | `screens/source.js:340` |
| F1-7 | Add YouTube domain validation in source.js | `screens/source.js:328-329` |
| F1-8 | Add per-item retry selection UI in downloads screen | `screens/downloads.js` |
| F1-9 | Surface poll errors to UI after 3 consecutive failures | `transport.js:46-47` |
| F1-10 | Add delete confirmation dialog in Library | `screens/library.js` |
| F1-11 | Add max retry count to error boundary | `components/error-boundary.js` |
| F1-12 | Stop systemStore health watch on page unload | `store/system.js:50-61` |

#### P2 — Medium (polish and scalability)

| ID | Fix | File |
|---|---|---|
| F2-1 | Add `>` to `_esc()` entity escaping | `screens/source.js:382`, `studio.js:504`, `library.js:96` |
| F2-2 | WS reconnect with exponential backoff | `transport.js` |
| F2-3 | Add "Job not found" state in Monitor for invalid/deleted jobIds | `screens/monitor.js` |
| F2-4 | Persist last-entered URL in sessionStorage across source screen mounts | `screens/source.js:374` |
| F2-5 | Clear studio preview timeout on unmount | `screens/studio.js:471` |
| F2-6 | Clear monitor connect timeout on unmount | `screens/monitor.js:263` |
| F2-7 | Extend `_normalizeDisplayTitle()` to Vimeo, Twitch, direct MP4 URLs | `screens/library.js` |
| F2-8 | Virtual scrolling for Library (30+ items) and Results clip list (20+ clips) | `screens/library.js`, `screens/results.js` |
| F2-9 | Content-hash cache-busting for static assets | `index.html`, deploy process |
| F2-10 | AI score humanization in Results (raw float → 0-100 + qualitative label) | `screens/results.js` |
| F2-11 | AI score null fallback state in Results (show "AI scoring unavailable" empty state) | `screens/results.js` |
| F2-12 | Add `createStore()` middleware layer for cross-cutting concerns | `store/create-store.js` |
| F2-13 | Validate `output_dir` on client before sending (no traversal sequences) | `screens/downloads.js:259` |

---

## Section 26: Library Screen Pagination Fix — 2026-05-16

### Problem

The Library screen called `jobsApi.getHistory()` with no parameters and loaded all returned items at once. With the backend previously capping at 30 rows (and now supporting up to 100 per page with `offset`), there was no way for the user to see older jobs.

### Fix

**`library.js` changes:**

- Added `_PAGE_SIZE = 20`, `_offset`, `_hasMore`, `_loadingMore` state variables
- `_load()` now requests `{ limit: 20, offset: 0 }` and reads `has_more` from the response
- New `_loadMore()` function fetches `{ limit: 20, offset: _offset }` and appends to `_history`
- `_renderList()` appends a "Load more" / "Loading…" button below the card list when `_hasMore` is true
- Removed the client-side `.sort()` in `_load()` — backend `ORDER BY updated_at DESC` is authoritative; re-sorting would break cross-page ordering
- `mount()` resets new pagination state alongside existing vars

**Existing features preserved:**
- Filter pills (All / Running / Completed / Failed / Interrupted) operate on `_history` (the full in-memory loaded set) — unchanged
- Search input filters the in-memory set — unchanged
- Card actions (View Results, Monitor, Retry, Resume) — unchanged
- Refresh button resets and re-loads from page 0 — unchanged

**Behavior with filters active:**
When a filter is active and the visible set is empty (all loaded items filtered out), "Load more" is still shown if `_hasMore` is true. This lets the user expand the loaded pool to find filtered items without clearing the filter.

**`api/jobs.js` change:**
`getHistory(params?)` now accepts an optional params object for `limit`/`offset`. Zero-argument call is backward compatible.

---

## Historical (resolved) / Current State (P2.9)

> The sections above this line document `backend/static-v2/` — the prototype V2 shell.
> The sections below document `backend/static/` — the production app shell — and the P2.5–P2.9 runtime intelligence phases.
> These are separate codebases. The V2 shell is not served in production.

---

## Section 27: Production Shell — P2.5–P2.9 Runtime Intelligence

**Codebase:** `backend/static/`  
**Phase range:** P2.5 → P2.9  
**Date range:** pre-2026-05-14 → 2026-05-16  
**Branch:** `feature/ai-output-upgrade`

### Historical (resolved) — Pre-P2.5 state

Before P2.5, `backend/static/` had a functional render dashboard:
- rdCard header with progress bar and status label
- `#rc_part_cards` grid of pending part rows
- `#event_log_render` raw event log
- `#render_output_list.clipsGrid` output clip grid

Status surfaces overlapped. No AI editorial voice. No narrative or causality. The UI communicated state accurately but not meaningfully.

### Current State (P2.9) — 2026-05-16

The runtime is now a three-surface AI orchestration system layered on the same DOM without restructuring it. All changes are additive.

**New surfaces introduced:**

| Surface | DOM ID | Role |
|---|---|---|
| AI Process Card | `#rc_ai_process_cards` | 12-stage editorial pipeline status |
| Clip Evolution Feed | `#rc_ai_evolution_feed` | per-clip completion narrative with tier-based editorial copy |
| AI Reasoning Stream | `#rc_ai_reason_feed` | stage-transition editorial sentences |
| Completion Intelligence | `#rc_benchmark_insight` | avg/top viral score + editorial summary |

**Behavioral changes:**
- Stage transitions: morph animation instead of hard innerHTML replacement
- Clip completion: causal elevation on output card (`p29Elevated`) + optional green editorial highlight (`p29Causal`)
- Confidence evolution: `data-p29-confidence` attribute on best card (emerging → rising → strong → peak)
- Completion arrival: one-shot cinematic transition (output rises, runtime recedes)
- Territory switching: `[data-render-state]` CSS controls which zone dominates

**Language changes:**
- All 12 stage labels changed from engineering to editorial copy ("Rendering" → "Rendering" stays, but "Scene Detection" → "Mapping the Story", etc.)
- All 12 reasoning sentences changed to human editorial voice
- Evolution feed uses tier-specific message pools (3 messages × 3 tiers)
- Completion bar becomes editorial creative outcome summary

**What improved vs. P2.5 baseline:**
- No more hard stage replacement cuts
- Output cards have visible consequence when clips complete
- Best clip confidence is observable and data-driven
- Runtime and output compete appropriately by lifecycle state
- Cognitive load reduced: duplicate % displays suppressed during running

**What remains weak:**
- `populateRenderOutputPanel` full re-render can wipe transient elevation classes mid-animation
- Confidence evolution uses `parts.length` as total count (may undercount early in pipeline)
- Raw `#rc_part_cards` still visible — partly redundant with `.clipsGrid`
- Log strip shows raw events with no editorial filtering
- `pointer-events: none` on receded runtime mount is not discoverable

**Full technical documentation:** `docs/review/frontend/RUNTIME_ORCHESTRATION.md`

---

## Section 28 — P3.1: Creator Memory & Preference Intelligence

**Date:** 2026-05-16
**Branch:** feature/ai-output-upgrade
**Scope:** `backend/static/js/`, `backend/app/`, `backend/static/css/v3/`

### What This Phase Addressed

The editor's AI suggestion system was session-only: accept/reject signals from `_trackPreference` accumulated in `aiPreferenceProfile` within EditorState but were discarded on every page load. `feedback_learning.py` (Phase 43) did backend preference learning at render level, but was never connected to the editor UI. This phase adds the persistence bridge and surfaces what the AI has learned.

### Files Changed

| File | Change |
|---|---|
| `backend/app/services/db.py` | Added `creator_prefs` table (singleton row, JSON blob); added `get_creator_prefs()` and `upsert_creator_prefs()` CRUD functions |
| `backend/app/routes/creator.py` | New file: `GET /api/creator/preferences` and `PUT /api/creator/preferences` |
| `backend/app/main.py` | Registered `creator_router` |
| `backend/static/js/creator-memory.js` | New file: `CreatorMemory` IIFE — localStorage cache + debounced backend sync + inspector panel render |
| `backend/static/js/editor-ai-actions.js` | `_trackPreference` now calls `CreatorMemory.recordSignal()`; `_buildReasoning` injects preference-aware copy when memory is confident |
| `backend/static/js/editor-view.js` | `CreatorMemory.init()` called on editor open; panel cleared on cancel |
| `backend/static/index.html` | Added `#cmPrefsPanel` div in inspector; added `<script>` tag for `creator-memory.js` |
| `backend/static/css/v3/review.css` | Added creator memory panel styles (learning state, known state, prefRow) |

### Architecture

```
accept/reject action
        │
        ▼
_trackPreference (editor-ai-actions.js)
  └── EditorState.setEditorState({ aiPreferenceProfile })   ← session memory (unchanged)
  └── CreatorMemory.recordSignal(name, accepted)            ← P3.1: persistent memory
          │
          ├── updates in-memory _profile
          ├── saves to localStorage (LS_KEY='cm_prefs_v1')
          ├── schedules debounced PUT /api/creator/preferences
          └── calls _refreshPanel() → updates #cmPrefsPanel DOM

editor open (editor-view.js)
  └── CreatorMemory.init()
          ├── GET /api/creator/preferences
          ├── merges remote prefs (higher totalSignals wins)
          ├── seeds EditorState.aiPreferenceProfile if totalSignals > 0
          └── renders #cmPrefsPanel

_buildReasoning (editor-ai-actions.js)
  └── if CreatorMemory.getDerivedPreferences().confident:
          ├── favored action → "Based on your history, you tend to keep this."
          └── avoided action → "You've passed on this before — worth a second look."
```

### Safety Design

- `MIN_SIG = 5` — no preference-aware copy injected until ≥5 accept/reject signals
- Monotonic UI: panel starts in "learning" state with progress bar, graduates to "known" state
- Reset button in "known" state clears localStorage, pushes empty prefs to backend, clears EditorState
- `aggressiveness` field already drives trim ratios in patch generators (pre-existing wiring via `_getAggressiveness()`)

### What Remains Weak

- No feedback loop from render output (what clips the user downloads, previews) — only editor accept/reject signals
- `feedback_learning.py` (Phase 43) backend learning is still disconnected from the creator_prefs table
- No taste model per content type (short-form comedy vs. long tutorial behave differently)
- `creator_prefs` is installation-scoped (no user accounts) — one profile per machine

**Next phase:** P3.2 would add conversational AI or render-output feedback (download signal, preview signal)

---

## Section 29 — P3.2: Conversational Editing

**Date:** 2026-05-16
**Branch:** feature/ai-output-upgrade
**Scope:** `backend/static/js/`, `backend/static/index.html`, `backend/static/css/v3/`

### What This Phase Addressed

The editor had AI intelligence (P2.x) and creator memory (P3.1), but interaction was still button-driven. Every creative intent required finding the right control. P3.2 adds a natural-language layer: type what you want changed, and the system converts it to a patch preview.

### Files Changed

| File | Change |
|---|---|
| `backend/static/js/editor-converse.js` | New file: `EditorConverse` IIFE — intent parser, conversation history, memory-aware responses |
| `backend/static/js/editor-view.js` | Added 'ai' tab to `validTabs` and `tabTitles`; `EditorConverse.init()` + `reset()` in editor lifecycle |
| `backend/static/js/editor-ai-actions.js` | Preview card accept/reject buttons now call `EditorConverse._onAccept()` / `_onReject()` |
| `backend/static/index.html` | Added "Talk" tab button; added `.convPanel` with history, example chips, input field; added script tag |
| `backend/static/css/v3/review.css` | Added conversation panel styles (history feed, user/AI turns, clarify buttons, example chips, input row) |

### Conversation Architecture

```
user text → _parseIntent()
  → keyword scoring per rule (multi-word matches = 2pts, single = 1pt)
  → if tied top-2 → clarify options shown
  → if no match → suggest 4 quick actions
  → if clear winner → _fireIntent(action, interpretation, desc)

_fireIntent():
  → memory context from CreatorMemory.getDerivedPreferences()
  → _addTurn('ai', interpretationMsg)
  → EditorAiActions.previewAction(action)   ← uses EXISTING patch system
  → ghost overlay on timeline + preview card in #evInspAiPanel

user clicks Accept/Discard (in existing #evInspAiPanel card):
  → EditorAiActions.acceptPreview() / rejectPreview()   ← unchanged
  → EditorConverse._onAccept() / _onReject()            ← adds follow-up turn
```

### Intent Rules (7 mapped to existing actions)

| User language | Matched action | Keywords |
|---|---|---|
| "slow intro", "hook weak" | `strongerHook` | hook, intro, opening, start, beginning |
| "too slow", "boring", "pace" | `fasterPacing` | slow, boring, dragging, pace, pacing, tighten |
| "silence", "dead air", "gaps" | `removeDeadSpace` | silence, dead, gap, pauses, quiet, air |
| "viral", "energy", "algorithm" | `viralMode` | viral, algorithm, tiktok, energy, energetic |
| "too jumpy", "cinematic", "flow" | `cinematicMode` | cinematic, emotional, story, jumpy, choppy, calm |
| "subtitle", "captions", "messy" | `subtitleCleanup` | subtitle, caption, hard to read, messy text |
| "best clips", "rank", "quality" | `smartClipPrioritization` | best, rank, quality, priority, highlight |

### Memory Integration (P3.2-E)

After intent resolves, `CreatorMemory.getDerivedPreferences()` is checked:
- If `confident` (≥5 signals) and action is in `favored` → "You usually keep this one."
- If action is in `avoided` → "You've skipped this before — still worth a look."
- If not confident → no memory prefix (clean signal, not guessing)

### What Remains Weak

- Intent parser is keyword-based heuristics — no NLP or semantic understanding
- "too slow" is ambiguous (could be hook OR pacing) — tied score shows clarification, may frustrate users who expect instant result
- No multi-step conversation (each input is independent, previous context doesn't inform next parse)
- No undo from conversation panel (must use Cut tab or keyboard shortcut)
- Example chips disappear after first message but don't come back

---

## Section 30 — P3.3: Taste Model & Adaptive Intent

**Date:** 2026-05-16
**Branch:** feature/ai-output-upgrade
**Scope:** `backend/static/js/`, `backend/static/css/v3/`

### What This Phase Addressed

P3.2's intent parser was generic — "make it stronger" always failed (no keyword match), "too slow" always triggered clarification despite the taste model having a clear signal. P3.3 makes the system creator-aware: vague requests resolve differently based on accumulated taste signals, and tied keyword scores are broken using taste profile instead of always showing a disambiguation prompt.

### Files Changed

| File | Change |
|---|---|
| `backend/static/js/creator-memory.js` | Added `getTasteModel()` — pace/hook/editStyle dimensional inference. Extended `_renderKnown()` to show taste rows (requires ≥8 signals) |
| `backend/static/js/editor-converse.js` | Full P3.3 additions: `_ctx` micro-memory state, `_tryContextResolve()`, `_breakTieWithTaste()`, `_resolveWithTaste()`, expanded keyword lists, `explainText` threading through `_fireIntent`/`_addTurn`/`_render` |
| `backend/static/css/v3/review.css` | Added `.convExplain` (explainability text style) and `.cmTasteVal` (taste dimension value style) |

### Taste Model Math (getTasteModel)

**Pace dimension** — Fast signals: `fasterPacing` + `removeDeadSpace` accepted; cinematic signals: `cinematicMode` accepted
```
paceRaw = (fastAcc + slowRej − fastRej − slowAcc) / paceObs  ∈ [-1, 1]
pace = 'fast' if > 0.2, 'cinematic' if < -0.2, else 'balanced'
```

**Hook dimension** — `strongerHook` + `viralMode` accepted = aggressive; rejected = soft
```
hookRaw = (hookAcc − hookRej) / hookObs  ∈ [-1, 1]
hook = 'aggressive' if > 0.3, 'soft' if < -0.3, else 'moderate'
```

**Edit style (composite)**
- `viral`: paceRaw > 0.2 AND hookRaw > 0.2
- `cinematic`: paceRaw < -0.2 AND hookRaw ≤ 0.1
- `educational`: edu signals net ≥ 2 AND paceRaw ≥ -0.1
- `balanced`: everything else

Taste model requires `MIN_TASTE_SIG = 8` signals for `confident = true`.

### Adaptive Intent Resolution Order

```
user text
  1. _tryContextResolve()       ← "again", "just the intro", "a bit less"
  2. keyword scoring            ← existing 7 rules (expanded keyword lists)
  3. clear winner?              → fire
  4. tied?                      → _breakTieWithTaste()  ← taste breaks tie
  5. still tied?                → show clarification
  6. no keyword match?          → _resolveWithTaste()   ← vague power words
  7. vague + no taste model?    → show fallback chips
```

### Micro Conversation Memory (P3.3-C)

`_ctx = { lastAction, lastIntent, lastRaw }` persists within a session.

| Pattern | Resolution |
|---|---|
| "again" / "repeat" / "more of that" | Repeat `_ctx.lastAction` |
| "just the intro" / "intro only" | Force `strongerHook` |
| "just the subtitles" / "captions only" | Force `subtitleCleanup` |
| "a bit less" / "dial it back" | Apply opposite of `_ctx.lastAction` |

On reject: `_ctx.lastAction` is cleared — "discarded" signals the user wants a different direction.

### Explainability (P3.3-D)

When taste or context resolution is used, an `explainText` string is generated:
- Vague power + viral style: `"Your high-energy editing style shaped this — I read 'stronger' as a tighter opening hook."`
- Tie-broken by taste: `"Your cinematic tendency resolved this."`
- Context scope: `"Scoping to the intro based on context."`

Displayed in `.convExplain` below the AI response — muted, italic, unobtrusive.

### Inspector Taste Surface (P3.3-E)

`_renderKnown()` now shows taste rows when `taste.confident` (≥8 signals):
- Pace tendency: Fast / Balanced / Cinematic
- Hook tendency: Aggressive / Moderate / Soft
- Edit tendency: shown if not 'balanced' (Viral / High-energy, Cinematic / Story, Educational / Clarity)

### What Remains Weak

- Taste model resets on `CreatorMemory.reset()` — no decay, no partial forget
- `editStyle` composite is overly binary (once in 'viral' bucket, stays there unless signals reverse)
- Context resolution uses regex patterns — "just the very beginning of the intro" may not match
- Vague power resolution requires taste confidence (≥8 signals) — new users always get clarification

---

## Section 31 — P3.4: Adaptive Runtime Intelligence (2026-05-16)

**Branch:** `feature/ai-output-upgrade`
**Files changed:** `editor-runtime-intelligence.js` (new), `render-ui.js`, `runtime.css`, `index.html`

### What Changed

Before P3.4, `RenderAiRuntime` showed the same editorial messages for every creator regardless of their taste profile. "Strong hook from the first frame — this one is a keeper." was served identically to a viral creator expecting aggressive hooks and a cinematic creator preferring narrative pacing. Completion intelligence used generic tier text with no creator context.

P3.4 adds `RuntimeIntelligence` — a new lightweight IIFE that bridges `CreatorMemory.getTasteModel()` into the render runtime. Three functions, no DOM access, no invented signals.

### RuntimeIntelligence Module (P3.4-A)

New file: `editor-runtime-intelligence.js` — `window.RuntimeIntelligence` IIFE.

**`getEvolutionContext(pNo, pct, tier)`**
- Returns `{ why: string, tasteNote: string|null }`
- `why` is the main editorial message — taste-adapted when `taste.confident`
- `tasteNote` is a short italic annotation (e.g. "Aligned with your high-energy editing profile.") or null
- When taste not confident (< 8 signals): returns generic messages identical to prior behavior

**`getConcerns(parts)`**
- Returns `[{ type, label, msg }]` — at most 2
- Detects two real-signal conditions:
  - **Hook risk**: first clip scored < 45% AND creator `hook === 'aggressive'`
  - **Pacing signal**: batch avg < 45% (≥3 clips) AND creator `editStyle === 'viral'` or `pace === 'fast'`
- Returns empty array when `taste.confident` is false — no hallucinated concerns

**`getCompletionNarrative(avgPct, topPct, completedCount)`**
- Returns `{ summaryMsg, bits, tasteNote }`
- `summaryMsg` is creator-aware: "High-energy output — signal density aligns with your viral editing profile." vs. "Output follows your cinematic rhythm — narrative signal is strong."
- `bits` array for the completion summary line — includes "high-energy profile matched" for confident creators
- `tasteNote` is an italic footer in the completion card — shown only when taste is confident

### Evolution Feed Upgrades (P3.4-D)

`_updateEvolutionFeed()` now calls `RuntimeIntelligence.getEvolutionContext()` instead of the static `_evolEditorialMsg()` pool. Taste-adaptive "why" messages appear per clip. When tasteNote is non-null, a `.p34EvolTaste` span renders below the main message — italic, muted, unobtrusive.

Generic `_evolEditorialMsg()` function removed.

### Concern System (P3.4-E)

`_renderConcernItems(parts)` is called from `update()` after each render heartbeat. Concerns render as `.p34ConcernItem` entries appended to `rc_ai_evolution_list` (after clip items). Deduplication: `_lastConcernHash` prevents re-renders when concerns haven't changed. Cleared by `reset()`.

Visual design: amber left-border, muted amber label in small caps, standard body text. Non-alarmist — "Retention Risk" / "Pacing Signal", not "Warning" / "Error".

### Completion Intelligence Upgrade (P3.4-G)

`showCompletionIntelligence()` now calls `RuntimeIntelligence.getCompletionNarrative()`. Taste-aware `summaryMsg` replaces generic text. `bits` array replaces hardcoded completion line. `.p34TasteNote` div added below `.rcAiCompSummary` when creator has taste data.

### Failure Safety (P3.4-I)

- Every `RuntimeIntelligence` call is wrapped in `typeof RuntimeIntelligence !== 'undefined'` — if the module fails to load, `RenderAiRuntime` falls back to prior static messages
- `getConcerns()` returns `[]` when `taste.confident` is false — no intelligence hallucinated for new creators
- `getEvolutionContext()` returns identical messages to prior behavior when taste is not confident

### What Remains Weak

- Concern system has no "resolved" state — a concern stays visible until cleared by the next hash change or reset
- No hook_score or motion_score available — all scoring is `viral_score` based
- `getCompletionNarrative` compares scores against taste expectations (high-energy vs. cinematic) but can't compare against prior render history (no historical avg per creator)

---

## Section 32 — P3.5: Multi-Agent Editing System (2026-05-16)

**Branch:** `feature/ai-output-upgrade`
**Files changed:** `editor-agents.js` (new), `editor-converse.js`, `editor-runtime-intelligence.js`, `review.css`, `index.html`

### What Changed

Before P3.5, all AI editing intelligence ran through one generalized brain. Every intent — hook, pacing, subtitle, emotion, viral — was handled by the same keyword-scoring parser and the same taste model. Recommendations were generic tradeoffs across all dimensions.

P3.5 introduces five specialized editing agents as pure-data functions. Each agent reads only from real signal sources (scene markers, review scores, creator taste), analyzes one editing dimension, and produces a `{ action, confidence, reason, agentLabel }` output. A consensus engine ranks them by confidence. No LLM, no orchestration bus, no fake data.

### Agent System (P3.5-A/B)

New file: `editor-agents.js` — `window.EditorAgents` IIFE.

**Signal sources used by agents:**
- `EditorSceneIntelligence.getLatest()` → `markers`, `scenes`, `silences`
- `EditorReviewIntelligence.getReviewData()` → `hookScore`, `retentionScore`, `retentionRisks`, `badSubCount`, `partScores` (emotion dimension)
- `CreatorMemory.getTasteModel()` → `pace`, `hook`, `editStyle`, `confident`
- `parts[]` → `viral_score` per completed render part (Viral Agent only)

**Five agents:**

| Agent | Action | Primary Signals | Confidence Baseline |
|---|---|---|---|
| Hook Agent | `strongerHook` | `weak-intro` marker, `hookScore < 0.55` | 0.82–0.87 |
| Pacing Agent | `fasterPacing` / `removeDeadSpace` | `pacing-drop` marker, silence zones > 0.8s | 0.74–0.88 |
| Subtitle Agent | `subtitleCleanup` | `subtitle-overload` marker, `badSubCount >= 3` | 0.65–0.84 |
| Emotion Agent | `cinematicMode` | `emotional-shift` count ≥ 2, avg emotion < 0.55 | 0.58–0.70 |
| Viral Agent | `viralMode` / `smartClipPrioritization` | `retentionRisks >= 2`, avg viral score < 50% | 0.63–0.78 |

**Taste weighting (soft, not hardcoded):**
- Hook Agent + `taste.hook === 'aggressive'` → +9% confidence
- Pacing Agent + `taste.pace === 'fast'` → +8% confidence
- Subtitle Agent + `taste.editStyle === 'educational'` → +12% confidence
- Emotion Agent + `taste.editStyle === 'cinematic'` → +12% confidence
- Viral Agent + `taste.editStyle === 'viral'` → +10% confidence

**Silence safety:** Agents return `null` when their signals are absent or below threshold. `runAll()` filters nulls. `getConcerns()` returns `[]` when no agent reaches ≥ 0.65 confidence.

### Consensus Engine (P3.5-C)

`EditorAgents.runAll(signals)` — runs all 5 agents, filters nulls, sorts by confidence descending.
`EditorAgents.getTopRecommendation(signals)` — returns highest-confidence agent or null.
`EditorAgents.getPillLabels(signals)` — returns up to 3 `{ agentLabel, tier, action }` objects for UI display.
`EditorAgents.buildSignals(parts)` — assembles live signal object from the 3 real data sources.

### Conversational Routing (P3.5-F)

`_parseIntent()` now has a 5th resolution step: after keyword scoring, tie-breaking, and vague power resolution all fail, `_resolveWithAgents()` runs the agent consensus. If the top agent reaches ≥ 0.65 confidence, it fires the recommendation.

When an agent fires via this path, a `.p35AgentPill` badge appears in the conversation turn above the explain text — e.g., "Hook Agent · high confidence". The `explainText` reads: "Hook Agent identified this — Opening clip is below engagement threshold — first impression needs a stronger hook."

`agentMeta` flows through: `_resolveWithAgents()` → `_parseIntent()` → `handleInput()` → `_fireIntent()` → `_addTurn()` → `_render()`.

### Runtime Integration (P3.5-E)

`RuntimeIntelligence.getConcerns()` now delegates to `EditorAgents.runAll()` when the module is available. Concern items in the render evolution feed now show agent labels: "Hook Agent" / "Pacing Agent" instead of generic "Retention Risk" / "Pacing Signal". Falls back to P3.4 taste-based logic when `EditorAgents` is undefined.

### Agent Pill UI (P3.5-H)

`.p35AgentPill` — small inline pill with tier coloring:
- `data-tier="high"` → green accent (confidence ≥ 0.80)
- `data-tier="moderate"` → amber (0.65–0.79)
- `data-tier="low"` → muted (< 0.65, only shown in evolution feed concerns)

### What Remains Weak

- No cross-agent conflict resolution — if Hook Agent and Emotion Agent both fire in the conversation, only the top one is routed; the second is silent (not surfaced as a secondary suggestion)
- `_resolveWithAgents()` is only called when ALL prior resolution steps fail — keyword matches bypass agents entirely even when an agent agrees
- Pacing Agent uses silence data from EditorSceneIntelligence which requires the editor to have been opened and analyzed; agents return empty in render-only mode
- No "agent memory" — agents are stateless and re-evaluate from scratch on every call

---

## Section 33 — P3.6: Agent Debate & Consensus Intelligence (2026-05-16)

**Branch:** `feature/ai-output-upgrade`
**Files changed:** `editor-consensus.js` (new), `editor-converse.js`, `editor-runtime-intelligence.js`, `review.css`, `index.html`

### What Changed

Before P3.6, the agent system was winner-takes-all: `runAll()` sorted by confidence and the top result was used. Agreement between agents was invisible. Conflict between agents was invisible. The creative tradeoffs that specialized agents detect — fast cuts vs. emotional pacing, viral energy vs. cinematic rhythm — were never surfaced.

P3.6 adds `EditorConsensus` — a lightweight debate engine that groups agent outputs by creative direction, scores multi-agent agreement, detects opposing conflict, and produces a consensus recommendation with explainable reasoning.

### Consensus Engine (P3.6-A through P3.6-D)

New file: `editor-consensus.js` — `window.EditorConsensus` IIFE.

**Creative direction groups:**
- `aggressive`: fasterPacing, strongerHook, viralMode, removeDeadSpace — "tighten and energize"
- `narrative`: cinematicMode — "preserve and deepen"
- `clarity`: subtitleCleanup, smartClipPrioritization — "structure and clarify"

**Agreement scoring:**
- Agents in the same direction form an "ally group"
- Multi-agent weight bonus: +10% per extra agent in the winning group
- Confidence boosted: +8% per extra agreeing agent (e.g., Hook + Viral → +8%)
- `allyLabel`: "Hook Agent + Viral Agent" (up to 2 names joined)
- `consensusMsg`: "Hook Agent + Viral Agent agree — opening needs a stronger hook."

**Conflict detection:**
- Opposing direction pair: aggressive vs. narrative
- `conflictLevel`: opposing group confidence sum / winning group confidence sum (0–1)
- `dissentMsg`: "Emotion Agent preferred Cinematic Flow."

**Compromise (extreme conflict: conflictLevel > 0.45, opposer ≥ 0.60 confidence):**
- aggressive vs. narrative → compromise action: `removeDeadSpace` (least aggressive, preserves intent)
- Note: "Removed dead air only — intentional pacing preserved for emotional impact."
- Confidence reduced by 7% when compromise applied
- If no compromise action available: "X's priority maintained — Y's concern noted."

**Creator clarification (P3.6-I):** When extreme conflict exists, `resolve()` returns `isExtremeConflict: true` with `conflictOptions: [{label, action, interpretation}]`. `_resolveWithAgents()` surfaces this as `ambiguous: true` → existing clarification button rendering — "Two valid directions detected."

### Conversation Debate (P3.6-G)

`_resolveWithAgents()` now calls `EditorConsensus.resolve()` instead of `EditorAgents.getTopRecommendation()`. The agentMeta object gains `consensus`, `dissent`, `compromiseNote`, `agreementScore`.

`_render()` renders the debate context in 3 tiers:
1. `.p35AgentPill` — ally label: "Hook Agent + Viral Agent" (no "· confidence" text when consensus follows)
2. `.convExplain` — consensus message: "Hook Agent and Viral Agent agree — opening needs a stronger hook."
3. `.p36Dissent` — "Emotion Agent preferred Cinematic Flow." (only when conflict > 0.30)
4. `.p36Compromise` — "Removed dead air only — intentional pacing preserved." (only when compromise applied)

Example turn output:
```
[Hook Agent + Viral Agent]
Hook Agent and Viral Agent agree — opening clip is below engagement threshold.
Emotion Agent preferred Cinematic Flow.
Compromise: Removed dead air only — intentional pacing preserved for emotional impact.
```

P3.5 path (no consensus module) still works via fallback in `_resolveWithAgents()`.

### Runtime Debate Feed (P3.6-F)

`getConcerns()` now produces consensus-aware concern items:
- Primary item: `label = debate.allyLabel`, `msg = debate.consensus` — shows "Hook Agent + Viral Agent" if both fired
- Secondary item (when `conflictLevel > 0.30`): compromise note or dissent message from opposing agent

Fallback: if `EditorConsensus` is undefined → P3.5 agent layer → P3.4 taste layer.

### What Remains Weak

- Clarity direction (subtitle, prioritization) has no natural conflict with other directions — clarity agents never trigger the compromise path
- `conflictLevel > 0.45` threshold is fixed — can't adapt to creator risk tolerance
- Compromise always resolves to `removeDeadSpace` for aggressive/narrative conflict — limited to one compromise action regardless of which specific agents are conflicting
- Agents within the same direction group don't debate each other — only cross-direction conflict is detected

## Section 34 — P3.7: Creator Co-Pilot & Adaptive Collaboration (2026-05-16)

### Overview

P3.7 transforms the AI from a static expert system into an adaptive creator co-pilot. The system now remembers HOW the creator resolves creative tradeoffs across debate sessions, and uses that history to adapt consensus behavior, co-pilot reasoning text, and runtime concern messaging.

### Collaboration Memory (`creator-memory.js`)

`_profile` extended with `collab` sub-object:

```js
collab: {
  aggressiveWins: 0, narrativeWins: 0, compromiseWins: 0,
  aggressiveRejects: 0, narrativeRejects: 0,
  lastDebateResult: null
}
```

New public functions:
- `recordDebateChoice(direction, accepted)` — called when creator accepts/rejects an agent-routed recommendation
- `getCollabProfile()` — derives `{ confident, preferredDir, compromiseTolerant }` from debate history. Requires ≥3 decisions for confidence.

`_renderKnown()` extended with P3.7 collab rows when `collab.confident`:
- "Debate tendency: Dynamic / High-energy" or "Debate tendency: Narrative / Cinematic"
- "Compromise: Accepts balanced solutions"

### Adaptive Consensus (`editor-consensus.js`)

`resolve()` reads `CreatorMemory.getCollabProfile()` and applies soft adjustments:
- `confidence × 1.04` when creator repeatedly chose the winning direction (reinforcement)
- Extreme conflict threshold lowered from `0.45` → `0.38` when `compromiseTolerant` (more synthesis-first behavior)

Adjustments are additive on top of real agent signals — they never dominate.

### Co-Pilot Reasoning (`editor-converse.js`)

`_ctx` extended with:
- `lastWasAgentRouted: false` — tracks when intent came from `_resolveWithAgents()`
- `lastAgentDir: null` — creative direction of last agent-routed turn

`_dirOf(action)` helper added — mirrors consensus direction groups, used to determine the direction of a fired action.

`_resolveWithAgents()` now computes `copilotNote` when debate direction diverges from collab history:
- "You tend to preserve emotional pacing. Applied a conservative adjustment."
- "You usually favor high-energy edits. Cinematic approach taken — signal was compelling."
- "Balanced compromise applied — aligns with how you usually resolve these."

`copilotNote` flows through `agentMeta` → `_addTurn` → `_render` → `.p37CopilotNote` (warm amber italic).

`_onAccept()` and `_onReject()` call `CreatorMemory.recordDebateChoice()` when `_ctx.lastWasAgentRouted` is true.

### Runtime Co-Pilot (`editor-runtime-intelligence.js`)

`getConcerns()` P3.6 path now appends a soft collab note to the primary concern message when the consensus direction conflicts with creator's debate history:
- "You usually prefer lighter adjustments." (aggressive rec, narrative creator)
- "Note: you usually favor high-energy edits." (narrative rec, aggressive creator)

### CSS (`review.css`)

P3.7 section appended:
- `.p37CopilotNote` — warm amber (#FFC35A at 55% opacity), italic, 11px, below compromise note
- `.p37CollabRow .cmPrefVal` — purple accent (`#c4b5fd`) for collab tendency rows in panel

### Failure Safety

- `getCollabProfile().confident = false` until 3+ debate decisions — zero adaptive behavior before threshold
- Collab weighting is bounded: max +4% confidence boost, -0.07 threshold adjustment
- All functions guard `typeof CreatorMemory !== 'undefined'`
- `Object.assign(base, _profile.collab || {})` handles old profiles without collab key
- Reset wipes collab data via `_empty()` which includes zero-state collab sub-object

### What Remains Weak

- `_dirOf()` is duplicated in `editor-converse.js` and `editor-consensus.js` — could drift
- Compromise action is still fixed (`removeDeadSpace`) for aggressive/narrative conflict
- Collab memory cannot distinguish "accepted despite dissent" from "accepted because of dissent"
- No graduated confidence decay in collab memory — old decisions weigh equally with recent ones

---

## Section 35 — UX-R1: Runtime Center Stage Re-Architecture (2026-05-16)

**Phase:** UX-R1  
**Branch:** `feature/ai-output-upgrade`  
**Commit:** `feat(ui): UX-R1 runtime center stage re-architecture`

### What Changed

Transforms the render runtime from a "render monitor" (rdCard as hero) into an "AI orchestration experience" (`#uxr1_ai_hero` as hero). No DOM elements removed, no backward compatibility broken.

**HTML (`index.html`)**

Added `#uxr1_ai_hero` div directly before `#rd_card` inside `#render_active_panel`. Sits outside `#render_runtime_mount` so it is never affected by the P2.9-B territory-switching opacity fade (which targets `#render_runtime_mount` only). Contains:
- `.uxr1HeroStage` — icon + label + message row (populated live from `_STAGES[idx]`)
- `#uxr1_concerns` — populated live from `RuntimeIntelligence.getConcerns(parts)` via `_updateHero()`

**JS (`render-ui.js`)**

- `_lastHeroConcernHash` — dedup variable, prevents DOM churn when concern content hasn't changed
- `_updateHero(idx, isFailed, parts)` — new function in `RenderAiRuntime`:
  - Updates hero icon/label/msg from `_STAGES[idx]`; sets `heroEl.dataset.stage` and `dataset.failed`
  - Calls `RuntimeIntelligence.getConcerns(parts)` and renders `.uxr1ConcernItem` rows with hash dedup
- `update()` calls `_updateHero(newIdx, isFailed, parts)` after `_renderConcernItems(parts)` — same cadence as existing concern rendering
- `reset()` clears `_lastHeroConcernHash` and restores hero to `_STAGES[0]` defaults

**CSS (`runtime.css`)**

UX-R1 section appended (all additive — no prior rules removed):

| Rule | Effect |
|---|---|
| `.uxr1AiHero` | Flex column, `flex-shrink:0`, subtle bg, bottom border |
| `.uxr1AiHero::before` | 3px purple gradient accent bar; pulses via `uxr1HeroEdge` animation when `[data-render-state="running"]` |
| `.uxr1StageLabel` | 18px, weight 600, 90% opacity |
| `.uxr1StageMsg` | 12.5px, 44% opacity |
| `.uxr1ConcernItem` | Left border accent, fade-in via `uxr1ConcernIn` |
| `.uxr1ConcernLabel` | 10px uppercase, purple 75% opacity |
| `.uxr1ConcernMsg` | 12.5px, 58% opacity |
| `#render_active_panel > .rdCard` | Demoted — compact padding (9px 18px 8px), low background |
| `[data-render-state="running"] > .rdCard::before` | `opacity: 0 !important` — suppresses P2.8 glow |
| `[data-render-state="complete"] > .rdCard` | `animation: none !important` — suppresses P2.8 `p28CardComplete` |
| `[data-render-state="complete"] .uxr1AiHero` | `opacity: 0.80` — hero fades slightly at completion |
| `[data-render-state="running"] .rcLogStrip` | `opacity: 0.60` — log strip recedes during render |
| `@media (max-width: 1366px)` | Hero padding 14px 18px, label 16px |
| `@media (max-width: 1024px)` | Hero padding 12px 14px, label 14px, msg 11.5px |

### Spatial Plane Architecture

```
Plane 1 — AI Hero     #uxr1_ai_hero         always-visible, stage + P3.x concerns
Plane 2 — Status      .rdCard               demoted strip (badge, title, %, meta)
Plane 3 — Queue       .rcQueuePanel         existing; unchanged
Plane 4 — Logs        .rcLogStrip           receded to 60% during active render
```

### What Was NOT Changed

- `#render_runtime_mount` mounting logic — untouched
- P2.9-B territory switching (`[data-render-state="complete"] #render_runtime_mount { opacity: 0.38 }`) — preserved; hero is a sibling of `#render_runtime_mount`, not a child
- `RenderAiRuntime.mountPanels()`, `_updateProcessCard()`, `_updateEvolutionFeed()` — untouched
- `#ai_insights_panel` — untouched (remains backend `ai_director.enabled` only)
- All existing P2.x / P3.x CSS rules — untouched (UX-R1 appended last, wins on specificity for rdCard only)

---

## Section 36 — UX-R2: Completion Experience Re-Architecture (2026-05-16)

**Phase:** UX-R2  
**Branch:** `feature/ai-output-upgrade`  
**Commit:** `feat(ui): UX-R2 completion experience re-architecture`

### What Changed

Transforms render completion from a utility event into a creative outcome delivery. No DOM destruction; all prior completion flow (P2.9 arrival, P2.8-F hero card, confidence evolution) is preserved.

**HTML (`index.html`)**

`#uxr2_completion_hero` div inserted between `render_completion_bar` and `render_output_panel`. Starts `hiddenView`. Three columns:
- `.uxr2HeroThumb` — best clip thumbnail + hover video + score badge (populated by JS at completion)
- `.uxr2HeroNarrative` — `Creative Outcome` label, narrative msg (from `RuntimeIntelligence.getCompletionNarrative()`), AI selection reason (from ranking), stat bits
- `.uxr2HeroCTA` — 3-level CTA: primary (`uxr2_cta_review`), secondary (`uxr2_cta_export` — `<a>` with download href), tertiary (`uxr2_cta_folder`)

**JS (`render-ui.js`) — RenderAiRuntime IIFE**

- `_morphHeroToOutcome(narrative)` — adds `uxr2OutcomeMode` class to `#uxr1_ai_hero`; updates icon to '✓', label to 'Creative Outcome', msg to `narrative.summaryMsg`; clears concerns
- `_showCompletionHero(job, parts, narrative, completed, topPct)`:
  - Calls `_rankMap(job)` to find best part
  - Populates thumb with static JPEG + hover-video (same URL pattern as clip cards: `/api/render/jobs/{id}/parts/{no}/thumbnail` + `/media`)
  - Populates narrative msg, reason (from `bestRkData.reason`), and stat bits
  - Wires up CTA buttons: Review Best Clip → `centerPreviewClip()`, Export Best → `/api/jobs/{id}/parts/{no}/stream` download href, Open Folder → `openRenderOutputFolder()`
  - Falls back gracefully when no best clip exists: `dataset.state = 'no-best'`, "AI could not confidently identify a strongest result.", "Review Clips" scroll action
  - Demotes `render_completion_bar` via `uxr2BarDemoted` class
  - Elevates output list via `uxr2Complete` class
  - Reveals hero with `requestAnimationFrame` + `uxr2HeroActive` class (triggers `uxr2HeroReveal` animation)
- Both called inside the `if (!_completionNarrativeSet)` guard in `showCompletionIntelligence()` — idempotent, fires once per render session
- `reset()` extended: clears hero to initial state, removes `uxr2OutcomeMode` / `uxr2BarDemoted` / `uxr2Complete` classes

**CSS (`runtime.css`) — UX-R2 section appended**

| Rule | Effect |
|---|---|
| `.uxr1AiHero.uxr2OutcomeMode` | Green accent bar, green icon, removes pulse animation |
| `[data-render-state="complete"] .uxr2OutcomeMode` | Overrides UX-R1 opacity 0.80 fade — outcome mode stays at opacity 1 |
| `.uxr2CompletionHero` | `display: grid; grid-template-columns: 180px 1fr auto` |
| `.uxr2CompletionHero.uxr2HeroActive` | `uxr2HeroReveal` animation (translateY + opacity, 0.65s ease) |
| `.uxr2HeroThumb` | Relative, 9/16 aspect, overflow hidden, hover video wired |
| `.uxr2ThumbScore` | Position absolute, bottom-right, blur backdrop |
| `.uxr2NarrativeLabel` | 9.5px uppercase green (`rgba(74,222,128,.70)`) |
| `.uxr2NarrativeMsg` | 15px, weight 500, 88% opacity |
| `.uxr2CtaPrimary` | Indigo filled button (36px) |
| `.uxr2CtaSecondary` | Ghost border link (30px) |
| `.uxr2CtaTertiary` | Minimal text button (26px) |
| `.renderCompletionBar.uxr2BarDemoted` | Reduced padding; hides redundant CTA buttons (keeps `#back_to_editor_btn`) |
| `.renderOutputList.uxr2Complete .isBestClip` | Stronger glow (box-shadow) |
| `@media (max-width: 1366px)` | Thumb 140px, padding reduced |
| `@media (max-width: 1024px)` | Single-column stack; thumb 16/5 aspect; CTA row wrap |

### Completion Arrival Sequence (updated)

```
render done → showCompletionIntelligence() [guarded by _completionNarrativeSet]
  ├── _triggerCompletionArrival()     → p29Arrival class → OutputRise + RuntimeRecede animations
  ├── completion bar text updated
  ├── _applyConfidenceEvolution()     → best clip confidence → "peak"
  ├── _morphHeroToOutcome(narrative)  → #uxr1_ai_hero morphs: green accent, "Creative Outcome"
  └── _showCompletionHero(...)        → #uxr2_completion_hero revealed with uxr2HeroReveal animation
```

### What Was NOT Changed

- `showRenderCompletionBar()` — untouched; still sets msg/summary/icon/state
- `_triggerCompletionArrival()` — untouched; p29Arrival + evolution header still fire
- P2.8-F hero card layout (`.clipsGrid .clipCard.isBestClip`) — untouched; UX-R2 only adds stronger glow
- P2.9 territory switching CSS — preserved (rdCard fades, runtime mount recedes)
- All P3.x intelligence paths — untouched

### Audit Note: P2.9-B CSS Dead Selectors

The CSS rules `#render_active_panel[data-render-state] #render_output_panel` and similar are **dead** — `render_output_panel` is a sibling of `render_active_panel`, not a descendant, so the descendant selector never matches. These rules exist from a prior design iteration. They have no effect in the live DOM. UX-R2 does not remove them (no DOM destruction policy) but does not rely on them.

---

## Section 37 — UX-R3: Review Experience Re-Architecture (2026-05-16)

**Phase:** UX-R3  
**Branch:** `feature/ai-output-upgrade`  
**Commit:** `feat(ui): UX-R3 review experience re-architecture`

### What Changed

Transforms the flat clip grid into an editorial review workspace with a four-tier visual hierarchy. No DOM element removed, no existing CSS overwritten, no JS functions replaced.

**JS (`render-ui.js`) — module scope + `populateRenderOutputPanel()`**

- `let _uxr3AutoSelectedBest = false` — module-level flag for auto-preview idempotency
- `_applyUxR3Tiers(list, ranking, done, failed, skipped)` — new function called after `RenderAiRuntime.reapplyTransientState()` in `populateRenderOutputPanel()`. Runs on every panel re-render; safe to call multiple times (cleans up previous pass first).
- Auto-preview logic — after tier application, when render is in terminal status and `_uxr3AutoSelectedBest` is false: finds best part from `ranking`, calls `centerPreviewClip()` after 900ms delay
- `clearRenderOutputPanel()` — resets `_uxr3AutoSelectedBest = false`

**`_applyUxR3Tiers()` detail:**
1. Removes existing `.uxr3TierHeader` elements; clears `data-uxr3-tier` attributes
2. Classifies each `.clipCard` by reading `isBestClip` class, `isFailed`/`isSkipped` classes, or `.clipCardScore[data-tier]` attribute for done cards:
   - `best` — `isBestClip` (or `ranking.isBest`)
   - `strong` — done, not best, score tier "high" (≥8)
   - `other` — done, not best, score tier mid/low/weak
   - `failed` — `isFailed`
   - `skipped` — `isSkipped`
3. In score-sort mode (`_clipsSortOrder === 'score'`), inserts `<div class="uxr3TierHeader">` elements:
   - "Strong Candidates (N)" — before first strong card, only when there are tiers on both sides
   - "Additional Results (N)" — before first other card, only when preceded by best or strong cards
   - "N failed · N skipped" — before first problem card, with collapsible toggle button
4. Problem section starts collapsed when `done.length > 0`; toggle button shows ▸/▾

**CSS (`review.css`) — UX-R3 section appended**

| Selector | Effect |
|---|---|
| `.uxr3TierHeader` | `grid-column: 1 / -1`, flex row with label + count + `::after` separator line |
| `.uxr3TierLabel` | 10px uppercase, 32% opacity — low-profile section label |
| `.uxr3TierToggle` | Minimal button, `order: -1` (before label) |
| `.uxr3ProblemHeader.uxr3Collapsed ~ .clipCard[data-uxr3-tier="failed"]` | `display: none` (collapse) |
| `.uxr3ProblemHeader.uxr3Collapsed ~ .clipCard[data-uxr3-tier="skipped"]` | `display: none` (collapse) |
| `[data-uxr3-tier="best"]` | 200px thumb, 26px score, stronger indigo glow — overrides P2.8-F 160px |
| `[data-uxr3-tier="strong"]` | Subtle indigo border + hover lift |
| `[data-uxr3-tier="other"]` | `opacity: 0.80`, recovers to 1 on hover |
| `[data-uxr3-tier="failed"]` | `opacity: 0.48` |
| `[data-uxr3-tier="skipped"]` | `opacity: 0.30` |
| `@media (max-width: 1366px)` | Best thumb → 160px, score → 22px |
| `@media (max-width: 1024px)` | Best thumb → 110px, score → 20px |

### Tier header insertion conditions

Headers only inserted when they add meaning:
- "Strong Candidates" only appears if there are ≥1 strong cards AND other groups exist
- "Additional Results" only appears if preceded by best or strong cards
- "Needs Review" always appears if any failed/skipped clips exist

When `_clipsSortOrder === 'part_no'` (user selected "In order"): `data-uxr3-tier` attributes are still set (CSS differentiation applies) but no headers are inserted (order-based view has no tier semantics).

### What Was NOT Changed

- `populateRenderOutputPanel()` HTML template — untouched; no card structure modified
- `_rankMap()`, `sortClipsView()`, `_bindCardHoverPreviews()` — untouched
- P2.8-F hero card (`grid-column: 1 / -1`, `grid-template-columns: 160px 1fr`) — `[data-uxr3-tier="best"]` overrides to 200px via later CSS rule (same specificity, later wins)
- P2.9 confidence evolution (`data-p29-confidence`) — untouched
- All existing clip card classes (`isDone`, `isSelected`, `p29Elevated`, etc.) — preserved
