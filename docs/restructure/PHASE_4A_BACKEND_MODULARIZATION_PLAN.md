# PHASE_4A_BACKEND_MODULARIZATION_PLAN.md

**Status**: PLANNING (Phase 4B SHIPPED, Phase 4C SHIPPED, Phase 4D SHIPPED, Phase 4E.1 SHIPPED, Phase 4E.2 SHIPPED, Phase 4E.3 SHIPPED, Phase 4E.4 SHIPPED, Phase 4E.5 SHIPPED, Phase 4F.0 PLANNING, Phase 4F.1 SHIPPED, Phase 4F.2 SHIPPED, Phase 4F.3 SHIPPED)
**Last updated**: 2026-05-22 (post Phase 4F.3 shipped)
**Branch**: `restructure/output-timeline-architecture`

This is a planning document only. No code changes are in scope. Phase 4A produces this document and updated supporting docs. Implementation begins in Phase 4B.

---

## 1. Current Backend State After Phase 3C

The core render restructure is complete. The overlay pipeline (base clip → composite → fallback) has stable contracts, clear ownership boundaries, and full test coverage.

**God files measured on 2026-05-22:**

| File | Lines | Problem |
|---|---|---|
| `render_pipeline.py` | 6,064 | Every render concern inlined — download, scene caching, scoring, subtitle processing, TTS, audio mix, FFmpeg cut, encode, QA, asset injection, AI integration, event emission, DB writes |
| `db.py` | 1,886 | All database domains (jobs, parts, upload accounts, queue, history, locks, proxies, creator prefs) in one file |
| `subtitle_engine.py` | 1,970 | Cohesive but large — Whisper transcription, SRT parsing, ASS conversion, text processing, market transforms all inlined |
| `render_engine.py` | 1,652 | Three distinct render functions (base clip, overlay composite, legacy all-in-one) plus all FFmpeg infrastructure in one file |
| `routes/render.py` | 1,368 | Preview session management, source prep, job creation, batch, streaming, thumbnail, quick-process inlined |
| `audio_mix_service.py` | 131 | Already small — narration mixer only |

**Total: 13,071 lines across 5 problematic files.**

The overlay architecture has given us a working model for what isolated, testable functions look like (`render_base_clip`, `composite_overlays_on_base_clip`). Phase 4 applies the same extraction pattern to the rest of the backend.

---

## 2. Why Modularization Is Now Safe

**The Phase 3 work produced the preconditions for safe extraction:**

1. `TimelineMap` and `BaseClipManifest` are stable domain anchors — all render functions now use them, providing clear data contracts at extraction boundaries.
2. 5,787 passing tests (post Phase 3C.5) provide a regression baseline. Any extraction that breaks behavior will fail tests immediately.
3. Phase 3 functions (`render_base_clip`, `composite_overlays_on_base_clip`) are already extracted from the all-in-one `render_part_smart()` and have proven that function-level extraction is safe and mechanical.
4. Feature flags default OFF — overlay path changes cannot affect production renders even if a bug is introduced during extraction.
5. `RENDER_BOUNDARIES.md` documents what each function owns and forbids — these invariants survive any file reorganization.

**What makes extraction safe:** moving a function to a new file and adding a backward-compat re-export at the old location. Callers see no change. Tests verify no behavioral regression.

---

## 3. God File Audit

### 3.1 render_pipeline.py (6,064 lines)

**Responsibility clusters currently inlined:**

| Cluster | Functions | Safe to extract |
|---|---|---|
| Post-assembly asset hooks | `_maybe_prepend_remotion_hook_intro`, `_maybe_prepend_asset_intro`, `_maybe_append_asset_outro`, `_maybe_apply_asset_logo` | **Yes — Phase 4B** |
| Output QA / validation | `_validate_render_output`, `_assess_output_quality`, `_resume_output_valid`, `_render_part_failure_detail`, `_duration_tolerance`, `_stall_deadline`, `_failed_part_progress` | **Yes — Phase 4C** |
| Render event emission + logging | `_job_log`, `_append_json_line`, `_render_error_code`, `_emit_render_event`, `_event_from_stage`, `_resolve_job_log_dir`, `_render_progress_timer` | Yes — Phase 4C or 4D |
| Caching helpers | `_render_cache_key`, `_scene_cache_get/_put`, `_transcription_cache_get/_put`, `_score_cache_get/_put` | Yes — Phase 4C or 4D |
| Scoring + selection helpers | `_build_variant_segments`, `resolve_combined_score_weights`, `_score_component`, `_first_score`, `_output_ranking_detail`, `_output_ranking_reason`, `_compute_output_ranking_entry`, `_select_cover_frame_time`, `_select_cta_text`, `_append_cta_block_to_srt` | Later — score system is stable but tightly coupled to AI plan extraction |
| Audio cleanup | `_maybe_cleanup_narration_audio` | Yes — Phase 4D |
| Output path helpers | `_resolve_output_dir`, `_sanitize_channel_subdir`, `_reserve_source_path`, `_safe_unlink`, `_safe_output_name`, `_smart_output_stem` | Yes — Phase 4C |
| Profile/validation helpers | `_get_effective_playback_speed`, `_resolve_profile`, `_validate_text_layers_or_400`, `_probe_video_duration` | Later — deeply coupled to RenderRequest |
| **Core orchestration** | `run_render_pipeline`, inner `_render_part` | **Never extract blindly** — this is the coordinator, not the thing being coordinated |

