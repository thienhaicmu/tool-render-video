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
        +--> Scene detection / segment generation
        |
        +--> [Layer 4.5] ContentAnalyzer (Pass 1 — single-pass content understanding)
        |       +--> Transcript normalization (SRT → chunks)
        |       +--> Emotion arc / pacing / beat analysis
        |       +--> Narrative arc (hook / build / climax / outro)
        |       +--> Hook position scoring
        |       +--> Speaker segmentation
        |       --> ContentAnalysisResult (shared by all downstream AI consumers)
        |
        +--> Segment scoring (viral_scorer — enriched with narrative_phase, hook_proximity)
        |
        +--> [Phase 1] Unified Scoring
        |       +--> select_ai_segments(transcript chunks)
        |       +--> match AI windows to heuristic segments by time overlap (>=30%)
        |       +--> write ai_blend_bonus (0-15 pts) onto matched segments
        |       --> blended score flows through hook-first + story-arc sequencing
        |
        +--> AI Director metadata planning (reads ContentAnalysisResult — no re-analysis)
        |       +--> [Phase 2] Cloud reranker (Groq): clip_type, thumbnail_sec, drop signal
        |       +--> [Phase 5] Audio energy analyzer: exclamation density, ALL-CAPS,
        |       |     energy keywords, speech acceleration (0-20 pts, transcript-only)
        |       +--> [Phase 6] Feedback bias: channel rating history -> hook_type/clip_type bonus
        |
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
| Job system | `backend/app/services/job_manager.py`, `backend/app/services/db.py` | SQLite job/part rows, in-process priority queue (O(1) duplicate check via mirror set), startup recovery. |
| Render pipeline | `backend/app/orchestration/render_pipeline.py` | End-to-end render orchestration, pre-render setup, render loop, and result JSON assembly. Reduced from 5,816 → 2,959 lines in Phase A (A-1..A-4). |
| Render pipeline helpers | `backend/app/orchestration/pipeline_helpers.py` | Subtitle slicing, SRT/ASS utilities, CTA blocks, platform profiles, playback speed helpers. Extracted in Phase A-1. |
| Render pipeline AI phases | `backend/app/orchestration/pipeline_ai_phases.py` | AI Director invocation, timing mutations, emphasis config, visual intensity, cover hint resolution. Extracted in Phase A-2. |
| Part renderer | `backend/app/orchestration/stages/part_renderer.py` | `PartRenderContext` dataclass + `prepare_part_assets()` + `process_one_part()`. Carries all per-part render logic (cut, transcribe, subtitle, voice, FFmpeg, QA, scoring). Extracted in Phase A-3. |
| Pre-render scenes | `backend/app/orchestration/pipeline_pre_render.py` | Scene detection, segment building, viral scoring, early transcription, visual analysis, content analysis, unified AI score blend (Phase 1). `run_pre_render_scenes()` → `PreRenderScenesResult`. Extracted in Phase A-6. |
| Render loop | `backend/app/orchestration/pipeline_render_loop.py` | JOB_SEMAPHORE acquire/release, worker throttle, sequential/parallel FFmpeg encode loop, per-part failure handling. `run_render_loop()` → `RenderLoopResult`. Extracted in Phase A-7. |
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
| `/api/channels` | `backend/app/routes/channels.py` | Channel and output-folder management. |
| `/api/feedback` | `backend/app/routes/feedback.py` | Per-clip user ratings (thumbs up/down), channel feedback summary, hook_type scores. |

There is no `backend/app/api` package in the current implementation; the real API layer is `backend/app/routes`.

## Frontend Architecture

**Stability marker: Semi-stable implementation**

The frontend is a React 18 + TypeScript application built with Vite. Source lives in `frontend/src/`. Built output is served from `backend/static-v2/` via `ui_gate.py`.

The old static JS frontend (`backend/static/`) is legacy. All active development targets the React app.

### Panel routing

There is no React Router. Navigation is controlled by a `activePanel` string in `uiStore` (Zustand). `App.tsx` maps panel keys to top-level screen components.

