# Fix Plan — 2026-05-19

> Derived from `backend_render_audit.md` and `frontend_ui_audit.md` (2026-05-19).  
> Ordered by priority. Each fix is minimal and does not redesign existing architecture.  
> All changes must preserve existing API contracts, DOM IDs, and result_json shape.

---

## Priority 1 — Critical (Fix Before Next Release)

### FIX-001 — `cancelled` status breaks UI permanently

**Source:** FE-1.1  
**File:** `backend/static/js/render-ui.js:263`  
**Risk if unfixed:** P0 — UI stuck after every cancel. Polling runs forever. Render button stays disabled. Requires page reload.

**Change:**  
In `normalizeRenderStatus`, add one line before the final `return`:

```javascript
// render-ui.js — inside normalizeRenderStatus(), before the final return statement:
if (st === 'cancelled') return 'failed';
```

This routes `cancelled` through the existing `isTerminalRenderStatus` path (which already handles `'failed'`), triggering the full cleanup: poll stop, WS stop, `setRenderActionBusy(false)`, `saveRenderHistoryEntry`, output panel update.

**Do not** add `cancelling` here — it is an intermediate state and must remain non-terminal until the job actually becomes `cancelled`.

**Test:** Cancel a running render. Verify the UI transitions to "Failed" or "Cancelled" state, the render button re-enables, and polling stops.

---

## Priority 2 — High (Fix in Current Sprint)

### FIX-002 — Batch `_done.wait()` no timeout

**Source:** BE-1.2  
**File:** `backend/app/routes/render.py:714`  
**Risk if unfixed:** P1 — batch coordinator hangs forever if a child render is OS-killed.

**Change:**  
```python
# render.py — _run_batch(), replace:
_done.wait()
# With:
completed_in_time = _done.wait(timeout=7200)  # 2h hard ceiling per child
if not completed_in_time:
    logger.error(
        "Batch child %s timed out waiting (7200s) — marking failed and continuing", child_id
    )
    update_job_progress(child_id, "timeout", 100, "Child timed out in batch", status="failed")
```

This does not change batch behavior in the normal case. It only prevents an infinite hang on OS-level child process failure.

---

### FIX-003 — Batch cancel does not stop coordinator

**Source:** BE-1.3  
**File:** `backend/app/routes/render.py:687` (inside `_run_batch`)  
**Risk if unfixed:** P1 — cancelling a batch job has no effect; coordinator continues launching children.

**Change:**  
Add a cancel check at the start of each loop iteration:

```python
# render.py — inside _run_batch, at the top of the for loop:
for idx, (url, child_id) in enumerate(zip(urls, child_job_ids), start=1):
    from app.services import cancel_registry
    if cancel_registry.is_cancelled(batch_id):
        logger.info("Batch %s: cancel requested — stopping after %d/%d", batch_id, idx - 1, len(urls))
        upsert_job(
            batch_id, "render_batch", effective_channel, "cancelled",
            payload.model_dump(), {"count": len(urls), "jobs": child_job_ids},
            stage=JobStage.DONE, progress_percent=100,
            message=f"Batch cancelled after {idx - 1}/{len(urls)} items",
        )
        return
    # ... existing child submission code
```

This ensures that after the currently running child finishes, the coordinator checks for cancel before submitting the next child.

---

### FIX-004 — Preview session deleted on render failure

**Source:** BE-1.5  
**File:** `backend/app/orchestration/render_pipeline.py:5566-5570`  
**Risk if unfixed:** P1 — retry of a failed session-based render fails immediately because the session is gone.

**Change:**  
Make cleanup conditional on terminal success:

```python
# render_pipeline.py — in the finally block where cleanup_session_fn is called:
# Replace:
if edit_session_id:
    try:
        cleanup_session_fn(edit_session_id)
    except Exception:
        pass

# With:
_session_render_succeeded = final_job_status in ("completed", "completed_with_errors")
if edit_session_id and _session_render_succeeded:
    try:
        cleanup_session_fn(edit_session_id)
    except Exception:
        pass
```

Where `final_job_status` is the terminal status string written to the DB at end of pipeline (check existing variable names in context). Sessions remain available for retry on failure and are cleaned up by TTL eviction (6h default) when not consumed.

**Note:** This requires knowing the final status at cleanup time. Verify the pipeline exposes it in the finally scope.

---

### FIX-005 — Subtitle gating defaults need product decision

**Source:** FE-4.1  
**Files:** `backend/static/js/render-engine.js:83-86`  
**Risk if unfixed:** P1 — users receive no subtitles on low-scoring clips with no UI indication.

**Decision required from product team:**

Option A — Intentional: Document in UI. Add a visible indicator when subtitle gating is active (e.g., a note: "Subtitles shown on high-scoring clips only").

