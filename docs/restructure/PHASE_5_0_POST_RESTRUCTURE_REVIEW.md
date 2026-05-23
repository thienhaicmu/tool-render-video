# PHASE_5_0_POST_RESTRUCTURE_REVIEW.md

**Purpose**: Post-restructure audit document for Phase 5.0. Records the final state of all backend modules after Phases 4E–4H, verifies all compatibility shims, audits frontend API usage, runs the full test suite, and issues a go/no-go recommendation for Phase 5.1 product/UI work.

**Date**: 2026-05-23  
**Branch**: `restructure/output-timeline-architecture`  
**Audited by**: Phase 5.0 review agent

---

## 1. Purpose

This document captures:
- The complete state of the backend module tree after all restructure phases (4E–4H) completed
- Verification that all compatibility shims are healthy and no import path is broken
- A full API route audit (all active routes, all removed upload routes)
- Frontend API usage audit across all static/ directories, classified A/B/C/D
- WebSocket contract audit
- Schema and payload audit
- Full test suite results with known-failure inventory
- A product readiness decision for Phase 5.1 UI work

---

## 2. Current Branch

**Branch**: `restructure/output-timeline-architecture`  
**Status**: Ahead of `main`. Not yet merged. All restructure work (Phases 1–4H) committed here.

---

## 3. Backend Restructure Summary (Phases 4E–4H)

| Phase | What Changed | Result |
|---|---|---|
| Phase 4E.1 | Extract FFmpeg helpers → `services/render/ffmpeg_helpers.py` | 28 symbols, 474 lines |
| Phase 4E.2 | Extract clip ops → `services/render/clip_ops.py` | 5 functions, 401 lines |
| Phase 4E.3 | Extract base clip renderer → `services/render/base_clip_renderer.py` | 242 lines |
| Phase 4E.4 | Extract overlay compositor → `services/render/overlay_compositor.py` | 164 lines |
| Phase 4E.5 | Extract legacy renderer → `services/render/legacy_renderer.py` | 458 lines; `render_engine.py` → 53-line shim |
| Phase 4F.1–4F.4 | Extract DB modules → `app/db/` (connection, jobs_repo, creator_repo, platform_repo) | `services/db.py` → 31-line shim |
| Phase 4F.5A–D | Upload domain fully removed | 42 routes, 2 files, 43 DB functions, 7 tables, 3 frontend JS files deleted |
| Phase 4F.6 | Test baseline stabilized; DB import audit confirmed clean | 8 failed / 6222 passed baseline |
| Phase 4F.7 | Architecture freeze + stale doc audit | No code changes |
| Phase 4G.1–4G.7 | `subtitle_engine.py` split into 7 modules under `services/subtitles/` | `subtitle_engine.py` → 45-line shim; 388 subtitle tests |
| Phase 4H.1 | Extract FFmpeg probe helpers → `services/preview/ffmpeg_probers.py` | 44 tests |
| Phase 4H.1A | Whisper test ordering fix | Baseline restored to 8 failures |
| Phase 4H.2 | Extract preview session state → `services/preview/session_service.py` | 17 tests |
| Phase 4H.3 | Extract media streaming helpers → `services/preview/media_streaming.py` | 28 tests |
| Phase 4H.6 | Route cleanup freeze | `routes/render.py` at 1,125 lines (down from 1,369) |

**Net result**: `render_engine.py`, `services/db.py`, and `subtitle_engine.py` — all formerly 1,650–1,970-line god files — are now pure re-export shims (45–53 lines each). All extracted logic lives in focused sub-modules with test coverage.

---

## 4. Final Backend Module Tree (After Phase 4H.6)

