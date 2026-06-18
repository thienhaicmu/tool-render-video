# Render path hang-point audit — 2026-06-18

> Append-only record. Follow-up to DB_BACKUP_WORKER_HANG_FIX. Swept the render
> engine for blocking primitives (`.result()`, `.join()`, `.wait()`,
> `.communicate()`, `subprocess.run`, semaphore `.acquire()`) to confirm no
> unbounded call can hang the render worker (and pin its job slot / NVENC permit).

## Already bounded (verified — no change)

- **Main FFmpeg encode** (`ffmpeg_helpers._run_ffmpeg_with_retry`): runs
  `communicate()` in a daemon thread and polls `_done.wait(1.0)` against a
  `_FFMPEG_TIMEOUT_SEC` (default 3600s) deadline + cancel_event, then
  terminate→kill. Bounded.
- **part_cut silence / first-frame scans** (`clip_ops.detect_silence_trim_offset`
  timeout=20, `detect_bad_first_frame` timeout=15): the `.result()` calls in
  `part_cut.py` are transitively bounded by these subprocess timeouts.
- **parallel_analysis** (scene-detect + transcription): `as_completed(timeout=…)`;
  the workers are compute-bound (TransNetV2 / Whisper / cv2 / timeout-bounded
  ffprobe), not unbounded subprocesses, so the pool-exit `shutdown(wait=True)`
  completes. Low risk — left as-is.
- **pipeline_render_loop** parallel branch: `future.result()` is called inside
  `as_completed`, i.e. on already-finished futures — never blocks.
- **DeepFilterNet cleanup** (`audio/cleanup_adapters._run_command`): wraps
  `subprocess.run(timeout=…)`. Bounded.
- **`audio/mixer._probe_duration_s`**: already `timeout=15`.

## Fixed (were unbounded — could hang the worker)

| Site | Was | Now |
|------|-----|-----|
| `motion/crop.py` `proc.wait()` (per-part, **holds NVENC permit**) | no timeout → hang if ffmpeg stalls after stdin close | `proc.wait(timeout=_FFMPEG_TIMEOUT_SEC)`; catch-all except kills + retries/raises |
| `audio/mixer.py` `_has_audio_stream` ffprobe | no timeout | `timeout=30` |
| `audio/mixer.py` narration mix ffmpeg | `subprocess.run(check=True)` | `+timeout` + `except TimeoutExpired → RuntimeError` |
| `audio/mixer.py` BGM mix ffmpeg | `subprocess.run(check=True)` | `+timeout` + `except TimeoutExpired → RuntimeError` |
| `pipeline_source_prep.py` preprocess ffmpeg | `subprocess.run(check=True)` | `+timeout` + `except TimeoutExpired → RuntimeError` |
| `encoder/encoder_helpers.py` `ffmpeg -encoders` | no timeout | `timeout=30` |
| `pipeline/pipeline_config.py` probe | no timeout | `timeout=30` |

Audio ffmpeg timeouts use `FFMPEG_TIMEOUT_SECONDS` (default 3600s); probes use a
fixed 30s. All are generous — they bound a *hang*, not normal work.

## Left as low-risk (documented, not changed)

- `encoder_helpers.nvenc_runtime_ready`: probes with a 0.1s synthetic
  `color=…:d=0.1` input — completes near-instantly, can't meaningfully hang.
- `preview/ffmpeg_probers._run_ffmpeg_checked`: runs on the **preview HTTP
  request** thread, not the render worker — a stall there blocks one request,
  not the render queue. Out of scope for the worker-hang class.

## Net effect

Combined with the earlier fixes (phantom setup-crash jobs, async DB snapshot),
every blocking call on the render worker's path is now bounded by a timeout or
a cancel poll. A stalled external process can no longer hang `process_render`,
hold a concurrency slot, or pin an NVENC session indefinitely.

Full suite: **1421 passed**.

## Files

```
backend/app/features/render/engine/motion/crop.py
backend/app/features/render/engine/audio/mixer.py
backend/app/features/render/engine/pipeline/pipeline_source_prep.py
backend/app/features/render/engine/encoder/encoder_helpers.py
backend/app/features/render/engine/pipeline/pipeline_config.py
```
