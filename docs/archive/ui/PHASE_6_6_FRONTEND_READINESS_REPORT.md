# Phase 6.6 — Frontend Integration Polish + Shell Readiness Report

**Date**: 2026-05-23
**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED

---

## 1. E2E UI Flow Audit

All four navigation panels verified end-to-end:

| Flow | Status |
|---|---|
| Render form → submit → redirects to History | Confirmed (test: render-submit.test.tsx) |
| History → click job → opens detail drawer | Confirmed (test: history-screen.test.tsx) |
| Detail drawer → "Open in Editor" → switches to Editor panel | Confirmed (test: job-detail-open-editor.test.tsx) |
| Editor panel → empty state → "Go to History" → switches to History | Confirmed (test: editor-screen.test.tsx) |
| Delete job while drawer open → drawer closes | Confirmed (HistoryScreen.handleDelete checks selectedJobId) |

---

## 2. Navigation Polish Summary

- **Sidebar**: All 4 nav items (Render, History, Editor, Settings) present with correct labels. Active item has `aria-current="page"` and `--color-accent-muted` background. No stale labels from prior phases.
- **Topbar**: Now shows panel-aware title via `PANEL_TITLES` map: `render→"New Render"`, `history→"History"`, `editor→"Editor"`, `settings→"Settings"`. Static "Render Studio" title removed.
- **Notifications**: Fixed-position at `bottom: var(--space-6); right: var(--space-6)`. `z-index: var(--z-toast)` = 300, above drawer (z-raised=10) and modal (z-modal=200). No overlap issues.
- **EditorEmptyState**: "Go to History" correctly calls `setActivePanel('history')`.

---

## 3. BASE_URL Fix

**File**: `frontend/src/api/client.ts`

**Before**: `export const BASE_URL = 'http://127.0.0.1:8000'`

**After**:
```typescript
export const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''
```

**Behavior**:
- Production (Electron loads `http://127.0.0.1:8000` from FastAPI): `VITE_API_BASE_URL` is unset → `BASE_URL = ''` → all `/api/...` calls become same-origin relative URLs. Correct.
- Development (Vite dev server with proxy): `VITE_API_BASE_URL` is unset → `BASE_URL = ''` → Vite proxy intercepts `/api/*` and `/media/*` → forwards to `127.0.0.1:8000`. Correct.
- Custom setup: Set `VITE_API_BASE_URL=http://my-backend:8000` in `.env.local`. Correct.

**Also added**: `frontend/src/vite-env.d.ts` with `/// <reference types="vite/client" />` — this was missing, causing TypeScript to not recognize `import.meta.env`. Now resolved.

---

## 4. WebSocket URL Fix

**File**: `frontend/src/websocket/RenderSocketClient.ts`

**Before**: `const WS_BASE = BASE_URL.replace(/^http/, 'ws')`
- When `BASE_URL = ''`, this produces `''` which is not a valid WebSocket URL.

**After**:
```typescript
function computeWsBase(): string {
  if (BASE_URL) {
    return BASE_URL.replace(/^http/, 'ws')
  }
  if (typeof window !== 'undefined') {
    return window.location.origin.replace(/^http/, 'ws')
  }
  return 'ws://127.0.0.1:8000'
}
const WS_BASE = computeWsBase()
```

**Behavior**:
- Electron/production: `BASE_URL = ''` → `window.location.origin = 'http://127.0.0.1:8000'` → `WS_BASE = 'ws://127.0.0.1:8000'`. Correct.
- Tests/SSR (no `window`): falls back to `'ws://127.0.0.1:8000'`. Correct.
- Custom `VITE_API_BASE_URL`: replaces `http` with `ws` in the custom URL. Correct.

---

## 5. Build Artifact Policy (static-new in .gitignore)

**Root `.gitignore`**: `backend/static-new/` already present — confirmed.

**`frontend/.gitignore`**: Added `*.tsbuildinfo` (was missing).

**Rationale**: `backend/static-new/` is generated build output. Electron packaging uses FastAPI serving `backend/static/` (or `backend/static-v2/` when `STATIC_UI_VERSION=v2`). Build artifacts are not source and must not be committed.

---

## 6. Static-new Readiness

### Build output (`backend/static-new/index.html`):
```html
<script type="module" crossorigin src="/assets/index-2J0zQlaj.js"></script>
<link rel="stylesheet" crossorigin href="/assets/index-CA7gLLj0.css">
```

