# Phantom render-job fix — "render done but can't start a new one" — 2026-06-18

> Append-only record. Fixes a bug where a render that ended without writing a
> terminal DB status left a phantom `running` job that blocked every new render
> until the user manually killed it.

## Symptom (user report)

"Render báo xong nhưng không render mới được … render xong job sao chưa kill
job để chạy render job mới." — a render finishes, but you can't start a new one
unless you kill the old job.

## Root cause

`run_render_pipeline` runs its setup phase — `setup_render_pipeline(payload)`,
`prepare_output_dir(...)`, the initial `upsert_job` — **before** its own
top-level `try/except` (the try opens further down at
`render_pipeline.py:602`).

If anything in that setup phase raises, the exception propagates out of
`run_render_pipeline` into `process_render`'s handler:

```python
except Exception:
    final_status = "failed"
    raise          # ← re-raised WITHOUT a terminal DB write
```

The scheduler marked the job `running` at dispatch (`_mark_job_running`), and
nothing wrote a terminal status, so the row sits at **`status='running'`
forever**. That phantom is then:

- counted as an active job by the FE jobs store (`status in running/queued`),
  so RenderWorkflow's auto-reattach + the "a render is still running" prompt
  fire on every attempt to start a new render, and
- matched by the queue's source-dedup (`_find_active_duplicate_source`),
  which 409s a re-render of the same source.

A render that *completes* normally writes `completed`, so the phantom is
typically left behind by an EARLIER setup failure and silently blocks all
later renders — hence "it reports done but I still can't render again".

## Fixes

1. **Prevent new phantoms** — `process_render` (routers/_common.py) now forces
   the row terminal on the error path: if the job is still `running`/`queued`
   when the pipeline raises, it writes `status='failed'` before re-raising.
   Idempotent — never downgrades an already-terminal row.

2. **Clear existing phantoms during a session** — new
   `manager.reconcile_orphaned_render_jobs(stale_seconds=120)` marks render
   jobs that are `running`/`queued` in the DB but NOT tracked by the scheduler
   (and untouched for ≥120 s) as `interrupted` (resumable). Wired into the
   periodic cleanup loop (`main.py`). Conservative gates (untracked + stale)
   make it impossible to reconcile a genuinely active or just-submitted job.

   Startup recovery (`recover_pending_render_jobs`) already cleared phantoms on
   restart; this closes the in-session gap.

## Verification

- `tests/test_process_render_terminal_status.py` (4):
  - pipeline setup-raise → row becomes `failed` (not stuck `running`);
  - happy path never clobbers a `completed` row;
  - reconcile marks a stale untracked phantom `interrupted`;
  - reconcile skips tracked (live) and fresh (<120 s) jobs.
- Full suite: **1418 passed**.

## Immediate remediation for an already-stuck instance

To clear a phantom that exists right now without waiting for the 30-min cleanup
tick: restart the backend (startup recovery marks it `interrupted`), or cancel
it from the History tab. New phantoms won't be created after this fix.

## Files

```
backend/app/features/render/routers/_common.py   (process_render terminal guarantee)
backend/app/jobs/manager.py                       (reconcile_orphaned_render_jobs)
backend/app/main.py                               (periodic-cleanup wiring)
backend/tests/test_process_render_terminal_status.py  (new)
```
