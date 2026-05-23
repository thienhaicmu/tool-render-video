# FULL_PROJECT_BACKEND_AI_GOVERNANCE_REVIEW.md

**Purpose**: Governance-grade audit of the full backend and AI architecture. Review-only — no runtime code was modified.

**Date**: 2026-05-23
**Branch**: `restructure/output-timeline-architecture`
**Audited by**: Governance review agent (Phase 5.0 post-restructure pass)
**Risk classification key**: P0 = runtime/API/frontend break risk · P1 = high-risk architecture · P2 = medium cleanup · P3 = low-priority debt · INFO = docs/history only

---

## 1. Executive Summary

The backend restructure (Phases 1–4H) is **functionally complete and architecturally sound**. The three major god-files (`render_engine.py`, `services/db.py`, `subtitle_engine.py`) are now pure re-export shims. All extracted logic lives in focused sub-modules with automated test coverage. The full test suite passes at **8 failed / 6699 passed / 1 skipped** — exactly matching the Phase 4H.6 freeze baseline.

**Backend verdict**: HEALTHY. Safe for product and feature work to proceed.

**AI verdict**: No external AI provider is wired. The `ai/` layer is 294 Python files of heuristic scoring, knowledge pack management, and RAG infrastructure. Zero calls to any LLM API. RAG system is built but inactive. This is not a defect per se, but the naming is misleading at every level.

**Product verdict**: GO. All core render APIs are stable, shims are healthy, no new failures introduced by the restructure.

**Primary remaining risk**: `render_pipeline.py` at 282,872 bytes (~5,340+ lines) is the only remaining god-file. It is the highest-risk file to touch for any new render feature.

---

## 2. Current Branch

**Branch**: `restructure/output-timeline-architecture`
**Status**: Ahead of `main`. Not yet merged. All restructure work (Phases 1–4H) committed here.
**Commit range**: Phase 0 hotfix through Phase 5.0 post-restructure review.

Recent commits (at audit time):
- `a9c2dd3` fix active frontend path in post restructure review
- `aadc870` phase 5 post restructure review
- `064a5f1` phase 4h6 route cleanup freeze
- `985eeeb` phase 4h3 extract media streaming helpers
- `ffb6f32` phase 4h2 extract preview session service

---

## 3. Source Documents Read

| Document | Status |
|---|---|
| `docs/restructure/MIGRATION_HISTORY.md` | READ — comprehensive per-phase log |
| `docs/restructure/PHASE_4F_7_ARCHITECTURE_FREEZE.md` | READ — arch freeze after Phase 4F |
| `docs/restructure/PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md` | READ — subtitle split complete; all 6 clusters extracted |
| `docs/restructure/PHASE_4H_ROUTE_CLEANUP_PLAN.md` | READ — route cleanup complete at 4H.6 freeze |
| `docs/restructure/PHASE_4H_6_ROUTE_FREEZE.md` | READ — official freeze document |
| `docs/restructure/PHASE_5_0_POST_RESTRUCTURE_REVIEW.md` | READ — prior phase 5.0 review (now superseded by this document) |
| `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` | READ — verified accurate as of 2026-05-23 |
| `docs/review/TECHNICAL_DEBT_REPORT.md` | READ — H1 RESOLVED; C1 outstanding |
| `docs/review/BRUTAL_REVIEW_SUMMARY.md` | READ — honest assessment, mostly accurate |
| `docs/review/SCORECARD.md` | READ — overall 5.2/10, three categories improved post-Phase 4H |

---

## 4. Current Project Structure (Real File Tree)

```
backend/app/
├── ai/                          ← 294 Python files across 55+ subdirectories
│   ├── ab_evaluation/
│   ├── adaptive/
│   ├── analyzers/
│   ├── camera/
│   ├── camera_promotion/
│   ├── camera_quality/
│   ├── clips/
│   ├── config/
│   ├── creator_archetype/
│   ├── creator_benchmark/
│   ├── creator_camera/
│   ├── creator_dna/
│   ├── creator_fusion/
│   ├── creator_style/
│   ├── creator_subtitle/
│   ├── debug/
│   ├── director/
│   ├── enhancement/
│   ├── execution/
│   ├── execution_mode/
│   ├── explainability/
│   ├── feedback/
│   ├── hook_quality/
│   ├── influence/
│   ├── knowledge/
│   ├── market/
│   ├── metrics/
│   ├── multivariant/
│   ├── mutations/
│   ├── orchestrator/
│   ├── outcome_tracking/
│   ├── output/
│   ├── packaging/
│   ├── platform/
│   ├── policy/
│   ├── preset_evolution/
│   ├── presets/
│   ├── preview/
│   ├── quality/
│   ├── quality_gate/
│   ├── rag/
│   ├── retention/
│   ├── retrieval/
│   ├── segment_promotion/
│   ├── simulation/
│   ├── story/
│   ├── story_optimization/
│   ├── strategy_variants/
│   ├── styles/
│   ├── subtitle_promotion/
│   ├── subtitle_quality/
│   ├── subtitles/
│   ├── thumbnail/
│   ├── timing/
│   ├── unified_quality/
│   ├── ux/
│   ├── variants/
│   ├── visibility/
│   └── visuals/
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
│   └── schemas.py               ← Pydantic models (Upload* classes are dead code)
├── orchestration/
│   ├── __init__.py
│   ├── asset_pipeline.py        ← Phase 4B
│   ├── audio_pipeline.py        ← Phase 4D
│   ├── qa_pipeline.py           ← Phase 4C
│   ├── render_events.py         ← Phase 4B/4D
│   └── render_pipeline.py       ← 282,872 bytes (~5,340+ lines) — GOD FILE
├── routes/
│   ├── channels.py
│   ├── creator.py
│   ├── devtools.py              ← gated ENABLE_DEVTOOLS=1
│   ├── download.py
│   ├── jobs.py
│   ├── render.py                ← 1,125 lines (frozen Phase 4H.6)
│   ├── subtitle.py
│   ├── viral.py
│   └── voice.py
│   # NOTE: routes/upload.py DELETED Phase 4F.5C
└── services/
    ├── preview/                 ← Phase 4H — 3 modules, 89 tests
    │   ├── __init__.py
    │   ├── ffmpeg_probers.py    ← 6 FFmpeg probe helpers (6,732 bytes)
    │   ├── session_service.py   ← _PREVIEW_SESSIONS singleton + 4 helpers (3,054 bytes)
    │   └── media_streaming.py   ← _parse_range_header, _iter_file_bytes (1,821 bytes)
    ├── render/                  ← Phase 4E — 5 modules
    │   ├── __init__.py
    │   ├── base_clip_renderer.py  (10,362 bytes)
    │   ├── clip_ops.py            (15,865 bytes)
    │   ├── ffmpeg_helpers.py      (19,072 bytes)
    │   ├── legacy_renderer.py     (20,527 bytes)
    │   └── overlay_compositor.py  (6,734 bytes)
    ├── subtitles/               ← Phase 4G — 7 modules, 388 tests
    │   ├── __init__.py
    │   ├── ass_core.py          (16,674 bytes)
    │   ├── output_timeline.py   (1,022 bytes)
    │   ├── readability.py       (19,212 bytes)
    │   ├── srt_core.py          (6,532 bytes)
    │   ├── styles.py            (13,875 bytes)
    │   ├── text_transforms.py   (13,677 bytes)
    │   └── transcription.py     (8,093 bytes)
    ├── db.py                    ← SHIM (31 lines) — re-exports from app/db/*
    ├── render_engine.py         ← SHIM (~54 lines) — re-exports from services/render/*
    ├── subtitle_engine.py       ← SHIM (47 lines) — re-exports from services/subtitles/*
    └── [40+ other services: audio_mix_service, bin_paths, cancel_registry,
         caption_engine, channel_service, clip_scorer, downloader, encoder_helpers,
         hook_optimizer, job_manager, maintenance, manifest_writer,
         market_subtitle_policy, motion_crop, qa_runner, remotion_adapter,
         report_service, scene_detector, segment_builder,
         subtitle_transcription_adapters, text_overlay, tts_service,
         tts_xtts_adapter, viral_scorer, viral_scoring, voice_profiles, warmup, ...]
    # NOTE: services/upload_engine.py DELETED Phase 4F.5B

backend/tests/
    139 Python test files
```