**Risky dependencies**: `run_render_pipeline` and `_render_part` use closures over 50+ local variables. The inner `_render_part` is technically an inner function of `run_render_pipeline`. Extracting it into a standalone function requires materializing all those closure variables into explicit parameters — a significant refactor that must be done as a separate dedicated phase.

**API/frontend coupling**: `run_render_pipeline` is called from `routes/render.py` with a `RenderRequest` payload. The payload schema must not change during any extraction phase.

### 3.2 render_engine.py (1,652 lines)

**Responsibility clusters:**

| Cluster | Functions | Safe to extract |
|---|---|---|
| FFmpeg infrastructure | `set_thread_cancel_event`, `probe_video_metadata`, `_run_ffmpeg_with_retry`, `nvenc_available`, `_resolve_codec`, `resolve_ffmpeg_threads`, `extract_thumbnail_frame`, `_has_audio_stream` | **Yes — Phase 4E (foundation first)** |
| Filter builders | `_effect_filter`, `_cinematic_color_filter`, `_cinematic_sharpen_filter`, `_smart_denoise_filter`, `content_type_crf_delta`, `_build_audio_mix_filter`, `_build_audio_filter`, `_sanitize_speed`, `resolve_target_dimensions`, `_parse_fps_ratio`, `_probe_fps`, `_resolve_fps` | Yes — Phase 4E with FFmpeg infrastructure |
| Clip operations | `cut_video`, `detect_silence_trim_offset`, `detect_bad_first_frame`, `_probe_duration`, `_detect_silence_segments`, `apply_micro_pacing` | Yes — Phase 4E |
| Base clip renderer | `render_base_clip` | **Yes — Phase 4E.3 SHIPPED** |
| Overlay compositor | `composite_overlays_on_base_clip` | **Yes — Phase 4E.4 SHIPPED** |
| Legacy renderer | `render_part_smart`, `render_part` | **Yes — Phase 4E.5 SHIPPED** |

**Current cross-file coupling**: `render_pipeline.py` imports `render_base_clip`, `composite_overlays_on_base_clip`, `render_part_smart`, `cut_video`, `nvenc_available`, and 8 other helpers directly from `render_engine`. After extraction, all these call sites need updating.

**Safest extraction order within render_engine.py**: infrastructure first, then renderers that depend on it. Never split renderers before their shared infrastructure is in the target location.

### 3.3 subtitle_engine.py (1,970 lines)

**Assessment: cohesive, not a god file in the dangerous sense.**

`subtitle_engine.py` is large but is about one domain: subtitles. All 50+ functions process, transform, or render subtitle data. Unlike `render_pipeline.py`, there is no unrelated code in this file.

**Safe clusters for eventual extraction:**

| Cluster | Functions | Phase |
|---|---|---|
| Transcription management | `get_whisper_model`, `_get_transcribe_lock`, `transcribe_to_srt`, `extract_audio_for_transcription`, `_run_with_retry`, `_transcribe_with_retry` | Phase 4G |
| SRT core (parse/write/slice) | `parse_srt_blocks`, `write_srt_blocks`, `slice_srt_by_time`, `slice_srt_to_output_timeline`, `slice_srt_to_text`, timestamp converters | Phase 4G |
| ASS conversion | `srt_to_ass_bounce`, `srt_to_ass_karaoke`, `ASSPreset`, `build_ass_style_line`, `_ass_*` helpers | Phase 4G |
| Text processing | `subtitle_emphasis_pass`, `resegment_srt_for_readability`, `_break_by_visual_width`, market transforms | Phase 4G |

**Verdict**: defer subtitle_engine.py split to Phase 4G. The extraction risk is low but the urgency is also low — subtitle_engine.py is already internally coherent. Render_pipeline.py is the acute problem.

### 3.4 db.py (1,886 lines)

**Clear domain boundaries — best candidate for repository pattern:**

| Domain | Functions | Target module |
|---|---|---|
| Connection management | `get_conn`, `_thread_conn`, `close_thread_conn`, `init_db`, `_resolve_db_path`, `_force_writable_file`, `_can_write_sqlite`, `_json_dumps`, `_json_loads`, `_utc_now`, `_utc_now_iso` | `db/connection.py` |
| Jobs | `upsert_job`, `update_job_progress`, `delete_job`, `get_job`, `list_jobs`, `list_jobs_page` | `db/jobs_repo.py` |
| Job parts | `upsert_job_part`, `list_job_parts`, `list_job_parts_bulk` | `db/jobs_repo.py` |
| Upload accounts | `create/update/get/list/disable_upload_account_row`, `enrich_upload_account_runtime_state`, normalize helpers | `db/uploads_repo.py` |
| Upload queue | `add/list/get/update_upload_queue_item`, status transitions | `db/uploads_repo.py` |
| Upload history | `insert/list_upload_history` | `db/uploads_repo.py` |
| Upload scheduler | `get/update_upload_scheduler_state`, `increment_upload_scheduler_running_count` | `db/uploads_repo.py` |
| Runtime locks | `acquire/release_upload_runtime_lock`, `list_active_runtime_locks`, `_set_account_lock_state` | `db/uploads_repo.py` |
| Proxy pool | `create/update/get/list/delete_proxy_pool_row`, normalize helper | `db/platform_repo.py` |
| Creator prefs | `get_creator_prefs`, `upsert_creator_prefs` | `db/creator_repo.py` |

