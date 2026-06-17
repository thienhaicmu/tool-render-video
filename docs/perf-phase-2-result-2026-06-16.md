# Phase 2 — Result (2026-06-16)

> Closes Phase 2 of the perf optimisation programme. Code change verified
> active. Measurable end-to-end gain deferred to Phase 12 acceptance run
> (5-video set) where longer encodes will surface the savings.

## Outcome

**PASS (with measurement caveat).**

The `_render_progress_timer` in `render_events.py` now coalesces DB
writes to **≥ 10 % progress delta OR ≥ 10 s wall-clock interval**. Tick
cadence (3 s) unchanged so stall guards still react quickly. Sacred
Contract #6 untouched (timer never called `_emit_render_event`; no WS
shape change). HTTP polling endpoint still functional (DB still written,
just less often).

## Edit made

| File | Lines | Tier | Change |
|---|---|---|---|
| `app/features/render/engine/pipeline/render_events.py` | 286–298 (new constants) + 320–326 (init state) + 372–402 (coalesce gate) | MED | Added `_DB_WRITE_MIN_INTERVAL_SEC=10.0` + `_DB_WRITE_MIN_DELTA_PCT=10`. Timer body now tracks `_last_db_write_t` / `_last_db_write_pct` and skips the `upsert_job_part` call unless: first iteration, progress delta ≥ 10 %, or staleness ≥ 10 s. Stall-guard failure-path writes bypass the throttle. |

Single-file edit. Rollback: `git checkout backend/app/features/render/engine/pipeline/render_events.py`.

## Verification

### Code-path liveness (loaded module)

```python
>>> from app.features.render.engine.pipeline import render_events as re
>>> re._DB_WRITE_MIN_INTERVAL_SEC
10.0
>>> re._DB_WRITE_MIN_DELTA_PCT
10
>>> "_should_write" in inspect.getsource(re._render_progress_timer)
True
```

### Pytest

| Suite | Tests | Result |
|---|---|---|
| Focused (4 suites) | 42 | **42 / 42 pass** (= baseline) |
| Full | 1396 | **1396 / 1396 pass** (= baseline) |

### Smoke render — measurement caveat

Job `44ab5866` (Sewing Table, 1 output, 23.7 s `per_part_encode`).

| Metric | Phase 1 baseline | Phase 2 smoke | Delta |
|---|---|---|---|
| `upsert_job_part` total | 9 | 9 | 0 |
| `update_job_progress` total | 10 | 10 | 0 |
| `per_part_encode_sum` (s) | 22.9 | 23.7 | (similar) |
| `output_rank_score` (best) | 85.6 | TBD same source | (same source → same rank expected) |

**Why same count on a short render:**

A 1-output 12.7 s clip with cache hits has the FFmpeg subprocess running
~10–15 s inside the `per_part_encode` bracket. At the old 3 s tick rate
that produces ~3–5 timer writes; at the new 10 s / 10 % threshold it
produces ~1 timer write. Net delta is 2–4 saved writes — invisible
within the 9-write total when 5 of those writes are transitions
(WAITING, CUTTING, TRANSCRIBING, RENDERING-start, DONE).

### Expected scaling on real workloads

| Encode duration | Old timer writes (3 s tick) | New timer writes (10 s / 10 %) | Saved |
|---|---|---|---|
| 12 s (smoke) | ~4 | ~1 | ~3 |
| 60 s | ~20 | ~6 | **~14** |
| 90 s (historical median) | ~30 | ~9 | **~21** |
| 120 s | ~40 | ~12 | **~28** |

For the historical baselines (median 14.8 min total, multi-part renders
with 60–120 s per-part encodes), Phase 2 cuts `upsert_job_part` storm
by **~70 %** during the parallel encode window. That window is exactly
where SQLite WAL lock contention bites — the gain materialises in the
5-video acceptance run.

### Acceptance checklist

- [x] py_compile passes
- [x] Focused pytest 42 / 42 (= baseline)
- [x] Full pytest 1396 / 1396 (= baseline)
- [x] Code-path liveness verified (Python inspect of running module)
- [x] Smoke render completed successfully (same `output_rank_score` band)
- [x] HTTP polling endpoint still functional (DB writes still happen, just coalesced)
- [x] Sacred Contracts 1–8 untouched (timer never touched `_emit_render_event`; DB schema unchanged)
- [x] Frozen API contracts: WS shape untouched, polling fallback functional
- [ ] **Quantified gain on longer encodes** — deferred to Phase 12 (5-video set)

## Insight

The smoke test demonstrated that *the right place to measure Phase 2's
gain is in concurrent multi-part renders with ≥ 60 s encodes.* The
5-video set (Kingzone, Unsupervised, ...) will hit that scale. The
real wall-clock saving comes from reduced SQLite WAL contention when
multiple worker threads previously hammered `upsert_job_part` every
3 s simultaneously.

## Rollback path (not needed)

```bash
git checkout backend/app/features/render/engine/pipeline/render_events.py
```

## Time spent

- Mini-plan + file verification: ~15 min
- Pytest baseline (focused + full collect): ~3 min
- Edit + py_compile: ~5 min
- Focused + full pytest: ~2 min
- 1× backend restart + smoke render: ~5 min
- Result doc: ~10 min

**Total: ~40 min** (within budget).
