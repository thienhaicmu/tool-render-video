# PROJECT_FLOW.md — Execution Flow Analysis

## A. User Flow

```
1. User opens desktop app (Electron)
   → Splash screen while backend boots (venv check, pip install if needed)
   → BrowserWindow loads http://127.0.0.1:8000/

2. [#create screen] User provides source
   → YouTube URL → POST /api/render/prepare-source (downloads in foreground, ~10-60s)
   → Local file   → POST /api/render/prepare-source (validates, transcodes preview if needed)
   → Response: { session_id, duration, title }

3. User configures render settings
   → Preset: Fast Hooks / Balanced / Story / Full
   → Format: 9:16 / 1:1 / 16:9
   → Optional: subtitle style, market, playback speed, AI mode, variants

4. User clicks "Generate Clips"
   → POST /api/render/process { source_mode, session_id, output_dir, ... }
   → Response: { job_id, status: "queued" }
   → Router navigates to #monitor/{job_id}

5. [#monitor screen] Real-time progress
   → WebSocket /api/jobs/{job_id}/ws → { job, parts, summary } every 500ms
   → Fallback: HTTP polling GET /api/jobs/{job_id} + /api/jobs/{job_id}/parts every 3s
   → Progress bar, stage label, per-clip status table

6. Job completes
   → Terminal status: completed / completed_with_errors / failed / interrupted
   → CTA: "View Results" → #results/{job_id}

7. [#results screen] Review clips
   → Streamed video via GET /api/render/jobs/{job_id}/parts/{part_no}/media (Range support)
   → Thumbnail: GET /api/render/jobs/{job_id}/parts/{part_no}/thumbnail
   → User approves clips → adds to upload queue

8. [Upload] Schedule or immediate upload
   → TikTok/YouTube via Playwright browser automation
```

---

## B. Render / Edit Flow

```
POST /api/render/process
  └── render.py: validate payload → _queue_render_job()
        └── job_manager.submit_job(job_id, process_render, ...)
              └── [job-worker thread] process_render()
                    └── run_render_pipeline(job_id, payload, ...)

run_render_pipeline (render_pipeline.py):

1. SOURCE ACQUISITION
   a. If edit_session_id: load_session_fn() → get pre-downloaded video path
   b. If youtube: download_youtube() via yt-dlp
   c. If local: validate path exists

2. INPUT VALIDATION
   - _probe_video_duration() via ffprobe
   - _validate_text_layers_or_400()
   - Aspect ratio / platform profile resolution

3. SCENE DETECTION
   - _scene_cache_get() → cache hit returns immediately
   - detect_scenes() → PySceneDetect ContentDetector OR TransNetV2
   - _scene_cache_put() → cache result

4. SEGMENT BUILDING
   - build_segments_from_scenes() → raw candidate segments
   - refine_segment_boundaries() → boundary alignment
   - refine_cuts_for_naturalness() → silence/speech-aware trims

5. SCORING
   - score_scenes_clip() → per-scene clip quality scores
   - score_segments() → viral scoring (heuristic or ML)
   - apply_retention_proxy() → retention signal
   - _mv_score_part() → market-specific scoring

6. AI EDIT PLANNING (optional, ai_director_enabled=True)
   - create_ai_edit_plan() → transcript + beat + emotion analysis
   - Returns AIEditPlan with: clip hints, subtitle plan, camera plan, pacing plan

7. SEGMENT SELECTION
   - Variant mode: _build_variant_segments() → 3 segments (aggressive/balanced/story-first)
   - Normal mode: top-N scored segments by combined weight

8. TRANSCRIPTION (per segment, may be cached)
   - _transcription_cache_get() → cache hit
   - transcribe_with_adapter() → Whisper base/medium (or faster-whisper)
   - Produces full-video SRT file

9. PER-PART PARALLEL RENDER (ThreadPoolExecutor)
   For each selected segment:
   a. SRT SLICING: slice_srt_by_time() → per-clip SRT
   b. SUBTITLE PROCESSING:
      - Market line breaks, hook text injection
      - Translation (if enabled) via deep-translator
      - ASS conversion: srt_to_ass_bounce() or srt_to_ass_karaoke()
      - AI subtitle influence (if enabled)
   c. NARRATION (if TTS enabled):
      - generate_narration_audio() → edge-tts or XTTS
      - _maybe_cleanup_narration_audio() → optional DeepFilterNet
      - mix_narration_audio() → voice + BGM mix
   d. VIDEO CUT: cut_video() → ffprobe-verified segment extract
   e. RENDER: render_part_smart() →
      - motion-aware crop (motion_crop.py → MediaPipe/ByteTrack)
      - ASS subtitle burn-in
      - Speed adjustment (atempo + setpts)
      - Color grading (eq + unsharp filters)
      - NVENC hardware encode or libx264 CPU fallback
      - Loudness normalization, audio polish
   f. POST-RENDER ASSEMBLY:
      - _maybe_prepend_remotion_hook_intro() → animated title card
      - _maybe_prepend_asset_intro()
      - _maybe_append_asset_outro()
      - _maybe_apply_asset_logo()
   g. QA: _validate_render_output() → duration check, size check
   h. THUMBNAIL: extract_thumbnail_frame() → JPEG
   i. DB UPDATE: upsert_job_part() → status=done, output_file=...

10. JOB COMPLETION
    - attach_ai_visibility_summaries() → AI plan metadata to parts
    - append_rows() → XLS report
    - update_job_progress() → status=completed
```

