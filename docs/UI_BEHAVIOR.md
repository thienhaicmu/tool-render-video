# UI Behavior

## UI Product Role

**Stability marker: Semi-stable implementation**

The UI is a static frontend for an AI rendering intelligence platform. It should help users prepare sources, refine render settings, monitor jobs, inspect outputs, and understand why AI-selected clips are useful.

The current UI behaves like a hybrid:

- creator productivity dashboard
- lightweight editor
- render monitor
- output gallery
- AI insight surface

It is not a full CapCut-style timeline editor. Manual controls are refinement tools around AI-assisted clip generation.

## Navigation Structure

**Stability marker: Stable contract**

Primary views are managed by `backend/static/js/nav.js`.

Known views:

- Render
- Download
- History
- Settings
- Editor

The Render setup card, Download setup card, editor workspace, output panel, bottom monitor, and inspector are toggled by view state and CSS classes. Do not move or rename these panels without updating all callers.

## State Ownership

**Stability marker: Semi-stable implementation**

Shared frontend state is global and fragile.

Important globals live in `backend/static/js/globals.js`, including:

- `currentJobId`
- `pollTimer`
- `pollIntervalMs`
- `activeJobStartedAt`
- `jobWs`
- `currentView`
- selected source/output paths

Editor state lives mostly in `_ev` in `backend/static/js/editor-view.js`.

Render output and monitor state is derived from backend job/part responses but also cached in DOM state, localStorage history, and current preview selection.

### What must not break: UI state

- Do not introduce competing sources of truth for `currentJobId`.
- Do not stop polling unless WebSocket replacement is fully verified.
- Do not clear output gallery/history state during normal view switches.
- Do not break `_ev.sessionId` and editor pending payload flow.

## Render View

**Stability marker: Stable contract**

The Render view starts from source setup and output selection. For YouTube input, the frontend prepares the source first through `/api/render/prepare-source`, then opens the editor with a session. Local input also goes through preview/session setup.

Render submission eventually posts to:

- `/api/render/process`
- `/api/render/process/batch` for batch YouTube render jobs

Important setup IDs include:

- `source_mode`
- `youtube_url`
- `source_video_path`
- `local_video_file_picker`
- `manual_output_dir`
- `render_output_dir`
- `start_render_btn`
- `resume_job_id`

These IDs are compatibility contracts.

## Download View

**Stability marker: Stable contract**

The Download view is separate from render source preparation. It submits standalone download jobs through `/api/download/process` and tracks per-item status.

Do not conflate Download tab jobs with render preview sessions. They share downloader infrastructure, but they serve different workflows.

## History View

**Stability marker: Semi-stable implementation**

History combines backend job history and local UI state. It displays completed, partial, failed, interrupted, and recent render states. Some render cards can reopen output panels or rerun jobs.

History state depends on `jobs.result_json`, `job_parts`, output paths, and status normalization.

## Editor View

**Stability marker: Semi-stable implementation**

The editor is driven by `_ev` in `editor-view.js`.

It manages:

- preview session ID
- preview video
- trim range
- volume
- subtitle preview/edit state
- voice settings
- text layers
- render payload assembly
- output folder

Important editor IDs include:

- `view_editor`
- `evVideo`
- `evSubOverlay`
- `evTextLayersOverlay`
- `evStartBtn`
- `evVoiceEnable`
- `evVoiceSource`
- `evSubTranslate`

Do not rename editor DOM IDs without updating `editor-view.js`.

## Center Preview Behavior

**Stability marker: Semi-stable implementation**

The center preview area is used for editor preview and rendered output preview.

Rendered clip preview uses job/part media endpoints, not raw filesystem paths. The output gallery can load a selected clip into the center preview and may attempt muted autoplay after media readiness events.

Important IDs include:

- `cs_preview_area`
- `cs_preview_video`
- `cs_preview_download`

## Output Gallery Behavior

**Stability marker: Stable contract**