| Panel key | Component | Notes |
|---|---|---|
| `clip-studio` | `ClipStudio` | Primary workflow — fullscreen, bypasses AppShell |
| `home` / `library` | `HistoryScreen` | Job history with filters and detail drawer |
| `download` | `DownloaderScreen` | YouTube/platform batch download |
| `studio` | `StudioScreen` | Source hero → ClipStudio redirect |
| `settings` | `SettingsScreen` | App settings |
| `render` | `RenderSetupScreen` | Deprecated — local file only, no YouTube |

### Feature modules

| Directory | Purpose |
|---|---|
| `features/clip-studio/` | 4-step render workflow: Source → Configure → Rendering → Results |
| `features/jobs/` | History screen, job list, filters, detail drawer |
| `features/downloader/` | YouTube/platform downloader UI |
| `features/studio/` | Source selection hero for ClipStudio |
| `features/render/` | Deprecated render form — local file only |

### State management

| Store | Purpose |
|---|---|
| `uiStore` | Active panel, toast notifications, render step |
| `renderStore` | Active job ID, job submission; written on submit only |

**Known debt**: `renderStore` is not updated from WebSocket events. Components that need live job state must use `useRenderSocket` hook directly.

### WebSocket and polling

- `useRenderSocket(jobId)` — connects to `WS /api/jobs/{job_id}/ws`, emits progress every 500ms
- `GET /api/jobs/{job_id}` — HTTP polling fallback; must remain functional per frozen contract
- Both paths must carry equivalent state; no progress data may be WebSocket-exclusive

### What must not break: UI

- WebSocket event shape: `{job, parts[], summary}` — all three keys required
- HTTP polling fallback — must return same state as WebSocket
- Job stage names: `QUEUED → DOWNLOADING → RENDERING → DONE`
- Part status names: `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE`
- `result_json` fields: `output_rank_score`, `is_best_output`, `is_best_clip` — consumed by history UI
- Media streaming endpoints: `/api/jobs/{id}/parts/{no}/media` — used by clip viewer

See `docs/FRONTEND_ARCHITECTURE.md` for full component-level detail.

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

## Two-Pass AI Architecture

**Stability marker: Semi-stable implementation**

The AI pipeline follows a two-pass design where content understanding is separated from clip-level technical decisions.

### Pass 1 — Content Understanding (Phase 46, render_pipeline.py)

`ContentAnalyzer.analyze()` runs once per job after early transcription and produces a `ContentAnalysisResult` dataclass. This is Layer 4.5 — between scene detection and segment selection.

```
ContentAnalysisResult fields
  .chunks              — normalized transcript (shared, no re-read)
  .narrative_arc       — hook / build / climax / outro windows
  .hook_positions      — top 5 hook candidates with scores
  .dominant_emotion    — emotion label + score
  .emotion_arc         — per-window emotion map (6 windows)
  .speaker_segments    — pause-gap speaker groups
  .beat_available      — beat detection result
  .bpm / .beat_count / .energy_level
  .pacing_style / .suggested_cut_style
  .silence_penalty
```

**Feature flags** (both default `False` — Contract 2 compliant):
- `ai_content_driven_selection` — AI Director segment selections override heuristic scored[]
- `ai_early_transcription` — Whisper runs before scene detection

### Pass 2 — Technical AI per consumer

Every downstream AI consumer reads from `ContentAnalysisResult` instead of running its own analysis:

| Consumer | What it reads | What it previously did |
|---|---|---|
| `viral_scorer.score_segments()` | `narrative_arc`, `hook_positions` | No content enrichment |
| `clip_selector.select_ai_segments()` | `hook_positions` → candidate boost | No content awareness |
| `ai_director._build_plan()` — chunks | `chunks` | Re-read and re-parsed SRT file |
| `ai_director._build_plan()` — pacing | `pacing_style`, `bpm`, `emotion`, `beat_count` | Re-ran `analyze_beats` + `analyze_pacing_emotion` |

### New fields produced by Pass 1 enrichment

