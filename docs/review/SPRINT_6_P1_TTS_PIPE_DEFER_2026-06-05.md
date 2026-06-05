# Sprint 6 P1 TTS Pipe — DEFERRED

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Baseline at decision:** Pytest 2376 passed / 1 skipped / 0 failed @ `f1a3d4b` (Sprint 6 P1 cache prune close)
**Decision:** DEFER. ROI tiny, cleanup adapter is path-based by design, Windows pipe deadlock risk. Third Sprint 6 P1 "Dự đoán P0" prediction to fail audit validation — see sibling meta-finding doc `SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md`.

## Purpose

Record the Sprint 6 P1 TTS-pipe audit so future agents do not re-attempt a path-bypass that the cleanup adapter actively forbids, and so the empirical-vs-prediction mismatch is captured as part of the broader Sprint 6 P1 closure record.

## Original target

Per `docs/review/SPRINT_PLAN_2026-06-04.md:260`, line item #3 of Sprint 6 P1:

> Dự đoán P0:
> - Skip per-part Whisper re-extract audio
> - Inline subtitle ASS qua filter graph (không write file)
> - Pipe TTS audio → mix (không write WAV intermediate)
> - Render cache prune (`maintenance.py` Issue 3 CLAUDE.md)

"Dự đoán" (predicted) is load-bearing — same provenance class as the previously-deferred Whisper-skip and Inline-ASS items.

## TTS engine inventory

The codebase supports two engines, both Python libraries (no subprocess CLI):

| Engine | Site | Output | Native stream capability |
|---|---|---|---|
| **Edge-TTS** (default, `tts_engine="edge"`) | `backend/app/services/audio/tts.py:215-264` (`generate_narration_mp3`) | MP3 chunks from Microsoft Edge cloud over WebSocket | YES — `edge_tts.Communicate.stream()` is an `AsyncGenerator[TTSChunk, None]`. `Communicate.save()` internally just iterates and writes to file. |
| **XTTS v2** (Coqui, `tts_engine="xtts"`) | `backend/app/services/audio/tts_xtts.py:138-223` (`synthesize_xtts`) | WAV → FFmpeg `libmp3lame` → MP3 | NO — `TTS.api.TTS.tts_to_file(file_path=...)` only takes a path. The `tts(...)` variant returns a numpy float array — manual encoding required to get MP3 bytes. |

The dispatcher at `tts.py:278-291` only routes `"edge"` and `"xtts"`. No OpenAI / Google / ElevenLabs subprocess adapters. The Sprint Plan §260 wording "Pipe TTS audio" implies a subprocess pipe, which mismatches the current architecture (library-mode).

## Mix consumer audit

Single consumer: `mix_narration_audio` at `backend/app/services/audio/mix.py:40-156`.