**Split risk**: `connection.py` is the shared foundation — every other repo module depends on `get_conn`. `connection.py` must be extracted first and stabilized before any domain repo is moved. Breaking `get_conn` during extraction kills all database operations across the entire app.

**Verdict**: safe but high-impact. Defer to Phase 4F.

### 3.5 routes/render.py (1,368 lines)

**Responsibility clusters:**

| Cluster | Functions | Problem |
|---|---|---|
| Preview session service | `_PREVIEW_SESSIONS`, `_save_session`, `_load_session`, `_cleanup_preview_session`, `evict_stale_preview_sessions` | Service logic in route layer — should be `services/preview_session.py` |
| Source preparation | `prepare_source`, `cancel_prepare_source` | Route functions — correct location |
| Preview endpoints | `preview_video`, `preview_transcript` | Route functions — correct location |
| Render job management | `create_render_job`, `resume_render_job`, `retry_failed_parts`, `cancel_render_job` | Route functions — correct location |
| Batch render | `create_render_batch`, `_run_batch` | `_run_batch` is 150+ lines of orchestration inlined in a route file |
| Media streaming | `stream_render_part_media`, `get_render_part_thumbnail` | Route functions — correct location |
| Quick process | `quick_process` | 285-line inline pipeline — should be extracted to a service |
| FFmpeg utilities | `_run_ffmpeg_checked`, `_detect_leading_black_duration` | Should be in render_engine.py or a dedicated helper |

**API/frontend coupling**: All routes have fixed URL paths and response schemas. None of these can change during extraction. The `_PREVIEW_SESSIONS` dict and preview session management can be extracted without any API change — the route handlers just delegate to the new service.

---

## 4. Target Backend Module Tree

Only modules justified by actual current code responsibilities are listed.

```
backend/app/
│
├── orchestration/
│   ├── render_pipeline.py       [thinned — core orchestration only]
│   ├── asset_pipeline.py        [NEW Phase 4B — post-assembly hooks]
│   ├── qa_pipeline.py           [NEW Phase 4C — output validation]
│   └── audio_pipeline.py        [NEW Phase 4D — audio cleanup orchestration]
│
├── services/
│   ├── render/
│   │   ├── __init__.py
│   │   ├── ffmpeg_helpers.py    [NEW Phase 4E — FFmpeg infrastructure + filter builders]
│   │   ├── clip_ops.py          [NEW Phase 4E — cut_video, silence trim, micro pacing]
│   │   ├── base_clip_renderer.py   [NEW Phase 4E — render_base_clip]
│   │   ├── overlay_compositor.py   [NEW Phase 4E — composite_overlays_on_base_clip]
│   │   └── legacy_renderer.py      [NEW Phase 4E — render_part_smart]
│   │
│   ├── render_engine.py         [RETAINED — backward-compat re-exports after Phase 4E]
│   ├── subtitle_engine.py       [RETAINED until Phase 4G]
│   ├── audio_mix_service.py     [RETAINED — already small and cohesive]
│   ├── manifest_writer.py       [RETAINED — already correct location]
│   └── preview_session.py       [NEW Phase 4H — extracted from routes/render.py]
│
└── db/
    ├── __init__.py              [re-exports for backward compat]
    ├── connection.py            [NEW Phase 4F — get_conn, init_db, close_thread_conn]
    ├── jobs_repo.py             [NEW Phase 4F — jobs + job_parts CRUD]
    ├── uploads_repo.py          [NEW Phase 4F — upload accounts, queue, history, locks]
    ├── platform_repo.py         [NEW Phase 4F — proxy pool]
    └── creator_repo.py          [NEW Phase 4F — creator prefs]
    │
    ├── db.py                    [RETAINED — backward-compat re-exports after Phase 4F]
```

**Not included (speculative, not backed by current code):**
- `part_pipeline.py` — `_render_part` is a closure inside `run_render_pipeline`; extracting it requires materializing 50+ closure variables. Do not attempt until render_pipeline.py has been thinned significantly.
- `overlay_pipeline.py` (as an orchestration file) — the overlay orchestration logic inside `_render_part` cannot be extracted as a unit without first extracting `_render_part` itself.
- `artifact_store.py` — path helpers are small enough to stay in render_pipeline.py or be promoted to a utility module later.
- `output_timeline.py` (separate from subtitle_engine) — `slice_srt_to_output_timeline` lives correctly in subtitle_engine.py; no extraction needed now.

---

## 5. Module Responsibility Map

