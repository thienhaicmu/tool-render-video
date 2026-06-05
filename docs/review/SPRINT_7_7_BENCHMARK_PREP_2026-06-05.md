# Sprint 7.7 Pre-Gate Benchmark — Prep & Initial Findings

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-7-prep-benchmark`
**Baseline:** Pytest 2423 passed / 1 skipped / 0 failed @ `ee83c82` (main, post Sprint 7.6a)
**Final pytest:** 2423 passed / 1 skipped / 0 failed (no code change to production; benchmark script is standalone)
**Source:** `docs/review/SPRINT_PLAN_2026-06-05.md` §"Sprint 7.7 — pre-gate benchmark plan" + `DB_CONNECTION_AUDIT_2026-06-05.md` §"Decision"

## Purpose

Sprint 7.7 proposes unifying `_thread_conn` → `db_conn` in `db/jobs_repo.py` so the project has one connection pattern instead of two. The Sprint 5.4 audit deferred the unification with **three explicit preconditions**:

1. Per-frame progress-write benchmark on representative render (WAL + SATA SSD).
2. Confirm `db_conn()` cost per call is **< 1ms** OR cost amortised by batching.
3. Audit that no render-thread reuse pattern breaks `_thread_conn` reuse semantics.

This sprint ships the **measurement tool** (`backend/scripts/benchmark_db_progress_writes.py`) that satisfies the data half of precondition #1 and gives a quantitative answer to precondition #2. Sprint 7.7 itself is gated on operators running this benchmark on their target hardware and the results passing the audit-doc criteria below.

## Initial findings on dev machine

The benchmark was smoke-run during this prep sprint to verify the tool works. The numbers are NOT a Sprint 7.7 ship/defer verdict (multiple runs on representative hardware are needed for that), but they are directionally instructive.

**Hardware:** Windows 11, Python 3.11.x, `data/app.db` on local drive, WAL mode confirmed via `PRAGMA journal_mode`.

**Config:** 500 iterations + 50 warmup per helper, single-threaded.

| Helper | Median (us) | p95 (us) | p99 (us) | Mean (us) | Throughput (calls/sec) |
|---|---|---|---|---|---|
| `_thread_conn` | 18.8 | 40.3 | 66.4 | 27 | 37,203 |
| `db_conn` (ctxmgr) | 3,151.8 | 3,944.7 | 5,193.5 | 3,331 | 300 |

**Ratio:** `db_conn` is ~165x slower per call. The connection-open + WAL-init + close cycle dominates the cost.

**Pass criteria evaluation:**

| Criterion | Threshold | Actual | Verdict |
|---|---|---|---|
| 1. db_conn p95 latency | < 5 ms | 3.94 ms | **PASS** (3.94 < 5.00) |
| 2. wall-time delta | < 1 % | +12,331 % | **FAIL** |
| 1. db_conn cost per call | < 1 ms | 3.15 ms | **FAIL** |

Note: the original Sprint 5.4 audit specified `<1ms` for the "cost per call" criterion. Sprint 7.7 row in SPRINT_PLAN_2026-06-05.md restated as `<5ms` p95 for tail-latency. Both criteria are documented because tail-latency p95 < 5 ms is the operator-visible bound, while median < 1 ms is the "fast enough to amortise" bound. Per the empirical data, **median fails the 1 ms bound by 3x**.

**Implication:** Sprint 7.7 as a 1:1 helper swap is NOT viable. The render hot path (`update_job_progress` + `upsert_job_part`) called at high frequency would slow ~165x. With even modest progress-tick rates (say 10/sec), total per-render DB time goes from milliseconds to seconds.

## Three ship paths after the benchmark

The benchmark surfaces three Sprint 7.7 options, each with a different audit doc footprint:

### Path A — Defer indefinitely, keep `_thread_conn`

Status quo. Sprint 5.4's "two-pattern surface" is the steady-state. CLAUDE.md Issue 2 stays PARTIALLY RESOLVED.

**Trigger to revisit:** Connection-pool dependency added (e.g. `sqlalchemy`), or SQLite migrated to a server-mode database, or render thread pool migration that breaks `_thread_conn` reuse.

### Path B — Add batching layer

Aggregate N progress writes into a single `db_conn()` call. Render thread writes to an in-memory queue; a flush helper (called every K ticks OR T ms) opens one `db_conn` for the batch.

**Pros:** Eliminates the per-call open cost. One open per K ticks instead of one per tick.

**Cons:** New abstraction layer. Per-tick progress visibility delayed by up to K ticks (HTTP polling sees stale data). Sacred Contract #6 spirit pressure (events arrive in batches, not real-time).

**ROI sketch:** If K=10, total writes drop 10x → `db_conn` cost amortises to ~315 us/tick. Still 17x slower than `_thread_conn` per equivalent tick of visible progress. Not obviously better than Path A.

### Path C — Reduce write frequency at the source

Find every `update_job_progress` call site, replace high-frequency calls (per-frame, per-second) with rate-limited equivalents (every Nth call, or debounced). Then ship `_thread_conn` → `db_conn` because the call rate is now low enough that the per-call cost doesn't matter.

**Pros:** Sacred Contract #6 unchanged. Unification ships.

**Cons:** Touches every call site. UI polling experience changes (progress bar updates less frequently). HIGH risk on user-visible behavior.

**ROI sketch:** Cut calls by 100x → total cost drops to 0.0331 sec of DB time per render. Acceptable. But touches HIGH-tier files.

## Recommended next step

**Path A** for this audit doc cycle. Reasoning:

1. The benchmark proves Sprint 7.7 in its original form (1:1 helper swap) doesn't pass the gate.
2. Path B and Path C each warrant their own Planner cycle + audit doc.
3. CLAUDE.md Issue 2 was already documented as PARTIALLY RESOLVED — this benchmark is the empirical justification for the deferral, not a regression.
4. No production user has reported the `_thread_conn` / `db_conn` mixed pattern as a problem.

**What to ship this sprint:**
- Benchmark script (one file under `backend/scripts/`).
- This audit doc.
- Update `DB_CONNECTION_AUDIT_2026-06-05.md` cross-reference? Per CLAUDE.md docs/review/ append-only rule, NO — cite this new doc from any future audit instead.
- Update CLAUDE.md Issue 2 status? Recommend YES — flip from PARTIALLY RESOLVED to RESOLVED-WITH-DEFER + reference this benchmark + SPRINT_7_7_BENCHMARK_PREP audit doc as the empirical justification.

## How to run the benchmark (for future operators)

```powershell
# From backend/ with venv active:
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
python -m scripts.benchmark_db_progress_writes --iterations 1000 --warmup 100
```

```bash
# Optional flags:
--iterations N    # Measured samples per helper (default 1000, minimum 100)
--warmup N        # Discarded initial samples (default 100)
--output path     # JSON output path (default: temp dir, printed at end)
```

**Methodology guarantees:**
- Single-threaded measurement. Multi-thread amplification (4-8 workers each holding their own `_thread_conn`) is NOT tested by this script. The per-call cost is the apples-to-apples; the parallel render scenario is the production amplification.
- WAL mode confirmed via `PRAGMA journal_mode` assertion before any benchmark write.
- Temp DB at `$TMP/sprint_7_7_bench_*/data/app.db`. NOT touched: production `data/app.db`.
- Warmup phase discarded (covers first-connection-open cost).
- Same `UPDATE jobs SET stage, progress_percent, message, updated_at WHERE job_id=?` statement run by both helpers.

**Interpretation guide:**

| Pass scenario | Verdict |
|---|---|
| Both criteria pass on 3 separate runs | Sprint 7.7 unification ready to scope (Path A original) |
| Criterion 1 pass, criterion 2 fail | Look at Path B (batching) or Path C (rate-limit) |
| Both fail | Path A (defer indefinitely) is the honest call |
| High stdev or p99 outlier | Re-run on quiet machine; flag for follow-up |

## Sacred Contracts walk (this sprint)

| Contract | Touched? | Disposition |
|---|---|---|
| #1-#8 | No | Benchmark script is standalone, never executes against production DB, never modifies render-pipeline code. Pure measurement tool. |
| Performance Protections (NVENC, WAL) | No | Script verifies WAL is set on the temp DB; does NOT change it. NVENC not involved. |
| CLAUDE.md "data/app.db is sole job state authority" | Honored | Script uses `$TMP/.../data/app.db` (temp DB initialised via `APP_DATA_DIR` env override). Production DB untouched. |

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.7 row — scoped this prep work
- `docs/review/DB_CONNECTION_AUDIT_2026-06-05.md` §"Decision" — three preconditions this benchmark satisfies
- `CLAUDE.md` "Known Active Issues" §"Issue 2 — Mixed DB Connection Model" — current status PARTIALLY RESOLVED; this audit doc is the data justification for further deferral
- `backend/scripts/benchmark_db_progress_writes.py` — the measurement tool
- `backend/app/db/connection.py:101-170` — the two helpers under test
- `backend/app/db/jobs_repo.py:37, 116` — the production sites that read `_thread_conn` today

## What this sprint does NOT do

- Does NOT ship the unification itself (Sprint 7.7 proper).
- Does NOT propose batching or rate-limiting implementations (Path B / Path C).
- Does NOT modify production DB connection helpers.
- Does NOT change CLAUDE.md Issue 2 status — that's a separate doc-only commit on a future audit cycle if operators choose Path A.
- Does NOT delete `_thread_conn`.

## Open follow-up

If a future operator runs the benchmark on representative production hardware AND all three pass scenarios from the matrix above ALL show consistent passes, the Sprint 7.7 unification can be re-scoped via a fresh Planner cycle citing this audit doc + their benchmark JSON.

If `_thread_conn` reuse semantics break (e.g. render workers migrate to a thread pool with reuse), the deferral becomes obsolete and Path C (rate-limit + unify) becomes the only viable route — author a new SPRINT_7_7_PLAN audit doc citing this one as the prior art.