Option B — Unintentional: Revert to schema defaults:
```javascript
subtitle_only_viral_high: false,
subtitle_viral_min_score: 0,
subtitle_viral_top_ratio: 1.0,
```

---

## Priority 3 — Medium (Fix in Next Sprint)

### FIX-006 — WebSocket exception not logged

**Source:** BE-3.1  
**File:** `backend/app/routes/jobs.py:467-469`

```python
# jobs.py — ws_job_progress, replace:
except Exception:
    pass
# With:
except WebSocketDisconnect:
    pass
except Exception as exc:
    logger.warning("ws_job_progress error job_id=%s: %s", job_id, exc)
```

One line change. Zero risk.

---

### FIX-007 — History title shows YouTube URL

**Source:** BE-4.1  
**File:** `backend/app/routes/jobs.py:54-68`

```python
# jobs.py — _render_title_and_hint, after parsing result:
result = _parse_json(row.get("result_json")) if "result_json" in row else {}
title = str(result.get("source_title") or result.get("title") or "").strip()
if title:
    return _truncate_text(title), _truncate_text(url or title)
```

Requires `_normalize_history_item` to pass `row` with `result_json` to the title helper. Verify signature compatibility.

---

### FIX-008 — `cancelling` status has no UX treatment

**Source:** FE-2.2  
**File:** `backend/static/js/render-ui.js:350`

```javascript
// render-ui.js — in renderUxStageLabel, add before final return:
if (status === 'cancelling' || String(job?.status || '').toLowerCase() === 'cancelling') return 'Cancelling…';
```

Optional: add an orange/amber color to the stage pill when `job.status === 'cancelling'`.

---

### FIX-009 — History pagination

**Source:** FE-6.4, BE-4.2  
**File:** `backend/static/js/history-ui.js:152`

Add a module-level offset tracker and a "Load more" button:

```javascript
// history-ui.js
let historyOffset = 0;
let historyHasMore = false;

async function loadHistoryView(append = false) {
  if (!append) { historyOffset = 0; historyItems = []; }
  historyLoading = true;
  renderHistoryView();
  try {
    const res = await fetch(`/api/jobs/history?limit=20&offset=${historyOffset}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'History could not be loaded');
    const newItems = Array.isArray(data.items) ? data.items : [];
    historyItems = append ? [...historyItems, ...newItems] : newItems;
    historyHasMore = !!data.has_more;
    historyOffset += newItems.length;
  } catch (err) {
    historyError = String(err?.message || 'History could not be loaded');
  } finally {
    historyLoading = false;
    renderHistoryView();
  }
}

function loadMoreHistory() {
  if (!historyHasMore || historyLoading) return;
  loadHistoryView(true);
}
```

Add "Load more" button at bottom of history list when `historyHasMore` is true.

---

### FIX-010 — `currentJobId` lost on page reload

**Source:** FE-7.1  
**File:** `backend/static/js/render-engine.js`, `globals.js`

```javascript
// After setting currentJobId in _submitRenderPayload:
try { sessionStorage.setItem('rc_last_job_id', currentJobId); } catch(_) {}

// On app init (init.js or equivalent):
const _savedJobId = (() => { try { return sessionStorage.getItem('rc_last_job_id'); } catch(_) { return null; } })();
if (_savedJobId && !currentJobId) {
    fetch(`/api/jobs/${_savedJobId}`)
        .then(r => r.ok ? r.json() : null)
        .then(job => {
            if (job && !isTerminalRenderStatus(job.status)) {
                currentJobId = _savedJobId;
                startPolling(currentJobId);
                addEvent(`Reconnected to job ${_savedJobId.slice(0,8)}…`, 'render');
            }
        }).catch(() => {});
}
```

---

### FIX-011 — Polling max-duration guard

**Source:** FE-7.2  
**File:** `backend/static/js/render-engine.js`

```javascript
// Add at module level:
let _pollStartedAt = 0;

// In startPolling():
_pollStartedAt = Date.now();

// In loadJobProgress(), at the top:
if (_pollStartedAt && currentJobId) {
    const elapsedMs = Date.now() - _pollStartedAt;
    if (elapsedMs > 3 * 3600 * 1000) {   // 3 hour hard stop
        clearInterval(pollTimer); pollTimer = null; _pollStartedAt = 0;
        addEvent('Polling stopped after 3 hours — job may be stuck. Check diagnostics.', 'render');
        setRenderActionBusy(false);
        return;
    }
}
```

---

### FIX-012 — `result_json` dual parse consolidation

**Source:** FE-3.1  
**File:** `backend/static/js/render-engine.js:662`

Extract `_renderJobRankingMap` to use data already parsed by `populateRenderOutputPanel`:

```javascript
// render-engine.js — change augmentRenderOutputRanking signature:
function augmentRenderOutputRanking(job, prearsedRanking = null) {
    const ranking = prearsedRanking || _renderJobRankingMap(job);
    // ... existing logic
}

