# Architecture

## Product Identity

**Stability marker: Stable contract**

This project is an **AI rendering intelligence platform with FFmpeg as the execution backend**.

It should not be treated as a plain FFmpeg wrapper. FFmpeg is the final execution layer, while the product value is in source preparation, AI-assisted clip selection, market-aware scoring, subtitles, motion crop, voice narration, output validation, ranking, and explainability.

The platform is intentionally conservative:

- AI is metadata-first by default.
- AI plans, ranks, recommends, and explains before it mutates render behavior.
- Bounded AI influence is opt-in and must stay narrow.
- Render jobs must remain backward compatible with existing payloads, events, result JSON, and frontend DOM contracts.

## System Diagram

**Stability marker: Stable contract**

```text
Electron shell or browser
        |
        v
Static frontend: backend/static
        |
        v
FastAPI backend: backend/app/main.py
        |
        v
Routes: render, jobs, download, voice, upload, channels
        |
        v
SQLite job state + in-process job queue
        |
        v
Render pipeline: backend/app/orchestration/render_pipeline.py
        |
        +--> Source prep / yt-dlp / local validation / preview session
        +--> Scene detection / segment generation / scoring
        +--> AI Director metadata planning
        +--> Subtitle / translation / ASS styling
        +--> Motion crop / reframe
        +--> Voice narration / audio mix
        +--> FFmpeg encode
        +--> Output validation / quality evaluation / ranking
        |
        v
Output clips, reports, result_json, logs
```

## Runtime Layers

**Stability marker: Semi-stable implementation**

| Layer | Main files | Responsibility |
|---|---|---|
| Desktop shell | `desktop-shell/main.js` | Starts/checks local backend, loads localhost UI, sets packaged runtime paths. |
| Static frontend | `backend/static/index.html`, `backend/static/js/*`, `backend/static/css/app.css` | Render setup, editor, download view, history, job monitor, output gallery. |
| FastAPI app | `backend/app/main.py` | Mounts static UI, registers routes, initializes DB, starts warmup/recovery tasks. |
| API routes | `backend/app/routes/*.py` | Render preparation/submission, jobs, downloads, voice profiles, upload/channels. |
| Job system | `backend/app/services/job_manager.py`, `backend/app/services/db.py` | SQLite job/part rows, in-process priority queue, startup recovery. |
| Render pipeline | `backend/app/orchestration/render_pipeline.py` | End-to-end render orchestration and result JSON assembly. |
| Render services | `backend/app/services/*.py` | FFmpeg, subtitles, motion crop, TTS, translation, scoring, downloader, reports. |
| AI intelligence | `backend/app/ai/**` | AI Director, scoring, planning, creator/market/subtitle/camera/quality metadata. |

## Backend Architecture

**Stability marker: Semi-stable implementation**

The backend is a local FastAPI application. `backend/app/main.py` registers route modules, mounts `/static`, initializes SQLite, ensures a default channel, prunes stale runtime files, marks unfinished render/download jobs as interrupted, and starts warmup.

Important routes:

| Route prefix | File | Responsibility |
|---|---|---|
| `/api/render` | `backend/app/routes/render.py` | Prepare source, preview sessions, render submission, batch render, quick process, resume/retry. |
| `/api/jobs` | `backend/app/routes/jobs.py` | Job/part state, logs, history, WebSocket progress, media streaming. |
| `/api/download` | `backend/app/routes/download.py` | Standalone batch downloader. |
| `/api/voice` | `backend/app/routes/voice.py` | Voice profile list APIs. |
| `/api/upload` | `backend/app/routes/upload.py` | Upload automation and scheduler APIs. |
| `/api/channels` | `backend/app/routes/channels.py` | Channel and output-folder management. |

There is no `backend/app/api` package in the current implementation; the real API layer is `backend/app/routes`.

## Frontend Architecture

**Stability marker: Semi-stable implementation**

The frontend is static HTML/CSS/JS under `backend/static`.

Important files:

| File | Responsibility |
|---|---|
| `backend/static/index.html` | DOM structure and stable IDs for render, download, history, editor, monitor, output gallery. |
| `backend/static/js/globals.js` | Shared runtime state such as `currentJobId`, poll timers, WebSocket handle, selected paths. |
| `backend/static/js/nav.js` | View switching: Render, Download, History, Settings, Editor. |
| `backend/static/js/render-engine.js` | Prepare-source, submit render payload, polling/WebSocket connection. |
| `backend/static/js/render-ui.js` | Render monitor, logs, output gallery, AI insight/strategy panels, history cards. |
| `backend/static/js/editor-view.js` | Preview session editor, trim/volume, subtitles, voice, text layers, final payload assembly. |
| `backend/static/css/app.css` | Full UI styling and state selectors. |

The frontend is feature-rich but fragile. State is shared across large JS files, and many behaviors depend on exact DOM IDs.

### What must not break: UI

- Preserve DOM IDs used by render setup, editor, progress monitor, logs, output gallery, and center preview.
- Preserve `currentJobId`, polling, and WebSocket state behavior unless all callers are updated together.
- Preserve Render / Download / History / Settings navigation behavior.
- Preserve output gallery media links and part streaming endpoints.
- Preserve editor session behavior around `edit_session_id`.

## Desktop Shell Architecture

**Stability marker: Experimental / needs verification**

The desktop app is an Electron shell around the local FastAPI backend.

`desktop-shell/main.js`:

- Enforces a single instance.
- Shows a splash window during startup.
- Checks `http://127.0.0.1:8000/health`.
- Starts a packaged backend executable when available.
- Falls back to Python/venv + Uvicorn when needed.
- Sets runtime data/cache/model paths.
- Injects packaged `ffmpeg-bin` and `ffprobe-bin` paths when present.
- Loads the static app through localhost with cache busting.

Packaged desktop behavior should be marked **needs verification** unless a packaged build has been tested on the target machine.

### What must not break: desktop

- Health check and wait-for-backend flow.
- Packaged `backend-bin/render-backend.exe` path handling.
- Python fallback bootstrap in dev/non-offline mode.
- Runtime env vars for database, temp, channels, caches, Playwright, FFmpeg.
- `preload.js` IPC surface used by folder pickers and shell open actions.

## AI Director Philosophy

**Stability marker: Stable contract**

The AI system is designed around **metadata-first execution**.

AI modules under `backend/app/ai/**` produce:

- clip plans
- camera plans
- subtitle plans
- pacing/emotion hints
- creator preference metadata
- market strategy metadata
- quality scores
- output ranking
- execution recommendations
- explainability

Most AI phases are advisory. They do not rewrite FFmpeg commands, mutate timing, enqueue jobs, delete outputs, or override executors.

Bounded execution exists, but only through explicit opt-in surfaces such as `ai_render_influence_enabled`, and even then it is conservative. For example, `backend/app/ai/director/render_influence.py` can enable limited camera/subtitle influence only under safety checks.

### Stability markers for AI areas

| Area | Marker | Notes |
|---|---|---|
| AI default-off flags in `RenderRequest` | Stable contract | Defaults preserve non-AI rendering behavior. |
| AI Director metadata plan | Stable contract | Pipeline must continue if AI returns `None`. |
| AI render influence | Experimental / needs verification | Opt-in, bounded, not a general render executor. |
| Creator intelligence | Experimental / needs verification | Rich metadata exists, user-facing behavior is still evolving. |
| Explainability | Semi-stable implementation | Useful product surface, but schema may evolve. |
| Quality evaluator | Semi-stable implementation | Evaluation-only; should not mutate files or fail jobs. |

## Render Intelligence Layer

**Stability marker: Semi-stable implementation**

Render intelligence includes more than cutting clips:

- `viral_scorer.py` scores segments for viral potential, motion, position, and hook timing.
- `viral_scoring.py` scores market fit for US/EU/JP using hook, keywords, duration, tone, and readability.
- AI modules under `retention`, `story`, `timing`, `subtitles`, `camera`, `quality`, `output`, `creator_*`, and `orchestrator` provide advisory intelligence.
- `render_pipeline.py` computes output ranking, best clip, quality penalties, partial-success metadata, and result JSON summaries.