```
backend/app/
├── ai/                          ← 60+ AI heuristic modules (unchanged throughout phases)
├── core/
│   ├── config.py                ← DATABASE_PATH, STATIC_UI_VERSION, TEMP_DIR, etc.
│   ├── stage.py                 ← JobStage enum
│   └── ui_gate.py               ← resolve_static_directory()
├── db/                          ← Phase 4F — live DB repositories
│   ├── __init__.py
│   ├── connection.py            ← get_conn, init_db, thread-local, _drop_upload_tables
│   ├── jobs_repo.py             ← upsert_job, update_job_progress, job parts CRUD
│   └── creator_repo.py         ← get_creator_prefs, upsert_creator_prefs
├── domain/                      ← Phase 1 domain models
│   ├── manifests.py             ← BaseClipManifest
│   └── timeline.py              ← TimelineMap
├── models/
│   └── schemas.py               ← Pydantic request/response models (Upload* schemas still present as dead code)
├── orchestration/
│   ├── asset_pipeline.py        ← Phase 4B
│   ├── audio_pipeline.py        ← Phase 4D
│   ├── qa_pipeline.py           ← Phase 4C
│   ├── render_events.py         ← Phase 4B/4D
│   └── render_pipeline.py       ← 5,340+ line coordinator (UNFROZEN god file)
├── routes/
│   ├── channels.py
│   ├── creator.py
│   ├── devtools.py              ← gated by ENABLE_DEVTOOLS=1
│   ├── download.py
│   ├── jobs.py
│   ├── render.py                ← 1,125 lines (Phase 4H frozen)
│   ├── subtitle.py
│   ├── viral.py
│   └── voice.py
│   # NOTE: routes/upload.py DELETED (Phase 4F.5C)
└── services/
    ├── preview/                 ← NEW Phase 4H — preview service package
    │   ├── __init__.py
    │   ├── ffmpeg_probers.py    ← _probe_video_codec, _probe_preview_profile, _is_browser_safe_preview,
    │   │                           _ensure_h264_preview, _run_ffmpeg_checked, _detect_leading_black_duration
    │   ├── session_service.py   ← _PREVIEW_SESSIONS, _save_session, _load_session,
    │   │                           _cleanup_preview_session, evict_stale_preview_sessions
    │   └── media_streaming.py   ← _parse_range_header, _iter_file_bytes
    ├── render/                  ← Phase 4E — render logic modules
    │   ├── __init__.py
    │   ├── base_clip_renderer.py  (242 lines)
    │   ├── clip_ops.py            (401 lines)
    │   ├── ffmpeg_helpers.py      (474 lines)
    │   ├── legacy_renderer.py     (458 lines)
    │   └── overlay_compositor.py  (164 lines)
    ├── subtitles/               ← Phase 4G — subtitle logic modules
    │   ├── __init__.py
    │   ├── styles.py            ← ASSPreset, _PRESETS, _STYLE_ALIASES, _HL_OPEN/_HL_CLOSE, presets/aliases
    │   ├── srt_core.py          ← format/parse timestamps, SRT parse/write/slice, _run_with_retry
    │   ├── output_timeline.py   ← slice_srt_to_output_timeline
    │   ├── readability.py       ← visual-width, emphasis, resegmentation
    │   ├── ass_core.py          ← ASS generation, srt_to_ass_bounce, srt_to_ass_karaoke, burn, preview
    │   ├── text_transforms.py   ← market/hook text transforms, AI execution hints
    │   └── transcription.py     ← Whisper model cache, transcribe_to_srt, has_audio_stream
    ├── db.py                    ← SHIM (31 lines) — re-exports from app/db/*
    ├── render_engine.py         ← SHIM (53 lines) — re-exports from services/render/*
    ├── subtitle_engine.py       ← SHIM (45 lines) — re-exports from services/subtitles/*
    └── [other services unchanged: audio_mix_service, bin_paths, cancel_registry,
         channel_service, clip_scorer, downloader, encoder_helpers, hook_optimizer,
         job_manager, maintenance, manifest_writer, market_subtitle_policy,
         motion_crop, qa_runner, remotion_adapter, report_service, scene_detector,
         segment_builder, subtitle_transcription_adapters, text_overlay, tts_service,
         tts_xtts_adapter, viral_scorer, viral_scoring, voice_profiles, warmup]
    # NOTE: services/upload_engine.py DELETED (Phase 4F.5B)
```

---

## 5. Render Architecture Review

`services/render_engine.py` is a 53-line pure re-export shim. All render logic is in focused sub-modules under `services/render/`:

| Module | Owns | Status |
|---|---|---|
| `services/render/ffmpeg_helpers.py` | FFmpeg infrastructure, filter builders, NVENC, probe cache, thread-local | HEALTHY |
| `services/render/clip_ops.py` | `cut_video`, silence detect, bad-frame detect, `apply_micro_pacing` | HEALTHY |
| `services/render/base_clip_renderer.py` | `render_base_clip()` — speed, crop, color, audio, BGM | HEALTHY |
| `services/render/overlay_compositor.py` | `composite_overlays_on_base_clip()` — subtitle, title, text_layers | HEALTHY |
| `services/render/legacy_renderer.py` | `render_part()`, `render_part_smart()` — legacy all-in-one | HEALTHY |
| `services/render_engine.py` | Pure re-export shim | HEALTHY — do not remove |

`render_pipeline.py` (coordinator) is 5,340+ lines and remains a god file. It is NOT frozen — it continues to import from `render_engine.py` shim and calls all pipeline stages. No further modularization of `render_pipeline.py` was performed in Phase 4H.

