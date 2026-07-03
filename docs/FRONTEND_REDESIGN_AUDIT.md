# AI Clip Studio — Frontend Product Audit & Redesign Blueprint

> **Status:** Reverse-engineered from source (`frontend/src`, ~40 kLOC React 18 + Zustand + Vite) on 2026-07-03.
> **Constraint:** The backend is frozen. Every recommendation here is achievable with the **existing** REST + WebSocket surface documented in §2.5. No backend feature is invented, removed, or assumed.
> **Audience:** A senior frontend team that will rebuild the UI without touching the backend.

---

## PHASE 1 — PRODUCT UNDERSTANDING

### 1.1 Purpose
An **offline-first desktop app** (Electron shell + local FastAPI backend on `127.0.0.1:8000`) that turns long-form local video into short-form vertical clips with AI-selected segments, platform-styled subtitles, optional AI narration/TTS, motion-aware reframing, and per-clip virality scoring. A secondary "Recap" mode assembles one long story-structured review video instead of many clips. A bundled multi-platform **downloader** (yt-dlp) feeds source files into the render pipeline.

### 1.2 Target users
- **Primary:** high-volume short-form creators / editors (the CommandPalette copy explicitly references "a creator running 100 videos/week"). Bilingual EN/VI — Vietnamese is a first-class locale, not an afterthought.
- **Secondary:** power users who batch-download source footage and iterate on render configs.

### 1.3 Core value
"Drop a video → AI picks the best moments → get ranked, publish-ready vertical clips, fully offline." The differentiator vs OpusClip/Captions is **local execution + no cloud requirement** (cloud LLM is optional, keys in `.env`).

### 1.4 Business workflow (canonical happy path)
```
(optional) Download source ──┐
                             ▼
Add source (drop/browse/handoff) → auto prepare-source (probe)
   → Configure (Quick or Advanced) → Start Render (enqueue)
   → job runs in background queue → Monitor (WS live) → Results (ranked clips)
   → Export / Save / Feedback (👍👎) → (optional) Trim in Editor → re-render
   → Library (history, re-run, duplicate, delete)
```

### 1.5 Feature & product hierarchy
```
AI Clip Studio (Electron)
├── Studio  (clip-studio)                ← default landing
│   ├── Render tab   → RenderWorkflow (Create → Monitor → Results)
│   └── Download tab → DownloadTab (yt-dlp staging + jobs)
├── Library (jobs/HistoryScreen)         ← history, batch ops, detail drawer
├── Download (sidebar)                   → same DownloadTab via DownloadScreen wrapper
├── Editor  (deep-linked only)           → trim preview (UI-only trim today)
├── Settings                             → 9 sections (see §12)
└── Publish                              → placeholder ("coming soon")
Global chrome: Sidebar rail · Topbar · ActiveJobsDock · QueueDrawer · CommandPalette (⌘K) · NotificationCenter · Toasts · ConfirmDialogHost
```

### 1.6 Primary vs secondary journeys
- **Primary:** Create clips from a local file; Monitor; collect results.
- **Secondary:** Download → "Send to Render" handoff; Duplicate a past job; Retry failed / Resume interrupted; Batch-manage the queue; Recap-mode long video; Trim + re-render a single clip.

### 1.7 Backend dependencies (what the FE cannot do without)
- **Job state** is 100% server-owned (`data/app.db`). The FE holds *no* durable job state — it polls `/api/jobs/history` and streams `/api/jobs/{id}/ws`.
- **All media** (thumbnails, clip mp4, preview video, subtitle-preview PNG) are backend URLs.
- **All AI** (segment selection, ranking, story model, narration) happens server-side; FE only renders results + a `test-cloud-ai` connectivity probe.

### 1.8 Frontend responsibilities
Config authoring + validation mirror, live progress visualization, results/ranking presentation, queue orchestration UI, notifications, i18n, theming, keyboard command surface, Electron IPC bridges (file/dir pickers, `openPath`, `pathExists`, cookie file pick).

### 1.9 Store ↔ API ↔ WS relationships
| Store | Owns | Talks to |
|-------|------|----------|
| `uiStore` | active panel, notifications(+history), lang, cross-screen handshakes (`duplicateSeedJobId`, `sendToRenderSourcePath`, `monitorJobId`, `newRenderRequest`), queue drawer flag | localStorage |
| `jobsStore` | shared 4 s poll of `/jobs/history` + `/jobs/queue/status`; `items`, `active`, `queueOrder`, `heldIds`; refcounted | `getJobHistory`, `getQueueStatus` |
| `renderStore` | thin optimistic map of submitted jobs, `activeJobId` | `submitRender` |
| `editorStore` | selected job/part, media URL, **UI-only** trim | (none — build media URL) |
| `qualityStore` | on-demand quality reports cache | `getJobQualitySummary`/part quality |
| `themeStore` | light/dark/system tri-state → `<html data-theme>` | localStorage + `matchMedia` |

Live progress is **not** in a store — it lives in `useRenderSocket` local state inside `RenderWorkflow`. This is a key architectural fact (see §2 & §11).

### 1.10 Pipeline summaries
- **Render pipeline (FE view):** `prepareSource` (probe, returns `session_id` + preview) → `POST /render/process` (enqueue) → WS stages `queued→…→rendering→done` with per-part `parts[]` → on terminal, fetch `parts`, `quality`, `ranking`, `ai-summary`.
- **Queue pipeline:** server scheduler; FE reads `queue/status.order`/`held`, mutates via move-top/bottom/move(delta)/hold/resume; dock + drawer are the two surfaces.
- **Download pipeline:** stage URLs (client `getVideoInfo` enrich) → `startDownload` per item → poll `/downloader` jobs every 1.5 s → done rows offer "Send to Render".
- **History pipeline:** paginated `/jobs/history` with server status filter + client text search; cumulative "load more"; live merge from the shared poll.
- **Settings pipeline:** 9 GET/PUT envelope endpoints under `/api/settings/*` plus system/maintenance.

---

## PHASE 2 — ARCHITECTURE REVIEW

