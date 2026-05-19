# Frontend UI Audit — 2026-05-19

> **Living document.** This revision adds findings from the 2026-05-19 production audit.  
> Scope: `backend/static/js/render-engine.js`, `render-ui.js`, `history-ui.js`, `globals.js`.  
> The `backend/static-v2/` new shell (audited 2026-05-14) is out of scope here.

---

## Audit Methodology

Reviewed:
- `render-engine.js` (full)
- `render-ui.js` (lines 1–450 in detail, plus targeted grep for all `normalizeRenderStatus`, `isTerminalRenderStatus`, `result_json` parse calls)
- `history-ui.js` (full)
- `backend/app/routes/jobs.py` WS `_TERMINAL_STATUSES` to cross-check frontend expectations
- `docs/FRONTEND_CONTRACT_PACKET_V1.md` for contract expectations

Severity: **P0** = crash / permanent stuck UI. **P1** = user-visible breakage. **P2** = UX gap or contract deviation.

---

## Section 1 — Critical: Cancelled Status

### FE-1.1 `cancelled` Status Not Recognized as Terminal — P0

**Files:** `backend/static/js/render-ui.js:263-301`, `backend/static/js/render-engine.js:283-312`

**Root cause:** `normalizeRenderStatus()` in render-ui.js does not map `'cancelled'`:

```javascript
// render-ui.js:263–282 — current code
function normalizeRenderStatus(status, stage = ''){
  const st = String(status || '').toLowerCase().trim();
  if (st === 'pending' || st === 'queued') return 'pending';
  if (st === 'preparing' || st === 'starting') return 'preparing';
  if (st === 'scene_detecting') return 'scene_detecting';
  if (st === 'rendering') return 'rendering';
  if (st === 'completed' || st === 'done' || st === 'complete') return 'completed';
  if (st === 'completed_with_errors' || st === 'partial_failed') return 'completed_with_errors';
  if (st === 'failed' || st === 'interrupted' || st === 'stalled' || st === 'timeout') return 'failed';
  if (st === 'running') { ... }
  return st || (sg ? 'working' : '');   // 'cancelled' falls here → returns 'cancelled'
}
```

`isTerminalRenderStatus` (render-ui.js:299–302):
```javascript
function isTerminalRenderStatus(status){
  const st = normalizeRenderStatus(status);
  return st === 'completed' || st === 'completed_with_errors' || st === 'partial_failed'
      || st === 'failed' || st === 'interrupted' || st === 'done' || st === 'complete';
  // 'cancelled' is NOT in this set
}
```

**Full failure chain after job cancel:**

1. Backend sets job status to `cancelled`.
2. Backend WebSocket sends `{job: {status: 'cancelled'}, ...}` and closes (correct — `cancelled` ∈ `_TERMINAL_STATUSES`).
3. `_applyJobUpdate` runs with `status = 'cancelled'`.
4. `isTerminal = isTerminalRenderStatus('cancelled')` → **`false`**.
5. `setRenderActionBusy(false)` is **never called** → render button stays disabled.
6. `saveRenderHistoryEntry` is **never called** → history not updated.
7. Output panel is **not shown or cleared** — stuck in whatever state it was in.
8. `_stopJobWs()` + poll clear DO run (because `_applyJobUpdate` calls them when `isTerminal`... but `isTerminal` is false, so they DO NOT run). 

Wait — re-reading `_applyJobUpdate`:
```javascript
if(isTerminal){
    _stopJobWs();
    if(pollTimer){ clearInterval(pollTimer); pollTimer = null; }
    ...
    setRenderActionBusy(false);
    saveRenderHistoryEntry(job, s, parts);
    ...
}
```
Since `isTerminal = false`, none of these run.

9. The backend WS closes → `ws.onclose` fires in render-engine.js:358:
```javascript
ws.onclose = () => {
    jobWs = null;
    if (!currentJobId) return;
    if (isTerminalRenderStatus(lastStatus)) return;  // 'cancelled' → false → does NOT return
    if (!pollTimer) {
        loadJobProgress();
        pollTimer = setInterval(loadJobProgress, pollIntervalMs);  // POLLING RESTARTS
    }
};
```

10. **Polling restarts indefinitely** against the cancelled job.
11. Each poll response has `status: 'cancelled'` → `isTerminal` = false → no cleanup.
12. The UI is permanently stuck: render button disabled, progress shown, polling active forever.

**Impact:** Any use of the cancel button results in a permanently broken UI session. The user must reload the page to recover.

**Fix (minimal, safe):** Add `'cancelled'` to `normalizeRenderStatus` mapping to `'failed'`:
```javascript
// render-ui.js:263 — in normalizeRenderStatus, before the final return:
if (st === 'cancelled' || st === 'cancelling') return 'failed';
```

