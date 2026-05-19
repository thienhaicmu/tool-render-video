# Backend Render Audit — 2026-05-19

> **Living document.** This revision supersedes the 2026-05-16 audit.  
> Scope: full production audit against current branch `feature/ai-output-upgrade`.  
> All findings reference exact file paths and line numbers verified in source.

---

## Audit Methodology

Read order:
1. All docs under `docs/` (ARCHITECTURE.md, RENDER_PIPELINE.md, FRONTEND_CONTRACT_PACKET_V1.md, UI_BEHAVIOR.md)
2. `backend/app/routes/render.py`, `routes/jobs.py`
3. `backend/app/services/job_manager.py`, `services/cancel_registry.py`, `services/db.py`
4. `backend/app/orchestration/render_pipeline.py` (targeted sections)
5. `backend/app/services/render_engine.py` (targeted sections)
6. `backend/app/models/schemas.py`

Severity scale: **P0** = crash / data-loss / stuck job / security. **P1** = production reliability, user-visible breakage. **P2** = UX gap, minor edge case, contract deviation.

---

## Section 1 — Queue and Job Lifecycle

### 1.1 Dual Semaphore — Status After Fix — P1

**Files:** `backend/app/services/job_manager.py`, `backend/app/orchestration/render_pipeline.py:1044`

**Previous audit finding (2026-05-16):** `MAX_CONCURRENT_JOBS` (job_manager) and `_JOB_SEM_VALUE` (render_pipeline) were independent, causing thread-pool exhaustion under divergent env vars.

**Current state:** `render_pipeline.py:1044` now reads:
```python
_JOB_SEM_VALUE: int = max(1, int(os.getenv("MAX_RENDER_JOBS", str(_MAX_CONCURRENT_JOBS))))
```
The default is now derived from `_MAX_CONCURRENT_JOBS` (imported from job_manager). The divergence only reappears if `MAX_RENDER_JOBS` is explicitly set without matching `MAX_CONCURRENT_JOBS`. This is an improvement but the independent override path remains.

**Residual risk:** An operator who sets `MAX_RENDER_JOBS=2` in the env without setting `MAX_CONCURRENT_JOBS=2` will run into the same thread exhaustion as before. The env var dependency is not documented.

**Fix:** Document the dependency in `docker-compose.yml` and `run-backend.ps1`. Optionally remove `MAX_RENDER_JOBS` and use only `MAX_CONCURRENT_JOBS`.

---

### 1.2 Batch Render — `_done.wait()` Has No Timeout — P1

**File:** `backend/app/routes/render.py:714`

**Current behavior:**
```python
_done = threading.Event()
def _child_fn(_id=child_id, _p=child_payload, _ev=_done):
    try:
        process_render(_id, _p, False)
    finally:
        _ev.set()
submitted = submit_job(child_id, _child_fn)
if submitted:
    _done.wait()   # ← no timeout
```

The batch coordinator thread blocks indefinitely on `_done.wait()`. `_ev.set()` is in a `finally` block so it fires for exceptions. However it does **not** fire if the worker thread is killed at the OS level (e.g. OOM kill, `os._exit`, or a C-extension crash inside Whisper/FFmpeg). In that case the coordinator hangs forever and the batch DB row stays `running`.

**Risk:** A single hung child render permanently stalls the batch coordinator daemon thread. The batch appears stuck with no user-visible recovery path short of server restart.

**Fix:**
```python
_done.wait(timeout=7200)   # 2-hour hard ceiling per child
if not _done.is_set():
    logger.error("Batch child %s timed out after 7200s — skipping", child_id)
    update_job_progress(child_id, "timeout", 100, "Child timed out in batch", status="failed")
```

---

### 1.3 Batch Cancel Does Not Stop Coordinator — P1

**File:** `backend/app/routes/render.py:763`, `backend/app/routes/render.py:1188-1204`

**Current behavior:**
- `cancel_render_job(batch_id)` sets `status=cancelling` in the DB and calls `cancel_registry.request_cancel(batch_id)`.
- The `_run_batch` daemon thread never checks `cancel_registry.is_cancelled(batch_id)`.
- Individual child jobs respect cancel signals via their own `cancel_registry` entries. But the coordinator continues submitting new children after the currently running child finishes.

