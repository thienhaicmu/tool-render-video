# TECHNICAL_DEBT_REPORT.md — Technical Debt Report

## CRITICAL

### C1. render_pipeline.py is a God File
**File**: `backend/app/orchestration/render_pipeline.py`
**Functions affected**: `run_render_pipeline()`, `_render_part()`, `_build_variant_segments()`, `_maybe_cleanup_narration_audio()`, plus 25+ helpers

**Debt**: Every render concern — download, scene detection caching, scoring, transcription, subtitle processing, TTS, audio mixing, FFmpeg cut, FFmpeg encode, QA validation, report generation, thumbnail extraction, AI plan integration — is inlined in one file. Navigation is difficult. Any change touches unrelated code.

**Impact**: Every bug fix, every new render feature, every refactor requires navigating a 5,700+ line file. High regression risk from any change.

**Phase 4B shipped (2026-05-22)**: Post-assembly asset helpers extracted to `orchestration/asset_pipeline.py`; shared logging/event helpers extracted to `orchestration/render_events.py`. `render_pipeline.py` reduced from 6,064 → 5,779 lines.

**Phase 4C shipped (2026-05-22)**: QA/output validation helpers extracted to `orchestration/qa_pipeline.py`. `render_pipeline.py` reduced from 5,779 → 5,510 lines.

**Phase 4D shipped (2026-05-22)**: `_maybe_cleanup_narration_audio` extracted to `orchestration/audio_pipeline.py`; `_event_from_stage`, `_resolve_job_log_dir`, `_render_progress_timer`, `_PROGRESS_TICK_SEC` moved to `orchestration/render_events.py`. `render_pipeline.py` reduced from 5,510 → 5,340 lines.

**Phase 4E.1 shipped (2026-05-22)**: Shared FFmpeg infrastructure extracted from `render_engine.py` to `services/render/ffmpeg_helpers.py`. `render_engine.py` reduced from 1,652 → ~1,210 lines (−442 lines). 28 names re-exported at old location for backward compat.

**Phase 4E.2 shipped (2026-05-22)**: Clip operations extracted from `render_engine.py` to `services/render/clip_ops.py`. `render_engine.py` reduced from ~1,210 → 829 lines (−381 lines). 5 names re-exported at old location for backward compat.

**Phase 4E.3 shipped (2026-05-22)**: `render_base_clip()` extracted from `render_engine.py` to `services/render/base_clip_renderer.py`. `render_engine.py` reduced from 829 → ~619 lines (−210 lines). 1 name re-exported at old location for backward compat.

**Phase 4E.4 shipped (2026-05-22)**: `composite_overlays_on_base_clip()` extracted from `render_engine.py` to `services/render/overlay_compositor.py`. `render_engine.py` reduced from ~619 → ~477 lines (−142 lines). 1 name re-exported at old location for backward compat.

**Phase 4E.5 shipped (2026-05-22)**: `render_part()` and `render_part_smart()` extracted from `render_engine.py` to `services/render/legacy_renderer.py`. `render_engine.py` reduced from ~477 → ~50 lines. `render_engine.py` is now a pure re-export shim with no function bodies. All render logic lives in focused modules under `services/render/`.

---

### C2. Subtitle Display Duration Compressed at Non-1.0 Speeds
**File**: `backend/app/orchestration/render_pipeline.py` — subtitle slicing and ASS burn-in logic
**Functions**: `slice_srt_by_time()` in `subtitle_engine.py` + `render_part_smart()` in `render_engine.py`

**Partially Resolved (2026-05-22)**: Phase 1.5 validation confirmed that the `ass-before-setpts` vf_chain order means subtitle timestamps ARE re-clocked by `setpts=PTS/speed`. A subtitle at source t=10.0s appears at output t=10.0/1.15 = 8.7s — correctly synchronized with the sped-up video and audio.

**Remaining Debt**: Subtitle *display duration* is compressed proportionally to playback speed. A subtitle block authored for 3.0s of screen time is shown for 3.0/1.15 ≈ 2.6s at 1.15x speed. At the default TikTok profile, end-of-clip subtitles have ≈0.4s less reading time per block than intended. This is a legibility concern, not a synchronization error.

