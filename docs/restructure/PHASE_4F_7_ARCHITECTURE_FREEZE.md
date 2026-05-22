# PHASE_4F_7_ARCHITECTURE_FREEZE.md

**Status**: COMPLETE — restructure architecture frozen as of Phase 4F.7  
**Date**: 2026-05-22  
**Branch**: `restructure/output-timeline-architecture`

---

## 1. Purpose

This document freezes the backend architecture state after Phase 4F completion, before any Phase 4G work begins. It serves as:

- The authoritative reference for what was modularized and what remains monolithic
- The compatibility shim policy for `services/render_engine.py` and `services/db.py`
- The entry gate for Phase 4G (subtitle_engine split)
- The definition of what must not change after this freeze

---

## 2. Current Branch

`restructure/output-timeline-architecture`

All restructure work since Phase 1 is committed on this branch. The branch is ahead of `main` and has not been merged.

---

## 3. Completed Restructure Scope

| Phase | Description | Status |
|---|---|---|
| Phase 0 | TTS atempo hotfix, yt-dlp cancel propagation | SHIPPED |
| Phase 1 | `TimelineMap` + `BaseClipManifest` + `manifest_writer` | SHIPPED |
| Phase 1.5 | Timeline semantics validation + contract docs | SHIPPED |
| Phase 2 | `slice_srt_to_output_timeline()` + output-timeline ASS | SHIPPED |
| Phase 3A | `composite_overlays_on_base_clip()` — overlay-only composite | SHIPPED |
| Phase 3B | Overlay path subtitle sync (output-timeline ASS) | SHIPPED |
| Phase 3C | BGM support on overlay path in `render_base_clip()` | SHIPPED |
| Phase 3C.5 | Test coverage freeze for overlay architecture | SHIPPED |
| Phase 4A | Backend modularization planning doc | SHIPPED |
| Phase 4B | `orchestration/asset_pipeline.py` + `orchestration/render_events.py` extracted | SHIPPED |
| Phase 4C | `orchestration/qa_pipeline.py` extracted | SHIPPED |
| Phase 4D | `orchestration/audio_pipeline.py` extracted | SHIPPED |
| Phase 4E.1 | `services/render/ffmpeg_helpers.py` extracted | SHIPPED |
| Phase 4E.2 | `services/render/clip_ops.py` extracted | SHIPPED |
| Phase 4E.3 | `services/render/base_clip_renderer.py` extracted | SHIPPED |
| Phase 4E.4 | `services/render/overlay_compositor.py` extracted | SHIPPED |
| Phase 4E.5 | `services/render/legacy_renderer.py` extracted — `render_engine.py` is now a shim | SHIPPED |
| Phase 4F.1 | `app/db/connection.py` extracted | SHIPPED |
| Phase 4F.2 | `app/db/jobs_repo.py` extracted | SHIPPED |
| Phase 4F.3 | `app/db/creator_repo.py` extracted | SHIPPED |
| Phase 4F.4 | `app/db/platform_repo.py` extracted (upload-domain, later deleted) | SHIPPED |
| Phase 4F.5 | Upload domain removal audit | SHIPPED |
| Phase 4F.5A | Upload router + upload frontend removed | SHIPPED |
| Phase 4F.5B | `upload_engine.py` deleted; `channels.py` decoupled | SHIPPED |
| Phase 4F.5C | `routes/upload.py` deleted; `platform_repo.py` deleted; upload DB functions removed from `services/db.py` | SHIPPED |
| Phase 4F.5D | Upload table DDL removed from `init_db()`; `_drop_upload_tables()` migration added | SHIPPED |
| Phase 4F.6 | Test baseline stabilized (edge-tts installed); DB import audit confirmed clean | SHIPPED |
| Phase 4F.7 | Architecture freeze + stale docs audit (this document) | SHIPPED |

---

## 4. Final Backend Module Tree