| Module | Owns | Imports from |
|---|---|---|
| `orchestration/render_pipeline.py` | Main job orchestration, `run_render_pipeline`, segment selection, caching, scoring orchestration | `asset_pipeline`, `qa_pipeline`, `audio_pipeline`, `services/render/*`, `subtitle_engine`, `audio_mix_service`, `db/*` |
| `orchestration/asset_pipeline.py` | Post-assembly hook intro/outro/logo watermark orchestration | `remotion_adapter`, `domain/*` |
| `orchestration/qa_pipeline.py` | Output duration/size validation, quality assessment, resume validation | `services/render/ffmpeg_helpers`, `domain/*` |
| `orchestration/audio_pipeline.py` | Audio cleanup (DeepFilterNet) orchestration, narration cleanup step | `audio_cleanup_adapters`, logging |
| `services/render/ffmpeg_helpers.py` | FFmpeg binary invocation, probe, NVENC detection, filter builders, speed sanitize | `bin_paths`, domain-agnostic stdlib |
| `services/render/clip_ops.py` | `cut_video`, `detect_silence_trim_offset`, `detect_bad_first_frame`, `apply_micro_pacing` | `ffmpeg_helpers` |
| `services/render/base_clip_renderer.py` | `render_base_clip()` — speed, crop, audio, BGM, no overlays | `ffmpeg_helpers`, `domain/timeline` |
| `services/render/overlay_compositor.py` | `composite_overlays_on_base_clip()` — subtitle, drawtext, fps, `-c:a copy` | `ffmpeg_helpers` |
| `services/render/legacy_renderer.py` | `render_part_smart()` — all-in-one legacy path, permanent fallback | `ffmpeg_helpers` |
| `db/connection.py` | SQLite connection lifecycle, `get_conn`, `init_db` | stdlib only |
| `db/jobs_repo.py` | jobs + job_parts CRUD | `db/connection` |
| `db/uploads_repo.py` | upload accounts, queue, history, scheduler, runtime locks CRUD | `db/connection` |
| `db/platform_repo.py` | proxy pool CRUD | `db/connection` |
| `db/creator_repo.py` | creator prefs CRUD | `db/connection` |

---

## 6. Dependency Direction Rules

**Enforced direction (top imports from bottom, never reversed):**

```
routes/
  └── orchestration/
        └── services/
              └── domain/
                    └── db/ (storage layer)
```

**Concrete rules:**

| Forbidden import | Reason |
|---|---|
| `services` importing from `routes` | Routes are the API surface; services must not know about HTTP |
| `domain` importing from `services` | Domain objects are pure data; they must not call service code |
| `db` importing from `orchestration` | DB layer has no knowledge of render jobs |
| `render_engine` importing from `render_pipeline` | Engine implements primitives; orchestration is the caller |
| `base_clip_renderer` importing from `overlay_compositor` | Renderers are peers; neither should import the other |
| `overlay_compositor` importing from `legacy_renderer` | Fallback logic belongs in the orchestrator, not in the renderer |
| Any new module importing from `routes/render.py` | Routes are a leaf in the dependency graph |

**Detecting violations**: After each extraction, run `grep -r "from app.orchestration" backend/app/services/` and `grep -r "from app.routes" backend/app/` to confirm no reverse dependencies were introduced.

---

## 7. Migration Strategy

**Rule 1 — Extract, do not rewrite.**
Move functions verbatim. Do not change logic, parameter names, return types, or default values during the move. Changes come in a separate PR after extraction is proven to be regression-free.

**Rule 2 — Preserve function signatures where possible.**
If a function signature must change (e.g., to remove a closure dependency), that is a dedicated task tracked separately, not bundled into the extraction PR.

**Rule 3 — Keep backward-compat re-exports at the old location.**
```python
# In render_engine.py after render_base_clip is moved to render/base_clip_renderer.py:
from app.services.render.base_clip_renderer import render_base_clip  # backward compat
```
This means render_pipeline.py call sites do not need simultaneous updates. They can be migrated in a follow-up PR.

**Rule 4 — Move tests with the module.**
When a function moves, its dedicated test class moves to a new test file in the same PR. Tests for the old module are updated to import from the new location.

**Rule 5 — No frontend/API/DB contract changes.**
None of the extraction phases touch public API endpoints, RenderRequest schema, WebSocket payloads, or SQLite schema. If an extraction touches any of these, it is not a pure extraction and must stop.

**Rule 6 — One concern per PR.**
Each extraction phase targets one responsibility cluster. Never bundle the asset pipeline extract and the QA pipeline extract into one commit.

**Rule 7 — Full test suite after each extraction.**
After each PR: `python -m pytest tests/ -v --tb=short`. Accept only the pre-existing 8 failures. Any new failure is a regression; revert and investigate.

**Rule 8 — Update docs every phase.**
After each extraction, update MIGRATION_HISTORY.md and any architecture docs that reference the moved functions.

---

## 8. Recommended Sub-Phases

| Phase | Name | Scope | Risk |
|---|---|---|---|
| 4A | Backend Modularization Planning | This document. No code changes. | None |
| 4B | Extract Asset Pipeline | `_maybe_prepend_*` / `_maybe_append_*` / `_maybe_apply_asset_logo()` → `orchestration/asset_pipeline.py` | **Low** |
| 4C | Extract QA Pipeline | `_validate_render_output`, `_assess_output_quality`, output path helpers → `orchestration/qa_pipeline.py` | **Low** |
| 4D | Extract Audio Cleanup Pipeline | `_maybe_cleanup_narration_audio` → `orchestration/audio_pipeline.py`; render event emission → `orchestration/render_events.py` | **Low-Medium** |
| 4E.1 | Extract FFmpeg helpers | `ffmpeg_helpers.py` SHIPPED — infrastructure + filter builders extracted, render_engine re-exports | **Done** |
| 4E.2 | Extract Clip Ops | `clip_ops.py` SHIPPED — `cut_video`, silence/bad-frame detect, `apply_micro_pacing` extracted | **Done** |
| 4E.3+ | Split render_engine.py (remaining) | `base_clip_renderer.py`, `overlay_compositor.py`, `legacy_renderer.py` | **Medium** |
| 4F | Split db.py | `db/connection.py` first, then domain repos | **Medium-High** |
| 4G | Split subtitle_engine.py | Transcription, SRT core, ASS conversion, text processing | **Medium** |
| 4H | Route cleanup | `preview_session.py` service, `quick_process` refactor | **Medium** |

