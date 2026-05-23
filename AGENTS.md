# AGENTS.md

## Required Reading Order (MANDATORY)

Before making any architecture, render, UI, AI, subtitle,
voice, motion crop, desktop, packaging, API,
or pipeline-related changes:

You MUST follow this order:

READ
→ UNDERSTAND
→ PLAN
→ PATCH
→ VERIFY

Do not start implementation immediately.

### Step 1 — Read Context First

Read the relevant documentation before touching code.

Always read:

1. `docs/PROJECT_FLOW_VI.md`
2. `docs/ARCHITECTURE.md`
3. `docs/RENDER_PIPELINE.md`
4. `docs/UI_BEHAVIOR.md`

Then read domain-specific docs depending on task:

Subtitle work:
- `docs/SUBTITLE_TRANSLATION.md`

Voice / narration / TTS:
- `docs/VOICE_NARRATION.md`

Download / source preparation:
- `docs/DOWNLOAD_SYSTEM.md`

Desktop / Electron / packaging:
- `docs/DESKTOP_APP.md`

### Step 2 — Understand The Project

Before patching, explain:

- what the system currently does
- where the relevant flow exists
- what files are responsible
- what compatibility contracts exist
- what must not break
- risks of the change

Do not guess architecture.

Treat this project as:

"An AI rendering intelligence platform with FFmpeg as execution backend"

NOT:

"An FFmpeg render tool with AI features"

### Step 3 — Plan First

Before editing files:

Provide:

1. Summary of understanding
2. Proposed approach
3. Files to touch
4. Risks
5. Test strategy
6. Rollback concerns

Do not patch before plan approval when scope is medium/high risk.

### Step 4 — Patch Conservatively

Rules:
- minimal patch only
- preserve backward compatibility
- preserve DOM IDs
- preserve result_json contracts
- preserve render events
- preserve job statuses
- preserve bounded AI execution
- preserve fallback behavior

Never casually refactor:
- `render_pipeline.py`
- `render_engine.py`
- `subtitle_engine.py`
- `motion_crop.py`
- `schemas.py`
- giant frontend JS files
- render/UI contracts

### Step 5 — Verify

Always:

- `py_compile` changed Python files
- run focused pytest
- recommend full pytest if needed
- explain compatibility impact

Protected folders:
- NEVER edit `docs/review/**`
- NEVER edit `docs/archive/**`
unless explicitly requested.

If docs and code disagree:
trust implementation first.

Strict operating instructions for AI agents working in this repository.

This project is a local video rendering tool. Treat it as production software: changes must be minimal, reviewable, backward compatible, and tested against the affected path.

## Project Overview