```
backend/app/
├── ai/                          ← 60+ AI heuristic modules (no changes in Phase 4F)
├── core/
│   └── config.py                ← DATABASE_PATH, STATIC_UI_VERSION, etc.
├── db/                          ← NEW (Phase 4F.1–4F.4) — live DB repositories
│   ├── __init__.py
│   ├── connection.py            ← get_conn, init_db, thread-local, _drop_upload_tables
│   ├── jobs_repo.py             ← upsert_job, update_job_progress, job parts CRUD
│   └── creator_repo.py         ← get_creator_prefs, upsert_creator_prefs
├── domain/                      ← Phase 1 domain models
│   ├── manifests.py             ← BaseClipManifest
│   └── timeline.py              ← TimelineMap
├── models/
│   └── schemas.py               ← Pydantic request/response models
├── orchestration/
│   ├── asset_pipeline.py        ← Phase 4B: hook intro, asset intro/outro, logo
│   ├── audio_pipeline.py        ← Phase 4D: narration cleanup orchestration
│   ├── qa_pipeline.py           ← Phase 4C: output QA/validation helpers
│   ├── render_events.py         ← Phase 4B: shared logging/event helpers
│   └── render_pipeline.py       ← coordinator (5,340 lines; Phase 4G target)
├── routes/
│   ├── channels.py
│   ├── creator.py
│   ├── devtools.py
│   ├── download.py
│   ├── jobs.py
│   ├── render.py
│   ├── subtitle.py
│   ├── viral.py
│   └── voice.py
│   # NOTE: routes/upload.py DELETED (Phase 4F.5C)
└── services/
    ├── render/                  ← NEW (Phase 4E.1–4E.5) — render logic modules
    │   ├── base_clip_renderer.py  (242 lines)
    │   ├── clip_ops.py            (401 lines)
    │   ├── ffmpeg_helpers.py      (474 lines)
    │   ├── legacy_renderer.py     (458 lines)
    │   └── overlay_compositor.py  (164 lines)
    ├── audio_mix_service.py
    ├── db.py                    ← SHIM (31 lines) — re-exports from app/db/*
    ├── render_engine.py         ← SHIM (53 lines) — re-exports from services/render/*
    ├── subtitle_engine.py       ← 1,970 lines (Phase 4G target)
    └── [other services unchanged]
    # NOTE: services/upload_engine.py DELETED (Phase 4F.5B)
```

---

## 5. Render Architecture Freeze

The render engine is fully modularized. `services/render_engine.py` is a pure re-export shim.

| Module | Owns | Lines |
|---|---|---|
| `services/render/ffmpeg_helpers.py` | FFmpeg infrastructure, filter builders, NVENC, codec | 474 |
| `services/render/clip_ops.py` | `cut_video`, silence detect, bad-frame detect, `apply_micro_pacing` | 401 |
| `services/render/base_clip_renderer.py` | `render_base_clip()` — speed, crop, color, audio, BGM | 242 |
| `services/render/overlay_compositor.py` | `composite_overlays_on_base_clip()` — subtitle, title, text overlays | 164 |
| `services/render/legacy_renderer.py` | `render_part()`, `render_part_smart()` — legacy all-in-one | 458 |
| `services/render_engine.py` | **Shim only** — all names re-exported from above | 53 |

Ownership invariants are documented in [RENDER_BOUNDARIES.md](../architecture/RENDER_BOUNDARIES.md).

---

## 6. Orchestration Architecture Freeze

| Module | Owns | Source phase |
|---|---|---|
| `orchestration/render_events.py` | `_emit_render_event`, `_job_log`, progress timer, event helpers | Phase 4B |
| `orchestration/asset_pipeline.py` | `_maybe_prepend_*`, `_maybe_append_*`, `_maybe_apply_asset_logo` | Phase 4B |
| `orchestration/qa_pipeline.py` | `_validate_render_output`, duration/size QA helpers | Phase 4C |
| `orchestration/audio_pipeline.py` | `_maybe_cleanup_narration_audio` — DeepFilterNet orchestration | Phase 4D |
| `orchestration/render_pipeline.py` | Main coordinator — `run_render_pipeline`, inner `_render_part` | Not extracted — 5,340 lines |

`render_pipeline.py` remains the largest file (5,340 lines). It is the Phase 4G target for `subtitle_engine` decoupling. No portion of `run_render_pipeline` or `_render_part` was extracted in Phase 4F.

---

## 7. DB Architecture Freeze

| Module | Owns | Lines |
|---|---|---|
| `app/db/connection.py` | `get_conn`, `init_db`, thread-local, `_drop_upload_tables`, helpers | ~230 |
| `app/db/jobs_repo.py` | `upsert_job`, `update_job_progress`, parts CRUD | ~145 |
| `app/db/creator_repo.py` | `get_creator_prefs`, `upsert_creator_prefs` | ~25 |
| `app/services/db.py` | **Shim only** — all names re-exported from `app/db/*` | 31 |

Live tables: `jobs`, `job_parts`, `creator_prefs` (3 total).

