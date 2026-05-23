# UI_BACKEND_CONTRACT.md

**Status**: FROZEN — Phase 5.10 contract freeze.
**Date**: 2026-05-23
**Branch**: `restructure/output-timeline-architecture`
**Next phase**: Phase 6 UI overhaul may now begin against this document.

---

## 1. Purpose

This document is the single authoritative contract between the frontend UI and the
FastAPI backend. It defines:
- Every active API endpoint (method, path, purpose)
- Every removed/deprecated endpoint
- Every field in `RenderRequest` with UI status
- All valid option enum values
- AI UI control contract
- Quality report API response shapes
- Job detail and output library contract
- WebSocket event contract
- Rules the Phase 6 UI must follow

Any UI code that violates this contract (calls a removed endpoint, sends an
invalid enum, accesses a field marked DO_NOT_USE) is a bug, not a feature.

---

## 2. Current Active Frontend

**Active static directory**: `backend/static/` (legacy UI, default)

**Controlled by**: `STATIC_UI_VERSION` environment variable.

| Value | Directory | Mount |
|---|---|---|
| `legacy` (default, unset) | `backend/static/` | `/static` |
| `v2` | `backend/static-v2/` | `/assets` |

At time of Phase 5.10 freeze, `backend/static-v2/` does not exist. The active
frontend is always `backend/static/`.

**Key frontend files**:
- `backend/static/index.html` — main SPA shell (99 KB)
- `backend/static/js/render-ui.js` — render form and job display (286 KB)
- `backend/static/js/editor-view.js` — video editor (176 KB)
- `backend/static/js/editor-audio-runtime.js` — BGM file upload (8.6 KB)
- `backend/static/js/render-engine.js` — render API calls (20 KB)

---

## 3. Active API Endpoints

All prefixes are relative to `http://127.0.0.1:8000`.

### Core / System

| Endpoint | Method | Purpose | Used by UI? | Contract Status |
|---|---|---|---|---|
| `/health` | GET | Liveness probe; returns `{status, ui_version}` | No (internal) | ACTIVE |
| `/api/warmup/status` | GET | Whisper/AI warmup status | Yes (warmup.js) | ACTIVE |

### Render Endpoints (`/api/render/`)

| Endpoint | Method | Purpose | Used by UI? | Contract Status |
|---|---|---|---|---|
| `POST /api/render/process` | POST | Submit a render job; returns `{job_id, status, resume_mode}` | Yes | ACTIVE — PRIMARY |
| `POST /api/render/process/batch` | POST | Submit batch render (multiple YouTube URLs); returns `{batch_id, job_ids, count, status}` | Yes | ACTIVE |
| `POST /api/render/prepare-source` | POST | Download/validate source before editor opens; returns `{session_id, duration, title, export_dir}` | Yes (editor) | ACTIVE |
| `DELETE /api/render/prepare-source/{session_id}` | DELETE | Cancel active YouTube download + clean session | Yes (editor) | ACTIVE |
| `GET /api/render/preview-video/{session_id}` | GET | Serve H.264 preview video (FileResponse) | Yes (editor) | ACTIVE |
| `GET /api/render/preview-transcript/{session_id}` | GET | Whisper-tiny transcript for editor subtitle preview; returns `{segments}` | Yes (editor) | ACTIVE |
| `POST /api/render/upload-local` | POST | Accept browser video file upload to channel source dir; returns `{path, filename, size}` | Yes | ACTIVE |
| `POST /api/render/download-health` | POST | Check YouTube URL download health | Yes | ACTIVE |
| `POST /api/render/quick-process` | POST | One-shot download + optional transform + save; returns status dict | Yes | ACTIVE |
| `POST /api/render/resume/{job_id}` | POST | Re-queue a job from where it stopped | Yes | ACTIVE |
| `POST /api/render/retry/{job_id}` | POST | Re-run only failed parts | Yes | ACTIVE |
| `POST /api/render/{job_id}/cancel` | POST | Signal cancel; returns `{job_id, status: "cancelling"}` | Yes | ACTIVE |
| `GET /api/render/jobs/{job_id}` | GET | Render job detail (from render router) | Yes | ACTIVE |
| `GET /api/render/jobs/{job_id}/parts/{part_no}/media` | GET | Stream rendered clip with Range support | Yes (video player) | ACTIVE |
| `GET /api/render/jobs/{job_id}/parts/{part_no}/thumbnail` | GET | JPEG thumbnail from rendered clip | Yes (gallery) | ACTIVE |
| `GET /api/render/queue-status` | GET | Active render count + max slots | Yes | ACTIVE |
| `GET /api/render/ai-diagnostics` | GET | AI runtime dependency status | Yes (dev panel) | ACTIVE |

### Job Management Endpoints (`/api/jobs/`)

