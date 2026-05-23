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

**Issue 1 — Frontend build disconnect** *(open — Phase B2)*
`vite.config.ts` builds to `backend/static-new/` (gitignored). `ui_gate.py` serves from
`backend/static-v2/`. Running `npm run build` produces output that is never served.
`backend/static-v2/` has an older build placed manually. **Do not resume React frontend
development until Phase B2 resolves this.**

**Issue 2 — AGENTS.md frontend section stale** *(open — Phase B1)*
AGENTS.md Protected Files describes `backend/static/js/render-ui.js`, `render-engine.js`,
`nav.js`. The active v2 UI in `backend/static-v2/` has no AGENTS.md protection. Documentation
gap, not a runtime failure. **Phase B1 will update AGENTS.md.**

**Issue 3 — Permission accumulation** *(open — Phase A3)*
`.claude/settings.local.json` has 200+ entries including `git add *`, `git commit *`,
`git checkout *` wildcards and `Remove-Item` for production files.
**Phase A3 will rebuild permissions using `/fewer-permission-prompts`.**

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

## Next Planned Phases

- **Phase A3**: Rebuild `.claude/settings.local.json` — remove dangerous wildcards
- **Phase B1**: Update AGENTS.md frontend section for three-state reality
- **Phase B2**: Fix frontend build pipeline disconnect
- **Phase C1**: Archive historical phase docs, documentation cleanup