### 2.1 Folder architecture (as-is)
```
src/
  api/            17 thin fetch modules (1 endpoint-group each)
  components/     ui/ (design-system primitives) · icons · quality · CommandPalette · NotificationCenter
  features/
    clip-studio/  render/ (the monolith) · download/ · history/ (dormant) · ClipStudio shell
    jobs/         Library (HistoryScreen + JobList/Item/Drawer/Filters/…)
    editor/       trim preview
    progress/     JobProgressPanel + sub-parts (partially parallel to render/steps)
    quality/      QualityPanel family
    settings/     one 1288-LOC SettingsScreen
    download/     DownloadScreen wrapper
  hooks/          useRenderSocket, useBackendHealth, useJobCompletionNotifier, useGlobalShortcuts, useSystemResources
  layouts/        AppShell, Sidebar, Topbar, ActiveJobsDock, QueueDrawer
  stores/         6 zustand stores
  styles/         tokens.css (451) · global.css · motion.css · polish.css (1330)
  types/          api.ts (624) · enums.ts · openapi-generated.ts (4091, generated)
  websocket/      RenderSocketClient + events
  i18n/           translations.ts (785) + render-local i18n.ts (512)
```
**Verdict:** feature-first and mostly sound. Two structural problems dominate (below).

### 2.2 The two architectural problems

**(A) `RenderWorkflow.tsx` is a god component (1003 LOC + 3 step files 500–1080 LOC each).**
It owns: view routing (`create|monitor|results`), source list, prepare-source lifecycle, config draft (localStorage), server-defaults hydration, 3 cross-screen handshake effects, submit (single + batch + 409 dedup navigation), cancel/retry/resume/rerender, terminal data-loading orchestration, toast wiring, and the WS hook. State is **17+ `useState` + 8 `useRef`** in one function. This is the single biggest maintainability and redesign risk.

**(B) Duplicated progress/quality subsystems.**
`features/progress/*` (JobProgressPanel, ProgressClipsGrid, ProgressStageTimeline, AiActivityPanel…) and `features/quality/*` are a *second* implementation of what `render/steps/StepRendering` + `StepResults` already render inline. The render flow does **not** use `features/progress` — it re-implements clip grids/timelines locally. Dead-ish parallel code = drift risk.

### 2.3 Routing
No router library. Navigation is `uiStore.activePanel` (a union type) → `PANEL_MAP` in `App.tsx` with `React.lazy` + idle prefetch. Deprecated aliases (`render`, `history`, `editor`) still map. Deep-linking, back/forward, and shareable URLs are impossible today. **Editor is only reachable via `setActivePanel('editor')` from a clip's ··· menu** — it has no nav entry.

### 2.4 React patterns
- Good: `React.memo` on the 3 heavy steps; refcounted shared poll (`jobsStore`); progress fingerprinting in `useRenderSocket` to skip no-op renders; per-step `ErrorBoundary`; code-splitting + idle prefetch; WS→HTTP-polling fallback (Sacred Contract compliance).
- Weak: **inline `styles` objects** everywhere (Topbar, Sidebar, Dock, Palette, StepResults, StepRendering, Settings) recreated each render; heavy prop-drilling of `t`, `cfg`, `setCfgKey`; cross-screen coordination via ad-hoc `uiStore` "signal" fields + `queueMicrotask` guards (fragile).

### 2.5 Backend contract inventory (the frozen surface — DO NOT change)
**Render** `/api/render/*`: `POST process` · `POST {id}/cancel` · `POST resume/{id}` · `POST retry/{id}` · `POST prepare-source` · `DELETE prepare-source/{id}` · `GET preview-video/{id}` · `GET preview-transcript/{id}` · `GET subtitle-preview?…` · `POST test-cloud-ai` · `GET jobs/{id}/parts/{n}/media`.
**Jobs** `/api/jobs/*`: `GET {id}` · `GET history` · `GET {id}/parts` · `GET {id}/parts/{n}/quality` · `GET {id}/quality` · `GET {id}/ai-summary` · `GET {id}/recap-plan` · `DELETE {id}` · `DELETE {id}/parts/{n}/output` · `POST {id}/extend` · `GET queue/status` · `POST {id}/queue/{move-top,move-bottom,move,hold,resume}` · `WS {id}/ws`.
**Editing** `/api/jobs/{id}/parts/{n}/{trim,rerender,export}`.
**Feedback** `/api/feedback/jobs/{id}/parts/{n}` (GET/POST/DELETE).
**Downloader** `/api/downloader/*`: list, start, cancel, video-info, cookie-status, refresh-cookies, import-cookies.
**Settings** `/api/settings/*`: creator-context, render-defaults, output-dir, data-retention, performance, clear-history.
**System** `/api/system/resources` · `/health` (+ warmup) · `/api/upload-file` · `/api/presets`.
**WS event shape (frozen):** every progress frame carries `{ job, parts[], summary }`; additive channels: `{type:"event", event:{…}}` (live log), `{type:"ping"}` (keepalive), `{error}` (error frame), `recap.plan.ready` log event.

### 2.6 Dead / dormant / debt
- `features/clip-studio/history/HistoryTab.tsx` (497 LOC) — unmounted since S2.6; Library replaced it.
- `features/progress/*`, most of `features/quality/*` — parallel to render steps; verify consumers before reuse.
- `Publish` panel — placeholder.
- ~~Editor trim is UI-only~~ **CORRECTED (WP4):** only the `editorStore` trim *state* is UI-local; `EditorMetadataPanel` **does** call `POST …/trim`, `…/rerender`, `…/export`. WP4 fixed its post-action nav (`'history'`→`'queue'`) and added an Electron Browse + open-folder to Export. Not a gap.
- Legacy token aliases: 3 generations of tokens coexist (`--color-*`, `--surface-*/--accent-*`, prototype `--bg-*/--text-1..3/--fh/--fb/--fo`).

### 2.7 Scalability / maintainability / extensibility
- Scalability of lists: History uses cumulative pages (no virtualization) — fine to ~hundreds, will degrade. Live event log capped at 50 (good).
- Maintainability: dominated by the god component + inline styles + triple token system.
- Extensibility: adding a config field touches `types.ts`, `cfgDefaults`, `buildRenderPayload`, `payloadToConfig`, `StepConfigure`, and i18n — 6 edits. High friction.

---

## PHASE 3 — WORKFLOW REVIEW

For each workflow: purpose · current UX/UI · backend · state · pain · improvement (backend-compatible).