**Impact**: Reduced readability at high playback speeds. Text-heavy subtitle blocks are harder to read. Not a synchronization bug — the subtitle text and speech are aligned.

**Resolved on overlay path (Phase 3A/3B, 2026-05-22)**: The overlay path generates `subtitle_output_timeline.ass` with output-second timestamps using `slice_srt_to_output_timeline()`. In `composite_overlays_on_base_clip()`, there is no `setpts` — the base_clip PTS is already output-timeline. Subtitle display duration on the overlay path is NOT compressed; a 3.0s subtitle block shows for exactly 3.0 output seconds.

**Remaining Debt (legacy path only)**: When `FEATURE_OVERLAY_AFTER_BASE_CLIP=0`, `render_part_smart()` is still used and the display duration compression remains. The legacy path is not fixed and is used as the fallback path.

---

### C3. TTS Narration Desync at Non-1.0 Speeds

**Resolved (Phase 0)**:  
`mix_narration_audio()` in `audio_mix_service.py` now accepts `playback_speed: float`
and applies `atempo={speed:.4f}` to the narration track before mixing. The narration
is speed-compensated to match the video playback speed. Speed is clamped to FFmpeg
atempo's range [0.5, 2.0] (a separate concern from the render pipeline's [0.5, 1.5] clamp).

`render_pipeline.py` passes `playback_speed=_get_effective_playback_speed(payload, _target_platform)`
to `mix_narration_audio()` at the call site.

Regression tests added: `TestMixNarrationAudioAtempo` (8 tests) in `test_phase0_hotfixes.py`.

**Historical debt**: TTS narration was generated at natural speaking rate and mixed
without speed compensation. At 1.15x speed the narration ended ~52s into a 60s clip.

---

## HIGH

### H1. db.py is a 1900-Line God Service — **RESOLVED (Phase 4F)**

**File**: `backend/app/services/db.py`  
**Resolution status**: `services/db.py` is now a 31-line pure re-export shim. All live DB logic lives in `app/db/` (connection.py, jobs_repo.py, creator_repo.py). The upload domain (43 functions, 7 tables) was deleted entirely in Phase 4F.5.

~~**Functions**: All of them (schema init, job CRUD, parts CRUD, upload accounts CRUD, upload queue CRUD, upload history CRUD, runtime locks CRUD, scheduler state CRUD, proxy pool CRUD, creator prefs CRUD)~~

~~**Debt**: One file owns all database interactions for all domains. Adding any new entity requires adding schema + migration + CRUD + normalization to this file. Zero separation of concerns.~~

~~**Impact**: Changes to upload account logic risk breaking render job logic. Hard to test domain logic in isolation.~~

**Phase 4F.0 planning (2026-05-22)**: DB split strategy defined. Target: `app/db/` with 5 modules (`connection.py`, `jobs_repo.py`, `uploads_repo.py`, `platform_repo.py`, `creator_repo.py`). `services/db.py` remains as backward-compat re-export shim. Plan: `docs/restructure/PHASE_4F_DB_SPLIT_PLAN.md`.

**Phase 4F.1 shipped (2026-05-22)**: `app/db/connection.py` extracted — Group A (connection, schema, thread-local, helpers) moved verbatim. `services/db.py` re-exports all moved symbols. `services/db.py` reduced from ~1,886 → ~1,386 lines (−500 lines). 33 new tests in `test_db_connection.py`.

**Phase 4F.2 shipped (2026-05-22)**: `app/db/jobs_repo.py` extracted — Group B (upsert_job, update_job_progress, delete_job, upsert_job_part, get_job, list_jobs, list_jobs_page, list_job_parts_bulk, list_job_parts) moved verbatim. `services/db.py` re-exports all 9 symbols. `services/db.py` reduced by ~145 additional lines. 35 new tests in `test_jobs_repo.py`.

