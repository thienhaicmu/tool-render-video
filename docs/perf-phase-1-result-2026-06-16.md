# Phase 1 — Result (2026-06-16)

> Completes Phase 1 of the perf optimisation programme. Compare against
> `docs/perf-phase-1-baseline-2026-06-16.md`. All acceptance gates met.

## Outcome

**PASS.** Pure-observation wrap of stage transitions in
`render_pipeline.py` (`_set_stage` closure) and `part_renderer.py`
(`_stage_end` helper) emits the `render_stage_seconds{stage}` histogram
defined in Phase 0. Zero state-machine / return-value / WS shape /
DB write changes. Pytest count unchanged (1396).

## Edits made

| File | Lines touched | Tier | Edit summary |
|---|---|---|---|
| `app/features/render/engine/stages/part_renderer.py` | 47–58 (+1 import) | CRITICAL | `_stage_end()` now also calls `RENDER_STAGE_DURATION.labels(stage=f"per_part_{name}").observe(elapsed)` wrapped in try/except. |
| `app/features/render/engine/pipeline/render_pipeline.py` | 37 (+1 import), 477–492 (closure body) | CRITICAL | Added `_stage_t0` tracker; `_set_stage` observes the **outgoing** stage's elapsed time on every transition, wrapped in try/except. |

## Verification

### Pre-edit baseline (recap from `perf-phase-1-baseline-...md`)
- Full pytest: **1396** collected
- Focused (13 suites): **154/154 pass**

### Post-edit
- py_compile both files: **OK**
- **Full pytest: 1396 passed in 61.05 s** — exact match to baseline ✓
- Unit verify of `_stage_end`: emits `per_part_cut` and `per_part_encode`
  observations with correct elapsed time ✓
- End-to-end smoke render (job `dd17780f`, Sewing Table source, 1
  output, 12.7 s clip): **completed** ✓

### Smoke render — `/metrics` snapshot

#### Per-part stage labels — **7 / 7 expected** ✓

| Stage | Count | Sum (s) | Notes |
|---|---|---|---|
| `per_part_cut` | 1 | 14.71 | Cutting raw source segment |
| `per_part_assets` | 1 | 0.05 | ASS cache hit → fast |
| `per_part_preflight` | 1 | 0.005 | Encoding param resolution |
| `per_part_encode` | 1 | **22.90** | Dominant cost — FFmpeg + NVENC encode |
| `per_part_voice_mix` | 1 | 0.0002 | Voice disabled → no-op |
| `per_part_finalize` | 1 | 1.52 | Micro-pacing + QA validation |
| `per_part_done` | 1 | 1.39 | Terminal cleanup + DB DONE write |

**Per-part total:** 40.58 s. This matches the job-level
`JobStage.RENDERING_PARALLEL` sum (40.62 s) — confirming the wrap
correctly attributes work to the right scope.

#### Job-level stage labels — 7 emitted

| Stage | Count | Sum (s) |
|---|---|---|
| `JobStage.STARTING` | 1 | 0.03 |
| `JobStage.DOWNLOADING` | 1 | 1.57 |
| `JobStage.ANALYZING` | 1 | 0.01 |
| `JobStage.TRANSCRIBING_FULL` | 2 | 1.05 (cache hit) |
| `JobStage.SCENE_DETECTION` | 1 | 0.01 |
| `JobStage.SEGMENT_BUILDING` | 1 | 0.26 |
| `JobStage.RENDERING_PARALLEL` | 1 | **40.62** |

**Cosmetic note:** job-level stage labels render as
`JobStage.STARTING` etc. (Python enum's `str()` repr) rather than
the plain string values. Stable + filterable, but not pretty. Polish
to plain lowercase is a low-risk future cleanup — not blocking
because Phase 4 / WS frozen names are NOT the same surface (these
are dashboard labels, not the WS event `step` field).

### Acceptance checklist

- [x] py_compile passes on both files
- [x] Full pytest count = 1396 (= baseline)
- [x] Focused pytest 154/154 pass (= baseline)
- [x] Smoke render `/metrics` shows ≥ 7 `per_part_*` labels (got **7**)
- [x] Smoke render `/metrics` shows ≥ 4 job-level stage labels (got **7**)
- [x] `output_rank_score` unchanged — no rank delta possible (pure observation)
- [x] WS event shape unchanged (frozen Contract #6)
- [x] DB writes unchanged (frozen Contract #7)
- [x] No new Sacred Contract violations

## Insight unlocked for later phases

The Phase 1 data already exposes optimisation hooks Phases 4–7 will exploit:

1. **Encode dominates per-part cost** (~56 % of part time in this
   sample). Phase 7 (single-decode pipe + source-seek fuse) directly
   targets this stage.
2. **Cut is large** (~36 % per-part). Phase 7's source-seek fuse also
   targets this — `cut_video` writes raw_part.mp4 then `render_part`
   re-reads it.
3. **Assets / preflight / voice_mix are sub-100 ms** on cache-hit path
   — Phase 6 (per-part SRT pre-slice) is most valuable on **miss** path,
   where Assets goes from 0.05 s → 10–30 s.
4. **Transcribing_full was 1.05 s** despite Whisper not running (cache
   hit). That's the cache lookup + DB heartbeat overhead — Phase 5
   (background Whisper + LLM pre-probe) eliminates this on resume.
5. **Rendering_parallel = 40.6 s** with only 1 part → Phase 4
   (semaphore release after render loop) lets a queued job start at
   ~40 s instead of waiting through finalize.

## Rollback path (not needed)

`git checkout backend/app/features/render/engine/stages/part_renderer.py
backend/app/features/render/engine/pipeline/render_pipeline.py` —
2-file revert, no dependents.

## Time spent

- Mini-plan + file verification: ~10 min
- Pytest baseline (incl. focused): ~2 min
- Edits + py_compile: ~3 min
- Full pytest: ~1 min
- 2× backend restart waits + smoke render: ~5 min
- Result doc: ~5 min

**Total: ~25 min** (well under the 1 hour budget).