- Backend: FastAPI app in `backend/app`. `backend/app/main.py` creates the app, mounts `/static`, registers routers, initializes SQLite, recovers interrupted jobs, and starts warmup checks.
- API routes: `backend/app/routes/` contains render, jobs, download, upload, voice, viral, subtitle, channels, and devtools endpoints. Render starts through `/api/render/process` and `/api/render/process/batch`; job status is exposed through `/api/jobs`, `/api/jobs/{job_id}`, `/api/jobs/{job_id}/parts`, `/api/jobs/{job_id}/logs`, `/api/jobs/{job_id}/parts/{part_no}/stream`, and `/api/jobs/{job_id}/ws`.
- Models/contracts: `backend/app/models/schemas.py` defines request payloads, especially `RenderRequest`. Most AI and render flags default to disabled for backward compatibility.
- Job persistence: `backend/app/services/db.py` owns SQLite schema for `jobs`, `job_parts`, upload queue/history, and related tables. `payload_json` and `result_json` are UI-facing contracts.
- Queue system: `backend/app/services/job_manager.py` runs a local priority queue backed by a thread pool. It does not use Celery. Startup marks queued/running jobs as `interrupted` for manual resume.
- Render pipeline: `backend/app/orchestration/render_pipeline.py` is the main orchestration entry point. It prepares source media, detects scenes, builds/scans segments, transcribes once, renders parts through FFmpeg, validates outputs, writes report rows, updates job/part progress, emits structured events, and writes result JSON.
- FFmpeg layer: `backend/app/services/render_engine.py` builds FFmpeg commands, resolves codecs/NVENC fallback, probes media metadata, applies crop/effects/text overlays/audio filters, and guards concurrent NVENC sessions.
- Subtitle pipeline: `backend/app/services/subtitle_engine.py` handles Whisper model loading/cache, SRT parsing/writing/slicing, market line breaks/hook text, and ASS karaoke/bounce generation.
- Voice/TTS pipeline: `backend/app/services/tts_service.py` generates Edge TTS narration; `backend/app/services/audio_mix_service.py` mixes narration back into rendered parts.
- Static frontend: `backend/static/index.html` is the main shell. CSS entry point is `backend/static/css/v3/app.css` (imports the v3 modular CSS system: tokens → layout → components → workflow → runtime → review → download → history → hardening → editor-engine). JS modules under `backend/static/js/` manage source setup, editor flow, render payloads, WebSocket/polling progress, output cards, history, download/upload UI, and navigation. Partials live in `backend/static/partials/`.
- AI Director and AI phases: `backend/app/ai/**` contains deterministic/local AI planning and advisory modules. Core Director files are under `backend/app/ai/director/`; many phase modules are tested one phase at a time in `backend/tests/test_ai_phase*.py`. AI features must remain opt-in unless explicitly requested.
- Knowledge data: `backend/knowledge/**` stores local JSON knowledge packs for platforms, subtitles, hooks, camera, pacing, creators, and patterns.
- Tests: primary tests are in `backend/tests/`. Root `tests/` currently contains no active test files. Tests focus on render guards, queue status, subtitle guards, probe unification, encoder helpers, audit fixes, and AI phase contracts.
- Docs/audit: `docs/` and `backend/docs/` contain architecture and behavior documents. `docs/review/render_audit.md` and `backend/docs/review/render_audit.md` are audit ledgers for render/AI behavior and must be updated when behavior or phase contracts change.

## Critical Safety Rules

- Do not rewrite large files unless the user explicitly asks for a rewrite. Prefer small, surgical patches.
- Prefer minimal diffs that preserve existing naming, structure, defaults, and call paths.
- Preserve backend API contracts: request fields, response keys, status codes, route paths, and accepted legacy payloads.
- Preserve WebSocket-first progress and HTTP polling fallback behavior in `backend/static/js/render-engine.js` and `/api/jobs/{job_id}/ws`.
- Preserve render job events, stage names, part statuses, and result JSON compatibility. Existing UI and tests consume `jobs.stage`, `jobs.status`, `job_parts.status`, `result_json.output_ranking`, `ai_edit_plan`, `ai_ux_metadata`, output aliases, and partial-success status.
- Preserve frontend DOM IDs, function names called by inline `onclick`, existing button/action behavior, and hidden compatibility fields in `backend/static/index.html`.
- Do not break the FFmpeg pipeline, subtitle pipeline, voice/TTS pipeline, queue system, output validation, report generation, or media streaming endpoints.
- Do not remove backward-compatible aliases without focused tests and audit notes. Examples include output ranking aliases like `output_rank_score` and `is_best_output`.
- Keep AI phases opt-in unless the existing phase explicitly says otherwise. Advisory/planning phases must not start cutting, rendering, reordering segments, mutating FFmpeg commands, or changing payloads unless that phase and tests already allow it.
- Do not add cloud/network AI dependencies to the main runtime path. Optional AI dependencies belong in `backend/requirements-ai.txt` and must not be required for default startup.
- Never bypass output validation to make a render appear successful. Failed or partial renders must stay visible in job/part state and logs.
- Be careful with Windows paths and FFmpeg filter escaping. Use existing helpers such as `safe_filter_path`, `get_ffmpeg_bin`, and `get_ffprobe_bin`.
- Do not change concurrency defaults casually. `MAX_CONCURRENT_JOBS`, `MAX_RENDER_JOBS`, and `NVENC_MAX_SESSIONS` protect local machines from overload and encoder failures.