| Endpoint | Method | Purpose | Used by UI? | Contract Status |
|---|---|---|---|---|
| `GET /api/jobs` | GET | List all jobs (unbounded — see M9 debt) | Yes (history) | ACTIVE |
| `GET /api/jobs/history` | GET | Paginated job history; params: `limit`, `offset` | Yes (history) | ACTIVE — PREFERRED |
| `GET /api/jobs/queue/status` | GET | Queue depth: `{max_concurrent, active, pending, available_slots}` | Yes | ACTIVE |
| `GET /api/jobs/{job_id}` | GET | Single job row | Yes | ACTIVE |
| `GET /api/jobs/{job_id}/parts` | GET | All parts for a job | Yes | ACTIVE |
| `GET /api/jobs/{job_id}/logs` | GET | Tail of job log file; param: `lines` (default 120) | Yes (log panel) | ACTIVE |
| `GET /api/jobs/{job_id}/parts/{part_no}/stream` | GET | Stream rendered clip (simple FileResponse, no Range) | Yes | ACTIVE |
| `WS /api/jobs/{job_id}/ws` | WebSocket | Live job progress stream; closes on terminal status | Yes | ACTIVE |
| `POST /api/jobs/cleanup/logs` | POST | Prune old log files | No (admin) | ACTIVE |
| `DELETE /api/jobs/{job_id}` | DELETE | Delete job + optionally its output files | Yes | ACTIVE |
| `GET /api/jobs/{job_id}/parts/{part_no}/quality` | GET | Single-part quality report sidecar | Not yet (Phase 6) | ACTIVE — NEW (5.9) |
| `GET /api/jobs/{job_id}/quality` | GET | Aggregated quality summary; param: `include_reports` | Not yet (Phase 6) | ACTIVE — NEW (5.9) |

### File Upload Endpoint

| Endpoint | Method | Purpose | Used by UI? | Contract Status |
|---|---|---|---|---|
| `POST /api/upload-file` | POST | Upload BGM/audio asset for editor; returns `{path}` | Yes (editor audio) | ACTIVE |

### Other Active Routers

The following router groups are registered but not documented in detail here
(not part of the render UI contract):

| Router prefix | Purpose |
|---|---|
| `/api/channels/` | Channel management |
| `/api/download/` | YouTube download domain |
| `/api/voice/` | TTS voice preview |
| `/api/viral/` | Viral scoring |
| `/api/subtitle/` | Subtitle preview |
| `/api/creator/` | Creator preferences |

---

## 4. Removed / Deprecated Endpoints

These endpoints no longer exist. Any UI code calling them will receive 404 or
405 responses. **Phase 6 UI must not reference these.**

| Endpoint | Removed In | Reason |
|---|---|---|
| `POST /api/upload/accounts/ensure` | Phase 4F.5A | TikTok upload domain deleted |
| `POST /api/upload/login/check` | Phase 4F.5A | TikTok upload domain deleted |
| `POST /api/upload/login/start` | Phase 4F.5A | TikTok upload domain deleted |
| `POST /api/upload/queue/add` | Phase 4F.5A | TikTok upload domain deleted |
| `GET /api/upload/queue` | Phase 4F.5A | TikTok upload domain deleted |
| `POST /api/upload/queue/{id}/run` | Phase 4F.5A | TikTok upload domain deleted |
| `POST /api/upload/queue/{id}/cancel` | Phase 4F.5A | TikTok upload domain deleted |
| Any `POST /api/upload/*` | Phase 4F.5A–C | Entire upload domain removed |

**Audit result (Phase 5.10)**: Zero occurrences of `/api/upload/` (slash-terminated
old upload domain) found in `backend/static/js/*.js`. Only two occurrences of
`/api/upload-file` (the hyphen form, BGM upload) exist — these are correct.

---

## 5. RenderRequest UI Field Contract

`POST /api/render/process` accepts a JSON body matching `RenderRequest` from
`backend/app/models/schemas.py`.

Status codes:
- **UI_READY** — show in Phase 6 UI, user-facing control
- **ADVANCED_ONLY** — show in advanced/pro section only
- **INTERNAL_ONLY** — set programmatically, not shown in UI
- **DEPRECATED** — do not add to new UI (legacy compat only)
- **DO_NOT_USE** — known broken or replaced; never send

### Source Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `source_mode` | str | `"youtube"` | Yes | Source type | UI_READY | `"youtube"` or `"local"` |
| `youtube_url` | str | `""` | Conditional | YouTube URL | UI_READY | Required when `source_mode=youtube` |
| `youtube_urls` | list[str] | `[]` | Conditional | Multiple YouTube URLs | UI_READY | Used by batch endpoint |
| `source_video_path` | str | `""` | Conditional | Local video path | UI_READY | Required when `source_mode=local` |
| `source_quality_mode` | str | `"standard_1080"` | No | Download quality | UI_READY | See quality enum below |

### Output Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `output_mode` | str | `"manual"` | Yes | Output mode | UI_READY | `"manual"` or `"channel"` (channel coerced to manual) |
| `channel_code` | str | `""` | Conditional | Channel | ADVANCED_ONLY | Required when `output_mode=channel` (legacy) |
| `output_dir` | str | `""` | Yes | Output folder | UI_READY | Must be non-empty |
| `render_output_subdir` | str | `""` | No | Subdirectory | ADVANCED_ONLY | |
| `keep_source_copy` | bool | `false` | No | Keep source | ADVANCED_ONLY | |
| `cleanup_temp_files` | bool | `true` | No | Auto-cleanup | ADVANCED_ONLY | |

