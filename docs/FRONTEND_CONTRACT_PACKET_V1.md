# FRONTEND_CONTRACT_PACKET_V1

API and entity contract packet for the frontend rebuild.

This packet bridges the real backend implementation to the future frontend rebuild and Figma MCP phase. It does not redesign UI, propose visual structure, change backend contracts, or invent product features. It defines what the frontend may safely trust, what must be normalized, and where optional or unstable data must be handled defensively.

Source baseline:

- `docs/PRODUCT_ARCHITECTURE_REVIEW_1.md`
- `docs/PRODUCT_ARCHITECTURE_REVIEW_3.md`
- `backend/app/models/schemas.py`
- `backend/app/routes/*`
- `backend/app/services/db.py`
- `backend/app/orchestration/render_pipeline.py`
- `backend/app/ai/director/edit_plan_schema.py`
- Current frontend files only as workflow evidence.

## 1. Executive Summary

This packet exists to prevent the next frontend from guessing backend behavior.

The current backend already has stronger contracts than the current frontend: `RenderRequest`, preview sessions, job rows, part rows, `result_json`, WebSocket updates, download jobs, upload automation tables, and Electron IPC boundaries. The rebuild should start from these contracts rather than from the current static DOM, current CSS, or current JavaScript organization.

The frontend can safely trust:

- Route paths that currently exist under `backend/app/routes`.
- `RenderRequest` field names, defaults, and validators from `backend/app/models/schemas.py`.
- SQLite job and part row shapes exposed by `/api/jobs/*`.
- `result_json` keys assembled by `render_pipeline.py`.
- Optionality of AI metadata: AI data may be absent, disabled, fallback, failed, or advisory-only.
- WebSocket update shape: `{job, parts, summary}`.
- Polling fallback as authoritative recovery.
- Media playback/download through backend endpoints rather than raw filesystem paths.

The frontend must not trust:

- That optional AI fields are always present.
- That a successful job has no warnings.
- That every job has parts immediately.
- That WebSocket will close for every terminal-like status.
- That raw `result_json` is parseable without guards.
- That upload automation is simple enough to merge into the core render state.
- That current DOM IDs or CSS classes are valid architecture for the rebuild.

The rebuild should create one normalization layer for each durable entity. No page or component should parse backend JSON ad hoc.

## 2. RenderRequest Contract

Implementation source: `backend/app/models/schemas.py::RenderRequest`.

Frontend contract:

- The frontend submits render jobs through `/api/render/process` with a `RenderRequest`.
- Backend defaults are meaningful. Do not force fields into the payload unless the creator changed them or the workflow needs them.
- Most fields are optional from the frontend perspective because Pydantic defaults fill them.
- Required practical fields depend on source/output mode. Backend validation still enforces source viability.
- AI flags default to disabled unless explicitly stated otherwise.

### 2.1 Source Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `source_mode` | optional string | `"youtube"` | Conditionally | High | Source | Known implemented values include `"youtube"` and `"local"`; backend lowercases in source prep. |
| `source_quality_mode` | string | `"standard_1080"` | No | Medium | Source | Validator allows `standard_1080`, `high_1440`, `best_available`. |
| `youtube_url` | optional string | `""` | Required for single YouTube render | High | Source | Required when source mode is YouTube and no valid session/local path is used. |
| `youtube_urls` | optional list of strings | `[]` | Required for backend batch with 2+ URLs | Medium | Source | Used by `/api/render/process/batch`; current main editor may instead submit individual jobs. |
| `source_video_path` | optional string | `""` | Required for local render without session | High | Source/Desktop adapter | Must be a backend-readable local path; do not use for browser playback. |

### 2.2 Output Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `output_mode` | optional string | `"manual"` | No | High | Source/Studio | Existing logic supports manual/channel-like coercion; do not invent new modes. |
| `channel_code` | optional string | `""` | No, but defaults effective channel to manual | Medium | Source/Channels | Backend uses blank as `"manual"` in render route. |
| `output_dir` | optional string | `""` | Practically required | High | Source/Studio/Desktop adapter | Backend validation rejects unusable output. Current editor may append `/video_output`; new frontend should make output policy explicit. |
| `render_output_subdir` | optional string | `""` | No | Low/Medium | Channels/Studio | Channel/output helper field; treat as optional. |
| `keep_source_copy` | boolean | `false` | No | Low | Studio | Enables source archive behavior when pipeline supports it. |
| `cleanup_temp_files` | boolean | `true` | No | Low | System/Studio advanced | Safe to omit and use default. |

### 2.3 Resume Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `resume_job_id` | optional string | `null` | No | Medium | Library/Monitor | If provided, route may reuse existing job ID. |
| `resume_from_last` | boolean | `false` | No | Medium | Library/Monitor | Only meaningful with an existing `resume_job_id`; do not show as generic render setting. |

### 2.4 Render Profile Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `render_profile` | optional string | `"quality"` | No | High | Studio | Validator allows `fast`, `balanced`, `quality`, `best`. |
| `render_preset` | optional string | `"custom"` | No | Medium | Studio | Preset label/id are metadata helpers; exact preset behavior is backend-side. |
| `render_preset_id` | optional string | `null` | No | Medium | Studio | Optional; preserve if selected by user/preset system. |
| `render_preset_label` | optional string | `null` | No | Low/Medium | Studio | Display metadata; do not rely on it for execution. |
| `video_preset` | optional string | `null` | No | Low | Studio advanced | FFmpeg-facing setting; expose carefully. |
| `video_crf` | optional integer | `null` | No | Low | Studio advanced | Backend interprets when supplied; omit unless user controls quality explicitly. |
| `video_codec` | optional string | `"h264"` | No | Medium | Studio/System | Backend handles codec/fallback; frontend should not promise hardware encoder success. |
| `audio_bitrate` | string | `"192k"` | No | Low | Studio advanced | Optional audio quality control. |
| `encoder_mode` | optional string | `"auto"` | No | Medium | Studio/System | Auto is safest; backend handles fallbacks. |
| `output_fps` | integer | `60` | No | Medium | Studio | Frontend should validate sane numeric input before submit. |
| `transition_sec` | optional float | `null` | No | Low | Studio advanced | Optional transition setting. |
| `whisper_model` | optional string | `"auto"` | No | Medium | Studio/System | Affects subtitle transcription performance/quality if used. |

### 2.5 Clip Generation Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `auto_detect_scene` | boolean | `true` | No | High | Studio | Enables scene-aware segmentation. |
| `min_part_sec` | integer | `15` | No | High | Studio | Used by segment builder; validate min <= max in UI. |
| `max_part_sec` | integer | `60` | No | High | Studio | Used by segment builder and AI clip constraints. |
| `max_export_parts` | optional integer | `null` | No | High | Studio | Limits selected outputs after scoring/order. |
| `part_order` | optional string | `"viral"` | No | Medium | Studio/Results | Known behavior includes viral/combined-style and timeline ordering. Do not invent sort modes. |

