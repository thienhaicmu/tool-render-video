# Phase 6.7 — Electron Cut-over + Static v2 Activation Report

**Status**: SHIPPED
**Date**: 2026-05-23
**Branch**: `restructure/output-timeline-architecture`

---

## 1. How to Build the v2 UI

```powershell
cd frontend
npx vite build
# Output: backend/static-new/index.html + backend/static-new/assets/*.js + *.css
```

Then promote to static-v2 (tracked by git):

```bash
# Remove old static-v2 if present
rm -rf backend/static-v2
# Copy build output
cp -r backend/static-new backend/static-v2
```

Note: `backend/static-new/` is in `.gitignore` (build artifact). `backend/static-v2/` is NOT in `.gitignore` and is tracked by git.

---

## 2. How to Launch (Legacy)

```powershell
# Electron desktop — legacy UI
.\run-desktop.ps1

# Backend only — legacy UI (browser testing)
.\run-backend.ps1
```

Both serve `backend/static/` (the original non-React UI) at `http://127.0.0.1:8000`.

---

## 3. How to Launch (v2 React UI)

```powershell
# Electron desktop — v2 React UI
.\run-desktop-v2.ps1

# Backend only — v2 React UI (browser testing)
.\run-backend-v2.ps1
```

Both set `STATIC_UI_VERSION=v2` before launching, which activates `backend/static-v2/`.

Alternative (manual env var in PowerShell):

```powershell
$env:STATIC_UI_VERSION = "v2"
cd desktop-shell
npm start
```

---

## 4. How STATIC_UI_VERSION Works

`backend/app/core/ui_gate.py` reads the `STATIC_UI_VERSION` env var at process startup:

| Value | Static directory served |
|---|---|
| `v2` + `backend/static-v2/` exists | `backend/static-v2/` |
| `v2` + `backend/static-v2/` missing | fallback to `backend/static/` (warning logged) |
| `legacy` | `backend/static/` |
| unset / empty | `backend/static/` |
| invalid value | `backend/static/` (warning logged) |

`backend/app/main.py` uses the returned directory to mount static files:
- `v2`: `app.mount("/assets", StaticFiles(directory=static_dir/assets))`
- `legacy`: `app.mount("/static", StaticFiles(directory=static_dir))`

The `GET /health` endpoint reports the active version: `{"status": "ok", "ui_version": "v2"}`.

---

## 5. Asset Path Strategy

Vite builds with default `base: '/'` (no explicit base in `vite.config.ts`), producing:

```
backend/static-v2/
  index.html          ← references /assets/index-HASH.js, /assets/index-HASH.css
  assets/
    index-HASH.js     ← main JS bundle
    index-HASH.css    ← main CSS bundle
    index-*.js/css    ← code-split chunks
```

`index.html` uses **absolute** paths (`/assets/index-HASH.js`), not relative (`./assets/`). This is correct for FastAPI's `/assets` mount which serves files relative to the URL root.

FastAPI `app.mount("/assets", StaticFiles(directory=static_dir/assets))` makes all files in `assets/` accessible at `/assets/*`. The code-split chunks (`index-*.js/css`) are also served correctly.

---

## 6. SPA Routing

The React app uses **panel-based routing** — no URL changes when switching panels (no React Router, no `window.location.pathname` changes). The only URL the browser navigates to is `/`, so no catch-all route is needed.

`@app.get("/")` in `main.py` is sufficient. A `/{path:path}` catch-all is not required and was not added.

Verified: no `useNavigate`, `BrowserRouter`, or `HashRouter` in any `.tsx` file.

---

## 7. Electron Environment Passthrough

`desktop-shell/main.js` function `startBackendWithCommand()` builds the environment:

```javascript
const env = {
  ...process.env,   // ← spreads Electron's full process environment
  APP_DATA_DIR: DATA_DIR,
  DATABASE_PATH: ...,
  // ...
}
```

`STATIC_UI_VERSION` set in the Electron process environment (e.g. by `run-desktop-v2.ps1`) is automatically included via `...process.env`. No code changes to `main.js` were needed.

---

## 8. CSP (Content Security Policy)

CSP was **not added** in Phase 6.7. Rationale:

- The app runs locally on `127.0.0.1` inside Electron — no remote content risks.
- Same-origin serving means all assets come from the same host; CSP buys little additional security in this threat model.
- Adding CSP requires auditing `unsafe-inline` usage for styles, `script-src` for chunks, and `connect-src` for WebSocket. This is non-trivial and deferred to a later hardening phase.
- Deferred to Phase 6.8+ or a dedicated hardening sprint.