### Resume Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `resume_job_id` | str | null | No | Resume job | INTERNAL_ONLY | Set by resume endpoint |
| `resume_from_last` | bool | `false` | No | — | INTERNAL_ONLY | Set by resume endpoint |

### Encoding / Quality Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `render_profile` | str | `"quality"` | No | Render profile | UI_READY | `"fast"/"balanced"/"quality"/"best"` |
| `render_preset` | str | `"custom"` | No | Preset | ADVANCED_ONLY | |
| `render_preset_id` | str | null | No | Preset ID | INTERNAL_ONLY | |
| `render_preset_label` | str | null | No | Preset label | INTERNAL_ONLY | |
| `video_preset` | str | null | No | Encoder preset | ADVANCED_ONLY | e.g. `"medium"` |
| `video_crf` | int | null | No | CRF | ADVANCED_ONLY | |
| `video_codec` | str | `"h264"` | No | Codec | ADVANCED_ONLY | |
| `audio_bitrate` | str | `"192k"` | No | Audio bitrate | ADVANCED_ONLY | |
| `encoder_mode` | str | `"auto"` | No | Encoder mode | ADVANCED_ONLY | `"auto"/"cpu"/"nvenc"` |
| `output_fps` | int | `60` | No | Output FPS | UI_READY | |
| `whisper_model` | str | `"auto"` | No | Whisper model | ADVANCED_ONLY | |

### Segmentation Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `auto_detect_scene` | bool | `true` | No | Auto scene detect | UI_READY | |
| `min_part_sec` | int | `15` | No | Min clip length (s) | UI_READY | AI pacing default: 15 |
| `max_part_sec` | int | `60` | No | Max clip length (s) | UI_READY | AI pacing default: 60 |
| `max_export_parts` | int | null | No | Max clips | UI_READY | null = unlimited |
| `part_order` | str | `"viral"` | No | Part order | UI_READY | `"viral"/"sequential"` |

### Subtitle Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `add_subtitle` | bool | `true` | No | Enable subtitles | UI_READY | |
| `subtitle_style` | str | `"pro_karaoke"` | No | Subtitle style | UI_READY | See subtitle style enum below |
| `sub_font_size` | int | `46` | No | Font size | UI_READY | |
| `sub_font` | str | `"Bungee"` | No | Font | ADVANCED_ONLY | |
| `sub_margin_v` | int | `170` | No | Vertical margin | ADVANCED_ONLY | |
| `sub_color` | str | `"#FFFFFF"` | No | Text color | ADVANCED_ONLY | |
| `sub_highlight` | str | `"#FFFF00"` | No | Highlight color | ADVANCED_ONLY | |
| `sub_outline` | int | `3` | No | Outline size | ADVANCED_ONLY | |
| `sub_x_percent` | float | `50.0` | No | Horizontal position | ADVANCED_ONLY | |
| `highlight_per_word` | bool | `false` | No | Word highlight | UI_READY | |
| `subtitle_viral_min_score` | int | `0` | No | Min viral score | ADVANCED_ONLY | |
| `subtitle_viral_top_ratio` | float | `1.0` | No | Top ratio | ADVANCED_ONLY | |
| `subtitle_only_viral_high` | bool | `false` | No | Viral only | ADVANCED_ONLY | |
| `subtitle_transcription_engine` | Literal | `"default"` | No | Transcription engine | ADVANCED_ONLY | `"default"/"faster_whisper"/"whisperx"` |
| `subtitle_translate_enabled` | bool | `false` | No | Translate subtitles | UI_READY | |
| `subtitle_target_language` | str | `"en"` | No | Target language | UI_READY | `"vi"/"en"/"ja"` |

### Frame / Crop Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `aspect_ratio` | str | `"3:4"` | No | Aspect ratio | UI_READY | See aspect ratio enum below |
| `frame_scale_x` | int | `100` | No | X scale | ADVANCED_ONLY | |
| `frame_scale_y` | int | `106` | No | Y scale | ADVANCED_ONLY | |
| `motion_aware_crop` | bool | `false` | No | Motion crop | ADVANCED_ONLY | |
| `reframe_mode` | str | `"center"` | No | Reframe | ADVANCED_ONLY | `"center"/"smart"` |

### Overlay / Effect Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `add_title_overlay` | bool | `false` | No | Title overlay | UI_READY | |
| `title_overlay_text` | str | `""` | No | Title text | UI_READY | |
| `effect_preset` | str | `"slay_soft_01"` | No | Visual effect | UI_READY | See effect preset enum |
| `loudnorm_enabled` | bool | `true` | No | Loudness normalize | ADVANCED_ONLY | |
| `audio_cleanup_engine` | Literal | `"none"` | No | Audio cleanup | ADVANCED_ONLY | `"none"/"deepfilternet"` |
| `tts_engine` | Literal | `"edge"` | No | TTS engine | ADVANCED_ONLY | `"edge"/"xtts"` |
| `remotion_hook_intro` | bool | `true` | No | Hook intro | UI_READY | |

