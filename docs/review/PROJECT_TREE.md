# PROJECT_TREE.md — Full Project Discovery

## Full Project Tree (Source Only)

```
tool-render-video/                     ← project root
├── AGENTS.md                          ← AI agent instructions
├── README.md
├── docker-compose.yml                 ← unused in production
├── .claude/settings.json              ← Claude Code harness config
│
├── backend/                           ← Python FastAPI backend
│   ├── app/
│   │   ├── main.py                    ← FastAPI entry point, startup/shutdown
│   │   ├── core/
│   │   │   ├── config.py              ← path resolution (dev vs packaged)
│   │   │   ├── stage.py               ← JobStage / JobPartStage enums
│   │   │   └── ui_gate.py             ← static UI version resolver
│   │   ├── models/
│   │   │   └── schemas.py             ← Pydantic request schemas
│   │   ├── routes/
│   │   │   ├── render.py              ← render jobs, preview sessions, batch
│   │   │   ├── jobs.py                ← WebSocket + job history API
│   │   │   ├── channels.py            ← channel CRUD
│   │   │   ├── download.py            ← yt-dlp download API
│   │   │   ├── upload.py              ← upload queue, scheduler, accounts
│   │   │   ├── viral.py               ← viral scoring API
│   │   │   ├── subtitle.py            ← subtitle utilities
│   │   │   ├── voice.py               ← TTS voice generation
│   │   │   ├── creator.py             ← creator preferences
│   │   │   └── devtools.py            ← dev-only (ENABLE_DEVTOOLS=1)
│   │   ├── orchestration/
│   │   │   └── render_pipeline.py     ← 290KB god file: full render orchestration
│   │   ├── services/
│   │   │   ├── db.py                  ← SQLite service layer (1900 lines)
│   │   │   ├── job_manager.py         ← priority heap + ThreadPool scheduler
│   │   │   ├── render_engine.py       ← FFmpeg wrappers, codec selection
│   │   │   ├── subtitle_engine.py     ← Whisper + ASS generation
│   │   │   ├── subtitle_transcription_adapters.py
│   │   │   ├── scene_detector.py      ← PySceneDetect + optional TransNetV2
│   │   │   ├── segment_builder.py     ← segment boundary logic
│   │   │   ├── clip_scorer.py         ← clip quality scoring
│   │   │   ├── viral_scorer.py        ← heuristic + optional ML scoring
│   │   │   ├── viral_scoring.py       ← market-specific scoring
│   │   │   ├── motion_crop.py         ← AI face-track crop
│   │   │   ├── audio_mix_service.py   ← narration + BGM mixing
│   │   │   ├── audio_cleanup_adapters.py ← optional DeepFilterNet
│   │   │   ├── tts_service.py         ← edge-tts primary TTS
│   │   │   ├── tts_xtts_adapter.py    ← optional XTTS local TTS
│   │   │   ├── translation_service.py ← deep-translator subtitle translation
│   │   │   ├── channel_service.py     ← channel directory management
│   │   │   ├── downloader.py          ← yt-dlp wrapper
│   │   │   ├── cancel_registry.py     ← job cancellation signals
│   │   │   ├── bin_paths.py           ← ffmpeg/ffprobe path resolution
│   │   │   ├── encoder_helpers.py     ← codec detection helpers
│   │   │   ├── text_overlay.py        ← text layer filter generation
│   │   │   ├── remotion_adapter.py    ← hook intro / outro generation
│   │   │   ├── report_service.py      ← XLS report generation
│   │   │   ├── maintenance.py         ← log pruning, temp cleanup
│   │   │   ├── warmup.py              ← background model preloading
│   │   │   ├── upload_engine.py       ← Playwright upload orchestration
│   │   │   ├── hook_optimizer.py
│   │   │   ├── market_subtitle_policy.py
│   │   │   └── ...
│   │   └── ai/                        ← AI subsystem (60+ modules)
│   │       ├── director/              ← AI edit plan orchestration
│   │       ├── analyzers/             ← transcript, emotion, beat, hook analyzers
│   │       ├── rag/                   ← in-memory vector store + SQLite memory
│   │       ├── knowledge/             ← JSON knowledge pack loading/retrieval
│   │       ├── clips/                 ← clip candidate/batch planning
│   │       ├── subtitles/             ← AI subtitle influence
│   │       ├── camera/                ← AI camera motion planning
│   │       ├── orchestrator/          ← confidence + conflict resolution
│   │       ├── quality/               ← AI quality gates
│   │       └── ... (30+ more packages)
│   ├── knowledge/                     ← JSON knowledge packs (platforms, hooks, etc.)
│   ├── static/                        ← legacy frontend (v1)
│   ├── static-v2/                     ← current frontend (v2, ES modules)
│   │   ├── index.html
│   │   └── assets/
│   │       ├── js/
│   │       │   ├── app.js             ← app bootstrap
│   │       │   ├── router.js          ← SPA hash router
│   │       │   ├── transport.js       ← WebSocket + polling
│   │       │   ├── desktop-adapter.js ← Electron IPC bridge
│   │       │   ├── screens/           ← create, monitor, results, library, source
│   │       │   ├── store/             ← state stores (draft, session, monitor, system)
│   │       │   ├── components/        ← shell, nav, status chip, log drawer, etc.
│   │       │   ├── api/               ← fetch wrappers per domain
│   │       │   └── entities/          ← data model parsers
│   │       └── css/                   ← tokens, base, layout, components
│   ├── static-v3/                     ← v3 shell fragment (not fully wired)
│   ├── static-v4/                     ← v4 fragment (not fully wired)
│   ├── requirements.txt               ← core deps (fastapi, uvicorn, whisper, yt-dlp...)
│   ├── requirements-ai.txt            ← optional AI deps (faiss, sentence-transformers...)
│   ├── Dockerfile                     ← containerized backend (unused in prod)
│   └── tests/                         ← 80+ AI unit tests (pytest)
│
├── desktop-shell/                     ← Electron host
│   ├── main.js                        ← Electron main process
│   ├── preload.js                     ← context bridge (IPC)
│   ├── splash.html                    ← loading screen
│   ├── package.json                   ← electron-builder config
│   ├── backend-bin/                   ← packaged backend exe (PyInstaller)
│   ├── ffmpeg-bin/                    ← bundled ffmpeg.exe / ffprobe.exe
│   └── scripts/logerror.js            ← error log CLI
│
├── channels/                          ← per-channel runtime data (videos, logs, uploads)
│   ├── k1/, T1/, Test 1/, ...
│   └── manual/, preview/, qa_auto_cmd/
│
├── data/                              ← app runtime data
│   ├── app.db                         ← SQLite database
│   ├── logs/                          ← error.log, app.log, request.log
│   ├── whisper_cache/                 ← Whisper model files
│   ├── adaptive/creator_profiles/     ← AI adaptive creator memory
│   ├── feedback/render_feedback/      ← render outcome feedback
│   └── temp/                          ← transient render work dirs
│
├── docs/                              ← extensive product documentation
│   ├── ARCHITECTURE.md
│   ├── RENDER_PIPELINE.md
│   ├── product/                       ← 50+ phase plans (PHASE_63 through PHASE_75)
│   ├── review/                        ← past review docs
│   └── render/                        ← quality upgrade logs
│
├── scripts/                           ← QA/smoke test scripts
└── tests/                             ← root-level tests
```