This makes `isTerminalRenderStatus('cancelled')` return `true`, which triggers the full cleanup path: poll stop, WS stop, action busy cleared, history saved, output panel updated.

Note: `cancelling` (intermediate) should NOT be terminal. Add only `cancelled` to the failed mapping. `cancelling` can map to `'preparing'` or remain as-is (non-terminal) since it is transient.

Precise minimal fix:
```javascript
if (st === 'cancelled') return 'failed';
```

---

## Section 2 — WebSocket and Polling

### FE-2.1 `ws.onclose` Polling Restart on `cancelled` — P0

**File:** `backend/static/js/render-engine.js:358-366`

This is a direct consequence of FE-1.1. Documented here separately because the `ws.onclose` handler is the site of the polling restart and the fix must address both `normalizeRenderStatus` and verify the `ws.onclose` guard.

After the fix in FE-1.1, `lastStatus` will be `'failed'` (normalized from `'cancelled'`), and `isTerminalRenderStatus(lastStatus)` will return `true`, so `ws.onclose` will correctly return without restarting polling.

**No additional code change needed if FE-1.1 is fixed.**

---

### FE-2.2 `cancelling` Status Has No Visible UI Treatment — P2

**File:** `backend/static/js/render-ui.js:263`

When a cancel is in progress, the backend sets `status='cancelling'` (intermediate). `normalizeRenderStatus('cancelling')` returns `'cancelling'` (no mapping). This is passed through to the stage pill label:

```javascript
qs('job_stage_pill').textContent = renderUxStageLabel(job, s, parts || []);
```

`renderUxStageLabel` in render-ui.js:350 has no case for `'cancelling'` → returns `'Working...'`.

**Risk:** The user sees "Working..." while cancellation is in progress. They don't know the cancel was received.

**Fix:** Add a case in `renderUxStageLabel`:
```javascript
if (status === 'cancelling' || st === 'cancelling') return 'Cancelling…';
```
And add a visual treatment (e.g., orange badge) to distinguish from active rendering.

---

## Section 3 — Render Output and Result Parsing

### FE-3.1 `result_json` Parsed Inline in render-engine.js — P1

**File:** `backend/static/js/render-engine.js:662-680`

```javascript
function _renderJobRankingMap(job) {
  const map = new Map();
  try {
    const raw = job?.result_json;
    const result = raw ? (typeof raw === 'string' ? JSON.parse(raw) : raw) : {};
    const ranking = Array.isArray(result?.output_ranking) ? result.output_ranking : [];
    ...
  } catch (_) {}
  return map;
}
```

This parses `result_json` independently from the render output panel population (`populateRenderOutputPanel`). This violates the single-parser contract from `FRONTEND_CONTRACT_PACKET_V1.md:568`: "Create exactly one `ResultPackage` parser/normalizer. No page or component may parse `result_json` independently."

**Risk:** If `populateRenderOutputPanel` normalizes `output_ranking` differently (e.g., handles missing fields differently), the ranking badges injected by `augmentRenderOutputRanking` may display stale or wrong data. If `output_ranking` shape changes, both parsers must be updated independently.

**Fix:** Extract a shared `parseOutputRanking(job)` helper and call it from both `augmentRenderOutputRanking` and `populateRenderOutputPanel`. Do not parse `result_json` more than once per job update.

---

### FE-3.2 `augmentRenderOutputRanking` Called After `populateRenderOutputPanel` — P2

**File:** `backend/static/js/render-engine.js:302-307`

```javascript
if (isCompleted) {
    ...
    if (typeof populateRenderOutputPanel === 'function') {
        populateRenderOutputPanel(job, parts);
        augmentRenderOutputRanking(job);   // augments DOM after populate
    }
}
```

`augmentRenderOutputRanking` walks the DOM to add ranking badges to `.renderClipItem` elements. If `populateRenderOutputPanel` is async or triggers a repaint, the ranking augmentation may run before the DOM is ready.

**Risk:** Ranking badges silently not applied (querySelector finds no elements). No error is surfaced.

**Fix:** Have `populateRenderOutputPanel` return the ranking data so `augmentRenderOutputRanking` doesn't need a second parse and DOM walk. Or call `augmentRenderOutputRanking` inside `populateRenderOutputPanel` after DOM insertion.

---

## Section 4 — Render Payload Defaults

### FE-4.1 Frontend Sends Non-Default Subtitle Gating Values — P1

**File:** `backend/static/js/render-engine.js:83-86`

```javascript
subtitle_only_viral_high: true,
subtitle_viral_min_score: 68,
subtitle_viral_top_ratio: 0.6,
```

Backend defaults (`backend/app/models/schemas.py`):
- `subtitle_only_viral_high`: `false`
- `subtitle_viral_min_score`: `0`
- `subtitle_viral_top_ratio`: `1.0`