**Findings**:
- Asset paths use `/assets/…` (absolute root-relative). Correct for FastAPI serving at `http://127.0.0.1:8000` — the `/assets` StaticFiles mount handles these.
- No `127.0.0.1` URLs baked into the HTML. API calls happen at runtime via `BASE_URL = ''` (same-origin).
- No `./assets/…` relative paths needed because Electron loads via `http://127.0.0.1:8000`, not `file://`.
- Vite `base` defaults to `/` — correct for this setup.

---

## 7. Electron Shell Readiness

### 7.1 How Electron Loads the UI

`desktop-shell/main.js` line 8:
```javascript
const BACKEND_URL = 'http://127.0.0.1:8000';
```
Electron spawns the FastAPI backend process, waits for health check at `/health`, then calls `mainWindow.loadURL('http://127.0.0.1:8000')`. The frontend is served by FastAPI as a static site over HTTP — not via `file://`.

### 7.2 FastAPI Static Mount

`backend/app/main.py` uses `resolve_static_directory()` from `backend/app/core/ui_gate.py`:

```python
STATIC_DIR, _UI_VERSION = resolve_static_directory(BACKEND_ROOT)

if _UI_VERSION == "v2":
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="static_assets")
else:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
```

`ui_gate.py` resolves:
- `STATIC_UI_VERSION=v2` → serves `backend/static-v2/`
- `STATIC_UI_VERSION=legacy` or unset → serves `backend/static/` (legacy UI)

### 7.3 Cut-over Plan (to activate static-new as v2)

Step-by-step to switch the new React UI live:

1. **Build** the new frontend:
   ```powershell
   cd frontend && npm run build
   ```
   Output lands in `backend/static-new/`.

2. **Rename** directories:
   ```powershell
   Rename-Item backend/static-new backend/static-v2
   ```
   (Keep `backend/static/` as the legacy fallback.)

3. **Activate** the new UI by setting the env var before starting FastAPI:
   ```powershell
   $env:STATIC_UI_VERSION = "v2"
   uvicorn app.main:app --port 8000
   ```
   Or in `.env` file: `STATIC_UI_VERSION=v2`

4. **Verify**: `GET /health` returns `{"status": "ok", "ui_version": "v2"}`.

5. **Rollback** (instant): unset `STATIC_UI_VERSION` or set to `legacy` → FastAPI reverts to `backend/static/`.

**No Electron shell change required** — Electron always loads `http://127.0.0.1:8000`. FastAPI decides what HTML to serve.

### 7.4 CSP Restrictions

No Content-Security-Policy header is set in `main.js` or `main.py`. No Electron `webPreferences.contentSecurityPolicy` is configured. The Electron `BrowserWindow` uses default permissive CSP for a localhost HTTP origin.

**Recommendation for Phase 6.7**: Add CSP header in FastAPI for the index route: `Content-Security-Policy: default-src 'self'; script-src 'self'; connect-src 'self' ws://127.0.0.1:8000`

### 7.5 WebSocket Compatibility

Electron loads `http://127.0.0.1:8000` → `window.location.origin = 'http://127.0.0.1:8000'` → `computeWsBase()` returns `'ws://127.0.0.1:8000'`. WebSocket connects to the same host/port as FastAPI. No cross-origin issues. No CORS configuration needed for WebSocket in this setup.

---

## 8. Remaining Blockers Before Cut-over

| # | Blocker | Severity | Notes |
|---|---|---|---|
| 1 | `backend/static-v2/` directory does not exist yet | **REQUIRED** | Run `npm run build` then rename `static-new` → `static-v2` |
| 2 | `STATIC_UI_VERSION=v2` not set in any launch config | **REQUIRED** | Must be set before FastAPI starts; add to `.env` or `start.bat` |
| 3 | Legacy UI at `backend/static/` has no feature parity for new editor/quality UI | **INFO** | Not a blocker — legacy can coexist |
| 4 | No CSP header | **LOW** | Security hardening; not blocking |
| 5 | `tsc -b` pre-existing errors in test files | **INFO** | `api.test.ts` (fs/path imports), `vite.config.ts` test key — pre-existing, do not block functionality |

---

## 9. Phase 6.7 Checklist

- [ ] Rename `backend/static-new/` → `backend/static-v2/` as part of first production deploy
- [ ] Set `STATIC_UI_VERSION=v2` in deployment environment
- [ ] Add CSP header to FastAPI index response
- [ ] Wire Electron `main.js` to optionally set `STATIC_UI_VERSION` env var before spawning backend
- [ ] Smoke-test full E2E in Electron: render submit → history → editor preview
- [ ] Add CI step: `npm run build` on PR to catch build regressions early
- [ ] Resolve `tsc -b` errors in `api.test.ts` (add `@types/node`) and `vite.config.ts` (separate vitest config file)