### 2.6 Subtitle Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `add_subtitle` | boolean | `true` | No | High | Studio | Enables subtitle pipeline. |
| `subtitle_style` | optional string | `"pro_karaoke"` | No | High | Studio | Style aliases handled backend-side; do not invent unsupported styles. |
| `subtitle_viral_min_score` | integer | `0` | No | Low/Medium | Studio advanced | Filters subtitle application by score. |
| `subtitle_viral_top_ratio` | float | `1.0` | No | Low/Medium | Studio advanced | Backend has fallback to avoid no subtitles when gates too strict. |
| `subtitle_only_viral_high` | boolean | `false` | No | Low/Medium | Studio advanced | Optional gating behavior. |
| `subtitle_transcription_engine` | literal | `"default"` | No | Medium | Studio/System | Validator allows `default`, `whisperx`; WhisperX is optional/advanced. |
| `highlight_per_word` | boolean | `false` | No | Medium | Studio | Requires suitable word timing/style support; fallback possible. |
| `sub_font_size` | integer | `46` | No | High | Studio | UI should validate range. |
| `sub_font` | string | `"Bungee"` | No | Medium | Studio | Font availability is runtime-dependent. |
| `sub_margin_v` | integer | `170` | No | Medium | Studio | Affects subtitle placement. |
| `sub_color` | string | `"#FFFFFF"` | No | Medium | Studio | Color string passed to backend. |
| `sub_highlight` | string | `"#FFFF00"` | No | Medium | Studio | Highlight color. |
| `sub_outline` | integer | `3` | No | Medium | Studio | Outline thickness. |
| `sub_x_percent` | float | `50.0` | No | Medium | Studio | Horizontal subtitle position. |

### 2.7 Frame, Camera, and Reframe Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `aspect_ratio` | string | `"3:4"` | No | High | Studio | Backend supports common social aspect ratios; do not assume every arbitrary ratio is valid. |
| `frame_scale_x` | integer | `100` | No | Medium | Studio advanced | Used by crop/scale behavior. |
| `frame_scale_y` | integer | `106` | No | Medium | Studio advanced | Used by crop/scale behavior. |
| `motion_aware_crop` | boolean | `false` | No | High | Studio | Enables OpenCV motion-aware path where backend chooses/falls back. |
| `reframe_mode` | string | `"center"` | No | High | Studio | Known backend behavior includes center/subject/motion-style modes; promotion may change it only under opt-in influence. |

### 2.8 Overlay, Effect, and Audio Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `add_title_overlay` | boolean | `false` | No | Low/Medium | Studio | Simple title overlay, not a full title system. |
| `title_overlay_text` | optional string | `""` | No | Low/Medium | Studio | Only meaningful when title overlay enabled. |
| `effect_preset` | string | `"slay_soft_01"` | No | Medium | Studio | Backend interprets preset. Do not expose unsupported preset names. |
| `loudnorm_enabled` | boolean | `false` | No | Medium | Studio | FFmpeg loudness normalization path. |
| `audio_cleanup_engine` | literal | `"none"` | No | Low/Medium | Studio advanced/System | Validator allows `none`, `deepfilternet`; optional dependency risk. |
| `remotion_hook_intro` | boolean | `false` | No | Low | Studio advanced | Optional hook intro path; current exposure weak and should be marked advanced. |

### 2.9 Reup Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `reup_mode` | boolean | `false` | No | Low/Medium | Studio advanced | Transform/repackaging mode, not a separate product workflow. |
| `reup_overlay_enable` | boolean | `true` | No | Low | Studio advanced | Only meaningful in reup mode. |
| `reup_overlay_opacity` | float | `0.08` | No | Low | Studio advanced | Validate numeric range in frontend. |
| `reup_bgm_enable` | boolean | `false` | No | Low | Studio advanced | Optional BGM mixing. |
| `reup_bgm_path` | optional string | `null` | No | Low | Studio/Desktop adapter | Local path; must be backend-readable. |
| `reup_bgm_gain` | float | `0.18` | No | Low | Studio advanced | Optional gain setting. |
| `playback_speed` | float | `1.07` | No | Medium | Studio | Affects render speed. AI must not arbitrarily rewrite it. |

### 2.10 Parallel and Retry Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `max_parallel_parts` | integer | `0` | No | Medium | Studio/System | `0` means adaptive backend selection; user value is a ceiling. |
| `retry_count` | integer | `2` | No | Low/Medium | Monitor/System | Backend uses for retry behavior; do not confuse with job retry endpoint. |

### 2.11 Editor Session and Manual Edit Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `edit_session_id` | optional string | `null` | Required for preview-session render | High | Source/Studio | Bridge from prepare-source to render pipeline. |
| `edit_trim_in` | float | `0` | No | High | Studio | Source-time trim start. |
| `edit_trim_out` | float | `0` | No | High | Studio | `0` means no explicit trim-out in current behavior. |
| `edit_volume` | float | `1.0` | No | Medium | Studio | Source volume multiplier. |
| `text_layers` | list of `TextLayerConfig` | `[]` | No | Medium | Studio | Validate nested text-layer shape before submit. |

Nested `TextLayerConfig`:

| Field | Type | Default behavior | Safe frontend assumptions |
|---|---|---|---|
| `id` | string | required by model | Must be stable per text layer. |
| `text` | string | required by model | Required for visible layer. |
| `font_family` | string | `"Bungee"` | Font availability depends on runtime. |
| `font_size` | integer | `42` | Validate in UI. |
| `color` | string | `"#FFFFFF"` | Color string passed through. |
| `position` | string | `"bottom-center"` | Backend/text overlay helper interprets. |
| `x_percent`, `y_percent` | optional float | `null` | Optional manual placement. |
| `alignment` | string | `"center"` | Text alignment. |
| `bold` | boolean | `false` | Style hint. |
| `outline` | object | disabled, thickness 2 | Optional; includes `enabled`, `thickness`. |
| `shadow` | object | disabled, offsets 2/2 | Optional; includes `enabled`, `offset_x`, `offset_y`. |
| `background` | object | disabled, color `#00000099`, padding 10 | Optional. |
| `start_time`, `end_time` | float | `0.0` | Layer timing in seconds. |
| `order` | integer | `0` | Layer ordering. |

### 2.12 Voice and Translation Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `voice_enabled` | boolean | `false` | No | High | Studio | Voice validator only strict when enabled. |
| `voice_language` | string | `"vi-VN"` | Required if voice enabled | High | Studio | Validator allows `vi-VN`, `ja-JP`, `en-US`, `en-GB`. |
| `voice_gender` | string | `"female"` | Required if voice enabled | Medium | Studio | Validator allows `female`, `male`. |
| `voice_rate` | string | `"+0%"` | No | Medium | Studio | Edge TTS-style rate string. |
| `voice_mix_mode` | string | `"replace_original"` | Required if voice enabled | High | Studio | Validator allows `replace_original`, `keep_original_low`. |
| `voice_text` | optional string | `null` | Required when voice enabled and source manual | High | Studio | Backend rejects missing manual text. |
| `voice_source` | string | `"manual"` | Required if voice enabled | High | Studio | Validator allows `manual`, `subtitle`, `translated_subtitle`. |
| `voice_id` | optional string | `null` | No | Medium | Studio | Optional selected voice profile. |
| `subtitle_translate_enabled` | boolean | `false` | No | High when localization used | Studio | Enables translation pipeline. |
| `subtitle_target_language` | string | `"en"` | Required if translation/translated voice used | Medium | Studio | Validator allows `vi`, `en`, `ja`. |

