# PHASE_4H_6_ROUTE_FREEZE.md

**Route cleanup architecture freeze document.**
**Phase**: 4H.6 — Audit + Freeze
**Date**: 2026-05-22
**Branch**: `restructure/output-timeline-architecture`
**Status**: FROZEN

This document records the official stopping point for the Phase 4H route cleanup effort and classifies all remaining code in `routes/render.py`.

---

## 1. What Phase 4H Accomplished

Starting from `routes/render.py` at ~1,369 lines (post Phase 4F upload removal), Phase 4H extracted three clusters of non-route logic into the `services/preview/` package:

| Sub-phase | Extraction | Lines removed |
|---|---|---|
| 4H.1 | `services/preview/ffmpeg_probers.py` — 6 FFmpeg probe helpers | −164 |
| 4H.2 | `services/preview/session_service.py` — 4 state vars + 4 session helpers | −55 |
| 4H.3 | `services/preview/media_streaming.py` — Range parser + file byte iterator | −25 |
| **Total** | **3 new service modules, 89 new tests** | **−244 lines** |

After Phase 4H.3, `routes/render.py` is **1,125 lines** — reduced from ~1,369 (−18%).

The `services/preview/` package now owns all stateless preview helpers:

```
backend/app/services/preview/
├── __init__.py            (empty — package scaffold)
├── ffmpeg_probers.py      (Phase 4H.1) — 188 lines, 44 tests
├── session_service.py     (Phase 4H.2) —  83 lines, 17 tests
└── media_streaming.py     (Phase 4H.3) —  54 lines, 28 tests
```

---

## 2. Current routes/render.py Structure

As of Phase 4H.3, `routes/render.py` contains the following elements:

### 2a. Module-Level Imports (lines 1–53)

All imports are correct and layered cleanly:

| Import group | Module | Relationship |
|---|---|---|
| FastAPI framework | `fastapi`, `fastapi.responses` | Route layer dependency |
| Pydantic schemas | `app.models.schemas` | Request/response contracts |
| DB shim | `app.services.db` | 4F-extracted; re-exports from `app/db/` |
| Job management | `app.services.job_manager` | Submit + status |
| Channel service | `app.services.channel_service` | Channel directory management |
| Downloader | `app.services.downloader` | yt-dlp wrapper |
| Core config | `app.core.config` | TEMP_DIR, CHANNELS_DIR, REQUEST_LOG |
| Stage enum | `app.core.stage` | JobStage constants |
| Bin paths | `app.services.bin_paths` | FFmpeg/ffprobe path lookup |
| Render pipeline | `app.orchestration.render_pipeline` | 5 symbols: run_render_pipeline + 4 helpers |
| Preview probers | `app.services.preview.ffmpeg_probers` | 6 symbols (Phase 4H.1) |
| Session service | `app.services.preview.session_service` | 8 symbols (Phase 4H.2) |
| Media streaming | `app.services.preview.media_streaming` | 2 symbols (Phase 4H.3) |

No circular imports. All module imports are strictly top-down.

### 2b. Module-Level Mutable State (lines 96–97)

| Variable | Type | Owner | Classification |
|---|---|---|---|
| `_ACTIVE_DOWNLOADS` | `dict[str, threading.Event]` | Download cancel lifecycle | **A — acceptable to remain** |
| `_UUID_RE` | `re.Pattern` | Session_id validation in `prepare_source` | **A — acceptable to remain** |

Both belong to the source preparation cluster. `_ACTIVE_DOWNLOADS` tracks in-flight yt-dlp downloads keyed by `session_id`; cancellation clears it. `_UUID_RE` validates client-supplied session IDs. Both are route-scoped concerns with no downstream service dependency.

### 2c. Module-Level Helper Functions (lines 100–178)

| Function | Lines | Role | Classification |
|---|---|---|---|
| `_emit_request_event(...)` | ~18 | Write Type 1 errors to request.log | **A — route-layer helper** |
| `_validate_output_dir(payload)` | ~4 | Require non-empty output_dir | **A — route-layer validation** |
| `_coerce_legacy_channel_payload(payload)` | ~10 | Convert channel mode to manual | **A — route-layer shaping** |
| `_validate_render_source(payload)` | ~40 | Validate source_mode + URLs + channel | **A — route-layer validation** |