**Phases 4B–4D operate only on render_pipeline.py (extracting top-level helper functions).** The core `run_render_pipeline`/`_render_part` orchestration remains untouched until the helper extraction creates enough space to see clearly.

**Phases 4E–4H are independent and can be scheduled in any order after 4D is complete.** The diagram above orders them by value/risk ratio, not strict dependency.

---

## 9. First Implementation Recommendation

**Phase 4B: Extract Asset Pipeline (`orchestration/asset_pipeline.py`)**

**Why asset pipeline first (not overlay composite, not db, not render_engine):**

The four `_maybe_*` post-assembly functions are the safest extraction candidates in the entire codebase:

1. They are already named top-level functions (not inlined in `_render_part`). Extraction is `cut → paste → re-export`. No refactoring needed.
2. They contain zero FFmpeg command building. They delegate entirely to `remotion_adapter` (already a clean service). There is no risk of breaking a filter chain.
3. They have clear parameters (payload, Path, job context identifiers) and a clear return value (duration float or None). The boundary is unambiguous.
4. They are called from the post-render assembly section of `_render_part`, which is its own logical block. Updating the call site is a 1-line import change.
5. The pattern this establishes — extract function, add re-export, update call site, run tests — is exactly the pattern that every subsequent phase uses. Phase 4B is the proof of concept for the entire extraction strategy.

**Why NOT overlay composite first:** `composite_overlays_on_base_clip` is already in `render_engine.py` (not `render_pipeline.py`). Extracting it from render_engine into `services/render/overlay_compositor.py` is a Phase 4E task. The most urgent problem is `render_pipeline.py` (6,064 lines). Asset pipeline extraction reduces it by ~350 lines and four top-level functions.

**Why NOT split db.py first:** `db.py` split requires moving `connection.py` first. `get_conn` is imported directly by every route, service, and orchestration file. Breaking `get_conn` during an extraction would fail silently in many places. The extraction value is real but the blast radius on failure is app-wide.

**Why NOT split render_engine.py first:** The render functions (`render_base_clip`, `composite_overlays_on_base_clip`, `render_part_smart`) all depend on shared infrastructure (`_run_ffmpeg_with_retry`, `probe_video_metadata`, etc.) that is also in render_engine.py. The infrastructure must be extracted first, creating a new module, before the renderers can safely be moved to their own files. This makes render_engine.py split a 5-step process (infrastructure → clip ops → base clip → composite → legacy). The asset pipeline extract is a 1-step process.

**Why NOT AI system first:** The AI system is already modularized into 60+ files. It is not a god file. Its problem is the RAG system not being wired — that is a feature task, not a modularization task.

---

## 10. Files Safe to Extract First

These functions are safe to extract in Phase 4B–4D because they are already top-level named functions in render_pipeline.py and have no cross-phase dependencies:

| Function | Phase | Lines (approx) |
|---|---|---|
| `_maybe_prepend_remotion_hook_intro` | 4B | ~90 |
| `_maybe_prepend_asset_intro` | 4B | ~40 |
| `_maybe_append_asset_outro` | 4B | ~40 |
| `_maybe_apply_asset_logo` | 4B | ~45 |
| `_validate_render_output` | 4C | ~110 |
| `_assess_output_quality` | 4C | ~125 |
| `_resume_output_valid` | 4C | ~35 |
| `_render_part_failure_detail` | 4C | ~12 |
| `_duration_tolerance` | 4C | ~10 |
| `_stall_deadline` | 4C | ~5 |
| `_failed_part_progress` | 4C | ~14 |
| `_maybe_cleanup_narration_audio` | 4D | ~70 |
| `_job_log` | 4D | ~25 |
| `_append_json_line` | 4D | ~9 |
| `_render_error_code` | 4D | ~17 |
| `_emit_render_event` | 4D | ~40 |
| `_event_from_stage` | 4D | ~4 |
| `_resolve_job_log_dir` | 4D | ~16 |
| `_render_progress_timer` | 4D | ~100 |

**Total: ~807 lines removed from render_pipeline.py across Phases 4B–4D.** This reduces the file from 6,064 to ~5,257 lines — modest but these are the safest reductions to validate the pattern.

---

## 11. Files Risky to Extract Later

These require dedicated planning before extraction:

| Function / cluster | Risk | Reason |
|---|---|---|
| `run_render_pipeline` | **Critical** | Public API entry point; called from `routes/render.py`; signature must not change; contains 3,000+ lines of orchestration |
| `_render_part` inner function | **High** | Closure over 50+ variables from `run_render_pipeline`; extracting requires materializing all closed-over state as explicit parameters |
| `render_part_smart` | **High** | Permanent fallback for overlay path; signature must never change; `RENDER_BOUNDARIES.md` has explicit invariants |
| `db.get_conn` | **High** | Imported by 30+ modules; any broken import causes silent runtime failure |
| `db.init_db` | **High** | Called at application startup; breaking this crashes the server before routes are registered |
| `_build_variant_segments` | **Medium** | Coupled to AI plan shape via many `getattr(payload, ...)` patterns; safe to move but must not be refactored during move |
| Scoring helpers in render_pipeline.py | **Medium** | `resolve_combined_score_weights` is called from both `render_pipeline.py` and potentially `viral_scoring.py`; check all callers before moving |

---

## 12. Naming Rules

**Allowed naming patterns for new modules:**

| Module | Naming rationale |
|---|---|
| `asset_pipeline.py` | Describes the asset injection stage (intro/outro/logo) |
| `qa_pipeline.py` | Describes the output quality assurance stage |
| `audio_pipeline.py` | Describes audio cleanup orchestration |
| `render_events.py` | Describes render event emission utilities |
| `ffmpeg_helpers.py` | Describes shared FFmpeg utilities |
| `clip_ops.py` | Describes clip-level operations (cut, silence trim) |
| `base_clip_renderer.py` | Describes the function it contains |
| `overlay_compositor.py` | Describes the function it contains |
| `legacy_renderer.py` | Describes the all-in-one legacy render path |
| `jobs_repo.py` | Standard repository pattern naming |
| `uploads_repo.py` | Standard repository pattern naming |
| `platform_repo.py` | Standard repository pattern naming |
| `creator_repo.py` | Standard repository pattern naming |
| `preview_session.py` | Describes the session management service |

**Forbidden naming patterns:**

- `new_pipeline.py`, `pipeline_v2.py` — version suffixes encode churn, not meaning
- `render2.py`, `helpers_new.py` — numeric/adjective suffixes are noise
- `temp_module.py`, `phase4_utils.py` — phase-number names must never appear in runtime code
- `utils.py` (standalone) — too generic; every module would want to import from it

---

## 13. Clean Code Rules

For every extraction PR:

1. **No logic changes** — move only. No renaming, no parameter reordering, no adding/removing defaults.
2. **No added logging** — the function's existing log calls move with it. No new log lines during extraction.
3. **No added type hints** — extract first, annotate later as a separate cleanup.
4. **No dead code removal** — if a private helper inside an extracted function appears unused, note it but do not delete it in the extraction PR. Deletion is a follow-up.
5. **No docstring addition** — existing docstrings move with functions; new docstrings are written in a cleanup PR.
6. **No format changes** — preserve existing indentation, blank line style, and comment placement to keep the diff minimal.
7. **Re-export at old location until all callers are migrated** — the re-export is removed only when no import of the old path remains in the codebase.

---

## 14. Testing Strategy

**Test requirements per extraction phase:**

| Check | When | How |
|---|---|---|
| Import test | After every extraction | `python -c "from app.orchestration.asset_pipeline import _maybe_prepend_remotion_hook_intro"` |
| Backward-compat import test | After adding re-export | `python -c "from app.orchestration.render_pipeline import _maybe_prepend_remotion_hook_intro"` |
| Behavior parity test | After extraction | Run existing tests for the extracted function from its new location |
| Feature flag matrix test | After any overlay-path change | `python -m pytest tests/test_composite_overlays.py tests/test_render_base_clip.py -v` |
| Full suite | After each PR merges | `python -m pytest tests/ --tb=short` — accept only the pre-existing 8 failures |
| No API schema change | After route cleanup phases | `python -m pytest tests/test_schemas.py` — if this file exists |
| Manifest round-trip | After any manifest-touching change | `python -m pytest tests/test_base_clip_manifest.py -v` |
| Fallback path test | After any overlay-path change | Confirm `render_part_smart` is still callable with its existing signature |

**Tests to add for Phase 4B (asset pipeline extraction):**
- `test_asset_pipeline.py`: import test from new location, assert backward-compat import works, assert `_maybe_prepend_remotion_hook_intro` with `remotion_hook_intro=False` returns 0.0 without calling `generate_hook_intro`.

**Tests to add for Phase 4C (qa pipeline extraction):**
- `test_qa_pipeline.py`: import test, `_validate_render_output` on missing file, on zero-size file, on duration-mismatch file (mock probe), on valid file.

**Tests to add for Phase 4E (render_engine.py split):**
- Import tests for all re-exports from `render_engine.py`.
- `_run_ffmpeg_with_retry` still reachable from both `render_engine` and `services/render/ffmpeg_helpers`.
- `render_base_clip` imports from `services/render/base_clip_renderer` but is re-exported from `render_engine`.

---

## 15. Docs Sync Strategy

**After each phase:**

| Document | Update required |
|---|---|
| `docs/restructure/MIGRATION_HISTORY.md` | Add phase entry: status, shipped changes, contracts introduced |
| `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` | Update render layer table if function locations change; update last-updated date |
| `docs/architecture/RENDER_BOUNDARIES.md` | Update file paths in ownership table as functions move |
| `docs/review/TECHNICAL_DEBT_REPORT.md` | Mark C1 sub-items complete as each cluster is extracted |
| `docs/review/BRUTAL_REVIEW_SUMMARY.md` | Update "What is not production-ready" test coverage bullet as coverage expands |

