# PRODUCT STATE — QUALITY-UP23: Batch Creator Workflow

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): batch creator workflow`
**Status:** Shipped

---

## Summary

Moves from "render one video at a time" to "creator batch workflow": queue many local video files, sleep, wake up to outputs. No cloud. No job orchestration rewrite. No architecture risk. Reuses existing render engine, existing queue, existing concurrency model.

**Creator experience:** Drop videos → Queue All → close laptop → come back to output folders.

---

## What Changed

### New file: `backend/static/js/batch-queue.js`

Self-contained `BatchQueue` IIFE module. Manages in-memory batch state (no localStorage — batch is a session-only operation).

**Public API:**
| Method | Description |
|---|---|
| `init()` | Initialize UI on editor open |
| `openFilePicker()` | Trigger file input |
| `onFilesSelected(files)` | Add FileList to queue |
| `onDrop(e)` / `onDragOver(e)` / `onDragLeave(e)` | Drag-and-drop handlers |
| `submit()` | Queue all pending items → POST to `/api/render/process` |
| `cancelItem(id)` | Cancel pending or running item |
| `retryItem(id)` | Re-queue and submit a failed item |
| `removeItem(id)` | Remove a non-running item from the list |
| `clear()` | Remove all non-running items |

**Item lifecycle:** `pending` → `queued` → `running` → `completed` / `failed` / `cancelled`

**Payload strategy:** Reads all form fields directly (same as `startRenderFromEditor`) without requiring a prepare-source session. Sets `source_mode: 'local'`, `source_video_path: item.filePath`, `edit_session_id: null`, `edit_trim_in/out: 0`. Voice, BGM, text layers, and market-viral are disabled for batch v1 simplicity.

**Output dir per file:** Computed client-side as `{parent_dir}/{file_stem}` from `file.path` (Electron exposes full path). Each source file gets a sibling output folder named after itself.

**Concurrency:** Backend `MAX_CONCURRENT_JOBS` enforced automatically by job_manager scheduler. Client submits all and lets backend queue.

**Failure isolation:** Each item has its own try/catch. One failed POST or render never cancels other items.

**Poll loop:** Single `setInterval` at 2s polls all active items in parallel via `GET /api/jobs/{job_id}`. Loop stops when no items are running or queued.

**Observability events:** `batch_started`, `batch_item_completed`, `batch_item_failed`, `batch_cancelled`, `batch_completed` — all emitted via `addEvent()`.

### Modified: `backend/static/index.html`

**Batch Queue section** added after the Output section (`evSectionBasic`), before Subtitle Style. Panel: `data-insp-panel="performance"` (Export tab).

Structure:
```
bqSection
  evSectionTitle "Batch Queue"
  bqDropZone (click to pick / drag-drop target)
    bqFileInput (hidden file input, accept="video/*" multiple)
  bqActions (hidden until files added)
    bqSubmitBtn "Queue N files"
    bqClearBtn  "Clear"
  bqList (card-per-file, dynamically rendered)
```

Script tag added after `creator-presets.js`:
```html
<script src="/static/js/batch-queue.js"></script>
```

### Modified: `backend/static/css/app.css`

New classes: `.bqSection`, `.bqDropZone`, `.bqDropZone.over`, `.bqDropIcon`, `.bqDropLabel`, `.bqActions`, `.bqSubmitBtn`, `.bqClearBtn`, `.bqList`, `.bqCard`, `.bqCard.bq-{status}`, `.bqCardTop`, `.bqCardName`, `.bqCardStatus.st-{status}`, `.bqProgress`, `.bqProgressBar`, `.bqCardActions`, `.bqActionBtn`, `.bqCardError`

### Modified: `backend/static/js/editor-view.js`

`BatchQueue.init()` called in both `openEditorView` and `openEditorView_withSession` after `CreatorPresets.init()`, before `evSyncQsBar()`.

---

## Architecture: What Was NOT Changed

| Not Changed | Reason |
|---|---|
| `/api/render/process` endpoint | Batch reuses it per-file, no new endpoint |
| `job_manager.py` scheduler | Already enforces MAX_CONCURRENT_JOBS |
| `startRenderFromEditor()` | Single-file path unchanged |
| `startBatchRender()` (P6-2 YouTube) | YouTube batch path unchanged |
| Render pipeline | Pure frontend addition |
| WebSocket / polling infra | Batch uses same `GET /api/jobs/{job_id}` |
| Cancel / retry (existing) | Untouched; batch uses same API endpoints |

---

## Constraints Honored

- **NO prepare-source call**: Batch goes directly to `/api/render/process` with `source_mode: 'local'`
- **NO session required**: `edit_session_id: null`; no pre-processing needed
- **NO architecture rewrite**: Reuses job lifecycle as-is
- **NO cloud**: All local, all in-process
- **NO memory explosion**: Items are lightweight in-memory objects; render work stays in backend job queue
- **NO regressions**: Single-file render, cancel, retry, WebSocket, history untouched

---

## Files Changed

| File | Change |
|---|---|
| `backend/static/js/batch-queue.js` | New: `BatchQueue` module |
| `backend/static/index.html` | Added `bqSection` HTML + `batch-queue.js` script tag |
| `backend/static/css/app.css` | New batch queue component styles |
| `backend/static/js/editor-view.js` | `BatchQueue.init()` in both editor open paths |
| `docs/render/PRODUCT_STATE_QUALITY_UP23.md` | This file |

---

## Manual QA Checklist

### File ingestion

- [ ] Click drop zone → file picker opens, accepts video files
- [ ] Multi-select 3 files → 3 cards appear (pending)
- [ ] Drag-drop 2 video files → 2 cards added (pending), drop zone highlights on dragover
- [ ] Drop zone accepts multiple files in one drop
- [ ] Cannot exceed 50 files (toast warning if over limit)

### Queue submit

- [ ] "Queue N files" button shows count of pending items
- [ ] Click "Queue All" → pending items flip to "Queued", then "Running" as backend picks up
- [ ] Submit button disabled while submitting, re-enabled after
- [ ] "Clear" removes non-running items only

### Per-item status

- [ ] Pending → Queued → Running (with progress %) → Completed (green border)
- [ ] Failed item shows error text, "Retry" button
- [ ] "Retry" re-queues and resubmits the failed item
- [ ] "Cancel" on pending → immediately cancelled
- [ ] "Cancel" on running → POST `/api/render/{job_id}/cancel` → cancelled
- [ ] "Remove" removes completed/failed/cancelled item from list

### Payload correctness

- [ ] Output dir = sibling folder of source file, named after file stem (no extension)
- [ ] Platform, subtitle style, CTA from Quick Strategy Bar reflected in rendered output
- [ ] Changing Creator Preset and then submitting uses updated preset settings

### Failure isolation

- [ ] Submit 3 files; intentionally break one (bad path) → other 2 continue rendering
- [ ] Network error on one poll tick does not crash other items

### Concurrency

- [ ] Submit 5 files; backend limits concurrency to MAX_CONCURRENT_JOBS; extras stay "Queued"
- [ ] As jobs complete, queued jobs pick up automatically

### No regressions

- [ ] Single-file editor render unaffected
- [ ] YouTube batch (P6-2) unaffected
- [ ] Cancel / retry in render queue unaffected
- [ ] WebSocket / history / export path unaffected
- [ ] Batch queue section appears in "Export" tab only (not other tabs)