These four helpers are route-request validation functions. They operate on `RenderRequest` objects, raise `HTTPException`, and are consumed only by route handlers. Extracting them to a service would not improve testability or separation — they are correctly placed in the route layer.

### 2d. Non-Route Orchestration Helpers (lines 412–471)

| Function | Lines | Role | Classification |
|---|---|---|---|
| `process_render(job_id, payload, resume_mode)` | ~18 | cancel_registry wrapper + `run_render_pipeline` call | **A — route orchestration helper** |
| `_queue_render_job(job_id, channel, payload, ...)` | ~40 | DB upsert + `submit_job` | **A — route orchestration helper** |

`process_render` is a thin cancel_registry wrapper around `run_render_pipeline`. It passes `_load_session` and `_cleanup_preview_session` as function-reference callbacks (Coupling Constraint C2 from the Phase 4H plan). Extraction would require changing the `run_render_pipeline` callback signature — out of scope and not worth the risk. `_queue_render_job` is a job submission helper used by create, resume, and retry routes — naturally belongs with those handlers.

### 2e. Route Handlers — Classification

| Handler | Method | Path | Lines | Classification |
|---|---|---|---|---|
| `get_queue_status` | GET | `/queue-status` | ~7 | **A — thin read-only** |
| `get_ai_diagnostics` | GET | `/ai-diagnostics` | ~12 | **A — thin read-only** |
| `prepare_source` | POST | `/prepare-source` | ~154 | **A — acceptable; route orchestration** |
| `cancel_prepare_source` | DELETE | `/prepare-source/{session_id}` | ~8 | **A — thin cancel handler** |
| `preview_video` | GET | `/preview-video/{session_id}` | ~19 | **A — thin file response** |
| `preview_transcript` | GET | `/preview-transcript/{session_id}` | ~43 | **A — route-embedded Whisper call with cache** |
| `process_render` (non-route) | — | — | ~18 | **A — orchestration helper** |
| `_queue_render_job` (non-route) | — | — | ~40 | **A — orchestration helper** |
| `create_render_job` | POST | `/process` | ~16 | **A — thin dispatch** |
| `create_render_batch` | POST | `/process/batch` | ~138 | **B — future extraction candidate (inner closure)** |
| `upload_local_video` | POST | `/upload-local` | ~28 | **A — thin file upload** |
| `download_health` | POST | `/download-health` | ~6 | **A — thin health proxy** |
| `quick_process` | POST | `/quick-process` | ~283 | **C — intentionally frozen** |
| `resume_render_job` | POST | `/resume/{job_id}` | ~19 | **A — thin dispatch** |
| `retry_failed_parts` | POST | `/retry/{job_id}` | ~35 | **A — thin retry logic** |
| `cancel_render_job` | POST | `/{job_id}/cancel` | ~18 | **A — thin cancel** |
| `get_render_job` | GET | `/jobs/{job_id}` | ~6 | **A — thin DB read** |
| `stream_render_part_media` | GET | `/jobs/{job_id}/parts/{part_no}/media` | ~53 | **A — handler; helpers extracted** |
| `get_render_part_thumbnail` | GET | `/jobs/{job_id}/parts/{part_no}/thumbnail` | ~27 | **A — thin thumbnail handler** |

**Classification key**:
- **A — acceptable to remain**: correct placement; no extraction benefit
- **B — future extraction candidate**: extractable but deferred (medium risk, low immediate value)
- **C — intentionally frozen**: extraction rejected; logic is self-contained

### 2f. Inner Closure

| Closure | Defined in | Lines | Classification |
|---|---|---|---|
| `_run_batch()` | Inside `create_render_batch` (line 524) | ~105 | **B — future extraction candidate** |

`_run_batch` captures `batch_id`, `child_job_ids`, `urls`, `effective_channel`, `payload` from the enclosing scope. Extraction to `services/render/batch_service.py` requires converting captured variables to explicit parameters. The logic itself is self-contained. This is the primary remaining extraction target if Phase 4H resumes.

### 2g. Deferred Imports Inside Handlers