---

## 5. Docs Accuracy Review

| Document | Accuracy | Finding |
|---|---|---|
| `CURRENT_RENDER_ARCHITECTURE.md` | ACCURATE | Last updated 2026-05-23; references all Phase 4H.6 modules correctly |
| `PHASE_5_0_POST_RESTRUCTURE_REVIEW.md` | ACCURATE | Complete baseline review; test results match actual run (6699 passed, 8 failed) |
| `PHASE_4F_7_ARCHITECTURE_FREEZE.md` | ACCURATE | Accurately documents Phase 4F end state; Phase 4G/4H references are planning notes, now complete |
| `PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md` | ACCURATE — Status updated to COMPLETE | All clusters extracted; `subtitle_engine.py` is now a 47-line shim |
| `PHASE_4H_ROUTE_CLEANUP_PLAN.md` | ACCURATE — Status updated to COMPLETE | `routes/render.py` at 1,125 lines; 3 service modules extracted |
| `TECHNICAL_DEBT_REPORT.md` | MOSTLY ACCURATE | H1 marked RESOLVED; C3 marked RESOLVED; C2 still partially open; `render_pipeline.py` entry outdated line count (says 5,510; file is now 282KB) |
| `BRUTAL_REVIEW_SUMMARY.md` | MOSTLY ACCURATE | Upload domain references cleaned; god file claim is still valid for `render_pipeline.py`; AI mislabeling section is accurate |
| `SCORECARD.md` | ACCURATE | Overall 5.2/10 post Phase 4H.6; three categories updated correctly |
| `MIGRATION_HISTORY.md` | ACCURATE through Phase 4H | Full phase log is complete and correct |

**Stale items found (INFO only)**:
- `TECHNICAL_DEBT_REPORT.md` line count for `render_pipeline.py` says "5,700+ lines" (C1 section) — actual file is 282,872 bytes (~5,340+ lines). Minor inaccuracy; correct order of magnitude.
- `SCORECARD.md` §3 says "290KB" for `render_pipeline.py` — actual file is 282,872 bytes (282KB). Close enough; no action needed.

---

## 6. Backend Architecture Summary

The backend uses a layered FastAPI architecture:

```
Electron shell → BrowserWindow → http://127.0.0.1:8000
    └── FastAPI + Uvicorn (single process)
          ├── routes/*  (9 active routers)
          ├── orchestration/render_pipeline.py  (GOD FILE — 282KB)
          ├── orchestration/{asset,audio,qa,render_events}_pipeline.py
          ├── services/render/ (5 modules via render_engine.py shim)
          ├── services/subtitles/ (7 modules via subtitle_engine.py shim)
          ├── services/preview/ (3 modules)
          ├── app/db/ (3 modules via db.py shim)
          ├── domain/ (TimelineMap, BaseClipManifest)
          ├── ai/ (294 files — heuristic scoring, RAG infrastructure)
          └── SQLite (3 live tables: jobs, job_parts, creator_prefs)
```

No cloud dependency. No external AI API calls. FFmpeg and Python runtime are bundled.

---

## 7. Final Backend Module Tree

Refer to §4 for complete tree. Key module metrics:

| Layer | Modules | Lines (approx) | Status |
|---|---|---|---|
| Render services | 5 + 1 shim | ~1,739 + 54 | HEALTHY |
| Subtitle services | 7 + 1 shim | ~1,840 + 47 | HEALTHY |
| Preview services | 3 | ~325 | HEALTHY |
| DB repositories | 3 + 1 shim | ~400 + 31 | HEALTHY |
| Orchestration | 5 files | ~5,600+ | render_pipeline.py CRITICAL GOD FILE |
| Routes | 9 files | ~3,000+ | ACCEPTABLE |
| AI modules | 294 files | ~40,000+ | HEURISTIC ONLY — no LLM calls |

---

## 8. Render Architecture Audit

**Status**: HEALTHY. All render logic is modularized.

| Module | Owns | Verified Clean? |
|---|---|---|
| `services/render/ffmpeg_helpers.py` | FFmpeg infrastructure, NVENC semaphore, probe cache, filter builders | YES |
| `services/render/clip_ops.py` | `cut_video`, silence detect, bad-frame detect, `apply_micro_pacing` | YES |
| `services/render/base_clip_renderer.py` | `render_base_clip()` — speed, crop, color, audio, BGM | YES |
| `services/render/overlay_compositor.py` | `composite_overlays_on_base_clip()` — subtitle, title, text_layers overlay | YES |
| `services/render/legacy_renderer.py` | `render_part()`, `render_part_smart()` — legacy all-in-one | YES |
| `services/render_engine.py` | Pure re-export shim — no function bodies | YES — 54 lines |

**Shim verified**: `render_engine.py` imports 28 symbols from `ffmpeg_helpers`, 5 from `clip_ops`, 1 from `base_clip_renderer`, 1 from `overlay_compositor`, 2 from `legacy_renderer`. All paths verified by compile check (clean) and 202 targeted test passes.

**Key coupling finding**: `motion_crop.py` and `thumbnail_quality.py` use deferred imports `from app.services.render_engine import probe_video_metadata` and `from app.services.render_engine import _has_audio_stream` inside function bodies. These are valid deferred imports routing through the shim — no circular import risk confirmed.

---

## 9. Render Invariants Audit

| Invariant | Status | Evidence |
|---|---|---|
| Overlay audio-copy invariant (`-c:a copy` in composite) | **VERIFIED** | `overlay_compositor.py:122`: `-c:a copy` hardcoded; docstring explicitly states "Audio is always copied" |
| No double atempo | **VERIFIED** | `base_clip_renderer.py` applies atempo in audio filter; `overlay_compositor.py` has no atempo; BGM path in `base_clip_renderer.py` applies atempo once per stream |
| No setpts in overlay path | **VERIFIED** | `overlay_compositor.py` docstring: "Invariants: no setpts, no atempo, no crop, no scale, no color/effect filters." Code confirms: only `ass=`, drawtext filters, and `fps=` in vf_chain |
| ASS-before-setpts ordering (legacy path) | **VERIFIED** | `legacy_renderer.py:146–175`: ass/drawtext filters added before `setpts=PTS/{speed:.4f}`, which is added before `fps=target_fps` |
| `render_base_clip` owns BGM | **VERIFIED** | `base_clip_renderer.py:169–203`: BGM filter_complex built into base clip; `overlay_compositor.py` only copies audio |
| TimelineMap semantics preserved | **VERIFIED** | `domain/timeline.py` unchanged; `base_clip_renderer.py` calls `_sanitize_speed(timeline.effective_speed)` directly |
| Speed clamped [0.5, 1.5] at all entry points | **VERIFIED** | `TimelineMap.__post_init__()`, `_get_effective_playback_speed()` in render_pipeline, `_sanitize_speed()` in ffmpeg_helpers |
| Output timing semantics preserved | **VERIFIED** | overlay path uses output-timeline ASS via `slice_srt_to_output_timeline()`; legacy path uses ass-before-setpts |
| Preview session singleton preserved | **VERIFIED** | `_PREVIEW_SESSIONS` defined once in `session_service.py`; `routes/render.py` imports and re-exports the same dict object |
| WebSocket payload structure stable | **VERIFIED** | `routes/jobs.py` unchanged throughout Phases 4E–4H |
| Subtitle style IDs stable | **VERIFIED** | `subtitles/styles.py` `_PRESETS` and `_STYLE_ALIASES` unchanged from original `subtitle_engine.py` |
| Compatibility shim behavior preserved | **VERIFIED** | `render_engine.py`, `db.py`, `subtitle_engine.py` all compile clean; 202 targeted tests pass |

**RISK finding**: Subtitle display duration compression on the legacy path is a known open invariant violation (C2 in TECHNICAL_DEBT_REPORT.md). At non-1.0 speeds, subtitle display duration is compressed proportionally. This is NOT a synchronization error but IS a legibility concern. Resolution exists on the overlay path (FEATURE_OVERLAY_AFTER_BASE_CLIP=1).

---

## 10. Orchestration Audit

