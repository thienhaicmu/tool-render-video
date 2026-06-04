# Temp File Audit — Sprint 1.4 (read-only inventory)

**Date:** 2026-06-04
**Branch:** `feature/render-engine-upgrade` @ `2f275c7`
**Scope:** Inventory + classify every temp file/dir creation in the backend
render pipeline. Output feeds Sprint 6 (Temp File Optimization).
**Method:** Two parallel `Explore` agents read 22 files end-to-end. This doc
synthesises their findings — no code was modified.

This is an audit-ledger entry per CLAUDE.md `docs/review/**` convention:
append-only, read-only after commit.

---

## 1. Inventory (orchestration layer)

| # | File:line | Type | Lifetime | Cleanup | Size | I/O cost | Optimisation |
|---|---|---|---|---|---|---|---|
| O-1 | `orchestration/render_pipeline.py:220-221` | staging dir | 1 job | `finally: shutil.rmtree` | MB–GB (parent of all per-part files) | write_only | MEDIUM |
| O-2 | `orchestration/pipeline_source_prep.py:219` | video_temp | 1 job | `cleanup_temp_files` flag | 100–500 MB | write_then_read_once | **HIGH** |
| O-3 | `orchestration/render_pipeline.py:425` | json | 1 job | `cleanup_temp_files` flag | KB | write_only | LOW |
| O-4 | `orchestration/stages/part_renderer.py:86` (`raw_part`) | **video_temp** | **1 part** | `cleanup_temp_files` | 20–50 MB / part | write_then_read_N_times | **HIGH** |
| O-5 | `orchestration/stages/part_renderer.py:87` (`srt_part`) | srt | 1 part | `cleanup_temp_files` | 50–500 KB / part | write_then_read_N_times | MEDIUM |
| O-6 | `orchestration/stages/part_renderer.py:88` (`ass_part`) | ass | 1 part | `cleanup_temp_files` | 50–500 KB / part | write_then_read_N_times | MEDIUM |
| O-7 | `orchestration/stages/part_renderer.py:107` (`translated_srt_part`) | srt | 1 part | `cleanup_temp_files` | 50–500 KB / part | write_then_read_N_times | MEDIUM |
| O-8 | `orchestration/stages/part_renderer.py:113` (`_meta_path`) | json | 1 part | `cleanup_temp_files` | 1–5 KB / part | write_only | LOW |
| O-9 | `orchestration/stages/part_cut.py:251` | json (manifest) | 1 part | `cleanup_temp_files` | 2–10 KB / part | write_then_read_once | LOW |
| O-10 | `orchestration/stages/part_render_encode.py:154-156` (`_base_clip_out`) | **video_cache** | **1 part** | `cleanup_temp_files` | 50–150 MB / part | write_then_read_once | **HIGH** (gated by `FEATURE_BASE_CLIP_FIRST`) |
| O-11 | `orchestration/stages/part_render_encode.py:216-217` (`_overlay_srt`, `_overlay_ass`) | srt/ass | 1 part | `cleanup_temp_files` | 50–300 KB / part | write_then_read_once | MEDIUM |
| O-12 | `orchestration/stages/part_render_finalize.py:214` (`_paced_part`) | video_temp | 1 part | `finally: _safe_unlink` | 10–100 MB / part | write_then_read_once | MEDIUM |
| O-13 | `orchestration/stages/part_voice_mix.py:136, 230` (`_part_mp3`) | audio_temp | 1 part | conditional | 1–10 MB / part | write_then_read_once | MEDIUM |
| O-14 | `orchestration/stages/part_voice_mix.py:302` (`mixed_part`) | video_temp | 1 part | `_safe_unlink` on exception | 10–100 MB / part | write_then_read_once | MEDIUM |
| O-15 | `orchestration/pipeline_cache.py:46, 78, 100` | cache dir | 72 h | maintenance scheduler | — | write_only | LOW |
| O-16 | `orchestration/pipeline_setup.py:136` | staging | 1 job | user-managed | — | write_only | LOW |

No temp creation found in: `llm_pipeline.py`, `part_render_setup.py`, `part_render_context.py`.

## 2. Inventory (services + routes layer)

