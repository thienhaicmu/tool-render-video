# PROJECT_MAP.md — Runtime File Ownership

Quick reference: what file owns what behavior. Updated 2026-05-23.

For the full protected-files list see `AGENTS.md`.
For stability markers (Stable / Semi-stable / Experimental) see `docs/ARCHITECTURE.md`.

---

## Backend Core

| System | File | Risk | Touch? |
|--------|------|------|--------|
| FastAPI entry + startup | `backend/app/main.py` | HIGH | Carefully |
| UI version resolver | `backend/app/core/ui_gate.py` | HIGH | Carefully |
| Env config / data paths | `backend/app/core/config.py` | MEDIUM | Yes |
| **API schema contract** | `backend/app/models/schemas.py` | CRITICAL | Minimal — preserve all defaults |
| **SQLite ORM** | `backend/app/services/db.py` | CRITICAL | No schema drops |
| **Job queue + recovery** | `backend/app/services/job_manager.py` | CRITICAL | Protected |
| **Render orchestration** | `backend/app/orchestration/render_pipeline.py` | CRITICAL | PROTECTED — plan first, full pytest required |
| Error classification | `backend/app/orchestration/render_events.py` | HIGH | Carefully |
| Output validation | `backend/app/orchestration/qa_pipeline.py` | HIGH | Carefully |
| Asset injection | `backend/app/orchestration/asset_pipeline.py` | MEDIUM | Yes |
| Audio cleanup | `backend/app/orchestration/audio_pipeline.py` | MEDIUM | Yes |
| **FFmpeg command layer** | `backend/app/services/render_engine.py` | CRITICAL | Protected |
| **Subtitle / SRT / ASS** | `backend/app/services/subtitle_engine.py` | CRITICAL | Protected |
| **Vertical crop** | `backend/app/services/motion_crop.py` | CRITICAL | Protected |
| Clip boundary builder | `backend/app/services/segment_builder.py` | MEDIUM | Carefully |
| Scene detection | `backend/app/services/scene_detector.py` | MEDIUM | Yes |
| TTS / narration | `backend/app/services/tts_service.py` | MEDIUM | Yes |
| Audio mixing | `backend/app/services/audio_mix_service.py` | MEDIUM | Yes |
| Standalone Downloader (yt-dlp) | `backend/app/services/downloader.py` | MEDIUM | Yes — feature lives outside the render pipeline |
| Cancel propagation | `backend/app/services/cancel_registry.py` | HIGH | Protected |
| FFmpeg binary paths | `backend/app/services/bin_paths.py` | HIGH | Protected |
| Preview sessions | `backend/app/services/preview/session_service.py` | MEDIUM | Yes |

## AI System

Phase G retired the legacy monolithic `ai/director/ai_director.py` and the
sibling `ai/orchestrator/`, `ai/analyzers/`, `ai/rag/` packages. The current
AI surface is distributed across the modules below. Every public entry point
in any `backend/app/ai/**` module MUST catch all exceptions and return
`None` on failure — see Sacred Contract #3 in CLAUDE.md.

| System | File | Risk | Touch? |
|--------|------|------|--------|
| LLM providers (Gemini, Claude, OpenAI) | `backend/app/ai/llm/` | HIGH | Add new provider behind the same dispatcher, never raise |
| LLM shared prompt + parser | `backend/app/ai/llm/prompts.py`, `parser.py` | HIGH | Schema is additive; backward-compat aliases stay until stored jobs migrate |
| Analysis (hybrid + local) | `backend/app/ai/analysis/` | MEDIUM | Yes — must return None on failure |
| Cloud analyzer providers | `backend/app/ai/analysis/cloud/` | MEDIUM | Yes |
| Visibility / tracing / diagnostics | `backend/app/ai/visibility/`, `ai/tracing.py`, `ai/diagnostics.py` | MEDIUM | Yes |
| LLM stage orchestration | `backend/app/orchestration/llm_stage.py`, `llm_pipeline.py` | HIGH | Sacred Contract #3 applies through the orchestration entry too |
| Knowledge packs | `backend/knowledge/` | LOW | Yes — add only |

## API Routes

