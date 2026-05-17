# PRODUCT STATE — RENDER-BE2.3: Concurrency Alignment

**Branch:** `feature/ai-output-upgrade`
**Commit:** `perf(render): concurrency alignment`
**Status:** Shipped

---

## Summary

One import. One line. Machines with 8+ cores now utilise all scheduled render
slots instead of silently capping at 2 concurrent FFmpeg-encode sections.

---

## Root Cause — The Mismatch

Two independent concurrency controls existed with no relationship to each other:

| Control | File | Default formula | Value on 8-core | Value on 16-core |
|---------|------|-----------------|-----------------|------------------|
| `MAX_CONCURRENT_JOBS` | `job_manager.py` | `max(1, cpu_count // 2)` | 4 | 8 |
| `JOB_SEMAPHORE` | `render_pipeline.py` | **hardcoded `2`** | **2** | **2** |

**Effect:** On an 8-core machine the scheduler grants 4 job slots, but only 2
jobs can ever enter the FFmpeg-encode section simultaneously. Jobs 3 and 4 hold
a `ThreadPoolExecutor` slot, block on `JOB_SEMAPHORE.acquire()`, and do nothing
until a slot opens. Throughput is capped at 50 % of the configured concurrency.

On a 16-core machine the waste is 75 %: 6 of 8 dispatched jobs sit idle.

---

## Fix — Single Source of Truth

`render_pipeline.py` now imports `MAX_CONCURRENT_JOBS` from `job_manager` and
uses it as the default for `JOB_SEMAPHORE`:

**Before:**
```python
_JOB_SEM_VALUE: int = max(1, int(os.getenv("MAX_RENDER_JOBS", "2")))
```

**After:**
```python
from app.services.job_manager import MAX_CONCURRENT_JOBS as _MAX_CONCURRENT_JOBS
_JOB_SEM_VALUE: int = max(1, int(os.getenv("MAX_RENDER_JOBS", str(_MAX_CONCURRENT_JOBS))))
```

`MAX_RENDER_JOBS` env var remains the explicit override for operators who want
to set a tighter ceiling than the scheduler's default.

---

## Why This Is Safe

### CPU distribution is already handled

The existing `_render_active_count` + `max_workers // _render_slot` logic
distributes CPU among concurrent jobs:

```python
JOB_SEMAPHORE.acquire()
with _render_active_lock:
    _render_active_count[0] += 1
    _render_slot = _render_active_count[0]
if _render_slot > 1:
    max_workers = max(1, max_workers // _render_slot)
```

When N jobs are in the encode section, each gets `1/N` of its computed
`hw_cap` part parallelism. This logic is untouched.

### `hw_cap` is already conservative

`hw_cap` for CPU-only encode is `cpu_total // 4` capped at 4. For GPU encode
it is `cpu_total // 3` capped at 6. These formulas already prevent a single
job from consuming all cores.

### No change on 4-core machines

`MAX_CONCURRENT_JOBS` on a 4-core machine is `max(1, 4 // 2) = 2`.
`JOB_SEMAPHORE` was already 2. Identical behaviour.

### No circular import

`job_manager.py` has no import of `render_pipeline.py`. The import is one-way.

---

## Effective Concurrency by Machine

| Cores | MAX_CONCURRENT_JOBS | JOB_SEMAPHORE (before) | JOB_SEMAPHORE (after) | Wasted slots (before) |
|-------|--------------------|-----------------------|----------------------|----------------------|
| 4     | 2                  | 2                     | 2                    | 0                    |
| 8     | 4                  | 2                     | 4                    | 2                    |
| 12    | 6                  | 2                     | 6                    | 4                    |
| 16    | 8                  | 2                     | 8                    | 6                    |

---

## Concurrency Ownership Map

| Layer | Owner | What it controls |
|-------|-------|-----------------|
| Scheduler | `job_manager.MAX_CONCURRENT_JOBS` | How many jobs are dispatched from the priority queue |
| Encode section | `render_pipeline.JOB_SEMAPHORE` | How many jobs can be in the FFmpeg-encode section simultaneously (now aligned to `MAX_CONCURRENT_JOBS`) |
| Per-job parts | `render_pipeline._render_active_count` + `hw_cap` | How many clip parts run in parallel within a single job |
| Per-ffmpeg threads | `render_engine.resolve_ffmpeg_threads` | How many threads ffmpeg uses per encode process |
| GPU sessions | `render_engine.NVENC_SEMAPHORE` | How many concurrent NVENC sessions (default 3, unchanged) |

---

## Constraints Honored

| Constraint | Status |
|-----------|--------|
| No scheduler rewrite | ✓ |
| No queue redesign | ✓ |
| No render pipeline rewrite | ✓ |
| No ffmpeg rewrite | ✓ |
| No websocket protocol change | ✓ |
| No API change | ✓ |
| No DB schema change | ✓ |
| No speculative autoscaling | ✓ |
| Cancel / resume / retry unaffected | ✓ |
| MAX_RENDER_JOBS override preserved | ✓ |

---

## Intentionally Deferred

- **Dynamic slot recalculation** — `JOB_SEMAPHORE` value is fixed at startup.
  Changing `MAX_CONCURRENT_JOBS` at runtime (e.g. via env reload) does not
  resize the semaphore. Acceptable: both values require a server restart to
  change anyway.
- **Per-job hw_cap re-tuning for very high core counts** — on 32+ core machines
  the `cpu_total // 4` base may still under-utilise. Out of scope; `hw_cap` and
  `hard_ceiling` formulas are unchanged.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/orchestration/render_pipeline.py` | Import `MAX_CONCURRENT_JOBS`; derive `_JOB_SEM_VALUE` default from it |
| `docs/render/PRODUCT_STATE_RENDER_BE2_3.md` | This file |

---

## Manual QA Checklist

- [ ] Single render: starts, progresses, completes correctly
- [ ] Single render cancel: stops cleanly, status = cancelled
- [ ] Single render retry: re-renders correctly
- [ ] Two concurrent renders: both dispatch and run (no deadlock, no stuck slots)
- [ ] `/queue-status` response: `max_renders` matches `max_concurrent` value
- [ ] `/queue/status` response: `max_concurrent`, `active`, `pending` truthful
- [ ] Console: `_JOB_SEM_VALUE=N` logged at startup (check job scheduler log)
- [ ] No backend errors during any of the above
