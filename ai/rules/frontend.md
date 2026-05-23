# Frontend Rules

## THREE States — Identify Before Touching Anything

| State | Path | Active when | Status |
|-------|------|-------------|--------|
| Legacy HTML app | `backend/static/` | Default — no `STATIC_UI_VERSION` env var | Protected by AGENTS.md |
| v2 React (served) | `backend/static-v2/` | `STATIC_UI_VERSION=v2` | Active in Electron + `run-backend-v2.ps1` |
| React source | `frontend/src/` | NEVER directly served | TypeScript source only |
| Build output | `backend/static-new/` | NEVER served | Gitignored — `ui_gate.py` ignores this path |

## Critical Gap (CURRENT.md Issue #1 — OPEN)

```
vite.config.ts → outDir: '../backend/static-new'   (gitignored, never served)
ui_gate.py     → serves 'backend/static-v2/'        (stale committed build)
```

**`npm run build` does NOT update the served UI.**
Running it produces output that `ui_gate.py` has no knowledge of.
Do NOT run `npm run build` to "update" the frontend until Phase B2 resolves this.

## Before Touching Any Frontend File

1. Check which state is currently served: `STATIC_UI_VERSION` env var or which run script is active
2. Read `CURRENT.md` — blockers may block frontend work entirely
3. Read `AGENTS.md` Protected Files section for legacy (`backend/static/`) protections

## Legacy App Rules (`backend/static/`)

- Preserve DOM IDs — JS uses them as selectors
- Preserve function names called by inline `onclick`
- Preserve hidden compatibility fields in `index.html`
- CSS entry: `backend/static/css/v3/app.css` — avoid broad rewrites
- `backend/static/css/app.css` is a legacy rollback file — not loaded in production

## v2 React App Rules (`backend/static-v2/`)

- Apply same minimal-patch discipline as backend changes
- Vite bundles are in `assets/` as hashed flat files (e.g., `index-A4p3dZbO.js`)
- No `js/screens/` subdirectory structure — that was an earlier era
- Changes here are committed manually (no build pipeline currently works)

## React Source Rules (`frontend/src/`)

- Changes here are invisible until Phase B2 is fixed AND a new build is committed to `static-v2/`
- Do not assume source changes reach users

## Never Do

- Assume changes in one state affect another
- Run `npm run build` expecting it to update the served UI
- Modify `ui_gate.py` or `vite.config.ts` without a Phase B2 approved plan
- Remove DOM IDs from `backend/static/index.html` without updating all JS call sites