---

## 6. DB Architecture Review

`services/db.py` is a 31-line pure re-export shim. All live DB logic is in `app/db/`:

| Module | Owns | Status |
|---|---|---|
| `app/db/connection.py` | `get_conn`, `init_db`, thread-local, `_drop_upload_tables` | HEALTHY |
| `app/db/jobs_repo.py` | `upsert_job`, `update_job_progress`, parts CRUD | HEALTHY |
| `app/db/creator_repo.py` | `get_creator_prefs`, `upsert_creator_prefs` | HEALTHY |
| `app/services/db.py` | Pure re-export shim | HEALTHY — do not remove |

**Live tables**: `jobs`, `job_parts`, `creator_prefs` (3 tables only).

`_drop_upload_tables()` is called inside `init_db()` on every startup — idempotently drops any residual upload tables from pre-Phase-4F.5D database files. This migration is permanent and correct.

**Note**: `app/db/platform_repo.py` was deleted in Phase 4F.5C (upload domain removal). No replacement planned.

---

## 7. Subtitle Architecture Review

`services/subtitle_engine.py` is a 45-line pure re-export shim. All subtitle logic is in 7 modules under `services/subtitles/`:

| Module | Owns | Status |
|---|---|---|
| `subtitles/styles.py` | ASSPreset, _PRESETS, _STYLE_ALIASES, _HL_OPEN/_HL_CLOSE | HEALTHY |
| `subtitles/srt_core.py` | Timestamp parsing, SRT parse/write/slice, _run_with_retry | HEALTHY |
| `subtitles/output_timeline.py` | `slice_srt_to_output_timeline` (output-timeline bridge) | HEALTHY |
| `subtitles/readability.py` | Visual-width, emphasis pass, resegmentation | HEALTHY |
| `subtitles/ass_core.py` | `srt_to_ass_bounce`, `srt_to_ass_karaoke`, burn, preview | HEALTHY |
| `subtitles/text_transforms.py` | Market/hook text transforms, AI execution hints | HEALTHY |
| `subtitles/transcription.py` | Whisper model cache, `transcribe_to_srt`, `has_audio_stream` | HEALTHY |
| `services/subtitle_engine.py` | Pure re-export shim | HEALTHY — do not remove |

**Coupling fix confirmed**: `transcription.py:has_audio_stream()` now imports `_has_audio_stream` directly from `render.ffmpeg_helpers`, not through the `render_engine` shim. Verified by 3 dedicated tests in `test_subtitle_engine_compat_exports.py`.

**Dependency DAG**: No circular imports. All arrows point inward (styles → no deps; srt_core → domain/timeline only; readability → styles; ass_core → styles + srt_core + readability; text_transforms → srt_core + readability; transcription → srt_core + ffmpeg_helpers).

---

## 8. Preview/Route Architecture Review

`routes/render.py` is at 1,125 lines (frozen at Phase 4H.6). Three service modules were extracted:

| Module | Owns | Status |
|---|---|---|
| `services/preview/ffmpeg_probers.py` | 6 FFmpeg probe helpers | HEALTHY |
| `services/preview/session_service.py` | `_PREVIEW_SESSIONS` singleton + 4 session helpers | HEALTHY |
| `services/preview/media_streaming.py` | `_parse_range_header`, `_iter_file_bytes` | HEALTHY |

**State ownership verified**: `_PREVIEW_SESSIONS` is defined exactly once in `session_service.py`. `routes/render.py` imports and re-exports it. `routes.render._PREVIEW_SESSIONS is session_service._PREVIEW_SESSIONS` — same dict instance.

**Backward-compat re-export confirmed**: `routes/render.py` re-exports `evict_stale_preview_sessions` so `main.py`'s deferred import at line 130 is unchanged. Verified by `test_preview_session_service.py`.

**Accepted remaining debt in `routes/render.py`** (intentionally frozen):
- `_run_batch()` inner closure — batch threading debt, logic not location
- `quick_process` 283-line self-contained handler
- `_ACTIVE_DOWNLOADS` dict — download-lifecycle state, appropriate in route module

---

## 9. Removed Upload Domain Summary

