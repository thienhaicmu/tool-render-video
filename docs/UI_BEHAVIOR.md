# UI Behavior

## Scope
This document covers runtime UI behavior for rendering:
- job state transitions (`queued -> running -> completed/failed/interrupted`)
- WebSocket stream + HTTP polling fallback
- completion bar behavior
- Back to Editor flow
- editor session usage (`_ev.sessionId`)

## Render State Lifecycle

## Backend status values
Render jobs are persisted in SQLite and exposed via `/api/jobs/*`.

Primary statuses:
- `queued`
- `running`
- `completed`
- `failed`
- `interrupted`

Related UI/summary status:
- `partial` (computed in history when completed parts + failed parts both exist)

## Typical state flow
1. User submits render from Editor.
2. Job starts at `queued`.
3. Worker updates to `running`.
4. Terminal state:
   - `completed` (full or partial clip success)
   - `failed`
   - `interrupted` (startup recovery marks unfinished jobs)

## Stage flow shown in monitor
Stage labels map from backend stage values:
- `queued`, `starting`, `downloading`
- `scene_detection`
- `segment_building`
- `transcribing_full`
- `rendering` / `rendering_parallel`
- `writing_report`
- `done` / `failed`

## Real-Time Updates

### Primary channel: WebSocket
Frontend first opens:
- `GET ws /api/jobs/{job_id}/ws`

Server pushes every ~500 ms:
```json
{
  "job": {...},
  "parts": [...],
  "summary": {
    "total_parts": 8,
    "completed_parts": 3,
    "failed_parts": 1,
    "processing_parts": 2,
    "pending_parts": 2,
    "overall_progress_percent": 41.3,
    "stuck_parts": []
  }
}
```

### Fallback channel: HTTP polling
If WebSocket errors, UI degrades gracefully to polling:
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/parts`
- poll interval from globals: `2500 ms`

This fallback is always available even if WS is blocked.

## Progress and Completion Bars

## Active progress bars
UI maintains smooth progress animation:
- backend value is source-of-truth
- display value interpolates for visual smoothness

During clip rendering:
- part aggregate is used to refine overall progress
- rendering segment maps roughly to 30-90% of job bar
- terminal states snap progress to 100%

## Completion bar
When job reaches `completed`:
- completion bar is shown (`render_completion_bar`)
- main message example:
  - `Render complete - X clips ready`
  - or `Render complete - X clips completed, Y failed`
- summary line includes output location and optional voice/subtitle translation summary

When job is `failed`/`interrupted`:
- completion bar is hidden

## Back to Editor Flow

Function: `backToEditorFromCompletion()`

Behavior:
1. Reads `(_ev && _ev.sessionId)`.
2. If missing session:
   - shows error toast/event (`Editor session is no longer available...`)
   - does not reopen editor
3. If session exists:
   - builds a minimal session payload (`session_id`, `duration`, `title`, `export_dir`)
   - calls `openEditorView_withSession(...)`
   - reuses existing preview session (no re-download)

## Editor Session Model (`_ev`)

Editor runtime object stores:
- `_ev.sessionId`
- `_ev.exportDir`
- `_ev.duration`
- `_ev.pendingPayload`
- `_ev.sourceMode`, `_ev.sourceUrl`

Session creation path:
- `POST /api/render/prepare-source`
- returns `session_id`, `duration`, `title`, `export_dir`

Preview paths:
- `GET /api/render/preview-video/{session_id}`
- `GET /api/render/preview-transcript/{session_id}` (Whisper tiny transcript for live subtitle preview)

Session failure behavior:
- if session missing/expired, render submission with `edit_session_id` fails clearly
- UI prompts user to re-open editor from source prep

## Stuck Detection and Monitor Signals

Backend summary marks active parts as stuck when no DB update crosses threshold.
UI uses this to display diagnostics badges and stale-progress hints.

## Practical UX Notes

- `queued` and early stages can show "waiting" animation state if backend progress is static.
- `interrupted` is treated as terminal in frontend monitor logic.
- history cards compute `completed` / `partial` / `failed` from part outcomes, not just base status.
