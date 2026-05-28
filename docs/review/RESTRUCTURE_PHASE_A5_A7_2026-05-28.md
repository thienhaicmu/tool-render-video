# Backend Restructure — Phase A (A-5 through A-7)

**Date:** 2026-05-28  
**Branch:** `restructure/output-timeline-architecture`  
**Baseline tests:** 7549 passed, 2 skipped (held through A-7)  
**Prior doc:** `RESTRUCTURE_PHASE_A_2026-05-28.md` (A-1..A-4)

---

## What Was Done

### Phase A-5 — Remove inner stub functions (LOW risk)

After A-3 extracted `_prepare_part_assets` and `_process_one_part` via Early Return Delegation,
the original function bodies in `render_pipeline.py` became 10-line and 5-line stubs that only
delegated to the extracted versions. A-5 removed these stubs entirely.

**Changes:**
- Removed `_prepare_part_assets` stub (previously lines 2174–2186)
- Removed `_process_one_part` stub (previously lines 2188–2189)
- Sequential loop call: `_process_one_part(idx, seg)` → `process_one_part(_part_ctx, idx, seg)`
- Parallel submit: `executor.submit(_process_one_part, idx, seg)` → `executor.submit(process_one_part, _part_ctx, idx, seg)`
- Cleaned import: removed `prepare_part_assets, process_one_part as _process_one_part_extracted`; kept only `PartRenderContext`

---

### Phase A-6 — Extract pre-render stages → `pipeline_pre_render.py` (MEDIUM risk)

Extracted original lines 739–1388 of `run_render_pipeline()` into a standalone function
`run_pre_render_scenes()` in `backend/app/orchestration/pipeline_pre_render.py`.

**What the extracted block contained:**
- Phase 45 early full-video transcription (Whisper, optional)
- Scene detection (`detect_scenes`)
- Segment building (`build_segments_from_scenes`)
- Scene scoring (`score_scenes_clip`)
- Viral scoring (`score_segments`)
- High-motion segment filtering (`HIGH_MOTION_MIN_SCORE`, `HIGH_MOTION_MIN_KEEP`)
- Segment variant building (`_build_variant_segments`)
- Visual analysis (`VisualAnalysisResult` population)
- Content analysis AI Director pre-phases
- Platform resolution and DNA visual flag

**Extraction strategy — true extraction (not Early Return Delegation):**  
The block was sequential top-level code inside `run_render_pipeline()`, not an inner closure.
A PowerShell script replaced lines 739–1388 with the `run_pre_render_scenes()` call block.
All local variables defined in the block that are used after it were identified and returned
via `PreRenderScenesResult` (11 fields).

**`PreRenderScenesResult` fields returned:**
- `full_srt`, `full_srt_available` — SRT path and availability flag
- `early_transcription_done` — whether Phase 45 Whisper already ran
- `scored`, `total_parts` — segment list and count
- `content_analysis`, `target_platform` — AI Director inputs
- `dna_clean_visual` — DNA visual flag
- `early_retrieved_knowledge` — knowledge retrieval results
- `seg_min_sec`, `seg_max_sec` — segment duration bounds

**`payload` mutation note:** `payload.sub_font_size` is mutated inside `run_pre_render_scenes()`.
Since `payload` is passed by object reference, this mutation is visible to the caller after return.
This preserves existing behavior — no behavior change.

**New file:** `backend/app/orchestration/pipeline_pre_render.py` (746 lines)

**Cleaned up from `render_pipeline.py`:**
- Removed imports: `detect_scenes`, `build_segments_from_scenes`, `score_scenes_clip`, `CLIP_SCORER_VERSION`, `score_segments`, `VisualAnalysisResult`
- Removed constants: `HIGH_MOTION_MIN_SCORE = 60`, `HIGH_MOTION_MIN_KEEP = 3`
- Kept: `refine_segment_boundaries`, `refine_cuts_for_naturalness` (still used in post-segmentation S4.x block), `apply_retention_proxy` (still used in S4.2 block)
- Added import: `from app.orchestration.pipeline_pre_render import run_pre_render_scenes`

---

### Phase A-7 — Extract render loop → `pipeline_render_loop.py` (MEDIUM risk)

Extracted the `JOB_SEMAPHORE.acquire()` block (sequential/parallel FFmpeg encode loop)
from `run_render_pipeline()` into `run_render_loop()` in
`backend/app/orchestration/pipeline_render_loop.py`.

