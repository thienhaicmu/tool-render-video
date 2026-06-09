# Render Studio — Local AI Video Platform

Auto-render, subtitle, score, and publish short-form vertical videos from YouTube or local files.  
Runs fully on-device. No cloud API required for core rendering.

---

## What it does

| Step | Feature |
|---|---|
| **Source** | YouTube / TikTok / local file |
| **Download** | yt-dlp multi-client retry, proxy support, cookie auth |
| **Scene detection** | PySceneDetect + TransNetV2 + silence-aware adaptive cuts |
| **AI scoring** | Viral score, retention score, hook score, market score per clip |
| **LLM segment selection** | Gemini / OpenAI / Claude picks best clips + builds RenderPlan |
| **Render** | Parallel FFmpeg encode — subtitles, motion crop, color grade, zoom burst |
| **Subtitles** | Whisper / faster-whisper / WhisperX → SRT → ASS karaoke or bounce |
| **Voice** | Edge TTS or XTTS local voice cloning, mixed per part |
| **BGM** | Background music library with mood-based pick and auto-ducking |
| **Cover frame** | AI-directed cover frame extracted at `cover_offset_ratio` |
| **A/B scores** | Per-output quality ratings stored for AI Director feedback loop |
| **Upload** | Playwright browser automation to TikTok (optional) |

---

## Project layout

```
tool-render-video/
├── backend/                        FastAPI application
│   ├── app/
│   │   ├── core/                   Config (config.py), stage enums (stage.py)
│   │   ├── db/                     SQLite connection, repos, migrations
│   │   │   └── migration_steps/    0001…0006 additive-only migrations
│   │   ├── domain/                 Pure dataclasses (RenderPlan, CreatorContext, Timeline)
│   │   ├── features/
│   │   │   ├── render/
│   │   │   │   ├── ai/             LLM providers (gemini/openai/claude), parser, prompts
│   │   │   │   ├── editing/        Trim, rerender, export endpoints
│   │   │   │   └── engine/
│   │   │   │       ├── audio/      mixer.py (narration + BGM), tts.py
│   │   │   │       ├── encoder/    ffmpeg_helpers.py, clip_renderer.py, clip_ops.py
│   │   │   │       ├── motion/     crop.py (OpenCV tracker), path.py
│   │   │   │       ├── overlay/    text_overlay.py
│   │   │   │       ├── pipeline/   render_pipeline.py (main orchestrator)
│   │   │   │       │               llm_pipeline.py, qa_pipeline.py, …
│   │   │   │       └── stages/     part_renderer.py + 8 helper stages
│   │   │   └── download/           yt-dlp engine + download router
│   │   ├── jobs/                   manager.py (ThreadPoolExecutor queue), cancel.py
│   │   ├── models/                 render.py (RenderRequest 152 fields)
│   │   │                           render_public.py (88-field wire surface)
│   │   ├── routes/                 jobs.py, settings.py, feedback.py, voice.py, …
│   │   └── main.py                 FastAPI app, router mounts, startup
│   ├── static-v2/                  React v2 frontend (built by frontend/)
│   ├── requirements.txt            Core dependencies
│   └── requirements-ai.txt         Optional: faster-whisper, torch, LLM clients
│
├── frontend/                       React + Vite source (builds → backend/static-v2/)
│   └── src/features/clip-studio/
│
├── desktop-shell/                  Electron wrapper
│   ├── main.js                     Bootstrap, venv, backend lifecycle, env injection
│   └── package.json
│
├── data/                           Runtime data (gitignored)
│   ├── app.db                      SQLite — sole job state authority
│   ├── logs/                       Structured JSON logs
│   ├── temp/                       Working + preview files
│   ├── cache/                      Render cache (72h TTL)
│   └── bgm/                        BGM library: bgm/{mood}/*.mp3
│
├── channels/                       Per-channel output trees
├── docs/                           Documentation (see index below)
├── .env.example                    Environment template — copy to .env
├── run-backend-v2.ps1              Start backend (PowerShell)
├── run-desktop-v2.ps1              Start desktop app (PowerShell)
└── CLAUDE.md                       AI agent instructions + Sacred Contracts
```

---

## Quick start — development

### Prerequisites

| Tool | Minimum | Install |
|---|---|---|
| Python | 3.11 | python.org |
| FFmpeg + FFprobe | 6.x | `winget install -e --id Gyan.FFmpeg` |
| Node.js | 18+ | Desktop shell / frontend only |

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Optional: AI extras (faster-whisper, LLM clients)
pip install -r requirements-ai.txt

# Copy and edit env
copy ..\.env.example ..\.env