| Route module | File | Key surface | Risk |
|--------------|------|-------------|------|
| Render | `backend/app/routes/render.py` | POST /api/render/process, resume, retry, cancel | CRITICAL |
| Jobs | `backend/app/routes/jobs.py` | GET /api/jobs/history, WebSocket /api/jobs/{id}/ws | CRITICAL |
| Editing | `backend/app/routes/editing.py` | POST trim, rerender, export | MEDIUM |
| Downloader | `backend/app/features/downloader/router.py` | `/api/downloader/*` standalone batch — independent of render | MEDIUM |
| Voice | `backend/app/routes/voice.py` | TTS endpoints | MEDIUM |
| Channels | `backend/app/routes/channels.py` | Channel management | LOW |
| DevTools | `backend/app/routes/devtools.py` | Shell exec — **DISABLED** (requires ENABLE_DEVTOOLS=1) | DANGER |

## Frontend States

| State | Path | Active when | Notes |
|-------|------|-------------|-------|
| Legacy HTML app | `backend/static/` | Default — no env var set | Protected by AGENTS.md. Default served UI. |
| v2 React app (served) | `backend/static-v2/` | `STATIC_UI_VERSION=v2` | Older Vite chunks. Cannot update via current `npm run build`. |
| React source | `frontend/src/` | **Never directly served** | TypeScript + React + Zustand source. |
| Build output | `backend/static-new/` | **Never served** | Gitignored. `ui_gate.py` has no knowledge of this path. |

**Build gap**: `vite.config.ts` → `backend/static-new/` (gitignored). `ui_gate.py` serves `backend/static-v2/`.
These paths differ. See CURRENT.md issue #1.

## Domain Models

| Model | File | Contract |
|-------|------|----------|
| Timeline coordinate transforms | `backend/app/domain/timeline.py` | Source↔output mapping, speed clamp [0.5, 1.5] |
| Clip timing manifests | `backend/app/domain/manifests.py` | BaseClipManifest — per-clip decisions before FFmpeg |

## Electron Desktop

| Component | File | Responsibility |
|-----------|------|----------------|
| Main process | `desktop-shell/main.js` | Boots Python backend, creates BrowserWindow, IPC |
| IPC bridge | `desktop-shell/preload.js` | contextBridge — renderer ↔ main |

Electron loads `http://127.0.0.1:8000/` as a WebView. All UI is served by FastAPI — not file://.

## Data and Runtime

| Item | Location | Risk |
|------|----------|------|
| Job state database | `data/app.db` | CRITICAL — NEVER delete |
| AI memory / learning | `data/ai_memory.db` | MEDIUM |
| Channel output videos | `channels/` | LOW — runtime outputs |
| Render temp files | `data/temp/` | LOW — auto-cleaned every 30 min |
| Whisper model cache | `data/whisper_cache/` | LOW — re-downloadable |

## Critical Contracts — Never Break

| Contract | Owner file | What must stay intact |
|----------|-----------|----------------------|
| result_json backward-compat aliases | `render_pipeline.py` | `output_rank_score`, `is_best_output`, `is_best_clip` |
| RenderRequest field defaults | `schemas.py` | New flags must default to `False` / disabled |
| WebSocket event shape | `jobs.py` | `{ job, parts[], summary: WsProgressSummary }` |
| Job stage enum names | `render_pipeline.py` | `QUEUED → DOWNLOADING → RENDERING → DONE` sequence |
| AI never-raises contract | `ai_director.py` | Returns `None` on any failure — never `raise` |
| Part status names | `render_pipeline.py` | `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE` |

## Key Environment Variables

| Variable | Effect | Default |
|----------|--------|---------|
| `STATIC_UI_VERSION` | `"v2"` → serve `backend/static-v2/`; else → `backend/static/` | legacy (static/) |
| `ENABLE_DEVTOOLS` | `"1"` → enables unauthenticated shell-exec route | disabled |
| `MAX_CONCURRENT_JOBS` | Render parallelism cap | `cpu_count // 2` |
| `APP_DATA_DIR` | Override data directory location | Platform-specific |
| `CLEANUP_INTERVAL_SEC` | Preview session and temp cleanup interval | `1800` (30 min) |
| `AUDIO_CLEANUP_AUTO` | Enable DeepFilterNet audio cleanup | disabled |
