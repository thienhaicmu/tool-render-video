# FRONTEND_REVIEW.md — Frontend Architecture Review

## Overview

The frontend is a hand-rolled vanilla JS SPA served by FastAPI.
No bundler, no framework, no TypeScript. Two versions co-exist:
- `backend/static/` — **V1 (default, active)**. Multiple top-level JS files, no ES modules, direct DOM manipulation.
- `backend/static-v2/` — V2 (opt-in via `STATIC_UI_VERSION=v2`). ES modules, component/store separation, hash router.
- `backend/static-v3/`, `backend/static-v4/` — orphaned fragments, not wired to any route.

**Active version**: V1 (`backend/static/`) is the default. `resolve_static_directory()` in `app/core/ui_gate.py` defaults to `backend/static/` when `STATIC_UI_VERSION` is unset or set to `"legacy"`. V2 requires explicit opt-in.

---

## V1 Folder Structure (Active Default)

```
static/
├── index.html          ← single HTML shell, all views inline with hiddenView toggling
├── css/v3/app.css      ← full stylesheet
└── js/
    ├── globals.js      ← all global state variables (currentJobId, pollTimer, jobWs, etc.)
    ├── init.js         ← DOMContentLoaded bootstrap, binds nav, sets initial view
    ├── nav.js          ← setView(view): toggles hiddenView CSS classes across panels
    ├── render-ui.js    ← render monitor, job polling, progress animation, clip compare
    ├── render-engine.js ← render form build, submit, source prep, batch queue
    ├── render-config.js ← preset configs, channel sync, form helpers
    ├── editor-view.js  ← editor panel mount
    ├── editor-state.js ← editor document model (clips, tracks, timeline data)
    ├── editor-timeline.js   ← timeline rendering
    ├── editor-playback.js   ← video playback sync
    ├── editor-waveform.js   ← audio waveform display
    ├── editor-thumbnail-cache.js ← frame thumbnail cache
    ├── editor-interactions.js    ← drag, resize, trim interactions
    ├── editor-virtualization.js  ← virtual scroll for large timelines
    ├── editor-coordinates.js     ← timeline ↔ pixel coordinate transforms
    ├── editor-text-runtime.js    ← subtitle/text overlay runtime
    ├── editor-audio-runtime.js   ← audio track runtime
    ├── editor-playback-runtime.js ← playback state machine
    ├── editor-performance-runtime.js ← frame budget / performance metrics
    ├── editor-ai-actions.js      ← AI action panel
    ├── editor-ai-sessions.js     ← AI session management
    ├── editor-agents.js          ← AI agent runner
    ├── editor-consensus.js       ← AI consensus/voting system
    ├── editor-converse.js        ← AI conversation UI
    ├── editor-scene-intelligence.js  ← scene analysis UI
    ├── editor-review-intelligence.js ← review/QA UI
    ├── editor-runtime-intelligence.js ← runtime hints
    ├── editing-autopilot.js     ← autopilot render flow
    ├── creator-memory.js        ← creator memory read/write UI
    ├── creator-dna.js           ← creator DNA profile UI
    ├── creator-presets.js       ← creator preset management
    ├── creator-assets.js        ← creator asset (intro/outro/logo) management
    ├── creator-consistency.js   ← consistency checks
    ├── creator-feedback.js      ← feedback submission
    ├── creator-series.js        ← series/campaign management
    ├── creator-taste.js         ← taste profile UI
    ├── clip-steering.js         ← clip preference steering
    ├── duration-preference.js   ← duration preference UI
    ├── score-preference.js      ← scoring preference UI
    ├── smart-defaults.js        ← smart default suggestions
    ├── batch-queue.js           ← batch URL queue management
    ├── review-queue.js          ← review queue (clips pending review)
    ├── workspace.js             ← workspace/home view
    ├── upload-engine.js         ← TikTok/YouTube upload automation
    ├── upload-manager.js        ← upload account + queue management UI
    ├── upload-config.js         ← upload account config forms
    ├── channels.js              ← channel management UI
    ├── history-ui.js            ← job history view
    ├── download-ui.js           ← source download view
    ├── smooth-progress.js       ← RAF-based animated progress bars
    ├── log-utils.js             ← log deduplication helpers
    ├── partials-loader.js       ← HTML partial injection (index.html sections)
    ├── warmup.js                ← model warmup status chip
    └── utils.js                 ← qs(), shared helpers
```

