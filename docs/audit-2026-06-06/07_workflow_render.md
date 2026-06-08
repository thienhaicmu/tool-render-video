# 07 — Render Pipeline Workflow

Deep technical trace of how a single render job executes. Source-of-truth: `backend/app/features/render/engine/`.

> Companion docs: [05_workflow_system.md](05_workflow_system.md) (top-level sequence) and [06_workflow_ai.md](06_workflow_ai.md) (AI phase detail). This doc focuses on the render engine itself.

---

## 1. Job entry

[backend/app/features/render/engine/pipeline/render_pipeline.py:299](../../backend/app/features/render/engine/pipeline/render_pipeline.py) — `run_render_pipeline(job_id, payload, resume_mode, *, load_session_fn, cleanup_session_fn)`.

Stage emissions (frozen `JobStage` enum):

| Stage | Line | Phase |
|---|---|---|
| `STARTING` | 329 | initial |
| `DOWNLOADING` | (via `_set_stage`) — `pipeline_source_prep.py:96` | source prep |
| `TRANSCRIBING_FULL` | 740 | when add_subtitle |
| `SCENE_DETECTION` | ~850 | pre-render-loop |
| `RENDERING_PARALLEL` / `RENDERING` | `pipeline_render_loop.py:87` | per-part loop |
| `FINALIZING` (via `_set_stage`) | ~1043 | pre-finalize |
| `WRITING_REPORT` | ~1043 | report assembly |
| `DONE` | `pipeline_finalize.py` terminal | success |
| `FAILED` | 1336 | exception path |
| `CANCELLED` | router-level finally | cancelled-by-user |

Stage closure: `_set_stage(stage, progress, message)` is declared at line 332 and mutates a `current_stage` local; each call writes `update_job_progress` + emits `_emit_render_event`. The outer try/except at 1277 catches everything except `JobCancelledError` (handled in router.py finally).

---

## 2. Source preparation

[pipeline_source_prep.py:65](../../backend/app/features/render/engine/pipeline/pipeline_source_prep.py) — `prepare_render_source`.

Two branches:

| Branch | Trigger | Behavior |
|---|---|---|
| Editor session | `payload.edit_session_id` resolves via `load_session_fn` | validates session video exists, builds source dict (title/slug/duration via `_probe_video_duration`), emits `render.prepare_source.select_strategy` |
| Local file | `payload.source_mode == "local"` | resolves local `source_path`, emits prepare-paths event |

YouTube/URL ingest was retired in Phase 4F.5A — local-only now.

If `trim_in/trim_out/volume` are set, an FFmpeg subprocess applies trim/volume to a derived file and `source_path` is rewritten to point at it.

Output dataclass: `SourcePrepResult` ([line 56](../../backend/app/features/render/engine/pipeline/pipeline_source_prep.py)) — `source, source_path, edit_session_id, detected_source_mode, output_stem`.

---

## 3. Transcription & scene analysis

[parallel_analysis.py:56](../../backend/app/features/render/engine/pipeline/parallel_analysis.py) — `run_parallel_analysis` runs Whisper + PySceneDetect on dedicated threads to save wall-clock.

Whisper:
- Adapter: [engine/subtitle/transcription/whisper.py:26-32](../../backend/app/features/render/engine/subtitle/transcription/whisper.py) — `get_whisper_model` loads via `whisper.load_model(model_name, download_root=…)`. Default model `base` (overridable env `LLM_WHISPER_MODEL`).
- Cache dir: `data/whisper_cache` ([whisper.py:22-23](../../backend/app/features/render/engine/subtitle/transcription/whisper.py)).
- Per-model `threading.Lock` to serialize concurrent transcribe calls on the same model.
- Audio extraction: `ffmpeg -i src -vn -ac 1 -ar 16000 …` → temp 16 kHz mono WAV.

Scene detection: [engine/pipeline/scene_detector.py](../../backend/app/features/render/engine/pipeline/scene_detector.py) — PySceneDetect content-detector (verify in code; CLAUDE.md does not document).