---

## Main Apps / Packages

| Layer | Technology | Entry Point |
|-------|-----------|-------------|
| Desktop shell | Electron 31 + Node.js | `desktop-shell/main.js` |
| Backend server | FastAPI + Uvicorn | `backend/app/main.py` → `backend/run_backend_server.py` |
| Frontend (v2) | Vanilla ES modules (no bundler) | `backend/static-v2/index.html` → `app.js` |
| Job queue | Python ThreadPoolExecutor + min-heap | `backend/app/services/job_manager.py` |
| Render pipeline | Python orchestrator | `backend/app/orchestration/render_pipeline.py` |
| AI subsystem | Pure Python, optional ML deps | `backend/app/ai/director/ai_director.py` |
| Database | SQLite via stdlib sqlite3 | `backend/app/services/db.py` |
| Upload automation | Playwright + Chromium | `backend/app/services/upload_engine.py` |

---

## Main Entrypoints

1. **Electron packaged**: `desktop-shell/main.js` bootstraps venv/backend exe → opens BrowserWindow
2. **Dev mode**: `uvicorn app.main:app` from `backend/` or via `run_backend_server.py`
3. **Frontend**: `GET /` → `backend/static-v2/index.html` → ES module bootstrap via `app.js`
4. **Primary render trigger**: `POST /api/render/process` → `render.py` → `render_pipeline.py`