### 3.1 Add Source
- **UX:** `CreateHero` drop zone (empty) → on add, auto-`prepareSource` in background, `StepConfigure` renders immediately while probe streams in.
- **Backend:** `POST /render/prepare-source` → `{session_id, duration, title, export_dir}`; preview via `GET preview-video/{id}`.
- **State:** `sources[]`, `prepareResult`, `isPreparing`, `prepareError`, `preparedForRef`.
- **Pain:** Electron-only file existence check; multi-source supported but only the *first* source drives the preview/config; no thumbnail of the actual source frame until preview video loads.
- **Improve:** show a source filmstrip when >1 source; surface probe duration/title as a proper media card with real poster frame.

### 3.2 Configure
- **UX:** 3-column layout (left knobs · center live preview + style strip · right AI/SUB/NARR tabs). Quick/Advanced mode toggle hides advanced knobs. Live subtitle preview via real libass PNG (`subtitle-preview`) with CSS fallback; transcript overlay cycles real segments.
- **Backend:** all fields serialized by `buildRenderPayload` → `RenderRequestPublic` (88 FE fields). `test-cloud-ai` for provider check.
- **State:** one `cfg: ConfigState` (~40 fields) + `cfgTab` + `cfgMode`, draft-persisted to localStorage (800 ms debounce).
- **Pain:** dense; discoverability of Advanced-only options low; Recap vs Clips mode changes hidden knobs behind a confirm dialog; presets v2 is a bare `<select>` + "Save as"; no visual diff of what a preset changes.
- **Improve:** progressive disclosure with clearer Quick default; preset chips with preview; inline "what AI will do" explainer.

### 3.3 Enqueue / Start Render
- **UX:** "Start Render" → **"Added to queue"** toast, returns to a clean Create screen (does *not* pin to monitor). 409 dedup → auto-navigates to the running job's monitor. Double-submit guard.
- **Backend:** `POST /render/process`.
- **Pain:** the "added to queue, now what?" moment is under-designed — success is a toast + tiny "View" button; the mental model "my job is running somewhere else now" relies on the dock.
- **Improve:** a confirmation state with clear next actions (Monitor / New / View queue).

### 3.4 Monitor
- **UX:** `StepRendering` — status card (elapsed + ETA), stage phase text, segmented clip bar, `RenderStage` focus-card + filmstrip, adaptive single status line (cancelling>stuck>watchdog>ws-error>reconnecting>polling), AI Director panel, collapsible Event Log, bottom toolbar. Recap mode swaps to `RecapLiveView`.
- **Backend:** WS `/jobs/{id}/ws` → `{job,parts,summary}`; HTTP polling fallback after 6 WS attempts (~40 s); `POST {id}/extend` for watchdog.
- **State:** `useRenderSocket` (stage, jobStatus, progress, liveParts, liveEvents, recapPlan, ws flags) + local ETA refs.
- **Pain:** monitor is only reachable through explicit handshakes (`monitorJobId`); the ETA is heuristic; two progress bars (card + toolbar) show the same number; recap detection depends on a latched event.
- **Improve:** promote monitor to a first-class, deep-linkable job view; single authoritative progress element; clearer phase timeline.

### 3.5 Results
- **UX:** `StepResults` — hero (success/failed KPIs), collapsible AI Analysis (best clip, ranking, story model, rejected count), sort bar (viral/duration/newest), clip cards (score ring, tier badge, BEST, AI reason, feedback 👍👎, ··· menu), in-app player modal, detail side panel with 6-signal ranking breakdown + quality issues + metrics, Export panel (per-clip checklist + platform preset + metadata sidecar).
- **Backend:** `parts`, `quality?include_reports`, `ranking` (from `result_json.output_ranking`), `ai-summary`, `feedback`, `export`, `deletePartOutput`.
- **Pain:** enormous single component (1089 LOC) with heavy inline styling; two score sources (`partScores` quality vs `partRanks.output_rank_score`) reconciled ad hoc; detail panel vs player modal overlap in purpose.
- **Improve:** componentize (ClipCard, RankingBreakdown, ExportPanel, AiAnalysis); unify score display; clarify player vs detail.

### 3.6 Download → Render handoff
- **UX:** stage URLs, enrich via `getVideoInfo`, per-item quality, "Download N videos", done rows → "Send to Render" sets `sendToRenderSourcePath`; ClipStudio flips to Render tab; RenderWorkflow pre-fills source.
- **Backend:** `/api/downloader/*` (separate engine, not in render queueOrder).
- **Pain:** cookie management UX is power-user heavy (v20 warnings, manual cookies.txt import); polling at 1.5 s is a third poller.
- **Improve:** keep, but visually unify download rows with the render dock language.

### 3.7 Editor (trim) / re-render
- **UX:** reachable from a clip's ··· "Trim" and (WP2) a nav home; preview + trim sliders; **Apply Trim / Re-render / Export all call real backend endpoints** (EditorMetadataPanel).
- **Backend:** `POST …/trim` and `…/rerender` exist and are unused by the editor.
- **Pain (resolved):** earlier believed to be a no-op; verified wired in WP4. Remaining polish: dir-picker parity (done) + reveal output (done).
- **Improve:** wire the existing trim/rerender endpoints; give the editor a real nav home.

### 3.8 Library / re-run / duplicate / delete
- **UX:** `HistoryScreen` — header stats, filters (server status + client search), batch multi-select (shift-range, ESC clears), Load more, detail drawer.
- **Backend:** `history`, `deleteJob`, `retry`, `resume`, duplicate via `duplicateSeedJobId` handshake.
- **Pain:** "Retry" (retry failed parts) vs "Re-run" (resume) vs "Duplicate" are three near-synonyms with subtle differences users won't parse.
- **Improve:** relabel around intent; unify with the render entry points.

---

## PHASE 4 — UX REVIEW

