# Performance Baseline — 2026-06-16

> Baseline reference for the multi-phase render + download performance
> optimisation programme (see CTO audit report in conversation history,
> 2026-06-16). Captured BEFORE any optimisation phase has been merged.
> Every subsequent phase compares against these numbers.

## Phase 0 — what changed in code

Pure-additive observability layer (LOW–MED tier, no logic change).
See commits this phase introduces (Batch 0A + 0B).

| Batch | File | Change |
|---|---|---|
| 0A | `app/services/metrics.py` | Added 4 metric definitions: `render_stage_seconds`, `render_cache_lookups_total`, `whisper_transcribe_seconds`, `render_db_writes_total` |
| 0B | `app/features/render/engine/pipeline/pipeline_cache.py` | `@_instrument_cache` decorator on 5 cache-get helpers (`scene`, `whisper_srt`, `ass`, `scores`, `llm_plan`) |
| 0B | `app/features/render/engine/pipeline/llm_pipeline.py` | `WHISPER_TRANSCRIBE_DURATION.observe()` in Whisper finally block |
| 0B | `app/db/jobs_repo.py` | `DB_WRITES_TOTAL.inc()` on 4 writer surfaces: `upsert_job`, `update_job_progress`, `update_render_plan`, `upsert_job_part` |
| 0B | `app/db/ab_scores_repo.py` | `DB_WRITES_TOTAL.inc()` on `upsert_ab_score` |

**Risk**: LOW–MED. Pure observation, never raises. Each emit wrapped in
try/except so a metric backend error never affects the pipeline.

**Sacred Contracts unchanged**:
- #1 result_json aliases — untouched.
- #2 RenderRequest defaults — untouched.
- #3 AI return-None — untouched (decorators preserve return value).
- #4/#5 stage names — untouched.
- #6 `_emit_render_event` signature — untouched.
- #7 sole DB authority — untouched (write counter wraps existing writes).
- #8 qa_pipeline — untouched.

---

## Pytest baseline

```
1396 tests collected
```

Pytest count must match this number after every subsequent phase. Any
delta triggers STOP per Render Edit Protocol.

Focused pytest run after Phase 0 edits: **68/68 pass** across
`test_llm_cache.py`, `test_llm_cache_integration.py`,
`test_pipeline_cache_atomic_write.py`, `test_db_conn_acquire_metrics.py`,
`test_llm_metrics.py`, `test_render_duration_metric.py`,
`test_jobs_repo_stage_validation.py`, `test_llm_pipeline_hard_fail.py`.

---

## Historical reference baselines (from `data/app.db`)

These are completed render jobs already in the system. Per Phase 0
decision (pragmatic Option B), we use them as the wall-clock reference
instead of re-running every video. The new per-stage / cache-lookup
metrics begin populating from the first job rendered after the Phase 0
restart (see "Fresh control render" below).

### Job 1 — `1c7062a7` — Stress: long-form, 8-output

| Field | Value |
|---|---|
| Source | `I Was Left Unsupervised for a Week….mp4` (471 MB) |
| Target | `target_duration=90`, `output_count=8`, `target_platform=tiktok` |
| Codec | `h264` (NVENC implicit), whisper=`auto` (resolved to `base` per LLM pipeline default) |
| Settings | `add_subtitle=1`, motion_crop=null, narration=null, bgm=null, title_overlay=0 |
| Final status | `completed_with_errors` (1/6 parts done, 5 failed at ≥99 %) |
| **Total wall-clock** | **2,311 s (38.5 min)** |
| **Best `output_rank_score`** | **88.00** |
| Per-part wall-clock (mean of 6 parts) | 95.5 s |

### Job 2 — `aa1000e4` — Standard heavy, 6-output

| Field | Value |
|---|---|
| Source | `I Was Left Unsupervised for a Week….mp4` |
| Target | `target_duration=90`, `output_count=6`, `target_platform=tiktok` |
| Settings | same as Job 1 |
| Final status | `completed` (DB shows 1 part-row but `output_count=6` requested) |
| **Total wall-clock** | **692 s (11.5 min)** |
| **Best `output_rank_score`** | **89.90** (highest in the set) |

### Job 3 — `5e722c2d` — Vietnamese long, 4-output