// Caller in _applyJobUpdate:
const parsedRanking = populateRenderOutputPanel(job, parts);  // returns ranking map
augmentRenderOutputRanking(job, parsedRanking);
```

This requires `populateRenderOutputPanel` to return the parsed ranking. Coordinate with render-ui.js changes.

---

## Priority 4 — Low (Backlog)

### FIX-013 — Batch `render_batch` excluded from `can_rerun`

**Source:** FE-6.1  
**File:** `backend/app/routes/jobs.py:196`

```python
"can_rerun": kind == "render" and base_status not in ("running", "queued"),
```

And separately exclude `render_batch` kind from the `"render"` normalization if needed.

---

### FIX-014 — Whisper preview transcript timeout guard

**Source:** BE-5.1  
**File:** `backend/app/routes/render.py:543-558`

```python
# Before transcription:
if session.get("duration", 0) > 1800:
    raise HTTPException(400, "Source longer than 30 minutes — preview transcript unavailable")
```

This prevents long transcription calls from blocking thread pool slots.

---

### FIX-015 — `_PREVIEW_SESSIONS` max-size guard

**Source:** BE-5.2  
**File:** `backend/app/routes/render.py:80-89`

```python
def _save_session(session_id: str, data: dict):
    MAX_SESSIONS = 200
    if len(_PREVIEW_SESSIONS) >= MAX_SESSIONS:
        oldest = min(_PREVIEW_SESSIONS, key=lambda k: _PREVIEW_SESSIONS[k].get("created_at", 0))
        _cleanup_preview_session(oldest)
    ...
```

---

### FIX-016 — Verify `rerunRenderJob` is defined

**Source:** FE-6.2  
**File:** `backend/static/js/history-ui.js:191-198`

Search all `backend/static/js/*.js` for `function rerunRenderJob`. If not found, either implement the function (calls `POST /api/render/resume/{job_id}` and starts monitoring) or remove the Rerun button.

---

### FIX-017 — `cancelled` parts in history count

**Source:** BE-4.3  
**File:** `backend/app/routes/jobs.py:81-92`

```python
def _parts_counts(parts: list[dict]) -> dict:
    counts = {"completed": 0, "failed": 0, "unsupported": 0, "cancelled": 0, "total": len(parts)}
    for part in parts:
        status = str(part.get("status") or "").lower()
        if status == "done":
            counts["completed"] += 1
        elif status == "failed":
            counts["failed"] += 1
        elif status == "unsupported":
            counts["unsupported"] += 1
        elif status == "cancelled":
            counts["cancelled"] += 1
    return counts
```

Update `_render_status_and_summary` to add cancelled to the failed bucket for display purposes.

---

## Implementation Order Summary

| Priority | ID | Description | Effort |
|----------|----|-------------|--------|
| **P0 — Ship blocker** | FIX-001 | `cancelled` status terminal mapping | 1 line |
| **P1 — Before next test** | FIX-002 | Batch wait timeout | 5 lines |
| P1 | FIX-003 | Batch cancel propagation | 10 lines |
| P1 | FIX-004 | Session cleanup on success only | 5 lines |
| P1 | FIX-005 | Subtitle gating product decision | Product call |
| P2 | FIX-006 | WS exception logging | 2 lines |
| P2 | FIX-007 | History title from result_json | 5 lines |
| P2 | FIX-008 | `cancelling` UX label | 3 lines |
| P2 | FIX-009 | History pagination | ~30 lines |
| P2 | FIX-010 | `currentJobId` session persistence | ~20 lines |
| P2 | FIX-011 | Polling max-duration guard | 10 lines |
| P2 | FIX-012 | result_json single parser | Refactor |
| **P3 — Backlog** | FIX-013 | Batch `can_rerun` exclusion | 3 lines |
| P3 | FIX-014 | Transcript timeout guard | 3 lines |
| P3 | FIX-015 | Session dict size bound | 5 lines |
| P3 | FIX-016 | Verify `rerunRenderJob` exists | Verify only |
| P3 | FIX-017 | `cancelled` parts in history count | 5 lines |

---

## What Not to Change

- Do not alter `_TERMINAL_STATUSES` in jobs.py — the backend correctly includes `cancelled`.
- Do not alter `cancel_registry` logic — the cancel chain from UI to FFmpeg is correct.
- Do not alter the `result_json` shape or key names.
- Do not alter DOM IDs referenced in render-ui.js or index.html.
- Do not rewrite `normalizeRenderStatus` — only add the missing `cancelled` case (FIX-001).
- Do not change WebSocket message shape `{job, parts, summary}`.
- Do not change polling fallback behavior — only add the duration guard (FIX-011).
