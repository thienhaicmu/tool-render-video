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

**UI-R3B — Downloads Screen**: Let users manage downloaded output files, view download history, and trigger re-downloads from completed job parts.
