# PRODUCT STATE — QUALITY-UP24: Smart Fail Recovery

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): smart fail recovery`
**Status:** Shipped

---

## Summary

Adds structured observability and surface-level UI for safe fallback events that already happen inside the render engine. **No pipeline rewrite. No new fallback logic.** The fallbacks existed; UP24 names them, emits events for them, and shows creators what happened.

**Creator goal:** "I trust this to run overnight."

---

## Failure Classification

### Recoverable (safe fallback exists)

| Failure | Fallback | Where |
|---|---|---|
| Motion-aware crop fails | Standard center crop | `render_engine.py:render_part_smart()` |
| GPU (NVENC) encode fails | CPU encoder (libx264/libx265) | `render_engine.py:render_part()` |
| AI narration (TTS) fails | Render without voice, original audio preserved | `render_pipeline.py` |
| Subtitle transcription fails | Render without subtitles | `render_pipeline.py` |
| FFmpeg transient error | Retry (2 attempts, exponential backoff) | `render_engine.py:_run_ffmpeg_with_retry()` |

### Hard Fail (no retry, no silent degradation)

| Failure | Behavior |
|---|---|
| Corrupt or missing source file | Immediate failure, clear error |
| Permission denied on output path | Immediate failure |
| Unsupported codec | Immediate failure |
| Empty source file | Immediate failure |
| User-cancelled job | `JobCancelledError` raised — **never retried** |
| All parts fail | `RuntimeError("All parts failed N/N")` — job fails cleanly |

### Isolation Rule

Each render part is isolated. One part failing does not cancel other parts. One batch item failing does not affect other batch items.

---

## What Was Added

### `backend/app/orchestration/render_pipeline.py`

- `_recovery_notes: list[str] = []` — collects fallback events during a job run
- In **TTS catch block**: appends `"AI narration failed — rendered without voice"` + emits `recovery_success` event
- In **subtitle transcription catch block**: appends `"Subtitle transcription failed — rendered without subtitles"` + emits `recovery_success` event
- `_final_message` updated: if `_recovery_notes` is not empty, appends `" [note1; note2]"` to the message
- `_result_payload["recovery_notes"]` — exposed in job result JSON for UI consumption

### `backend/app/services/render_engine.py`

Added structured recovery log lines alongside existing warnings:

- **NVENC → CPU fallback**: `logger.info("recovery_attempted strategy=cpu_encoder reason=... output=...")`  + `logger.info("recovery_success strategy=cpu_encoder output=...")`
- **Motion crop → standard fallback**: `logger.info("recovery_attempted strategy=fallback_standard_crop ...")` + `logger.info("recovery_success strategy=fallback_standard_crop ...")`

No function signatures changed. No logic changed. Log lines only.

### `backend/static/js/batch-queue.js`

- Added `STATUS.RECOVERED = 'recovered'` to the status enum
- `_fetchJobStatus()` now reads `data.message`:
  - `status === 'completed'` + recovery keywords in message → `STATUS.RECOVERED`
  - `status === 'completed_with_errors'` → `STATUS.RECOVERED`
- `_render()` shows `"Recovered"` label with amber color and hover tooltip `"Rendered using safe fallback"`
- Recovery note (why it recovered) shown as `.bqCardRecoveredNote` under the chip
- `removeItem()` and poll terminal check treat `RECOVERED` as done

### `backend/static/js/render-ui.js`

- Reads `parseRenderResult(job)?.recovery_notes` before clip card loop
- Each completed clip card shows `<div class="clipRecoveredNote" title="...">Recovered</div>` when `_jobRecovered` is true
- Hover tooltip = the recovery notes joined by `' · '`

### `backend/static/css/app.css`

New classes:
- `.bqCard.bq-recovered` — amber border
- `.bqCardStatus.st-recovered` — amber badge  
- `.bqCardRecoveredNote` — amber note text under card status
- `.clipRecoveredNote` — amber text chip on clip cards

---

## What Was Intentionally NOT Changed

| Not Changed | Reason |
|---|---|
| Fallback logic in render_engine.py | Already correct — log lines only added |
| `_run_ffmpeg_with_retry()` retry count | Existing 2-retry policy is appropriate |
| Cancel flow | `JobCancelledError` path unchanged — cancelled jobs never retry |
| Job status values for normal complete/fail | Only new: `recovered` in client tracking |
| Per-part failure tracking (`failed_parts`) | Unchanged |
| Any render pipeline order | Pure addition |

---

## Observability Events

| Event | When | Level |
|---|---|---|
| `voice_failed` | TTS generation throws | ERROR |
| `recovery_success` (strategy=skip_voice) | After TTS failure, pipeline continues | INFO |
| `subtitle_transcription_failed` | Whisper throws | WARNING |
| `recovery_success` (strategy=skip_subtitles) | After transcription fail, pipeline continues | INFO |
| `recovery_attempted` (strategy=cpu_encoder) | NVENC encode throws | INFO (log only) |
| `recovery_success` (strategy=cpu_encoder) | CPU fallback completes | INFO (log only) |
| `recovery_attempted` (strategy=fallback_standard_crop) | Motion crop throws | INFO (log only) |
| `recovery_success` (strategy=fallback_standard_crop) | Standard crop fallback completes | INFO (log only) |

---

## Trust Rules

- A recovered render **always produces usable output**. If quality would collapse (e.g., all parts fail), the job hard-fails cleanly instead of silently completing.
- Subtitles are never silently removed unless creator chose `add_subtitle = false`. The transcription failure is logged and surfaced in the job message.
- TTS failure falls back to original audio — creator's voice is preserved, AI narration is skipped.
- Cancelled jobs are never retried, ever. The cancel registry checks this before any retry path.
- "Recovered" is honest: it appears only when a fallback actually fired.

---

## Manual QA Checklist

### A — Motion crop fail

- [ ] Force motion-aware crop to raise (e.g., corrupt motion data or set env to block)
- [ ] Expected: render succeeds with center crop
- [ ] Logs: `recovery_attempted strategy=fallback_standard_crop` + `recovery_success`
- [ ] No "Recovered" on clip card (motion crop fallback is transparent, not surfaced via `_recovery_notes` — it's a within-render-engine event)

### B — GPU fail

- [ ] Force NVENC encode to fail (disable GPU or set `encoder_mode=nvenc` on CPU-only machine)
- [ ] Expected: render succeeds with CPU encode
- [ ] Logs: `recovery_attempted strategy=cpu_encoder` + `recovery_success`

### C — Corrupt file

- [ ] Feed a zero-byte or corrupt video as source
- [ ] Expected: job fails with clear error, no retry

### D — Cancel render

- [ ] Cancel a running job mid-render
- [ ] Expected: status = `cancelled`, no retry attempt, batch continues with next item

### E — Batch: 1 failure, others continue

- [ ] Queue 3 files; file #2 has a corrupt path
- [ ] Expected: file #2 fails, files #1 and #3 complete normally

### F — TTS fail

- [ ] Enable AI narration with a voice service unavailable
- [ ] Expected: render completes, message contains `"[AI narration failed — rendered without voice]"`
- [ ] Batch card shows "Recovered" in amber
- [ ] Clip cards show "Recovered" chip with hover detail

### G — Subtitle transcription fail

- [ ] Force Whisper to fail (e.g., remove model files)
- [ ] Expected: render completes without subtitles, `recovery_notes` in result JSON
- [ ] Clip cards show "Recovered" chip

### H — No infinite retry

- [ ] All recovery paths: max 1 safe fallback attempt, then hard fail or continue

### I — Single render path unaffected

- [ ] Normal single-file render in editor: no regressions

### J — Recovered output usable

- [ ] Download a recovered clip: verify it plays, has correct aspect ratio, has audio