### Reup Mode Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `reup_mode` | bool | `false` | No | Reup mode | UI_READY | |
| `reup_overlay_enable` | bool | `true` | No | Reup overlay | UI_READY | |
| `reup_overlay_opacity` | float | `0.08` | No | Overlay opacity | ADVANCED_ONLY | |
| `reup_bgm_enable` | bool | `false` | No | BGM enable | UI_READY | |
| `reup_bgm_path` | str | null | No | BGM file path | UI_READY | Use `/api/upload-file` to get path |
| `reup_bgm_gain` | float | `0.18` | No | BGM volume | ADVANCED_ONLY | |
| `playback_speed` | float | `1.07` | No | Playback speed | UI_READY | Clamped `[0.5, 1.5]` by pipeline |

### Parallel / Retry Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `max_parallel_parts` | int | `0` | No | Max parallel | ADVANCED_ONLY | 0 = adaptive |
| `retry_count` | int | `2` | No | Retry count | ADVANCED_ONLY | |

### Editor Session Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `edit_session_id` | str | null | No | Session ID | INTERNAL_ONLY | From `prepare-source` |
| `edit_trim_in` | float | `0` | No | Trim start | UI_READY | Editor control |
| `edit_trim_out` | float | `0` | No | Trim end | UI_READY | Editor control |
| `edit_volume` | float | `1.0` | No | Volume | UI_READY | Editor control |
| `text_layers` | list[TextLayerConfig] | `[]` | No | Text layers | UI_READY | Editor text overlay |
| `voice_enabled` | bool | `false` | No | TTS voice | UI_READY | |
| `voice_language` | str | `"vi-VN"` | No | Voice language | UI_READY | `"vi-VN"/"ja-JP"/"en-US"/"en-GB"` |
| `voice_gender` | str | `"female"` | No | Voice gender | UI_READY | `"female"/"male"` |
| `voice_rate` | str | `"+0%"` | No | Voice rate | ADVANCED_ONLY | |
| `voice_mix_mode` | str | `"replace_original"` | No | Voice mix | ADVANCED_ONLY | `"replace_original"/"keep_original_low"` |
| `voice_text` | str | null | No | Voice text | UI_READY | Required when `voice_source=manual` |
| `voice_source` | str | `"manual"` | No | Voice source | UI_READY | `"manual"/"subtitle"/"translated_subtitle"` |
| `voice_id` | str | null | No | Voice ID | ADVANCED_ONLY | |
| `subtitle_edits` | list | null | No | Subtitle edits | INTERNAL_ONLY | Editor subtitle corrections |
| `market_viral` | dict | null | No | Market viral | INTERNAL_ONLY | |
| `viral_market` | str | null | No | Viral market | INTERNAL_ONLY | |
| `hook_applied_text` | str | null | No | Hook text | INTERNAL_ONLY | |
| `hook_apply_enabled` | bool | `false` | No | Hook apply | UI_READY | |
| `hook_overlay_enabled` | bool | `false` | No | Hook overlay | UI_READY | |
| `hook_score` | float | null | No | Hook score | INTERNAL_ONLY | |

### AI Director Group

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `ai_director_enabled` | bool | `false` | No | AI Director | UI_READY | Master AI enable |
| `ai_mode` | str | `"viral_tiktok"` | No | AI mode | ADVANCED_ONLY | |
| `ai_auto_cut` | bool | `true` | No | AI auto cut | ADVANCED_ONLY | |
| `ai_target_duration` | int | null | No | AI target duration | ADVANCED_ONLY | |
| `ai_use_semantic_hooks` | bool | `true` | No | Semantic hooks | ADVANCED_ONLY | |
| `ai_use_rag_memory` | bool | `false` | No | RAG memory | ADVANCED_ONLY | Disabled by default |
| `ai_render_influence_enabled` | bool | `false` | No | AI render influence | ADVANCED_ONLY | Opt-in |
| `ai_beat_execution_enabled` | bool | `false` | No | Beat execution | ADVANCED_ONLY | |
| `ai_timing_mutation_enabled` | bool | `false` | No | Timing mutation | ADVANCED_ONLY | Advisory-only |
| `multi_variant` | bool | `false` | No | Multi-variant | UI_READY | |
| `target_platform` | str | `"youtube_shorts"` | No | Target platform | UI_READY | See platform enum |
| `cta_enabled` | bool | `false` | No | CTA | UI_READY | |
| `cta_type` | str | `"auto"` | No | CTA type | UI_READY | `"auto"/"comment"/"part_2"/"follow"` |
| `creator_dna` | dict | `{}` | No | Creator DNA | INTERNAL_ONLY | Computed by creator-dna.js |
| `combined_scoring_enabled` | bool | `false` | No | Combined scoring | ADVANCED_ONLY | |
| `adaptive_scoring_enabled` | bool | `false` | No | Adaptive scoring | ADVANCED_ONLY | |
| `auto_best_export_enabled` | bool | `false` | No | Auto-best export | ADVANCED_ONLY | |
| `auto_best_export_count` | int | `3` | No | Auto-best count | ADVANCED_ONLY | |