**Effect:** The frontend enables subtitle gating that the backend disables by default. With `subtitle_viral_min_score: 68`, segments scoring below 68 will not receive subtitles. With `subtitle_viral_top_ratio: 0.6`, only the top 60% of segments (by score) get subtitles. Combined with `subtitle_only_viral_high: true`, low-scoring segments get no subtitles at all.

**Risk:** Users who expect subtitles on all clips are silently getting partial subtitle coverage. This is product-level behavior that differs from documented defaults with no UI indication that gating is active.

**Clarification needed:** If this is intentional product behavior (subtitle gating enabled by default in the UI), it should be:
1. Documented in the render config UI.
2. The schema defaults should be updated to match, or the frontend should be explicit that it is overriding defaults.

If unintentional (inherited from old code), revert to schema defaults:
```javascript
subtitle_only_viral_high: false,
subtitle_viral_min_score: 0,
subtitle_viral_top_ratio: 1.0,
```

---

### FE-4.2 `highlight_per_word: true` Overrides Backend Default — P2

**File:** `backend/static/js/render-engine.js:65`

Backend schema default: `highlight_per_word: false`. Frontend sends `true`. Karaoke-style per-word highlighting is on by default in the current UI. This is likely intentional (product decision) but should be verified against the subtitle style compatibility: `highlight_per_word: true` requires word-level timing from Whisper and a compatible subtitle style.

**Risk:** If the selected `subtitle_style` doesn't support per-word highlighting, the backend may silently fall back to sentence-level timing, causing a discrepancy between what the user expects and what renders.

---

### FE-4.3 `max_export_parts: 0` vs Schema Default `null` — P2

**File:** `backend/static/js/render-engine.js:70`

Frontend sends `0`. Backend schema default is `null`. Backend pipeline check:
```python
# render_pipeline.py:2381
if payload.max_export_parts and payload.max_export_parts > 0:
    scored = scored[:payload.max_export_parts]
```

`0` is falsy in Python, so `max_export_parts=0` behaves identically to `null` (no limit). This is **not a bug** but deviates from the documented contract default. Sending `null` explicitly from the frontend would be more correct.

---

## Section 5 — Source Preparation

### FE-5.1 `cancelYtDownload` Does Not Clean Up Server-Side Download — P1

**File:** `backend/static/js/render-engine.js:161-165`

```javascript
function cancelYtDownload() {
  if (_ytDownloadAbortCtrl) {
    _ytDownloadAbortCtrl.abort();
    _ytDownloadAbortCtrl = null;
  }
}
```

Aborting the fetch request aborts the HTTP connection to the server. However, the server-side `download_youtube` (yt-dlp process) continues running until completion. The session directory is created and the video is fully downloaded to `TEMP_DIR/preview/{session_id}/` even after the client has moved on.

**Risk:** Disk space waste. On slow connections, repeated cancel-and-retry cycles accumulate full video downloads in temp storage.

**Fix (frontend):** After abort, issue a fire-and-forget DELETE request to signal the server (requires backend endpoint):
```javascript
if (_ytDownloadAbortCtrl) {
    _ytDownloadAbortCtrl.abort();
    if (_pendingPrepareSessionId) {
        fetch(`/api/render/prepare-source/${_pendingPrepareSessionId}`, { method: 'DELETE' }).catch(() => {});
    }
}
```

This requires the backend `DELETE /api/render/prepare-source/{session_id}` endpoint (see BE-1.6).

---

## Section 6 — History View

### FE-6.1 `can_rerun` Always True for All Render Kinds — P2

**File:** `backend/app/routes/jobs.py:196`

```python
"can_rerun": kind == "render",
```

`kind` is normalized to `"render"` for all non-download jobs (including `render_batch`, interrupted, failed, and completed renders). This means:

1. `render_batch` parent jobs show a "Rerun" button — but `rerunRenderJob` in the frontend is designed for single renders, not batch coordinator jobs.
2. Interrupted renders from sessions that no longer have a valid `edit_session_id` show "Rerun" — clicking it attempts a resume that fails with no preview session.

**Fix (backend):** Add a check:
```python
"can_rerun": kind == "render" and base_status in ("completed", "completed_with_errors", "failed", "interrupted"),
```

Exclude `render_batch` from `can_rerun`.

---

### FE-6.2 `rerunHistoryRender` Uses Undefined Function — P2

**File:** `backend/static/js/history-ui.js:191-198`

```javascript
async function rerunHistoryRender(encodedJobId) {
  const jobId = decodeURIComponent(String(encodedJobId || ''));
  try {
    if (typeof rerunRenderJob !== 'function') throw new Error('Render rerun is unavailable');
    await rerunRenderJob(jobId);
  } catch (err) {
    showToast(String(err?.message || 'Render job could not be loaded'), 'error');
  }
}
```