Caches (all 72 h TTL, all at `APP_DATA_DIR/cache/`):

| Surface | Key | Location |
|---|---|---|
| Transcription | `(path, mtime, size, model, lang, suffix)` | `cache/transcription/{key}.srt` |
| Scene detect | `(path, mtime, size)` | `cache/scene_detect/{key}.json` |
| Motion path | `_motion_cache_key()` | `cache/motion_paths/` |
| ASS content | SHA-256 of 13 inputs | `cache/ass/` |

ASS content cache is Sprint 7.3 (content-addressable; the keyed hash is the SHA-256 of `srt_bytes + writer + style + scale_y + font + size + margin + play_res + x_percent + highlight_per_word + colors + outline`).

---

## 4. Segment selection (post-LLM) & ranking

[pipeline_segment_selection.py](../../backend/app/features/render/engine/pipeline/pipeline_segment_selection.py) and [pipeline_ranking.py](../../backend/app/features/render/engine/pipeline/pipeline_ranking.py).

Inputs from LLM: `scored: list[dict]` with `{start, end, duration, viral_score, hook_score, retention_score, motion_score, speech_density_score, market_score, …}`.

Ranking weights ([pipeline_ranking.py:113](../../backend/app/features/render/engine/pipeline/pipeline_ranking.py) — `_RANKING_WEIGHTS`):

```
segment_viral_score   0.35
hook_score            0.20
retention_score       0.20
speech_density_score  0.10
market_score          0.10
duration_fit_score    0.05
```

Adaptive normalization at line 11 keeps the sum at 1.0 even when some scores are missing.