- **Signature:** `narration_audio_path: str` (file path), `video_path: str`, `output_path: str` — line 42-47.
- **Internal:** FFmpeg `-i {video} -i {narration}` at line 77, `filter_complex` (atempo / apad / amix / volume), `-c:v copy` + `-c:a aac` re-encode. Calls `_probe_duration_s(source_video)` at line 73 first.
- **Could it accept bytes?** FFmpeg can take stdin via `-i pipe:0`. But mix has TWO file inputs; only ONE can be `pipe:0`. The narration side could be the pipe (video stays on disk — it's the per-part final MP4).

## The downstream constraint — audio cleanup adapter is path-based

After TTS, before mix, `_maybe_cleanup_narration_audio(narration_audio_path, ...)` is called at four sites:
- `backend/app/orchestration/pipeline_narration.py:120` (manual voice path)
- `backend/app/orchestration/stages/part_voice_mix.py:170-177` (per-part subtitle-source path)
- `backend/app/orchestration/stages/part_voice_mix.py:262-269` (per-part translated-subtitle path)

When `audio_cleanup_engine == "deepfilternet"` (auto-enabled if the optional package is installed — see `audio_cleanup.py:27-30`):

1. Runs FFmpeg to **convert MP3 → WAV on disk** (`backend/app/services/audio/cleanup_adapters.py:65, 162-184`)
2. Loads the WAV via `df.enhance.load_audio(str(work_wav), ...)` — **path string, not bytes** (`cleanup_adapters.py:69`)
3. Writes enhanced audio to `target` via `df.enhance.save_audio(str(target), ...)` — **path string** (`cleanup_adapters.py:71`)
4. Probes input + cleaned output durations with ffprobe for integrity (`cleanup_adapters.py:64, 77`)

DeepFilterNet's `df.enhance` API is **path-based by design**. Piping TTS → mix means either:
- (a) **Skip the entire audio cleanup stage for piped TTS** — silent quality regression for users with DeepFilterNet installed; users may not detect it until they notice noisier narration.
- (b) **Materialize a temp WAV anyway** — defeats the purpose of piping.

Neither option is acceptable for Sprint 6 P1's stated goal.

## Feasibility per engine

### Edge-TTS — partially feasible at API level, blocked by cleanup constraint

`edge_tts.Communicate.stream()` is the public async-iterator yielding MP3 chunks. Today `generate_narration_mp3` uses it indirectly through `.save()`. Replacing `.save()` with chunk-iteration into a `subprocess.Popen(stdin=PIPE)` FFmpeg call is mechanically achievable on Windows.

But: see the downstream cleanup constraint above. Edge-TTS piping requires either skipping cleanup or buffering. Net win ≈ zero.

### XTTS v2 — not feasible without major refactor

The library only exposes `tts_to_file(file_path=str)` cleanly. Switching to `tts(...)` returns a numpy float array (24kHz mono), which then needs:
1. Manual encoding (numpy → PCM → MP3) via lameenc or another FFmpeg subprocess
2. Then piping encoded bytes to mix

This means two FFmpeg processes pipelined plus a Python encoder. The `xtts_cache` shipped in Sprint 6 P0 commit `1db0df3` already short-circuits repeat synthesis to a file copy — piping bypasses the cache entirely (a regression). Touches the GPU semaphore lock in `tts_xtts.py`.

## Windows compatibility

| Aspect | Status |
|---|---|
| `subprocess.Popen(stdin=PIPE)` on Windows | Works (Python stdlib portable). |
| FFmpeg `-i pipe:0` on Windows | Works (libavformat). |
| `os.mkfifo` (named pipe) | DOA — POSIX-only. Already documented in `docs/review/SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` §"Mechanism options". |
| `edge_tts.Communicate.stream()` on Windows | Works — aiohttp over WebSocket, no OS-specific calls. |
| **Pipe buffer deadlock** | **Real risk.** Windows anonymous pipes have a 4-64 KB buffer. If TTS produces faster than FFmpeg consumes (or vice versa), the producer blocks. Without a draining thread on each side, `subprocess.Popen.communicate()` is the safe API but **buffers everything in memory** — defeats the streaming win for a 1-10 MB payload. |

## Sacred Contract walk

- **#3 AI returns None never raises** — TTS lives in `services/audio/`, not `backend/app/ai/**`. The existing failure semantics: `part_voice_mix.py:178-192, 270-284` catch all exceptions, emit `voice_failed` with `error_code=VOICE001`, render continues. Pipe behaviour would surface broken pipes as `BrokenPipeError`; the broader try/except catches it; cleanup of broken `mixed_part` is wired at `:333-346`. Honored.
- **#6 `_emit_render_event`** — Eight call sites in `part_voice_mix.py` reference `audio_path` in event context (line 168, 260). If we pipe, that field becomes meaningless. Either emit `"audio_path": "<piped>"` (consumer-breaking sentinel) or skip the field (silently breaks WebSocket consumers that read it). Field shape change is a non-zero Sacred Contract risk.
- **#8 qa_pipeline** — qa reads only the final mp4. No interaction with TTS pipe vs file. Safe.

## ROI verification

Per `docs/review/TEMP_FILE_AUDIT_2026-06-04.md`:

| Quantity | Value |
|---|---|
| Per-part `_part_mp3` size (audit row O-13) | 1-10 MB |
| × 50 parts worst case | 50-500 MB |
| Per-job voice dir total (audit row S-4) | 10-50 MB |
| Time to write 1-10 MB to NVMe | < 50 ms |
| Time saved vs FFmpeg encode wall-clock | < 0.5% per part |
| `xtts_cache` (Sprint 6 P0 commit `1db0df3`) | Already short-circuits to file copy in < 100 ms |

**Disk + time win is single-digit MB per part and millisecond-class.** The xtts_cache work already covers the repeated-synthesis disk concern. Audit explicitly ranked `_part_mp3` as MEDIUM, not P0/P1, and listed only "`_part_mp3` cleanup guarantee" (closed by `1db0df3`'s try/finally wrap) — not piping.

**The Sprint Plan §260 line "Pipe TTS audio → mix" does NOT appear in the empirical audit's P0/P1 ranking** (verified by grep of TTS/voice/narration rows in `TEMP_FILE_AUDIT_2026-06-04.md`). It is the third pre-audit "Dự đoán P0" prediction, following Whisper-skip and Inline-ASS.

## Why DEFER

1. **ROI failure.** Disk win < 500 MB worst case, time win millisecond-class, both dominated by the FFmpeg encode wall clock that piping does not touch. `xtts_cache` already shipped covers the repeat-synthesis case.

2. **Cleanup adapter is path-based by design.** DeepFilterNet's `df.enhance.load_audio(str)` / `save_audio(str)` API takes paths only. Piping = skip cleanup = silent quality regression. Materialising a temp WAV defeats the purpose.

3. **Windows deadlock risk** for the only feasible engine (Edge-TTS) requires draining-thread pattern or memory-buffer-and-feed, both of which negate the streaming win for a < 10 MB payload.

4. **XTTS DOA without major refactor** touching the GPU semaphore lock and bypassing the existing `xtts_cache`.

5. **Sacred Contract #6 risk** — `audio_path` field in `_emit_render_event` context loses meaning under piping; consumer-breaking.

## What this audit does NOT defer

- The `_part_mp3` cleanup guarantee (audit row O-13) is already closed by Sprint 6 P0 commit `1db0df3`. No further action.
- The `xtts_cache` bounding (audit row S-5) is already closed by Sprint 6 P0 commit `1db0df3`. No further action.

## What this commit does

Single commit, single file: this audit doc. No code change. Pytest baseline (2376/1/0) unchanged.

A sibling meta-finding doc (`SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md`) captures the 0/3 prediction-validation rate across all three deferred Sprint 6 P1 items and recommends future sprints index from the empirical audit rather than the SPRINT_PLAN prediction list.

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-04.md:253-266` — Sprint 6 outline (the predicted P0 list)
- `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` — empirical audit (the document whose ranking superseded the prediction)
- `docs/review/SPRINT_6_P1_WHISPER_DEFER_2026-06-05.md` — sibling P1 defer #1 (PIN load-bearing)
- `docs/review/SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` — sibling P1 defer #2 (FFmpeg fopen() impossibility)
- `docs/review/SPRINT_6_P1_CACHE_PRUNE_2026-06-05.md` — sibling P1 resolution (the one prediction the audit endorsed)
- `docs/review/SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md` — meta-finding doc capturing the 0/3 rate
- `backend/app/services/audio/tts.py` — Edge-TTS entry
- `backend/app/services/audio/tts_xtts.py` — XTTS entry
- `backend/app/services/audio/mix.py` — mix consumer
- `backend/app/services/audio/cleanup_adapters.py` — DeepFilterNet path-based API (the blocking constraint)
- `backend/app/orchestration/stages/part_voice_mix.py` — orchestration site
- `backend/app/orchestration/pipeline_narration.py` — manual voice orchestration

## What future sprints should NOT do

- Do not delete this audit doc. It records that the TTS-pipe swap was investigated and rejected on cleanup-adapter / ROI / Windows-deadlock grounds.
- Do not attempt piping for Edge-TTS without first making `cleanup_adapters.py` bytes-native — and that refactor itself is not justified by the 1-10 MB per-part disk win.
- Do not attempt piping for XTTS — the GPU-semaphore + xtts_cache interaction makes the change strictly worse than the file path.
- Do not silently disable audio cleanup for any code path. Users who installed DeepFilterNet expect it to run; bypassing it is a quality regression detectable only via listening.
