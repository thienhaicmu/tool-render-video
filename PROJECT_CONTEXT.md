# PROJECT_CONTEXT.md — AI Video Render Studio

> This file is read by every agent on every invocation.
> For full domain knowledge, sacred contracts, and runtime protections: read `CLAUDE.md`.
> Keep this file current — stale context produces bad agent behavior.
> Last Updated: 2026-05-25

---

## Project Identity

**Name:** AI Video Render Studio
**Type:** Offline-first desktop AI video rendering platform
**Owner:** thienhaicmu
**Status:** Active development — backend stable, frontend being rebuilt
**Current Branch:** restructure/output-timeline-architecture

---

## Stack

**Language(s):** Python 3.x (backend), TypeScript/React (frontend — being rebuilt)
**Framework(s):** FastAPI + Uvicorn
**Database:** SQLite WAL mode — `data/app.db` (sole job state authority)
**Infrastructure:** Electron desktop shell + local FFmpeg subprocess + Whisper + OpenCV
**AI/ML:** yt-dlp (download), Whisper (transcription), OpenCV (subject tracking), Edge TTS (voice)
**Package Manager:** pip + uv (backend), npm (frontend)
**Test Framework:** pytest
**CI/CD:** None — offline desktop app

---

## Repository Structure

```
tool-render-video/
├── backend/
│   ├── app/
│   │   ├── orchestration/
│   │   │   ├── render_pipeline.py     # CRITICAL — 5,816 lines, all render stages
│   │   │   ├── qa_pipeline.py         # CRITICAL — output validation gate
│   │   │   ├── asset_pipeline.py      # HIGH
│   │   │   ├── audio_pipeline.py      # MEDIUM
│   │   │   └── render_events.py       # HIGH
│   │   ├── ai/
│   │   │   └── director/
│   │   │       └── ai_director.py     # CRITICAL — 5,718 lines
│   │   ├── services/
│   │   │   ├── render/
│   │   │   │   ├── ffmpeg_helpers.py  # HIGH — real FFmpeg execution layer
│   │   │   │   ├── legacy_renderer.py # HIGH
│   │   │   │   └── clip_ops.py        # HIGH
│   │   │   ├── motion_crop.py         # CRITICAL — 2,464 lines
│   │   │   ├── subtitle_engine.py     # HIGH
│   │   │   ├── job_manager.py         # HIGH
│   │   │   └── db.py                  # HIGH
│   │   ├── routes/
│   │   │   ├── render.py              # MEDIUM
│   │   │   ├── jobs.py                # MEDIUM
│   │   │   └── devtools.py            # HIGH — SECURITY: unauthenticated shell route
│   │   ├── models/
│   │   │   └── schemas.py             # HIGH — Pydantic API contracts
│   │   ├── core/
│   │   │   ├── config.py              # LOW
│   │   │   └── ui_gate.py             # HIGH
│   │   └── main.py                    # HIGH
│   └── .venv/
├── frontend/                          # Being rebuilt — do not treat as authoritative
├── desktop-shell/                     # Electron wrapper
├── data/
│   └── app.db                         # CRITICAL — sole job state, never delete
├── docs/
│   ├── RENDER_PIPELINE.md
│   ├── ARCHITECTURE.md
│   └── review/                        # READ-ONLY audit ledger — never edit existing files
├── .claude/
│   ├── agents/                        # Agent definitions
│   └── commands/
├── rules/                             # Universal decision rules
├── workflows/                         # Operating procedures
├── memory/                            # Persistent agent state
├── CLAUDE.md                          # Full domain knowledge — read for all render/backend tasks
└── PROJECT_CONTEXT.md                 # This file
```

---

## Core Conventions

- **Code style:** Standard Python (no strict formatter enforced)
- **Commit format:** Conventional Commits preferred
- **Branch strategy:** Feature branches off main
- **Secrets management:** `.env` only — never commit secrets
- **Error handling:** AI modules MUST return `None` on failure — never raise
- **Git staging:** Stage explicit file paths only — `git add .` and `git add *` are FORBIDDEN

---

## Domain Context

**What this system does:**
Accepts YouTube URLs or local video files. Uses an AI Director to select the best segments. Renders them with FFmpeg as short-form vertical videos with platform-optimized subtitles, overlays, and audio. No cloud API required — fully offline desktop application.

**Key domain concepts:**

- **Job:** A render request tracked in `data/app.db`. Has stage and parts.
- **Stage:** Job-level status — `QUEUED → DOWNLOADING → RENDERING → DONE` (frozen)
- **Part:** Per-clip status — `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE` (frozen)
- **result_json:** Blob stored per job — must always contain `output_rank_score`, `is_best_output`, `is_best_clip`
- **NVENC:** NVIDIA GPU hardware encoder — has hardware session limit (3–5 concurrent max)
- **qa_pipeline:** Output validation gate — never bypass, never fake success
- **AI Director:** `ai_director.py` — 5,718 lines, selects and scores segments

**Business-critical paths (treat as HIGH risk by default):**
- Render pipeline execution (render_pipeline.py)
- Output validation (qa_pipeline.py)
- Job state management (data/app.db + job_manager.py)
- API contracts (routes/render.py, routes/jobs.py + WebSocket)

---

## Current Focus

