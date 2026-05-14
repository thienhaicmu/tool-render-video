# UI Rebuild Audit — Static-V2 Product Shell Foundation

**Phase:** UI-R2A  
**Date:** 2026-05-14  
**Branch:** feature/ai-output-upgrade  
**Scope:** New vanilla-JS product shell under `backend/static-v2/`

---

## 1. Summary

A complete UI rebuild was delivered under `backend/static-v2/` — a zero-dependency, no-build-step vanilla JavaScript ES module application. The legacy `backend/static/` directory is untouched. No changes were made to `backend/app/main.py`.

The new shell implements 4 product screens (Source, Studio, Monitor, Results) with a 4-panel grid layout, design-token–driven theming, WebSocket + polling transport, single entity normalizers, a reactive store factory, and all specified components (StatusChip, AIBadge, NavRail, EmptyState).

---

## 2. File Inventory

### Entry Point
| File | Purpose |
|---|---|
| `index.html` | HTML entry point; loads 4 CSS + app.js module |
| `package.json` | `{"type":"module"}` — enables `node --check` on ES module files |

### CSS (4 files)
| File | Contents |
|---|---|
| `assets/css/tokens.css` | All design tokens as CSS custom properties (colors, spacing, radius, typography, layout vars) |
| `assets/css/base.css` | Box-model reset, body defaults, scrollbar styling, typography utility classes, focus ring |
| `assets/css/layout.css` | 4-panel shell grid, screen/panel/strip wrappers, flex helpers |
| `assets/css/components.css` | StatusChip (8 states), AIBadge (6 states), NavRail items, EmptyState, Btn, Card, FormField, ProgressBar, Spinner, Toast, PartItem, MetricGrid |

### JS Infrastructure (4 files)
| File | Purpose |
|---|---|
| `assets/js/app.js` | Boot: mounts shell, inits systemStore, inits router |
| `assets/js/router.js` | Hash-based router: `#/source`, `#/studio`, `#/monitor/:jobId`, `#/results/:jobId` |
| `assets/js/transport.js` | `openJobStream()` — WebSocket primary, polling fallback; `fetchJson()` — typed HTTP client |
| `assets/js/desktop-adapter.js` | Electron `contextBridge` adapter — no-op in browser context |

### API Wrappers (3 files)
| File | Endpoints covered |
|---|---|
| `assets/js/api/render.js` | POST /api/render, POST /cancel, GET/PUT /api/render/draft, GET platforms/creator-types |
| `assets/js/api/jobs.js` | GET list, GET job, GET parts, GET result, GET summary, DELETE job |
| `assets/js/api/system.js` | GET /api/health, GET /api/system/info, GET /api/system/execution-mode, GET /api/sessions |

### Entity Normalizers (4 files)
| File | Entities normalized |
|---|---|
| `assets/js/entities/job.js` | `normalizeJob()` — raw job → typed Job with status validation |
| `assets/js/entities/part.js` | `normalizePart()`, `normalizePartList()` — raw part → typed Part with status + aiState validation |
| `assets/js/entities/result-package.js` | `parseResultPackage()` — raw result → ResultPackage with inline parts array + summary |
| `assets/js/entities/source-session.js` | `normalizeSession()`, `normalizeSessionList()` — raw session → SourceSession |

### Stores (6 files)
| File | State managed |
|---|---|
| `assets/js/store/create-store.js` | `createStore(initialState)` factory — `set`, `update`, `subscribe`, `reset` |
| `assets/js/store/session.js` | `sessions[]`, `activeSessionId`, `loading`, `error` |
| `assets/js/store/draft.js` | Render config form state — `draft`, `dirty`, `saving`, `error` |
| `assets/js/store/monitor.js` | Live job stream — `job`, `parts`, `summary`, `connected`, `error` |
| `assets/js/store/results.js` | Completed result package — `result`, `selectedPartIndex`, `loading`, `error` |
| `assets/js/store/system.js` | Backend health, execution mode, `backendReady` flag |

### Components (5 files)
| File | Component |
|---|---|
| `assets/js/components/status-chip.js` | `statusChip(status)` HTML string + `statusChipElement()` DOM node |
| `assets/js/components/ai-badge.js` | `aiBadge(state)` HTML string + `aiBadgeElement()` DOM node |
| `assets/js/components/nav-rail.js` | `navRail.mount(container)` + `navRail.setActive(id)` — 4 enabled + 4 disabled items |
| `assets/js/components/empty-state.js` | `emptyState({ icon, title, body, ctaLabel, onCta })` + `ICONS` map |
| `assets/js/components/shell.js` | `shell.render()` + `shell.mount(root)` + `shell.setActiveNav(id)` |

### Screens (4 files)
| File | Screen | Route |
|---|---|---|
| `assets/js/screens/source.js` | Source — file drop zone + session list | `#/source` |
| `assets/js/screens/studio.js` | Studio — render config form, launch button | `#/studio` |
| `assets/js/screens/monitor.js` | Monitor — live part list via WebSocket stream | `#/monitor/:jobId` |
| `assets/js/screens/results.js` | Results — result package metrics + per-part detail | `#/results/:jobId` |