`init_db()` calls `_drop_upload_tables(conn)` as its first action — idempotently drops all 7 upload tables from any existing database file created before the upload domain was removed. This migration is permanent.

---

## 8. Upload Domain Removal Status

**COMPLETE. All upload code is removed.**

| Layer | Status |
|---|---|
| Upload router (`routes/upload.py`, 1,501 lines, 42 endpoints) | DELETED Phase 4F.5C |
| Upload automation engine (`services/upload_engine.py`, 1,793 lines) | DELETED Phase 4F.5B |
| Upload proxy pool repo (`app/db/platform_repo.py`, 142 lines) | DELETED Phase 4F.5C |
| Upload DB functions (43 functions in `services/db.py`) | REMOVED Phase 4F.5C |
| Upload frontend JS (3 files: manager, config, engine; ~6,200 lines) | DELETED Phase 4F.5A |
| Upload `<script>` tags in `index.html` (3 tags) | REMOVED Phase 4F.5A |
| Upload table DDL (7 tables in `init_db()`) | REMOVED Phase 4F.5D |
| Upload constants (`UPLOAD_PROFILE_LOCK_TTL_MINUTES`, `UPLOAD_SCHEDULER_STATE_ID`) | REMOVED Phase 4F.5D |
| `init_db()` upload seed rows and `_ensure_columns` calls | REMOVED Phase 4F.5D |
| Upload router registration in `main.py` | REMOVED Phase 4F.5A |

**No `/api/upload` routes exist. The upload domain is dead code only in dev tooling strings.**

Residual non-upload references accepted:
- `app/db/connection.py` — `_UPLOAD_TABLES` tuple + `_drop_upload_tables()` — migration helper, correct
- `app/routes/channels.py` + `services/channel_service.py` — `upload_settings.json`, `upload/` dir path strings — filesystem channel management, not TikTok upload API
- `app/routes/render.py:808` — `upload_local_video` endpoint — local file upload to render pipeline, unrelated to TikTok upload domain
- `app/models/schemas.py` — `last_upload_at` — channel schema field, not upload domain
- `services/dev_commands.py` + `services/qa_runner.py` — string path literals to deleted files — dev tooling only, not Python imports, disabled by default

---

## 9. Compatibility Shim Policy

Two compatibility shims exist to preserve all existing import paths:

### `services/render_engine.py` (53 lines)

Re-exports everything from `services/render/`:
```python
from app.services.render.ffmpeg_helpers import (...)
from app.services.render.clip_ops import (...)
from app.services.render.base_clip_renderer import render_base_clip
from app.services.render.overlay_compositor import composite_overlays_on_base_clip
from app.services.render.legacy_renderer import render_part, render_part_smart
```

**Policy**: Do NOT remove this shim. Dozens of callers use `from app.services.render_engine import ...`. The shim must remain until all callers are explicitly migrated in a dedicated phase (post-Phase 4G).

### `services/db.py` (31 lines)

Re-exports everything from `app/db/*`:
```python
from app.db.connection import (get_conn, init_db, close_thread_conn, ...)
from app.db.jobs_repo import (upsert_job, get_job, list_jobs, ...)
from app.db.creator_repo import (get_creator_prefs, upsert_creator_prefs)
```

**Policy**: Do NOT remove this shim. All 14 app callers (`main.py`, 5 routes, 4 orchestration files, 3 service files) import via `app.services.db`. The shim must remain until all callers are explicitly migrated.

---

## 10. Active Public APIs Still Supported

All render API endpoints remain unchanged:

| Endpoint | Status |
|---|---|
| `POST /api/render/process` | Active |
| `POST /api/render/prepare-source` | Active |
| `POST /api/render/batch` | Active |
| `GET /api/render/stream/{job_id}/{part_no}` | Active |
| `GET /api/render/quick-process` | Active |
| `GET /api/jobs` | Active |
| `GET /api/jobs/{job_id}` | Active |
| `DELETE /api/jobs/{job_id}` | Active |
| `GET /api/jobs/ws/{job_id}` | Active |
| `GET /api/channels/*` | Active |
| `GET /api/creator/*` | Active |
| `GET /api/system/*` | Active |

---

## 11. Removed APIs / Features