### Pro Timeline Steering Group (UP26)

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `clip_lock` | list[dict] | null | No | Clip lock | UI_READY | `[{start_sec, end_sec}]` |
| `clip_exclude` | list[dict] | null | No | Clip exclude | UI_READY | `[{start_sec, end_sec}]` |
| `structure_bias` | str | null | No | Structure bias | UI_READY | `"hook"/"balanced"/"story"` |
| `subtitle_emphasis` | str | null | No | Subtitle emphasis | UI_READY | `"subtle"/"balanced"/"aggressive"` |

### Creator Asset Intelligence Group (UP27)

| Field | Type | Default | Required? | UI Label | Status | Notes |
|---|---|---|---|---|---|---|
| `asset_logo_path` | str | null | No | Logo path | UI_READY | Absolute path to PNG/JPEG |
| `asset_intro_path` | str | null | No | Intro path | UI_READY | Absolute path to intro clip |
| `asset_outro_path` | str | null | No | Outro path | UI_READY | Absolute path to outro clip |
| `asset_music_profile` | str | null | No | Music profile | UI_READY | `"clean"/"energetic"/"soft"` |
| `asset_brand_subtitle` | str | null | No | Brand subtitle style | ADVANCED_ONLY | |

---

## 6. Option Enums

### 6.1 Platform Options (`target_platform`)

| Value | Label | Description | Backend field |
|---|---|---|---|
| `"tiktok"` | TikTok | Short-form vertical, 9:16 native | `target_platform` |
| `"youtube_shorts"` | YouTube Shorts | Default — vertical format | `target_platform` |
| `"instagram_reels"` | Instagram Reels | Square or vertical | `target_platform` |

**Safe default**: `"youtube_shorts"`

### 6.2 Aspect Ratio Options (`aspect_ratio`)

| Value | Label | Description | Backend field |
|---|---|---|---|
| `"9:16"` | 9:16 Vertical | Full-screen vertical (TikTok native) | `aspect_ratio` |
| `"3:4"` | 3:4 Portrait | Default — portrait, safe for all platforms | `aspect_ratio` |
| `"1:1"` | 1:1 Square | Square format | `aspect_ratio` |
| `"16:9"` | 16:9 Landscape | Standard widescreen | `aspect_ratio` |
| `"4:3"` | 4:3 Standard | Classic TV ratio | `aspect_ratio` |

**Safe default**: `"3:4"`

### 6.3 Subtitle Style Options (`subtitle_style`)

These are the canonical preset IDs from `backend/app/services/subtitles/styles.py`.

| Value | Label | Description | Backend field |
|---|---|---|---|
| `"tiktok_bounce_v1"` | TikTok Bounce | Classic bounce, Bungee font, outline shadow | `subtitle_style` |
| `"bold_cap"` | Bold Cap | Bold, large Bungee, auto-scale | `subtitle_style` |
| `"story_clean_01"` | Story Clean | Montserrat, soft bounce, editorial | `subtitle_style` |
| `"viral_bold"` | Viral Bold | Bold Bungee, boosted size, karaoke highlight | `subtitle_style` |
| `"clean_pro"` | Clean Pro | Inter font, clean professional look | `subtitle_style` |
| `"boxed_caption"` | Boxed Caption | Opaque box behind text, no bounce | `subtitle_style` |
| `"viral"` | Viral | Anton font, 50px, thick outline, TikTok native | `subtitle_style` |
| `"clean"` | Clean | Inter, minimal outline, wide margins | `subtitle_style` |
| `"story"` | Story | Montserrat, cinematic, emotional content | `subtitle_style` |
| `"gaming"` | Gaming | Anton, box-backed, fast-motion readability | `subtitle_style` |

**Legacy aliases** (accepted, auto-resolved — do NOT use in new UI):
| Alias | Resolves to |
|---|---|
| `"viral_clean_montserrat"` | `"tiktok_bounce_v1"` |
| `"viral_soft_poppins"` | `"tiktok_bounce_v1"` |
| `"viral_pop_anton"` | `"tiktok_bounce_v1"` |
| `"viral_compact_barlow"` | `"tiktok_bounce_v1"` |
| `"clean_bold_01"` | `"clean_pro"` |
| `"pro_karaoke"` | Not in canonical presets — falls back to `"tiktok_bounce_v1"` |

**Safe default**: `"tiktok_bounce_v1"`

### 6.4 Effect Preset Options (`effect_preset`)

From `backend/app/services/render/ffmpeg_helpers.py` (`_effect_filter()` supported presets):