**Risk:** Cancelling a batch job has no effect on already-queued children. The coordinator will continue launching children until all URLs are processed, while the batch DB row shows `cancelling`.

**Fix:** Add a check inside the `_run_batch` loop:
```python
from app.services import cancel_registry
for idx, (url, child_id) in enumerate(zip(urls, child_job_ids), start=1):
    if cancel_registry.is_cancelled(batch_id):
        update_job_progress(batch_id, ..., status="cancelled", ...)
        return
    # ... submit child
```

---

### 1.4 `_queue_render_job()` Race Condition — P1

**File:** `backend/app/routes/render.py:547-621`

**Current flow (unchanged since last audit):**
```python
if is_running(job_id):          # check — not atomic
    raise HTTPException(409)
previous = get_job(job_id)
upsert_job(job_id, ..., "queued")   # overwrites existing status
submitted = submit_job(job_id, ...)
if submitted:
    return
# restore previous state if submit rejected
```

Two concurrent POST requests for the same `resume_job_id` can both pass `is_running()`. Both overwrite DB state to `queued`. The second `submit_job` returns False (idempotent), triggering a restore attempt. But the restore reads `previous` captured before either `upsert_job` call, so the first request's queued state is overwritten by the second's restore of the original state, creating a brief state corruption window.

**Risk:** Rare (requires concurrent duplicate submits). Causes the job to flip back to `interrupted/failed` after appearing queued. Most visible when a user double-clicks Resume.

**Fix:** Use a DB-level optimistic lock:
```python
rowcount = db_try_claim_job(job_id, from_statuses=('interrupted','failed'))
if rowcount == 0:
    raise HTTPException(409, "Job already claimed or running")
```

---

### 1.5 Preview Session Deleted on Any Terminal — P1

**File:** `backend/app/orchestration/render_pipeline.py:5566-5570`

**Current behavior:**
```python
if edit_session_id:
    try:
        cleanup_session_fn(edit_session_id)   # always, in finally block
    except Exception:
        pass
```

The `cleanup_session_fn` (`_cleanup_preview_session`) is called unconditionally in the render pipeline's finally block, regardless of whether the render succeeded or failed.

**Risk:** If a user's session-based render fails (e.g., FFmpeg error, subtitle error) and they attempt to retry from the History view via "Rerun", the `edit_session_id` in the stored payload is no longer valid. The pipeline attempts `load_session_fn(edit_session_id)` → returns `None` → render fails immediately with no useful error.

**Affected flow:** History → Rerun a failed editor-session render.

**Fix:** Only clean up the session on successful completion:
```python
if edit_session_id and job_final_status in ("completed", "completed_with_errors"):
    cleanup_session_fn(edit_session_id)
```
Or: keep the session until it expires via TTL; do not actively delete it on failure.

---

### 1.6 `prepare_source` — YouTube Download Not Aborted Server-Side — P2

**File:** `backend/app/routes/render.py:449`

**Current behavior:** `download_youtube(yt_url, work_dir)` is called synchronously in the route function. The frontend sends a cancellable fetch with `AbortController`. When the user cancels via `cancelYtDownload()` in render-engine.js:161, the HTTP request is aborted client-side, but the server-side `download_youtube` (yt-dlp subprocess) continues to completion.

**Risk:**
- Orphaned temp directories accumulate in `TEMP_DIR/preview/` until `evict_stale_preview_sessions` runs.
- yt-dlp continues consuming bandwidth and disk I/O for a download the user abandoned.
- On slow connections or large videos, this can hold resources for many minutes.

**Fix:** Track active prepare-source downloads in a module-level dict keyed by session_id. Expose a `DELETE /api/render/prepare-source/{session_id}` endpoint that sends SIGTERM to the yt-dlp subprocess and cleans up the work dir.

---

## Section 2 — Cancel Flow

### 2.1 Cancellation Status Contract Is Correct — Informational