| API / Feature | Removed in | Details |
|---|---|---|
| `POST /api/upload/*` (42 endpoints) | Phase 4F.5A/C | TikTok upload scheduler, queue, account management |
| Upload frontend (upload-manager.js, upload-config.js, upload-engine.js) | Phase 4F.5A/B | ~6,200 lines of Playwright TikTok automation UI |
| `app/db/platform_repo.py` | Phase 4F.5C | Proxy pool CRUD |
| `app/services/upload_engine.py` | Phase 4F.5B | 1,793-line Playwright TikTok automation |
| Upload DB tables (7) | Phase 4F.5D | upload_accounts, upload_queue, upload_videos, upload_history, upload_runtime_locks, upload_scheduler_state, upload_proxy_pool |

---

## 12. Current Test Baseline

```
8 failed, 6222 passed, 1 skipped
```

(With `edge-tts==7.2.8` installed in venv — the declared `requirements.txt` production dependency.)

Test files introduced in Phase 4F restructure: `test_db_connection.py` (33), `test_jobs_repo.py` (35), `test_creator_repo.py` (17), `test_platform_repo.py` (deleted in 4F.5C), `test_upload_entrypoints_removed.py` (9), `test_upload_engine_removed.py` (11), `test_upload_domain_removed.py` (13), `test_upload_schema_removed.py` (20), `test_db_import_audit.py` (15).

---

## 13. Known Failures (Pre-Existing)

All 8 failures are pre-existing before Phase 4F work began. None are regressions from the restructure. The exact failure identities are stable and unchanged since the start of Phase 4F.

---

## 14. Stale Reference Audit Results

Audit commands run:
```
rg "upload_|/api/upload|upload_engine|routes/upload|..." backend/app backend/tests docs
rg "render_engine.py|app.services.render_engine|..." backend/app backend/tests docs
rg "services/db.py|app.services.db|..." backend/app backend/tests docs
rg "Phase 4F.5|Phase 4F.6|Phase 4F.7|uploads_repo|platform_repo|db.py god" docs
rg "subtitle_engine.py|Phase 4G" docs
```

| Finding | Location | Class | Action |
|---|---|---|---|
| `_drop_upload_tables()` + `_UPLOAD_TABLES` in `connection.py` | `app/db/connection.py:132–142` | A — correct migration helper | None |
| `upload_settings.json` path strings | `routes/channels.py`, `channel_service.py` | B — filesystem channel paths, not upload API | None |
| `upload_local_video` endpoint | `routes/render.py:808` | A — local file render, not TikTok upload | None |
| `last_upload_at` fields | `models/schemas.py:446,500` | B — channel schema field | None |
| String refs to deleted files in dev_commands.py, qa_runner.py | Various lines | B — dev tooling string literals, not Python imports | None |
| `from app.services.render_engine import ...` (all callers) | `render_pipeline.py:34`, `routes/render.py`, etc. | D — active shim import, acceptable | None |
| `from app.services.db import ...` (all callers) | `main.py`, routes, etc. | D — active shim import, acceptable | None |
| `platform_repo.py (proxy pool CRUD); uploads_repo planned` in CURRENT_RENDER_ARCHITECTURE.md:26 | `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` | C — STALE, platform_repo deleted, uploads_repo cancelled | Fixed |
| H1 "1900-Line God Service" still named active in TECHNICAL_DEBT_REPORT.md | `docs/review/TECHNICAL_DEBT_REPORT.md:67` | C — STALE, db.py is 31-line shim | Fixed |
| L1 `enrich_upload_account_runtime_state()` N+1 debt | `docs/review/TECHNICAL_DEBT_REPORT.md:227` | C — STALE, function deleted with upload domain | Fixed |
| `upload.py` listed as active router in SCORECARD.md | `docs/review/SCORECARD.md:44` | C — STALE, router deleted | Fixed |
| TikTok upload credentials in SQLite claim in BRUTAL_REVIEW_SUMMARY.md | `docs/review/BRUTAL_REVIEW_SUMMARY.md:122` | C — STALE, upload domain removed | Fixed |
| `subtitle_engine.py` references in product docs | `docs/product/OQ_*.md` | B — product planning docs, acceptable historical | None |
| No `Phase 4G` references found in docs | (none) | — correct, 4G not started | None |

No classification-E findings (unexpected active upload code). Upload domain removal is complete.

---

## 15. Dependency Direction Rules

These rules apply to all future phases:

```
app/routes/*      → app/services/*        ← OK
app/routes/*      → app/db/*             ← OK (direct repo access)
app/routes/*      → app/orchestration/*  ← OK (render pipeline dispatch)
app/services/*    → app/db/*             ← OK
app/services/*    → app/domain/*         ← OK
app/orchestration/* → app/services/*    ← OK
app/orchestration/* → app/db/*          ← OK
app/db/*          → app/core/*           ← OK (config only)
app/db/*          → app/services/*       ← FORBIDDEN (circular)
app/db/*          → app/routes/*         ← FORBIDDEN (circular)
app/domain/*      → [anything]           ← FORBIDDEN (pure dataclasses)
```

Shim exception: `app/services/render_engine.py` and `app/services/db.py` may import from `app/db/*` and `app/services/render/*` respectively — this is the shim's purpose.

---

## 16. What Must Not Change After Freeze

1. **`services/render_engine.py`** must continue to re-export all render symbols unchanged.
2. **`services/db.py`** must continue to re-export all DB symbols unchanged.
3. **`app/db/connection.py:_drop_upload_tables()`** must remain in `init_db()` — ensures safe upgrade from pre-4F.5D database files.
4. **Upload domain must not be re-added** — no new `/api/upload/*` routes, no new upload DB tables, no `upload_engine.py` recreation.
5. **Render pipeline behavior must not change** — no FFmpeg filter changes, no timing contract changes, no feature flag behavior changes.
6. **Test baseline** must not regress below 8 known pre-existing failures. All Phase 4F-introduced tests must continue to pass.
7. **`app/db/`** must contain only: `connection.py`, `jobs_repo.py`, `creator_repo.py`. No new files until Phase 4G or later requires them.

---

## 17. What Remains for Phase 4G

Phase 4G is `subtitle_engine.py` extraction. Scope:

- `backend/app/services/subtitle_engine.py` — 1,970 lines — cohesive but large
- Responsibility clusters: Whisper transcription, SRT parsing/writing, ASS generation, style presets, text transform, market policy, `slice_srt_*` functions, output-timeline SRT conversion
- `render_pipeline.py` imports 15+ functions from `subtitle_engine.py` — these are the extraction boundary
- Phase 4G is NOT started. This section is planning context only.

Key risks for Phase 4G:
- `subtitle_engine.py` has no `__all__` — all exported names must be audited before extraction
- `render_pipeline.py` is a closure-heavy coordinator — subtitle function call sites share local variables
- Circular import risk: `subtitle_engine.py` currently imports from `render_engine.py` (`_has_audio_stream`) — this must be resolved before extraction

---

## 18. Phase 4G Entry Criteria

Phase 4G may begin when ALL of these are true:

- [x] Phase 4F.7 architecture freeze doc committed
- [x] Stale doc references corrected
- [x] `services/render_engine.py` shim policy documented and stable
- [x] `services/db.py` shim policy documented and stable
- [x] Upload domain removal verified by test suite (13+20+15 tests pass)
- [x] Test baseline confirmed: 8 known failures only, no regressions
- [x] Dependency direction rules documented
- [ ] Phase 4G plan doc created (`docs/restructure/PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md`)
- [ ] `subtitle_engine.py` responsibility clusters audited
- [ ] Circular import with `render_engine._has_audio_stream` resolved or documented
- [ ] Phase 4G test baseline snapshot taken

---

## 19. Phase 4H Preview: Route Cleanup Note

`routes/render.py` (1,368 lines) mixes preview session state, download orchestration, job creation, batch coordination, media streaming, and thumbnail serving. This is Phase 4H scope.

Phase 4H must NOT begin until:
- Phase 4G is complete and subtitle_engine extraction tests pass
- `render_pipeline.py` has been partially decoupled (its subtitle calls are Phase 4G outputs)

Do not start Phase 4H in the same session as Phase 4G.

---

## 20. Definition of Done

Phase 4F.7 is complete when:

- [x] This document exists and is committed
- [x] `CURRENT_RENDER_ARCHITECTURE.md` no longer references `platform_repo.py` or `uploads_repo planned`
- [x] `TECHNICAL_DEBT_REPORT.md` H1 marked RESOLVED; L1 marked OBSOLETE
- [x] `SCORECARD.md` no longer lists `upload.py` as an active router
- [x] `BRUTAL_REVIEW_SUMMARY.md` no longer claims TikTok credentials in SQLite
- [x] No unexpected active upload code found in `backend/app/`
- [x] No code behavior, schema, or API changed
- [x] Targeted test suite passes (test_db_import_audit, test_upload_domain_removed, test_upload_schema_removed)
- [x] Commit hash recorded in MIGRATION_HISTORY.md
- [x] Pushed to remote