| Value | Label | Description | Backend field |
|---|---|---|---|
| `"slay_soft_01"` | Natural Cinematic | Default — natural look, light sharpening | `effect_preset` |
| `"slay_pop_01"` | High Energy | Boosted contrast/saturation/unsharp | `effect_preset` |
| `"story_clean_01"` | Story Clean | Subtle — low contrast/saturation, soft sharpening | `effect_preset` |
| `"social_bright"` | Social Bright | High saturation, strong brightness | `effect_preset` |
| `"cinematic_soft"` | Cinematic Soft | Desaturated, soft, denoised | `effect_preset` |
| `"high_contrast"` | High Contrast | Maximum contrast, heaviest unsharp | `effect_preset` |

**Safe default**: `"slay_soft_01"`

**AI visual intensity → preset mapping** (renderer-owned, not UI-selectable):
| AI hint | Maps to preset |
|---|---|
| `"low"` | `"story_clean_01"` |
| `"medium"` | `"slay_soft_01"` |
| `"high"` | `"slay_pop_01"` |

### 6.5 Source Quality Mode (`source_quality_mode`)

| Value | Label | Description | Backend field |
|---|---|---|---|
| `"standard_1080"` | Standard 1080p | Default — safe, fast download | `source_quality_mode` |
| `"high_1440"` | High 1440p | Higher quality, larger file | `source_quality_mode` |
| `"best_available"` | Best Available | Highest quality yt-dlp can fetch | `source_quality_mode` |

**Safe default**: `"standard_1080"`

### 6.6 Render Profile (`render_profile`)

| Value | Label | Backend field |
|---|---|---|
| `"fast"` | Fast | `render_profile` |
| `"balanced"` | Balanced | `render_profile` |
| `"quality"` | Quality (default) | `render_profile` |
| `"best"` | Best | `render_profile` |

### 6.7 Duration Bounds

| Parameter | Min | Max | Default | Notes |
|---|---|---|---|---|
| `min_part_sec` | 5 | 300 | 15 | AI pacing hint applies when AI Director enabled and user has not changed default |
| `max_part_sec` | 10 | 300 | 60 | AI pacing hint applies when AI Director enabled and user has not changed default |
| `playback_speed` | 0.5 | 1.5 | 1.07 | Hard clamped by pipeline at all entry points |

### 6.8 Output Count Limits

| Parameter | Min | Max | Default | Notes |
|---|---|---|---|---|
| `max_export_parts` | 1 | unlimited (null) | null | null = export all scored clips |
| `max_parallel_parts` | 0 | cpu_count | 0 | 0 = adaptive |
| `ai_clip_candidate_limit` | 1 | 20 | 5 | Validated by field_validator |
| `ai_clip_target_count` | 1 | 20 | 3 | Validated by field_validator |
| `ai_clip_batch_limit` | 1 | 20 | 5 | Validated by field_validator |

---

## 7. AI Controls Contract

### 7.1 What the UI Should Show for AI

| UI Control | Mapped Field | Default | Notes |
|---|---|---|---|
| AI Director toggle | `ai_director_enabled` | `false` | Master switch; all AI behavior off when false |
| Target platform (also affects AI) | `target_platform` | `"youtube_shorts"` | Used by knowledge retriever as filter |
| Clip duration min/max | `min_part_sec` / `max_part_sec` | 15 / 60 | AI pacing hints apply when user leaves at defaults |
| Multi-variant output | `multi_variant` | `false` | Produces 3 variant clips per segment |
| CTA enable | `cta_enabled` | `false` | Adds call-to-action at segment end |
| CTA type | `cta_type` | `"auto"` | `"auto"/"comment"/"part_2"/"follow"` |

### 7.2 What the UI Should Display (AI Status)

| Display | Source endpoint | Notes |
|---|---|---|
| AI readiness | `GET /api/render/ai-diagnostics` | Shows whether FAISS, sentence-transformers, knowledge index are available |
| Warmup status | `GET /api/warmup/status` | Whisper model cache status |

### 7.3 AI Contract Rules for UI

1. AI is **advisory only at render time** — no LLM API calls occur during renders.
2. AI Director results (`execution_hints`) are validated and clamped before render influence.
3. If `ai_director_enabled=false`, all AI fields are ignored. Safe to omit them entirely.
4. Sending `ai_director_enabled=true` without knowledge data degrades gracefully (renders proceed with defaults).
5. Do NOT let users set `ai_render_influence_enabled=true` unless they understand the consequence (AI may override visual preset when `effect_preset` is at default).

### 7.4 AI Render Influence Summary (Phase 5.3–5.7)

| AI Hook | Active? | User Override? | Notes |
|---|---|---|---|
| Hook overlay gate | Yes (5.3) | hook_overlay_enabled field | AI can disable hook overlay |
| Pacing (segment duration) | Yes (5.4) | Any non-default min/max_part_sec | AI sets segment duration bounds from knowledge |
| Subtitle emphasis | Yes (5.5) | No direct override | AI sets emphasis level inside subtitle pass |
| Visual intensity | Yes (5.7) | Any non-default effect_preset | AI maps low/medium/high to preset; user preset wins |

---

## 8. Quality Report API Contract

### 8.1 Single-Part Quality Report