**Phase 4F.3 shipped (2026-05-22)**: `app/db/creator_repo.py` extracted — Group E (get_creator_prefs, upsert_creator_prefs) moved verbatim. `services/db.py` re-exports both symbols. `services/db.py` reduced by ~25 additional lines (~1,236 lines remaining). 17 new tests in `test_creator_repo.py`.

**Phase 4F.4 shipped (2026-05-22)**: `app/db/platform_repo.py` extracted — Group D (_normalize_proxy_pool_row, list_proxy_pool_rows, get_proxy_pool_row, create_proxy_pool_row, update_proxy_pool_row, delete_proxy_pool_row) moved verbatim. `services/db.py` re-exports all 6 symbols. `services/db.py` reduced by ~130 additional lines (~1,106 lines remaining). 44 new tests in `test_platform_repo.py`.

**Phase 4F.5 audit (2026-05-22)**: Upload domain removal audit completed. Audit found the upload domain is **100% active** (routes registered, frontend loaded, all 43 upload DB functions called by live endpoints). `uploads_repo.py` extraction **cancelled** — upload domain will be deleted directly, not extracted first. Deletion plan in `docs/restructure/PHASE_4F_5_UPLOAD_DOMAIN_REMOVAL_AUDIT.md`. **No backend code changed in this audit step.**

**Phase 4F.5A shipped (2026-05-22)**: Upload router unregistered from `main.py` (import + `include_router` removed). Upload frontend entry points removed: `upload-manager.js` (5,397 lines), `upload-config.js` (713 lines), `upload-engine.js` (114 lines) deleted; 3 `<script>` tags removed from `index.html`. Upload API now returns 404. Render pipeline and all non-upload routes unaffected. `routes/upload.py`, `upload_engine.py`, upload DB functions, and upload tables intentionally left for Phases 4F.5B–D. 9 new tests in `test_upload_entrypoints_removed.py`.

**Phase 4F.5B shipped (2026-05-22)**: `services/upload_engine.py` (1,793 lines; Playwright TikTok automation) deleted. `routes/channels.py` upload_engine imports removed; `create_channel` unified to always use local `_write_channel_settings`/`_write_channel_profile` helpers; `bootstrap_portable_runtime_for_channel` call removed; `channel_info` replaced `load_upload_settings` with direct JSON file read. `render-engine.js` upload block removed (~248 lines; `collectUploadPayload` through `_stopUploadWs`, 3 `/api/upload/` fetch calls). `render-ui.js` upload queue block removed (~145 lines; `addRenderClipToUploadQueue` through `cancelUploadQueueItem`, 5 `/api/upload/` fetch calls). `routes/upload.py`, upload DB functions, and upload tables intentionally left for Phases 4F.5C–D. 11 new tests in `test_upload_engine_removed.py`.

**Phase 4F.5C shipped (2026-05-22)**: `routes/upload.py` (1,501 lines, 42 endpoints) deleted. `app/db/platform_repo.py` (142 lines, proxy pool CRUD) deleted. All 43 upload-domain DB functions removed from `services/db.py` (~1,062 lines removed); `UPLOAD_PROFILE_LOCK_TTL_MINUTES`/`UPLOAD_SCHEDULER_STATE_ID` re-exports and `platform_repo` re-export block also removed. `services/db.py` reduced from 1,116 → 31 lines (pure re-export shim). `test_platform_repo.py` (44 tests) deleted; 1 upload-constants re-export test removed from `test_db_connection.py`; 13 new tests in `test_upload_domain_removed.py`. Upload tables in `init_db()` intentionally left for Phase 4F.5D.

**Phase 4F.5D shipped (2026-05-22)**: Upload domain fully removed. `app/db/connection.py` rewritten: removed `UPLOAD_PROFILE_LOCK_TTL_MINUTES`/`UPLOAD_SCHEDULER_STATE_ID` constants, removed all 7 upload table DDL blocks and 6 upload `_ensure_columns` blocks, removed `upload_scheduler_state` seed row. Added `_drop_upload_tables(conn)` helper (called inside `init_db()`) that idempotently `DROP TABLE IF EXISTS` all 7 upload tables on every startup — safely cleans up existing database files. `connection.py` reduced from 522 → ~230 lines. `TestConstants` class removed from `test_db_connection.py`; `EXPECTED_TABLES` updated to 3 tables; 20 new tests in `test_upload_schema_removed.py`. `services/db.py` public namespace: no upload or proxy symbols. **Upload domain removal complete (Phases 4F.5A–D).**