# Start
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` (React v2 UI, requires `STATIC_UI_VERSION=v2` in .env).

### PowerShell shortcuts

```powershell
.\run-backend-v2.ps1      # backend only
.\run-desktop-v2.ps1      # Electron desktop app
```

### Desktop app (Electron)

```powershell
cd desktop-shell
npm install
npm start                  # development
npm run dist:win           # NSIS + portable installer
```

---

## AI features

The render engine is driven by a **RenderPlan** (`domain/render_plan.py`) emitted by the LLM
after analysing the source. All fields default to `""` / `None` — empty means "inherit from
payload / creator DNA".

| RenderPlan field | Effect in engine |
|---|---|
| `ClipPlan.pacing` (fast/medium/slow) | `words_per_group` for subtitle timing |
| `SubtitlePolicy.subtitle_mode` | word_by_word / phrase / sentence ASS writer |
| `ClipPlan.hook_intensity` (0–1) | Zoom burst + `visual_intensity_hint="high"` when ≥ 0.75 |
| `ClipPlan.retention_score` + `viral_score` | CRF ±1 micro-adjustment per clip |
| `ClipPlan.cover_offset_ratio` | Cover frame JPEG extracted at that timestamp |
| `CameraStrategy.reframe_mode` | center / track / fixed reframe mode |
| `CameraStrategy.tracker_hint` | trackerless = detection-only OpenCV path |
| `CameraStrategy.motion_aware_crop` | Override payload motion_aware_crop per job |
| `AudioPlan.bgm_mood` | Pick BGM file from `data/bgm/{mood}/` |
| `AudioPlan.bgm_volume` | BGM gain offset (dB, relative to -18 dB floor) |

### LLM providers

Configure via `.env` — all three are optional (install the matching client from `requirements-ai.txt`):

| Provider | Env var | Default model |
|---|---|---|
| Gemini | `GEMINI_API_KEY` | gemini-2.0-flash-exp |
| OpenAI | `OPENAI_API_KEY` | gpt-4o-mini |
| Claude | `CLAUDE_API_KEY` | claude-3-5-haiku |

Set `AI_PROVIDER_DEFAULT=gemini` (or `openai` / `claude`) in `.env`.

---

## Key environment variables

See `.env.example` for the full list with comments. Most important:

| Variable | Default | Purpose |
|---|---|---|
| `STATIC_UI_VERSION` | `v2` | `v2` = React UI; `legacy` = old static HTML |
| `APP_DATA_DIR` | `./data` | SQLite, logs, cache, BGM library |
| `FFMPEG_BIN` / `FFPROBE_BIN` | auto-detect | Override if FFmpeg is not on PATH |
| `NVENC_MAX_SESSIONS` | `3` | Hardware encoder session limit — **never exceed GPU limit** |
| `MAX_RENDER_JOBS` | `2` | Concurrent render jobs |
| `AI_PROVIDER_DEFAULT` | `gemini` | LLM provider for new jobs |
| `GEMINI_API_KEY` | — | Gemini API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `CLAUDE_API_KEY` | — | Anthropic API key |
| `SUBTITLE_PER_PART_MODEL` | `small` | Whisper model size (tiny/small/medium/large-v3) |
| `BGM_DUCKING_ENABLED` | `1` | Duck BGM under voice with sidechain compressor |
| `LLM_EMIT_RENDER_PLAN` | `0` | Enable RenderPlan emission from LLM (Sprint 1–3) |

---

## Tests

```powershell
cd backend
python -m pytest                          # full suite (~8 min)
python -m pytest tests/test_foo.py -v     # focused
```

**Baseline:** 1087 passed, 1 pre-existing flaky fail
(`test_render_pipeline_integration` — passes in isolation, fails only in full-suite ordering).

---

## API

| Method | Path | Description |
|---|---|---|
| POST | `/api/render/process` | Submit render job (`RenderRequestPublic` body) |
| GET | `/api/jobs/{id}` | Job status poll |
| GET | `/api/jobs/{id}/ws` | WebSocket live progress stream |
| GET | `/api/jobs/{id}/scores` | A/B quality scores |
| POST | `/api/jobs/{id}/parts/{no}/trim` | Trim a rendered part |
| POST | `/api/jobs/{id}/parts/{no}/rerender` | Re-render a part |
| POST | `/api/jobs/{id}/parts/{no}/export` | Export a part |
| GET | `/api/settings/data-retention` | Retention config |
| GET | `/metrics` | Prometheus metrics |

Full contract: [docs/FRONTEND_CONTRACT.md](docs/FRONTEND_CONTRACT.md)

---

## Documentation index

| File | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System overview, data flow, component map |
| [docs/RENDER_PIPELINE.md](docs/RENDER_PIPELINE.md) | All render stages, parallelism, resume logic |
| [docs/AI_INTEGRATION.md](docs/AI_INTEGRATION.md) | RenderPlan contract, LLM providers, prompt flow |
| [docs/FRONTEND_CONTRACT.md](docs/FRONTEND_CONTRACT.md) | REST + WebSocket frozen API contracts |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | All environment variables with descriptions |
| [docs/DATABASE.md](docs/DATABASE.md) | Schema, migrations, WAL mode, connection model |
| [CLAUDE.md](CLAUDE.md) | Sacred Contracts, blast radius tiers, agent protocol |

---

## Sacred Contracts (never break)

These are hardcoded invariants — violations corrupt the system silently:

1. `result_json` must always contain `output_rank_score`, `is_best_output`, `is_best_clip`
2. Every new `RenderRequest` field defaults to `False` / disabled
3. All AI modules catch exceptions internally — never raise, always `return None`
4. Job stage names are frozen: `QUEUED → STARTING → RUNNING → … → DONE`
5. Part stage names are frozen: `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE`
6. `_emit_render_event` signature is frozen — 50+ call sites, no schema validation
7. `data/app.db` is the sole job state — never delete, never write outside `db/` module
8. `qa_pipeline.py` output validation is never bypassed — corrupt videos must fail, not succeed

Full details: [CLAUDE.md](CLAUDE.md)