| Dimension | Finding |
|-----------|---------|
| **Information architecture** | Overloaded: Studio has its own Render/Download sub-tabs *and* Download exists again in the sidebar (same component). Library ≈ home ≈ history (3 aliases → same screen). Publish is dead weight in nav. |
| **Navigation** | Icon-only 56px rail (4 items) + no labels except tooltips → low discoverability. Editor & monitor have no nav home. No URL/deep-link/back. |
| **Mental model** | "Start render returns me to an empty screen" is correct for throughput but disorienting; the job "moved" to the dock. Needs an explicit queue mental model. |
| **Discoverability** | ⌘K palette is powerful but invisible to new users; Advanced config knobs hidden; feedback→AI-training only revealed via a one-time toast. |
| **Onboarding** | None. First run drops you on an empty Create hero. No sample, no tour, no "what is a score" until a one-time tip. |
| **Accessibility** | Partial: `role="button"`+`tabIndex`+Enter/Space on custom segmented controls (good), aria-labels on rail. But: pervasive inline color-only status, tiny 9–11px type, low-contrast tertiary text, custom `<div>` toggles, modal focus-trap not guaranteed, no reduced-motion audit. |
| **Feedback** | Strong: toasts + notification history + OS notifications + dock attention rows + adaptive status line. |
| **Loading** | Good coverage: skeletons, spinners, screen-fallback, per-timeout data loads (12 s races). |
| **Error handling** | Strong: error-kind inference + fix-step lists, raw-error disclosure, WS→poll fallback, 409 navigation, per-step error boundaries. |
| **Empty states** | Present for Create, Results, Download, Editor, Library — but visually plain. |
| **Progressive disclosure** | Exists (Quick/Advanced, collapsible AI/Event panels) but inconsistent. |
| **Decision fatigue** | Configure is the pain point: platform, ratio, focus, duration, count, story-intel, trim, quality, AI provider/model/lang, subtitle style/size/translate, narration (lang/gender/mix/source/tone/reaction). ~20 decisions before one render. |
| **Consistency** | Broken: two shells' worth of styling merged; three token systems; inline styles vs CSS classes vs `polish.css`. |
| **Trust** | Mostly high (real previews, real scores, transparent AI) — but the dead Editor trim undermines it. |

---

## PHASE 5 — UI REVIEW

- **Visual hierarchy:** functional but flat; dense micro-typography (a lot of 9–11px). Cards rely on 1px hairline borders + faint shadows.
- **Typography:** 3 font stacks declared (`Inter` UI, `Space Grotesk` display, `JetBrains Mono`) **plus** prototype `Rajdhani`/`Orbitron` (`--fh/--fo`) still used across render/history. Scale is fine (`--text-xs..2xl`) but under-used; too much text sits at xs/sm.
- **Spacing/grid:** 4px base scale (`--space-1..16`) is good and mostly respected in CSS; inline-styled components drift.
- **Cards/buttons/inputs:** primitives exist in `components/ui/*` (Button, Card, Badge, ScoreBadge, StatusPill, ProgressBar, Panel, EmptyState) — but the render/results/settings screens largely **bypass** them with bespoke inline styles. Inconsistent button taxonomy (`btn-xs`, `btn-next`, `res-export-btn`, raw inline buttons).
- **Dialogs:** `ConfirmDialogHost` + imperative `confirmDialog()` — good pattern, consistently used.
- **Tables:** Download uses a hand-rolled grid; History uses a list; no shared data-grid.
- **Badges/pills:** many one-off inline pills (tiers, confidence, hybrid, platform, AI) — should be a single `<Badge variant>`.
- **Icons:** mixed — an `icons/index.tsx` set + inline SVGs in Sidebar/Topbar/Download + emoji (▶ ⬇ 👍 ⚡ ☁ 💻 🔥 ★ ✦). Emoji-as-icon is off-brand for "premium".
- **Charts/progress:** custom SVG score rings + CSS bar tracks — decent, reusable if extracted.
- **Animation/motion:** `motion.css` + spin keyframes + score animation; generally restrained. No systematic micro-interaction language.
- **Premium/modern/professional appearance:** **currently "capable internal tool," not "premium commercial."** Emoji, hairline density, mixed fonts, and inline styling are the biggest tells.

---

## PHASE 6 — DESIGN SYSTEM REVIEW

**What exists (`tokens.css`, 451 lines):** a genuinely thoughtful token set — light+dark themes, violet→pink brand gradient, semantic status/score/confidence colors, RGB triplets for alpha overlays, spacing/radius/motion/z-index scales, platform brand colors.

**Problems:**
1. **Three coexisting token generations** (`--color-*` legacy, `--surface-*/--accent-*` spec, `--bg-*/--text-1..3/--fh/--fb/--fo` prototype). All resolve to the same values now, but authors don't know which to use → drift.
2. **Primitive components are under-adopted.** Design system is ~40% realized; screens hand-roll instead.
3. **No documented usage** — no Storybook/inventory; tokens are discoverable only by reading CSS.
4. **Type ramp under-used**; motion tokens partially applied.
5. **WCAG:** tertiary text + 9–11px + color-only status fail AA in places. Dark mode is solid; light mode ("warm off-white") is coherent.

**Recommendation:** collapse to **one** token namespace (keep the semantic `--surface/--accent/--text-*` set), delete legacy aliases behind a codemod, and make the `components/ui` primitives mandatory (lint rule against raw inline `style` for color/spacing).

---

## PHASE 7 — CARD SYSTEM REVIEW

| Card | Purpose | Info priority | CTA | States today | Redesign |
|------|---------|--------------|-----|--------------|----------|
| **Clip result card** (`clip-card2`) | show a rendered clip + score | thumb › score ring › tier › AI reason › actions | Save + 👍/👎 + ··· | hover overlay (▶/⬇), selected, is-top(BEST) | Elevate: real 9:16 poster, single primary (Play), score ring as chip, move Save/download into overflow; consistent `<ClipCard>` |
| **Config source card** (`cfg-src-card`) | confirm chosen source | title › duration | Change | static | add real poster frame |
| **Dock row card** | live job glance | kind badge › title › progress › % | open/cancel/reorder | hover, queued, attention(failed) | unify with queue drawer row as one `<JobRow>` |
| **Download row** | download state | platform badge › title › progress | send-to-render/open/copy/cancel | active/queued/done/failed | share `<JobRow>` language |
| **AI Analysis card** | explain ranking | best clip › ranking list › story | expand/collapse | ok/degraded/no-result | keep; componentize `<RankingBreakdown>` |
| **Score ring** (`ScoreRingSm/Lg`) | 0–100 virality | number + arc | — | color by tier | extract `<ScoreRing size>` primitive |
| **KPI tiles** (results hero) | top score / clips / duration | number › label | — | color variants | extract `<Stat>` |
| **History list item** | past job | title › status › score › time | select/···/batch | selected, batch, loading | consistent with `<JobRow>` |
| **Settings section card** | grouped prefs | title › fields | save/clear | configured badge | keep; standardize header |

Cross-cutting: hover/loading/empty/error states are **inconsistently** implemented per card. Standardize a `<Surface>`/`<Card>` with slots + a shared state matrix.

---

## PHASE 8 — COMPONENT REVIEW