**Phase 4F.6 shipped (2026-05-22)**: Test baseline stabilized. Root cause of 8→67 failure spike: `tts_service.py` hard-imports `edge_tts` at module level; `edge-tts==7.2.8` is a declared `requirements.txt` dependency but was missing from the test venv. Installed — baseline restored to 8 pre-existing failures. DB import audit confirmed: `services/db.py` namespace clean (no upload/proxy/platform symbols), all callers use only live symbols, no active Python imports of deleted modules anywhere in the codebase. 15 new tests in `test_db_import_audit.py`.

---

### H2. No Test Coverage for Core Pipeline
**Files**: `backend/app/orchestration/render_pipeline.py`, `backend/app/services/render_engine.py`, `backend/app/services/subtitle_engine.py`

**Debt**: The render pipeline — the most critical code in the project — has zero test coverage. The 80+ test files in `backend/tests/` all test AI subsystem schema validators. No integration tests for FFmpeg invocation, subtitle slicing, audio mixing, or output validation.

**Impact**: Any regression in render quality, subtitle correctness, or FFmpeg command generation is only discovered by running a real render job.

**Phase 4G.0 planning (2026-05-22)**: `subtitle_engine.py` (1,970 lines) audited and split plan documented. 7 clusters identified (styles, srt_core, ass_core, readability, text_transforms, transcription, shim). Target: `app/services/subtitle/` package (7 focused modules). Cross-module coupling with `render_engine._has_audio_stream` documented; resolution planned for Phase 4G.6. Hard `import whisper` at module level (line 9) isolated to transcription cluster only — after extraction only `transcription.py` is affected. Plan: `docs/restructure/PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md`. No backend code changed in 4G.0.