**File:** `backend/app/routes/render.py:1188-1205`, `backend/app/routes/jobs.py:21`, `backend/app/services/cancel_registry.py`

Backend cancellation is correctly implemented:
1. `cancel_render_job` → `status='cancelling'` (intermediate) → `cancel_registry.request_cancel(job_id)`.
2. `cancel_registry.register()` creates a `threading.Event` that is set immediately when cancel is requested.
3. `process_render` catches `JobCancelledError` → `status='cancelled'`.
4. WebSocket `_TERMINAL_STATUSES` includes `'cancelled'` → WS closes on cancel.
5. `set_thread_cancel_event(ev)` propagates the event to `render_engine._run_ffmpeg_with_retry` which kills the FFmpeg process.

The backend cancel chain is complete and correct. The bug is in the frontend (see frontend audit FE-2.1).

---

### 2.2 `cancel_render_job` Idempotency — P2

**File:** `backend/app/routes/render.py:1199`

```python
status = (row.get("status") or "").lower()
if status not in ("running", "queued"):
    raise HTTPException(status_code=409, ...)
```

If a job is in `cancelling` state (intermediate), calling cancel again returns 409. This is technically correct but non-idempotent. A frontend that aggressively retries the cancel call (e.g., after a failed request) gets a 409 it must interpret.

**Fix:** Also allow `cancelling` in the permitted statuses, but treat it as a no-op success:
```python
if status == "cancelling":
    return {"job_id": job_id, "status": "cancelling"}
```

---

## Section 3 — WebSocket and Transport

### 3.1 WebSocket Exception Silently Swallowed — P2

**File:** `backend/app/routes/jobs.py:467-469`

```python
except Exception:
    pass
```

All exceptions inside the WS loop are silently dropped. A bug in `_compute_progress_summary`, `get_job`, or `list_job_parts` causes the WebSocket to close with no diagnostic log. The client falls back to polling but neither developer nor user knows the WS died for a non-disconnect reason.

**Fix:**
```python
except WebSocketDisconnect:
    pass
except Exception as exc:
    logger.warning("ws_job_progress error job_id=%s: %s", job_id, exc)
```

---

### 3.2 Stuck Part Detection — No Automatic Recovery — P2

**File:** `backend/app/routes/jobs.py:380-384`

`_compute_progress_summary` computes `stuck_parts` (parts with no DB update for `>120s`) and includes them in WebSocket and poll responses. The frontend's `_detectStallSignal` checks for stall messages in the job row, but `stuck_parts` is not surfaced in any automatic recovery action.

**Risk:** A part that is genuinely stuck (FFmpeg hung after the `_FFMPEG_TIMEOUT_SEC` global timeout, or between pipeline stages) is detected but not acted upon. The job stays `running` indefinitely.

**Context:** `_FFMPEG_TIMEOUT_SEC` (default 3600s) applies per-FFmpeg-call, not per-part. A part with many serial FFmpeg calls could exceed 120s total without triggering the hang guard.

**Recommendation:** When `stuck_parts` is non-empty in the WS summary, the frontend should surface a "Render may be stuck" warning with a manual Cancel option more prominently than the current log-only behavior.

---

## Section 4 — History and Database

### 4.1 History Title Shows YouTube URL, Not Video Title — P2

**File:** `backend/app/routes/jobs.py:54-68`

```python
def _render_title_and_hint(payload: dict) -> tuple[str, str]:
    ...
    url = str(payload.get("youtube_url") or "").strip()
    if not url:
        return "Render job", "Render source unavailable"
    ...
    return _truncate_text(url), _truncate_text(url)
```

For YouTube renders, the history title is the raw YouTube URL (truncated to 72 chars). The video title is available in `result_json` (if the render completed) and in the download metadata stored during `prepare_source`, but neither is consulted here.

**Risk:** History list is not human-readable for YouTube renders.

**Fix:** Extract title from `result_json`:
```python
result = _parse_json(row.get("result_json"))
title = (result.get("source_title") or result.get("title") or "").strip()
if not title:
    title = _truncate_text(url)
```

---

