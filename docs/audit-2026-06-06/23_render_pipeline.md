# 23 — Render Pipeline Reference

Rebuilt from code on 2026-06-06. Deep trace in [07_workflow_render.md](07_workflow_render.md).

## Entry

[features/render/engine/pipeline/render_pipeline.py:299](../../backend/app/features/render/engine/pipeline/render_pipeline.py) `run_render_pipeline(job_id, payload, resume_mode, *, load_session_fn, cleanup_session_fn)`.

## Phases

```
1. setup_render_pipeline()                pipeline_setup.py
2. prepare_render_source()                pipeline_source_prep.py
3. run_manual_voice_tts() (opt)           pipeline_narration.py
4. run_llm_pre_render() (mandatory)       llm_pipeline.py        ── Whisper + LLM
5. select_render_plan() (opt, default ON) llm_stage.py
6. subtitle gating
7. run_render_loop()                      pipeline_render_loop.py
     for each scored seg:
       part_renderer.process_one_part()
         ├─ part_asset_planner            stages/part_asset_planner.py
         ├─ part_cut                      stages/part_cut.py
         ├─ part_render_setup             stages/part_render_setup.py
         ├─ part_render_encode            stages/part_render_encode.py
         ├─ part_voice_mix                stages/part_voice_mix.py
         ├─ part_render_finalize          stages/part_render_finalize.py  (Sacred #8 surface)
         └─ part_done                     stages/part_done.py
8. attach_ai_visibility_summaries()       ai/visibility/...
9. run_render_finalize()                  pipeline_finalize.py
```

## Frozen state transitions

- Job: `QUEUED → DOWNLOADING → RENDERING → DONE` (+ `FAILED`, `CANCELLED`).
- Per-part: `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE` (+ `FAILED`, `SKIPPED`).

Enforced by convention only; no SQL `CHECK` (Phase 4 BR05).

## Feature flags

All env-read at module load ([render_pipeline.py:109-161](../../backend/app/features/render/engine/pipeline/render_pipeline.py)):

| Flag | Default | What it does when ON |
|---|---|---|
| `FEATURE_BASE_CLIP_FIRST` | 0 | render `base_clip.mp4` as parallel artifact before overlay composite |
| `FEATURE_OVERLAY_AFTER_BASE_CLIP` | 0 | composite subtitle overlays onto `base_clip.mp4` |
| `FEATURE_RAW_PART_SKIP` | 0 | fuse cut+render with input-side `-ss/-t` seek (Sprint 7.4) |
| `FEATURE_RAW_PART_SKIP_MOTION_AWARE` | 0 | extend fused path to motion-crop case (Sprint 7.8) |
| `LLM_EMIT_RENDER_PLAN` | **1** | LLM Call 2 emits full RenderPlan (Sprint 7.6a flip) |

4 OFF + 1 ON → 32 combinations; tested combinations limited (Phase 9 §3).

## FFmpeg layer

[features/render/engine/encoder/ffmpeg_helpers.py](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py) — `_run_ffmpeg_with_retry(cmd, retry_count, wait_sec, *, nvenc_externally_held)`.

- Retry attempts 1..retry_count+1.
- `time.sleep(wait_sec * attempt)` between attempts.
- Deadline `now + _FFMPEG_TIMEOUT_SEC` (default 3600 s).
- Cancel poll every 1.0 s, terminate child on flag.
- Metrics: `FFMPEG_DURATION`, `FFMPEG_INVOCATIONS_TOTAL`, `NVENC_ACQUIRE_WAIT`, `NVENC_ACTIVE_SESSIONS`.

`NVENC_SEMAPHORE = threading.Semaphore(_NVENC_SEM_VALUE)` at line 27-28. Default 3, override via `NVENC_MAX_SESSIONS`. Acquired at:

- `clip_renderer.py:98` (render_base_clip when NVENC)
- inside `render_part_smart` motion-crop branch
- `overlay_compositor.py:133`

**Open gap:** other FFmpeg call sites (`clip_ops.cut_video`, `mixer.mix_narration_audio`, `motion`, `preview/ffmpeg_probers`) don't consult the semaphore. If any of them passes `*_nvenc` argv, the hardware limit can be silently breached and all NVENC sessions fail together (Phase 2 R01 / Phase 4 BR04).

## QA gate (Sacred Contract #8)

[features/render/engine/pipeline/qa_pipeline.py:64](../../backend/app/features/render/engine/pipeline/qa_pipeline.py) `_validate_render_output(output_path, expected_duration, expect_audio)`:

| Check | Failure code |
|---|---|
| file exists | RN001 |
| size ≥ 10 KB | RN002 |
| `ffprobe -print_format json` parses | RN003 |
| has video stream | RN004 |
| duration > 0 | RN005 |
| `|duration_actual − expected|` ≤ tolerance | RN006 |

Tolerance: `max(0.5, min(expected * 0.15, 3.0))` seconds. Returns dict; never raises at the QA layer. Caller (`part_render_finalize`) raises `RuntimeError` on `ok=False`.

## Sacred Contract #6 — WS event shape

[features/render/engine/pipeline/render_events.py:102](../../backend/app/features/render/engine/pipeline/render_events.py) defines `_emit_render_event` with kw-only signature. All 22+ call sites comply. Events go to **per-job log file** (`data/logs/job-{id}/`), NOT to the WS frame. The FE-visible WS stream is built independently by [routes/jobs.py:644-696](../../backend/app/routes/jobs.py) polling the DB at 500 ms and emitting `{job, parts, summary}` on fingerprint change.

## Resume

[features/render/router.py](../../backend/app/features/render/router.py): `POST /api/render/resume/{job_id}` reuses the job_id, reloads `payload_json`, sets `resume_from_last=True`. Parts already with an `output_file` are skipped; downloaded source files are reused.

## Cancel

`cancel_registry.register(job_id)` returns a `threading.Event`. The pipeline polls at safe checkpoints. FFmpeg child is `.terminate()`-ed when cancel triggers between subprocess polls.

## Output

Per job: outputs go to `payload.output_dir` (validated by router). Per part: `final_part.mp4` (with subtitles, narration, overlays). Auto-best-export (`payload.auto_best_export_enabled`) copies top-N to `output_dir/best/`.

`result.json` is written in `output_dir`. `jobs.result_json` column is updated by `pipeline_finalize`.

End of 23_render_pipeline.md.