## Protected Files / High-Risk Areas

- `backend/app/orchestration/render_pipeline.py`: Main render state machine. Do not break stage transitions, per-part updates, `_emit_render_event`, resume behavior, result JSON shape, source cleanup, validation, partial success handling, report writing, or AI metadata pass-through.
- `backend/app/services/render_engine.py`: FFmpeg command builder and media probing layer. Do not break codec fallback, NVENC semaphore use, probe cache behavior, audio/video filters, motion-aware crop integration, text overlays, path escaping, or retry/error diagnostics.
- `backend/app/services/subtitle_engine.py`: Whisper/SRT/ASS path. Do not break timestamp parsing, SRT block round-tripping, playback-speed timing, market subtitle formatting, karaoke/bounce ASS output, or Whisper cache behavior.
- `backend/app/models/schemas.py`: API schema contract. Do not rename/remove fields or change defaults without compatibility handling. New render flags should usually default to disabled or preserve old behavior.
- `backend/app/ai/**`: Phase-based AI architecture. Do not introduce hard dependency on optional packages in import-time paths. Keep safety gates and "planning/advisory only" boundaries intact. Update focused phase tests and audit docs for behavior changes.
- `backend/app/ai/director/ai_director.py`: AI Director orchestration. It must never crash the render pipeline; failures should fall back safely and return `None` or advisory warnings.
- `backend/app/ai/director/edit_plan_schema.py`: AI result contract. Add fields with default factories and maintain `to_dict()` compatibility.
- `backend/app/services/job_manager.py`: Queue semantics. Do not break priority ordering, duplicate-job prevention, startup interruption marking, or thread-safe condition/lock behavior.
- `backend/app/services/db.py`: SQLite schema and job/result persistence. Avoid destructive migrations. Preserve `jobs` and `job_parts` columns consumed by routes and frontend.
- `backend/app/routes/render.py`: Render API boundary. Preserve validation, legacy channel payload coercion, prepare-source sessions, resume/retry endpoints, and media preview routes.
- `backend/app/routes/jobs.py`: Job history/progress boundary. Preserve normalized history shape, stale/stuck detection, log lookup, part streaming, WebSocket payload shape, and polling fallback data.
- `backend/static/index.html`: DOM contract for the static app. Do not remove IDs, hidden fields, modal/editor elements, or inline handler targets unless all JS call sites are updated and tested.
- `backend/static/css/v3/` (modular CSS system): Shared UI styling. The v3 entry point is `v3/app.css`. Avoid broad layout rewrites. Check render/editor/output/history views after changes. (`backend/static/css/app.css` is a legacy rollback file — not loaded in production; do not rely on it for active styling.)
- `backend/static/js/render-ui.js`: Render monitor, output cards, history, AI panels, progress UI. Preserve global functions, localStorage history compatibility, output ranking display, clip preview/download actions, and terminal state behavior.
- `backend/static/js/render-engine.js`: Payload construction, prepare-source, process/resume calls, WebSocket/polling loop. Preserve `/api/render/*` and `/api/jobs/*` interaction and graceful fallback when WebSocket fails.
- `backend/static/js/nav.js`: View switching and render/editor visibility. Do not break `setView`, nav item state, bottom panel state, or render-home/history refresh behavior.
- `docs/review/render_audit.md` and `backend/docs/review/render_audit.md`: Audit ledgers. Update when render behavior, AI phase behavior, compatibility boundaries, or safety guarantees change.

## Development Workflow