`scored[]` dicts (output of `viral_scorer`) now carry:
- `narrative_phase` — which arc phase the clip falls in ("hook", "build", "climax", "outro")
- `hook_proximity_score` — 0–100 proximity to nearest hook position

`AIClipPlan` candidates (output of `clip_selector`) now carry:
- score bonus up to +5 when candidate starts within 8s of a known hook position
- `hook_proximity` appended to reason string when boost applied

### Fallback behavior

When `ContentAnalysisResult.available=False` (no transcript, analyzer exception, or feature flags off), every consumer falls back to its original independent analysis path. No behavior change for existing jobs.

## Hybrid Analysis Layer

**Stability marker: Experimental / needs verification**

The hybrid analysis layer (`backend/app/ai/analysis/`) provides a unified interface for combining local rule-based analyzers with optional cloud AI enrichment. It sits inside `ai_director._build_plan()` and runs once per job, before clip selection.

### Architecture

```text
Transcript chunks + context
        |
        v
HybridAnalyzer  (ai/analysis/hybrid_analyzer.py)
  |-- LocalAnalyzer  (always runs, never fails)
  |     |-- hook_analyzer.py    — regex hook scoring, 9 types
  |     └── emotion_analyzer.py — keyword emotion detection
  |
  |-- CloudAnalyzer  (optional, gated by ai_cloud_enabled=False)
  |     |-- OpenAIProvider  — gpt-4o-mini (~$0.0003/video)
  |     └── GroqProvider    — llama-3.1-8b-instant (free tier)
  |
  └── MergeStrategy  (ai/analysis/merger.py)
        — cloud 70% / local 30% for semantic signals
        — cloud subtitle/camera hints take priority when present
        |
        v
  AnalysisSignals  (unified output schema)
    .clip_signals     — per-window hook scores + relevance + hook_type
                        + clip_type (hook/payoff/educational/emotional/transition)  [Phase 2]
                        + thumbnail_sec                                              [Phase 2]
                        + drop flag (cloud reranker signals low quality)            [Phase 2]
    .emotion          — dominant emotion label + score
    .subtitle_hints   — style_preset, highlight_keywords, density
    .camera_hints     — behavior, zoom_strength, follow_strength
    .confidence       — blended confidence 0–1
    .source           — "local" | "cloud" | "hybrid"
```

### What AnalysisSignals flows into

| Downstream | Effect |
|---|---|
| `clip_selector._apply_cloud_enrichment()` | Blends cloud hook scores into local candidate scores; copies clip_type and thumbnail_sec; drops clips flagged drop=True [Phase 2] |
| `clip_selector._select_diverse()` | Applies clip_type diversity penalty — too many clips of same type reduces score [Phase 2] |
| `audio_energy_analyzer.score_audio_energy()` | Transcript-only audio energy proxy: exclamation density, ALL-CAPS, energy keywords, speech acceleration (0-20 pts per clip) [Phase 5] |
| `pacing_ctx` in `_build_plan()` | Cloud emotion overrides local when confidence ≥ 40 |
| `pacing_ctx` cloud hint fields | `cloud_subtitle_density`, `cloud_subtitle_preset`, `cloud_camera_behavior` available to planners |
| `camera_planner` | Receives enriched pacing_ctx → better behavior decisions |
| `subtitle_planner` | Receives enriched pacing_ctx → better tone/density/emphasis decisions |

### What AnalysisSignals does NOT touch

The analysis layer never writes to `payload`, never calls FFmpeg, never writes to SQLite, and never modifies `render_pipeline.py` state. The only path from `AnalysisSignals` to actual FFmpeg parameters is through the existing `render_influence.py` gate (unchanged).

### Contract 2 compliance

All four new `RenderRequest` fields default to `False` / `None`:

```python
ai_cloud_enabled: bool = False
ai_cloud_provider: Optional[str] = None   # "openai" | "groq"
ai_cloud_api_key: Optional[str] = None
ai_cloud_model: Optional[str] = None      # None = provider default
```

