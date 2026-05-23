# CURRENT.md — Active Project State

**Last updated**: 2026-05-23 | **Branch**: `restructure/output-timeline-architecture`

## Current State

Phase 6.8 complete. Editing operations finalized. UI v2 cutover active (`STATIC_UI_VERSION=v2`).
Late stabilization — no large feature additions before RC.

## Active Runtime

| System | State |
|--------|-------|
| Default UI | `backend/static/` — legacy HTML (no env var needed) |
| v2 UI | `backend/static-v2/` — React chunks (`STATIC_UI_VERSION=v2`) |
| Electron | `run-desktop-v2.ps1` — sets `STATIC_UI_VERSION=v2` automatically |
| Database | `data/app.db` — SQLite WAL, sole job state authority |
| Backend | FastAPI + Uvicorn, port 8000, single process |

## Known Critical Issues

**Issue 1 — Frontend build disconnect** *(resolved in Phase B4)*
`vite.config.ts` `outDir` aligned to `backend/static-v2/`. `emptyOutDir: true` added.
`npm run build` (or `npx vite build`) now produces output that `ui_gate.py` serves.
Orphan chunks removed. Runtime proof completed. React frontend development unblocked.

**Issue 2 — AGENTS.md frontend section stale** *(resolved in Phase B1)*
AGENTS.md Protected Files section updated. v2 UI in `backend/static-v2/` now documented.

**Issue 3 — Permission accumulation** *(resolved in Phase A3)*
`.claude/settings.local.json` rebuilt to 27 safe entries. Local-only, not versioned.

## What Must NOT Be Touched

- `backend/app/orchestration/render_pipeline.py` — unless fully planned + full pytest run
- `backend/app/ai/director/ai_director.py` — unless explicitly approved
- `backend/app/services/motion_crop.py` — unless explicitly approved
- `data/app.db` — NEVER delete or modify directly
- `docs/review/**` — READ-ONLY per AGENTS.md line 111
- `result_json` aliases: `output_rank_score`, `is_best_output`, `is_best_clip`

## Safe Working Areas

- New documentation files (zero runtime impact)
- `backend/app/routes/` non-render routes (voice, channels, files, creator)
- `backend/app/services/` non-critical services (not render_engine, subtitle_engine, motion_crop)

## Completed Phases (this branch)

- **Phase A3** ✓ — Settings.local.json rebuilt (27 entries, local-only)
- **Phase B1** ✓ — Agent team foundation: `.claude/agents/` + `ai/rules/` + `ai/skills/` + `ai/workflows/`
- **Phase B2** ✓ — Commercial product blueprint (analysis-only, no file changes)
- **Phase B2.5** ✓ — Design direction lock (philosophy, nav, workspace, component priority)
- **Phase B3** ✓ — Design system spec: `docs/design/tokens.css`, `components.md`, `screens-tier1.md`, `motion.md`
- **Phase B3.5** ✓ — Refined specs (3-track timeline, minimal Source screen, single-pane Results v1)
- **Phase B4** ✓ — Build pipeline aligned: `vite.config.ts` → `backend/static-v2/`, orphan chunks cleaned
- **Phase B5.0** ✓ — Frontend foundation: spec tokens, motion system, app shell, sidebar nav, 7 primitive components

## Next Planned Phases

- **Phase B5.1**: Tier-1 screen implementation (Source, Studio, Monitor, Results) using B5.0 foundation
- **Phase C1**: Archive historical phase docs, documentation cleanup

## Known TS Issue (non-blocking)
`frontend/tests/editor-operations.test.tsx` has 3 unused import warnings that cause `npm run build` (which runs `tsc -b`) to fail. Use `npx vite build` for production builds until fixed. Does not affect runtime.