### 2.13 Market, Hook, and Best Export Fields

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `market_viral` | optional dict | `null` | No | Medium | Studio | Freeform backend config; normalize only known UI-owned keys. |
| `viral_market` | optional string | `null` | No | Medium | Studio/Results | Used for market scoring/context. |
| `hook_applied_text` | optional string | `null` | No | Medium | Studio | Hook text may affect subtitle/hook logic when enabled. |
| `hook_apply_enabled` | boolean | `false` | No | Medium | Studio | Do not imply AI rewrites hooks unless backed by field/content. |
| `hook_overlay_enabled` | boolean | `false` | No | Low/Medium | Studio | Optional overlay behavior. |
| `hook_score` | optional float | `null` | No | Medium | Studio/Results | May feed output ranking default. |
| `subtitle_edits` | optional list | `null` | No | Medium | Studio | Backend applies edited subtitle blocks; validate shape in UI if exposed. |
| `combined_scoring_enabled` | boolean | `false` | No | Medium | Studio/Results | Affects ordering/ranking behavior. |
| `adaptive_scoring_enabled` | boolean | `false` | No | Medium | Studio/Results | Affects scoring behavior where implemented. |
| `auto_best_export_enabled` | boolean | `false` | No | Medium | Results/Studio | Copies top outputs to best export path when enabled. |
| `auto_best_export_count` | integer | `3` | No | Medium | Results/Studio | Count for best exports. |

### 2.14 AI Settings

| Field | Type | Default behavior | Required | UI importance | Owner | Safe frontend assumptions |
|---|---|---|---|---|---|---|
| `ai_director_enabled` | boolean | `false` | No | High | Studio/System | Master opt-in for AI Director metadata plan. |
| `ai_mode` | string | `"viral_tiktok"` | No | Medium | Studio | Treat as strategy mode, not a guarantee of platform-specific output. |
| `ai_auto_cut` | boolean | `true` | No | Medium | Studio advanced | Only meaningful when AI Director enabled; does not override safety gates. |
| `ai_target_duration` | optional integer | `null` | No | Medium | Studio | Target duration guidance. |
| `ai_use_semantic_hooks` | boolean | `true` | No | Low/Medium | Studio advanced | Optional semantic hook behavior. |
| `ai_use_rag_memory` | boolean | `false` | No | Low/Medium | Studio advanced/System | Optional local memory/retrieval context. |
| `ai_render_influence_enabled` | boolean | `false` | No | High/Advanced | Studio/Results | Opt-in bounded execution influence; must show report after render. |
| `ai_beat_execution_enabled` | boolean | `false` | No | Medium | Studio/Results | Beat-aware planning/execution metadata; do not imply arbitrary timing mutation. |
| `ai_beat_pulse_enabled` | boolean | `true` | No | Low | Studio advanced | Only meaningful with beat execution. |
| `ai_beat_transition_enabled` | boolean | `false` | No | Low | Studio advanced | Only meaningful with beat execution. |
| `ai_timing_mutation_enabled` | boolean | `false` | No | Advanced | Studio advanced | Opt-in; default preserves advisory behavior. |
| `ai_variant_planning_enabled` | boolean | `false` | No | Advanced | Studio advanced | Plans advisory variants; comments say never auto-renders. |
| `ai_variant_count` | integer | `3` | No | Advanced | Studio advanced | Variant planning count. |
| `ai_clip_discovery_enabled` | boolean | `false` | No | Advanced | Studio advanced | Discovery-only, never executes cuts by itself. |
| `ai_clip_min_duration_sec` | integer | `15`, clamped 5..180 | No | Advanced | Studio advanced | Validator clamps. |
| `ai_clip_max_duration_sec` | integer | `60`, clamped 10..300 and >= min | No | Advanced | Studio advanced | Validator adjusts if less than min. |
| `ai_clip_candidate_limit` | integer | `5`, clamped 1..20 | No | Advanced | Studio advanced | Discovery limit. |
| `ai_clip_segment_selection_enabled` | boolean | `false` | No | Advanced | Studio advanced | Selection-only unless later promoted through influence path. |
| `ai_clip_target_count` | integer | `3`, clamped 1..20 | No | Advanced | Studio advanced | Segment selection target count. |
| `ai_clip_batch_planning_enabled` | boolean | `false` | No | Advanced | Studio advanced | Planning-only; never executes batch renders by itself. |
| `ai_clip_batch_limit` | integer | `5`, clamped 1..20 | No | Advanced | Studio advanced | Batch planning limit. |

## 3. Source Session Contract

Implementation source: `backend/app/routes/render.py`.

### 3.1 Prepare Source Request

Endpoint: `POST /api/render/prepare-source`

Request model: `PrepareSourceRequest`

| Field | Type | Default | Meaning |
|---|---|---|---|
| `source_mode` | optional string | `"youtube"` | `"youtube"` or `"local"` workflow. |
| `youtube_url` | optional string | `""` | Required for YouTube mode. |
| `source_video_path` | optional string | `""` | Required for local mode. |

### 3.2 Prepare Source Response

Successful response shape:

```json
{
  "session_id": "uuid",
  "duration": 123.45,
  "title": "source title",
  "export_dir": "path/to/temp/preview/{session_id}/exports"
}
```

Trusted fields:

- `session_id`: required for editor/render handoff.
- `duration`: numeric source duration when probing succeeds.
- `title`: source title or local filename stem.
- `export_dir`: temporary export path; current editor may use/fallback to it, but final output should be user-controlled.

Optional/internal session fields are stored server-side in `TEMP_DIR/preview/{session_id}/session.json`:

- `video_path`: original source path used for render.
- `preview_path`: browser-safe preview path when generated.
- `duration`.
- `title`.
- `work_dir`.
- `source_mode`.

Frontend must not require direct access to `session.json`.

### 3.3 Preview Video

Endpoint: `GET /api/render/preview-video/{session_id}`

Behavior:

- Serves `preview_path` if available.
- Falls back to original `video_path`.
- Returns `FileResponse` with `media_type="video/mp4"`, `Accept-Ranges: bytes`, `Cache-Control: no-cache`.

Safe assumptions:

- Use this endpoint for preview playback.
- Do not load local `video_path` directly into video elements.
- 404 means missing/expired session or missing media.

### 3.4 Preview Transcript

Endpoint: `GET /api/render/preview-transcript/{session_id}`

Success shape:

```json
{
  "segments": [
    {"start": 0.0, "end": 1.23, "text": "caption text"}
  ]
}
```

Behavior:

- Uses cached `preview_transcript.json` when present.
- Otherwise runs Whisper tiny through `get_whisper_model("tiny")`.
- Returns 404 for missing session/video.
- Returns 500 with detail on transcription failure.

Safe assumptions:

- Transcript is optional readiness data.
- Missing transcript must not block render unless the selected workflow explicitly depends on it.
- Segment times are preview/source seconds, not per-part rebased SRT times.

### 3.5 Session Lifecycle

Preview sessions live in temp storage under `TEMP_DIR/preview/{session_id}`.

Safe assumptions:

- Session IDs are short-lived local runtime objects.
- Render pipeline can resolve `edit_session_id` through session storage.
- A reload may keep session usable if temp files still exist, but the frontend should handle 404 as expired/missing.
- Cleanup behavior may remove temp files. Do not treat preview sessions as a library.

## 4. Job Contract

Implementation source: `backend/app/services/db.py`, `backend/app/routes/jobs.py`, `backend/app/services/job_manager.py`, `backend/app/orchestration/render_pipeline.py`.

### 4.1 Job Row Shape

Jobs table fields exposed by `/api/jobs/{job_id}`:

| Field | Type | Meaning | Safe frontend assumptions |
|---|---|---|---|
| `job_id` | string | Primary ID | Stable identifier for routing/subscription. |
| `kind` | string | `render`, `download`, `render_batch`, etc. | Branch behavior by kind. |
| `channel_code` | string | Channel/manual grouping | May be `"manual"`. |
| `status` | string | Queue/execution terminal state | Normalize defensively. |
| `stage` | string | Current pipeline stage | Can be empty or backend-specific. |
| `progress_percent` | integer | Job-level percent | Display hint, not proof of output existence. |
| `message` | string | Latest human-readable message | Optional, may be empty. |
| `payload_json` | JSON string | Submitted request payload | Must parse defensively. |
| `result_json` | JSON string | Result package | Must parse through `ResultPackage` parser. |
| `created_at` | string | SQLite UTC timestamp | Convert defensively. |
| `updated_at` | string | SQLite UTC timestamp | Convert defensively. |

Note: `upsert_job()` includes `priority` in SQL, implying migrations may add this column, but `/api/jobs/{job_id}` should be treated as row-driven. The frontend should ignore unknown fields.

### 4.2 Job Statuses

Known render/download statuses from code and docs:

- `queued`
- `running`
- `completed`
- `completed_with_errors`
- `failed`
- `interrupted`

History normalization may convert render status to:

- `completed`
- `partial`
- `failed`
- `running`
- `queued`
- `interrupted`

Safe assumptions:

- `completed_with_errors` is a real terminal partial-success state.
- History `partial` is a normalized display status, not necessarily the raw job status.
- Unknown statuses should render as recoverable "unknown" states, not crash.

### 4.3 Stage Lifecycle

Typical render stages:

```text
queued
-> starting
-> downloading
-> scene_detection
-> segment_building
-> transcribing_full
-> rendering or rendering_parallel
-> writing_report
-> done or failed
```

Safe assumptions:

- Stage is a progress hint.
- Stage strings may evolve.
- Do not encode business logic solely around exact stage strings.

### 4.4 Progress Semantics

Job progress:

- `jobs.progress_percent` is coarse job-level progress.
- `job_parts.progress_percent` is per-part progress.
- `/api/jobs/{job_id}/ws` and poll responses include part rows.
- Summary progress is computed from parts by averaging part progress.

Safe assumptions:

- Job progress can reach 100 while result parsing still needs validation.
- Parts may be empty early in the job.
- Part progress is more useful for multi-clip rendering.

### 4.5 Queue Behavior

Endpoints:

- `GET /api/jobs/queue/status`
- `GET /api/render/queue-status`

`/api/jobs/queue/status` response:

```json
{
  "max_concurrent": 2,
  "active": 1,
  "pending": 0,
  "available_slots": 1
}
```

Safe assumptions:

- Queue is local in-process, not Celery/Redis.
- Startup recovery marks queued/running jobs interrupted.
- Queue state is local-machine runtime state.

### 4.6 Retry and Resume

Render endpoints:

- `POST /api/render/resume/{job_id}`
- `POST /api/render/retry/{job_id}`
- `POST /api/render/process` with `resume_job_id` and `resume_from_last`

Safe assumptions:

- Retry/resume depend on existing job payload/result.
- Render retry should be surfaced from Monitor/Library, not generic Studio controls.
- Backend may reject if job missing, wrong kind, or already running.

## 5. Job Part Contract

Implementation source: `backend/app/services/db.py`, `backend/app/routes/jobs.py`, `backend/app/routes/render.py`.

### 5.1 Part Row Shape

Fields from `job_parts`:

| Field | Type | Meaning | Safe frontend assumptions |
|---|---|---|---|
| `id` | integer | DB row ID | Internal; do not use as durable product ID. |
| `job_id` | string | Parent job | Required. |
| `part_no` | integer | Part number | Stable within job. |
| `part_name` | string | Human/file label | May be generated. |
| `status` | string | Part state | Normalize defensively. |
| `progress_percent` | integer | Part progress | Display hint. |
| `start_sec` | number | Source start | May be 0 for download items. |
| `end_sec` | number | Source end | May be 0 for download items. |
| `duration` | number | Part duration | May be 0 until known. |
| `viral_score` | number | Score | May be 0/default. |
| `motion_score` | number | Score | May be 0/default. |
| `hook_score` | number | Score | May be 0/default. |
| `output_file` | string | Local output path | Do not use directly for browser playback. |
| `message` | string | Latest part message | Optional. |
| `created_at`, `updated_at` | string | SQLite timestamps | Parse defensively. |

### 5.2 Known Part States

Known active statuses:

- `waiting`
- `cutting`
- `transcribing`
- `rendering`
- `downloading`

Known completion/failure statuses:

- `done`
- `failed`
- `unsupported` for download parts

Other statuses may appear during queue/setup. Unknown states must not crash UI.

### 5.3 Media and Stream Behavior

Endpoints:

- `GET /api/jobs/{job_id}/parts/{part_no}/stream`
- `GET /api/render/jobs/{job_id}/parts/{part_no}/media`

Safe assumptions:

- Use endpoints for browser preview/download.
- Both depend on part `output_file` existing on disk.
- 404 means no part, no output file, or missing file on disk.
- A done part with missing file is a recoverable filesystem/result mismatch.

### 5.4 Partial Success

Partial success is first-class.

Result JSON fields:

- `failed_parts`
- `failed_parts_detail`
- `successful_outputs_count`
- `failed_outputs_count`
- `is_partial_success`
- `output_ranking_warning`

Safe assumptions:

- Successful outputs must remain visible when some parts fail.
- Failed part details should be rendered in Results and Library.
- `completed_with_errors` must be treated as terminal but useful.