Cloud analysis is entirely disabled unless `ai_cloud_enabled=True` is explicitly set. Existing jobs never activate it on replay.

### Extension points

Adding a new cloud provider requires one new file implementing `CloudAnalyzerBase._call_api()`. Adding a new local analyzer requires extending `LocalAnalyzer._score_clips()`. Neither change requires modifying `ai_director.py`.

## Unified Scoring Layer (Phase 1)

**Stability marker: Semi-stable implementation**

When Phase 46 content analysis produces transcript chunks, `pipeline_pre_render.py` runs
`select_ai_segments()` (the same function used by AI Director) and blends the resulting
scores back into the heuristic `scored[]` list before final sorting.

### How it works

```text
Phase 46 ContentAnalysisResult.chunks (transcript)
        |
        v
select_ai_segments(chunks, scenes, mode_config)
        |
        v
For each heuristic segment:
    find best-overlap AI window (>= 30% of segment duration)
    ai_blend_bonus = min(15.0, ai_score * 0.15)
        |
        v
Sort key: (viral_score + ai_blend_bonus) x structure_bias x dna_bonus x platform_hook
        |
        v
Hook-first sequencing -> Story arc (hook -> build -> payoff)
```

### Properties

- **Max influence:** +15 pts onto a viral_score that typically ranges 0-150 (~10% max)
- **Non-replacing:** heuristic segments are kept; only their sort weight changes
- **Idempotent fallback:** any exception logs and continues with unblended scores
- **ENV gate:** `UNIFIED_SCORING_ENABLED=0` disables entirely
- **Cache-safe:** `ai_blend_bonus` is computed after score cache read/write (never cached itself)
- **Activates when:** `ai_early_transcription=True` or `ai_content_driven_selection=True`

### Relationship to Phase 44

| Condition | Result |
|-----------|--------|
| `ai_content_driven_selection=False` | Phase 1 blends AI scores into heuristic order |
| `ai_content_driven_selection=True` | Phase 44 replaces `scored[]` entirely; Phase 1 blend already baked in |

---

## Feedback Learning Loop (Phase 6)

**Stability marker: Experimental / needs verification**

Users can rate individual rendered clips with thumbs up/down in the results screen.
Ratings accumulate per channel and are applied as score bonuses/penalties in future renders
for the same channel.

### Data model

```sql
clip_feedback (
    job_id, part_no, channel_code, goal,
    rating INTEGER CHECK(rating IN (-1, 1)),
    hook_type, clip_type,
    start_sec, end_sec, duration_sec,
    rated_at,
    UNIQUE(job_id, part_no)
)
```

### Learning signal flow

```text
User clicks thumbs up/down on a clip in StepResults (frontend)
        |
POST /api/feedback/jobs/{id}/parts/{no}
        |
clip_feedback table (channel_code + goal + hook_type + clip_type)
        |
        v (next render for same channel)
feedback_scorer.build_feedback_context(channel_code, goal)
    -> hook_type_net: {hook_type: liked_count - disliked_count}
    -> clip_type_net: {clip_type: liked_count - disliked_count}
    -> avg_liked_position: float (position bias)
        |
apply_feedback_bias(candidates, feedback_context)
    -> hook_type bonus/penalty (max +-4 pts)
    -> clip_type bonus/penalty (max +-2 pts)
    -> position bias (max +1.5 pts)
```

### Safety properties

- Rating the same clip twice toggles it off (DELETE then re-rate)
- `build_feedback_context` returns empty dict on any DB error
- `apply_feedback_bias` catches all exceptions — failure is silent and advisory only
- ENV gate: `FEEDBACK_SCORING_ENABLED=0` disables entirely

---

## Render Intelligence Layer

**Stability marker: Semi-stable implementation**

Render intelligence includes more than cutting clips:

- `viral_scorer.py` scores segments for viral potential, motion, position, hook timing, narrative phase, and hook proximity.
- `viral_scoring.py` scores market fit for US/EU/JP using hook, keywords, duration, tone, and readability.
- `ContentAnalyzer` runs a single-pass content analysis shared by all downstream consumers.
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