- **Duplicates to consolidate:**
  - Job row: `ActiveJobsDock.DockRow` + `QueueDrawer` row + `DownloadRow` + `JobListItem` → one `<JobRow variant>`.
  - Progress viz: `render/steps/RenderStage`/`StepRendering` vs `features/progress/*` (ProgressClipsGrid, ProgressStageTimeline, ProgressPartList) → pick one.
  - Quality: `StepResults` inline vs `features/quality/*` → pick one.
  - Score display: `ScoreRingSm/Lg` + `ScoreBadge` + inline bars → `<ScoreRing>` + `<ScoreBar>`.
  - Pills/badges: dozens of inline → `<Badge>`/`<StatusPill>` (both already exist, under-used).
- **Legacy/dormant:** `HistoryTab.tsx`, `features/progress` subset, `features/quality` subset, `DownloadScreen` thin wrapper.
- **Missing abstractions:** `<SegmentedControl>` (re-implemented ~10× as `seg`/`seg-b` divs), `<Toggle>` (`Tog`), `<Field>`/`<FormRow>` (exists only in Settings), `<Popover>` (Export & ScoreTip hand-roll absolute divs), `<Modal>` (Palette, ClipPlayer, ConfirmDialog each hand-roll a backdrop).
- **Missing variants:** Button has no formal size/tone matrix; screens invent `btn-xs/btn-next/btn-back/btn-cancel`.

---

## PHASE 9 — AI EXPERIENCE REVIEW

**Strengths (this app does AI-UX unusually well):**
- **Transparency:** per-clip AI reason, 6-signal ranking breakdown (viral/hook/retention/speech/market/duration), dominant vs suppressed signals, confidence tier, score margin vs #2, rejected-segment count, whole-film Story Model.
- **Trust:** real libass subtitle previews; `test-cloud-ai` latency probe; hybrid/cloud/local source badge with confidence %.
- **Feedback loop:** 👍/👎 feeds AI Director training; a one-time toast reveals it.
- **Latency perception:** stage-blended progress bar, "estimating…" ETA hint, live Event Log, AI Director activity panel.
- **Recover:** retry/resume/extend, WS→poll fallback, degraded-AI status messages (`no_ranking`/`degraded`/`no_result`).

**Gaps:**
- No **streaming** of AI reasoning (events arrive as discrete log lines, not token stream) — acceptable given backend, but the Event Log is power-user raw.
- AI "confidence"/"why" is buried in expand-panels; first-time users see a number without meaning until a manual tip.
- Cancel exists; there's no "pause AI / cheaper mode" concept surfaced.
- The Story Model (a genuinely premium artifact) is under-presented (a small card).

**Redesign:** make AI explainability a **first-class, always-visible narrative** ("Why this clip won") rather than a collapsed panel; present the Story Model as a hero timeline in Recap.

---

## PHASE 10 — PERFORMANCE REVIEW

- **Bundle:** vendor chunk split (react/react-dom/zustand); per-screen `React.lazy` + idle prefetch. Good. `openapi-generated.ts` (4091 LOC) is types-only (no runtime cost).
- **Rendering:** `React.memo` on heavy steps; WS fingerprinting avoids no-op renders. But inline style objects recreate each render across many components (GC pressure, not catastrophic).
- **Lists:** no virtualization (History cumulative, live event log capped at 50, clip grids bounded by output count). Fine at current scale.
- **Polling:** consolidated to one shared 4 s jobs poll (good) — but Download adds a 1.5 s poll and health/resources add more; several independent timers.
- **Media:** thumbnails via backend URLs with `loading="lazy"` in Download; clip grid images not explicitly lazy. Preview `<video autoplay loop>` in Configure runs continuously.
- **Animation:** CSS-based, cheap.
- **Memory:** bounded event buffers; WS teardown on unmount; polling cleared on unmount.
- **Opportunities:** move inline styles → CSS classes (biggest win + design consistency); lazy clip thumbnails; pause Configure preview video when tab hidden; unify pollers into a single scheduler.

---

## PHASE 11 — REDESIGN STRATEGY

**Design goals:** premium · elegant · modern · clean · creator-first · fast · trustworthy · scalable — **without a backend change.**