---

## V1 Architecture

### State Management

All application state lives in global variables declared in `globals.js`. There are no stores, no reactive primitives — state changes trigger UI re-renders by calling functions that directly manipulate the DOM.

Key globals:
- `currentJobId`, `pollTimer`, `pollIntervalMs` — render job tracking
- `jobWs`, `uploadWs` — active WebSocket connections
- `currentView` — current nav state
- `_partTarget`, `_partDisplay`, `_jobTargetPct`, `_jobDisplayPct` — smooth progress animation state
- `batchYoutubeUrls`, `selectedUploadVideos` — batch/upload selection state
- `_localEditorVideoSrc`, `_localEditorDuration`, `_localEditorSessionId` — editor state
- `renderChannelsRootPath`, `uploadChannelsRootPath` — path state

State for individual subsystems is declared as module-level `let` in each file. `render-ui.js` alone has 20+ top-level mutable variables (`_renderFlowStepRank`, `_renderMonitorLastJob`, `_rcLastActivePartNo`, `_r821CompareRefPartNo`, etc.).

### Navigation

`nav.js` → `setView(view)`: toggles `hiddenView` CSS class on each view's root element. All views exist in the DOM simultaneously; visibility is controlled by class. No routing, no URL change, no back button support.

Views: `workspace`, `render`, `editor`, `review`, `download`, `history`, `reports`, `settings`.

### Progress / WebSocket

`globals.js` declares `jobWs` for the WebSocket connection. `render-ui.js` manages the connection lifecycle, polling fallback (`pollTimer`), and smooth progress animation via `requestAnimationFrame` (`_smoothRafId`). This mirrors the same WebSocket + polling hybrid pattern as V2's `transport.js` but implemented inline in the render UI file rather than in a dedicated transport module.

`smooth-progress.js` handles the RAF-based progress bar animation with the `_partTarget` / `_partDisplay` target/display split.

### The Editor

The editor is a substantial subsystem spanning ~15 files:

- `editor-state.js` — document model (clips, tracks, timeline data)
- `editor-timeline.js` — timeline rendering
- `editor-playback.js` / `editor-playback-runtime.js` — video playback sync
- `editor-waveform.js` — audio waveform display
- `editor-thumbnail-cache.js` — frame thumbnail cache
- `editor-interactions.js` — drag, resize, trim
- `editor-virtualization.js` — virtual scroll for large timelines
- `editor-text-runtime.js` / `editor-audio-runtime.js` — subtitle and audio track runtime
- `editor-ai-actions.js` / `editor-ai-sessions.js` / `editor-agents.js` / `editor-consensus.js` / `editor-converse.js` — AI-assisted editing UI

The editor is accessible via `setView('editor')` from the render flow.

---

## Strengths

1. **Complete feature set**: The active frontend covers the full user workflow — source prep, render config, job monitoring, editor, creator tools, upload, channels, batch queue, review queue. Nothing is a stub.

2. **WebSocket + polling hybrid**: The render-ui.js WebSocket + pollTimer pattern correctly handles terminal status detection and falls back to polling. `smooth-progress.js` RAF animation is correctly separated from the data update path.

3. **Smooth progress animation**: The `_partTarget` / `_partDisplay` split with RAF interpolation produces visually smooth progress bars even when backend updates arrive at coarse intervals. This is a good UX detail.

4. **No framework dependency**: Zero npm dependencies for the runtime UI. The app works without a build step, which is practical for a desktop tool with bundled assets.

5. **Creator tools are real**: `creator-memory.js`, `creator-dna.js`, `creator-presets.js`, `creator-assets.js`, `creator-taste.js`, `creator-series.js` are implemented features, not stubs. The creator workflow has real UI backing.

6. **Log deduplication**: `log-utils.js` `LOG_DEDUPE_WINDOW_MS=12000` deduplication with count accumulation avoids spamming the log panel with repeated messages. Correctly implemented.

---

## Weaknesses

### All State Is Global

