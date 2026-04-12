# Upgrade Checklist

Last updated: 2026-04-08

## Render quality
- [x] Motion-aware crop integrated in real render flow
- [x] Aspect presets 3:4, 1:1, 9:16
- [x] Independent frame scale X/Y (default 100/106)
- [x] Effect presets: `slay_soft_01`, `slay_pop_01`, `story_clean_01`
- [x] Subtitle styles: `tiktok_bounce_v1`, `clean_bold_01`, `story_clean_01`
- [x] Toggle subtitle/title overlay respected by pipeline
- [x] Codec options `h264` / `h265`
- [x] Encode tuning flags (profile/tune/x265 params, threads, faststart)

## Render speed
- [x] Whisper model cache enabled
- [x] Full-video transcription once, then slice SRT per segment
- [x] Faster cut path: `ffmpeg -c copy` first, fallback to re-encode
- [x] Retry for ffmpeg/whisper failures
- [x] Reduced UI polling noise (default 6s)

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
- [x] Detailed upload report columns: status, attempts, caption, detail

## UI/UX
- [x] Dashboard redesigned for desktop/mobile
- [x] Better status widgets (job chip, stage, progress, activity feed)
- [x] Upload control panel expanded (dry run, schedule, hashtags, retries, max items)
- [x] Render controls expanded (profile/codec/model/retry/resume/cleanup toggles)

## Optimizations (2026-04-09)
- [x] CapCut-style Auto Reframe — face/body detection + CSRT tracker thay pixel-diff
- [x] Skip-frame scene detection — auto frame_skip theo FPS, nhanh 3-6x
- [x] WebSocket real-time progress thay HTTP polling (render + upload)
- [x] Playwright fallback selectors — _try_locator() + screenshot on error
- [x] Job queue persistent — ThreadPoolExecutor + interrupted status on restart
- [x] Improved viral scorer — Gaussian duration, pacing accel, ML-ready features
- [x] GPU encoding path (`h264_nvenc` / `hevc_nvenc`) with auto-detect
- [x] Parallel part rendering with bounded workers
- [x] Production-safe selector strategy for TikTok UI changes
- [x] yt-dlp updated 2025.3.31 → 2026.3.17, android client bypass 403

## Next recommended work
- [ ] Automated tests for segment builder, resume flow, and upload schedule
- [ ] PO Token support for yt-dlp (khi android client cũng bị chặn)
- [ ] ML viral scorer training khi có đủ feedback từ TikTok