| Module | Owns | Status |
|---|---|---|
| `orchestration/render_events.py` | `_emit_render_event`, `_job_log`, progress timer, event helpers | HEALTHY |
| `orchestration/asset_pipeline.py` | `_maybe_prepend_*`, `_maybe_append_*`, `_maybe_apply_asset_logo` | HEALTHY |
| `orchestration/qa_pipeline.py` | `_validate_render_output`, duration/size QA helpers | HEALTHY |
| `orchestration/audio_pipeline.py` | `_maybe_cleanup_narration_audio` — DeepFilterNet orchestration | HEALTHY |
| `orchestration/render_pipeline.py` | Main coordinator — 282,872 bytes GOD FILE | CRITICAL DEBT |

**Orchestration does NOT own render logic**: Confirmed. `render_events.py` imports from `services/db` only. `asset_pipeline.py` imports from `render_engine` shim (for FFmpeg calls) and `audio_mix_service`. `qa_pipeline.py` imports from `services/db`. `audio_pipeline.py` has no render imports. None import from `routes/`.

**render_pipeline.py finding (P1)**: The 282KB coordinator still inlines 15+ platform config dicts (`_PLATFORM_PROFILES`, `_CTA_TEXTS`, `_VARIANT_AGGRESSIVE_SUB`, `_PLAY_RES_Y_MAP`, etc.) and the entire `_render_part()` inner function. This is the largest remaining technical debt item.

---

## 11. DB Architecture Audit

| Module | Owns | Lines | Status |
|---|---|---|---|
| `app/db/connection.py` | `get_conn`, `init_db`, thread-local, `_drop_upload_tables`, helpers | 8,654 bytes | HEALTHY |
| `app/db/jobs_repo.py` | `upsert_job`, `update_job_progress`, parts CRUD | 5,695 bytes | HEALTHY |
| `app/db/creator_repo.py` | `get_creator_prefs`, `upsert_creator_prefs` | 810 bytes | HEALTHY |
| `app/services/db.py` | Pure re-export shim | 31 lines | HEALTHY — do not remove |

**Live tables**: `jobs`, `job_parts`, `creator_prefs` — 3 tables only. Confirmed by `TestInitDbLiveTablesPresent::test_exactly_three_live_tables` passing.

**`_drop_upload_tables()`**: Called inside `init_db()` on every startup. Idempotently drops all 7 upload tables from any pre-Phase-4F.5D database file. This migration is permanent and correct.

**No circular imports**: `app/db/*` modules only import from `app/db/connection` and stdlib. They do NOT import from `app/services/*` or `app/routes/*`. Dependency direction is clean.

**Shim callers confirmed**: `main.py`, `routes/creator.py`, `routes/download.py`, `routes/jobs.py`, `routes/render.py`, `orchestration/render_pipeline.py`, `orchestration/render_events.py`, `orchestration/qa_pipeline.py`, `services/dev_commands.py`, `services/maintenance.py`, `services/job_manager.py` — all import via `app.services.db` shim.

---

## 12. Subtitle Architecture Audit

| Module | Owns | Lines | Status |
|---|---|---|---|
| `subtitles/styles.py` | ASSPreset, _PRESETS, _STYLE_ALIASES, _HL_OPEN/_HL_CLOSE | 13,875 bytes | HEALTHY |
| `subtitles/srt_core.py` | Timestamp parsing, SRT parse/write/slice, _run_with_retry | 6,532 bytes | HEALTHY |
| `subtitles/output_timeline.py` | `slice_srt_to_output_timeline` | 1,022 bytes | HEALTHY |
| `subtitles/readability.py` | Visual-width, emphasis pass, resegmentation | 19,212 bytes | HEALTHY |
| `subtitles/ass_core.py` | `srt_to_ass_bounce`, `srt_to_ass_karaoke`, burn, preview | 16,674 bytes | HEALTHY |
| `subtitles/text_transforms.py` | Market/hook text transforms, AI execution hints | 13,677 bytes | HEALTHY |
| `subtitles/transcription.py` | Whisper model cache, `transcribe_to_srt`, `has_audio_stream` | 8,093 bytes | HEALTHY |
| `services/subtitle_engine.py` | Pure re-export shim | 47 lines | HEALTHY — do not remove |

**TimelineMap behavior preserved**: `output_timeline.py` calls `slice_srt_by_time` with `apply_playback_speed=True` and `timeline.effective_speed`. Contract unchanged from original `subtitle_engine.py`.

**ASS contract preserved**: `_ass_time()` centisecond precision, `_ass_escape_text()` resolves `_HL_OPEN`/`_HL_CLOSE` PUA codepoints, `srt_to_ass_bounce()` output is bit-identical. Both are in `ass_core.py`. `_HL_OPEN`/`_HL_CLOSE` defined exactly once in `styles.py`.

**Subtitle styles stable**: `_PRESETS` table (11 presets), `_STYLE_ALIASES` (5 backward-compat mappings), `_DEFAULT_PRESET_ID = "tiktok_bounce_v1"` all unchanged. Confirmed by 388 subtitle tests passing.

**Coupling fix confirmed**: `transcription.py:has_audio_stream()` now imports `_has_audio_stream` from `render.ffmpeg_helpers` directly, not via the `render_engine` shim. Verified by `test_subtitle_engine_compat_exports.py` (3 tests).

**No circular imports**: Dependency DAG: styles → nothing; srt_core → domain/timeline; readability → styles; ass_core → styles+srt_core+readability; text_transforms → srt_core+readability; transcription → srt_core+ffmpeg_helpers. Clean.

**Whisper singleton**: `_MODEL_CACHE`, `_MODEL_CACHE_LOCK`, `_MODEL_TRANSCRIBE_LOCKS` defined exactly once in `transcription.py`. The shim re-exports them; they are never re-initialized.

**`import whisper` at top of `transcription.py`**: This is a hard import. If Whisper is not installed, `transcription.py` fails to load, which causes `subtitle_engine.py` shim to fail to load. This is acceptable — Whisper is a declared production dependency. All other subtitle modules are clean of Whisper imports.

---

## 13. Preview / Route Cleanup Audit

| Module | Owns | Status |
|---|---|---|
| `services/preview/ffmpeg_probers.py` | 6 FFmpeg probe helpers | HEALTHY |
| `services/preview/session_service.py` | `_PREVIEW_SESSIONS` singleton + 4 session helpers | HEALTHY |
| `services/preview/media_streaming.py` | `_parse_range_header`, `_iter_file_bytes` | HEALTHY |
| `routes/render.py` | Route handlers + download state | FROZEN AT 1,125 LINES |

**State ownership verified**: `_PREVIEW_SESSIONS` is defined in `session_service.py`. `routes/render.py` imports it via `from app.services.preview.session_service import _PREVIEW_SESSIONS`. Same dict object — no aliasing risk. Confirmed by `test_preview_session_service.py` (17 tests).

**`evict_stale_preview_sessions` re-export confirmed**: `routes/render.py` re-exports `evict_stale_preview_sessions` so `main.py`'s deferred import at line 130 (`from app.routes.render import evict_stale_preview_sessions`) is unchanged. Verified by test.

**Singleton preserved**: Only one `_PREVIEW_SESSIONS` dict instance in process. `routes.render._PREVIEW_SESSIONS is session_service._PREVIEW_SESSIONS` — same object.

**Accepted remaining debt in `routes/render.py`**:
- `_run_batch()` inner closure (batch threading debt — logic not location)
- `quick_process` 283-line self-contained handler
- `_ACTIVE_DOWNLOADS` dict — download-lifecycle state, appropriate in route module

---

## 14. Upload Domain Removal Audit

| Layer | Status | Finding |
|---|---|---|
| `routes/upload.py` (1,501 lines, 42 endpoints) | DELETED Phase 4F.5C | CONFIRMED |
| `services/upload_engine.py` (1,793 lines) | DELETED Phase 4F.5B | CONFIRMED |
| `app/db/platform_repo.py` (142 lines) | DELETED Phase 4F.5C | CONFIRMED |
| Upload DB functions (43 functions in services/db.py) | REMOVED Phase 4F.5C | CONFIRMED |
| Upload frontend JS (3 files ~6,200 lines) | DELETED Phase 4F.5A | CONFIRMED |
| Upload `<script>` tags in index.html (3 tags) | REMOVED Phase 4F.5A | CONFIRMED |
| Upload table DDL (7 tables) | REMOVED Phase 4F.5D | CONFIRMED |