**What the extracted block contained:**
- `JOB_SEMAPHORE.acquire()` / `.release()` (via try/finally)
- `_render_active_count` contention tracking + worker throttling
- `resolve_ffmpeg_threads()` and `part_ctx.ffmpeg_threads` finalization
- Sequential single-worker render loop (`max_workers == 1`)
- Parallel `ThreadPoolExecutor` render loop (`max_workers > 1`)
- Per-part failure handling (`_render_part_failure_detail`, `upsert_job_part`)
- `_emit_render_event` calls for part progress
- Cancellation checks at every part boundary

**Key design decisions:**

1. **`PartRenderContext` constructed before semaphore with `ffmpeg_threads=1` placeholder.**  
   `ffmpeg_threads` depends on the contention-based throttle that happens inside the semaphore.
   Constructing `_part_ctx` before `acquire()` avoids a 214-field constructor inside the
   semaphore section. `run_render_loop()` overwrites `part_ctx.ffmpeg_threads` after throttle.

2. **Semaphore and locks passed as parameters.**  
   `JOB_SEMAPHORE`, `_render_active_lock`, `_render_active_count` are module-level in
   `render_pipeline.py`. Importing them from `pipeline_render_loop.py` would create a circular
   import. Passing them as parameters avoids the circular dependency.

3. **`set_stage_fn` callback.**  
   `_set_stage` is a closure in `run_render_pipeline()` that uses `nonlocal current_stage,
   current_progress`. Passed as a `Callable` to `run_render_loop()`. Since Python closures
   capture variables by reference, calls from inside `run_render_loop()` update the outer
   scope variables correctly.

4. **`RenderLoopResult` dataclass.**  
   Returns `outputs: list`, `rows: list`, `failed_parts: list` — the three mutable lists
   populated during the render loop.

**Circular import avoidance:**
`pipeline_render_loop.py` imports from `qa_pipeline`, `render_events`, `stages.part_renderer`,
`cancel_registry`, `services.db`, and `services.render_engine` — none of which import from
`render_pipeline.py`. No circular dependency introduced.

**New file:** `backend/app/orchestration/pipeline_render_loop.py` (250 lines)

---

## Size Reduction Summary (A-1 through A-7)

| File | Before A-1 | After A-7 |
|------|-----------|----------|
| `render_pipeline.py` | 5,816 lines | **2,158 lines** |
| Reduction | — | **−3,658 lines (−63%)** |
| New: `pipeline_helpers.py` | — | 544 lines |
| New: `pipeline_ai_phases.py` | — | 519 lines |
| New: `stages/part_renderer.py` | — | 2,089 lines |
| New: `pipeline_render_loop.py` | — | 250 lines |
| New: `pipeline_pre_render.py` | — | 746 lines |

Total code in the orchestration layer: unchanged. Logic redistributed into smaller, focused modules.

Target from A-5..A-7 plan was 800–1,000 lines. Achieved 2,158 lines — larger than target because
the S4.x refinement block (refine_segment_boundaries, apply_retention_proxy, refine_cuts_for_naturalness),
AI Director phases, subtitle/voice preparation, and post-loop result assembly remain in
`run_render_pipeline()` and were not part of the A-6 extraction range.

---

## Frozen Contracts — Status Through A-7

All frozen contracts remain intact:

| Contract | Status |
|----------|--------|
| Stage names: `QUEUED → DOWNLOADING → RENDERING → DONE` | ✅ Unchanged |
| Part names: `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE` | ✅ Unchanged |
| `_emit_render_event` signature and call sites | ✅ Unchanged |
| `result_json` aliases: `output_rank_score`, `is_best_output`, `is_best_clip` | ✅ Unchanged |
| WebSocket event shape: `job`, `parts[]`, `summary` | ✅ Unchanged |
| REST route paths | ✅ Unchanged |
| `RenderRequest` field defaults | ✅ Unchanged |

---

## Test Results

All phases maintained the test baseline:

| Phase | Result |
|-------|--------|
| A-1..A-4 baseline | 7549 passed, 2 skipped |
| After A-5 | 7549 passed, 2 skipped |
| After A-6 | 7549 passed, 2 skipped |
| After A-7 | 7549 passed, 2 skipped |