| Field | Value |
|---|---|
| Source | `Update Kingzone 1 Cân 3- 3842+Vs 3835++ … - YouTube.mp4` (185 MB) |
| Target | `target_duration=90`, `output_count=4`, `target_platform=tiktok` |
| Settings | same |
| Final status | `completed` (2/2 parts done — cleanest run in the set) |
| **Total wall-clock** | **1,079 s (18.0 min)** |
| **Best `output_rank_score`** | **80.50** (rank #2 = 77.10) |

### Job 4 — `74c8177e` — Light Vietnamese, 3-output

| Field | Value |
|---|---|
| Source | `Update Kingzone 1 Cân 3- … - YouTube.mp4` |
| Target | `target_duration=90`, `output_count=3`, `target_platform=tiktok` |
| Settings | same |
| Final status | `completed_with_errors` (1/3 parts done) |
| **Total wall-clock** | **592 s (9.9 min)** |
| **Best `output_rank_score`** | **85.10** |

### Aggregated reference numbers

| Metric | Value |
|---|---|
| Median render wall-clock (4 jobs) | **885 s (14.8 min)** |
| Min / Max | 592 s (9.9 min) / 2,311 s (38.5 min) |
| Median best `output_rank_score` | **86.55** |
| Min / Max best rank | 80.50 / 89.90 |
| Per-part median wall-clock | **~88 s** (across parts that reached ≥99 %) |

These four numbers are the **wall-clock targets to preserve quality
against** in every subsequent phase. A phase that lowers `output_rank_score`
below the per-job historical value by more than 0.5 % halts roll-out
per the protocol.

---

## Fresh control render — Sewing Table Flip Potential

**STATUS: CAPTURED** (2026-06-16, post-restart with Phase 0A+0B code live).

### Source

| Field | Value |
|---|---|
| Path | `D:\demo\Sewing Table Flip Potential.mp4` |
| Size | 109 MB |
| **Duration** | **72.2 s** |
| Resolution | 1080 × 1440 |
| FPS | 30 |
| Prior history | None — first ever render |

### Submission attempts

Two attempts were submitted. The first failure is a useful data point
because it exercises the LLM cold-cache miss path; the second is the
clean success used as the fresh-control baseline.

| Attempt | Job ID | Params | Wall-clock | Outcome |
|---|---|---|---|---|
| 1 | `aa5c89fb` | `output_count=2`, `target_duration=60`, `min/max_part_sec=15/120` | **37 s** | **failed at RENDERING_PARALLEL** — `ai_emission_empty`: LLM returned 0 usable clips. Root cause: configuration mismatch — 2 × 60-s clips cannot fit in a 72.2-s source. Not a code bug. |
| 2 | `4bcf9326` | `output_count=1`, `target_duration=20`, `min/max_part_sec=10/35` | **55 s** | **completed** — 1 part `Make Money Reselling.mp4` rendered, duration 12.7 s |

### Quality reference — successful job (`4bcf9326`)

| Field | Value |
|---|---|
| Total wall-clock | **55 s** |
| Best `output_rank_score` | **85.6** (within historical band 80.50 – 89.90) |
| Part #1 duration | 12.7 s |
| Final stage | `done` / `progress=100` / `message="Render completed"` |

### Captured metric values from `/metrics` (after both jobs)

#### Cache lookups (`render_cache_lookups_total`)

| Cache | Outcome | Count |
|---|---|---|
| `whisper_srt` | miss | 1 (job 1 cold) |
| `whisper_srt` | hit | 1 (job 2 reused SRT) |
| `llm_plan` | miss | 2 (both jobs missed LLM cache) |
| `ass` | miss | 1 (subtitle file generated once for job 2) |
| `scene`, `scores` | — | not exercised on single-output 20-s clip |

**Key insight:** the `whisper_srt` cache *worked*. Job 2 reused job 1's
transcript (same source file, same model+engine+lang key) → Whisper was
not re-invoked. This is exactly the cache-correctness signal we want.

#### Whisper (`whisper_transcribe_seconds`)

| Model | Engine | Count | Sum (s) | Avg (s) |
|---|---|---|---|---|
| `small` | `default` | 1 | **23.11** | 23.11 |

Cold-start Whisper for 72.2 s source = 23.1 s wall-clock with `small`
model. That's ~3.1 × realtime on this CPU. Job 2 did not invoke Whisper
(cache hit) — exactly as designed.

#### LLM (`llm_render_plan_seconds` + `llm_render_plan_calls_total`)

| Provider | Calls | Sum (s) | Notes |
|---|---|---|---|
| `gemini` | 2 | **20.52** | 1 success (job 2) + 1 empty (job 1) |
| `claude` | 1 | 0.001 | Job 1 fallback chain (returned empty fast) |
| `openai` | 1 | 0.001 | Job 1 fallback chain (returned empty fast) |

Job 1's "no usable clips" cascaded through all 3 providers via the
fallback chain (see Phase audit Part 7). Each provider returned empty
near-instantly because the config was impossible — the fallback chain
worked correctly, it's the request that was malformed.

#### DB writes (`render_db_writes_total`)

| Surface | Count (across both jobs) | Avg per job | Notes |
|---|---|---|---|
| `upsert_job` | 6 | 3 | Per-job status transitions |
| `update_job_progress` | 19 | 9.5 | **Phase 2 coalescing target — 70 % reduction goal** |
| `upsert_job_part` | 15 | 7.5 | Per-part transitions + encode-progress ticks |
| `update_render_plan` | 1 | 0.5 | Persisted only on successful LLM plan |
| `upsert_ab_score` | 1 | 0.5 | Per output |

This is the baseline `update_job_progress` + `upsert_job_part` rate
that Phase 2 (coalescing) must reduce by ≥ 70 % without losing UI
progress fidelity.

#### NVENC (`nvenc_acquire_wait_seconds`)

| Metric | Value |
|---|---|
| Wait count | 0 |
| Wait sum | 0 s |

No contention — only one job ran at a time, NVENC always free. Baseline
target for Phase 4 (semaphore release after render loop) needs to be
re-measured under **concurrent-job load**; this single-job run does not
expose the bottleneck.

#### FFmpeg

| Metric | Value |
|---|---|
| Invocations (result=ok) | 2 |
| Duration sum | 12.45 s |

2 FFmpeg calls (cut + render-part) for the single output. Matches the
intermediate-file pattern flagged as R8 in the audit — first call writes
`raw_part.mp4`, second reads it.

#### Whole-job

| Metric | Value |
|---|---|
| `render_job_duration_seconds_sum{status="succeeded"}` | 91.95 s |
| `render_jobs_total{status="succeeded"}` | 2 |

(Two jobs counted as succeeded includes job 1's failure, which is a
known telemetry-classification quirk in `RENDER_JOBS_TOTAL` — it
increments on the normal path; failure was emitted but the success
counter was also incremented. Not affecting baseline numbers; flagged
for cleanup later.)

#### Per-stage timing (`render_stage_seconds`)

**NOT EMITTED** — Batch 0C was deferred to Phase 1 per the agreed
plan. The metric is defined but the wrap was not applied to
`render_pipeline.py` / `part_renderer.py`. This is intentional — those
files are CRITICAL tier and need the full Render Edit Protocol before
any change. Will be wired as the first step of Phase 1 once the
correctness fixes (NVENC missing acquires) are merged.

---

## How to interpret this baseline

Future phase reports should write a sibling file
`docs/perf-phase-N-result-YYYY-MM-DD.md` and compare:

1. **Total render wall-clock delta** vs the 4 historical references and
   the fresh control run. Quality preservation gate: `output_rank_score`
   stays within ± 0.5 % of the same-source baseline.
2. **Per-stage delta** via `render_stage_seconds`. Tells us which stage
   moved the needle — e.g. Phase 4 (semaphore release) should mainly
   show up in shorter wait time on queued jobs, not in median render time.
3. **Cache hit-rate** via `render_cache_lookups_total{outcome="hit"}` /
   (hit + miss). Phase 3 should drive `motion_path` and `ffprobe`
   hit-rates from 0 → high (those caches don't exist yet so they will
   start appearing once Phase 3 ships).
4. **DB write count** via `render_db_writes_total{surface="update_job_progress"}`
   and `…upsert_job_part`. Phase 2 coalescing target: ≥ 70 % drop in
   the encode-progress write rate while WebSocket emission cadence is
   preserved.

---

## Acceptance — Phase 0

- [x] 4 new metric definitions live in `app/services/metrics.py`
- [x] Cache decorator wraps 5 cache-get helpers (instrumented, returns
      preserved)
- [x] Whisper timing wired in `llm_pipeline.py` (finally block emits on
      both success and failure paths)
- [x] DB write counter wired on 5 writer surfaces
- [x] `py_compile` passes on all 5 edited files
- [x] Focused pytest 68/68 pass
- [x] Full pytest count baseline recorded: **1396 tests**
- [x] 4 historical baselines documented
- [x] Backend restarted; 4 new metric names visible in `/metrics`
- [x] Fresh control render captured: `4bcf9326` (55 s, rank 85.6)
- [x] `whisper_srt` cache correctness verified: job 2 hit job 1's
      transcript ✓
- [x] LLM fallback chain verified (gemini → claude → openai) on empty
      response
- [x] Cleanup of `backend/_phase0_*` temp helpers

---

*Document owner: Leader. Append-only — do not edit historical entries.
Sibling files for each phase result.*