---

## C. Job Lifecycle

```
States:
  queued      → job accepted by DB + job_manager heap
  starting    → scheduler popped from heap, marking DB
  running     → process_render() executing
  cancelling  → cancel signal sent by user
  cancelled   → JobCancelledError caught
  interrupted → server restart while job was running
  failed      → unhandled exception in process_render
  completed   → all parts done (even if some failed → completed_with_errors)

Transitions:
  POST /api/render/process          → queued
  job_manager._scheduler_loop()     → starting → running
  POST /api/render/{id}/cancel      → cancelling → (async) cancelled
  server restart                    → interrupted (no auto-restart)
  POST /api/render/resume/{id}      → queued (re-queued)
  POST /api/render/retry/{id}       → queued (failed parts only)

Cancel mechanism:
  cancel_registry.request_cancel(job_id) → sets threading.Event
  render_pipeline checks ev.is_set() between stages
  render_engine._run_ffmpeg_with_retry() → proc.terminate() on cancel_event
  ~1s cancel latency (checks every 1s in FFmpeg wait loop)

Resume mechanism:
  Reads last completed parts from DB (list_job_parts)
  Skips parts where status=done
  Re-runs only pending/failed parts
```

---

## D. File Lifecycle

```
Input files:
  YouTube source  → TEMP_DIR/preview/{session_id}/  (preview) or work_dir during render
  Local source    → referenced by path, never copied until render
  Preview H.264   → TEMP_DIR/preview/{session_id}/preview_h264.mp4 (browser-compatible)

Render work dirs:
  TEMP_DIR/render_{job_id}/          ← created at render start
    ├── source.mp4                   ← downloaded YouTube video (or symlink to local)
    ├── full.srt                     ← full Whisper transcription
    ├── part_{n}/
    │   ├── cut.mp4                  ← raw video cut
    │   ├── part_{n}.srt             ← sliced subtitle
    │   ├── part_{n}.ass             ← styled subtitle
    │   ├── narration.mp3            ← TTS audio
    │   ├── narration_cleaned.mp3    ← DeepFilterNet cleaned
    │   ├── bgm_mix.mp3              ← narration + BGM blend
    │   └── part_{n}_rendered.mp4   ← intermediate render
    └── {safe_title}_part_{n}.mp4   ← final output

Output files:
  output_dir/{title}_part_{n}.mp4   ← creator's selected output directory

Cleanup:
  _safe_unlink() — intermediate files deleted per-part
  prune_render_temp_dirs() — run on startup + every 30min background thread
  prune_preview_dirs() — 6h TTL on preview sessions

Scene/transcription cache:
  tempfile.gettempdir()/render_cache/scene_detect/{md5}.json   (72h TTL)
  tempfile.gettempdir()/render_cache/transcription/{md5}.srt   (72h TTL)
  tempfile.gettempdir()/render_cache/segment_scores/{md5}.json (72h TTL)
```

---

## E. State Lifecycle

```
Frontend state (stores):
  draftStore         ← user render configuration (persisted to sessionStorage)
  monitorStore       ← live job transport state (WS/polling data)
  renderSessionStore ← active render summary (driven by monitorStore)
  readinessStore     ← backend dependency availability (warmup status)
  systemStore        ← general system info

Backend state:
  jobs table         ← job_id, status, stage, progress_percent, payload_json, result_json
  job_parts table    ← per-clip status, scores, output_file path
  creator_prefs      ← singleton row, user preferences

Realtime sync:
  Backend: DB updated every part stage transition
  WS: polls DB every 500ms, sends only on change (fingerprint check)
  Frontend: monitorStore.update() → renderSessionStore.sync() → shell re-render

Persistence:
  SQLite WAL mode — concurrent reads during writes
  Thread-local DB connections for high-frequency render-path writers
  Job recovery on restart: queued/running → interrupted (user must resume)
```