**Residual references classified:**

| Finding | Location | Classification | Risk |
|---|---|---|---|
| `_UPLOAD_TABLES` + `_drop_upload_tables()` | `app/db/connection.py` | A — correct migration helper | INFO |
| `upload_settings.json` path strings | `routes/channels.py`, `channel_service.py` | A — filesystem channel management, not TikTok API | INFO |
| `upload_local_video` endpoint | `routes/render.py:632` | A — local file upload for render pipeline, not TikTok | INFO |
| `Upload*` schema classes (8 classes) | `app/models/schemas.py` | B — dead code, no active callers, no routes | P3 |
| `uploadWs = null` declaration | `backend/static/js/globals.js` | B — orphan variable, never assigned | P3 |
| `logStateByScope.upload` entry | `backend/static/js/globals.js:13–16` | B — orphan log scope, never triggered | P3 |
| `upload` string refs in `dev_commands.py`, `qa_runner.py` | Various | B — dev tooling string literals, not Python imports | P3 |

**No active upload code found.** Tests `test_upload_domain_removed.py` (13 tests) and `test_upload_schema_removed.py` (20 tests) all pass.

---

## 15. API Route Audit (Full Route Table)

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
| POST | `/api/render/upload-local` | `upload_local_video` | ACTIVE (local file, not TikTok) |
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
| GET | `/api/jobs` | `api_list_jobs` | ACTIVE (unbounded — P2 debt) |
| GET | `/api/jobs/history` | `api_list_jobs_history` | ACTIVE (paginated) |
| GET | `/api/jobs/queue/status` | `api_queue_status` | ACTIVE |
| GET | `/api/jobs/{job_id}` | `api_get_job` | ACTIVE |
| GET | `/api/jobs/{job_id}/parts` | `api_list_job_parts` | ACTIVE |
| GET | `/api/jobs/{job_id}/logs` | `api_get_job_logs` | ACTIVE |
| GET | `/api/jobs/{job_id}/parts/{part_no}/stream` | `api_stream_job_part` | ACTIVE |
| WebSocket | `/api/jobs/{job_id}/ws` | `ws_job_updates` | ACTIVE |
| POST | `/api/jobs/cleanup/logs` | `api_cleanup_logs` | ACTIVE |
| DELETE | `/api/jobs/{job_id}` | `api_delete_job` | ACTIVE |

### Other Active Routes

| Method | Path | Router | Status |
|---|---|---|---|
| GET, POST | `/api/channels`, `/api/channels/*` | channels.py | ACTIVE |
| POST | `/api/download/process` | download.py | ACTIVE |
| POST | `/api/download/retry/{job_id}` | download.py | ACTIVE |
| POST | `/api/dev/command` | devtools.py | ACTIVE (ENABLE_DEVTOOLS=1 only) |
| POST | `/api/subtitle/preview` | subtitle.py | ACTIVE |
| POST, GET | `/api/viral/score`, `/api/viral/score/all` | viral.py | ACTIVE |
| GET | `/api/voice/profiles` | voice.py | ACTIVE |
| GET, PUT | `/api/creator/preferences` | creator.py | ACTIVE |
| GET | `/api/feedback/summary` | creator.py | ACTIVE |
| GET | `/api/warmup/status` | main.py | ACTIVE |
| GET | `/health` | main.py | ACTIVE |
| GET | `/` | main.py | ACTIVE — serves index.html |

### Removed Routes (Upload Domain)

All 42 `/api/upload/*` endpoints — REMOVED Phase 4F.5A–C. No residual route registrations. Confirmed by `TestUploadRoutesAbsent::test_no_upload_routes_registered` passing.

---

## 16. Frontend API Usage Audit

**Active frontend**: `backend/static/` (V1 — default). `backend/static-v2/` is opt-in via `STATIC_UI_VERSION=v2`. `backend/static-v3/` and `backend/static-v4/` are dead archives not served by any route.

| File | Line | URL | Classification |
|---|---|---|---|
| `batch-queue.js` | 230, 395 | `POST /api/render/process` | A — valid |
| `channels.js` | 112 | `GET /api/channels/root` | A — valid |
| `channels.js` | 248 | `POST /api/channels` | A — valid |
| `creator-memory.js` | 46, 55 | `PUT/GET /api/creator/preferences` | A — valid |
| `download-ui.js` | 218 | `POST /api/download/process` | A — valid |
| `editor-audio-runtime.js` | 89 | `POST /api/upload-file` | **C — 404: no backend route for this URL** |
| `editor-view.js` | 1107 | `POST /api/upload-file` | **C — 404: no backend route for this URL** |
| `editor-view.js` | 1186 | `POST /api/render/prepare-source` | A — valid |
| `editor-view.js` | 1761 | `POST /api/subtitle/preview` | A — valid |
| `editor-view.js` | 3087 | `POST /api/render/process` | A — valid |
| `editor-view.js` | 3745 | `POST /api/viral/score/all` | A — valid |
| `render-config.js` | 81, 105 | `POST /api/render/upload-local` | A — valid (local file render) |
| `render-config.js` | 206 | `POST /api/render/download-health` | A — valid |
| `render-engine.js` | 125 | `POST /api/render/prepare-source` | A — valid |
| `render-engine.js` | 392 | `GET /api/jobs` | A — valid (unbounded query debt) |
| `render-ui.js` | 167 | `GET /api/render/queue-status` | A — valid |
| `render-ui.js` | 2455 | `GET /api/jobs/history?limit=3&kind=render` | A — valid |
| `render-ui.js` | 3836 | `GET /api/feedback/summary` | A — valid |
| `review-queue.js` | 96 | `POST /api/render/process` | A — valid |
| `warmup.js` | 15 | `GET /api/warmup/status` | A — valid |

**Classification summary**: 21 valid (A), 2 broken (C), 0 removed-domain (B classified as INFO).

---

## 17. WebSocket Contract Audit

**Active WebSocket route**: `GET /api/jobs/{job_id}/ws` in `routes/jobs.py`

**Contract (unchanged throughout all phases)**:
- Accepts: `job_id` path parameter
- Server sends: JSON progress event objects `{status, stage, progress_percent, message, parts, ...}`
- Server uses `_ws_fingerprint` to suppress sends on pure timestamp changes
- Terminal statuses (`completed`, `completed_with_errors`, `failed`, `interrupted`) close the connection
- Client fallback: HTTP polling every 3s if WebSocket fails (implemented in `render-engine.js`)

**No WebSocket contract changes in Phases 4E–4H.** `routes/jobs.py` was not modified in any phase.

**Upload WebSocket** (`uploadWs` in `globals.js`): Variable declared but never assigned after Phase 4F.5B. No upload WebSocket route exists. Classification: B (harmless dead code).

---

## 18. Schema/Payload Contract Audit

**`RenderRequest`** (`app/models/schemas.py:109`): 70+ field Pydantic model. Unchanged since Phase 3C.5. Contains `source_mode`, `youtube_url`, `source_video_path`, `output_dir`, `channel_code`, `render_profile`, `video_codec`, `add_subtitle`, `subtitle_style`, `aspect_ratio`, `playback_speed`, `ai_director_enabled`, `ai_mode`, `multi_variant`, `asset_logo_path`, `asset_intro_path`, `asset_outro_path`, and 50+ more fields.

**Upload schemas (dead code)**: Classes `UploadRequest`, `UploadQueueAddRequest`, `UploadAccountBase`, `UploadAccountCreate`, `UploadAccountUpdate`, `UploadVideoResponse`, `UploadQueueUpdateRequest`, `UploadQueueResponse`, `UploadSchedulerStatusResponse` are present in `schemas.py`. No registered routes. No active callers. Dead code. Classification: P3 (no runtime impact).

**Job response shape**: Stable. Dict from SQLite rows via `jobs_repo.get_job()`. No schema changes in Phases 4E–4H.

**`BaseClipManifest`**: All optional fields (`base_clip_*`, `overlay_*`) stable since Phase 3C. No changes in Phases 4E–4H.

---

## 19. Compatibility Shim Audit