**Endpoint**: `GET /api/jobs/{job_id}/parts/{part_no}/quality`

**Security**:
- `job_id`: alphanumeric + hyphens/underscores, max 128 chars. Invalid → 400.
- `part_no`: positive integer only. Invalid (0, negative, non-integer) → 400.
- Missing job → 404. Missing part → 404. Missing report sidecar → 404.
- Response never contains filesystem paths.

**Response shape** (from `QualityReport.to_dict()`):
```json
{
  "job_id": "abc123",
  "part_no": 1,
  "score": 85.0,
  "issues": [
    {
      "code": "audio_missing",
      "severity": "warning",
      "message": "No audio stream detected in output",
      "confidence": 0.95,
      "part_no": 1,
      "evidence": {},
      "recommended_action": "Check source audio"
    }
  ],
  "metrics": {},
  "ai_trace_refs": [],
  "created_at": "2026-05-23T12:00:00"
}
```

### 8.2 Job-Level Quality Summary

**Endpoint**: `GET /api/jobs/{job_id}/quality`

**Query params**: `include_reports=false` (default) or `include_reports=true`

**Response shape**:
```json
{
  "job_id": "abc123",
  "parts": [
    {
      "part_no": 1,
      "available": true,
      "score": 85.0,
      "issue_count": 2,
      "critical_count": 0,
      "error_count": 0,
      "warning_count": 2,
      "info_count": 0,
      "report": null
    }
  ],
  "summary": {
    "available_parts": 3,
    "total_parts": 3,
    "average_score": 87.5,
    "critical_count": 0,
    "error_count": 1,
    "warning_count": 4,
    "info_count": 2
  }
}
```

When `include_reports=true`, each part's `"report"` key contains the full `QualityReport.to_dict()` object instead of null.

### 8.3 UI Score Thresholds

| Score Range | Label | Suggested UI Color |
|---|---|---|
| >= 85 | Good | Green |
| 70–84 | Needs review | Yellow |
| 50–69 | Warning | Orange |
| < 50 | Poor | Red |

### 8.4 Quality Issue Severity Levels

| Severity | Score Penalty | What it means |
|---|---|---|
| `"critical"` | −100 (score → 0) | Output is probably broken (missing file, zero-byte) |
| `"error"` | −25 | Significant problem (bad duration, ffprobe failure) |
| `"warning"` | −10 | Potential quality concern (no audio, subtitle flash, dark first frame) |
| `"info"` | −2 | Advisory notice |

---

## 9. Job Detail Contract

`GET /api/jobs/{job_id}` returns the raw DB row. Key fields:

| Field | Type | Notes |
|---|---|---|
| `job_id` | str | UUID |
| `kind` | str | `"render"` or `"render_batch"` |
| `status` | str | See status values below |
| `stage` | str | Current pipeline stage |
| `progress_percent` | int | 0–100 |
| `message` | str | Human-readable status |
| `payload_json` | str (JSON) | Serialized `RenderRequest` |
| `result_json` | str (JSON) | Output metadata |
| `created_at` | str | SQLite UTC timestamp |
| `updated_at` | str | SQLite UTC timestamp |

**Job status values**:
`queued` | `running` | `completed` | `completed_with_errors` | `failed` | `interrupted` | `cancelled` | `cancelling`

**Terminal statuses** (WebSocket closes when reached):
`completed` | `completed_with_errors` | `failed` | `interrupted` | `cancelled`

`GET /api/jobs/{job_id}/parts` returns `{items: [...]}` where each part has:

| Field | Type | Notes |
|---|---|---|
| `part_no` | int | 1-indexed |
| `status` | str | `done` / `failed` / `waiting` / `cutting` / `transcribing` / `rendering` / `downloading` |
| `progress_percent` | int | 0–100 |
| `output_file` | str | Absolute path to rendered clip |
| `updated_at` | str | Timestamp |

---

## 10. Output Library Contract

The output library (rendered clips) is served via:
- `GET /api/render/jobs/{job_id}/parts/{part_no}/media` — Range-aware streaming (preferred for video player)
- `GET /api/render/jobs/{job_id}/parts/{part_no}/thumbnail` — JPEG thumbnail (params: `t=0.5`, `w=320`)
- `GET /api/jobs/{job_id}/parts/{part_no}/stream` — Simple FileResponse (no Range support)

**Security**: All paths are resolved from DB, never from user input. No path traversal risk.

---

## 11. WebSocket / Event Contract

**Endpoint**: `WS /api/jobs/{job_id}/ws`

**Push interval**: Every 500 ms, or immediately when state changes.

**Message format** (JSON):
```json
{
  "job": { /* same as GET /api/jobs/{job_id} */ },
  "parts": [ /* same as GET /api/jobs/{job_id}/parts items */ ],
  "summary": {
    "total_parts": 3,
    "completed_parts": 2,
    "failed_parts": 0,
    "pending_parts": 1,
    "processing_parts": 0,
    "in_progress_count": 0,
    "active_parts": [],
    "stuck_parts": [],
    "current_part": null,
    "current_stage": null,
    "overall_progress_percent": 66.7,
    "parts_percent": 66.7
  }
}
```

