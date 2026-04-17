# Upgrade Checklist

Last updated: 2026-04-17

## Architecture V2 (2026-04)

- [x] Phase 1: audit — identified all render logic embedded in `routes/render.py`
- [x] Phase 2: stage + logging — `JobStage`, `JobPartStage`, `STAGE_TO_EVENT` in `core/stage.py`; `LOGS_DIR`, `REQUEST_LOG` in `core/config.py`
- [x] Phase 3: orchestration extraction — all pipeline logic moved to `orchestration/render_pipeline.py`; `run_render_pipeline()` with `load_session_fn` / `cleanup_session_fn` callbacks to avoid circular imports
- [x] Phase 4: documentation — README, ARCHITECTURE.md, STRUCTURE.md, RULES.md, doc/, cowork/ updated to reflect V2 state
- [x] `routes/render.py` is now a thin HTTP wrapper; `process_render()` is a 6-line delegation

## Stabilization (2026-04)

- [x] Prepare-source timeout: duration-aware `min(3600, 120 + 2×duration_sec)`, NVENC first with CPU fallback
- [x] Session reuse: `edit_session_id` → `load_session_fn` → use `sess["video_path"]` without downloading
- [x] Session-missing behavior: `RuntimeError` raised immediately if `edit_session_id` is set but session not found; never silent re-download
- [x] `_validate_render_source` bypass: when `edit_session_id` present, only `output_dir` leaf name is validated; source_mode/URL validation skipped
- [x] `_validate_output_dir` extracted as shared helper
- [x] `export_dir` in `prepare-source` response: `work_dir/"exports"` returned for both YouTube and local paths
- [x] Frontend `_ev.exportDir`: stored from `pd.export_dir` in both `openEditorView` and `openEditorView_withSession`
- [x] Editor output override: `output_mode='manual'`, `channel_code=''`, `render_output_subdir=''`; `export_dir` used as fallback when `output_dir` is empty
- [x] Editor error recovery: `_submitRenderPayload` returns `{ok, error}`; editor stays open on failure; error shown in `evStatusLine`
- [x] text_layers frontend normalizers: `_toOutline` / `_toShadow` / `_toBg` applied before submission
- [x] `evTxtFont` synced to `VALID_FONTS` / `evSubFont`: 12 fonts with matching labels (added Archivo Black, Teko, Luckiest Guy)
- [x] `_SuppressClientDisconnect` filter on `uvicorn.error`: suppresses harmless preview video disconnect messages
- [x] Downloader logging: "(will retry)" on intermediate failures; `(after N retries)` on success

## Render quality
- [x] Motion-aware crop integrated in real render flow
- [x] Aspect presets 3:4, 1:1, 9:16
- [x] Independent frame scale X/Y (default 100/106)
- [x] Effect presets: `slay_soft_01`, `slay_pop_01`, `story_clean_01`
- [x] Subtitle styles: `tiktok_bounce_v1`, `clean_bold_01`, `story_clean_01`, `pro_karaoke`, `viral_pop_anton`
- [x] Toggle subtitle/title overlay respected by pipeline
- [x] Codec options `h264` / `h265`
- [x] Encode tuning flags (profile/tune/x265 params, threads, faststart)

## Render speed
- [x] Whisper model cache enabled
- [x] Full-video transcription once, then slice SRT per segment
- [x] Faster cut path: `ffmpeg -c copy` first, fallback to re-encode
- [x] Retry for ffmpeg/whisper failures
- [x] Parallel part rendering with bounded adaptive workers

## Segment and scoring
- [x] Segment builder upgraded with boundary candidates and hook bias
- [x] Better min/max handling for segment duration
- [x] Viral scorer tuned for early-hook and duration fitness

## Stability and resume
- [x] Resume existing render job by `resume_job_id`
- [x] Resume endpoint `POST /api/render/resume/{job_id}`
- [x] Skip already-rendered parts on resume
- [x] Per-job logging with debug gating (`RENDER_DEBUG_LOG=1`)

## Temp cleanup and source retention
- [x] Keep original source copy at `channels/<channel>/upload/source`
- [x] Remove per-part temp files (`raw/srt/ass`) after each part
- [x] Remove whole `temp/<job_id>` directory at end of job
- [x] Request flags: `keep_source_copy`, `cleanup_temp_files`

## Upload
- [x] Upload payload expanded: `max_items`, `caption_prefix`, `include_hashtags`, `use_schedule`, `retry_count`, `headless`
- [x] Caption builder from filename + optional prefix + hashtags file
- [x] Schedule date/time filling in Playwright flow
- [x] Submit action + retry attempts
- [x] Move files to `uploaded` / `failed`

## UI/UX
- [x] Editor workflow: prepare-source → session → preview → configure → render
- [x] text_layers: up to 8 text overlays with drag positioning, font, outline, shadow, background
- [x] Realtime WebSocket progress (render + upload)
- [x] Smooth progress interpolation (eased toward backend values)
- [x] Live part tracking panel with per-part progress cards

## Next recommended work
- [ ] Automated tests for segment builder, resume flow, and upload schedule
- [ ] PO Token support for yt-dlp (when android client is blocked)
- [ ] ML viral scorer training once enough TikTok feedback is available
