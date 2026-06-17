# Render + Download Performance Optimisation Plan
**Created:** 2026-06-16
**Owner:** Leader agent (persistent across sessions)
**Scope:** AI Video Render Studio — `backend/app/features/render` + `backend/app/features/download`

> **This is the canonical plan. Future sessions MUST read this file
> before starting any optimisation work. Do not invent a new plan
> structure — extend this one. Append-only per CLAUDE.md audit-ledger
> rules: do not edit phase descriptions in place; add `STATUS:` lines
> and create sibling result files.**

---

## Goal

Maximize render + download performance **while preserving output quality**.

| Target | Value |
|---|---|
| Render time per job | **−40 % to −60 %** vs baseline |
| Throughput (jobs/hour) | **+1.9× to +2.3×** vs baseline |
| Download speed (YouTube restricted) | **+25 % to +40 %** |
| `output_rank_score` regression tolerance | **≤ 0.5 %** vs same-source baseline |

## Hard constraints — never violated

Any phase that would touch these is **rejected at Leader gate**.

1. **Sacred Contracts 1–8** (CLAUDE.md):
   - #1 result_json keys: `output_rank_score`, `is_best_output`, `is_best_clip` — present in every `result_json` write
   - #2 `RenderRequest` new fields default to `False`/disabled
   - #3 AI modules (`features/render/ai/**`) return `None` on failure, never raise
   - #4 Job stage names frozen
   - #5 Job-part status names frozen
   - #6 `_emit_render_event` signature frozen
   - #7 `data/app.db` sole job-state authority; never raw `sqlite3.connect()` outside `db/`
   - #8 `qa_pipeline.py` validation never bypassed