### 4.2 History View — No Pagination Beyond 20 Items — P2

**File:** `backend/app/routes/jobs.py:269-287`

The `/api/jobs/history` endpoint supports `limit` and `offset` params (with `has_more` in the response), and enforces `limit <= 100`.

However, the frontend `loadHistoryView()` hardcodes `?limit=20` with no pagination UI. Users with >20 jobs cannot see older history.

**Fix (frontend):** Load the next page when the user scrolls to the bottom of the history list, or add explicit "Load more" button using the `has_more` flag from the response.

---

### 4.3 `_parts_counts` Does Not Count `cancelled` Parts — P2

**File:** `backend/app/routes/jobs.py:81-92`

```python
def _parts_counts(parts: list[dict]) -> dict:
    counts = {"completed": 0, "failed": 0, "unsupported": 0, "total": len(parts)}
    for part in parts:
        status = str(part.get("status") or "").lower()
        if status == "done":
            counts["completed"] += 1
        elif status == "failed":
            counts["failed"] += 1
        elif status == "unsupported":
            counts["unsupported"] += 1
    return counts
```

Parts with `status='cancelled'` are counted in `total` but in none of the counts. In `_render_status_and_summary`, this means a job with all-cancelled parts would appear as `failed` with `0 clips failed` (because `failed=0, completed=0`), giving a confusing summary message.

**Fix:** Add `cancelled` to the failed bucket or add a separate `cancelled` counter.

---

## Section 5 — Temp File and Resource Management

### 5.1 `preview_transcript` Has No Timeout — P2

**File:** `backend/app/routes/render.py:543-558`

```python
model = get_whisper_model("tiny")
result = model.transcribe(str(video_path), fp16=False, verbose=False)
```

Whisper transcription has no timeout. For a 60-minute source video, `tiny` model transcription can take several minutes. FastAPI runs sync routes in a thread pool (Starlette default: 40 threads). Multiple simultaneous transcript requests can exhaust the thread pool and stall other API calls.

**Fix:** Wrap in a `concurrent.futures.ThreadPoolExecutor` with a timeout, or add a length-based guard:
```python
if duration > 1800:   # > 30 minutes
    raise HTTPException(400, "Source too long for preview transcript — use a shorter clip")
```

---

### 5.2 `_PREVIEW_SESSIONS` Memory Dict — No Size Bound — P2

**File:** `backend/app/routes/render.py:74`

`_PREVIEW_SESSIONS: dict[str, dict]` is bounded by the TTL eviction in `evict_stale_preview_sessions()`. If many sessions are created within 6 hours, the dict grows linearly. On a production machine with multiple users, this is low risk, but on a long-running dev machine with repeated testing, it can accumulate hundreds of entries.

**Fix:** Add a max-size guard in `_save_session`:
```python
if len(_PREVIEW_SESSIONS) > 200:
    # evict oldest
    oldest = min(_PREVIEW_SESSIONS, key=lambda k: _PREVIEW_SESSIONS[k].get("created_at", 0))
    _cleanup_preview_session(oldest)
```

---

## Section 6 — Security

### 6.1 `_resolve_job_log_path` Path Traversal Guard — Verified Correct

**File:** `backend/app/routes/jobs.py:215-260`

The log path resolver validates that user-supplied `output_dir` from the job payload resolves to a path under `Path.home()` or `CHANNELS_DIR`:
```python
_safe_roots = (Path.home().resolve(), CHANNELS_DIR.resolve())
if not any(out_path == r or out_path.is_relative_to(r) for r in _safe_roots):
    out_path = None
```
This is correct and prevents log reading from system directories.

---

### 6.2 `delete_job` Output File Deletion — Verified Correct

**File:** `backend/app/routes/jobs.py:494-526`

File deletion is similarly guarded:
```python
_safe_roots = tuple(r.resolve() for r in [CHANNELS_DIR, TEMP_DIR] if r.exists())
if not any(p == r or p.is_relative_to(r) for r in _safe_roots):
    logger.warning(...)
    skipped_files += 1
    continue
```
Output files outside `CHANNELS_DIR` or `TEMP_DIR` are never deleted. Correct.

