# Backend Restructure — Phase A (A-1 through A-4)

**Date:** 2026-05-28  
**Branch:** `restructure/output-timeline-architecture`  
**Baseline tests:** 7549 passed, 2 skipped (established before A-1, held through A-4)

---

## Motivation

`render_pipeline.py` was a 5,816-line monolith containing every render stage, inner closure,
dataclass, helper, and result-write in a single file. The CLAUDE.md blast-radius section
classified it as CRITICAL tier and required full pytest + explicit user approval for any change.

This made even small fixes risky. The refactor goal: decompose without changing observable
behavior, preserving all frozen contracts (stage names, WS event shape, result_json aliases).

---

## What Was Done

### Phase A-1 — `pipeline_helpers.py` (prior session)

Extracted: `_select_cover_frame_time`, `_select_cta_text`, `_append_cta_block_to_srt`,
`_get_effective_playback_speed`, `_read_srt_meta`, `_build_variant_segments`,
`_aspect_play_res_y`, `_apply_subtitle_edits_to_srt`, `_PLATFORM_PROFILES`, and related
constants into `backend/app/orchestration/pipeline_helpers.py` (544 lines).

### Phase A-2 — `pipeline_ai_phases.py` (prior session)

Extracted: AI Director invocation, timing mutations, emphasis config, visual intensity,
cover hint resolution into `backend/app/orchestration/pipeline_ai_phases.py` (519 lines).

### Phase A-3 — `stages/part_renderer.py` (this session)

Extracted the two largest inner closures of `run_render_pipeline()`:

- `_prepare_part_assets` (~649 lines): subtitle slicing, ASS conversion, hook formatting,
  text-layer assembly → `prepare_part_assets(ctx, ...)`
- `_process_one_part` (~1,374 lines): cut, transcribe, render, voice, micro-pacing,
  validation, scoring, cover extraction → `process_one_part(ctx, ...)`

**Strategy used — Early Return Delegation:**  
Instead of deleting 2,025 lines of function body (impossible to match in Edit tool),
inserted a single `return extracted_fn(ctx, ...)` as the first line of each inner function.
Old bodies became unreachable dead code — safe to remove after tests confirmed green.

**PartRenderContext dataclass (39 fields):**  
Carries all closure-captured state (job_id, payload, paths, flags, mutable shared lists).
Shared mutable lists (`_voice_mix_ok`, `_recovery_notes`, etc.) are passed by reference —
same list object, no data loss for pre-context and post-context writes.

New file: `backend/app/orchestration/stages/part_renderer.py` (2,089 lines)  
New file: `backend/app/orchestration/stages/__init__.py` (empty package marker)

### Phase A-4 — Dead code removal + test fixes (this session)

Removed the 2,011 lines of unreachable dead code from `render_pipeline.py`:
- Lines 2187–2823 (dead body of `_prepare_part_assets`, 637 lines)
- Lines 2827–4200 (dead body of `_process_one_part`, 1,374 lines)

Done via Python script (Edit tool cannot match 2,000-line blocks).

**Test fixes:**  
2 source-inspection tests in `test_phase0_hotfixes.py` used `inspect.getsource(render_pipeline)`
to assert that `SUBTITLE_PER_PART_MODEL` and `playback_speed=_get_effective_playback_speed`
appear in the file. After extraction, these strings moved to `part_renderer.py`.
Fix: updated both assertions to check `getsource(render_pipeline) + getsource(part_renderer)`.
Behavior unchanged — the code still runs correctly, only the source location changed.

---

## Size Reduction

| File | Before | After |
|------|--------|-------|
| `render_pipeline.py` | 5,816 lines | **2,959 lines** |
| Reduction | — | **−2,857 lines (−49%)** |
| New: `pipeline_helpers.py` | — | 544 lines |
| New: `pipeline_ai_phases.py` | — | 519 lines |
| New: `stages/part_renderer.py` | — | 2,089 lines |

Total code in the orchestration layer: unchanged. Just moved into smaller, focused modules.

---

## Frozen Contracts — Status

All frozen contracts remain intact through A-1..A-4:

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

## Known Preserved Bug

`srt_path` at line 4097 of the original `_process_one_part` was an undefined variable
(NameError silently caught by `except Exception: pass`). This bug is preserved verbatim
in `part_renderer.py` at the corresponding line in `process_one_part()`. It is annotated
with a `# noqa: F821` comment. Do not fix it without a dedicated investigation — it is
inside a `try/except` that already handles it safely.

---

## Next Plan (A-5 through A-7)

### A-5 — Remove inner stub functions (LOW risk, ~15 lines)

`_prepare_part_assets` and `_process_one_part` in `render_pipeline.py` are now 10-line and
5-line stubs that only delegate. They can be deleted. The 2–4 call sites inside
`run_render_pipeline()` (sequential loop line ~4298, parallel submit line ~4349) must be
updated to call `process_one_part(_part_ctx, idx, seg)` directly.

**Risk:** LOW — pure call-site update, no logic change. Focused pytest recommended.

### A-6 — Extract pre-render stages → `pipeline_pre_render.py` (MEDIUM risk, ~600–800 lines)

The outer `run_render_pipeline()` still contains a large block of pre-render logic:
- Scene detection (`detect_scenes`)
- Segment generation and scoring (`build_segments_from_scenes`, `score_scenes_clip`)
- Full-video transcription (Whisper, optional early transcription)
- AI Director invocation (already partially extracted in A-2, but some wiring remains)
- Voice TTS preparation (manual voice mode)

These could move to `pipeline_pre_render.py` and be called via a structured result dataclass.

**Risk:** MEDIUM — many closure variables, requires Planner + focused pytest. Do not start
without an approved per-line change list.

### A-7 — Extract render loop → `pipeline_render_loop.py` (MEDIUM risk, ~300–400 lines)

The ThreadPoolExecutor loop, sequential fallback, part failure handling, and result collection
(currently in `run_render_pipeline()` after the `JOB_SEMAPHORE.acquire()` block) could move
to a dedicated module. `_part_ctx` is already the right abstraction for the worker inputs.

**Risk:** MEDIUM — touches the concurrency model. Requires Planner + full pytest baseline.

### Target state after A-5..A-7

`render_pipeline.py` at approximately **800–1,000 lines** — pure orchestration: setup,
pre-render call, loop call, result assembly. All heavy logic in dedicated modules.