## 6. Result Package Contract

Critical parser source: `jobs.result_json` assembled in `backend/app/orchestration/render_pipeline.py`.

Frontend rule:

Create exactly one `ResultPackage` parser/normalizer. No page or component may parse `result_json` independently.

### 6.1 Raw `result_json` Keys

Known top-level result payload:

| Key | Type | Meaning | Optionality |
|---|---|---|---|
| `outputs` | list | Rendered output paths/items from pipeline | Present on successful render result; may be empty on failure. |
| `render_preset` | string | Effective preset name | Optional. |
| `render_preset_id` | string/null | Effective preset ID | Optional. |
| `render_preset_label` | string/null | Effective label | Optional. |
| `segments` | list | Selected/scored segment metadata | Optional/empty. |
| `market_viral_parts` | list/dict | Market viral metadata | Optional. |
| `output_ranking` | list | Ranking entries | Critical when outputs exist. |
| `output_ranking_warning` | string | Partial warning text | Optional. |
| `best_clip` | dict/null | Best ranking entry | Optional. |
| `best_exports` | list | Auto-best copied outputs | Optional. |
| `voice_summary` | string | `not used`, `applied`, `failed`, etc. | Present in render result. |
| `subtitle_translate_summary` | string | `not used`, `applied`, `failed`, `partial` | Present in render result. |
| `failed_parts` | list[int] | Failed part numbers | Present in render result. |
| `failed_parts_detail` | list[dict] | Failure details | Present in render result. |
| `selected_segments_count` | integer | Total selected parts | Present in render result. |
| `successful_outputs_count` | integer | Successful output count | Present in render result. |
| `failed_outputs_count` | integer | Failed output count | Present in render result. |
| `is_partial_success` | boolean | Partial success flag | Present in render result. |
| `ai_director` | dict | AI plan or `{enabled:false}` | Present in render result. |
| `ai_render_influence` | dict | Influence report | Present, may be disabled. |
| `ai_beat_execution` | dict | Beat execution report | Present, may be disabled. |
| `story` | dict | AI story metadata | Optional/empty. |
| `preset_evolution` | dict | AI preset metadata | Optional/empty. |
| `creator_style` | dict | AI creator style metadata | Optional/empty. |
| `ai_output_ranking` | dict | AI ranking recommendation | Present, may be unavailable. |
| `ai_render_quality_evaluation` | dict | AI quality evaluation | Present, may be unavailable. |
| `ai_ux` | dict | Displayable AI UX metadata | Present, may be unavailable. |

Compatibility note:

Docs elsewhere mention `selected_parts_count`; current code writes `selected_segments_count`. A frontend parser should normalize both, preferring `selected_segments_count` when present.

### 6.2 Output Ranking Entry

Ranking entries are built by `_compute_output_ranking_entry()`.

Canonical fields:

| Field | Type | Meaning |
|---|---|---|
| `part_no` | integer | Part number. |
| `output_file` | string | Local output path. |
| `output_rank` | integer | Rank after sorting, 1 is best. |
| `output_score` | number | 0..100 score. |
| `is_best_clip` | boolean | Best clip flag. |
| `ranking_reason` | string | Human-readable reason summary. |
| `ranking_components` | object | Component scores. |
| `selection_reason` | string | Segment selection reason when available. |
| `output_rank_score` | number | Backward-compatible alias for `output_score`. |
| `is_best_output` | boolean | Backward-compatible alias for best output. |
| `reasons` | list[string] | Component reason strings. |

Known `ranking_components`:

- `segment_viral_score`
- `hook_score`
- `retention_score`
- `speech_density_score`
- `market_score`
- `duration_fit_score`
- `continuity_score`

Normalization rules:

- Score = `output_score ?? output_rank_score ?? 0`.
- Best = `is_best_clip || is_best_output || output_rank === 1`.
- Rank = numeric `output_rank`; if missing, derive from list order.
- Output media URL must be built from `job_id` and `part_no`, not `output_file`.

### 6.3 Best Clip

`best_clip` should be normalized as an `OutputClip` reference.

Safe assumptions:

- It may be `null`/empty if ranking failed or no outputs succeeded.
- It should correspond to one ranking entry.
- Do not assume `best_clip.output_file` exists on disk without stream endpoint success.

### 6.4 Failed Parts

`failed_parts` is a list of integers.

`failed_parts_detail` is a list of failure dictionaries. Shape can vary; parser should preserve unknown keys and normalize at least:

- `part_no`
- `message` or error-like text when present
- output/segment context when present

Safe assumptions:

- Failed details are diagnostic data and may vary.
- Never hide failed parts when outputs exist.

### 6.5 Voice and Translation Summaries

Known voice summary values from pipeline:

- `not used`
- `applied`
- `failed`

Known subtitle translation summary values:

- `not used`
- `applied`
- `failed`
- `partial`

Safe assumptions:

- Treat these as status labels, not detailed logs.
- Detailed failure context may only exist in logs or part messages.

### 6.6 Canonical `ResultPackage` Entity

Frontend normalized shape:

```ts
type ResultPackage = {
  jobId: string;
  rawAvailable: boolean;
  parseError?: string;
  outputs: OutputClip[];
  ranking: OutputClip[];
  bestClip?: OutputClip;
  bestExports: unknown[];
  failedPartNumbers: number[];
  failedPartDetails: FailedPartDetail[];
  selectedCount: number;
  successfulCount: number;
  failedCount: number;
  isPartialSuccess: boolean;
  rankingWarning?: string;
  voiceSummary: "not used" | "applied" | "failed" | string;
  subtitleTranslateSummary: "not used" | "applied" | "failed" | "partial" | string;
  ai: AIInsightSummary;
  raw: Record<string, unknown>;
}
```

Parser ownership:

- `entities/result-package/parseResultPackage`.
- No component-level parsing.

## 7. AI Metadata Contract

Implementation sources:

- `backend/app/ai/director/edit_plan_schema.py`
- `backend/app/ai/director/ai_director.py`
- `backend/app/ai/director/render_influence.py`
- `backend/app/ai/subtitle_promotion/*`
- `backend/app/ai/camera_promotion/*`
- `backend/app/ai/segment_promotion/*`
- `backend/app/ai/quality_gate/*`
- `backend/app/ai/output/*`
- `backend/app/ai/ux/*`
- `backend/app/orchestration/render_pipeline.py`

Frontend rule:

AI metadata is optional and must be summarized. Missing AI metadata is not a frontend error.

### 7.1 Advisory AI

Source:

- `result_json.ai_director`
- Nested `AIEditPlan.to_dict()` fields.

Important advisory groups:

- `selected_segments`
- `subtitle`
- `camera`
- `pacing`
- `explainability`
- `confidence`
- `ai_summary`
- `ai_confidence`
- `story`
- `retention`
- `subtitle_execution`
- `beat_visual_execution`
- `timing_mutation`
- `story_optimization`
- `render_decision_preview`
- `execution_recommendations`
- `execution_simulation`
- `safe_render_mutations`
- `clip_candidate_discovery`
- `clip_segment_selection`
- `clip_batch_planning`
- `creator_*`
- `market_optimization_intelligence`
- `platform_*`
- `strategy_variants`
- `variant_evaluation`
- `best_strategy_reasoning`
- `subtitle_quality_v2`
- `camera_quality_v2`
- `hook_quality_v2`
- `render_quality_v2`

Creator-safe meaning:

- AI analyzed and recommended.
- It may not have changed the render.
- Empty dict means unavailable/no signal, not necessarily failure.

Frontend representation:

- Summarize available recommendations and confidence.
- Hide raw phase names by default.
- Preserve raw data for advanced diagnostics.

### 7.2 Execution AI

Sources:

- `result_json.ai_render_influence`
- `result_json.ai_beat_execution`
- `ai_director.timing_apply`
- `ai_director.subtitle_text_apply`
- `ai_director.camera_motion_apply`
- `ai_director.multivariant_execution` where present

Creator-safe meaning:

- Some AI systems may affect execution only when opt-in flags are enabled and safety gates allow it.
- Not all execution-labeled metadata implies files were changed.

Frontend representation:

- Show whether execution influence was enabled.
- Show applied/skipped counts and reasons where available.
- Show "advisory only" when enabled metadata did not mutate render.

### 7.3 Promotion AI

Sources:

- `ai_director.subtitle_execution_promotion`
- `ai_director.camera_execution_promotion`
- `ai_director.segment_selection_promotion`

Creator-safe meaning:

- Subtitle promotion can promote allowed subtitle style/highlight behavior under constraints.
- Camera promotion can promote `reframe_mode` and `motion_aware_crop` under constraints.
- Segment selection promotion can reorder existing scored segments; it must not invent timestamps.

Frontend representation:

- Report what changed.
- Report user override/lock behavior when present.
- Report confidence/quality gate blocks when present.

### 7.4 Quality Gate

Source:

- `ai_director.quality_gated_influence`

Creator-safe meaning:

- Risky AI influence may be blocked, downgraded, or reverted.
- This is a trust feature, not a failure.

Frontend representation:

- Show blocked/downgraded changes after render.
- Do not represent quality gate as creator-controlled styling.

### 7.5 Ranking AI

Sources:

- `result_json.output_ranking`
- `result_json.ai_output_ranking`
- `ai_director.output_ranking`

Creator-safe meaning:

- Core ranking exists even without AI Director.
- AI output ranking is additional recommendation metadata and may be unavailable.

Frontend representation:

- Use `output_ranking` as canonical clip ranking.
- Use `ai_output_ranking` as supplemental explanation/recommendation only.

### 7.6 Explainability AI

Sources:

- `result_json.ai_ux`
- `ai_director.explainability`
- `ai_director.render_decision_preview`
- `ai_director.ai_execution_summary`
- `ai_director.ai_execution_metrics`

Creator-safe meaning:

- Explains recommendations, confidence, and assistance level.
- May be unavailable if AI disabled or failed.

Frontend representation:

```ts
type AIInsightSummary = {
  available: boolean;
  directorEnabled: boolean;
  advisoryAvailable: boolean;
  executionInfluenceEnabled: boolean;
  appliedChanges: unknown[];
  skippedChanges: unknown[];
  warnings: string[];
  confidence?: Record<string, unknown>;
  summaryLines: string[];
  qualityGate?: Record<string, unknown>;
  raw: Record<string, unknown>;
}
```

Parser ownership:

- `entities/ai-insight/parseAIInsightSummary`.

## 8. Monitor / Transport Contract

Implementation sources:

- `backend/app/routes/jobs.py`
- current frontend `render-engine.js` workflow.

### 8.1 Polling

Polling endpoints:

- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/parts`
- `GET /api/jobs/{job_id}/logs`

Safe assumptions:

- Polling is authoritative recovery.
- Polling must continue or be restartable if WebSocket fails.
- Polling must be able to rebuild monitor state after page reload.

### 8.2 WebSocket

Endpoint: `WS /api/jobs/{job_id}/ws`

Message shape:

```json
{
  "job": {},
  "parts": [],
  "summary": {}
}
```

Error shape:

```json
{"error": "not_found"}
```

Summary shape from `_compute_progress_summary()`:

| Field | Meaning |
|---|---|
| `total_parts` | Part count. |
| `completed_parts` | Done count. |
| `failed_parts` | Failed count. |
| `pending_parts` | Pending count. |
| `processing_parts` | Active count. |
| `in_progress_count` | Backward-compatible alias. |
| `active_parts` | List of active part summaries. |
| `stuck_parts` | Active parts with old `updated_at`. |
| `current_part` | First active part number. |
| `current_stage` | First active part status. |
| `overall_progress_percent` | Mean part progress. |
| `parts_percent` | Backward-compatible alias. |

Important edge:

- WebSocket currently breaks on raw job statuses `completed` and `failed`.
- It may not close automatically for `completed_with_errors` or `interrupted`.
- Frontend must not depend on socket close as terminal detection.

### 8.3 Authoritative Source Rules

- Backend job row is authoritative for status/stage/message/result.
- Backend part rows are authoritative for per-part state.
- WebSocket is transport acceleration.
- Polling is fallback and refresh authority.
- Logs are diagnostics, not state authority.
- Local UI optimistic state must be reconciled with backend rows.

### 8.4 Log Contract

Endpoint: `GET /api/jobs/{job_id}/logs?lines=120`

Response:

```json
{
  "job_id": "uuid",
  "log_file": "path",
  "items": ["line"]
}
```

Safe assumptions:

- Missing log file returns empty `items`.
- Logs can be long; endpoint clamps line count.
- Logs may contain backend/runtime detail not suitable for primary creator UX.

## 9. Download Contract

Implementation source: `backend/app/routes/download.py`.

### 9.1 Create Download Batch

Endpoint: `POST /api/download/process`

Request:

```json
{
  "urls": ["https://..."],
  "output_dir": "path"
}
```

Success response:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "count": 2,
  "output_dir": "path",
  "items": [
    {"part_no": 1, "url": "https://...", "source": "youtube|facebook|instagram|unknown"}
  ]
}
```

Safe assumptions:

- Download jobs are stored in the same jobs/job_parts tables with kind `download`.
- Download parts use part statuses such as `done`, `failed`, `unsupported`, `downloading`.
- Download history is available through `/api/jobs/history` as normalized jobs.

### 9.2 Retry Download Items

Endpoint: `POST /api/download/retry/{job_id}`

Request:

```json
{
  "part_numbers": [1, 3]
}
```