**Docs that do NOT need updating per phase** (they describe behavior/contracts, not file locations):
- `FEATURE_FLAG_MATRIX.md` — flag behavior does not change
- `AUDIO_PIPELINE.md` — audio ownership invariants do not change
- `OVERLAY_PIPELINE.md` — composite behavior does not change
- `TIMELINE_SEMANTICS.md` — timeline contracts do not change

**Docs that must never claim shipped until the code is merged:**
- All plan docs use `**Status**: PLANNING` until the implementing PR is merged.
- MIGRATION_HISTORY.md entries must include commit hash.

---

## 16. Risk Checklist

Before starting each implementation phase, verify:

- [ ] The target functions are already top-level (not inlined inside another function)
- [ ] All imports used by the function are available in the new module's location
- [ ] The function does not read from any module-level mutable state in render_pipeline.py (e.g., `_JOB_LOG_DIRS`, `_render_active_count`)
- [ ] The function has no closure dependency on variables from `run_render_pipeline` or `_render_part`
- [ ] A backward-compat re-export will be added at the old import location
- [ ] The full test suite passes before the PR is submitted
- [ ] No API endpoint signature changes were introduced
- [ ] No `RenderRequest` field was added, removed, or renamed
- [ ] No DB schema changes were made
- [ ] No feature flag behavior was altered
- [ ] `render_part_smart()` signature is unchanged

---

## 17. What Must NOT Change

**Hard invariants across all Phase 4 work:**

| What | Why |
|---|---|
| `run_render_pipeline(job_id, payload, resume_mode, *, load_session_fn, cleanup_session_fn)` signature | Called from `routes/render.py`; changing this requires an API change |
| `render_part_smart()` signature and behavior | Permanent fallback for overlay path; `RENDER_BOUNDARIES.md` invariant |
| `composite_overlays_on_base_clip()` — no atempo, no setpts, `-c:a copy` | Audio ownership invariant; double-atempo prevention |
| `render_base_clip()` — no ass=, no drawtext= | Base clip must be overlay-free; Phase 3 contract |
| `mix_narration_audio()` signature | Called from render_pipeline.py; Phase 0 fix preserved |
| Feature flag defaults (`FEATURE_BASE_CLIP_FIRST=0`, `FEATURE_OVERLAY_AFTER_BASE_CLIP=0`) | Production safety — flags default OFF |
| All public API endpoint paths and response schemas | Frontend depends on these |
| SQLite schema and column names | Existing jobs/parts in DB depend on exact column names |
| `TimelineMap` and `BaseClipManifest` public field names | Manifest JSON files already written to disk by existing renders |
| `db.py` module-level public function names | Imported by 30+ modules; breaking these is an app-wide crash |

---

## 18. Exact Implementation Order

```
Phase 4B (first code PR):
  1. Create backend/app/orchestration/asset_pipeline.py
  2. Move: _maybe_prepend_remotion_hook_intro, _maybe_prepend_asset_intro,
           _maybe_append_asset_outro, _maybe_apply_asset_logo
  3. Add backward-compat re-exports in render_pipeline.py
  4. Add tests/test_asset_pipeline.py
  5. Run: python -m pytest tests/ --tb=short
  6. Update MIGRATION_HISTORY.md
  7. Commit: "phase 4b extract asset pipeline"

Phase 4C (second code PR):
  1. Create backend/app/orchestration/qa_pipeline.py
  2. Move: _validate_render_output, _assess_output_quality, _resume_output_valid,
           _render_part_failure_detail, _duration_tolerance, _stall_deadline,
           _failed_part_progress, output path helpers (_resolve_output_dir etc.)
  3. Add backward-compat re-exports in render_pipeline.py
  4. Add tests/test_qa_pipeline.py
  5. Run: python -m pytest tests/ --tb=short
  6. Update MIGRATION_HISTORY.md
  7. Commit: "phase 4c extract qa pipeline"

Phase 4D (third code PR):
  1. Create backend/app/orchestration/audio_pipeline.py
  2. Move: _maybe_cleanup_narration_audio
  3. Create backend/app/orchestration/render_events.py
  4. Move: _job_log, _append_json_line, _render_error_code, _emit_render_event,
           _event_from_stage, _resolve_job_log_dir, _render_progress_timer
  5. Add backward-compat re-exports in render_pipeline.py
  6. Run: python -m pytest tests/ --tb=short
  7. Update MIGRATION_HISTORY.md
  8. Commit: "phase 4d extract audio and event pipeline"

Phase 4E (fourth code PR — split render_engine.py):
  Sub-step 4E-1: Create services/render/ffmpeg_helpers.py
    Move all FFmpeg infrastructure and filter builders
    Add re-exports in render_engine.py
    Run full tests

  Sub-step 4E-2: Create services/render/clip_ops.py
    Move cut_video, detect_silence_trim_offset, detect_bad_first_frame, apply_micro_pacing
    Add re-exports in render_engine.py
    Run full tests

  Sub-step 4E-3: Create services/render/base_clip_renderer.py
    Move render_base_clip
    Add re-export in render_engine.py
    Run full tests (TestRenderBaseClipBgm must pass)

  Sub-step 4E-4: Create services/render/overlay_compositor.py
    Move composite_overlays_on_base_clip
    Add re-export in render_engine.py
    Run full tests (TestCompositeAudioInvariantsPhase3C must pass)

  Sub-step 4E-5: Create services/render/legacy_renderer.py
    Move render_part_smart (and render_part)
    Add re-export in render_engine.py — this is the LAST step; render_part_smart is the fallback
    Run full tests

  Commit per sub-step. Never bundle multiple sub-steps.

Phase 4F: Split db.py — see risk notes; requires dedicated planning mini-doc before implementation.

Phase 4G: Split subtitle_engine.py — defer until after Phase 4E validates the services/render/ pattern.

Phase 4H: Route cleanup — extract preview_session.py from routes/render.py.
```