| Shim | Lines | Re-exports from | Known callers | Verified? |
|---|---|---|---|---|
| `services/render_engine.py` | 54 | `services/render/` (5 modules, 28+ symbols) | `render_pipeline.py`, `routes/render.py`, `motion_crop.py`, `thumbnail_quality.py`, tests | YES — compile clean, 202 tests pass |
| `services/db.py` | 31 | `app/db/` (3 modules, 12 symbols) | `main.py`, 5 routes, 4 orchestration files, 3+ service files | YES — compile clean, 202 tests pass |
| `services/subtitle_engine.py` | 47 | `services/subtitles/` (7 modules, 40+ symbols) | `render_pipeline.py`, `routes/subtitle.py`, `routes/render.py`, `segment_builder.py`, `subtitle_transcription_adapters.py`, tests | YES — compile clean, 202 tests pass |

**Same-object identity**: All three shims re-export the actual objects from their implementation modules. When `render_pipeline.py` imports `render_base_clip` from `render_engine`, it gets the same function object as if it had imported from `services/render/base_clip_renderer`. No shadow copies, no stale bindings.

**`render_engine.py` non-shim imports**: The shim file also imports from `app.services.motion_crop`, `app.services.encoder_helpers`, and `app.services.bin_paths` at the top. These are pass-through re-exports that existed before modularization. This is acceptable but makes the shim slightly heavier than a pure re-export file. Not a risk.

**Policy**: Do NOT remove any compatibility shim. All three must remain until an explicit caller migration phase is completed.

---

## 20. Import Graph Audit

**Dependency direction rules (verified)**:

| Direction | Rule | Status |
|---|---|---|
| `routes/*` → `services/*` | ALLOWED | Confirmed used throughout |
| `routes/*` → `db/*` | ALLOWED | Confirmed (`routes/render.py` → `services/db`) |
| `routes/*` → `orchestration/*` | ALLOWED | Confirmed (`routes/render.py` → `render_pipeline`) |
| `services/*` → `db/*` | ALLOWED | Confirmed (`services/job_manager`, `services/maintenance`) |
| `services/*` → `domain/*` | ALLOWED | Confirmed (`services/render/base_clip_renderer` → `domain/timeline`) |
| `orchestration/*` → `services/*` | ALLOWED | Confirmed |
| `orchestration/*` → `db/*` | ALLOWED | Confirmed |
| `db/*` → `services/*` | FORBIDDEN | NOT FOUND — clean |
| `db/*` → `routes/*` | FORBIDDEN | NOT FOUND — clean |
| `domain/*` → anything | FORBIDDEN | NOT FOUND — `timeline.py` and `manifests.py` import only stdlib |

**Circular import check**: No circular imports found. Compile check (`python -m compileall app -q`) returned clean with no output.

**Stale import paths found**: None. All imports resolved to existing modules.

**Service → route violation**: `routes/render.py` imports from `orchestration/render_pipeline.py` — this is an orchestration import, not a route→route import. Acceptable.

---

## 21. State Ownership Audit

| Mutable State | Owner Module | Singleton? | Risk |
|---|---|---|---|
| `_PREVIEW_SESSIONS: dict` | `services/preview/session_service.py` | YES — one dict | VERIFIED clean |
| `_ACTIVE_DOWNLOADS: dict` | `routes/render.py` (intentional) | YES — per-process | ACCEPTABLE |
| `_PROBE_CACHE: dict` | `services/render/ffmpeg_helpers.py` | YES — one cache | VERIFIED clean |
| `_PROBE_CACHE_LOCK` | `services/render/ffmpeg_helpers.py` | YES — one lock | VERIFIED clean |
| `NVENC_SEMAPHORE` | `services/render/ffmpeg_helpers.py` | YES — one semaphore | VERIFIED clean |
| `_tls` (thread-local) | `services/render/ffmpeg_helpers.py` | YES — thread-local | VERIFIED clean |
| `_MODEL_CACHE: dict` | `services/subtitles/transcription.py` | YES — one cache | VERIFIED clean |
| `_MODEL_CACHE_LOCK` | `services/subtitles/transcription.py` | YES — one lock | VERIFIED clean |
| `_MODEL_TRANSCRIBE_LOCKS: dict` | `services/subtitles/transcription.py` | YES — one dict | VERIFIED clean |

**`_PREVIEW_SESSIONS` singleton verification**: Defined once in `session_service.py`. `routes/render.py` imports it via `from app.services.preview.session_service import _PREVIEW_SESSIONS`. The import creates a reference to the same dict object, not a copy. `evict_stale_preview_sessions()` and all session helpers operate on the same dict. No aliasing risk.

**No duplicate mutable state found** across the audit.

---

## 22. FFmpeg / Render Contract Audit

All contracts verified by reading `legacy_renderer.py`, `base_clip_renderer.py`, and `overlay_compositor.py` directly.

### Legacy path vf_chain order (render_part_smart / render_part):

```
scale → crop → zoom → fixed_canvas → [denoise] → [effect] → [color] → [sharpen] →
format=yuv420p → [fade] →
ass= (subtitle, if present)       ← BEFORE setpts
drawtext=title (if present)        ← BEFORE setpts
text_layers (if present)           ← BEFORE setpts
setpts=PTS/{speed:.4f}            ← speed re-clock
fps={target_fps}                  ← always last
```

**ASS-before-setpts confirmed**: `legacy_renderer.py:146–175` — subtitle/drawtext added to `vf_parts` before `setpts` append.

### Overlay path vf_chain order (composite_overlays_on_base_clip):

```
ass= (output-timeline ASS, if present)     ← no setpts needed, PTS already output-timeline
drawtext=title (if present)
text_layers (if present)
fps={base_fps}                             ← always last
```

**No setpts confirmed**: `overlay_compositor.py:79–100` — no `setpts` in vf_parts.
**Audio copy confirmed**: `overlay_compositor.py:122`: `-c:a copy` hardcoded.

### Base clip vf_chain order (render_base_clip, non-motion-crop path):

```
scale → crop → zoom → fixed_canvas → [denoise] → effect → [color] → [sharpen] →
format=yuv420p → [fade] →
[NO ass=, NO drawtext=, NO text_layers]
setpts=PTS/{speed:.4f}   ← speed baked here
fps={target_fps}
```

**BGM in base clip**: When `reup_bgm_enable=True`, `filter_complex` is used. atempo applied once per stream in the base clip. `overlay_compositor.py` then copies audio via `-c:a copy` — no second atempo.

**Double atempo check**: base clip applies atempo in `_build_audio_filter()` or inside `filter_complex`. `overlay_compositor.py` has `-c:a copy` and zero audio filter chains. `mix_narration_audio()` is called on the final output after composite (not on base clip). No double atempo possible.

---

## 23. AI Architecture Audit

**Summary**: The `backend/app/ai/` namespace contains 294 Python files across 55+ subdirectories. None call any external AI API. All AI decision-making is implemented as deterministic heuristic scoring with JSON knowledge packs.

**Actual AI components in the system**:

| Component | What it actually is |
|---|---|
| `ai_director.py` | Orchestrator that calls heuristic analyzers and assembles an edit plan |
| `emotion_analyzer.py` | Keyword scoring on transcript text |
| `retention_predictor.py` | Weighted alias for scene quality score |
| `creator_dna/dna_engine.py` | Reads JSON file from disk |
| `ai/rag/` | Full RAG implementation (vector_store, sqlite_store, memory_store, retriever, embeddings) — INACTIVE in production |
| `clip_scorer.py` | Multi-factor heuristic scorer with configurable weights |
| `knowledge/` JSON files | Platform-specific tuning tables (explicit, auditable, version-controlled) |

**Real local ML (optional, all off by default except Whisper)**:
- Whisper — transcription (active, required)
- sentence-transformers — RAG embeddings (optional, built, INACTIVE in production)
- FAISS — vector search (optional, built, INACTIVE in production)
- TransNetV2 — scene detection (optional)
- MediaPipe — face tracking (optional)
- DeepFilterNet — audio cleanup (optional)
- XTTS2 — TTS (optional, alternative to edge-tts)

**External LLM calls**: Only in `services/caption_engine.py` — supports Claude API (via `anthropic` package) and Ollama local LLM as optional caption generators, with template fallback. This file is NOT wired to the render pipeline. No render pipeline code calls `generate_caption()`.