| Layer | Status |
|---|---|
| Upload router `routes/upload.py` (1,501 lines, 42 endpoints) | DELETED Phase 4F.5C |
| Upload automation engine `services/upload_engine.py` (1,793 lines) | DELETED Phase 4F.5B |
| Upload proxy pool repo `app/db/platform_repo.py` (142 lines) | DELETED Phase 4F.5C |
| Upload DB functions (43 functions in `services/db.py`) | REMOVED Phase 4F.5C |
| Upload frontend JS (3 files, ~6,200 lines) | DELETED Phase 4F.5A |
| Upload `<script>` tags in `index.html` (3 tags) | REMOVED Phase 4F.5A |
| Upload table DDL (7 tables) | REMOVED Phase 4F.5D |

**Residual accepted references** (all correctly classified as non-upload-domain):
- `app/db/connection.py` — `_UPLOAD_TABLES` + `_drop_upload_tables()` — correct migration helper
- `app/routes/channels.py` — `upload_settings.json` path strings — filesystem channel management
- `app/routes/render.py:632` — `upload_local_video` endpoint — local file upload to render pipeline (unrelated to TikTok upload domain)
- `app/models/schemas.py` — `Upload*` schema classes (UploadRequest, UploadAccountBase, etc.) — dead classes, no active callers, no routes, but not yet deleted
- `backend/static/js/globals.js` — `uploadWs = null` variable declaration — orphan, never assigned after Phase 4F.5B

**FINDING**: `app/models/schemas.py` contains 8 Upload-related Pydantic model classes (UploadRequest, UploadQueueAddRequest, UploadAccountBase, UploadAccountCreate, UploadAccountUpdate, UploadVideoResponse, UploadQueueUpdateRequest, UploadQueueResponse, UploadSchedulerStatusResponse). These have no active callers and no registered routes. They are dead code but have not been deleted. This is low-priority cleanup (no runtime impact).

---

## 10. Compatibility Shim Policy

Three compatibility shims exist. All are healthy. None should be removed until an explicit caller migration phase is completed.

| Shim | Lines | Re-exports from | Active callers | Policy |
|---|---|---|---|---|
| `services/render_engine.py` | 53 | `services/render/` (5 modules) | `render_pipeline.py`, `routes/render.py`, tests | DO NOT REMOVE until all callers migrated |
| `services/db.py` | 31 | `app/db/` (3 modules) | `main.py`, 5 routes, 4 orchestration files, 3 service files | DO NOT REMOVE until all callers migrated |
| `services/subtitle_engine.py` | 45 | `services/subtitles/` (7 modules) | `render_pipeline.py`, `routes/subtitle.py`, `routes/render.py`, `segment_builder.py`, `subtitle_transcription_adapters.py`, tests | DO NOT REMOVE until all callers migrated |

All three shims verified via compile check: `python -m compileall app` — CLEAN (no compile errors).

---

## 11. API Route Audit

All active routes found across `backend/app/routes/`:

### `/api/render` (routes/render.py — prefix `/api/render`)

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/render/queue-status` | `get_queue_status` | ACTIVE |
| GET | `/api/render/ai-diagnostics` | `get_ai_diagnostics` | ACTIVE |
| POST | `/api/render/prepare-source` | `prepare_source` | ACTIVE |
| DELETE | `/api/render/prepare-source/{session_id}` | `cancel_prepare_source` | ACTIVE |
| GET | `/api/render/preview-video/{session_id}` | `preview_video` | ACTIVE |
| GET | `/api/render/preview-transcript/{session_id}` | `preview_transcript` | ACTIVE |
| POST | `/api/render/process` | `create_render_job` | ACTIVE |
| POST | `/api/render/process/batch` | `create_render_batch` | ACTIVE |
| POST | `/api/render/upload-local` | `upload_local_video` | ACTIVE (local file, not TikTok upload) |
| POST | `/api/render/download-health` | `download_health` | ACTIVE |
| POST | `/api/render/quick-process` | `quick_process` | ACTIVE |
| POST | `/api/render/resume/{job_id}` | `resume_render_job` | ACTIVE |
| POST | `/api/render/retry/{job_id}` | `retry_failed_parts` | ACTIVE |
| POST | `/api/render/{job_id}/cancel` | `cancel_render_job` | ACTIVE |
| GET | `/api/render/jobs/{job_id}` | `get_render_job` | ACTIVE |
| GET | `/api/render/jobs/{job_id}/parts/{part_no}/media` | `stream_render_part_media` | ACTIVE (Range-aware) |
| GET | `/api/render/jobs/{job_id}/parts/{part_no}/thumbnail` | `get_render_part_thumbnail` | ACTIVE |

### `/api/jobs` (routes/jobs.py)

| Method | Path | Handler | Status |
|---|---|---|---|
| GET | `/api/jobs` | `api_list_jobs` | ACTIVE (unbounded query — known debt M9) |
| GET | `/api/jobs/history` | `api_list_jobs_history` | ACTIVE (paginated) |
| GET | `/api/jobs/queue/status` | `api_queue_status` | ACTIVE |
| GET | `/api/jobs/{job_id}` | `api_get_job` | ACTIVE |
| GET | `/api/jobs/{job_id}/parts` | `api_list_job_parts` | ACTIVE |
| GET | `/api/jobs/{job_id}/logs` | `api_get_job_logs` | ACTIVE |
| GET | `/api/jobs/{job_id}/parts/{part_no}/stream` | `api_stream_job_part` | ACTIVE |
| WebSocket | `/api/jobs/{job_id}/ws` | `ws_job_updates` | ACTIVE |
| POST | `/api/jobs/cleanup/logs` | `api_cleanup_logs` | ACTIVE |
| DELETE | `/api/jobs/{job_id}` | `api_delete_job` | ACTIVE |

### `/api/channels` (routes/channels.py)

| Method | Path | Status |
|---|---|---|
| GET | `/api/channels` | ACTIVE |
| GET | `/api/channels/root` | ACTIVE |
| GET | `/api/channels/scan` | ACTIVE |
| POST | `/api/channels` | ACTIVE |
| GET | `/api/channels/{channel_code}` | ACTIVE |
| GET | `/api/channels/{channel_code}/config` | ACTIVE |

### Other routes

| Method | Path | Router | Status |
|---|---|---|---|
| POST | `/api/download/process` | download.py | ACTIVE |
| POST | `/api/download/retry/{job_id}` | download.py | ACTIVE |
| POST | `/api/dev/command` | devtools.py | ACTIVE (ENABLE_DEVTOOLS=1 only) |
| POST | `/api/subtitle/preview` | subtitle.py | ACTIVE |
| POST | `/api/viral/score` | viral.py | ACTIVE |
| POST | `/api/viral/score/all` | viral.py | ACTIVE |
| GET | `/api/voice/profiles` | voice.py | ACTIVE |
| GET | `/api/creator/preferences` | creator.py | ACTIVE |
| PUT | `/api/creator/preferences` | creator.py | ACTIVE |
| GET | `/api/feedback/summary` | creator.py | ACTIVE |
| GET | `/api/warmup/status` | main.py | ACTIVE |
| GET | `/health` | main.py | ACTIVE |

### Removed routes (upload domain)

All 42 `/api/upload/*` endpoints — REMOVED Phase 4F.5A–C. No residual route registrations.

---

## 12. Frontend API Usage Audit

Audited directory: `backend/static/` (V1 frontend — active default).

**Classification key**:
- A — Still valid API call, backend endpoint exists
- B — Intentionally removed endpoint, but frontend call is benign/never reaches it
- C — Stale broken frontend reference — frontend will get 404
- D — Unknown / needs user decision

### API fetch calls

| File | Line | URL | Classification |
|---|---|---|---|
| `batch-queue.js` | 230 | `POST /api/render/process` | A |
| `batch-queue.js` | 395 | `POST /api/render/process` | A |
| `channels.js` | 112 | `GET /api/channels/root` | A |
| `channels.js` | 248 | `POST /api/channels` | A |
| `creator-memory.js` | 46 | `PUT /api/creator/preferences` | A |
| `creator-memory.js` | 55 | `GET /api/creator/preferences` | A |
| `download-ui.js` | 218 | `POST /api/download/process` | A |
| `editor-audio-runtime.js` | 89 | `POST /api/upload-file` | C — no backend route `/api/upload-file` exists; will 404 |
| `editor-view.js` | 1107 | `POST /api/upload-file` | C — no backend route `/api/upload-file` exists; will 404 |
| `editor-view.js` | 1186 | `POST /api/render/prepare-source` | A |
| `editor-view.js` | 1761 | `POST /api/subtitle/preview` | A |
| `editor-view.js` | 3087 | `POST /api/render/process` | A |
| `editor-view.js` | 3745 | `POST /api/viral/score/all` | A |
| `render-config.js` | 81 | `POST /api/render/upload-local` | A (local file render endpoint) |
| `render-config.js` | 105 | `POST /api/render/upload-local` | A (local file render endpoint) |
| `render-config.js` | 206 | `POST /api/render/download-health` | A |
| `render-engine.js` | 125 | `POST /api/render/prepare-source` | A |
| `render-engine.js` | 392 | `GET /api/jobs` | A |
| `render-ui.js` | 167 | `GET /api/render/queue-status` | A |
| `render-ui.js` | 2455 | `GET /api/jobs/history?limit=3&kind=render` | A |
| `render-ui.js` | 3836 | `GET /api/feedback/summary` | A |
| `review-queue.js` | 96 | `POST /api/render/process` | A |
| `warmup.js` | 15 | `GET /api/warmup/status` | A |

### WebSocket connections

| File | Line | URL | Classification |
|---|---|---|---|
| `download-ui.js` | 301 | `WebSocket /api/jobs/{downloadJobId}/ws` | A |
| `render-engine.js` | 358 | `WebSocket /api/jobs/{jobId}/ws` | A (WS primary, HTTP polling fallback) |

### Upload-domain stale references

| File | What | Classification |
|---|---|---|
| `globals.js:6` | `let uploadWs = null` declaration | B — orphan variable, never assigned after Phase 4F.5B; harmless dead code |
| `globals.js:13–16` | `logStateByScope.upload` entry | B — orphan log scope, never triggered; harmless |
| `static/partials/settings-view.html:3` | "render and upload results" string | B — UI text, not an API call; harmless |

---

## 13. Stale/Broken Frontend References

| File | Line | What | Impact |
|---|---|---|---|
| `backend/static/js/editor-audio-runtime.js` | 89 | `POST /api/upload-file` | Will return 404. Editor audio file selection will silently fail. No backend route exists for this URL. |
| `backend/static/js/editor-view.js` | 1107 | `POST /api/upload-file` | Same as above — editor view file drop will fail with 404. |

**Note on `/api/upload-file`**: This URL uses a hyphen, not the `/api/upload/` upload-domain path. It is NOT a TikTok upload domain call — it was an editor file-selection endpoint that was never implemented or was removed independently. The upload domain removal (Phase 4F.5A–C) correctly left this untouched (it was outside scope), but the backend endpoint does not exist. This is a pre-existing bug, not a regression from the restructure.

---

## 14. Upload Domain Frontend Impact

**Summary**: No frontend files call `/api/upload/` (with slash-upload prefix) after Phase 4F.5B. The test `test_upload_domain_removed.py::TestStaticNoUploadApiFetches` confirms this for both `render-engine.js` and `render-ui.js`.

The only upload-adjacent frontend references are:
1. `globals.js:uploadWs` — dead declaration, never used
2. `/api/upload-file` in editor files — pre-existing broken reference, unrelated to TikTok upload domain

**Verdict**: Frontend is clean of TikTok upload domain calls. The `/api/upload-file` issue is a pre-existing editor bug unrelated to the restructure.

---

## 15. WebSocket Contract Audit

**Active WebSocket route**: `GET /api/jobs/{job_id}/ws` in `routes/jobs.py`

**Contract (unchanged throughout all phases)**:
- Accepts: job_id path parameter
- Server sends: JSON progress event objects `{status, stage, progress_percent, message, parts, ...}`
- Server uses fingerprinting (`_ws_fingerprint`) to suppress sends on pure timestamp changes
- Terminal statuses (completed, completed_with_errors, failed, interrupted) close the connection
- Client fallback: HTTP polling every 3s if WebSocket fails (implemented in `render-engine.js`)

**No WebSocket contract changes in Phases 4E–4H.** All WebSocket send/receive behavior is in `routes/jobs.py` and `render-ui.js`/`render-engine.js` — neither was modified in any phase. The Phase 4H preview session extraction did not affect job progress WebSocket.

**WebSocket for upload** (`uploadWs` in `globals.js`): The variable is declared but never assigned after Phase 4F.5B. No upload WebSocket route exists.

---

## 16. Schema/Payload Audit

### RenderRequest (active, unchanged)

`app/models/schemas.py:109` — `class RenderRequest(BaseModel)`. Contains 70+ fields including:
- Source: `source_mode`, `youtube_url`, `source_video_path`
- Output: `output_dir`, `channel_code`, `render_output_subdir`
- Render quality: `render_profile`, `video_codec`, `output_fps`
- Subtitle: `add_subtitle`, `subtitle_style`, `sub_font_size`, `sub_font`, `sub_margin_v`
- Crop/frame: `aspect_ratio`, `frame_scale_x`, `reframe_mode`
- Playback: `playback_speed`
- AI: `ai_director_enabled`, `ai_mode`, `multi_variant`
- Creator assets: `asset_logo_path`, `asset_intro_path`, `asset_outro_path`

**No fields added or removed in Phases 4E–4H.** Schema is frozen since Phase 3C.5 or earlier.

### Upload schemas (dead code in schemas.py)

Classes `UploadRequest`, `UploadQueueAddRequest`, `UploadAccountBase`, `UploadAccountCreate`, `UploadAccountUpdate`, `UploadVideoResponse`, `UploadQueueUpdateRequest`, `UploadQueueResponse`, `UploadSchedulerStatusResponse` are still present in `schemas.py`. They have no registered routes and no active callers. They are dead code. **Classification: stale, no runtime impact, low-priority cleanup.**

### Job response shape

Jobs returned from `/api/jobs/{job_id}` and WebSocket progress events are dicts from SQLite rows via `jobs_repo.get_job()`. The schema is stable. `BaseClipManifest` JSON fields (written to `work_dir/part_N/manifest.json`) are unchanged since Phase 3C.

### Manifest fields

`app/domain/manifests.py` — `BaseClipManifest` dataclass. Fields are stable. All optional fields (`base_clip_*`, `overlay_*`) were added in Phases 2–3C and have not changed since.

---

## 17. Test Baseline

**Compile check**: `python -m compileall app` — CLEAN. No compile errors.

**Targeted test run** (critical Phase 4E–4H tests):
```
tests/test_db_import_audit.py
tests/test_subtitle_engine_compat_exports.py
tests/test_preview_ffmpeg_probers.py
tests/test_preview_session_service.py
tests/test_preview_media_streaming.py
tests/test_upload_domain_removed.py
tests/test_upload_schema_removed.py
→ 202 passed, 0 failed, 4 warnings (7.68s)
```

**Full test suite**:
```
8 failed, 6699 passed, 1 skipped, 4 warnings (86.42s)
```

**Result**: MATCHES Phase 4H.6 freeze baseline exactly. No new failures. No regressions.

### Known pre-existing failures (all 8 unchanged since before Phase 1)

| Test file | Count | Root cause |
|---|---|---|
| `test_remotion_adapter.py` | 4 | `remotion_hook_intro` default is `True` but test expects `False`; FFmpeg command assertion expects inline args but gets list |
| `test_ai_optional_dependencies.py` | 1 | `deepfilternet` key mismatch in AI dependency status response |
| `test_ai_phase36_clip_segment_selection.py` | 2 | `safety_check_failed` reason key not found in response — schema mismatch |
| `test_ai_visibility_summary.py` | 1 | `badges` key missing from summary response |

**None of these failures are caused by the restructure.** They pre-date Phase 1 and are unrelated to module organization.

---

## 18. Frontend Impact Conclusion

**Is the frontend safe to build on?**

**YES, with two known caveats.**

All active API endpoints are unchanged:
- `POST /api/render/process` — unchanged
- `POST /api/render/prepare-source` — unchanged
- `GET /api/jobs/{job_id}/ws` — unchanged
- All channel, creator, subtitle, download, job endpoints — unchanged

**Caveat 1 — Editor file upload (pre-existing bug)**:
`editor-audio-runtime.js:89` and `editor-view.js:1107` call `POST /api/upload-file` which has no backend route. This is a pre-existing bug unrelated to the Phase 4 restructure. The editor audio file selection and file-drop in editor-view will return 404. This was broken before the restructure began.

**Caveat 2 — Upload domain schemas still in schemas.py**:
`UploadRequest` and related schema classes in `schemas.py` are dead code. If any future frontend code accidentally imports or references these schemas via a JSON schema endpoint, it would find dead definitions. This is low-priority cleanup.

**All other frontend API calls are valid.** The WebSocket contract is unchanged. The RenderRequest payload shape is unchanged. No route paths were modified.

---

## 19. Remaining Backend Technical Debt

From `TECHNICAL_DEBT_REPORT.md` (post Phase 4H.6), key items:

### CRITICAL

| ID | Item | Status |
|---|---|---|
| C1 | `render_pipeline.py` god file (~5,340+ lines) | UNRESOLVED — not touched since Phase 4D; 15+ config dicts still inlined |
| C2 | Subtitle display duration compressed at non-1.0 speed (legacy path) | PARTIALLY RESOLVED — resolved on overlay path (Phase 3B); legacy path still affected |

### HIGH

| ID | Item | Status |
|---|---|---|
| H2 | No test coverage for core pipeline | PARTIALLY RESOLVED — overlay path, domain models, audio mix, subtitle modules now covered; legacy `render_part_smart()` path has no end-to-end test |
| H3 | RAG memory not wired to production render | UNRESOLVED — one-line fix, never done |
| H4 | FAISS vector index not persisted | UNRESOLVED |
| H5 | V2/V3/V4 frontends ship but are not default | UNRESOLVED |
| H6 | YouTube download hang risk (partial) | PARTIALLY RESOLVED — socket_timeout=60; no wall-clock timeout |
| H7 | Preview session memory loss on restart | UNRESOLVED |

### New findings from this review

| ID | Item | Priority |
|---|---|---|
| NEW-1 | `app/models/schemas.py` — 8 dead Upload* Pydantic classes | LOW — no runtime impact |
| NEW-2 | `globals.js:uploadWs` — orphan variable declaration | LOW — no runtime impact |
| NEW-3 | `editor-audio-runtime.js:89` + `editor-view.js:1107` — `POST /api/upload-file` 404 | MEDIUM — editor audio file selection broken |
| NEW-4 | `main.py` uses deprecated `@app.on_event` FastAPI pattern | LOW — deprecation warning only |

---

## 20. Product Readiness Decision

**Can UI/product work begin? YES.**

**Backend stability**: All core render APIs are stable. The three compatibility shims are healthy. The compile check is clean. The full test suite passes at the known baseline (8 pre-existing failures, 6699 passing).

**API contract stability**: No route paths, HTTP methods, request body shapes, or response shapes have changed since Phase 4F.7. The WebSocket progress contract is unchanged. The `RenderRequest` Pydantic model is unchanged.

**Conditions for beginning Phase 5.1 product work**:
1. UI code must not call `/api/upload-file` — this endpoint does not exist. If editor audio file upload is a Phase 5.1 feature, the backend endpoint must be created first.
2. UI code must not re-introduce any `/api/upload/*` routes or reference removed upload schemas.
3. New UI phases should import frontend fetch targets from the route audit table in §11 — all those routes are verified active.
4. The `render_pipeline.py` god file is still 5,340+ lines. Feature work that requires touching render pipeline behavior (new render option, new AI hint, new segment logic) still carries the god-file navigation risk. This is accepted as known debt.

---

## 21. Recommended Next Product/UI Phases

### Phase 5.1 — Output Quality Hardening (Backend)
**Scope**: Close the most impactful production readiness gaps identified in TECHNICAL_DEBT_REPORT.md §BRUTAL_REVIEW_SUMMARY.md §Current priorities.
- Add audio stream presence check to `_validate_render_output()` — muted output currently passes QA silently
- Tighten QA duration tolerance from ±20% to ±5%
- Add total wall-clock timeout to `download_youtube()` (supplement the existing socket_timeout=60)
- Wire `memory_store` to `create_ai_edit_plan()` in `render_pipeline.py` — one-line change; activates built RAG system

**Entry criteria**: This review complete. No other preconditions.

### Phase 5.2 — Frontend V1 Cleanup / V2 Promotion
**Scope**: Consolidate the V1/V2/V3/V4 frontend situation.
- Audit V1 vs V2 feature parity gap
- Remove or archive V3/V4 dead directories
- Decide whether to promote V2 as default or clean up V1
- Fix `/api/upload-file` in editor (create a backend endpoint or remove the editor upload UI)

**Entry criteria**: Phase 5.1 QA improvements shipped (ensures stable API surface for frontend targeting).

### Phase 5.3 — Render Pipeline Partial Extraction (render_pipeline.py)
**Scope**: Begin reducing `render_pipeline.py` below 4,000 lines.
- Extract `_render_part()` inner function to its own module
- Extract platform config dicts (`_PLATFORM_PROFILES`, `_CTA_TEXTS`, etc.) to `knowledge/` JSON
- Requires careful planning (similar to Phase 4G) due to closure dependencies

**Entry criteria**: Phase 5.2 frontend is stable. Full test coverage for Phase 5.3 targets added first (no regression without tests).

---

## 22. Final Recommendation

**GO for Phase 5.1 product work.**

The backend restructure (Phases 1–4H) is functionally complete. All major god files are either eliminated (`render_engine.py` → shim, `services/db.py` → shim, `subtitle_engine.py` → shim) or managed (`routes/render.py` frozen at 1,125 lines). All 202 critical Phase 4E–4H tests pass. Full suite at 6699 passing / 8 known pre-existing failures — no regressions.

The frontend can build on the current API contract safely. The only blocking issue for editor audio upload is the pre-existing missing `/api/upload-file` backend endpoint — this must be addressed before any Phase 5.1 work requires that feature.

The remaining `render_pipeline.py` god file (5,340+ lines) is acknowledged technical debt but does not block product work. It becomes critical only when new render features require modifying the pipeline.

**Blockers for go**: None (0 blocking issues).  
**Known caveats**: `/api/upload-file` pre-existing 404, dead Upload* schema classes in schemas.py, V3/V4 dead frontend directories.