**Error message** (unknown job):
```json
{"error": "not_found"}
```

**Terminal behavior**: WebSocket closes automatically when `job.status` enters a terminal state (`completed`, `failed`, `cancelled`, `interrupted`, `completed_with_errors`). Frontend must not attempt reconnect for terminal states.

**Fingerprint change detection**: The WS only sends when one of these changes: `status`, `stage`, `progress_percent`, `message`, `parts[*].status`, `parts[*].progress_percent`, `summary.completed_parts`, `summary.failed_parts`, `summary.stuck_parts.length`. Pure heartbeat ticks (only `updated_at` changes) are suppressed.

---

## 12. Frontend Implementation Rules

1. **Always use `/api/upload-file`** (with hyphen) for BGM/audio asset uploads. Never call `/api/upload/*` (slash, old upload domain).
2. **Validate enums client-side** before sending. Do not rely on server 422 errors for UX.
3. **Use WebSocket** (`/api/jobs/{job_id}/ws`) for live progress. Fall back to polling `GET /api/jobs/{job_id}` only if WebSocket fails.
4. **Use paginated history** (`GET /api/jobs/history?limit=20&offset=N`) instead of `GET /api/jobs` for large job lists.
5. **Never show raw filesystem paths** to users. Display only filenames.
6. **Display quality scores** using the thresholds from §8.3 (>=85 Good, 70–84 Needs Review, etc.).
7. **Do not send** `DO_NOT_USE` or `INTERNAL_ONLY` fields from the UI — let the backend handle them.
8. **Set `output_dir` always** — it is required even though the type is Optional. The backend rejects empty `output_dir`.
9. **Respect speed clamp**: UI should validate `playback_speed` in `[0.5, 1.5]` before submission.
10. **Do not call quality endpoints** in polling loops — they hit the filesystem. Call them on demand (when user views a clip).

---

## 13. Do-Not-Use Fields / Endpoints

### Fields — never send from new UI code

| Field | Reason |
|---|---|
| `output_mode = "channel"` | Coerced to "manual" silently. Legacy only. |
| `channel_code` | Upload domain removed. Only used for log path resolution. |
| `resume_job_id` | Set by resume/retry endpoints, not by UI directly. |
| `resume_from_last` | Same as above. |
| `creator_dna` | Computed by creator-dna.js — never hardcode. |
| `hook_score` | Computed by pipeline. |
| `market_viral`, `viral_market` | Internal scoring state. |
| `render_preset_id`, `render_preset_label` | Not used by current pipeline. |
| `ai_use_rag_memory` | RAG memory not active in production render path. |

### Endpoints — never call from new UI code

| Endpoint | Reason |
|---|---|
| `POST /api/upload/*` | Upload domain removed. Will 404. |
| `GET /api/jobs` (unbounded) | Performance risk. Use `GET /api/jobs/history` instead. |
| `GET /api/jobs/{id}/parts/{no}/stream` | No Range support. Use `/media` endpoint instead. |

---

## 14. Phase 6 UI Overhaul Checklist

The following items must be addressed in Phase 6 before the new UI ships:

- [ ] **Quality panel**: Add UI panel showing quality score badge per clip (use §8.3 thresholds)
- [ ] **Quality on demand**: Call `GET /api/jobs/{id}/parts/{no}/quality` when user opens a clip detail
- [ ] **Job-level quality summary**: Show `GET /api/jobs/{id}/quality` aggregate on job row in history
- [ ] **Subtitle style enum sync**: UI dropdown must list exactly the 10 canonical presets from §6.3 (not aliases)
- [ ] **Effect preset enum sync**: UI dropdown must list exactly the 6 presets from §6.4
- [ ] **Remove `pro_karaoke`** from any UI dropdown — it resolves to `tiktok_bounce_v1` but is not canonical
- [ ] **Range-aware video player**: Use `/api/render/jobs/{id}/parts/{no}/media` (with Range headers) not `/stream`
- [ ] **AI Director section**: Expose `ai_director_enabled`, `target_platform`, `multi_variant` as a toggleable panel
- [ ] **Speed validation**: Prevent playback_speed outside [0.5, 1.5] in UI before submit
- [ ] **Upload-file for BGM only**: Keep `/api/upload-file` for BGM, nothing else
- [ ] **Stale JS cleanup**: Remove any remaining `/api/upload/` references (none found in Phase 5.10 audit, but verify after Phase 6 JS changes)
- [ ] **WebSocket terminal handling**: On terminal status, close WS and do not reconnect
- [ ] **Paginated history**: History page must use `/api/jobs/history` not `/api/jobs`
- [ ] **Output dir required**: UI must require output_dir, not default to empty

---

## Changelog

| Date | Phase | Change |
|---|---|---|
| 2026-05-23 | 5.10 | Initial contract freeze — all active endpoints, RenderRequest field contract, option enums, AI UI contract, quality report contract, WebSocket contract documented |