If `rerunRenderJob` is not defined in the current JS bundle (it's not visible in render-engine.js or render-ui.js), every Rerun click shows a toast error "Render rerun is unavailable".

**Action:** Verify `rerunRenderJob` is defined and exported from one of the static JS files. If not, implement or remove the Rerun button.

---

### FE-6.3 History Filter "Failed" Silently Includes Interrupted — P2

**File:** `backend/static/js/history-ui.js:80`

```javascript
if (historyFilter === 'failed') return status === 'failed' || status === 'interrupted';
```

Filtering by "Failed" also shows `interrupted` jobs. This may confuse users who expect "Interrupted" to be a distinct category. Whether this is correct depends on the product definition of "failed" vs "interrupted".

**Recommendation:** Either add a separate "Interrupted" filter button, or rename the filter to "Failed / Interrupted" in the UI.

---

### FE-6.4 History — No Pagination — P2

**File:** `backend/static/js/history-ui.js:152`

```javascript
const res = await fetch('/api/jobs/history?limit=20');
```

Hard-coded limit of 20 with no pagination UI. The backend response includes `has_more: true` when more items exist, but the frontend never reads it.

**Fix:** Check `data.has_more` after load. If true, show a "Load more" button or auto-paginate on scroll:
```javascript
if (data.has_more) {
    historyCanLoadMore = true;
    renderHistoryLoadMoreButton();
}
```

---

## Section 7 — State Management

### FE-7.1 `currentJobId` Not Persisted Across Page Reload — P2

**Files:** `backend/static/js/globals.js`, `backend/static/js/render-engine.js`

`currentJobId` is a module-level global. If the user reloads the page while a render is in progress, the job ID is lost and the render monitor goes blank. The user must know the job ID or wait for the job to appear in history.

**Risk:** Users who accidentally reload during a long render lose visibility into progress. The render continues on the backend (correctly), but the frontend cannot reconnect without the job ID.

**Fix:** Persist `currentJobId` to `sessionStorage` on update:
```javascript
// In _submitRenderPayload after setting currentJobId:
try { sessionStorage.setItem('lastJobId', currentJobId); } catch(_) {}
// On init, restore if job is still active:
const lastJobId = sessionStorage.getItem('lastJobId');
if (lastJobId) checkAndResumeJobMonitor(lastJobId);
```

---

### FE-7.2 Polling Never Stops on Unexpected WS Close for Non-Terminal Status — P1

**File:** `backend/static/js/render-engine.js:358-366`

The `ws.onclose` handler restarts polling unless `isTerminalRenderStatus(lastStatus)` is true. This is the correct fallback pattern. However, if the WS closes with `lastStatus` as an unexpected status (e.g., backend bug returns unknown status string), polling runs forever because no unknown status is terminal.

**Fix:** Add a max-polling-duration guard:
```javascript
let _pollStartedAt = 0;
// In startPolling:
_pollStartedAt = Date.now();
// In loadJobProgress:
if (_pollStartedAt && Date.now() - _pollStartedAt > 3 * 3600 * 1000) {
    clearInterval(pollTimer); pollTimer = null;
    addEvent('Polling stopped after 3 hours — job may be stuck. Check logs.', 'render');
}
```

---

## Summary Table

| ID | Severity | Area | Status |
|----|----------|------|--------|
| FE-1.1 | **P0** | `cancelled` not recognized as terminal — UI stuck forever | **Open — fix immediately** |
| FE-2.1 | P0 | `ws.onclose` restarts polling on cancel | Fixed by FE-1.1 |
| FE-2.2 | P2 | `cancelling` has no UX treatment | Open |
| FE-3.1 | P1 | `result_json` parsed inline — dual parse risk | Open |
| FE-3.2 | P2 | `augmentRenderOutputRanking` DOM timing | Open |
| FE-4.1 | P1 | Subtitle gating defaults differ from schema | **Needs product decision** |
| FE-4.2 | P2 | `highlight_per_word: true` default override | Verify intentional |
| FE-4.3 | P2 | `max_export_parts: 0` vs `null` | Safe; not a bug |
| FE-5.1 | P1 | Cancel YouTube download — server orphan | Open |
| FE-6.1 | P2 | `can_rerun` too broad | Open |
| FE-6.2 | P2 | `rerunRenderJob` may not be defined | Verify |
| FE-6.3 | P2 | Filter "Failed" includes interrupted | By design? |
| FE-6.4 | P2 | History no pagination | Open |
| FE-7.1 | P2 | `currentJobId` lost on page reload | Open |
| FE-7.2 | P1 | Polling never stops on unknown terminal status | Open |
