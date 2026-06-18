# DB-backup worker-hang fix — "render succeeded but the worker still hangs" — 2026-06-18

> Append-only record. Companion to PHANTOM_RENDER_JOB_FIX_2026-06-18.md. That
> fix covered jobs left at `running` by a setup-phase crash. This one covers
> the other half of the user's question: a render that SUCCEEDS (DB=`completed`)
> but whose worker thread still hangs, holding its job slot and blocking new
> renders once the slots fill.

## Root cause

`pipeline_finalize.py` takes an opportunistic DB snapshot right after writing
`status=completed`:

```python
try:
    from ...db_backup import maybe_snapshot_after_job
    maybe_snapshot_after_job()      # ← synchronous, on the render worker thread
except Exception:
    pass
```

`maybe_snapshot_after_job` → `snapshot_db` → `src.backup(dst)`
(`sqlite3.Connection.backup`). The CPython implementation of `backup()`
**loops on `SQLITE_BUSY` / `SQLITE_LOCKED` with no maximum retry count** —
it sleeps and retries until the step succeeds or returns a non-busy error.
Under DB contention (other concurrent renders writing through `_thread_conn`,
or a checkpoint) the source can stay busy and the call **hangs indefinitely**.

Because the call is synchronous on the render worker:
- the DB row is already `completed` (so the UI reports done), but
- `process_render` never returns → the job stays in the scheduler's
  `_active_job_ids` → its concurrency slot is never freed.

With `MAX_CONCURRENT_JOBS` slots, a few such hangs exhaust the pool and every
new render sits `queued` forever. The `try/except: pass` around the call
catches exceptions but **cannot catch a hang**.

## Fixes

1. **Run the snapshot off the worker thread** (`pipeline_finalize.py`): the
   opportunistic backup is now `threading.Thread(target=maybe_snapshot_after_job,
   daemon=True).start()`. A slow/hung backup abandons a daemon thread instead
   of the render — completion never waits on it, and the job slot frees
   immediately.

2. **Prevent snapshot-thread pile-up** (`db_backup.py`): a hung backup leaves
   `_last_backup_at` stale, so the 1-hour time-trigger would re-fire on every
   later render and spawn a new connection pair each time. A
   `_snapshot_in_progress` guard makes `maybe_snapshot_after_job` a no-op while
   one is already running; a `try/finally` clears it even if the backup fails.

## Verification

- `tests/test_db_backup_async.py` (3): in-progress guard skips; a real
  snapshot is taken and the flag resets; the flag clears even when the backup
  raises.
- Full suite: **1421 passed**.

## Notes

- `Connection.backup()` itself still has no internal timeout; bounding the
  busy-loop reliably isn't possible through the Python API (the busy-loop is
  inside a single `backup_step`, below the `progress` callback). Moving it off
  the critical path is the correct fix — the snapshot is best-effort and must
  never gate a render.
- Combined with PHANTOM_RENDER_JOB_FIX (setup-crash phantoms) and
  `reconcile_orphaned_render_jobs`, both halves of "render done but can't start
  a new one" are now closed: a job can no longer be left non-terminal, and a
  successful render can no longer hang its worker on the backup.

## Files

```
backend/app/features/render/engine/pipeline/pipeline_finalize.py  (async snapshot)
backend/app/features/render/engine/pipeline/db_backup.py          (in-progress guard)
backend/tests/test_db_backup_async.py                              (new)
```