---

## Tech Stack Detected

**Backend**
- Python 3.11 (targeted)
- FastAPI 0.115.0 + Uvicorn 0.30.6
- SQLite (stdlib) — sole persistent store
- Whisper (openai-whisper 20231117) — transcription
- PySceneDetect 0.6.4 + OpenCV — scene detection
- yt-dlp 2025.3.31 — YouTube download
- Playwright 1.51.0 — browser automation (upload)
- edge-tts 7.2.8 — text-to-speech
- deep-translator 1.11.4 — subtitle translation
- numpy 1.26.4, opencv-python-headless 4.10.0.84
- FFmpeg (bundled binary) — all video processing
- **Optional AI**: sentence-transformers, faiss-cpu, librosa, mediapipe, faster-whisper, whisperx, TransNetV2, DeepFilterNet

**Frontend**
- Vanilla JavaScript ES modules (no React, no Vue, no Svelte)
- No bundler (Vite/webpack/esbuild)
- No TypeScript
- Hash-based SPA router (`#create`, `#monitor`, `#results`, etc.)
- WebSocket + HTTP polling hybrid for live updates

**Desktop**
- Electron 31.0.2
- electron-builder 24.13.3 (NSIS + portable)
- Python venv bootstrapped at first launch (dev mode only)

---

## Dependency Map

```
Electron main.js
  └── spawns → backend Python process (packaged exe OR uvicorn)
  └── BrowserWindow → loads http://127.0.0.1:8000/

FastAPI app (main.py)
  ├── routes/render.py        → orchestration/render_pipeline.py
  │     └── services/render_engine.py  → FFmpeg subprocess
  │     └── services/scene_detector.py → PySceneDetect + TransNetV2
  │     └── services/subtitle_engine.py → Whisper model
  │     └── services/downloader.py     → yt-dlp
  │     └── ai/director/ai_director.py → 60+ AI modules
  ├── routes/jobs.py          → services/db.py + WebSocket
  ├── routes/upload.py        → services/upload_engine.py → Playwright
  ├── routes/voice.py         → services/tts_service.py → edge-tts
  └── services/job_manager.py → ThreadPoolExecutor priority heap

ai/director/ai_director.py
  ├── ai/analyzers/* (transcript, emotion, hook, beat, retention)
  ├── ai/rag/* (vector_store.py FAISS/cosine, sqlite_store.py, memory_store.py)
  ├── ai/knowledge/* (knowledge_pack_loader.py → /knowledge/*.json)
  ├── ai/clips/* (clip_candidate_engine, clip_segment_selector, clip_batch_planner)
  ├── ai/orchestrator/* (render_orchestrator, strategy_planner, confidence_engine)
  └── ai/creator_dna/* (adaptive creator profile)
```

---

## Runtime Flow Map

```
User opens app
  → Electron main.js: splash screen
  → bootstrap: find Python, create venv, pip install (dev only)
  → spawn: uvicorn app.main:app --port 8000
  → poll /health until ready
  → open BrowserWindow at http://127.0.0.1:8000/
  → FastAPI serves static-v2/index.html
  → app.js: init stores, router, shell component
  → router navigates to #create
```