| # | File:line | Type | Lifetime | Cleanup | Size | I/O cost | Optimisation |
|---|---|---|---|---|---|---|---|
| S-1 | `services/subtitle_transcription_adapters.py:261` (`wav_path .fw.wav`) | audio_temp | 1 part | `finally: unlink(missing_ok=True)` | MB | write_then_read_once | MEDIUM |
| S-2 | `services/subtitle_transcription_adapters.py:338` (`.whisperx.tmp` SRT) | srt | 1 job | `try/finally: unlink` | KB | write_then_read_once | LOW |
| S-3 | `services/subtitles/ass_core.py:398` (`tempfile.TemporaryDirectory`) | staging | 1 part | context manager | 10–50 MB (preview only) | write_then_read_once | MEDIUM |
| S-4 | `services/tts_service.py:244` (`TEMP_DIR/{job_id}/voice/`) | audio_temp | 1 job | per-job prune | 10–50 MB | write_then_read_once | MEDIUM |
| S-5 | `services/tts_xtts_adapter.py:161` (`xtts_cache/*.mp3`) | **cache** | **NONE — unbounded** | **lazy only, no TTL prune** | MB (40–50 avg) | write_then_read_N | **HIGH** |
| S-6 | `services/tts_xtts_adapter.py:179` (`narration.xtts.wav`) | audio_temp | 1 job | explicit `unlink()` line 203 | 50–200 MB | write_then_read_once | LOW |
| S-7 | `services/text_overlay.py:76-97` (`data/temp/text_overlays/`) | json | **per_request, NONE cleanup** | **NONE** | KB–MB | write_only | **HIGH** |
| S-8 | `services/preview/ffmpeg_probers.py` | — | — | — | — | (no temp creation — `_ensure_h264_preview` is no-op since Sprint 1.5) | — |
| S-9 | `services/preview/session_service.py:18-21` (`_PREVIEW_DIR = TEMP_DIR/preview`) | staging | 6 h TTL | `evict_stale_preview_sessions` scheduler | 1–10 MB | write_then_read_once | MEDIUM |
| S-10 | `services/manifest_writer.py:38` (`.json.tmp`) | json | 1 part | `try/finally: unlink` | KB | write_then_read_once | LOW (atomic write — keep as-is) |
| S-11 | `services/maintenance.py:76` (`APP_DATA_DIR/cache/*`) | cache | 72 h | `prune_render_cache` scheduler ✅ | 100 MB+ | write_then_read_N | partly resolved — see §3 |
| S-12 | `services/downloader.py:196, 393` (yt-dlp `outtmpl`) | video_temp | per request | `_cleanup_partial` + per-job prune | 100–500 MB | write_only | LOW (outside render pipeline) |
| S-13 | `services/downloader.py:624` (`source*` glob unlink) | video_temp | per request | explicit unlink | varies | write_only | LOW |
| S-14 | `services/cookie_extractor.py:185` (`chrome_cookies_*.db`) | cookie | per request | context manager → delete | 1–5 MB | write_then_read_once | LOW |
| S-15 | `routes/render.py:272` (`TEMP_DIR/preview/{session_id}`) | staging | per session | `_cleanup_preview_session` → rmtree | 50–500 MB | write_then_read_once | LOW |
| S-16 | `routes/render.py:457` (`preview_audio.wav`) | audio_temp | per request | `unlink(missing_ok=True)` line 485 | 10–100 MB | write_then_read_once | MEDIUM |

---

## 3. Cache hierarchy & prune status

| Cache | Path | TTL | Prune mechanism | Status |
|---|---|---|---|---|
| Render cache (main) | `APP_DATA_DIR/cache/` (`scene_detect/`, `transcription/`, `segment_scores/`, …) | 72 h | `prune_render_cache` startup + scheduler | ✅ resolved (CLAUDE.md Issue 3 — partly) |
| XTTS synthesis cache | `TEMP_DIR/xtts_cache/*.mp3` | none | **none — unbounded growth** | ❌ gap |
| Text overlay temp | `data/temp/text_overlays/` (fallback: `TEMP_DIR/tool-render-video/text_overlays`) | none | **none** | ❌ gap |
| Preview sessions | `TEMP_DIR/preview/{session_id}/` | 6 h | `evict_stale_preview_sessions` + `prune_preview_dirs` | ✅ |
| Per-job work dirs | `TEMP_DIR/{job_id}/` | on job completion | `prune_render_temp_dirs` (startup + scheduler), protects active jobs | ✅ |
| Whisper / HuggingFace / Torch / Ollama model dirs | `data/whisper_cache/`, `data/huggingface/`, `data/torch/`, `data/ollama/` | indefinite | none — model storage, intentional | (not a temp concern) |

> **Issue 3 (CLAUDE.md) status revisited:** the warning was right about
> `APP_DATA_DIR/cache` lacking scheduled prune; that part is now fixed in
> `main.py` startup + scheduler. **But two new gaps surfaced during this
> audit** that the original Issue 3 entry did not name:
> the **XTTS synthesis cache** and the **text overlay temp directory**.
> Both grow unbounded.

---

## 4. Per-part vs per-job overhead

The per-part files dominate disk pressure because they multiply with
`output_count`. For a 50-part render the cumulative on-disk footprint
during execution is **≈ 4.5 – 21 GB**:

| Per-part file | Per-part size | × 50 parts |
|---|---|---|
| `raw_part` (O-4) | 20–50 MB | 1.0–2.5 GB |
| `_base_clip_out` (O-10, conditional on `FEATURE_BASE_CLIP_FIRST=1`) | 50–150 MB | 2.5–7.5 GB |
| `_paced_part` (O-12) | 10–100 MB | 0.5–5.0 GB |
| `mixed_part` (O-14, conditional on voice) | 10–100 MB | 0.5–5.0 GB |
| `_part_mp3` (O-13, conditional on voice) | 1–10 MB | 50–500 MB |
| `srt_part`, `ass_part`, `translated_srt_part` (O-5/6/7) | 0.15–1.5 MB combined | 7.5–75 MB |
| `_meta_path`, manifest (O-8, O-9) | < 15 KB | < 750 KB |