---

## 19. Phase 4B Prompt Recommendation

When Phase 4A planning is approved, use this prompt for Phase 4B:

```
Phase 4B — Extract Asset Pipeline

Goal:
Extract the four post-assembly hook/asset functions from render_pipeline.py
into a new module: backend/app/orchestration/asset_pipeline.py

Strict rules:
- DO NOT modify any function logic
- DO NOT change function signatures
- DO NOT remove the original functions from render_pipeline.py
  (add backward-compat re-exports instead)
- DO NOT change any tests that currently pass
- DO NOT touch render_engine.py, db.py, routes/render.py, or any frontend file
- DO NOT change RenderRequest, API schemas, WebSocket payloads, or DB schema

Functions to move:
- _maybe_prepend_remotion_hook_intro (render_pipeline.py line ~645)
- _maybe_prepend_asset_intro (render_pipeline.py line ~734)
- _maybe_append_asset_outro (render_pipeline.py line ~775)
- _maybe_apply_asset_logo (render_pipeline.py line ~816)

Steps:
1. Read each function verbatim
2. Create backend/app/orchestration/asset_pipeline.py with the 4 functions
3. Add backward-compat re-exports in render_pipeline.py:
   from app.orchestration.asset_pipeline import (
       _maybe_prepend_remotion_hook_intro,
       _maybe_prepend_asset_intro,
       _maybe_append_asset_outro,
       _maybe_apply_asset_logo,
   )
4. Add backend/tests/test_asset_pipeline.py with import smoke tests
5. Run: python -m pytest tests/ --tb=short
6. If tests pass: commit "phase 4b extract asset pipeline"
7. If tests fail: report exact failures, do NOT commit

Source of truth for boundaries: docs/architecture/RENDER_BOUNDARIES.md
```

---

## 20. Definition of Done

Phase 4A is done when:

- [x] `docs/restructure/PHASE_4A_BACKEND_MODULARIZATION_PLAN.md` created and complete
- [x] `docs/restructure/MIGRATION_HISTORY.md` has Phase 4A entry
- [x] `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` updated to post Phase 3C.5
- [x] `docs/review/TECHNICAL_DEBT_REPORT.md` updated: C1 notes Phase 4A plan in progress
- [x] No code files changed
- [x] Full test suite still passing (5,787+ pass, 8 pre-existing failures)
- [x] Committed and pushed on branch `restructure/output-timeline-architecture`

Phase 4B is done (2026-05-22, commit `2be39cc`):
- [x] `asset_pipeline.py` created with 4 functions
- [x] `render_pipeline.py` has re-exports for all 4 functions (callers unchanged)
- [x] `tests/test_asset_pipeline.py` added and passing (23 tests)
- [x] Full suite: 5,810 passed, 1 skipped, 8 pre-existing failures
- [x] MIGRATION_HISTORY.md updated with Phase 4B entry + commit hash
- [x] `render_pipeline.py` reduced 6,064 → 5,779 lines (−285)

Phase 4C is done (2026-05-22, commit `f0666c5`):
- [x] `qa_pipeline.py` created with 7 QA functions
- [x] `render_pipeline.py` has re-exports for all 7 functions (callers unchanged)
- [x] `tests/test_qa_pipeline.py` added and passing (34 tests)
- [x] Full suite: 5,844 passed, 1 skipped, 8 pre-existing failures
- [x] MIGRATION_HISTORY.md updated with Phase 4C entry
- [x] `render_pipeline.py` reduced 5,779 → 5,510 lines (−269)

Phase 4D is done (2026-05-22):
- [x] `audio_pipeline.py` created with `_maybe_cleanup_narration_audio`
- [x] `render_events.py` extended with `_event_from_stage`, `_resolve_job_log_dir`, `_render_progress_timer`, `_PROGRESS_TICK_SEC`
- [x] `render_pipeline.py` has re-exports for all moved names (callers unchanged)
- [x] `tests/test_audio_pipeline.py` added and passing (9 tests)
- [x] `tests/test_render_events.py` added and passing (15 tests)
- [x] Full suite: 5,868 passed, 1 skipped, 8 pre-existing failures
- [x] MIGRATION_HISTORY.md updated with Phase 4D entry
- [x] `render_pipeline.py` reduced 5,510 → 5,340 lines (−170)

Phase 4 is fully done when:
- [ ] `render_pipeline.py` contains only orchestration logic (no utility function clusters)
- [ ] `render_engine.py` contains only backward-compat re-exports
- [ ] `db.py` contains only backward-compat re-exports
- [ ] All new modules have dedicated test files
- [ ] Dependency direction rule has no violations (verified by grep)
- [ ] Full test suite passes with no new failures
- [ ] All architecture docs updated to reflect final file locations