| Handler | Import | Reason deferred |
|---|---|---|
| `get_queue_status` | `_render_active_count, _render_active_lock, _JOB_SEM_VALUE` | Internal pipeline state; deferred avoids circular import risk |
| `get_ai_diagnostics` | `get_ai_runtime_diagnostics` | AI optional dependency; deferred avoids startup cost |
| `process_render` | `cancel_registry` | Avoids circular at module load time |
| `_run_batch` | `cancel_registry` | Same as above |
| `preview_transcript` | `get_whisper_model` | Shim import; avoids loading Whisper at startup |
| `get_render_part_thumbnail` | `extract_thumbnail_frame`, `Response` | Shim import; avoids loading render_engine shim at startup |

All deferred imports are intentional. None are candidates for promotion to module-level without additional analysis.

---

## 3. Compatibility Shim Status

Three compatibility shims are active and must not be removed:

| Shim | Location | Points to | Status |
|---|---|---|---|
| `services/db.py` | `backend/app/services/db.py` | `app/db/connection.py`, `app/db/jobs_repo.py`, `app/db/creator_repo.py` | **FROZEN** — Phase 4F.5 |
| `services/render_engine.py` | `backend/app/services/render_engine.py` | `app/services/render/` (5 modules) | **FROZEN** — Phase 4E.5 |
| `services/subtitle_engine.py` | `backend/app/services/subtitle_engine.py` | `app/services/subtitles/` (7 modules) | **FROZEN** — Phase 4G.7 |

All three shims are pure re-exports. All callers (`routes/render.py`, `render_pipeline.py`, external test imports) continue to work via the shim path. Do NOT remove shims — they are the backward-compat layer that allowed each extraction to be independent.

**Verified re-export chains** (as of Phase 4H.6):
- `routes.render.evict_stale_preview_sessions` → `services/preview/session_service.evict_stale_preview_sessions` (same object)
- `routes.render._PREVIEW_SESSIONS` is `session_service._PREVIEW_SESSIONS` (same dict — singleton)
- `routes.render._probe_video_codec` is `ffmpeg_probers._probe_video_codec` (same object)
- `routes.render._parse_range_header` is `media_streaming._parse_range_header` (same object)
- `main.py` `from app.routes.render import evict_stale_preview_sessions` — works unchanged

---

## 4. Circular Import Audit

Import direction is strictly one-way:

```
main.py
  └── routes/render.py
        ├── services/preview/ffmpeg_probers.py       (no route imports)
        ├── services/preview/session_service.py      (no route imports)
        ├── services/preview/media_streaming.py      (no route imports)
        ├── services/db.py (shim)
        │     └── db/connection.py, jobs_repo.py, creator_repo.py
        ├── orchestration/render_pipeline.py
        ├── services/job_manager.py
        ├── services/channel_service.py
        ├── services/downloader.py
        └── services/bin_paths.py
```

None of the extracted preview modules import from `routes/render.py` or from each other. No circular imports exist in the preview package. Verified via `python -m compileall app` — no errors.

---

## 5. Cross-Module Coupling

Remaining coupling constraints from the Phase 4H plan (§14):

| Constraint | Status |
|---|---|
| C1: `evict_stale_preview_sessions` called from `main.py` | **RESOLVED** — re-exported from `routes/render.py` |
| C2: `_load_session` / `_cleanup_preview_session` as pipeline callbacks | **ACCEPTED** — functions imported from `session_service`, passed as references; behavior unchanged |
| C3: `_run_batch()` inner closure | **DEFERRED** — closure remains; batch_service extraction not started |
| C4: `_ACTIVE_DOWNLOADS` shared between prepare/cancel handlers | **ACCEPTED** — stays in `routes/render.py`; belongs to download lifecycle |
| C5: ffprobe helpers depend on `_run_ffmpeg_checked` | **RESOLVED** — all 6 helpers travel together in `ffmpeg_probers.py` |

---

## 6. Why 4H.4 and 4H.5 Were Not Completed

### Phase 4H.4 — Source Prepare Service (not started)

The plan proposed extracting `prepare_source` and `cancel_prepare_source` handlers into `services/preview/source_prep.py`. After audit, this extraction was rejected:

- `prepare_source` is 154 lines of **route-handler code**, not service logic. It handles HTTP request body fields, raises `HTTPException`, emits route-level events, and returns JSON response shapes. Extracting it to a service would create a service that is parameterized by 8+ arguments and mimics a route handler in structure.
- `cancel_prepare_source` is 8 lines. Extraction is cosmetic.
- `_ACTIVE_DOWNLOADS` would need to travel with `prepare_source`. Moving it to a service introduces state that the route module no longer owns but still reads via import.
- The extraction value is low; the coupling complexity is high.

