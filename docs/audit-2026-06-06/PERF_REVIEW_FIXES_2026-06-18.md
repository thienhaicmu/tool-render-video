# Perf-Review Fixes — 2026-06-18

> **Append-only audit record.** New file (does not edit any prior audit
> document). Closes 10 findings raised by a high-recall code review of
> commit `4a47ea2b` ("perf(render+download): 12-phase optimisation
> programme"). Baseline pytest before edits: **1396 passed**. After edits
> + new regression tests: **1401 passed, 0 failed.**

## Context

A `/code-review high` pass over `4a47ea2b` (19 backend files, ~1245 LOC of
code change) surfaced 2 correctness regressions, 1 thread-safety race, 3
behaviour changes, and 4 cleanup items. All were fixed in a single
session under the Render Edit Protocol (full pytest baseline → minimal
edits → full pytest verify). No Sacred Contract or frozen API surface was
touched. Fuse-path and audio-copy changes preserve `qa_pipeline.py`
(Contract #8) and the WS event shape (Contract #6).

## Findings & closures

### F1 (CORRECTNESS) — `batch_upsert_job_parts_queued` crashed on `None` scores
- **File:** `backend/app/db/jobs_repo.py`
- **Defect:** The R13 batch seeder coerced scores with `float(r.get("viral_score", 0))`
  — no `or 0` guard. A reachable `None` score (the codebase guards these
  with `float(... or 0)` everywhere, e.g. `pipeline_segment_selection.py`)
  raised `TypeError` outside any try/except, aborting *all* part seeding
  and failing the job at SEGMENT_BUILDING. The pre-R13 per-row
  `upsert_job_part` bound the value raw (`None` → SQL NULL, tolerated).
- **Fix:** Added `or 0` / `or 0.0` / `or ""` guards to all coerced fields
  so the batch path is as tolerant as the per-row path it replaced.
- **Test:** `test_batch_upsert_tolerates_none_scores`,
  `test_batch_upsert_empty_rows_short_circuits`.

### F2 (CORRECTNESS) — high-frame-rate sources mis-scaled scene timestamps
- **File:** `backend/app/features/render/engine/encoder/ffmpeg_helpers.py`
  (root) + `pipeline/scene_detector.py` (consumer)
- **Defect:** R11 routed `_get_video_fps` through `probe_video_metadata`,
  which clamped fps to `[1.0, 120.0]` (else `0.0`). A 144/240fps source
  reported `0.0` → `scene_detector` fell back to `30.0` → `_transnetv2_detect`
  converted scene-cut frame indices as `frame/30` instead of `frame/144`,
  off by ~4.8×. The old direct `r_frame_rate` parse returned the true fps.
- **Fix:** Raised the probe clamp upper bound `120.0 → 240.0` (fixes the
  root for all callers). `scene_detector` already accepted `[1.0, 240.0]`.
- **Test:** `test_probe_reports_true_hfr_fps[144/240/60]`.

### F3 (THREAD-SAFETY) — shared Whisper-tiny model raced under concurrency
- **File:** `backend/app/features/download/engine/enrichment.py`
- **Defect:** The D2 singleton `_TINY_MODEL` is reused across the 2-worker
  (env-raisable) `_ENRICH_EXECUTOR`. Concurrent `model.transcribe()` calls
  on one torch nn.Module are not thread-safe (shared buffers / CUDA
  context) → silently wrong/empty language under load. The pre-change
  per-call `load_model` isolated each transcription.
- **Fix:** Added `_TINY_INFER_LOCK` serialising `transcribe()`. Keeps the
  load-time saving; inference is one-at-a-time across assets.

### F5 + F9 (ENCODE BEHAVIOUR / CLEANUP) — audio-copy fast path
- **File:** `backend/app/features/render/engine/encoder/clip_renderer.py`
- **Defect:** R27's `-c:a copy` branch had no `-shortest`, so a copied
  audio track longer than the (re-encoded) video could extend the output
  and desync. The gate was also duplicated across the NVENC and
  CPU-recovery paths in two divergent shapes (incl. a dead
  `else_branch_no_af` flag set then filtered out).
- **Fix:** Extracted one `_audio_copy_safe(input_path, bgm_ok,
  input_has_audio, af)` helper shared by both paths; added `-shortest` to
  both copy branches; removed the `else_branch_no_af` bookkeeping.
  Bit-identical pass-through (the perf intent) is unchanged for the safe
  case. CRITICAL-tier file — verified with full pytest.

### F4 (BEHAVIOUR, env-gated) — fuse path silently dropped `tracker_hint`
- **File:** `backend/app/features/render/engine/stages/part_cut.py`
- **Defect:** `render_part_from_source` (the `RENDER_FUSE_CUT=1` path) has
  no `crop_cfg_override` parameter, so an AI-selected subject tracker was
  silently replaced by the default tracker in fuse mode. Cut runs before
  preflight, so the gate must read the plan, not preflight.
- **Fix (Option A — conservative):** `_fuse_safe_active` now returns
  `False` whenever `ctx.render_plan.camera_strategy.tracker` is set, so a
  named tracker keeps the correct legacy cut+render path. Fuse is opt-in
  (default off); cost is only a missed optimisation in that case.

### F6 (BEHAVIOUR) — progress-write coalescing reduced polling fidelity
- **File:** `backend/app/features/render/engine/pipeline/render_events.py`
- **Defect:** R1 throttled per-part DB writes to ≥10% delta or ≥10s,
  leaving `GET /api/jobs/{id}` (the offline-first polling fallback) stale
  up to 10s on a slowly-advancing part.
- **Fix:** Tightened to 5s / 5% — better polling fidelity while still
  coalescing the bulk of per-tick writes. Final 100% still guaranteed by
  `part_done.py`; stall-guard writes still bypass the throttle.

### F7 (EFFICIENCY) — `get_video_info` cache: no single-flight + early timestamp
- **File:** `backend/app/features/download/engine/engine.py`
- **Defect:** The D3 cache released its lock during the 1–2s yt-dlp probe,
  so concurrent first-time requests for the same URL all probed in
  parallel (the exact cost the cache targets). The TTL timestamp was also
  captured *before* the probe, ageing each entry by the probe duration.
- **Fix:** Added a per-URL single-flight lock (`_info_url_lock`, bounded
  map) so concurrent same-URL probes run yt-dlp once; extracted the probe
  into `_probe_video_info`; the cache timestamp is now captured *after* the
  probe. Different URLs still probe in parallel.

### F8 (REUSE) — duplicated `_instrument_cache` decorator
- **Files:** `backend/app/services/metrics.py` (new home) +
  `pipeline/pipeline_cache.py`, `motion/cache.py` (consumers)
- **Defect:** Two byte-identical 18-line decorators, drift risk.
- **Fix:** Single `instrument_cache` definition in `services/metrics.py`;
  both cache modules `import ... as _instrument_cache`. Call sites
  unchanged.

### F10 (EFFICIENCY) — per-asset `ThreadPoolExecutor`
- **File:** `backend/app/features/download/engine/enrichment.py`
- **Defect:** `_do_enrich` created and tore down a fresh 2-thread pool per
  asset (nested inside the module-level enrich executor).
- **Fix:** Reused a module-level `_ENRICH_PAR_POOL` (threads spawned lazily)
  for the language‖thumbnail fan-out.

## Verification

- Baseline (pre-edit) full pytest: **1396 passed**.
- Post-edit full pytest at three checkpoints (after Phase 1, after the
  CRITICAL clip_renderer change, final): **no regression**.
- New regression suite `tests/test_perf_fixes_2026_06_18.py` (5 tests,
  all green) locks F1 and F2 — both would fail against the pre-fix code.
- Final: **1401 passed, 0 failed.**

## Files touched

```
backend/app/db/jobs_repo.py
backend/app/features/download/engine/engine.py
backend/app/features/download/engine/enrichment.py
backend/app/features/render/engine/encoder/clip_renderer.py
backend/app/features/render/engine/encoder/ffmpeg_helpers.py
backend/app/features/render/engine/motion/cache.py
backend/app/features/render/engine/pipeline/pipeline_cache.py
backend/app/features/render/engine/pipeline/render_events.py
backend/app/features/render/engine/stages/part_cut.py
backend/app/services/metrics.py
backend/tests/test_perf_fixes_2026_06_18.py   (new)
```