1. Inspect before editing. Read the relevant route, service, schema, frontend call site, tests, and docs/audit entries before patching.
2. Summarize the plan before patching. State the files to change and the compatibility risks being guarded.
3. Make minimal changes. Keep patches narrow and preserve existing patterns.
4. Add focused tests when behavior changes. Prefer the nearest existing test file in `backend/tests/`; add a new focused test only when no suitable file exists.
5. Run syntax checks on changed Python files.
6. Run focused pytest for the affected path.
7. Recommend full pytest when the change touches shared render pipeline, schemas, job queue, DB, AI Director contracts, or frontend/API contracts. Run it when feasible.
8. Update audit docs when behavior/spec changes, especially for render pipeline and AI phase changes.
9. For frontend changes, manually verify the affected static flow in a browser when possible: source setup, editor start, render queue/progress, output cards, history, and navigation.
10. Keep generated/runtime outputs out of commits unless explicitly requested. Do not edit `data/`, `channels/`, `tmp_verify_output/`, `.pytest_cache/`, build artifacts, or local virtualenv files unless the task is specifically about them.

## Commands

Use Windows PowerShell from this repository.

```powershell
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
```

Install/update backend dependencies only when needed:

```powershell
python -m pip install -r requirements.txt
```

Optional local AI dependencies are not part of the default runtime:

```powershell
python -m pip install -r requirements-ai.txt
```

Run the backend dev server:

```powershell
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Syntax-check changed Python files:

```powershell
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
python -m py_compile app\orchestration\render_pipeline.py
python -m py_compile app\services\render_engine.py
python -m py_compile app\models\schemas.py
```

Run focused tests:

```powershell
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests\test_render_pipeline_guards.py
python -m pytest tests\test_render_guards.py
python -m pytest tests\test_subtitle_guards.py
python -m pytest tests\test_queue_status_endpoint.py
```

Run AI phase tests only for the affected phase/module:

```powershell
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests\test_ai_phase10_render_influence.py
python -m pytest tests\test_ai_phase47_orchestrator.py
```

Run all backend tests before broad/shared changes are considered complete:

```powershell
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1
python -m pytest
```

Check FFmpeg availability:

```powershell
ffmpeg -version
ffprobe -version
```

## Review Checklist

- API payload and response compatibility preserved.
- `RenderRequest` defaults preserve old behavior.
- Job status/stage/part status transitions still make sense.
- WebSocket progress and polling fallback still work.
- `result_json` remains parseable by history/output/AI UI code.
- Output validation still catches missing, tiny, streamless, or zero-duration videos.
- Subtitle and voice paths still no-op safely when disabled.
- Queue concurrency and resume/retry semantics are unchanged unless intentionally tested.
- AI changes are bounded by phase safety rules and do not add import-time optional dependency failures.
- Audit docs updated for any behavior/spec change.

## Frontend System Note

The Project Overview section above describes the **legacy** frontend at `backend/static/`.
That description and those protected files remain accurate — the legacy app is still the
default served UI when `STATIC_UI_VERSION` is not set.

Three frontend states now coexist in this repository:

**Legacy** (`backend/static/`) — served by default (no env var).
Protected files in this document cover this state.

**v2** (`backend/static-v2/`) — served when `STATIC_UI_VERSION=v2`.
Contains Vite-bundled React app chunks. Active in `run-backend-v2.ps1` and `run-desktop-v2.ps1`.
Apply the same minimal-patch discipline when modifying files in this directory.

**React source** (`frontend/src/`) — never directly served.
TypeScript + React + Zustand source. `vite.config.ts` builds to `backend/static-new/`
(gitignored). `ui_gate.py` has no knowledge of `static-new/`.
Running `npm run build` does NOT update the served UI. This is a known gap — see `CURRENT.md`.

When working on any frontend state:
- Apply the same minimal-patch discipline as for backend changes
- Do not assume changes in one state affect another
- Check `CURRENT.md` for active known issues before starting any UI work
- Identify which state is actually served before modifying any UI file