**Guiding principles (each ties to backend reality):**
1. **One job model, one job surface.** Backend already exposes uniform job state (history/queue/ws). Collapse dock+drawer+library+download rows into one `<JobRow>` + one Queue surface. *Why:* removes the app's biggest inconsistency; zero API change.
2. **Promote Monitor & Editor to first-class, deep-linkable views.** Introduce a lightweight route layer over `activePanel` keyed by `jobId`. *Why:* fixes the "where did my render go" problem; backend already keys everything on `job_id`.
3. **AI explainability as narrative, not footnote.** Reuse `ai-summary`/ranking data already fetched. *Why:* the premium differentiator is transparency.
4. **Progressive config.** Default to a 3-decision Quick flow (platform, length, count) with an Advanced drawer; everything else uses the existing server defaults (Sacred Contract #2 makes new fields default-off). *Why:* cuts decision fatigue with no payload change.
5. **One token system + mandatory primitives.** *Why:* the fastest path from "tool" to "product."
6. **Wire the dormant real features** (Editor trim/rerender). *Why:* endpoints already exist; closes a trust gap.

**Per-change lens:** each redesign item below is tagged with Business value / UX value / Eng impact / Backend impact (always **none/contract-safe**) / Risk / Priority.

---

## PHASE 12 — SCREEN-BY-SCREEN REDESIGN

Notation: **Current → Problems → Target layout (ASCII) → Component tree → Interaction → Responsive → A11y → Motion.**

### 12.1 App shell
```
┌──────────────────────────────────────────────────────────────┐
│  Topbar: ✦ AI Clip Studio        [job pill] 🔔 ☾ EN/VI ●conn  │
├────┬─────────────────────────────────────────────────────────┤
│ N  │                                                          │
│ a  │                  ACTIVE SCREEN                           │
│ v  │                                                          │
│ r  │                                                          │
│ a  │                                                          │
│ i  ├─────────────────────────────────────────────────────────┤
│ l  │  Queue dock (only when jobs active)  ▸ manage           │
└────┴─────────────────────────────────────────────────────────┘
```
- **Nav:** widen rail to 64px with icon **+ label on hover-expand** (or a persistent 200px on ≥1440px). Add **Create**, **Queue**, **Library**, **Downloads**, **Editor**, **Settings**. Retire Publish until real.
- **A11y:** rail items are real `<a>`/buttons with visible labels at ≥1440px; focus ring from `--border-focus`.
- **Motion:** rail expand 180ms ease-out; panel cross-fade 150ms.

### 12.2 Create (source + configure)
- **Problems:** god component; ~20 decisions; two visual shells.
- **Target:** split into `CreateScreen` orchestrator + `<SourcePicker>`, `<ConfigQuick>`, `<ConfigAdvanced drawer>`, `<PreviewStage>`, `<StyleStrip>`.
```
┌─ Create ─────────────────────────────────────────────────────┐
│  ① Source ────────────────  ② Preview ───────────  ③ Output   │
│  ┌─────────────┐            ┌───────────────┐      ┌────────┐ │
│  │ drop / pick │            │  9:16 live    │      │Platform│ │
│  │ [poster]    │            │  preview +    │      │Length  │ │
│  │ title · dur │            │  subtitle     │      │Count   │ │
│  └─────────────┘            └───────────────┘      │[Adv ▸] │ │
│  Style strip: [Soft][Pop][Clean][Bright]…          └────────┘ │
│                                        [ Start render → ]     │
└──────────────────────────────────────────────────────────────┘
```
- **Quick = 3 fields.** Advanced drawer holds AI provider/model/lang, subtitle detail, narration, trim, quality, focus, story-intel.
- **Interaction:** auto prepare-source on add; debounced draft persists; Recap toggle promotes to a distinct mode card (not a hidden confirm).
- **Responsive:** 3-col ≥1200px; stack to 1-col with sticky Start bar < 1000px.
- **A11y:** real `<fieldset>`/`<legend>`, `<SegmentedControl role=radiogroup>`, labels ≥12px.

### 12.3 Monitor (deep-linkable job view)
- **Problems:** only reachable via handshake; duplicate progress bars.
- **Target:** single hero progress + phase timeline + clip filmstrip + collapsible Event Log + AI Director strip.
```
┌─ Job ab12… · Rendering ─────────────────────  ⏱ 03:12 · ETA 04:0┐
│ ●───●───◐───○───○   Analyze Transcribe Render Report Done        │
│ ▓▓▓▓▓▓▓▓▓▓░░░░░░ 62%                                             │
│ Filmstrip: [✓][✓][◐ 40%][…][…]                                   │
│ AI Director: ⚡ Hybrid · Gemini — "ranking 5 candidate moments"   │
│ ⚠ status line (stuck/watchdog/ws) — one line, contextual         │
│ ▸ Event log (24)                                                 │
│                                   [Cancel]        [View results] │
└──────────────────────────────────────────────────────────────────┘
```
- **Interaction:** watchdog +1h inline; recap swaps filmstrip → episode timeline.
- **Motion:** phase dots fill with spring; bar width transitions 300ms.

### 12.4 Results
- Componentize into `<ResultsHero>`, `<AiAnalysis>`, `<ClipGrid>`→`<ClipCard>`, `<ClipDetail>` (merge player+detail into one right panel with tabs Preview/Ranking/Quality), `<ExportPanel>`.
- Unify score to a single `output_rank_score ?? qualityScore` at the data layer; one `<ScoreRing>`.
```
┌─ Results ────────────────────────────────────────────────────┐
│ ✓ 5 clips ready   Top 87 · 5 clips · 4:12   [Open folder]     │
│ ✦ Why "Clip 3" won: hook + retention (+6.2 vs #2)  [details]  │
│ Sort: Viral▾   Export▾                                        │
│ ┌ClipCard┐ ┌ClipCard┐ ┌ClipCard┐ …   │  Detail: Preview|Rank │
│ │ 87 ★   │ │ 74     │ │ 61     │      │  6-signal bars        │
│ └────────┘ └────────┘ └────────┘      │  Quality issues       │
└──────────────────────────────────────────────────────────────┘
```

### 12.5 Queue (new unified surface)
Merge dock (glance) + drawer (manage) + active portion of Library into one Queue screen with the shared `<JobRow>` and full reorder/hold/resume/cancel. Dock becomes a **summary launcher** into it.

### 12.6 Library
- Keep cumulative pages but add optional virtualization; use `<JobRow>`; clarify actions: **Duplicate** (new config), **Retry failed parts**, **Resume interrupted**, **Delete**. Detail drawer becomes a right panel with the same `<ClipGrid>` as Results.

### 12.7 Downloads
- Reuse `<JobRow>`; move cookie management into a quieter, progressive panel; keep staging table but style with the shared data-row.

### 12.8 Editor
- Give it a nav home; **wire `POST …/trim` + `…/rerender`** (endpoints exist); show "Trim → new job" vs "Re-render with new style". Preview + trim + right-rail metadata already built.

### 12.9 Settings
- 9 sections already well-structured (Creator Context, Render Defaults, Output Dir, Data Retention, Performance, Storage, Database, Stats, Help) + `SettingsNav`. Redesign is cosmetic: adopt primitives, add section anchors already present (`settings-defaults` etc.), tighten copy.

---

## PHASE 13 — DESIGN LANGUAGE

**Target feel:** Linear's density + restraint, Raycast's command ergonomics, Arc's warmth, OpenAI/Perplexity's calm AI-transparency.

**Move toward:**
- One violet→pink brand accent used *sparingly* (primary action, active nav, AI identity).
- Real iconography (single line-icon set), **retire emoji-as-icon**.
- Fewer, larger type steps; raise the floor to 12px; use `Space Grotesk` for numerals/scores, `Inter` for body — **drop** `Rajdhani`/`Orbitron` prototype fonts.
- Generous surfaces, one elevation system, soft shadows (already in tokens).
- Motion as feedback (spring on completion, subtle score count-up) — not decoration.

**Move away from:** hairline-dense grids, 9–11px text walls, three token systems, inline-styled bespoke buttons, emoji semantics, "dashboard" density.

---

## PHASE 14 — REDESIGN ROADMAP

Effort: S ≤2d · M ≤1wk · L ≤2wk · XL >2wk (single senior FE). **Backend impact = none for every item** (contract-safe).

### Phase 0 — Quick wins (visual + trust), ~1 sprint
| Item | Files | Risk | Effort |
|------|-------|------|--------|
| Collapse to one token namespace; codemod legacy `--color-*`/prototype aliases | `styles/*`, global sweep | L (visual regressions) | M |
| Replace emoji icons with the line-icon set | Sidebar, Topbar, StepResults, Download | Low | S |
| Raise min type size to 12px; fix tertiary-text contrast | `tokens.css`, screens | Low | S |
| Wire Editor `trim`/`rerender` (close trust gap) | `editor/*`, `api/editing.ts` | Med | M |
| Retire dead nav (Publish) + dormant `HistoryTab` | `App.tsx`, uiStore | Low | S |
**UX outcome:** immediately reads as a product, not a tool; no more no-op feature.

### Phase 1 — Visual consistency, ~1–2 sprints
| Item | Files | Risk | Effort |
|------|-------|------|--------|
| Make `components/ui` primitives mandatory; lint against raw color/spacing inline styles | all screens | Med | L |
| Extract `<Badge>`, `<StatusPill>`, `<ScoreRing>`, `<ScoreBar>`, `<SegmentedControl>`, `<Toggle>`, `<Popover>`, `<Modal>` | components/ui | Low | M |
| Unify job rows into `<JobRow variant>` | dock, drawer, library, download | Med | M |
| ⭐ **Rendering monitor + clip-card redesign** (see Appendix E) — rich clip tiles, conic-ring active state, remove duplicate progress | `StepRendering`, `RenderStage`, `RecapLiveView`, `RenderWorkflow.css` | Low | M |
**UX outcome:** one consistent visual language; the live monitor becomes a showcase surface that flows into Results.

### Phase 2 — UX refactor, ~2–3 sprints
| Item | Files | Risk | Effort |
|------|-------|------|--------|
| Progressive Configure (Quick 3-field + Advanced drawer) | `render/steps/StepConfigure` | Med | L |
| Unified **Queue** screen; dock → launcher | new `Queue/`, dock, drawer | Med | L |
| Deep-linkable **Monitor** + **Editor** (route layer over activePanel keyed by jobId) | `App.tsx`, uiStore, RenderWorkflow | High (state) | L |
| AI explainability as first-class "Why this won" narrative | StepResults, ai-summary | Low | M |
| Onboarding: first-run tour + score/feedback explainers inline | new | Low | M |
**UX outcome:** fixes decision fatigue, "where did my job go", and AI legibility.

### Phase 3 — Architecture cleanup, ~2–3 sprints
| Item | Files | Risk | Effort |
|------|-------|------|--------|
| Decompose `RenderWorkflow` god component (extract state to a `useRenderWorkflow` hook + subscreens) | render/* | High | XL |
| Lift live progress into a store (or React Query-style cache) so Monitor is not owned by one component | new store, useRenderSocket | High | L |
| Delete duplicate `features/progress` / `features/quality` after confirming single owner | those dirs | Med | M |
| Single poll scheduler (jobs 4s + downloads 1.5s + health + resources) | stores/hooks | Med | M |
**UX outcome:** invisible to users; unlocks velocity and reliability.

### Phase 4 — Premium product experience, ~2–3 sprints
| Item | Files | Risk | Effort |
|------|-------|------|--------|
| Motion system: spring completion, score count-up, phase-dot fills, reduced-motion | motion.css, primitives | Low | M |
| Story Model as hero timeline (Recap) | RecapLiveView, StoryModelCard | Low | M |
| Real Publish surface (only if backend later adds it — **out of current scope**) | — | — | — |
| Full WCAG AA pass + keyboard-complete flows | all | Med | L |
**UX outcome:** the "commercial premium" finish.

---

## APPENDICES

### A. Screen inventory (28 mounted surfaces)
Shell(3): AppShell/Sidebar/Topbar. Global(6): ActiveJobsDock, QueueDrawer, CommandPalette, NotificationCenter, Notifications(toasts), ConfirmDialogHost. Studio(2 tabs): RenderWorkflow(Create/Monitor/Results), DownloadTab. Library(1)+JobDetailDrawer. Editor(1)+states. Settings(9 sections). Publish(placeholder).

### B. Interaction inventory
Drag-drop source, file/dir pickers (Electron IPC), ⌘K palette, ⌘N new render, ⌘, settings, shift-range batch select, ESC dismiss, hover overlays, in-app video player w/ nav, per-clip 👍👎, export checklist, queue reorder (top/up/down/bottom/hold/resume), watchdog extend, WS reconnect/poll, clipboard auto-paste (download), cookie import.

### C. Technical debt inventory (ranked)
1. `RenderWorkflow` god component (1003 LOC). 2. Three token generations. 3. Inline styles bypassing the design system. 4. Duplicate progress/quality subsystems. 5. Editor trim is UI-only vs live endpoints. 6. Prototype fonts (`Rajdhani`/`Orbitron`) still in use. 7. No routing/deep-link. 8. Multiple independent pollers. 9. Cross-screen coordination via ad-hoc uiStore signals + `queueMicrotask` guards. 10. Emoji-as-icon.

### E. Rendering Monitor & Clip-Card Redesign  ⭐ (elevated priority per stakeholder, 2026-07-03)

> Stakeholder note: the per-clip rendering cards and the live monitor currently look **flat and unfinished**. This is now a **Phase 1 priority** (moved up from Phase 2). Scope: `render/steps/StepRendering.tsx`, `render/steps/RenderStage.tsx`, `render/steps/RecapLiveView.tsx`, and the `.rd-*`/`.rs-*` blocks of `RenderWorkflow.css`. **No backend change** — every state below is derived from data the pipeline already streams (`ClipSlot = {part_no, status, progress_percent, duration?, message?}`, per-part status enum, `getPartThumbnailUrl` on done, `getPartMediaUrl` for play).

#### E.1 Diagnosis (why it reads as "đơn điệu / plain")
1. **Filmstrip chips** (`.rs-chip`) are tiny grey text pills with glyph icons (`○ ✓ ✕ ▶`) — no shape, no imagery, no life.
2. **Focus card preview** is an empty gradient box with a giant `#03` because an in-progress clip has no thumbnail yet — it reads as a colored blank.
3. **Four stacked progress representations** (`.rd-seg-bar` + `.rd-overall-pct` + focus `.rs-bar` + `.rd-abp-toolbar`) — redundant, no anchor.
4. **Prototype HUD fonts** (`--fh` Rajdhani, `--fo` Orbitron) + emoji-as-icons → "gamer overlay", not premium.
5. **Bottom toolbar** duplicates the top progress entirely.

#### E.2 New concept — "Live Studio" board
One clear hierarchy: **Hero progress (1) → Now-Rendering focus card (1) → Clip grid (rich mini-cards)**. Delete the duplicate bottom toolbar. The clip grid uses the **same card geometry as the Results grid**, so Monitor → Results feels like one continuous surface (the clip you watched build is the clip you review).

```
┌─ Rendering · 3 of 5 clips ──────────────────── ⏱ 03:12 · ETA 04:05 ┐
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░  62%      ← ONE hero bar (Space Grotesk #) │
│  ● Analyze ─ ● Transcribe ─ ◐ Render ─ ○ Report ─ ○ Done            │
└─────────────────────────────────────────────────────────────────────┘
┌─ NOW RENDERING ─────────────────────────────────────────────────────┐
│  ┌──────────┐  Clip #03 · 0:48                          ~1:20 left   │
│  │ conic    │  ● RENDERING                                           │
│  │  ring    │  Cut ✓ ──── Sub ✓ ──── Render ◐                        │
│  │  72%     │  Burning subtitles · FFmpeg NVENC                      │
│  └──────────┘                                                        │
└─────────────────────────────────────────────────────────────────────┘
Clips ───────────────────────────────────────────────────────────────
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐
│[thumb]│ │[thumb]│ │▓▓▓ 72│ │▒shim │ │▒shim │   ← rich mini-cards,
│✓ 0:42 │ │✓ 0:55 │ │◐ rend│ │queued│ │queued│     aspect = output ratio
└──────┘ └──────┘ └──────┘ └──────┘ └──────┘
```

#### E.3 Clip mini-card — the core redesign (replaces `.rs-chip`)
A real card sized to the output aspect ratio (`thumbRatio`), not a text pill. Four states, all "alive":

- **Done** — real thumbnail (`getPartThumbnailUrl`), gradient scrim bottom, ✓ chip top-left, duration badge bottom-right, hover reveals ▶ play (→ `getPartMediaUrl`). Entrance: `rs-pop` spring scale-in when it flips to done. *This is the beautiful default — most cards become real imagery.*
- **Active** — **conic-gradient progress ring** OR **vertical "liquid" fill** rising with `progress_percent`, big % in `--font-display`, a 3-dot micro-pipeline (Cut·Sub·Render), pulsing accent (`--ai-active`) border, subtle animated mesh background. Rich even with zero thumbnail.
- **Waiting** — ghost card: faint skeleton shimmer (reuse `rs-shimmer`), muted `#0N`, "queued" label; opacity ~.55. Reads as "coming up", not broken.
- **Failed** — red-tinted surface, ✕ mark, first line of `message` on hover; retry affordance deferred to Results.

Card anatomy (active state):
```
┌───────────────┐
│   ╭─────╮      │  conic ring (accent→pink), % in center
│   │ 72% │      │  Space Grotesk, tabular-nums
│   ╰─────╯      │
│ ● ● ○  Render  │  micro-pipeline + current step
│ #03            │  clip number, mono-ish but Inter
└───────────────┘   1px accent border, soft glow while live
```
Every card is **clickable to focus** it in the Now-Rendering card (keep current `setFocusOverride`), with `role=option`/`aria-selected` preserved. The grid replaces both `.rs-strip` (filmstrip) and the redundant `.rd-seg-bar` segmented bar.

#### E.4 Now-Rendering focus card (evolve `.rs-focus`)
Keep the one genuinely good touch — the animated gradient border (`.rs-focus-live`) — but:
- Replace the empty `#03` placeholder with the **same conic ring** treatment (large), so the hero always shows meaningful progress, not a blank.
- When the focused clip is **done**, swap the ring for the real thumbnail + inline ▶ (continuity into Results).
- Pipeline `Cut → Sub → Render` becomes real line-icon nodes (scissors / captions / film), not bordered circles with a ✓ char.
- Activity line maps status → human copy already exists (`activityLabel`) — keep, but add the encoder hint ("FFmpeg NVENC") as a quiet mono tag.

#### E.5 Progress hierarchy cleanup (declutter)
- **Keep:** one hero bar + % (top card) and the phase rail. Numerals move to `--font-display` (drop `--fo` Orbitron).
- **Remove:** `.rd-abp-toolbar` (bottom) entirely — it duplicates the hero.
- **Fold:** the segmented `.rd-seg-bar` into the clip grid (the grid *is* the per-clip status now).
- **Result:** from 4 progress elements → 2 (hero + grid), plus the focus card's own ring.

#### E.6 Motion & polish
- Card done-flip: spring scale-in + brief accent flash (reuse `--ease-spring`).
- Active ring: smooth `stroke-dashoffset`/`background-position` transition on `progress_percent` (300–400ms) so it glides, never jumps.
- Waiting shimmer + active mesh at low amplitude; **honor `prefers-reduced-motion`** (freeze animations, keep static fills).
- Hero bar width transitions 300ms; phase dots fill with the spring.
- Replace emoji glyphs (`▶ ○ ✓ ✕`) with the line-icon set (Phase 0 icon work applies here first).

#### E.7 Files & effort
| Change | File | Note |
|--------|------|------|
| Clip mini-card grid (4 states) + conic ring | new `render/steps/ClipTile.tsx` (extract) | replaces `.rs-chip` map |
| Focus card ring + real-thumb-on-done | `RenderStage.tsx` | keep focus logic/ETA as-is |
| Remove bottom toolbar, unify progress | `StepRendering.tsx` | delete `.rd-abp-toolbar` JSX |
| CSS: `.rs-*` grid/tile/ring, retire `.rd-seg-bar`/`.rd-abp-*` | `RenderWorkflow.css` | scope stays local |
| Recap parity (same tile language) | `RecapLiveView.tsx` | so both modes read identically |

**Effort:** M (~1 week). **Risk:** Low (frontend LOW-tier, no contract touch). **Data:** 100% existing. **UX outcome:** the monitor becomes the visual centerpiece and flows seamlessly into Results.

---

### D. Hard constraints for the rebuild team (must not break)
- WS frame shape `{job,parts,summary}`; job-stage & part-stage enum strings; `result_json` keys `output_rank_score`/`is_best_output`/`is_best_clip`; the 3 frozen routes (`POST /render/process`, `GET /jobs/{id}`, `WS /jobs/{id}/ws`); new render fields default-off; HTTP polling must remain a full WS alternative. (See CLAUDE.md Sacred Contracts.)