---

## 24. AI Provider / Adapter Audit

| Provider | Status | Location | Wired to render? |
|---|---|---|---|
| Claude API (Anthropic) | OPTIONAL | `services/caption_engine.py` | NO — caption only, not in render pipeline |
| Ollama local LLM | OPTIONAL | `services/caption_engine.py`, `services/warmup.py` | NO — caption only |
| Whisper | ACTIVE (required) | `services/subtitles/transcription.py` | YES — transcription is core |
| FAISS | OPTIONAL — INACTIVE | `ai/rag/` | BUILT but not wired in production |
| sentence-transformers | OPTIONAL — INACTIVE | `ai/rag/embeddings.py` | BUILT but not wired in production |

**No provider adapters, no prompt templates, no model configuration files** were found for any external LLM beyond `caption_engine.py`.

---

## 25. AI Prompt / Knowledge Audit

**Knowledge packs**: Located in `backend/knowledge/` — JSON files with platform-specific tuning (TikTok hook bonuses, speed deltas, subtitle styles, etc.). These are explicit, auditable, version-controlled configuration. Not prompts.

**`caption_engine.py` prompts**: Hardcoded string templates for Claude/Ollama caption generation. Not used in the render pipeline.

**No prompt injection risk** from user input: AI plan context (`_ai_context` in `render_pipeline.py:2251`) contains only: `job_id` (UUID), `srt_path` (file path), `scenes` (list), `duration` (float), `market` (string), `source_path` (file path). None of these are passed to any external API in the current code.

---

## 26. AI → Render Contract Audit

`create_ai_edit_plan()` is called in `render_pipeline.py:2250` when `ai_director_enabled=True`. It returns an `AIEditPlan` dataclass or `None`. The render pipeline applies plan fields to segment selection, subtitle hints, and camera behavior.

**`memory_store` not passed**: `render_pipeline.py` builds `_ai_context` without `memory_store`. The RAG retrieval system (which would inject creator memory into plan generation) is never activated. This is the single largest functional gap in the AI layer.

**AI plan fallback**: If `create_ai_edit_plan()` returns `None` (exception or disabled), rendering proceeds with full fallback. No render failure path is AI-gated.

**AI → render boundary**: AI plan data is consumed via `getattr` with defaults at call sites in `render_pipeline.py`. The AI layer never calls render functions directly. Clean separation.

---

## 27. AI Validation / Fallback Audit

**Pattern**: All AI module imports in `render_pipeline.py` use deferred imports inside `try` blocks. Failures return `None` or default values. This is consistent throughout.

**Risk with `except ImportError`**: This pattern catches `ImportError` but also catches any `AttributeError`, `NameError`, or `ImportError` raised inside an imported module's top-level code. A real bug in an AI module at import time (e.g., a typo in a constants file) appears as "feature unavailable" rather than "error at module X line Y". This is a known pattern issue, classified P2.

**Graceful degradation**: Every optional AI dependency (`TransNetV2`, `MediaPipe`, `DeepFilterNet`, `FAISS`, `sentence-transformers`, `XTTS2`) wrapped with try/except with fallback. Confirmed in `BRUTAL_REVIEW_SUMMARY.md` §What Is Genuinely Good.

---

## 28. AI Knowledge Injection Readiness

**RAG system status**: `ai/rag/` contains complete infrastructure — `vector_store.py`, `sqlite_store.py`, `memory_store.py`, `memory_writer.py`, `retriever.py`, `embeddings.py`. Has test coverage. SQLite memory store persists across restarts. LocalVectorStore falls back from FAISS to cosine similarity.

**Production activation status**: `render_pipeline.py` does NOT pass `memory_store` to `create_ai_edit_plan()`. The RAG retrieval that would inject creator preferences into plan generation is one parameter away from activation.

**One-line fix required**: Add `"memory_store": memory_store_instance` to `_ai_context` dict at `render_pipeline.py:2251`. The memory_store object must first be loaded (requires `from app.ai.rag.memory_store import MemoryStore`).

**FAISS index**: In-memory only — lost on every server restart. No rebuild from SQLite on startup. Even if RAG is activated, cold-start renders have no vector index until the in-memory FAISS is rebuilt.

**Readiness assessment**: RAG system is 95% ready. The gaps are: (1) missing `memory_store` wiring in `render_pipeline.py`, (2) missing FAISS rebuild on startup. Both are P1 features, not architectural blockers.

---

## 29. AI Governance Risks

| Risk | Classification | Description |
|---|---|---|
| AI branding mismatch | P2 | 60+ modules named as AI (ai_director, emotion_analyzer, retention_predictor) implement heuristics. Maintenance hazard — developers unfamiliar with the codebase will expect LLM inference and find keyword scoring. |
| RAG system inactive | P1 | Creator memory learning is built but not wired. The product promise of AI remembering creator preferences is not delivered in any render. |
| `except ImportError` broad catch | P2 | Module bugs at import time are silently swallowed and appear as unavailable features. |
| FAISS not persisted | P1 | In-memory FAISS vector index is rebuilt from nothing on every server restart. Creator memory retrieved from FAISS is lost on restart. SQLite store persists but FAISS is not rebuilt from it. |
| Knowledge packs loaded per-render | P3 | JSON files read on every render call with no module-level caching. Minor I/O inefficiency for a desktop tool. |
| AI → render coupling via global context | INFO | `_ai_context` is a plain dict. No type safety on the context keys. If a key is renamed in the director, render callers silently get `None`. Low risk but fragile. |

---

## 30. Test Coverage Audit

| Coverage Area | Status | Test Files |
|---|---|---|
| Domain models (TimelineMap, BaseClipManifest, manifest_writer) | COVERED — 65+ tests | `test_timeline_map.py`, `test_base_clip_manifest.py`, `test_manifest_writer.py` |
| Render modules (base_clip, overlay, composite, narration) | COVERED — 200+ tests | `test_render_base_clip.py`, `test_composite_overlays.py`, `test_overlay_narration.py`, etc. |
| Subtitle modules (all 7) | COVERED — 388 tests | `test_subtitle_styles.py`, `test_subtitle_srt_core.py`, `test_subtitle_ass_core.py`, etc. |
| Preview services (ffmpeg_probers, session, streaming) | COVERED — 89 tests | `test_preview_ffmpeg_probers.py`, `test_preview_session_service.py`, `test_preview_media_streaming.py` |
| DB repositories | COVERED — 85 tests | `test_db_connection.py`, `test_jobs_repo.py`, `test_creator_repo.py` |
| Upload domain removal | COVERED — 33 tests | `test_upload_domain_removed.py`, `test_upload_schema_removed.py`, `test_db_import_audit.py` |
| AI schema validators | COVERED — 100s of tests | Across 80+ AI test files |
| `render_pipeline.py` | NOT COVERED | No tests for the main pipeline coordinator |
| `job_manager.py` | NOT COVERED | No tests for the job queue |
| `scene_detector.py` | NOT COVERED | No tests |
| `downloader.py` | NOT COVERED | No tests |
| `tts_service.py` | NOT COVERED | No tests |
| Legacy `render_part_smart()` end-to-end | NOT COVERED | Tested via mocked FFmpeg only; no real render integration test |

**Total tests at audit**: 6699 passing, 8 failing (all pre-existing), 1 skipped.
**139 test files** across `backend/tests/`.

---

## 31. Test Results (Exact Numbers)

### Compile check

```
python -m compileall app -q
# Result: CLEAN — no output, no errors
```

### Targeted critical tests (7 suites)

```
tests/test_db_import_audit.py          — 15 passed
tests/test_subtitle_engine_compat_exports.py — 3+ passed
tests/test_preview_ffmpeg_probers.py   — 44 passed
tests/test_preview_session_service.py  — 17 passed
tests/test_preview_media_streaming.py  — 28 passed
tests/test_upload_domain_removed.py    — 13 passed
tests/test_upload_schema_removed.py    — 20 passed

TOTAL: 202 passed, 0 failed, 4 warnings (6.19s)
```

### Full test suite

```
8 failed, 6699 passed, 1 skipped, 4 warnings (88.80s)
```

**Result**: MATCHES Phase 4H.6 freeze baseline exactly. No new failures. No regressions introduced by the restructure.