---

### 6.3 `quick-process` Video Filter Allowlist — Verified Correct

**File:** `backend/app/routes/render.py:966-978`

The `video_filter` parameter is validated against an allowlist of safe FFmpeg filter names before use. Filters like `movie=`, `geq=`, or `script=` are rejected. This prevents FFmpeg filter injection.

---

### 6.4 Media Streaming — File Path from DB Only — Verified Correct

**File:** `backend/app/routes/render.py:1230`

Both streaming endpoints (`/render/jobs/{job_id}/parts/{part_no}/media` and `/jobs/{job_id}/parts/{part_no}/stream`) resolve the output file path from the job_parts DB row, not from user input. No path traversal risk.

---

## Section 7 — API Contract Deviations

### 7.1 `selected_parts_count` vs `selected_segments_count` — P2

**File:** `docs/FRONTEND_CONTRACT_PACKET_V1.md:601`, `backend/app/orchestration/render_pipeline.py`

Documentation (`FRONTEND_CONTRACT_PACKET_V1.md:601`) mentions both `selected_parts_count` and `selected_segments_count`. The contract doc notes: "A frontend parser should normalize both, preferring `selected_segments_count` when present." The render pipeline writes `selected_segments_count`.

The legacy key `selected_parts_count` exists in older history entries. Parsers must handle both.

**Status:** Documented inconsistency; not a new bug. Verify frontend parser normalizes both.

---

### 7.2 Duplicate Streaming Endpoints — P2

**Files:** `backend/app/routes/render.py:1217`, `backend/app/routes/jobs.py:404`

Two endpoints serve the same part output file:
- `/api/render/jobs/{job_id}/parts/{part_no}/media` — `StreamingResponse` with manual Range request handling (correct HTTP 206).
- `/api/jobs/{job_id}/parts/{part_no}/stream` — `FileResponse` with `Accept-Ranges: bytes` header (Starlette handles Range natively since v0.20).

Both work. Having two endpoints for the same resource creates documentation debt and maintenance risk if one is updated without the other.

**Fix:** Deprecate `/api/jobs/{job_id}/parts/{part_no}/stream` in favor of the render endpoint, or ensure both use identical Range logic.

---

## Summary Table

| ID | Severity | Area | Status |
|----|----------|------|--------|
| BE-1.1 | P1 | Dual semaphore env var dependency | Partially fixed; residual risk documented |
| BE-1.2 | P1 | Batch `_done.wait()` no timeout | Open |
| BE-1.3 | P1 | Batch cancel not propagated | Open |
| BE-1.4 | P1 | `_queue_render_job` race condition | Open |
| BE-1.5 | P1 | Preview session deleted on failure | Open |
| BE-1.6 | P2 | yt-dlp not aborted on client cancel | Open |
| BE-2.1 | ✓ | Cancel chain (cancel_registry → FFmpeg kill) | Correct |
| BE-2.2 | P2 | Cancel idempotency on `cancelling` | Open |
| BE-3.1 | P2 | WS exception silently swallowed | Open |
| BE-3.2 | P2 | Stuck part — no auto-recovery | Open (by design; surface in UI) |
| BE-4.1 | P2 | History title shows URL not video title | Open |
| BE-4.2 | P2 | History no pagination beyond 20 | Open (frontend fix needed) |
| BE-4.3 | P2 | `cancelled` parts not counted in history | Open |
| BE-5.1 | P2 | Whisper transcript no timeout | Open |
| BE-5.2 | P2 | `_PREVIEW_SESSIONS` no size bound | Open |
| BE-6.1 | ✓ | Log path traversal guard | Correct |
| BE-6.2 | ✓ | File deletion safety roots | Correct |
| BE-6.3 | ✓ | FFmpeg filter injection guard | Correct |
| BE-6.4 | ✓ | Media streaming — DB path only | Correct |
| BE-7.1 | P2 | `selected_parts_count` alias | Documented; parser handles both |
| BE-7.2 | P2 | Duplicate streaming endpoints | Open |
