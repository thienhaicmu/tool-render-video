# PRODUCT STATE — RENDER-BE2.1: Stability & Free Wins

**Branch:** `feature/ai-output-upgrade`
**Commit:** `perf(render): stability and free wins`
**Status:** Shipped

---

## Summary

Four targeted low-risk improvements validated by the RENDER-BE1 audit.
No render behavior changed. No output changed. No queue semantics changed.
No creator-facing UX changed.

---

## Part A — `_JOB_LOG_DIRS` Defensive Cleanup

**File:** `backend/app/orchestration/render_pipeline.py`

**Finding:** `_JOB_LOG_DIRS.pop(job_id, None)` was the last statement in the
`finally` block. If `cleanup_session_fn(edit_session_id)` raised before it,
the pop would never execute.

**Fix:** Wrapped `cleanup_session_fn` in `try/except` so the pop and subsequent
`close_thread_conn()` always run regardless of session cleanup errors.

**Why safe:** The existing pop already used `.pop(key, None)` — no behavior
change for the normal path. Only the error path is affected.

**What was NOT done:** The existing cleanup at `_JOB_LOG_DIRS.pop(job_id, None)`
was already present and correct for all non-exception paths; no new sweep needed.

---

## Part B — Thread-Local DB Connection Reuse

**File:** `backend/app/services/db.py`, `backend/app/orchestration/render_pipeline.py`

**Finding:** `update_job_progress()` and `upsert_job_part()` each called `get_conn()`
(open SQLite connection) and `conn.close()` on every invocation. During a render
job, these are called ~150+ times (10 parts × 10 stage transitions + job-level
updates). Each open/close cycle has OS-level overhead.

**Fix:**
- Added `_tls = threading.local()` module-level thread-local store
- Added `_thread_conn()` — returns cached thread-local connection, re-opens on
  sqlite3 errors
- Added `close_thread_conn()` — explicit release (called from render `finally`)
- Changed `update_job_progress()` and `upsert_job_part()` to use `_thread_conn()`
  with `conn.commit()` but no `conn.close()`
- `render_pipeline.py` imports and calls `close_thread_conn()` in its `finally`
  block to release the main render thread's connection

**Thread safety:**
- Thread-local by design — no sharing across threads
- Inner `ThreadPoolExecutor` part workers each get their own thread-local
  connection, GC'd when threads exit (CPython ref counting, immediate)
- WAL mode handles concurrent multi-connection writes safely
- `SELECT 1` health check on reuse; re-opens silently on sqlite3 errors

**All other DB functions** (`get_job`, `list_job_parts`, `upsert_job`, etc.) are
unchanged — they continue to use `get_conn()` / `conn.close()` per-operation.

**Behavior unchanged:** Writes are identical. History is identical. Retry is
identical. Only the number of connection lifecycle operations changes.

---

## Part C — WebSocket Unchanged-Payload Skip

**File:** `backend/app/routes/jobs.py`

**Finding:** `ws_job_progress` sent the full `{job, parts, summary}` payload
every 500 ms unconditionally, even when nothing had changed between ticks.

**Fix:**
- Added `_TERMINAL_STATUSES` frozenset constant
- Added `_ws_fingerprint(job, parts, summary) -> tuple` — a cheap comparable
  tuple of material render state: job status/stage/progress/message, per-part
  (part_no, status, progress_percent), completed_parts, failed_parts, stuck count.
  Deliberately excludes timestamps (`updated_at`) so pure heartbeat DB ticks do
  not trigger sends.
- WS loop now tracks `last_fp` and only calls `send_json` when `fp != last_fp`
  OR when the job is in a terminal state.

**Safety guarantees:**
- Terminal events are ALWAYS sent (even if fingerprint matches prior tick)
- First tick always sends (`last_fp` starts as `None`)
- Any status, stage, progress, part status, or stuck-detection change triggers send
- DB reads still happen every 500 ms — only the WS send is skipped

**Why safe:** Prefer slightly noisy over missing a critical update. Terminal events
bypass the fingerprint check entirely.

---

## Part D — `_PENDING` Cancel Registry Cleanup

**Files:** `backend/app/services/cancel_registry.py`, `backend/app/services/job_manager.py`

**Finding:** `_PENDING` (set of job IDs cancelled before `register()` was called)
could accumulate stale entries for jobs that were cancelled while queued but never
dispatched (e.g., removed from queue externally, or edge-case race conditions).

**Fix:**
- Added `prune_pending(active_job_ids: frozenset) -> int` to `cancel_registry.py`
  — atomically removes `_PENDING` entries whose job ID is not in the provided
  active set
- `job_manager._run` wrapper calls `prune_pending()` after each job completes,
  passing the current snapshot of `_active_job_ids ∪ pending_heap_ids`

**Why safe:**
- `prune_pending` only removes entries NOT in the active set
- Snapshot is taken while holding `_cond` lock, ensuring consistency
- `prune_pending` call itself takes `_LOCK` separately — no nested lock
- Normal cancel flow (cancel while queued → `register()` → `_PENDING.discard()`)
  is unchanged; this is purely a safety sweep after job completion

---

## Constraints Honored

| Constraint | Status |
|-----------|--------|
| No scheduler rewrite | ✓ |
| No queue redesign | ✓ |
| No concurrency rewrite | ✓ |
| No ffmpeg rewrite | ✓ |
| No websocket protocol change | ✓ |
| No API change | ✓ |
| No DB schema change | ✓ |
| No creator-facing UI change | ✓ |
| No render output change | ✓ |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/orchestration/render_pipeline.py` | Part A: try/except around session cleanup; Part B: `close_thread_conn` import + call in finally |
| `backend/app/services/db.py` | Part B: `_tls`, `_thread_conn()`, `close_thread_conn()`; changed `update_job_progress` and `upsert_job_part` to use thread-local connection |
| `backend/app/routes/jobs.py` | Part C: `_TERMINAL_STATUSES`, `_ws_fingerprint()`, WS dedup loop |
| `backend/app/services/cancel_registry.py` | Part D: `prune_pending()` |
| `backend/app/services/job_manager.py` | Part D: call `prune_pending()` from `_run` wrapper after job completes |
| `docs/render/PRODUCT_STATE_RENDER_BE2_1.md` | This file |

---

## Manual QA Checklist

- [ ] Single render: starts, progresses, completes
- [ ] Multi render: both jobs run concurrently (if slots available)
- [ ] Resume: skips already-done parts
- [ ] Retry: re-renders failed parts
- [ ] Cancel: job stops within ~1s; status = cancelled
- [ ] History: all completed jobs appear with correct counts
- [ ] WS: runtime updates still live (progress changes visible)
- [ ] WS: completion event arrives instantly (not on next tick)
- [ ] WS: failure event arrives instantly
- [ ] DB: no lock errors or WAL corruption in logs
- [ ] Memory: no runaway growth over multiple renders
- [ ] Console: no new backend errors or warnings

---

## Intentionally Deferred

- **SQLite WAL checkpoint control** — WAL files grow until checkpoint; adding
  explicit `PRAGMA wal_checkpoint` calls is a future improvement but carries
  more risk than the changes here.
- **WS DB read frequency reduction** — reads still happen every 500 ms; reducing
  poll interval requires more architectural work (e.g., server-push on write).
- **apply_micro_pacing cancel-awareness** — `apply_micro_pacing` uses bare
  `subprocess.run()` and ignores cancel signals; fixing this requires refactoring
  into `_run_ffmpeg_with_retry` pattern (out of scope for this phase).