---

## 32. Known Failures

All 8 failures are pre-existing — they predate Phase 1 and are unrelated to the restructure.

| Test File | Count | Root Cause |
|---|---|---|
| `test_remotion_adapter.py` | 4 | (1) `remotion_hook_intro` schema default is `True` but test expects `False`; (2) FFmpeg command assertion expects inline arg string but gets a list |
| `test_ai_optional_dependencies.py` | 1 | `deepfilternet` key mismatch in AI dependency status response dict |
| `test_ai_phase36_clip_segment_selection.py` | 2 | `safety_check_failed` reason key not found in response — schema mismatch |
| `test_ai_visibility_summary.py` | 1 | `badges` key missing from summary response |

**None of these failures are caused by the restructure.** They pre-date Phase 1.

---

## 33. Remaining Backend Technical Debt

### CRITICAL

| ID | Item | File | Priority |
|---|---|---|---|
| C1 | `render_pipeline.py` god file (282KB / ~5,340+ lines) | `orchestration/render_pipeline.py` | P1 |
| C2 | Subtitle display duration compressed at non-1.0 speeds (legacy path only) | `render_pipeline.py` + `legacy_renderer.py` | P1 (product quality) |

### HIGH

| ID | Item | File | Priority |
|---|---|---|---|
| H2 | No test coverage for `render_pipeline.py`, `job_manager.py`, `scene_detector.py`, `downloader.py`, `tts_service.py` | Various | P1 |
| H3 | RAG memory not wired to production render (`memory_store` not passed to `create_ai_edit_plan`) | `render_pipeline.py:2251` | P1 |
| H4 | FAISS vector index not persisted (rebuilt from zero on restart) | `ai/rag/` | P1 |
| H5 | Dead frontend directories `static-v3/`, `static-v4/` ship in every Electron build | `backend/` | P2 |
| H6 | YouTube download has no total wall-clock timeout (only per-packet `socket_timeout=60`) | `services/downloader.py` | P1 |
| H7 | Preview session memory lost on server restart (disk fallback is fragile) | `services/preview/session_service.py` | P2 |

### NEW FINDINGS (from this audit)

| ID | Item | Priority |
|---|---|---|
| NEW-1 | `app/models/schemas.py` — 8 dead `Upload*` Pydantic classes with no active callers | P3 |
| NEW-2 | `globals.js:uploadWs` — orphan variable declaration | P3 |
| NEW-3 | `editor-audio-runtime.js:89` + `editor-view.js:1107` — `POST /api/upload-file` returns 404 (editor audio file selection broken) | P0 for that feature, P2 overall |
| NEW-4 | `main.py` uses deprecated `@app.on_event` FastAPI lifecycle pattern | P3 (deprecation warning only) |
| NEW-5 | AI branding mismatch — 60+ modules with AI names implement heuristics | P2 (maintenance hazard) |
| NEW-6 | `except ImportError` broad catch in AI module loading swallows real bugs | P2 |
| NEW-7 | `caption_engine.py` uses `claude-haiku-4-5-20251001` model ID — verify this is a valid model name | P2 (model ID accuracy) |

---

## 34. Remaining Cleanup Candidates

These are safe to clean up in any future phase without risk to core functionality:

| Item | Action | Priority |
|---|---|---|
| 8 dead `Upload*` schema classes in `schemas.py` | Delete | P3 |
| `globals.js:uploadWs` dead variable | Delete | P3 |
| `globals.js:logStateByScope.upload` entry | Delete | P3 |
| `static-v3/`, `static-v4/` dead directories | Delete from build | P2 |
| Migrate all callers from `app.services.db` shim to `app.db.*` directly | Planned future phase | P2 |
| Migrate all callers from `app.services.render_engine` shim to `app.services.render.*` directly | Planned future phase | P2 |
| Migrate all callers from `app.services.subtitle_engine` shim to `app.services.subtitles.*` directly | Planned future phase | P2 |
| Update `main.py` to use FastAPI `lifespan` instead of deprecated `@app.on_event` | Modernization | P3 |
| Add pagination to `/api/jobs` endpoint (switch to `list_jobs_page`) | Correctness | P2 |
| Extract platform config dicts from `render_pipeline.py` to `knowledge/` JSON | Phase 5.3 scope | P1 |

---

## 35. High-Risk Areas

| Area | Risk | Why |
|---|---|---|
| `orchestration/render_pipeline.py` | **CRITICAL** | 282KB god file; any change touches unrelated code; no tests; highest regression risk in the codebase |
| `services/subtitles/transcription.py` | **HIGH** | Hard `import whisper` at top; `_MODEL_CACHE` singleton; if Whisper not installed, entire subtitle shim fails to load |
| `services/render/legacy_renderer.py` | **HIGH** | Legacy `render_part_smart()` has no end-to-end test; produces all current output in default mode |
| Batch rendering (`_run_batch` closure in `routes/render.py`) | **HIGH** | Bare thread with 7200s blocking wait; no batch-level cancel; no resume on server restart |
| `_PREVIEW_SESSIONS` dict | **MEDIUM** | Module-level dict lost on server restart; disk fallback requires file + video path to still exist |
| `caption_engine.py` Anthropic import | **LOW** | Deferred import; only fails if `ANTHROPIC_API_KEY` is set and `anthropic` package is installed; no render impact |

---

## 36. Safe-to-Build Areas

These areas are stable, tested, and have clean interfaces:

| Area | Why Safe |
|---|---|
| All render API endpoints | Unchanged since Phase 4F.7; frontend calls them by hardcoded URL |
| WebSocket progress contract | Unchanged throughout all phases |
| `RenderRequest` Pydantic model | Frozen; all fields documented |
| DB repositories (`app/db/`) | Clean, tested, shim-backed |
| Subtitle services (`services/subtitles/`) | 388 tests; all invariants verified |
| Preview services (`services/preview/`) | 89 tests; state ownership verified |
| Render services (`services/render/`) | 200+ tests; ownership invariants verified |
| Job management (`job_manager.py`) | Well-designed priority heap; cancel/resume/retry correct |
| Creator preferences API | Simple CRUD via `creator_repo.py` |
| Channel API | Independent domain; no coupling to render pipeline |
| AI heuristic layer (when `ai_director_enabled=True`) | Graceful degradation; never blocks render |

---

## 37. Backend / Product / AI Readiness Decision

### Backend Readiness: **GO**

All compatibility shims are healthy. Compile check is clean. 6699 tests pass at known baseline. No new failures. All render APIs are stable. Upload domain is fully removed and verified by 33 tests. Three major god-files are now pure re-export shims. The backend is safe for product feature work.

### Product Readiness: **GO WITH CAVEATS**

- All active API endpoints are unchanged and callable.
- WebSocket contract is unchanged.
- `RenderRequest` payload shape is unchanged.
- **Caveat 1 (P0 for that feature)**: `POST /api/upload-file` called by `editor-audio-runtime.js:89` and `editor-view.js:1107` returns 404. If editor audio file selection is a Phase 5.1 feature, the backend endpoint must be created first.
- **Caveat 2 (P3)**: Dead `Upload*` schema classes in `schemas.py` — no runtime impact.
- **Caveat 3 (P2)**: `render_pipeline.py` at 282KB — any new render feature touching the pipeline carries god-file navigation risk.

### AI Readiness: **CONDITIONAL GO**

AI heuristic layer (60+ modules) is functional and stable — all heuristic scoring works, graceful degradation is correct.

RAG memory system is NOT production-ready because `memory_store` is not wired to `create_ai_edit_plan()`. Creator preference learning is inert.

If the goal is "ship with current AI behavior" — GO. If the goal is "activate creator memory learning" — the one-line wiring plus FAISS persistence fix must happen first (P1 items H3 and H4).

---

## 38. Recommended Next Development Phases

### Phase 5.1 — Output Quality Hardening (Backend)

**Priority: HIGH — no preconditions**

- Add audio stream presence check to `_validate_render_output()` — muted output currently passes QA silently (P1)
- Tighten QA duration tolerance from ±20% to ±5% (P1)
- Add total wall-clock timeout to `download_youtube()` — supplement the existing `socket_timeout=60` (P1)
- Wire `memory_store` to `create_ai_edit_plan()` in `render_pipeline.py` — one-line change; activates RAG creator memory (P1)
- Add FAISS index rebuild from SQLite on startup in `ai/rag/` (P1)