Output gallery logic lives mostly in `backend/static/js/render-ui.js`.

It reads job result JSON and part rows to display:

- rendered clips
- part numbers
- scores
- best clip metadata
- download/preview links
- partial failures
- AI insights when available

Important IDs:

- `render_output_panel`
- `render_output_panel_title`
- `render_output_badge`
- `render_output_path`
- `render_output_list`

### What must not break: output gallery

- Preserve media stream URLs for job parts.
- Preserve ranking field aliases from `result_json`.
- Preserve display of partial success and failed parts.
- Preserve download links.
- Preserve output panel visibility behavior across view changes.

## Job Progress Monitor

**Stability marker: Stable contract**

The frontend uses both polling and WebSocket:

- Polling starts immediately after job submission.
- WebSocket connects to `/api/jobs/{job_id}/ws` when possible.
- If WebSocket fails, polling continues.

Backend state remains the source of truth. UI smoothing is display-only.

Important monitor IDs include:

- `render_active_panel`
- `render_active_state`
- `render_completion_bar`
- `render_monitor_header`
- `render_monitor_progress`
- `rc_status`
- `rc_stage`
- `rc_active_badge`

## Logs and Diagnostics

**Stability marker: Stable contract**

Render logs appear in `event_log_render`. They combine frontend events, backend job logs, and structured progress messages.

Important ID:

- `event_log_render`

Do not remove logs. They are part of the support and recovery workflow, especially for FFmpeg, download, subtitle, TTS, and partial-failure diagnosis.

## AI Visibility in the UI

**Stability marker: Experimental / needs verification**

The backend contains more AI intelligence than the UI currently exposes.

Hidden AI value includes:

- ranking reasons
- hook strength
- retention fit
- market fit
- subtitle strategy
- camera strategy
- creator intelligence
- quality evaluation
- explainability

The UI should increasingly help users understand why a clip is best, why a subtitle/camera/market strategy was chosen, and what quality warnings mean. This is product direction, not a mandate to redesign the UI in this doc.

## DOM ID Compatibility Contract

**Stability marker: Stable contract**

DOM IDs are effectively API contracts for this static frontend.

High-risk ID groups:

- Render setup: `source_mode`, `youtube_url`, `manual_output_dir`, `start_render_btn`.
- Editor: `evVideo`, `evStartBtn`, `evVoice*`, `evSub*`, text layer controls.
- Monitor: `render_active_panel`, `render_monitor_*`, `rc_*`.
- Output: `render_output_panel`, `render_output_list`, `cs_preview_video`.
- Logs: `event_log_render`.

Before changing IDs, search all `backend/static/js/*.js`, `backend/static/index.html`, and `backend/static/css/app.css`.

UI contract tests: Needs verification. Avoid DOM/state refactors until critical render setup, editor session, monitor, output gallery, and log contracts are verified by focused tests or manual checks.

## UI Fragility and Ownership Boundaries

**Stability marker: Semi-stable implementation**

The UI is fragile because:

- state is global
- `render-ui.js` and `editor-view.js` are large
- `app.css` is very large and includes many late-phase overrides
- behavior is split between DOM state, CSS state selectors, localStorage, polling responses, WebSocket responses, and backend result JSON
- many features share the same page instead of isolated components

This explains why small UI edits can cause unrelated regressions.

### What must not break: UI ownership

- `render-engine.js` owns submission/polling/WebSocket setup.
- `render-ui.js` owns monitor/output/log rendering.
- `editor-view.js` owns editor session and final payload assembly.
- `nav.js` owns top-level view switching.
- `index.html` owns stable IDs and layout anchors.
- `app.css` owns visual state and layout.

## What Should Not Be Documented

**Stability marker: Stable contract**

- Do not document every CSS selector.
- Do not promise a redesign.
- Do not describe unimplemented UI AI features as current behavior.
- Do not treat visual polish experiments as stable contracts.