Every piece of application state is a global variable. `globals.js` + the top-level `let` declarations scattered across 54 files make up the entire state layer. There is no isolation: a bug in `upload-engine.js` can corrupt `currentJobId` in `globals.js`. A navigation event does not reset state — it only toggles CSS visibility. Old state from a previous render session persists across navigation to the workspace view and back.

`render-ui.js` has 20+ top-level `let` declarations tracking render monitor state. These are reset by `resetRenderSessionUi()`, but that function must be called explicitly and is not guaranteed to run in all navigation paths.

### No Module System

All 54 JS files are loaded as classic `<script>` tags with no `type="module"`. Every function and variable declared at the top level of any file becomes a global. Name collisions are a constant risk. There is no import/export — file load order in `index.html` determines dependency resolution.

This means: a typo in one file that shadows a global in another file produces a silent bug, not a module resolution error.

### index.html Holds All Views

All views — workspace, render, editor, review, download, history, settings — are present in the DOM simultaneously, toggled by `hiddenView`. For a complex editor with waveform rendering, thumbnail cache, and timeline virtualization, this means the editor DOM is always present even when the user is on the workspace view. There is no lazy initialization — `partials-loader.js` injects HTML at startup.

### The Editor's AI Surface Is Largely Disconnected

`editor-ai-actions.js`, `editor-agents.js`, `editor-consensus.js`, `editor-converse.js` provide AI chat, consensus voting, and agent-driven editing UI. These connect to a backend AI layer that, as documented in AI_PIPELINE_REVIEW.md, is heuristic-only with no LLM API calls. The UI presents AI capabilities that the backend does not actually implement.

### No Error Boundary

There is no global error boundary. An unhandled exception in any event handler silently fails with a console error. Users see the UI freeze or an action that does nothing. There is no "something went wrong" UI state.

### Progress UX Gaps

- No estimated time remaining shown anywhere.
- Scene detection and Whisper transcription stages show the stage name but no sub-progress — the progress bar appears frozen for 1–5 minutes during scene detection and up to 20 minutes during Whisper transcription on long videos.
- Stuck render detection exists in the backend (`stuck_parts` in job summary) but is not displayed prominently in the UI — users see a frozen progress bar with no explanation.

---

## V2 Notes (Opt-In Only)

`backend/static-v2/` is accessible only when `STATIC_UI_VERSION=v2` is set. It implements:
- ES module graph with `import`/`export`
- Hash-based SPA router (`router.js`)
- Reactive stores (`create-store.js`)
- WebSocket + polling in a dedicated `transport.js`
- Entity parsers in `entities/`
- Thin API wrappers in `api/`

V2 is a cleaner architecture but covers fewer features than V1 — it does not have the full editor subsystem. It is an in-progress replacement, not yet the primary UI.

`backend/static-v3/` and `backend/static-v4/` are partial UI iterations that serve no active route.

---

## State / API Issues

| Issue | Location | Risk |
|-------|----------|------|
| All state is global — no isolation between subsystems | `globals.js` + all 54 JS files | State corruption across navigation and sessions |
| No module system — name collision risk | All `<script>` tags in `index.html` | Silent bugs when globals shadow each other |
| `resetRenderSessionUi()` not called on all navigation paths | `render-ui.js` | Stale render state bleeds into new sessions |
| `_PREVIEW_SESSIONS` lost on server restart | `routes/render.py:74` | User sees 404 for preview video |
| Editor AI UI presents capabilities the backend does not have | `editor-ai-actions.js`, `editor-converse.js` | User expectation vs. actual behavior gap |

---

## UX Risks

1. **Prepare-source blocking**: POST `/api/render/prepare-source` is synchronous (up to 10min for large YouTube videos). The UI shows a spinner with no progress. User cannot easily cancel a stalled download.

2. **Output directory must be typed manually** on non-Electron web: no folder picker → high friction for first-time users.

3. **No validation of output directory** before render starts — user finds out the path is wrong only when the job fails mid-render.

4. **Results screen**: clips listed in part order, not ranked by score — best clip may be buried.

5. **Batch render**: multi-URL batch has no per-URL progress visibility in the UI. Users see the overall job queue, not per-URL render stage.