---

## 9. Rollback

To immediately roll back to legacy UI:

**Option A: Unset the env var**
```powershell
# Remove env var (session only)
Remove-Item Env:\STATIC_UI_VERSION -ErrorAction SilentlyContinue
# Then launch normally
.\run-desktop.ps1   # or .\run-backend.ps1
```

**Option B: Force legacy even with env var**
```powershell
$env:STATIC_UI_VERSION = "legacy"
.\run-desktop.ps1
```

**Option C: Delete static-v2 (nuclear)**
```bash
rm -rf backend/static-v2
# ui_gate will fallback to legacy even if STATIC_UI_VERSION=v2
```

---

## 10. Electron Smoke Test Checklist

Use this checklist to verify v2 activation after deploying:

### Pre-smoke setup
- [ ] Build frontend: `cd frontend && npx vite build`
- [ ] Promote: `cp -r backend/static-new backend/static-v2`
- [ ] Confirm `backend/static-v2/index.html` exists

### Backend smoke (browser)
1. [ ] **Legacy**: `.\run-backend.ps1` → open `http://127.0.0.1:8000` → confirm legacy HTML UI loads
2. [ ] **V2**: `.\run-backend-v2.ps1` → open `http://127.0.0.1:8000` → confirm React UI loads (cinematic dark theme, sidebar, panels)
3. [ ] **Health check**: `GET /health` → `{"status": "ok", "ui_version": "v2"}`
4. [ ] **Assets served**: Browser network tab shows `/assets/index-*.js` returns 200

### UI feature smoke
5. [ ] **Render Setup**: Navigate to "New Render" — form loads with all dropdowns populated
6. [ ] **Form validation**: Leave required fields empty, submit — validation errors shown inline
7. [ ] **History**: Navigate to "History" — job list loads (may be empty)
8. [ ] **Job detail**: Click a job — drawer opens with job_id, status, progress, quality
9. [ ] **WebSocket**: Open a running job — progress bar updates in real time
10. [ ] **Quality panel**: Open a completed job — quality score + issue list visible (or empty state)
11. [ ] **Editor**: Open editor via "Open in Editor" on completed job — video preview loads
12. [ ] **Trim controls**: Adjust trim start/end — mm:ss display updates

### API path verification
13. [ ] **Same-origin**: All API calls in browser network tab use `/api/...` (no `http://127.0.0.1:8000`)
14. [ ] **WebSocket**: WS connection in network tab shows `ws://127.0.0.1:8000/api/jobs/{id}/ws`

### Electron desktop smoke
15. [ ] `.\run-desktop-v2.ps1` → Electron window opens → React UI loads (not blank screen)
16. [ ] No console errors in Electron DevTools

### Rollback verification
17. [ ] Unset `STATIC_UI_VERSION`, restart → legacy HTML UI returns

---

## 11. Files Created in Phase 6.7

| File | Purpose |
|---|---|
| `backend/static-v2/` | Promoted v2 React build (tracked by git) |
| `run-desktop-v2.ps1` | Launch Electron with STATIC_UI_VERSION=v2 |
| `run-backend-v2.ps1` | Launch FastAPI backend with STATIC_UI_VERSION=v2 |
| `backend/tests/test_ui_static_v2_gate.py` | Backend tests for ui_gate + static-v2 artifact |
| `frontend/tests/electron-cutover-readiness.test.ts` | Frontend tests for Electron readiness |
| `docs/ui/PHASE_6_7_ELECTRON_CUTOVER_REPORT.md` | This document |

---

## 12. Remaining Blockers

None for static serving. The v2 UI is fully activated.

Future phases:
- **Phase 6.8**: Apply Trim — submit trim range to backend for re-render
- **Phase 6.8**: Re-render Selection — re-render a specific clip segment
- **Phase 6.8**: Export Clip — export trimmed clip to output directory
- **Future**: CSP header for FastAPI index response
- **Future**: Resolve `tsc -b` errors in test files (`api.test.ts`, `vite.config.ts`)
- **Future**: Electron packager build test with static-v2 included via `extraResources`

---

## 13. Test Results

| Suite | Tests | Result |
|---|---|---|
| Frontend (all 22 files) | 399/399 | PASS |
| Backend targeted (test_ui_static_v2_gate.py) | 21/21 | PASS |
| Backend contract (test_ui_backend_contract.py) | 49/49 | PASS |