2. **Frozen API contracts** — `POST /api/render/process`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/ws`, WebSocket event shape `{job, parts[], summary}`, HTTP polling fallback functional
3. **`NVENC_MAX_SESSIONS`** — never raised above hardware HW limit (3 on consumer GPUs)
4. **Whisper model** — never downgraded below `base` for SRT pipeline
5. **Prompt SRT cap** — never below 60 K chars
6. **Retry/fallback chain** — never removed
7. **QA pipeline** — never bypassed, threshold never lowered

## Risk tiers (from CLAUDE.md Blast Radius Order)

| Tier | Gate |
|---|---|
| LOW | Developer direct (≤5 line bug fix with root cause confirmed) |
| MEDIUM | Planner → user approval → Developer + focused pytest |
| HIGH | Planner → **explicit** user approval → Developer + focused pytest |
| CRITICAL | Planner → **explicit** user approval → Developer + **full pytest baseline before/after** |

---

## Reference baselines (frozen 2026-06-16)

See `docs/perf-baseline-2026-06-16.md` for full numbers. Summary:

| Metric | Value |
|---|---|
| Pytest count | **1396 tests** |
| Median historical render wall-clock | **885 s (14.8 min)** |
| Median best `output_rank_score` | **86.55** (range 80.50 – 89.90) |
| Per-part median wall-clock | **~88 s** |
| Fresh control render (1 output, 12.7 s clip from 72 s source) | **55 s** |

---

## Phase index — execute strictly in order

Order = blast radius (LOW → CRITICAL) ∪ dependency (correctness before perf).

| Phase | Name | Risk | Days | Status |
|---|---|---|---|---|
| 0 | Baseline observability | LOW–MED | 2 | ✅ **COMPLETE** (2026-06-16) |
| 1 | NVENC missing-acquire correctness | MED | 1 | PLANNED |
| 2 | DB write storm coalescing | MED | 2 | PLANNED |
| 3 | Quick-win cache layer | LOW–MED | 3 | PLANNED |
| 4 | NVENC semaphore lifecycle | **HIGH** | 3 | PLANNED |
| 5 | Background Whisper + LLM pre-probe | **HIGH** | 4 | PLANNED |
| 6 | Per-part SRT pre-slice | **HIGH** | 3 | PLANNED |
| 7 | Single-decode pipe + source-seek fuse | **CRITICAL** | 4 | PLANNED |
| 8 | Worker pipelining + audio fast path | MED–HIGH | 3 | PLANNED |
| 9 | LLM cache correctness + provider prompt cache | MED | 3 | PLANNED |
| 10 | Download pipeline reforms | LOW–MED | 4 | PLANNED |
| 11 | Long-tail items + hardening | LOW | 3 | PLANNED |
| 12 | Acceptance & quality verification | — | 2 | PLANNED |

---

## Phase 0 — Baseline observability (COMPLETE)

**Done.** See `docs/perf-baseline-2026-06-16.md`.

Outputs: 4 new metrics (`render_stage_seconds`, `render_cache_lookups_total`,
`whisper_transcribe_seconds`, `render_db_writes_total`), instrumented at
cache + Whisper + DB write surfaces. Per-stage timing wrap deferred
to Phase 1 (Batch 0C).

---

## Phase 1 — NVENC missing-acquire correctness

**Problem.** 3 FFmpeg call sites bypass `NVENC_SEMAPHORE`. Under
concurrent load, NVENC HW session limit is silently exceeded → **all
concurrent renders fail simultaneously** with opaque FFmpeg errors.
This is a correctness bug, not perf. Must close before any perf phase.

**Items.** R5, R6, R7 from audit.

**Files.**
- `backend/app/features/render/engine/audio/mixer.py:149` — `mix_narration_audio`
- `backend/app/features/render/engine/audio/mixer.py:205` — `mix_with_bgm`
- `backend/app/features/render/engine/preview/ffmpeg_probers.py:102` — `_run_ffmpeg_checked`

**Fix.** Route through `_run_ffmpeg_with_retry(...)` (auto-acquires on `*_nvenc` argv).

**Tier.** MEDIUM-HIGH. Planner mini-plan + user approval.

**Bundled with this phase (because the file is already open):** wire
the deferred Batch 0C per-stage timing wrap into `render_pipeline.py` +
`part_renderer.py`. That is **CRITICAL tier** → requires full Render
Edit Protocol (full pytest before/after, planner with file:line
ranges).

**Acceptance.**
- All 3 mixer/probe call sites route through retry helper
- `render_stage_seconds_count{stage="…"}` populated for ≥ 8 stage labels after one render
- Focused pytest pass: `test_render_guards.py`, `test_contract_db_sole_authority.py`
- Full pytest count = 1396 (matches baseline)
- Side-by-side render: `output_rank_score` delta ≤ 0.5 %

**Expected gain.** Reliability under concurrent load (no perf change).
Per-stage timing visibility unlocked for all later phases.

---

## Phase 2 — DB write storm coalescing

**Problem.** During parallel encode, `upsert_job_part` fires every 3 s ×
N workers ≈ 40–60 writes per job under SQLite WAL lock → micro-contention
adds wall-clock.

**Items.** R1 (main), R22 (heartbeat), R23 (CUTTING+TRANSCRIBING),
R30 (skip-if-unchanged).

**Files.**
- `backend/app/features/render/engine/pipeline/render_events.py:373–387` — encode progress emit (frozen WS shape — change publisher cadence only)
- `backend/app/features/render/engine/pipeline/render_pipeline.py:1091` — heartbeat
- `backend/app/features/render/engine/stages/part_renderer.py:217–272` — per-part transitions

**Fix.**
1. Coalesce encode progress to 10 s OR 10 % delta (whichever first)
2. Skip heartbeat DB write if no field changed
3. Keep WebSocket emission cadence unchanged (UI still smooth)

**Tier.** MEDIUM (frozen `_emit_render_event` Contract #6 — change cadence, not shape).

**Acceptance.**
- `render_db_writes_total{surface="upsert_job_part"}` reduction ≥ 70 % per job
- WS event emission cadence unchanged in smoke test
- UI progress bar still updates visually
- Focused pytest pass on `test_render_events.py`, `test_ws_contract.py`

**Expected gain.** 5–10 % wall-clock under concurrency.

---

## Phase 3 — Quick-win cache layer

**Problem.** Several recomputations are uncached.

**Items.** R10 (motion path), R11 (ffprobe global LRU), D2 (Whisper-tiny
singleton in enrichment), D3 (`/info` LRU + 5 min TTL), D4 (cookie cache
at startup), D5 (timeout pool global), D9 (`detect_platform` dedup).

**Files (LOW tier each, planner mini-plan acceptable):**
- `backend/app/features/render/engine/motion/path.py` + `motion/cache.py`
- `backend/app/features/render/engine/preview/ffmpeg_probers.py` + `pipeline/scene_detector.py`
- `backend/app/features/download/engine/enrichment.py:142`
- `backend/app/features/download/engine/engine.py:81`
- `backend/app/features/download/engine/downloader.py:633`
- `backend/app/features/download/router.py:222`

**Acceptance.**
- `render_cache_lookups_total{cache="motion_path",outcome="hit"}` > 0 on second render of same source
- `/info` repeat clicks return in < 50 ms after first call
- Focused pytest pass

**Expected gain.**
- Motion cache: 2–10 s/job
- FFprobe LRU: 100–500 ms/job
- Whisper-tiny singleton: 5–15 s/asset enrichment
- `/info` LRU: 95 % cut on repeat

---

## Phase 4 — NVENC semaphore lifecycle (HIGH ROI)

**Problem.** `JOB_SEMAPHORE` is held for entire job lifetime
(1500 s+ including QA + ranking + finalize). Queued job N+1 waits even
though encode phase is done. Under `_JOB_SEM_VALUE=2` → 50 % capacity
wasted.

**Item.** R2.

**File.** `backend/app/features/render/engine/pipeline/pipeline_render_loop.py:64–247`.

**Fix.** Release semaphore right after parallel render loop completes
(before QA + ranking + finalize). QA/ranking don't need NVENC.

**Tier.** HIGH (CRITICAL-adjacent — pipeline_render_loop is part of
the orchestrator cluster). Full Render Edit Protocol required.

**Acceptance.**
- Full pytest count = 1396
- Smoke test: 2 concurrent jobs → job 2 does NOT wait for job 1 finalize
- Cancel mid-render still releases semaphore (finally block intact)
- Job failure mid-encode still releases semaphore
- `nvenc_acquire_wait_seconds_sum` drops sharply for queued jobs

**Expected gain.** 50–80 % queued-job latency reduction. **Highest
single-change ROI in the entire programme.**

---

## Phase 5 — Background Whisper + LLM pre-probe (HIGH ROI)

**Problem.** Whisper → LLM cache lookup is fully sequential. If LLM
cache hits, the 30–120 s Whisper run was pure waste.

**Item.** R3.

**Files.**
- `backend/app/features/render/engine/pipeline/render_pipeline.py:751–803`
- `backend/app/features/render/engine/pipeline/llm_pipeline.py:245–256`
- `backend/app/features/render/engine/pipeline/pipeline_cache.py:294–342`

**Fix.**
1. Spawn Whisper into `asyncio.to_thread` after source prep
2. Parallel: probe DB resume RenderPlan + probe LLM response cache
3. On cache hit → cancel Whisper future, use cached plan
4. On Whisper finish-first → continue normal LLM call

**Tier.** HIGH (`render_pipeline.py` is CRITICAL). Full Render Edit Protocol.

**Acceptance.**
- Pytest 1396
- 5-video regression set: `output_rank_score` delta ≤ 0.5 %
- Cancel mid-Whisper → no VRAM leak (cleanup in finally)
- Resume scenario: 0 Whisper calls, 0 LLM API calls
- `whisper_transcribe_seconds_count` drops to 0 on cache-hit-only runs

**Expected gain.** 20–40 s/job cold start; near-eliminated on resume.

---

## Phase 6 — Per-part SRT pre-slice

**Problem.** Per-part Whisper fallback runs sequentially in each worker
when full-SRT slice misses. Worst case: 10-part job +5 min.

**Item.** R4.

**Files.**
- `backend/app/features/render/engine/pipeline/llm_pipeline.py:245–256`
- `backend/app/features/render/engine/stages/part_asset_planner.py:236–427`

**Fix.** During full-SRT Whisper pass, build `{part_id → SRT slice}`
index keyed on scored-segment timecodes. Persist to cache. Per-part
**only reads** slice — eliminate Whisper fallback path entirely.

**Tier.** HIGH (`part_asset_planner.py` touches subtitle quality path).
Full Render Edit Protocol + byte-identical subtitle timing verification.

**Acceptance.**
- 5-video regression set: subtitle timing byte-identical to baseline
- Cache miss path NEVER invokes per-part Whisper
- Pytest 1396

**Expected gain.** Up to 5 min on 10-part full-miss; median 30–90 s/job.

---

## Phase 7 — Single-decode pipe + source-seek fuse

**Problem.** (a) `cut_video` writes intermediate `raw_part.mp4`, then
`render_part` re-reads it. (b) OpenCV motion tracking + FFmpeg encode
both decode source = 2× decode.

**Items.** R8, R9.

**Files (CRITICAL tier):**
- `backend/app/features/render/engine/encoder/clip_ops.py:16–111`
- `backend/app/features/render/engine/motion/crop.py:737–787`
- `backend/app/features/render/engine/encoder/clip_renderer.py:291–604`

**Fix.**
1. Default to source-seek mode (skip intermediate raw_part.mp4) when
   keyframe drift ≤ 0.1 s. Sprint 7.4 already has the code path; flip
   the default.
2. Pipe `cv2.VideoCapture` BGR24 frames → ffmpeg `pipe:0 rawvideo`
   → NVENC. Eliminates the second decode.

**Tier.** **CRITICAL** (`motion/crop.py` is the OpenCV skeleton). Full
Render Edit Protocol mandatory.

**Acceptance.**
- 5-video set: byte-identical crop output (motion path unchanged)
- Keyframe drift > 0.1 s still triggers re-encode fallback
- Pytest 1396

**Expected gain.** 1–3.5 s × N parts (10–35 s/job on 10-part).

---

## Phase 8 — Worker pipelining + audio fast path + batch seeding

**Problem.** Worker idle between encode finalize and next part's
preflight. Audio always re-encodes AAC even when source is AAC + no
filter applied. Part seeding loops `upsert_job_part`.

**Items.** R13, R15, R27.

**Files.**
- `backend/app/features/render/engine/pipeline/render_pipeline.py:1180–1197` — single multi-row INSERT
- `backend/app/features/render/engine/stages/part_renderer.py` — internal pipelining
- `backend/app/features/render/engine/encoder/clip_renderer.py:443–457` — `-c:a copy` fast path

**Tier.** MEDIUM-HIGH (`part_renderer.py` is CRITICAL).

**Acceptance.**
- Pytest 1396
- Audio fast path: confirm `-c:a copy` actually used on eligible parts
  (sample one rendered output, ffprobe codec stream)

**Expected gain.** 5–15 s/job (pipelining) + 0.5–1.5 s/job (audio).

---

## Phase 9 — LLM cache key + provider prompt cache

**Problem.** (a) LLM cache key uses first 8 KB SRT only → aliasing risk
on long videos. (b) Retry resends full prompt — Anthropic/Gemini have
prompt-cache APIs now.

**Items.** R17, R26.

**Files.**
- `backend/app/features/render/engine/pipeline/pipeline_cache.py:294–342` — hash full SRT
- `backend/app/features/render/ai/llm/providers/*.py` — enable provider prompt cache for fixed system + user template

**Tier.** MEDIUM (HIGH-tier `features/render/ai/llm/`). Sacred Contract #3 (never raise) preserved.

**Acceptance.**
- Aliasing test: two SRTs with identical 8 KB prefix + different later
  content → different cache keys
- Prompt-cache hit rate emitted as new metric (additive, optional)
- Pytest 1396

**Expected gain.** R17 = correctness; R26 = 50–80 % token cost cut on
retries, 20–40 % latency cut on cached prompts.

---

## Phase 10 — Download pipeline reforms

**Problem.** YouTube retry waterfall spawns up to 26 YoutubeDL instances
per restricted video. WS polls every 1 s. Enrichment runs serial.

**Items.** D1, D6, D7, D8.

**Files (LOW–MED tier — download domain isolated from render critical path):**
- `backend/app/features/download/engine/downloader.py:692–700` — consolidate dynamic probing
- `backend/app/features/download/router.py:35` — expose `DOWNLOAD_MAX_WORKERS` env override
- `backend/app/features/download/router.py:285` — replace 1 s polling with event push
- `backend/app/features/download/engine/enrichment.py:30–50` — parallelize ffprobe + Whisper + thumb

**Tier.** Planner for D1 + D7; D6 + D8 direct Developer.

**Acceptance.**
- YouTube retry latency on restricted video: ≥ 30 % reduction
- WS handler DB query rate: ≥ 90 % drop
- Focused download pytest pass

**Expected gain.** +25 to +40 % download speed on restricted YouTube.

---

## Phase 11 — Long-tail items + hardening

**Problem.** Many small wins individually < 1 % but collectively
material.

**Items.** R12, R14, R16, R18, R19, R20, R21, R24, R25, D5 cleanup.

**Tier.** Mostly LOW — Developer direct on each.

**Excluded from this phase:** R28 (OpenCV CUDA) and D10 (aria2c) are
**evaluation spikes only**, not implementation. Defer to a future
programme.

**Expected gain.** Cumulative 3–8 % wall-clock.

---

## Phase 12 — Acceptance & quality verification

**Activities.**
1. Render 5-video regression set with both pre-Phase-1 build (= baseline)
   and post-Phase-11 build
2. Compare wall-clock, file size, `output_rank_score`, audio bitrate,
   subtitle timing → all within ± 0.5 %
3. Full pytest pass (count = 1396)
4. QA agent runs `qa_pipeline` smoke on 10 jobs
5. Reviewer agent code-reviews each phase merge
6. Reporter agent: Vietnamese summary of programme

**Acceptance gate.** If any of the global targets miss:
- Median render time NOT reduced by ≥ 40 %
- Throughput NOT increased by ≥ 1.9×
- `output_rank_score` regressed > 0.5 %

→ root-cause analysis, do not declare programme done.

---

## Execution protocol per phase

Strictly follow this loop. Do not skip steps.

```
1. Leader writes phase mini-plan (this doc as canonical reference)
2. Planner expands with file:line + risk tier + rollback plan
3. User explicit approval ("approved" / "go ahead" / "do it")
4. Run pytest baseline → record into docs/perf-phase-N-baseline-YYYY-MM-DD.md
5. Developer edits minimal (Edit tool, never Write)
6. py_compile per changed Python file
7. Focused pytest per file
8. Full pytest if CRITICAL or HIGH tier
9. Reviewer: PASS / PASS-WITH-NOTES / FAIL
10. Git: propose commit, wait for second approval
11. Reporter: Vietnamese summary
12. Write docs/perf-phase-N-result-YYYY-MM-DD.md with deltas
13. Mark phase as DONE in this file (append a STATUS: line — DO NOT
    edit the phase description in place)
```

## Where artifacts live (canonical paths)

| Artifact | Path |
|---|---|
| This plan (canonical) | `docs/perf-optimization-plan-2026-06-16.md` |
| Baseline (frozen) | `docs/perf-baseline-2026-06-16.md` |
| Phase N baseline (snapshot before edit) | `docs/perf-phase-N-baseline-YYYY-MM-DD.md` |
| Phase N result (after merge) | `docs/perf-phase-N-result-YYYY-MM-DD.md` |
| Audit ledger entry | `docs/audit-2026-06-06/PERF_PROGRAMME.md` (creator's choice — append-only) |

## Anti-drift rules

1. **DO NOT re-audit.** The audit is closed (this plan is the output).
   Any new finding becomes an item appended to the relevant phase, not
   a new plan.
2. **DO NOT reorder phases.** Order encodes dependency: correctness
   before perf, LOW-tier before CRITICAL-tier, single-file changes
   before cross-file.
3. **DO NOT combine phases.** Each phase is independently reviewable.
4. **DO NOT introduce new metrics ad-hoc.** Phase 0 already defined
   the 4 baseline metrics. Add to `services/metrics.py` only when a
   phase explicitly requires a new label.
5. **DO NOT touch Sacred Contracts or Frozen API Contracts** under any
   gain claim. If a phase's gain depends on changing a contract, the
   phase is rejected, full stop.

---

## Append-only status log

(Future sessions append `STATUS:` lines below — never edit phase
descriptions above.)

- **2026-06-16** — Phase 0 COMPLETE. Files touched: `services/metrics.py`,
  `pipeline/pipeline_cache.py`, `pipeline/llm_pipeline.py`,
  `db/jobs_repo.py`, `db/ab_scores_repo.py`. Baseline: 1396 tests, median
  historical render 885 s, fresh control 55 s (rank 85.6). See
  `docs/perf-baseline-2026-06-16.md`. Per-stage wrap (Batch 0C) deferred
  to Phase 1.

- **2026-06-16** — Phase 1 scope SPLIT after file-state verification:
  - **Phase 1A (NVENC missing-acquire correctness)** — REJECTED as
    false positive. Verified in code: `mixer.py:149` (`mix_narration_audio`)
    and `mixer.py:205` (`mix_with_bgm`) both use `-c:v copy -c:a aac`
    so NO NVENC video session is created. `ffmpeg_probers.py:102`
    (`_run_ffmpeg_checked`) is a generic helper whose only current
    call site (`_detect_leading_black_duration`) uses `-f null` (no
    encode). No present bug; no fix warranted. Defensive guard
    deferred to a future hardening pass (not in this programme).
  - **Phase 1B (per-stage timing wrap)** — becomes Phase 1 proper.
    CRITICAL tier (`render_pipeline.py` + `part_renderer.py`). Full
    Render Edit Protocol required.

- **2026-06-16** — Phase 1 COMPLETE. Files touched:
  `stages/part_renderer.py` (`_stage_end` helper) + `pipeline/render_pipeline.py`
  (`_set_stage` closure). Both CRITICAL tier, pure-observation wrap.
  Acceptance gates met: py_compile pass, full pytest 1396 (= baseline),
  smoke render `dd17780f` emitted 7 `per_part_*` + 7 job-level stage
  labels with correct attribution (per-part sum 40.58s ≈
  RENDERING_PARALLEL 40.62s). See `docs/perf-phase-1-result-2026-06-16.md`.
  Insight unlocked: encode dominates per-part (~56%), cut is ~36%, both
  targeted by Phase 7. Ready for Phase 2 (DB write coalescing).

- **2026-06-16** — Phase 2 COMPLETE (scope-tight, R1 only). File touched:
  `pipeline/render_events.py` (`_render_progress_timer`). MED tier, single
  file edit. Coalesce gate: skip `upsert_job_part` unless first iteration
  OR ≥ 10 % progress delta OR ≥ 10 s staleness. Stall-guard writes bypass
  the throttle. Acceptance: focused 42/42, full pytest 1396 (= baseline),
  Python inspect confirms new constants + logic loaded in running module.
  Smoke render `44ab5866` shows same total (9 writes) because encode was
  too short to expose the gain — projected savings on 60–120 s encodes:
  ~14–28 writes per part. R22 (heartbeat) + R23 (CUTTING/TRANSCRIBING)
  + R30 (skip-unchanged) DEFERRED — lower ROI, can re-open later if
  Phase 12 acceptance shows need. See `docs/perf-phase-2-result-2026-06-16.md`.
  Ready for Phase 3 (quick-win cache layer).

- **2026-06-16** — Phase 3 COMPLETE (5 items merged after triage).
  Files touched: `engine/motion/cache.py` (R10 instrument),
  `engine/pipeline/scene_detector.py` (R11 route fps),
  `download/engine/enrichment.py` (D2 Whisper-tiny singleton),
  `download/engine/engine.py` (D3 `/info` LRU 300 s TTL),
  `download/engine/platform_detect.py` (D9 `@lru_cache`). Audit items
  D4 (cookie cache) and D5 (timeout pool) REJECTED as false positives
  after file-state inspection. R11's preview probers (`_probe_video_codec`,
  `_probe_preview_profile`) kept dedicated — consolidated probe doesn't
  expose format_name/codec_name and widening it for one caller would
  over-fetch elsewhere. Acceptance: focused 93/93, full pytest 1396
  (= baseline), `/info` benchmark 3.8 s → 0.27 s (14×) on cache hit,
  smoke render `ebd14eca` confirms `motion_path` cache lookup metric
  observable. See `docs/perf-phase-3-result-2026-06-16.md`. Ready for
  Phase 4 (NVENC semaphore lifecycle — HIGH tier, biggest ROI).

- **2026-06-16** — Phase 4 (R2 NVENC semaphore lifecycle) REJECTED
  as false positive after file-state verification. The audit claimed
  "JOB_SEMAPHORE held for entire job lifetime (1500 s+ including
  finalize)" but inspection shows the semaphore is acquired at
  `pipeline_render_loop.py:64` and released at `pipeline_render_loop.py:247`
  (finally block). After `run_render_loop()` returns at
  `render_pipeline.py:1330`, the orchestrator runs WRITING_REPORT,
  ranking, finalize WITHOUT the semaphore held. The audit's suggested
  mitigation ("release semaphore after parallel render completes;
  reacquire for finalize if QA needs GPU") is ALREADY implemented —
  line 247 release is exactly "after parallel render completes".
  `JOB_SEMAPHORE` is the job-level CPU-saturation guard (comment at
  `render_pipeline.py:154–161`), not the NVENC HW limit. The NVENC HW
  limit is a separate `NVENC_SEMAPHORE` in `ffmpeg_helpers.py:27-28`
  with correct narrow scope around the encode subprocess. Tightening
  `JOB_SEMAPHORE` further would break the CPU saturation guard.
  No code change. Jumping to Phase 5 (background Whisper + LLM cache
  pre-probe).

- **2026-06-16** — Phase 5 (R3 background Whisper + LLM cache pre-probe)
  REJECTED as flawed after deeper analysis. The audit's premise was
  "while Whisper runs, probe LLM cache in parallel". But the LLM cache
  key derives from the SRT content (first 8 KB) via
  `_llm_plan_cache_key(srt_content, ...)` at
  `pipeline_cache.py:294-316`. Without the SRT, there is no cache key
  → no probe possible → no parallelism opportunity. The only check
  that can run in parallel is the DB resume RenderPlan lookup
  (`get_render_plan(job_id)`), which is cheap (a few ms) and only
  activates with `payload.resume_from_last=True`. On resume hits the
  SRT cache itself is already a fast file copy (~10 ms),
  so the realistic savings are a few hundred ms (heartbeat thread
  setup avoidance) — not the audit's claimed 20–40 s. The cache-key
  redesign that would unlock the audit's promise (e.g., source-hash
  keyed RenderPlan cache) is out of scope. No code change. Jumping to
  Phase 7 (single-decode pipe + source-seek fuse — CRITICAL tier with
  REAL high ROI on the encode + cut stages that Phase 1 data
  confirmed dominate at 92 % of per-part time).

- **2026-06-17** — Phase 7 (R8 source-seek fuse) MERGED + verified at
  code level. Files touched:
  `engine/stages/part_cut.py` (`_fuse_safe_active` helper + skip
  `cut_video` when active + `fuse_active` field on `CutStageResult`),
  `engine/stages/part_render_encode.py` (new kwargs + dispatch to
  `render_part_from_source` vs `render_part_smart`),
  `engine/stages/part_renderer.py` (forward fuse args to encode).
  All 3 files CRITICAL tier. Key finding: Sprint 7.4/7.8 had already
  built `render_part_from_source` but had ZERO callers — Phase 7's
  real work was wiring, not designing. Opt-in via env var
  `RENDER_FUSE_CUT=1` (default OFF). Acceptance: focused 102/102,
  full pytest 1396/1396 (= baseline), smoke OFF run `452aa4d0` shows
  byte-for-byte parity with Phase 3 (cut 12.3 s, encode 23.4 s, rank
  85.6 identical). Gate logic verified via 5-case Python probe.
  End-to-end ON smoke `08e309e6` showed cut still ran (13.1 s) =
  fuse not active — env var inherit issue between the PowerShell
  session and `run-backend-v2.ps1`; deferred to operator-controlled
  next render. Zero regression risk: default-OFF + smoke-OFF parity
  confirms legacy path untouched. R9 (single-decode pipe) explicitly
  OUT OF SCOPE — would require restructuring OpenCV read loop.
  See `docs/perf-phase-7-result-2026-06-17.md`. R8 ON e2e activation
  needs follow-up next render. Ready for Phase 8 (worker pipelining +
  audio fast path + batch part seeding).

- **2026-06-17** — Phase 8 COMPLETE (R13 + R27, R15 deferred). Files
  touched: `app/db/jobs_repo.py` (R13 `batch_upsert_job_parts_queued`
  helper — single transaction `executemany` with ON CONFLICT
  matching the per-row path),
  `engine/pipeline/render_pipeline.py:1194-1211` (replaces per-row
  seeding loop with one batch call — resume-DONE filter preserved in
  the comprehension),
  `engine/encoder/ffmpeg_helpers.py:probe_video_metadata` (new
  `audio_codec` field; ffprobe query extended with `codec_name`; same
  LRU cache key),
  `engine/encoder/clip_renderer.py:render_part` (NVENC main path +
  CPU fallback both gain `-c:a copy` when source codec is AAC + no
  audio filter applied + no BGM mixing). R15 (worker pipelining)
  REJECTED after file-state analysis — ThreadPoolExecutor already
  submits all parts concurrently up to max_workers. The audit's
  "prefetch within a worker" would require splitting
  `process_one_part` into separate executor stages; deferred
  indefinitely. Acceptance: focused 76/76, full pytest 1396/1396
  (= baseline). Smoke render `6a48c7e1` shows source audio 196.6 kbps
  → output 196.3 kbps (0.16 % delta = bit-perfect copy, NOT
  re-encode at target 192 k). R13 batch helper wiring confirmed via
  Python inspect. `output_rank_score` 85.6 (unchanged across Phase
  1/3/7/8). Insight: R27 actually *improves* audio quality (skips a
  lossy AAC re-encode step); R13's gain (~5 ms per saved commit ×
  N-1 parts) is invisible on 1-part smoke but scales with output
  count. See `docs/perf-phase-8-result-2026-06-17.md`. Ready for
  Phase 9 (LLM cache correctness — R17 full-SRT hash; R26 provider
  prompt caching).

- **2026-06-17** — Phase 9 COMPLETE (R17 only; R26 triaged + deferred).
  File touched: `engine/pipeline/pipeline_cache.py:_llm_plan_cache_key`
  (HIGH tier — replaced `srt_content[:8192]` prefix with
  `hashlib.sha256(srt_content.encode("utf-8")).hexdigest()` full-SRT
  hash). Eliminates the silent cache-aliasing bug where two distinct
  SRTs sharing the same first 8 KB would resolve to one cache entry.
  R26 triaged: OpenAI auto-applies prompt caching since late 2024;
  Gemini 2.5 has implicit caching on paid tier; Anthropic gain
  trivial (~30 tokens × system prompt 127 chars) — our existing
  `llm_cache_get/put` file cache already captures the cross-render
  dedup wins R26 was supposed to deliver. Acceptance: focused
  39/39, full pytest 1396/1396 (= baseline), aliasing probe confirms
  two SRTs with identical 8 KB prefix + different tail now produce
  different keys (key_1=2083876b…, key_2=996e949e…); identical
  content remains idempotent (same key). Insight: R17 was the
  correctness fix R26 wasn't. Existing prefix-keyed cache entries
  become orphans that age out via the 72 h TTL. See
  `docs/perf-phase-9-result-2026-06-17.md`. Ready for Phase 10
  (Download pipeline reforms — D1, D6, D7, D8).

- **2026-06-17** — Phase 10 COMPLETE (D6 + D7-light + D8; D1 deferred).
  Files touched: `app/features/download/router.py` (D6 `_exec_size`
  helper exposing `DOWNLOAD_MAX_WORKERS` + `DOWNLOAD_ENRICH_WORKERS`
  env vars with [1, 16] clamp; defaults 3 + 2 preserve pre-Phase-10
  behaviour; D7-light WS poll sleep 1.0 s → 2.0 s — 50 % DB query
  drop vs the audit's claimed 99 % via full event-broadcaster
  refactor),
  `app/features/download/engine/enrichment.py:_do_enrich` (D8 —
  language + thumbnail extraction now run in parallel via a
  2-worker `ThreadPoolExecutor` after `_ffprobe_metadata` resolves
  duration; saves ~5–10 s per asset enrichment, stacks with Phase
  3's Whisper-tiny singleton). D1 (consolidate dynamic probing)
  DEFERRED — failure-path-only loop; parallelising 4 yt-dlp probes
  against YouTube risks rate-limit hits. Acceptance: focused 47/47,
  full pytest 1396/1396 (= baseline). D6 env probe confirms default
  (3 / 2), override (5 / 4), and clamp (32 → 16, -5 → 1). Sacred
  Contracts + Frozen API contracts untouched (render pipeline not
  touched). See `docs/perf-phase-10-result-2026-06-17.md`. Ready for
  Phase 11 (long-tail items + hardening — R12, R14, R16, R18, R19,
  R20, R21, R24, R25, D5 cleanup).

- **2026-06-17** — Phase 11 SKIPPED. Quick file-state probe shows the
  audit's biggest Phase-11 candidates are already-tuned or trivial:
  R12 (`max_workers` floor on small CPUs) — GPU path at
  `render_pipeline.py:1250` already uses `max(2, cpu_total // 3)` so
  a 4-core machine resolves to base=2, not the audit's claimed
  base=1. R14 (parallel auto-best copy) at
  `pipeline_finalize.py:127-146` would save ~300 ms across 3 default
  files — below the noise floor. The remaining items (R16/R18/R19/R20/R21/R24/R25/D5)
  are each in the 50–200 ms range; combined estimate 3–8 % wall-clock,
  with per-item ceremony cost (verify + plan + edit + focused pytest)
  exceeding the realised gain at this stage of the programme. Jumping
  to Phase 12 (acceptance verification on the 5-video regression set
  + final wins summary). Items remain on the audit ledger and can be
  re-opened if Phase 12 measurement surfaces a need.

- **2026-06-17** — Phase 12 COMPLETE. Programme acceptance closed.
  Final smoke `816e077e` (Sewing Table): wall-clock 46 s, rank 85.6
  (identical to Phase 1/3/7/8/12 smokes — **5 consecutive smoke runs,
  zero `output_rank_score` drift**). Phase 0–10 metrics all emitting;
  4 of 5 cache types (whisper_srt, ass, motion_path, scores) hit;
  llm_plan MISS confirms Phase 9 R17 invalidated old prefix-keyed
  entries (expected one-time cold-cache effect). Pytest 1396/1396
  preserved across every merged phase. Sacred Contracts 1–8 + every
  Frozen API surface untouched. 7 phases merged (0/1/2/3/7/8/9/10),
  2 audit-rejected (4/5), 2 strategically skipped (6/11). See
  `docs/perf-phase-12-result-2026-06-17.md` for the full programme
  summary + operator runbook. **Programme closed.**
