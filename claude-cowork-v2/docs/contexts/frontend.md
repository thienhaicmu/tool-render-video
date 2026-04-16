# Frontend Context

## Stack

- **Runtime**: Electron (desktop shell) + browser (single-page web app)
- **UI**: Single `backend/static/index.html` — vanilla JS, no framework
- **Styling**: Inline CSS in `<style>` tags within index.html
- **API Communication**: `fetch()` for REST, `WebSocket` for job progress

## Views

The UI is a single HTML file with multiple `<div class="view">` sections:

| View ID | Purpose |
|---------|---------|
| `settings` | Configure render parameters, select source |
| `editor` | Preview video, adjust segments and timing |
| `render` | Monitor job progress, pipeline steps |
| `jobs` | List past job runs |
| `upload` | Configure and start TikTok upload |

View transitions: `setView(viewName)` hides all views, shows the target.

## Job Progress Flow

1. User submits render → `_submitRenderPayload()` → POST `/api/render/start`
2. Response includes `job_id` → stored in `currentJobId`
3. `startPolling()` opens WebSocket to `/api/jobs/<job_id>/ws`
4. WS messages: `{ job: JobRecord, parts: JobPart[] }`
5. `_applyJobUpdate(job, parts)` updates all UI elements
6. On WS error: fall back to `setInterval(loadJobProgress, 2500)`
7. On job `completed` or `failed`: stop polling, update UI

## Pipeline Node Rendering

`renderPipeline(stage, status)` maps backend stage names to UI pipeline nodes.

Stage-to-node mapping:
- `queued` / `starting` → node 0 (Queue)
- `downloading` → node 1 (Download)
- `scene_detection` / `segment_building` → node 2 (Segment)
- `transcribing_full` → node 3 (Transcribe)
- `rendering` / `rendering_parallel` → node 4 (Render)
- `writing_report` / `done` → node 5 (Export)

## Key JavaScript Functions

| Function | Purpose |
|----------|---------|
| `startRender()` | Entry point for render submission |
| `openEditorView(mode, path, payload)` | Open editor for local video |
| `openEditorView_withSession(data, url, payload)` | Open editor for downloaded YouTube video |
| `startPolling()` | Begin WebSocket + HTTP fallback polling |
| `_applyJobUpdate(job, parts)` | Apply a job update to all UI state |
| `renderPipeline(stage, status)` | Update pipeline node visualization |
| `addEvent(msg, type)` | Append to the live event log |

## Critical Rules

1. YouTube source: download FIRST (via `prepare-source` API), THEN open editor
2. Local source: open editor directly, `prepare-source` is called on render submit
3. Never call `setView('editor')` before `prepare-source` completes for YouTube
4. `ws.onclose` without `ws.onerror` should also trigger fallback HTTP polling
5. All user-visible strings must be escaped via `esc()` before inserting into innerHTML