**Phase 4G.1 shipped (2026-05-22)**: Cluster A extracted to `app/services/subtitles/styles.py` (~292 lines). Moved: `ASSPreset`, `_PRESETS` (10 presets), `_STYLE_ALIASES`, `_DEFAULT_PRESET_ID`, `_HL_OPEN`/`_HL_CLOSE`, `_compute_subtitle_scale`, `_compute_margin_v`, `BOUNCE_FX`, `_PRESET_MOTION_FX`, `_MOTION_FX_DEFAULT`, `_get_motion_fx`, `normalize_subtitle_style_id`, `get_subtitle_preset`, `build_ass_style_line`. `subtitle_engine.py` reduced 1,970 → 1,699 lines (−271). 39 new tests in `test_subtitle_styles.py`. **Phase 4G.2 shipped (2026-05-22)**: Cluster B (partial) extracted to `app/services/subtitles/srt_core.py` (~165 lines). Moved: `format_srt_timestamp`, `parse_srt_timestamp`, `_parse_srt_blocks`, `parse_srt_blocks`, `write_srt_blocks`, `slice_srt_by_time`, `slice_srt_to_text`, `_run_with_retry`. `subtitle_engine.py` reduced 1,699 → 1,539 lines (−160). 44 new tests in `test_subtitle_srt_core.py`. **Phase 4G.3 shipped (2026-05-22)**: Cluster B completed — `slice_srt_to_output_timeline` extracted to `app/services/subtitles/output_timeline.py` (~30 lines). `subtitle_engine.py` reduced 1,539 → 1,514 lines (−25). 21 new tests. **Phase 4G.4 shipped (2026-05-22)**: Cluster C (ASS Core) extracted to `app/services/subtitles/ass_core.py` (~290 lines). Also created `app/services/subtitles/readability.py` stub (~70 lines) with visual-width helpers required by `srt_to_ass_bounce`. Moved: `_ass_time`, `_ass_escape_text`, `_ass_highlight_tags`, `srt_to_ass_bounce`, `_hex_to_ass`, `srt_to_ass_karaoke`, `_safe_filter_path`, `burn_subtitle_onto_video`, `_PREVIEW_ASPECT_RES`, `_PREVIEW_FONTS_DIR`, `render_subtitle_preview`, `_WIDE_CHARS`, `_NARROW_CHARS`, `_approx_visual_width`, `_break_by_visual_width`. `subtitle_engine.py` reduced 1,514 → 1,018 lines (−496). 62 new tests in `test_subtitle_ass_core.py`. ASS output content, karaoke timing, style line values — all unchanged. `subtitles/` package: 5 modules. **Phase 4G.5 shipped (2026-05-22)**: Cluster D (full readability/emphasis) extended into `readability.py` and Cluster E (text transforms) extracted to new `app/services/subtitles/text_transforms.py`. `readability.py` extended from stub (~70) to full module (~370 lines): added `_HOOK_EMPHASIS_WORDS`, `_is_cjk`, `_emphasis_level`, emphasis constants/helpers, `subtitle_emphasis_pass`, intel readability constants, `_find_phrase_split`, `_split_block_semantic`, `resegment_srt_for_readability`. `text_transforms.py` created (~270 lines): `resolve_hook_overlay_text`, `apply_market_line_break_to_srt`, `apply_market_hook_text_to_srt`, `format_hook_subtitle`, `apply_hook_subtitle_format`, `apply_subtitle_execution_hints`. `subtitle_engine.py` reduced 1,018 → 249 lines (−769) — now contains only re-export blocks + Whisper/transcription cluster. 89 functional tests added (`test_subtitle_readability.py` 57 tests, `test_subtitle_text_transforms.py` 49 tests; 17 tests fail on `whisper` env limitation — same pre-existing issue as `test_subtitle_ass_core.py`). `subtitles/` package: 6 modules. **Phase 4G.6 shipped (2026-05-22)**: Cluster F (Whisper/transcription) extracted to new `app/services/subtitles/transcription.py` (~210 lines). Moved: `_MODEL_CACHE`, `_MODEL_CACHE_LOCK`, `_MODEL_TRANSCRIBE_LOCKS`, `_WHISPER_CACHE_DIR`, `WORD_MIN_GAP_SEC/MIN_DURATION_SEC/MERGE_SHORTER_THAN_SEC`, `get_whisper_model`, `_get_transcribe_lock`, `_transcribe_with_retry`, `_ensure_ffmpeg_in_path_for_whisper`, `has_audio_stream`, `extract_audio_for_transcription`, `transcribe_to_srt`, `_write_word_level_srt`, `_write_segment_level_srt`. **Coupling fix**: `has_audio_stream()` now imports directly from `render.ffmpeg_helpers._has_audio_stream` instead of via `render_engine` shim. `subtitle_engine.py` is now a pure ~45-line re-export shim with no function bodies and no `import whisper`. 49 new tests in `test_subtitle_transcription.py`. `subtitles/` package: 7 modules. `subtitle_engine.py` 249 → 45 lines (−204). **Phase 4G.7 complete (2026-05-22)**: Caller audit complete. 6 production callers + 15+ test callers all classified A/C (keep as-is). Zero circular imports, zero `render_engine` coupling, zero upward deps from subtitles/*. Compatibility shim frozen. New code should import from `app.services.subtitles.*`. 67 new tests in `test_subtitle_engine_compat_exports.py`. `subtitle_engine.py` debt: **RESOLVED** — god file split complete, pure shim remains for backward compat.

---

### H2b. routes/render.py Mixes Route Logic with Service Logic
**File**: `backend/app/routes/render.py`
**Line count**: ~1,125 lines (post Phase 4H.3)

**Debt**: `routes/render.py` contains at least 7 remaining responsibility clusters: source preparation, preview streaming, render job lifecycle, batch orchestration, media streaming, one-shot quick process, and 2 module-level state variables (`_ACTIVE_DOWNLOADS`, `_UUID_RE`). Non-route logic (batch runner) is still inlined as an inner closure. Media streaming route handlers remain in `routes/render.py` but their helper logic (range parsing, file iteration) has been extracted (Phase 4H.3).

**Impact**: Batch runner is still an inner closure with no cancel/resume/progress. `_ACTIVE_DOWNLOADS` is route-module-local state that could move to a download service in a future phase.

**Phase 4H.0 planning (2026-05-22)**: `routes/render.py` audited. 9 clusters and all module-level state inventoried. 3 coupling constraints documented (evict called from main.py; session callbacks passed to render pipeline; batch inner closure). Target modules: `services/preview/ffmpeg_probers.py`, `services/preview/session_service.py`, `services/render/batch_service.py`. Plan: `docs/restructure/PHASE_4H_ROUTE_CLEANUP_PLAN.md`. No backend code changed.

**Phase 4H.1 shipped (2026-05-22)**: `services/preview/ffmpeg_probers.py` created — 6 FFmpeg probe helpers extracted verbatim. `routes/render.py` reduced from ~1,369 → 1,205 lines (−164 lines). 44 new tests in `test_preview_ffmpeg_probers.py` — all pass. Same-object identity preserved. No API changes.

**Phase 4H.1A shipped (2026-05-22)**: `TestGetWhisperModel` ordering failures fixed. Root cause: `test_subtitle_engine_compat_exports.py` (alphabetically earlier) injected a different whisper mock into `sys.modules`, defeating `test_subtitle_transcription.py`'s `setdefault`. Fix: 3 test methods now use `mock.patch("app.services.subtitles.transcription.whisper", ...)` directly. Baseline stabilized to 8 failed / 6654 passed.

**Phase 4H.2 shipped (2026-05-22)**: `services/preview/session_service.py` created — 4 session helper functions and 4 state variables extracted verbatim. `routes/render.py` reduced from 1,205 → 1,150 lines (−55 lines). `evict_stale_preview_sessions` re-exported from `routes/render.py` so `main.py` deferred import is unchanged. 17 new tests in `test_preview_session_service.py` — all pass. Singleton identity verified (`routes.render._PREVIEW_SESSIONS is session_service._PREVIEW_SESSIONS`). No API changes.

**Phase 4H.3 shipped (2026-05-22)**: `services/preview/media_streaming.py` created — `_parse_range_header` (Range header parser + 416 error) and `_iter_file_bytes` (byte-range file generator) extracted from inline body of `stream_render_part_media`. `routes/render.py` reduced from 1,150 → 1,125 lines (−25 lines). Both route handlers (`stream_render_part_media`, `get_render_part_thumbnail`) remain in `routes/render.py`. 28 new tests in `test_preview_media_streaming.py` — all pass. Same-object identity verified. Range/no-range/416 behavior unchanged. No API changes.

---

### H3. RAG Memory Not Connected to Production Render
**File**: `backend/app/orchestration/render_pipeline.py` — call to `create_ai_edit_plan()`
**Line**: ~1550 (approximate — the context dict build)

**Debt**: `create_ai_edit_plan()` accepts a `memory_store` context key for RAG retrieval of prior render decisions. `render_pipeline.py` does not pass this key. The entire RAG infrastructure (vector store, SQLite memory, embeddings, retriever) is built and tested but effectively unused in production renders.

**Impact**: The AI system has no memory of prior renders. Creator preference learning is siloed in the adaptive profile JSON files, not in the RAG system. Work done on Phases 3–5 (memory phases) is not active.

---

### H4. FAISS Vector Index Not Persisted
**File**: `backend/app/ai/rag/vector_store.py` — `LocalVectorStore`

**Debt**: The in-memory vector store is rebuilt from scratch on every server restart. The `SQLiteStore` (`sqlite_store.py`) persists the raw text and metadata, but the vector embeddings are not saved to disk. Rebuilding from SQLite requires re-embedding all entries on startup — no code does this.

**Impact**: RAG retrieval on the first render after a server restart has no vector index. The system falls back to cosine search over empty entries (no results).

---

### H5. V2/V3/V4 Frontends Ship But Are Not the Default
**Directories**: `backend/static-v2/`, `backend/static-v3/`, `backend/static-v4/`

**Debt**: The active default frontend is `backend/static/` (V1). `static-v2/` is opt-in via `STATIC_UI_VERSION=v2` and does not have feature parity with V1 (missing the full editor, creator tools, review queue). `static-v3/` and `static-v4/` are partial UI iterations that serve no active route. All three ship in every Electron build.

**Impact**: Package bloat. `static-v3/` and `static-v4/` add confusion about which UI is canonical. `static-v2/` creates a second surface to maintain for any API contract change.

---

### H6. YouTube Download Hang Risk (Partially Resolved)
**File**: `backend/app/services/downloader.py` — `download_youtube()`
**Called from**: `render_pipeline.py` (main render path), `routes/render.py` (prepare-source, quick-process)

**Partially Resolved (Phase 0)**: `socket_timeout: 60` added to yt-dlp options, and `cancel_event` is now passed from `render_pipeline.py` so user cancel propagates to the download subprocess. The 60s socket timeout mitigates the most common stall scenario (network drop, hung connection).

**Remaining Debt**: yt-dlp's `socket_timeout` applies to individual socket operations, not total download time. A very slow download that keeps making progress can still run indefinitely. A total wall-clock timeout per download session is not yet implemented.

---

### H7. Preview Session Memory Loss on Server Restart
**File**: `backend/app/routes/render.py` — `_PREVIEW_SESSIONS` dict
**Lines**: 74–141

**Debt**: Preview sessions are stored in a module-level dict. On server restart, the in-memory dict is lost. Disk fallback (`session.json`) works only if: (a) the file exists, (b) the session directory was not cleaned, (c) the `video_path` still exists. In the packaged app, server restarts are common (crash, update).

**Impact**: Users lose their prepared source session on server restart and must re-prepare (re-download YouTube video).

---

## MEDIUM

### M1. Module-Level Mutable State in Screens
**File**: `backend/static-v2/assets/js/screens/create.js` — lines 30–40
**Variables**: `_phase`, `_srcMode`, `_url`, `_filePath`, `_outputDir`, `_error`, `_session`, `_activePreset`, `_advOpen`, `_generating`

**Debt**: Screen state is stored as module-level variables. Navigation away and back does not reset state unless explicitly handled. The current code resets most vars in `mount()` but `_error` retention on error states and `_session` retention across navigations is incomplete.

---

### M2. Batch Child Wait Has 7200s Hard Ceiling
**File**: `backend/app/routes/render.py` — `_run_batch()` function, line ~749
**Code**: `_done.wait(timeout=7200)`

**Debt**: If a child render job gets stuck (FFmpeg hung past `_FFMPEG_TIMEOUT_SEC`), the `_child_fn` finally block may not call `_done.set()` in some edge cases. The batch coordinator then waits the full 7200s before moving to the next URL.

---

### M3. Knowledge Packs Loaded Per-Render
**File**: `backend/app/ai/knowledge/knowledge_pack_loader.py`

**Debt**: Knowledge pack JSON files are opened and parsed on every render that uses AI planning. For the 20+ knowledge JSON files, this is unnecessary repeated I/O.

---

### M4. No Disk Space Check Before Render
**File**: `backend/app/orchestration/render_pipeline.py` — start of `run_render_pipeline()`

**Debt**: No disk space validation before starting. A full disk causes FFmpeg to produce a 0-byte output after a full encode pass. The QA check catches it, but the time for the full encode is wasted.

---

### M5. Scene Detection Progress Not Reported
**File**: `backend/app/services/scene_detector.py` — `detect_scenes()`

**Debt**: Scene detection on a 1-hour video takes 1–5 minutes. During this time, the job stage is `scene_detection` but `progress_percent` does not advance. The progress bar appears frozen.

---

### M6. V3/V4 Static Fragments Ship But Are Not Wired
**Directories**: `backend/static-v3/`, `backend/static-v4/`

**Debt**: Incomplete UI iterations that ship in the package but serve no active route. They add confusion and package size.

---

### M7. Optional AI Imports Use Broad Exception Swallow
**File**: All AI module `__init__` blocks (e.g. `ai/director/ai_director.py` lines 25–115)
**Pattern**: `try: from app.ai.X import Y; _AVAILABLE = True; except ImportError: _AVAILABLE = False`

**Debt**: `except ImportError` catches `ModuleNotFoundError` but will also catch any `ImportError` raised by a bug inside the imported module (e.g. referencing a missing attribute at import time). A bug in an AI module silently makes it appear as "optional and unavailable."

---

### M8. Whisper Model Lock Blocks All Concurrent Transcriptions
**File**: `backend/app/services/subtitle_engine.py` — `_get_transcribe_lock()`

**Debt**: One lock per Whisper model name. With `MAX_CONCURRENT_JOBS=2` and two renders both using Whisper base, the second render's transcription step blocks behind the first. Both jobs are counted as "running" but one is effectively waiting. Users see a stalled render with no explanation.

---

### M9. `list_jobs()` Returns All Jobs Without Pagination
**File**: `backend/app/services/db.py` — `list_jobs()`
**Called from**: `routes/jobs.py` `api_list_jobs()`

**Debt**: `GET /api/jobs` fetches ALL jobs from the database. For long-running apps with hundreds of jobs, this query materializes the full table. `list_jobs_page()` exists and is used by the history endpoint, but the raw `/api/jobs` endpoint still uses the unbounded query.

---

## LOW

### L1. `enrich_upload_account_runtime_state()` is N+1 on Lock List — **OBSOLETE (Phase 4F.5)**

~~**File**: `backend/app/services/db.py` — `enrich_upload_account_runtime_state()`~~  
~~**Function calls**: `list_active_runtime_locks()` called once per account~~

~~**Debt**: `list_upload_account_rows()` calls `enrich_upload_account_runtime_state()` per row, which calls `list_active_runtime_locks()` per row. For 10 accounts, this is 10 separate lock queries.~~

**Resolution**: `enrich_upload_account_runtime_state()`, `list_active_runtime_locks()`, and `list_upload_account_rows()` were all deleted in Phase 4F.5C as part of the upload domain removal. This debt no longer exists.

---

### L2. Scene Cache Uses System Temp Dir
**File**: `backend/app/orchestration/render_pipeline.py` — `_scene_cache_get()` / `_scene_cache_put()`
**Path**: `tempfile.gettempdir() / "render_cache" / "scene_detect" / ...`

**Debt**: Cache goes to the system temp dir (C:\Windows\Temp on Windows), not the project data dir. System cleanup tools can delete this cache unexpectedly, causing expensive scene re-detection.

---

### L3. `_PREVIEW_SESSIONS` LRU Eviction Uses Submit Time
**File**: `backend/app/routes/render.py` — `_save_session()` line 85
**Code**: `oldest = min(_PREVIEW_SESSIONS, key=lambda k: _PREVIEW_SESSIONS[k].get("created_at", 0))`

**Debt**: Eviction is by creation time, not by last access. An old but actively used session can be evicted in favor of a newer one.

---

### L4. SQLite Schema Migrations Use ALTER TABLE Per-Column — **PARTIALLY RESOLVED (Phase 4F)**

**File**: `backend/app/db/connection.py` — `_ensure_columns()`

**Debt**: Schema migration is done by checking column existence and running `ALTER TABLE ADD COLUMN`. Harmless but not idiomatic.

**Phase 4F resolution**: All upload table `_ensure_columns` calls removed (Phase 4F.5D). Only `jobs` and `job_parts` `_ensure_columns` blocks remain — significantly reduced scope. The pattern persists for the two live tables.

---

### L5. No Content Integrity for Output Files
**File**: `backend/app/orchestration/render_pipeline.py` — `_validate_render_output()`

**Debt**: Output validation checks duration and size. No MD5/SHA checksum of output files stored to DB. No way to verify file integrity after delivery (e.g. network copy corruption, partial disk write).
