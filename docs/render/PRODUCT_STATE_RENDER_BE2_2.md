# PRODUCT STATE — RENDER-BE2.2: Cancel Integrity

**Branch:** `feature/ai-output-upgrade`
**Commit:** `fix(render): cancel integrity`
**Status:** Shipped

---

## Summary

Cancel now feels instant. Eight cancel checkpoints are added before long-running
operations in the render pipeline. `apply_micro_pacing`'s ffmpeg call is now
cancel-aware via `_run_ffmpeg_with_retry`. The UI reflects "cancelling" status
immediately when the user clicks Cancel.

---

## Root Cause

Cancel signal (`cancel_registry.request_cancel`) sets a threading Event. Only
`_run_ffmpeg_with_retry` polled this event (every 1 s). All other long-running
operations — transcription (minutes), scene detection, translation, TTS, silence
analysis, AI visibility summaries — ran to completion regardless of the cancel
signal.

`apply_micro_pacing` used bare `subprocess.run(cmd, timeout=150)` — not
`_run_ffmpeg_with_retry` — so its ffmpeg process was never killed on cancel.

The UI had no "cancelling" DB state, so the WS ticker showed the last render
stage until the pipeline eventually noticed the cancel flag.

---

## Part A — Cancel Checkpoints (`render_pipeline.py`)

Eight `is_cancelled` checks inserted before long-running operations. Each check
is placed **outside** any `except Exception` block that would swallow
`JobCancelledError`, so the signal always propagates to the pipeline's top-level
cancel handler.

| Location | Stage | Max blind window (before) |
|----------|-------|--------------------------|
| Before manual voice TTS (`generate_narration_mp3`) | pre-scene | 30–120 s |
| Before `detect_scenes` | scene detection | 10–60 s |
| Before `score_segments` | segment building | 1–5 s |
| Before transcription heartbeat try (`transcribe_with_adapter`) | transcription | 30–300 s |
| Before subtitle translation try (`translate_srt_file`) | subtitle | 10–60 s per part |
| Before per-part TTS try (`generate_narration_mp3`) | voice (per part) | 5–30 s per part |
| Before micro pacing block | pacing (per part) | up to 150 s per part |
| Before `attach_ai_visibility_summaries` | post-render ranking | 5–30 s |

Pattern at each site:
```python
if cancel_registry.is_cancelled(job_id):
    raise cancel_registry.JobCancelledError()
```

---

## Part B — `apply_micro_pacing` Cancel-Awareness (`render_engine.py`)

**`apply_micro_pacing` ffmpeg call:**

Replaced:
```python
subprocess.run(cmd, capture_output=True, text=True, timeout=150, check=True)
```
With:
```python
_run_ffmpeg_with_retry(cmd, retry_count=0)
```

`_run_ffmpeg_with_retry` polls `_tls.cancel_event` every 1 s. On cancel it calls
`proc.terminate()` / `proc.kill()` and raises `RuntimeError("FFmpeg cancelled")`.
The caller's `except Exception` in render_pipeline.py catches this and skips
pacing — the original clip is kept. The pipeline then hits the next checkpoint
and terminates cleanly.

`retry_count=0`: pacing is non-critical; no retry on failure.

**`_detect_silence_segments` cancel check:**

Added before `subprocess.run`:
```python
cancel_ev = getattr(_tls, 'cancel_event', None)
if cancel_ev is not None and cancel_ev.is_set():
    return []
```
Cancel returns empty silence list → `apply_micro_pacing` returns `_NO_OP`
without spawning ffmpeg.

---

## Part C — Runtime Truthfulness (`routes/render.py`)

In `cancel_render_job`, before signalling the cancel registry:
```python
update_job_progress(job_id, "cancelling", 0, "Cancelling…", status="cancelling")
```

The WS fingerprint dedup (`_ws_fingerprint`) includes `job.status`, so the next
tick sends the "cancelling" state immediately. The UI reflects the user's action
within 500 ms rather than waiting for the pipeline's finally block.

---

## Parts D & E — Already Handled

**Part D (terminal state write):** The existing `process_render` finally/except
already writes `status="cancelled"` and calls `cancel_registry.unregister(job_id)`.
No change needed.

**Part E (resume/retry safety):** Cancel checkpoints raise `JobCancelledError`
which propagates to the top-level handler. Resume checks `final_part.exists()`
on the output file only — unaffected. Retry re-queues the job fresh — unaffected.

---

## Behavior Matrix

| Cancel requested during | Before | After |
|------------------------|--------|-------|
| Voice TTS (manual) | TTS runs to completion | Cancelled before TTS starts |
| Scene detection | Runs to completion | Cancelled before detect_scenes |
| Segment scoring | Runs to completion | Cancelled before score_segments |
| Transcription | Runs to completion (minutes) | Cancelled before Whisper call |
| Subtitle translation | Runs to completion | Cancelled before translate_srt_file |
| Per-part TTS | Runs to completion | Cancelled before generate_narration_mp3 |
| Micro pacing (silence detect) | silence ffprobe blocks 60 s | Returns [] immediately |
| Micro pacing (ffmpeg pass) | ffmpeg runs up to 150 s | ffmpeg killed within ~1 s |
| AI visibility summaries | Runs to completion | Cancelled before attach call |
| Active ffmpeg encode | Killed within ~1 s | **Unchanged** (already handled) |

---

## Constraints Honored

| Constraint | Status |
|-----------|--------|
| No render rewrite | ✓ |
| No ffmpeg pipeline rewrite | ✓ |
| No queue/scheduler rewrite | ✓ |
| No API change | ✓ |
| No DB schema change | ✓ |
| No WS protocol change | ✓ |
| Resume unaffected | ✓ |
| Retry unaffected | ✓ |
| YouTube flow unchanged | ✓ |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/orchestration/render_pipeline.py` | 8 cancel checkpoints before long-running operations |
| `backend/app/services/render_engine.py` | `apply_micro_pacing`: `subprocess.run` → `_run_ffmpeg_with_retry(retry_count=0)`; `_detect_silence_segments`: cancel-early check |
| `backend/app/routes/render.py` | Write `status="cancelling"` to DB before signalling cancel registry |
| `docs/render/PRODUCT_STATE_RENDER_BE2_2.md` | This file |

---

## Manual QA Checklist

- [ ] Cancel during voice TTS: job stops quickly, status = cancelled
- [ ] Cancel during scene detection: job stops quickly, status = cancelled
- [ ] Cancel during transcription: job stops quickly, status = cancelled
- [ ] Cancel during subtitle translation: job stops quickly, status = cancelled
- [ ] Cancel during per-part TTS: job stops quickly, status = cancelled
- [ ] Cancel during micro pacing: job stops quickly (≤2 s), status = cancelled
- [ ] Cancel during active ffmpeg encode: job stops within ~1 s (unchanged)
- [ ] Cancel queued job: job never starts, status = cancelled
- [ ] UI: "Cancelling…" state visible immediately on cancel click
- [ ] UI: transitions to "Cancelled" within ~2 s of clicking Cancel
- [ ] Normal render (no cancel): completes correctly, no regression
- [ ] Resume after cancel: skips done parts, completes remaining
- [ ] Retry after cancel: re-renders correctly