The current product gap is not only technical. Technical render quality is stronger than creator-perceived premium quality. Outputs may still feel less premium when hook visuals, subtitle motion, audio polish, branding, intro/outro treatment, and visual consistency are not strongly art-directed.

## Job, Event, and Result Flow

**Stability marker: Stable contract**

Jobs are stored in SQLite:

- `jobs` stores job status, stage, progress, payload JSON, result JSON.
- `job_parts` stores per-part status, progress, timing, scores, output files.

The frontend observes jobs through:

- WebSocket: `/api/jobs/{job_id}/ws`
- HTTP polling: `/api/jobs/{job_id}` and `/api/jobs/{job_id}/parts`
- logs: `/api/jobs/{job_id}/logs`

Polling starts immediately and WebSocket augments it; WebSocket should not be documented as the only source of truth.

Startup recovery marks queued/running jobs as `interrupted`; it does not silently resume them.

## Result JSON Compatibility Contract

**Stability marker: Stable contract**

`jobs.result_json` is a compatibility surface for the UI, history, output gallery, ranking, and future agents.

Important fields include:

- `outputs`
- `segments`
- `market_viral_parts`
- `output_ranking`
- `output_ranking_warning`
- `best_clip`
- `best_exports`
- `voice_summary`
- `subtitle_translate_summary`
- `failed_parts`
- `failed_parts_detail`
- `selected_parts_count`
- `successful_outputs_count`
- `failed_outputs_count`
- `is_partial_success`
- `ai_director`
- `ai_render_influence`
- `ai_beat_execution`
- `ai_output_ranking`
- `ai_render_quality_evaluation`
- `ai_ux`

Compatibility aliases such as `output_rank_score`, `is_best_output`, and `is_best_clip` must not be removed casually.

### What must not break: result_json

- Preserve existing keys consumed by frontend history/output UI.
- Preserve failed-part metadata for partial success.
- Preserve output ranking aliases.
- Preserve AI metadata as optional fields.
- Preserve valid JSON shape even when optional systems fail.

## Skill and Adapter Direction

**Stability marker: Semi-stable implementation**

The project already has adapter-like seams, but not a formal plugin system.

Current modular areas:

- Subtitle engines and styles: SRT, ASS, bounce, karaoke, aliases.
- Crop engines: standard FFmpeg render vs motion-aware crop.
- Voice sources: manual, subtitle, translated subtitle.
- Caption generation modes: template, local Ollama, Claude when configured.
- Market subtitle and viral policies.
- AI advisory modules with explicit safety/fallback behavior.

Document this as current extensibility direction only. Do not promise future plugin systems unless implemented.

## High-Risk Areas

**Stability marker: Stable contract**

| Area | Why risky |
|---|---|
| `backend/app/orchestration/render_pipeline.py` | Central coordinator for source prep, AI, subtitle, voice, FFmpeg, validation, ranking, result JSON. |
| `backend/app/services/render_engine.py` | FFmpeg command construction, codec fallback, motion-aware render delegation. |
| `backend/app/services/subtitle_engine.py` | Timing, SRT slicing/rebasing, ASS generation, karaoke fallback, style aliases. |
| `backend/app/services/motion_crop.py` | OpenCV tracking, subject/motion fallback, subtitle-safe crop logic. |
| `backend/app/models/schemas.py` | API payload compatibility and defaults. |
| `backend/app/ai/**` | Phase-based advisory intelligence and safety contracts. |
| `backend/static/index.html` | DOM IDs are frontend API contracts. |
| `backend/static/js/render-ui.js` | Output gallery, logs, monitor, AI panels. |
| `backend/static/js/render-engine.js` | Render submission, polling, WebSocket. |
| `backend/static/js/editor-view.js` | Preview/editor state and final payload assembly. |
| `backend/static/css/app.css` | Large stateful stylesheet with many late-phase overrides. |

## What Should Not Be Documented

**Stability marker: Stable contract**

- Do not mirror every function body or FFmpeg argument.
- Do not document unverified future features as existing.
- Do not expose private machine paths as general architecture.
- Do not treat experimental AI phases as guaranteed output behavior.
- Do not document forbidden `docs/review/**` or `docs/archive/**` content as editable workflow.