Output keys (Sacred Contract #1):
- `output_rank_score` — weighted sum (lines 230)
- `is_best_output` — top-N flag (line 237)
- `is_best_clip` — per-variant best (line 238)

When `LLM_EMIT_RENDER_PLAN=1` and a valid permutation of `clips[i].rank` (1..N, no gaps) exists, that permutation drives output order ([pipeline_ranking.py:313-334](../../backend/app/features/render/engine/pipeline/pipeline_ranking.py)). Otherwise fallback to score-descending.

---

## 5. Per-part render loop

[pipeline_render_loop.py:43](../../backend/app/features/render/engine/pipeline/pipeline_render_loop.py) — `run_render_loop(part_ctx, scored, source, total_parts, max_workers, …)`:

- `JOB_SEMAPHORE.acquire()` (line 64) caps simultaneous renders.
- Reads `_render_slot`; when more than one job is rendering concurrently, decrements `max_workers` ([line 70](../../backend/app/features/render/engine/pipeline/pipeline_render_loop.py)).
- Emits stage `RENDERING_PARALLEL` if max_workers > 1, else `RENDERING` (lines 87-91).
- For each seg: `_run_part(part_ctx, idx, seg)` → `stages/part_renderer.py:91 process_one_part`.
- Parallel path uses `ThreadPoolExecutor(max_workers=…)` + `as_completed`; sequential path is a plain loop.
- Failed parts go to `failed_parts`; loop continues — partial-success is the supported model.
- Cancel signal polled via `ctx.cancel_registry.is_cancelled(job_id)` ([part_renderer.py:142](../../backend/app/features/render/engine/stages/part_renderer.py)).

---

## 6. Per-part stage chain

[stages/part_renderer.py:91](../../backend/app/features/render/engine/stages/part_renderer.py) `process_one_part(ctx, idx, seg)` calls (in order):

### 6.1 part_asset_planner

`prepare_part_assets` — builds per-part SRT slice from full_srt; runs translation if enabled; converts SRT→ASS (with ASS cache); selects camera strategy (zoom/pan/hold/mosaic) from RenderPlan if present.

### 6.2 part_cut

[stages/part_cut.py:95](../../backend/app/features/render/engine/stages/part_cut.py) — `run_cut_stage`:

- Detects silence-trim offset (`detect_silence_trim_offset`), bad first frame (`detect_bad_first_frame`) via [encoder/clip_ops.py](../../backend/app/features/render/engine/encoder/clip_ops.py).
- Applies AI timing mutations if enabled (tighten_setup, shorten_outro).
- Writes TimelineMap + BaseClipManifest snapshot.
- **Upserts** `JobPartStage.CUTTING` (Sacred Contract #5).
- `cut_video()` ([clip_ops.py:16](../../backend/app/features/render/engine/encoder/clip_ops.py)):
  - **Stream-copy fast path** (lines 46-80): `-ss start -t duration -c copy -avoid_negative_ts make_zero`.
  - Fallback re-encode (lines 91-100): `-c:v libx264 -preset fast -crf 18` on keyframe drift or `force_accurate_cut`.

**Sprint 7.8 motion-aware skip:** when `_FEATURE_RAW_PART_SKIP=1` AND `_FEATURE_RAW_PART_SKIP_MOTION_AWARE=1` AND `payload.motion_aware_crop`, `_should_skip_raw_part_write` returns True and the cut+motion-crop is fused into `render_part_from_source` (input-side `-ss/-t` seek directly into the encode).

### 6.3 part_render_setup

[stages/part_render_setup.py](../../backend/app/features/render/engine/stages/part_render_setup.py) — `run_render_preflight`:

- Resolves codec/preset/CRF.
- Finalizes `ffmpeg_threads` based on concurrent contention.
- Spawns the progress-timer daemon ([render_events.py:174](../../backend/app/features/render/engine/pipeline/render_events.py) `_render_progress_timer`) — wakes every 3 s, writes `progress = 70 + 30 * (elapsed / expected_duration)`, clamps at 99 % so the final terminal write wins.
- Builds MotionCropConfig when `payload.motion_aware_crop`.
- Returns `RenderPreflightResult(encode_stop: threading.Event, encode_timer: Thread, plan, …)`.

### 6.4 part_render_encode

[stages/part_render_encode.py:1](../../backend/app/features/render/engine/stages/part_render_encode.py) — `run_render_encode`:

Three dispatch paths:

1. **Base-clip path** (`_FEATURE_BASE_CLIP_FIRST=1` AND overlay/validation consumer active):
   - `render_base_clip()` ([encoder/clip_renderer.py:40+](../../backend/app/features/render/engine/encoder/clip_renderer.py)) — produces `base_clip.mp4` with metadata.
   - When `motion_aware_crop=True`, calls `render_motion_aware_crop()` ([motion/crop.py:100+](../../backend/app/features/render/engine/motion/crop.py)).
   - `NVENC_SEMAPHORE.acquire()` at clip_renderer.py:98 when NVENC codec.

2. **Overlay composite** (`_FEATURE_OVERLAY_AFTER_BASE_CLIP=1` and base_clip produced):
   - Slices output-timeline SRT, generates per-output ASS.
   - `composite_overlays_on_base_clip()` ([overlay_compositor.py](../../backend/app/features/render/engine/encoder/overlay_compositor.py)) — semaphore-protected at line 133.

3. **Default `render_part_smart()`** (full single-pass encode with subtitles+overlays+effects+motion-crop).

The `finally` block: `preflight.encode_stop.set()` ; `encode_timer.join(timeout=5.0)`.

### 6.5 part_voice_mix

[stages/part_voice_mix.py](../../backend/app/features/render/engine/stages/part_voice_mix.py):

- TTS narration text source: subtitle text OR translated subtitle text.
- Backend: edge-tts (asyncio, [audio/tts.py:8](../../backend/app/features/render/engine/audio/tts.py)) by default; XTTS ([audio/tts_xtts.py](../../backend/app/features/render/engine/audio/tts_xtts.py)) when `payload.tts_engine == "xtts"`.
- Voice-rate nudges per `content_type` (commentary +10 %, tutorial −8 %, montage +12 %, …).
- Humanization: `humanize_narration_text` inserts breaths/pauses ([tts.py:57](../../backend/app/features/render/engine/audio/tts.py)).
- `mix_narration_audio` ([audio/mixer.py:40](../../backend/app/features/render/engine/audio/mixer.py)) — supports `replace_original`, `duck`, `overlay`, `sidechain`. Applies `atempo` for `playback_speed != 1.0`.
- Atomic file swap: mixed output overwrites final_part.

### 6.6 part_render_finalize

[stages/part_render_finalize.py](../../backend/app/features/render/engine/stages/part_render_finalize.py):

- **Sacred Contract #8 surface** — calls `_validate_render_output` ([qa_pipeline.py:64](../../backend/app/features/render/engine/pipeline/qa_pipeline.py), see §11).
- Selects cover frame + thumbnail.
- Upserts `JobPartStage.DONE`.
- Returns `RenderOutputResult(output_file, metadata)`.

### 6.7 part_done

Cleanup + emit final per-part event.

---

## 7. FFmpeg invocations

[engine/encoder/ffmpeg_helpers.py:186](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py) — `_run_ffmpeg_with_retry(command, retry_count, wait_sec, *, nvenc_externally_held=False)`.

Distinct command shapes:

| Operation | Module | Codec | Notes |
|---|---|---|---|
| cut (stream-copy) | clip_ops.py | `-c copy` | no NVENC |
| cut (accurate) | clip_ops.py | `libx264 -preset fast -crf 18` | no NVENC |
| encode part | clip_renderer.py | `h264_nvenc / hevc_nvenc / libx264` | semaphore |
| overlay composite | overlay_compositor.py | `h264_nvenc` | semaphore |
| audio mix | audio/mixer.py | `aac/copy` | no NVENC |
| concat | (FFmpeg concat demuxer) | `-c copy` | no NVENC |

`NVENC_SEMAPHORE = threading.Semaphore(_NVENC_SEM_VALUE)` at [ffmpeg_helpers.py:27-28](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py). Default 3, override via `NVENC_MAX_SESSIONS`. Acquired at:
- clip_renderer.py:98 (`render_base_clip` when NVENC)
- inside `render_part_smart` (motion-crop branch)
- inside `composite_overlays_on_base_clip` (overlay_compositor.py:133)

Retry/timeout logic:
- Loop attempts 1..retry_count+1; on `CalledProcessError`, `time.sleep(wait_sec * attempt)`.
- Deadline: `now + _FFMPEG_TIMEOUT_SEC` (default 3600 — env-tunable).
- Cancel poll every 1.0 s ([line 253](../../backend/app/features/render/engine/encoder/ffmpeg_helpers.py)) — terminates child on flag.

Metrics (Prometheus): `FFMPEG_DURATION`, `FFMPEG_INVOCATIONS_TOTAL`, `NVENC_ACQUIRE_WAIT`, `NVENC_ACTIVE_SESSIONS`.

**FINDING-R01 (HIGH — repeat of CLAUDE.md Audit 2026-06-02 §NVENC gap):** The semaphore is only acquired at the three sites above. Other modules that *might* invoke an NVENC codec do not consult it — namely `engine/encoder/clip_ops.py` (cut), `engine/audio/mixer.py` (mix), `engine/preview/ffmpeg_probers.py`, `engine/motion/*` calls. If any path passes `*_nvenc` argv without holding the semaphore, NVENC's hardware limit triggers a *whole-cluster* failure (all active NVENC sessions fail). The right fix is to centralize acquire/release inside `_run_ffmpeg_with_retry` conditioned on `_argv_uses_nvenc(command)`. Open issue.

---

## 8. Motion crop

[engine/motion/crop.py:69](../../backend/app/features/render/engine/motion/crop.py) — `build_subject_path(video_path, crop_w, crop_h, cfg: MotionCropConfig, _scene_ranges, content_type)`.

CapCut-style auto-reframe algorithm:

1. Every `cfg.subject_detect_interval` frames: face → body detection via MediaPipe ([motion/detection.py:62-66](../../backend/app/features/render/engine/motion/detection.py)).
2. Between detections: CSRT tracker + `ByteTrackSubject` (velocity-predicted IoU gate) — [motion/tracker.py](../../backend/app/features/render/engine/motion/tracker.py).
3. Raw (cx, cy) → Gaussian smoothing ([motion/utils.py](../../backend/app/features/render/engine/motion/utils.py)) → velocity-limited.
4. Fallback `_build_motion_path_legacy()` in [motion/pixel_diff.py](../../backend/app/features/render/engine/motion/pixel_diff.py) when no subject ever found AND `cfg.motion_fallback=True`.

Multi-scene dispatch (`_scene_ranges` has 2+ ranges): per-range `build_subject_path_scene` carries last visible crop center across boundaries.

Path applied as `-vf "crop=…"` in the FFmpeg filter chain during encode. Hybrid (path computed Python-side; ffmpeg applies it).

Motion path cache: 72 h TTL ([motion/cache.py](../../backend/app/features/render/engine/motion/cache.py)).

---

## 9. Subtitle pipeline

[engine/subtitle/](../../backend/app/features/render/engine/subtitle/):

| Layer | Files | Notes |
|---|---|---|
| Transcription | `transcription/whisper.py`, `transcription/adapters.py` | per-model lock, cache 72 h |
| Generator | `generator/{ass,srt,timeline}.py` | `srt_to_ass_bounce` styled SRT→ASS |
| Processing | `processing/{styles,readability,market_policy,text_transforms}.py` | font sizing, line-break optimization, locale rules (CJK spacing, RTL), emoji handling |
| Translation | `translation_service.py` | invoked when `payload.subtitle_target_language != original` |

ASS style selection driven by `content_type + variant_type` (viral / clean / gaming / story). Font + position scaled per `play_res_y` (helper at [pipeline_subtitle_utils.py](../../backend/app/features/render/engine/pipeline/pipeline_subtitle_utils.py)).

---

## 10. Audio

[engine/audio/](../../backend/app/features/render/engine/audio/):

- `tts.py` — edge-tts (async, ~50 ms/word, 100+ langs).
- `tts_xtts.py` — XTTS (slower, higher quality, voice cloning if sample provided).
- `mixer.py` — see §6.5.
- `audio_cleanup.py` / `cleanup_adapters.py` — spectral subtraction or RNNoise denoise, silence trim, level normalize before mix.
- `profiles.py` — voice profiles per content_type (rate/pitch).

---

## 11. QA gate (Sacred Contract #8)

[engine/pipeline/qa_pipeline.py:64](../../backend/app/features/render/engine/pipeline/qa_pipeline.py) — `_validate_render_output(output_path, expected_duration, expect_audio)`.

Checks in order:

| Check | Line | Failure code |
|---|---|---|
| file exists | 89 | RN001 |
| size ≥ 10 KB | 98 | RN002 |
| `ffprobe -print_format json` parses | 104-121 | RN003 |
| has video stream | 138 | RN004 |
| duration > 0 | 147-150 | RN005 |
| duration within tolerance | 152-160 | RN006 |

Duration tolerance: `max(0.5, min(expected_duration * 0.15, 3.0))` ([qa_pipeline.py:40-42](../../backend/app/features/render/engine/pipeline/qa_pipeline.py)).

Returns `{ok, warnings, error, code, phase, metadata}`. **Never raises** at the QA layer. Caller (part_finalize) raises a `RuntimeError` on `ok=False` → part marked `FAILED`, added to `failed_parts`.

---

## 12. Finalize

[engine/pipeline/pipeline_finalize.py:76](../../backend/app/features/render/engine/pipeline/pipeline_finalize.py) — `run_render_finalize(ctx)`:

- Aggregates per-part results into `result_json` (`outputs[]`, rank entries).
- Copies Sacred Contract #1 keys through unchanged (`output_rank_score`, `is_best_output`, `is_best_clip`).
- Writes `{output_dir}/result.json`.
- P5-2 Auto Best Export: when `payload.auto_best_export_enabled`, copies top-N ranked outputs to `{output_dir}/best/`.
- Terminal status: `completed` (no failed parts) or `completed_with_errors` (some failed).
- DB-WRITE `upsert_job(status=…, result_json=…)`.
- Optional db_backup snapshot.

---

## 13. Caching surfaces (recap)

| Cache | Path | TTL | Win |
|---|---|---|---|
| Transcription | `cache/transcription/{key}.srt` | 72 h | 30–90 s |
| Scene detect | `cache/scene_detect/{key}.json` | 72 h | 2–15 s |
| Motion path | `cache/motion_paths/` | 72 h | 5–60 s |
| ASS content | `cache/ass/` (SHA-256) | n/a (content-addressable) | 5–20 ms |

Pruner: `prune_render_cache` ([services/maintenance.py:76-122](../../backend/app/services/maintenance.py)) runs at startup and every 1800 s.

---

## 14. Feature flags (env-gated, all default OFF except #5)

| Flag | Env | render_pipeline.py | Default | Alt path |
|---|---|---|---|---|
| `_FEATURE_BASE_CLIP_FIRST` | `FEATURE_BASE_CLIP_FIRST` | line 109 | 0 | parallel base_clip.mp4 before overlay composite |
| `_FEATURE_OVERLAY_AFTER_BASE_CLIP` | `FEATURE_OVERLAY_AFTER_BASE_CLIP` | line 114 | 0 | composite subtitle overlays onto base_clip.mp4 |
| `_FEATURE_RAW_PART_SKIP` | `FEATURE_RAW_PART_SKIP` | line 123 | 0 | fused cut+render (Sprint 7.4) |
| `_FEATURE_RAW_PART_SKIP_MOTION_AWARE` | `FEATURE_RAW_PART_SKIP_MOTION_AWARE` | line 132 | 0 | extends fused path to motion-crop (Sprint 7.8) |
| `_FEATURE_LLM_EMIT_RENDER_PLAN` | `LLM_EMIT_RENDER_PLAN` | line 161 | **1** | RenderPlan emission (Sprint 7.6a flip) |

Sprint 7.2 (2026-06-05) removed `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` — `base_clip.mp4` now only written when an overlay consumer is active (line 140-142 comment).

**FINDING-R02 (MED):** Four `_FEATURE_*` flags in the render path, all defaulting OFF. Test matrix is 2^4 = 16 combinations. Existing tests likely cover the OFF baseline + the targeted feature path per sprint — but cross-combinations (e.g., `RAW_PART_SKIP=1` AND `BASE_CLIP_FIRST=1` simultaneously) are untested by name. Phase 9 will audit explicitly.

---

## 15. Sacred Contract #6 — `_emit_render_event` signature

[engine/pipeline/render_events.py:102](../../backend/app/features/render/engine/pipeline/render_events.py):

```python
def _emit_render_event(
    *,
    channel_code: str,
    job_id: str,
    event: str,
    level: str,
    message: str,
    step: str,
    context: dict | None = None,
    exception: Exception | None = None,
    traceback_text: str = "",
    duration_ms: int | None = None,
    error_code: str = "",
):
```

All 22+ call sites in `render_pipeline.py` + extracted stages use **keyword-only** invocation. ✓ Signature frozen.

**FINDING-R03 (LOW):** Verified per Phase 1 already — but worth restating: events emitted here go to per-job log files, **not** to the WebSocket frame. The FE never sees them. Phase 5 should propose either piping a subset onto the WS or accepting the current log-only model and documenting it.

---

## 16. Stage names (Sacred Contracts #4 + #5)

| Level | Frozen states |
|---|---|
| Job | `QUEUED → DOWNLOADING → RENDERING → DONE`, terminals `FAILED` / `CANCELLED` |
| Part | `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE`, terminals `FAILED` / `SKIPPED` |

Phase 1 already noted these are plain strings — no enum enforcement (FINDING-D02). Phase 8 will recommend.

---

## 17. Cross-references

- DB writes per step: [05_workflow_system.md §DB writes timeline](05_workflow_system.md)
- AI sub-phases: [06_workflow_ai.md](06_workflow_ai.md)
- Sacred Contract #1 keys: see [03_database_inventory.md §H](03_database_inventory.md)

End of 07_workflow_render.md.