**Total: 33 files**

---

## 3. Design Token Coverage

All tokens from `design/figma-import/design_tokens_v1.json` mapped to CSS custom properties:

| Token category | Count | CSS prefix |
|---|---|---|
| Colors (bg, surface, border, text, accent, ai) | 11 | `--color-*` |
| Status semantics | 6 | `--color-{status}` |
| Spacing | 10 | `--sp-{n}` |
| Radius | 3 | `--radius-*` |
| Typography | 5 | `--text-*`, `--font-family` |
| Layout | 3 | `--nav-rail-width`, `--right-panel-width`, `--bottom-strip-height` |

---

## 4. Layout Architecture

```
┌─────────────────────────────────────────────────────┐
│  .shell  (grid: 72px | 1fr | 300px / 1fr | 52px)   │
├──────────┬────────────────────────────┬─────────────┤
│          │                            │             │
│ .shell   │    .shell__workspace       │ .shell      │
│ __nav    │    (screen injected here)  │ __panel     │
│ (72px)   │                            │ (300px)     │
│          │                            │             │
├──────────┴────────────────────────────┴─────────────┤
│            .shell__strip (52px)                      │
└─────────────────────────────────────────────────────┘
```

---

## 5. Component State Matrix

### StatusChip (8 states)
| State | Color | Background |
|---|---|---|
| queued | `--color-text-muted` | rgba(170,180,190,0.12) |
| running | `--color-running` | rgba(121,184,255,0.12) |
| completed | `--color-success` | rgba(116,212,143,0.12) |
| partial | `--color-partial` | rgba(241,154,91,0.12) |
| failed | `--color-failed` | rgba(255,124,124,0.12) |
| interrupted | `--color-warning` | rgba(242,198,110,0.12) |
| unsupported | `--color-unsupported` | rgba(133,129,142,0.12) |
| unavailable | `--color-text-faint` | rgba(115,127,137,0.12) |

### AIBadge (6 states)
| State | Color | Background |
|---|---|---|
| disabled | `--color-text-faint` | rgba(115,127,137,0.10) |
| advisory | `--color-ai` | `--color-ai-soft` |
| applied | `--color-accent` | `--color-accent-soft` |
| skipped | `--color-text-muted` | rgba(170,180,190,0.10) |
| blocked | `--color-warning` | rgba(242,198,110,0.10) |
| unavailable | `--color-text-faint` | rgba(115,127,137,0.10) |

---

## 6. Transport Contract

```
WebSocket primary:   ws(s)://host/api/jobs/{jobId}/ws
  message shape:     { job: {...}, parts: [...], summary: {...} }

Polling fallback:    GET /api/jobs/{jobId}
                     GET /api/jobs/{jobId}/parts
  interval:          3000ms
  triggers:          on WS error, on WS close
```

---

## 7. Router Contract

| Hash path | Screen | Params |
|---|---|---|
| `#/source` | sourceScreen | — |
| `#/studio` | studioScreen | — |
| `#/monitor/:jobId` | monitorScreen | `[jobId]` |
| `#/results/:jobId` | resultsScreen | `[jobId]` |
| (any unmatched) | redirect → `#/source` | — |

---

## 8. Constraints Verified

| Constraint | Status |
|---|---|
| No framework (React/Vue/Svelte) | ✅ Vanilla JS only |
| No npm build step / bundler | ✅ Native ES modules, no build |
| No edits to `backend/app/main.py` | ✅ Not touched |
| No edits to `backend/static/` | ✅ Not touched |
| `{"type":"module"}` in package.json | ✅ Present |
| All design tokens from tokens V1 used | ✅ Full coverage in tokens.css |
| 4-panel grid layout (72px/1fr/300px + 52px strip) | ✅ Implemented in layout.css + shell.js |
| WebSocket primary + polling fallback | ✅ transport.js |
| Single entity normalizer pattern | ✅ entities/ directory |
| createStore factory (no external state library) | ✅ store/create-store.js |
| 8-state StatusChip | ✅ |
| 6-state AIBadge | ✅ |
| 4 enabled + 4 disabled NavRail items | ✅ nav-rail.js |
| 4 screen skeletons | ✅ source, studio, monitor, results |

---

## 9. Known Limitations (UI-R2A Scope)

- Right panel (`#shell-panel`) only shows part detail from Results screen; other screens leave it at default "Select a job" copy — context wiring is a UI-R2B task.
- No toast notification system wired to stores yet — CSS is present, JS implementation deferred.
- No drag-and-drop from browser `<input type=file>` — Source screen relies on Electron `pickVideoFile()` for path resolution; browser drag-and-drop uses `file.name` as fallback (path only available in Electron).
- Studio screen does not include subtitle/camera/segment advanced fields — basic platform/creator/mode/AI toggle only.
- No offline/error boundary at the shell level — individual screens handle their own error states.