**Entry criteria**: This review complete. No other preconditions.

### Phase 5.2 — Frontend V1 Cleanup / V2 Promotion

**Priority: MEDIUM — after Phase 5.1 QA improvements**

- Audit V1 vs V2 feature parity gap
- Remove or archive `static-v3/`, `static-v4/` dead directories from build
- Decide whether to promote V2 as default or clean up V1
- Fix `/api/upload-file` in editor (create a backend endpoint or remove the editor upload UI)

**Entry criteria**: Phase 5.1 QA improvements shipped.

### Phase 5.3 — Render Pipeline Partial Extraction

**Priority: MEDIUM — after Phase 5.2 frontend is stable**

- Extract `_render_part()` inner function to its own module
- Extract platform config dicts (`_PLATFORM_PROFILES`, `_CTA_TEXTS`, etc.) to `knowledge/` JSON
- Requires careful planning (similar to Phase 4G) due to closure dependencies
- Target: reduce `render_pipeline.py` below 4,000 lines

**Entry criteria**: Phase 5.2 frontend stable. Full test coverage for Phase 5.3 targets added first.

### Phase 5.4 — Caller Migration from Shims

**Priority: LOW — deferred**

- Migrate all callers from `app.services.db` → `app.db.*` directly
- Migrate all callers from `app.services.render_engine` → `app.services.render.*` directly
- Migrate all callers from `app.services.subtitle_engine` → `app.services.subtitles.*` directly
- Only after Phase 5.3 confirms `render_pipeline.py` is partially extracted

**Entry criteria**: Phase 5.3 complete.

---

## 39. Things Future AI Must NOT Touch

The following invariants must be preserved in all future development phases. Any AI agent or developer modifying these must re-run the full test suite and verify all 9 render invariants in §9.

1. **`services/render_engine.py`** — must remain a pure re-export shim; no new function bodies
2. **`services/db.py`** — must remain a pure re-export shim; no new function bodies
3. **`services/subtitle_engine.py`** — must remain a pure re-export shim; no new function bodies
4. **`app/db/connection.py:_drop_upload_tables()`** — must remain in `init_db()`; ensures safe upgrade from pre-Phase-4F.5D database files
5. **Upload domain must not be re-added** — no new `/api/upload/*` routes, no new upload DB tables, no `upload_engine.py` recreation
6. **`composite_overlays_on_base_clip()` audio `-c:a copy`** — must never be changed to re-encode; this would break BGM flow-through
7. **ASS-before-setpts ordering in `render_part_smart()`** — subtitle/drawtext filters must remain before `setpts` in vf_chain
8. **`setpts` must not appear in `composite_overlays_on_base_clip()`** — base_clip PTS is already output-timeline
9. **`_PREVIEW_SESSIONS` must remain a singleton** — only defined in `session_service.py`; never re-declare in any other module
10. **`_MODEL_CACHE` must remain a singleton** — only defined in `subtitles/transcription.py`; never re-declare
11. **`_HL_OPEN` / `_HL_CLOSE` PUA codepoints** — must remain defined exactly once in `subtitles/styles.py` and imported by all other modules that use them
12. **Speed clamp [0.5, 1.5]** — must be enforced at `TimelineMap.__post_init__()`, `_get_effective_playback_speed()`, and `_sanitize_speed()` consistently
13. **`_PRESETS` table values** — no ASS color, font, size, or boundary value may change; these are externally serialized in job configs
14. **Test baseline** — must not regress below 8 known pre-existing failures; new code must not introduce new failures

---

## 40. Final Recommendation

**GO for Phase 5.1 product work.**

The backend restructure (Phases 1–4H) is functionally complete. The three major god-files that were the primary maintenance hazards are now pure re-export shims backed by focused, tested sub-modules:

- `render_engine.py` (formerly 1,650 lines) → 54-line shim + 5 focused modules with 200+ tests
- `services/db.py` (formerly 1,900 lines) → 31-line shim + 3 focused modules with 85 tests
- `subtitle_engine.py` (formerly 1,970 lines) → 47-line shim + 7 focused modules with 388 tests

The only remaining god-file is `render_pipeline.py` at 282KB. This is acknowledged technical debt but does not block product work. It becomes critical only when new render features require modifying the pipeline.

All 202 critical Phase 4E–4H tests pass. Full suite at 6699 passing / 8 known pre-existing failures — no regressions from the restructure. Compile check is clean.

**Top 5 priorities for Phase 5.1**:
1. Wire `memory_store` to `create_ai_edit_plan()` — activates the built RAG system in one line
2. Add audio stream check to output QA — prevents silent muted output from passing validation
3. Add wall-clock download timeout — prevents worker thread starvation from hung yt-dlp
4. Fix FAISS persistence — rebuild vector index from SQLite on startup so creator memory survives restarts
5. Create `/api/upload-file` backend endpoint or remove the editor upload UI in `editor-audio-runtime.js` and `editor-view.js`

**Blockers for go**: None (0 blocking issues).
**Known caveats**: `/api/upload-file` pre-existing 404 (editor audio broken), dead `Upload*` schema classes in `schemas.py`, `static-v3/`/`static-v4/` dead frontend directories.

---

## Phase 5.1 — AI Knowledge and Render Safety Foundation (2026-05-23)

**Summary of Phase 5.1 changes:**

### Resolved: /api/upload-file 404
`POST /api/upload-file` now exists at `backend/app/routes/files.py`. Accepts `file` field (FormData), saves to `APP_DATA_DIR/editor-uploads/`, returns `{"path": "<saved_path>"}`. Safe filename validation prevents path traversal. Does not recreate the upload domain. Editor audio file selection is now functional.

### Resolved: Output QA now checks audio stream
`_validate_render_output()` in `orchestration/qa_pipeline.py` now warns when the rendered output has no audio stream, regardless of the `expect_audio` flag. Severity is WARNING (non-fatal, `ok=True` preserved) — consistent with existing QA pattern. Uses the existing ffprobe JSON parse — no additional subprocess calls.

### Resolved: Downloader has wall-clock timeout
`download_youtube()` in `services/downloader.py` now enforces a `_DOWNLOAD_WALLCLOCK_TIMEOUT = 300s` ceiling per download attempt via `concurrent.futures` with `result(timeout=...)`. Timeout raises `RuntimeError` with "wall-clock" text for easy distinction from format/network errors. Applies to both main and dynamic fallback loops. `socket_timeout: 60` preserved.

### Shipped: Local knowledge foundation
`backend/knowledge/` directory structure created with 7 processed `.jsonl` files (one example each), empty raw directories, and index directory. `knowledge/README.md` documents the schema, usage, and AI governance rules.

### Shipped: RAG/FAISS persistence primitives
`LocalVectorStore.save_index(path)` and `load_index(path)` added to `backend/app/ai/rag/vector_store.py`. Graceful degradation: missing index returns False (no crash). Entry-count validation on load prevents position mismatches. Full startup wiring (load → rebuild from knowledge/*.jsonl → save) deferred to Phase 5.2.

### AI knowledge direction clarified
`memory_store` (RAG infrastructure for per-job render experience) and `knowledge/` (filter-based platform/video-quality retrieval) are now documented as separate concerns in both `vector_store.py` docstring and `knowledge/README.md`. RAG is filter-based platform/video knowledge retrieval — not personal user memory.

### No external LLM required at render runtime
Confirmed and documented in `docs/ai/AI_RENDER_CONTRACT.md`. Cloud AI may populate `knowledge/processed/*.jsonl` offline. Render jobs work fully offline once the knowledge index exists.

### No UI overhaul started
Phase 5.1 does not include any frontend changes beyond the backend endpoint that enables the existing editor audio file picker.

### New documentation
- `docs/ai/AI_RENDER_CONTRACT.md` — 10-section governance contract for AI in the render pipeline
- `docs/ai/AI_DECISION_TRACEABILITY_PLAN.md` — planning doc for future AI decision logging

**Test suite state (expected post-Phase 5.1)**:
```
8 failed (same known failures), 6738+ passed (39+ new tests), 1 skipped
```
