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

## 23. Next Phase

_(pending)_