**Goal:** Backend stability and correctness. Frontend is being rebuilt from scratch.

**Active work streams:**
- Agent OS migration (new CLAUDE.md complete, ai/rules/ cleanup in progress)
- Backend architecture documentation
- Known issues: mixed DB connection model, cache location bug (see CLAUDE.md)

**Known issues / tech debt to avoid touching:**
- `render_pipeline.py` — 5,816 lines monolith, touch only with full pytest + explicit approval
- `ai_director.py` — 5,718 lines, same caution level
- Mixed DB connection model in `db.py` / `jobs_repo.py` — do not worsen, dedicated fix needed
- `devtools.py` — unauthenticated shell route, never make easier to enable
- Frontend build pipeline gap — `vite.config.ts` builds to wrong path, pending frontend rebuild

---

## Routing Overrides

| Task Type | Agent | Notes |
|-----------|-------|-------|
| Any change to `render_pipeline.py` | architect → backend → reviewer → qa | Always — no exceptions |
| Any change to `ai_director.py` | architect → backend → reviewer → qa | Always — same as render_pipeline |
| Database schema change | architect + human confirm | Additive-only rule must be verified |
| API route path change | architect + human confirm | Frozen interface — check backward compat |
| WebSocket event shape change | architect + human confirm | All WS consumers must be updated simultaneously |

---

## Risk Overrides

> These override `rules/risk_matrix.md` for this project.

| Change Type | Risk Level | Reason |
|-------------|------------|--------|
| Any edit to `render_pipeline.py` | CRITICAL | 5,816-line monolith — all render stages, full pytest required |
| Any edit to `ai_director.py` | CRITICAL | 5,718-line monolith — same caution level |
| Any edit to `qa_pipeline.py` | CRITICAL | Output validation gate — bypass = corrupt renders delivered silently |
| Any edit to `data/app.db` directly | CRITICAL | Sole job state — corruption is permanent |
| Any edit to `motion_crop.py` | CRITICAL | 2,464-line OpenCV module |
| Removing any `result_json` alias | CRITICAL | Breaks UI backward compat — auto-reject |
| Any schema field removal or rename | HIGH | API consumers break silently |
| Any API route path change | HIGH | Electron + frontend consumers |
| Any WS event shape change | HIGH | UI progress tracking breaks |
| SQLite schema DROP or RENAME | CRITICAL | Irreversible in offline desktop |
| `devtools.py` changes | HIGH | Unauthenticated shell execution surface |
| `NVENC_MAX_SESSIONS` change | HIGH | GPU session exhaustion = all renders fail |
| AI module changes in `backend/app/ai/**` | HIGH | Import failure = FastAPI won't start |

---

## Agent Notes

**Backend:**
- Read `CLAUDE.md` before any render-touching change — it has the full Render Edit Protocol
- Use `Edit` tool (surgical diff) never `Write` tool for existing files
- Run `python -m py_compile app/<file>.py` after every Python change
- Run `python -m pytest` before declaring done on HIGH/CRITICAL changes
- Venv activation: `cd D:\tool-render-video\backend && .\.venv\Scripts\Activate.ps1`
- For `render_pipeline.py`: run full pytest BEFORE edit (record baseline), then AFTER (compare)

**Architect:**
- Read `docs/RENDER_PIPELINE.md` and `docs/ARCHITECTURE.md` before any render system design
- All new `RenderRequest` fields must default to `False` or disabled — document this in design
- Frozen interfaces (routes, WS shape, result_json aliases) must be preserved — design around them
- SQLite changes: additive-only design — no DROP, no RENAME

**Reviewer:**
- Read `CLAUDE.md` — it contains the complete auto-reject conditions and review checklist
- Auto-reject if: result_json aliases removed, API route changed, AI module raises, qa_pipeline bypassed
- Check: stage names frozen, part names frozen, WS shape preserved, HTTP polling still works

**QA:**
- Test framework: `python -m pytest` from `backend/` with venv activated
- Focused test: `python -m pytest tests/<relevant>.py -v --tb=short`
- Full suite required for CRITICAL/HIGH changes: `python -m pytest`
- Syntax check: `python -m py_compile app/<file>.py`

---

## Do Not Touch

- `data/app.db` — never delete, never direct SQL writes outside `backend/app/db/`
- `docs/review/**` — READ-ONLY audit ledger, append-only (create new files, never edit existing)
- `docs/archive/**` — READ-ONLY historical record
- `backend/static/` — legacy frontend, still served by default
- `.env` files — never stage or commit

---

## External Systems

| System | Purpose | Notes |
|--------|---------|-------|
| FFmpeg | Video encoding/decoding | Installed locally, path via `get_ffmpeg_bin()` helper |
| Whisper | Audio transcription | Optional AI dep — `requirements-ai.txt` |
| OpenCV | Subject tracking | `motion_crop.py` — 2,464 lines |
| yt-dlp | YouTube download | `routes/download.py` |
| Edge TTS | Voice narration | Optional |
| NVIDIA NVENC | GPU encoding | Session limit: 3–5 concurrent max |

---

## Contacts / Escalation

- **Architecture decisions:** thienhaicmu (project owner)
- **Business logic questions:** thienhaicmu
- **Security concerns:** thienhaicmu — especially for devtools.py