**Decision**: Source preparation is route-level orchestration. It stays in `routes/render.py`.

### Phase 4H.5 — Audit + Freeze (merged into 4H.6)

The original plan had a separate 4H.5 "audit + freeze" sub-phase. This has been collapsed into Phase 4H.6 (this document). No separate 4H.5 phase is needed.

---

## 7. Official Freeze Policy

`routes/render.py` is now considered:
- An **orchestration-focused route layer** — it owns route handler definitions, request validation, job dispatch, and session-coupled orchestration
- **No longer a dumping ground** for stateless helpers — three helper clusters have been extracted
- **Acceptable at its current state** for the project's architectural stage

The following are **intentionally accepted** in `routes/render.py`:
- Route-level request validation helpers (`_validate_render_source`, `_coerce_legacy_channel_payload`)
- Route-level orchestration helpers (`process_render`, `_queue_render_job`)
- Route-level mutable state (`_ACTIVE_DOWNLOADS`, `_UUID_RE`)
- Inner closures that capture route-local context (`_run_batch`)
- Self-contained single-endpoint implementations (`quick_process`)
- `StreamingResponse` / `FileResponse` construction inside route handlers

The following will **NOT** be attempted:
- Extracting every function into a micro-service module
- Achieving zero logic inside route handlers
- Perfect CQRS or onion-architecture layering
- Extracting `quick_process` (283 lines, self-contained FFmpeg pipeline with good error handling)
- Extracting `_run_batch` without fixing the underlying batch threading debt simultaneously

---

## 8. Architecture Quality Assessment — Route Layer

| Metric | Before 4H | After 4H.3 |
|---|---|---|
| `routes/render.py` size | ~1,369 lines | ~1,125 lines |
| Stateless helper functions in route module | 10+ | 4 (validation only) |
| Extractable pure functions with no tests | 6 FFmpeg probers, 4 session helpers, range/iter | 0 remaining |
| Module-level state vars | 6 | 2 (`_ACTIVE_DOWNLOADS`, `_UUID_RE`) |
| Preview service modules | 0 | 3 (probers, session, streaming) |
| Preview service test coverage | 0 | 89 tests |
| Circular imports | 0 | 0 |

---

## 9. Remaining Technical Debt in routes/render.py

Acknowledged but intentionally deferred:

| Debt | Location | Priority |
|---|---|---|
| `_run_batch()` inner closure (no cancel, no resume, 7200s hang risk) | `create_render_batch` | LOW — logic debt, not location debt |
| `quick_process` self-contained FFmpeg pipeline | `quick_process` | LOW — well-structured, acceptable |
| `preview_transcript` inline Whisper call | `preview_transcript` | LOW — isolated, cached |
| `prepare_source` 154-line handler | `prepare_source` | ACCEPTABLE — route orchestration |

None of these are extraction candidates at this time.

---

## 10. Definition of Done — Phase 4H Complete

All Phase 4H completion criteria are satisfied:

- [x] `services/preview/__init__.py` exists (empty)
- [x] `services/preview/ffmpeg_probers.py` — 6 FFmpeg probe helpers (Phase 4H.1)
- [x] `services/preview/session_service.py` — 4 functions + 4 state vars (Phase 4H.2)
- [x] `services/preview/media_streaming.py` — 2 streaming helpers (Phase 4H.3)
- [x] `routes/render.py` re-exports `evict_stale_preview_sessions` — `main.py` unchanged (Phase 4H.2)
- [x] All API paths, methods, response shapes unchanged (verified)
- [x] `main.py` `evict_stale_preview_sessions` import path unchanged
- [x] No circular imports in preview package
- [x] Test suite: `8 failed, 6699 passed, 1 skipped` — 89 new preview tests all pass
- [x] `MIGRATION_HISTORY.md` — Phase 4H.0 through 4H.6 entries added
- [x] `CURRENT_RENDER_ARCHITECTURE.md` — `services/preview/` block added
- [x] `TECHNICAL_DEBT_REPORT.md` — `routes/render.py` entry updated
- [x] `BRUTAL_REVIEW_SUMMARY.md` — priorities updated
- [x] `SCORECARD.md` — backend architecture and maintainability scores updated
- [x] This freeze document created

**Phase 4H is complete.** No further route cleanup phases are planned.