Per-job files (O-1, O-2, O-3, S-2, S-4, S-6) sum to <1 GB and are not
the bottleneck.

---

## 5. Concurrency safety

| Concern | Verdict |
|---|---|
| File-name collision between parallel jobs | **Safe** — paths are `TEMP_DIR/{job_id}/…`, and `upsert_job()` + the in-process queue guard against the same `job_id` running twice. |
| File-name collision between parallel parts of the same job | **Safe** — paths include `_part_{idx:03d}_` formatted to 3 digits. |
| Cleanup race | **Mostly safe.** `finally` blocks wrap the big intermediates (`_paced_part` O-12, `mixed_part` O-14, parent `work_dir` O-1). Gap: `_part_mp3` (O-13) is only conditionally unlinked — if the TTS subprocess succeeds but `mix_narration_audio` raises before the explicit cleanup branch, the MP3 stays until the per-job prune runs. |
| Atomic write of small artefacts | **Safe** — `manifest_writer.py:38` uses `.json.tmp` + rename, and `part_render_finalize.py:214` uses `_paced_part` + `os.replace` pattern. |

---

## 6. Sprint 6 P0 / P1 / P2 candidates

This is the synthesised optimisation backlog. Each item carries
file:line so Sprint 6 can route to the right risk tier directly.

### P0 — high ROI, scoped, low–medium risk

1. **`xtts_cache/` prune (S-5)** — add `prune_xtts_cache(max_age_days=30)`
   or size-bounded LRU eviction inside the existing `maintenance.py`
   scheduler. **Effort: ½ day. Risk: LOW.** Frees ~200–500 MB / user / month.
2. **`text_overlay.py:76-97` cleanup (S-7)** — currently the `text_overlays/`
   directory has **no cleanup at all** and accumulates one file per layer
   per render. Add a cache-key digest + TTL prune in the same scheduler
   tick as S-5. **Effort: ½ day. Risk: LOW.**
3. **`_part_mp3` cleanup guarantee (O-13)** — wrap the TTS-then-mix
   sequence in `part_voice_mix.py:136-230` in a `try/finally` that
   `_safe_unlink`s the MP3 unconditionally. **Effort: < ½ day. Risk:
   LOW.** Eliminates the only orphan path identified in §5.

### P0 — high ROI but higher risk (CRITICAL tier — Render Edit Protocol applies)

4. **`raw_part` in-memory staging (O-4)** — replace the 20–50 MB / part
   disk file with a `BytesIO` buffer (or `subprocess.Popen` stdout pipe)
   when the buffer fits under a threshold (e.g. 200 MB). Saves
   1.0–2.5 GB / 50-part job. **Effort: 2–3 days. Risk: HIGH** — touches
   `part_cut.py` + `render_engine.cut_video()` signature. Requires
   Render Edit Protocol (9 steps) per CLAUDE.md.
5. **`_base_clip_out` gating (O-10)** — when `FEATURE_BASE_CLIP_FIRST=1`
   AND motion-crop cache is HIT, the intermediate base-clip MP4 is
   wasted (2.5–7.5 GB / 50-part job). Detect the cache hit earlier and
   skip the base-clip render. **Effort: 2 days. Risk: HIGH.**

### P1 — medium ROI

6. **Inline SRT/ASS via FFmpeg filter graph (O-5/6/7, S-3)** — the
   `ass` filter requires a libass-readable file on disk, so a true
   inline replacement is **not feasible**. However, the audit confirms
   the SRT-input variant of `subtitles=` is possible for the simpler
   subtitle paths that don't use karaoke `\k` tags. Worth one focused
   sub-sprint to identify which call sites can opt in.
7. **Preview audio in-memory (S-16)** — `preview_audio.wav` is written
   then immediately read by Whisper. A `BytesIO` pipe is feasible.
8. **Preview transcript caching by content hash (S-9)** — currently
   keyed by `session_id`; switching to content hash lets re-previews of
   the same source reuse the transcript.

### P2 — cosmetic / monitoring

9. **Cache size telemetry** — surface `du -s` of each cache root in the
   metrics endpoint so Sprint-6 follow-ups have evidence.
10. **Disk-pressure guard in `pipeline_render_loop`** — if free space
    below threshold, throttle worker count before launch.

---

## 7. What this audit did NOT touch

- Whisper model cache (`data/whisper_cache/`) — intentional persistent storage.
- HuggingFace / Torch / Ollama model dirs — intentional.
- Output directory tree under user control.
- Frontend disk usage (out of scope).

---

## 8. Next

This doc is the deliverable for Sprint 1.4. It is read-only after commit.
Sprint 6 will pick up the P0 candidates above and convert them into
plans (the CRITICAL-tier items must go through Planner → user approval →
Render Edit Protocol per CLAUDE.md before any code change).