Success:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "retried": [1, 3]
}
```

Safe assumptions:

- Empty `part_numbers` retries failed parts.
- Backend rejects non-download jobs, running jobs, invalid part numbers, and no failed downloads.

## 10. Upload Contract

Implementation source: `backend/app/routes/upload.py`, upload models in `backend/app/models/schemas.py`, upload tables in `backend/app/services/db.py`.

Status: **advanced-module-only for frontend rebuild v1 unless Publish is explicitly included.**

Upload is implemented enough to document as a real module, but it is operationally complex and should not be merged into core render/result state.

### 10.1 Accounts

Endpoints:

- `GET /api/upload/accounts`
- `POST /api/upload/accounts`
- `PATCH /api/upload/accounts/{account_id}`
- `DELETE /api/upload/accounts/{account_id}`
- `POST /api/upload/accounts/{account_id}/login-check`
- `POST /api/upload/accounts/{account_id}/test-proxy`

Account fields from model/table:

- `account_id`
- `platform`
- `channel_code`
- `account_key`
- `display_name`
- `status`
- `profile_path`
- `proxy_id`
- `proxy_config`
- `daily_limit`
- `cooldown_minutes`
- `today_count`
- `last_upload_at`
- `last_login_check_at`
- `login_state`
- `profile_lock_state`
- `health_json`
- `metadata_json`

Allowed account statuses:

- `active`
- `warming`
- `limited`
- `banned`
- `disabled`
- `login_required`

Allowed login states:

- `unknown`
- `logged_in`
- `logged_out`
- `challenge`
- `expired`

Allowed profile lock states:

- `idle`
- `locked`
- `stale_recovered`
- `conflict`

### 10.2 Videos

Endpoints:

- `POST /api/upload/videos/add`
- `GET /api/upload/videos`
- `PATCH /api/upload/videos/{video_id}`
- `DELETE /api/upload/videos/{video_id}`

Video fields:

- `video_id`
- `video_path`
- `file_name`
- `platform`
- `source_type`
- `status`
- `caption`
- `hashtags`
- `cover_path`
- `note`
- `duration_sec`
- `file_size`
- `metadata`
- `created_at`
- `updated_at`

Allowed source types:

- `manual_file`
- `import_folder`
- `render_export_later`

Allowed video statuses:

- `ready`
- `queued`
- `uploaded`
- `failed`
- `disabled`

### 10.3 Queue

Endpoints:

- `POST /api/upload/queue/add`
- `GET /api/upload/queue`
- `GET /api/upload/queue/{queue_id}`
- `PATCH /api/upload/queue/{queue_id}`
- `GET /api/upload/queue/{queue_id}/history`
- `POST /api/upload/queue/retry-failed`
- `POST /api/upload/queue/{queue_id}/hold`
- `POST /api/upload/queue/{queue_id}/resume`
- `POST /api/upload/queue/{queue_id}/run`
- `POST /api/upload/queue/{queue_id}/cancel`

Queue item fields:

- `queue_id`
- `video_id`
- `video_path`
- `account_id`
- `platform`
- `caption`
- `hashtags`
- `status`
- `priority`
- `scheduled_at`
- `attempt_count`
- `max_attempts`
- `last_error`
- `metadata`
- `video_file_name`
- `account_display_name`
- `account_key`
- `created_at`
- `updated_at`
- detail endpoint may add `eligible` and `blocked_reason`.

Allowed queue statuses:

- `pending`
- `scheduled`
- `uploading`
- `success`
- `failed`
- `held`
- `cancelled`

Safe update statuses:

- `pending`
- `scheduled`
- `held`

### 10.4 Scheduler, Proxy, Workers

Scheduler endpoints:

- `POST /api/upload/scheduler/start`
- `POST /api/upload/scheduler/stop`
- `GET /api/upload/scheduler/status`
- `POST /api/upload/scheduler/tick`

Scheduler status fields:

- `scheduler_enabled`
- `max_concurrent_uploads`
- `tick_interval_seconds`
- `last_tick_at`
- `running_count`
- `status`
- `next_eligible_count`
- `blocked_counts`

Allowed scheduler statuses:

- `stopped`
- `running`

Proxy endpoints:

- `GET /api/upload/proxies`
- `POST /api/upload/proxies`
- `DELETE /api/upload/proxies/{proxy_id}`
- `POST /api/upload/proxies/{proxy_id}/test`

Worker endpoints:

- `POST /api/upload/workers/register`
- `GET /api/upload/workers/next-job`
- `POST /api/upload/workers/complete`

Safe assumptions:

- Upload is real but setup-dependent.
- Do not design it as guaranteed one-click social publishing.
- Treat it as advanced operational automation with accounts, profiles, queues, proxies, and scheduler state.

## 11. Desktop Adapter Contract

Implementation source: `desktop-shell/preload.js`, `desktop-shell/main.js`.

Frontend rule:

No feature module should call Electron APIs directly. Use a desktop adapter with browser fallback.

### 11.1 Exposed Electron API

`window.electronAPI` exposes:

| Method | Return | Meaning |
|---|---|---|
| `pickDirectory()` | string or `""` | Choose channels root folder. |
| `openFolderPicker()` | object/null | Choose profile folder. |
| `pathExists(targetPath)` | boolean/null | Check local path. |
| `openPath(targetPath)` | string/error-ish result | Shell-open file/folder. |
| `openBrowserProfile(opts)` | object | Open browser profile. |
| `onBootStatus(cb)` | event subscription | Backend boot status messages. |
| `onBootVersion(cb)` | event subscription | Boot version messages. |

Safe assumptions:

- `window.electronAPI` may be absent in browser mode.
- IPC calls may fail and return null/empty/error strings.
- Desktop actions are convenience capabilities, not core data authority.

### 11.2 Adapter Entity

```ts
type DesktopCapabilities = {
  available: boolean;
  canPickDirectory: boolean;
  canOpenPath: boolean;
  canCheckPath: boolean;
  canOpenBrowserProfile: boolean;
}
```

Browser fallback:

- Disable folder picker and open-path actions.
- Allow manual path entry if backend can read it.
- Use media endpoints for playback.
- Never require Electron for result parsing or job monitoring.

## 12. Entity Normalization Layer

All entities should live under a shared `entities/*` layer. Parsers must tolerate unknown fields and missing optional fields.

### 12.1 SourceSession

Required fields:

- `sessionId`
- `previewVideoUrl`

Optional fields:

- `duration`
- `title`
- `exportDir`
- `transcriptSegments`
- `sourceMode`

Parser ownership:

- `entities/source-session/parsePrepareSourceResponse`
- `entities/source-session/parsePreviewTranscript`

### 12.2 RenderDraft

Required fields:

- `source_mode`
- source identifier: `youtube_url`, `source_video_path`, or `edit_session_id`
- `output_dir` or channel-derived equivalent

Optional fields:

- All other `RenderRequest` fields.

Parser/builder ownership:

- `entities/render-request/buildRenderRequest`
- `entities/render-request/validateRenderDraft`

Rule:

The draft builder must preserve backend defaults and only include intentional changes where possible.

### 12.3 Job

Required fields:

- `jobId`
- `kind`
- `status`

Optional fields:

- `stage`
- `progressPercent`
- `message`
- `payload`
- `result`
- `createdAt`
- `updatedAt`
- unknown backend fields

Parser ownership:

- `entities/job/parseJobRow`

### 12.4 JobPart

Required fields:

- `jobId`
- `partNo`
- `status`

Optional fields:

- `partName`
- `progressPercent`
- `startSec`
- `endSec`
- `duration`
- `viralScore`
- `motionScore`
- `hookScore`
- `outputFile`
- `message`
- timestamps

Parser ownership:

- `entities/job-part/parseJobPart`

### 12.5 ResultPackage

Required fields:

- `jobId`
- `rawAvailable`
- `outputs`
- `ranking`
- `failedPartNumbers`
- `ai`

Optional fields:

- `bestClip`
- `bestExports`
- summaries
- warnings
- raw data

Parser ownership:

- `entities/result-package/parseResultPackage`

### 12.6 OutputClip

Required fields:

- `jobId`
- `partNo`

Optional fields:

- `rank`
- `score`
- `isBest`
- `rankingReason`
- `rankingComponents`
- `selectionReason`
- `outputFile`
- `streamUrl`
- `mediaUrl`
- `partStatus`
- `message`

Parser ownership:

- `entities/result-package/parseOutputClip`

Rule:

`streamUrl` and `mediaUrl` are derived from `jobId` and `partNo`, not trusted from backend output paths.

### 12.7 AIInsightSummary

Required fields:

- `available`
- `directorEnabled`
- `advisoryAvailable`
- `executionInfluenceEnabled`
- `summaryLines`
- `warnings`
- `raw`

Optional fields:

- `appliedChanges`
- `skippedChanges`
- `confidence`
- `qualityGate`
- `ranking`
- `promotion`
- `executionMetrics`

Parser ownership:

- `entities/ai-insight/parseAIInsightSummary`

### 12.8 UploadQueueItem

Required fields:

- `queueId`
- `videoPath`
- `status`
- `platform`

Optional fields:

- `videoId`
- `accountId`
- `caption`
- `hashtags`
- `priority`
- `scheduledAt`
- `attemptCount`
- `maxAttempts`
- `lastError`
- `eligible`
- `blockedReason`

Parser ownership:

- `entities/upload/parseUploadQueueItem`

Scope:

- Advanced module only unless Publish is in rebuild v1.

### 12.9 SystemReadiness

Required fields:

- `available`
- `raw`

Optional fields:

- `ffmpeg`
- `ffprobe`
- `ytDlp`
- `whisper`
- `ollama`
- `gpu`
- warnings/errors

Parser ownership:

- `entities/system/parseWarmupStatus`
- `entities/system/parseAIDiagnostics`

## 13. Frontend Trust Rules

### 13.1 Frontend May Trust

- `RenderRequest` field names and defaults from schema.
- `/api/render/process` response `{job_id, status, resume_mode}`.
- `/api/render/process/batch` response `{batch_id, job_ids, count, status}` when using backend batch.
- `/api/render/prepare-source` response `{session_id, duration, title, export_dir}` on success.
- `/api/jobs/{job_id}` returns a job row or 404.
- `/api/jobs/{job_id}/parts` returns `{items}`.
- `/api/jobs/{job_id}/logs` returns `{job_id, log_file, items}`.
- WebSocket sends `{job, parts, summary}`.
- `/api/download/process` returns queued download job details.
- Upload manager endpoints usually return `{status:"ok", item}` or `{status:"ok", items}` patterns.

### 13.2 Frontend Must Validate

- Required source values before submit.
- Output directory presence.
- Numeric fields before submit.
- Voice settings when `voice_enabled`.
- Text layer IDs/text/timing.
- AI fields as opt-in/advanced.
- Result JSON parse success.
- Media endpoint success before assuming file availability.
- Upload account/video/queue status before enabling actions.

### 13.3 May Be Missing

- Preview transcript.
- Parts early in a job.
- `result_json` before terminal state.
- AI metadata when disabled or failed.
- `best_clip` when no outputs succeeded.
- `output_ranking` on failed jobs or malformed results.
- Logs.
- Local files referenced by old `output_file` paths.
- Electron API in browser mode.

### 13.4 Must Never Crash UI

- Malformed `payload_json`.
- Malformed `result_json`.
- Unknown job status.
- Unknown part status.
- Missing optional AI fields.
- Empty ranking.
- Partial success.
- WebSocket disconnect.
- Missing log file.
- Upload login/proxy errors.
- Desktop IPC failure.

## 14. Risk Areas

### 14.1 Unstable or Semi-Stable Contracts

- AI phase metadata is broad and evolving.
- Upload automation is implemented but operationally complex.
- Packaged desktop behavior needs verification.
- Batch render has backend support but current main editor may submit individual jobs.
- `result_json` docs and implementation differ on `selected_parts_count` vs `selected_segments_count`.
- WebSocket close behavior does not cover every terminal-like status.

### 14.2 Optional Metadata

- AI Director can be disabled.
- AI Director can fail and render can continue.
- AI output ranking can be unavailable.
- AI quality evaluation can be unavailable.
- AI UX metadata can be unavailable.
- Subtitle translation summary can be `not used`.
- Voice summary can be `not used`.

### 14.3 Legacy Aliases

Do not remove or ignore:

- `output_rank_score`
- `is_best_output`
- `is_best_clip`
- `parts_percent`
- `in_progress_count`

Parser should normalize aliases while preserving raw values.

### 14.4 Dangerous Assumptions

- Assuming completed job means every part succeeded.
- Assuming `output_file` exists.
- Assuming browser can play local filesystem paths.
- Assuming WebSocket is enough without polling.
- Assuming upload success is guaranteed.
- Assuming every AI insight executed.
- Assuming frontend can infer backend defaults better than Pydantic.
- Assuming current UI groupings are product architecture.

### 14.5 Runtime Edge Cases

- Source prep can fail with 400 or 500.
- Preview session can expire or lose files.
- Whisper transcript can fail.
- FFmpeg/NVENC can fall back or fail.
- Motion crop can fall back to standard render.
- Translation can fall back to original text.
- TTS/mix can fail while preserving video.
- Some parts can fail while job completes with errors.
- Startup recovery can mark jobs interrupted.
- Electron IPC can be absent or fail.

## 15. Recommended Implementation Guardrails

Before Figma or frontend implementation, create these frontend-only contract modules:

1. `renderRequest.contract.ts`
2. `sourceSession.contract.ts`
3. `job.contract.ts`
4. `jobPart.contract.ts`
5. `resultPackage.contract.ts`
6. `aiInsight.contract.ts`
7. `download.contract.ts`
8. `upload.contract.ts` if Publish is in scope
9. `desktopAdapter.contract.ts`
10. `systemReadiness.contract.ts`

Each contract module should include:

- Raw backend shape.
- Normalized frontend entity.
- Parser.
- Validation helpers.
- Unknown-field tolerance.
- Fixture examples from real responses.

This is the required bridge between backend implementation and future Figma/frontend work.

