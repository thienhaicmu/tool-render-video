# PRODUCT STATE — QUALITY-UP32: Creator Workspace

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(ui): creator workspace`
**Status:** Shipped

---

## Summary

Workflow consolidation phase. Moves from multiple disconnected screens to a single creator workspace as the default landing.

The workspace shows four sections at a glance: today's render status, a series continuation card (when series is active), quick create, and a favorites gallery. All data is read from localStorage — zero API calls on open, instant render.

**Creator experience:** "I open the app and immediately know what's going on."

---

## Philosophy

- **Single creator context, not project management.** One view that surfaces the most useful state without mode-switching overhead.
- **Instant.** All workspace data from localStorage (review_queue_v1, creator_series_v1). No API calls on open.
- **No forced workflow.** Workspace is a starting point, not a gatekeeper. Creators can click through to any screen.
- **Advisory only.** Series continuation nudge is a button, not a preset override.
- **Nav simplification.** Four items: Home / Create / Review / Batch.
- **No new dependencies.** Reads existing localStorage schemas directly. No new module coupling.

---

## What Was NOT Built

| Not built | Reason |
|---|---|
| Cloud dashboard / sync | Local only. Same philosophy as UP12–UP31. |
| Project management | No folders, no tagging. Workspace is a soft surface. |
| Auto-fill from workspace | Creator choice always wins. Workspace is advisory. |
| Statistics / analytics panel | Out of scope. Status strip is enough. |
| Batch queue as separate nav view | BatchQueue is embedded in the Create panel — extraction would break the workflow. |
| History in primary nav | History accessible via workspace status area; removed from top nav to reduce clutter. |

---

## Architecture

### Storage sources (read-only in workspace)

| Key | Source | Used for |
|---|---|---|
| `review_queue_v1` | `ReviewQueue` module | Today count, new count, favorites |
| `creator_series_v1` | `CreatorSeries` module | Series fingerprint for status chip + Continue Series card |

Workspace reads both keys directly — does not call module functions to avoid init-order coupling.

---

## Sections

### A — Today Status Strip

Horizontal chip row at the top of the workspace. Shows:

| Chip | Condition | Style |
|---|---|---|
| `X rendered today` | ≥ 1 render in last 24h | Muted grey |
| `X to review` | ≥ 1 item in STATE.NEW | Blue (clickable → Review tab) |
| `Series: {prefix}` or `Series style` | `fingerprint.series_detected && confidence >= 0.35` | Cyan |

Empty state: "No renders yet today — ready when you are."

### B — Continue Series Card

Appears when `fingerprint.series_detected === true && confidence >= 0.35`.

Shows:
- Card title: "Continue Series"
- Card sub: "Series style active · {pct}% confidence"
- Series name: `"podcast ep"` (title_prefix) or `"Your series"`
- Metadata chips: preset_id + platform
- Button: "Continue" → `setView('render')`
- Log: `workspace_continue_series`, `workspace_action: continue_series`

Card is absent when series confidence is below detect gate.

### C — Quick Create Card

Always shown. Minimal CTA to start rendering.

Shows:
- Card title: "Quick Create"
- Active preset label (via `CreatorPresets.getActive()?.label` — optional, graceful if absent)
- Button: "New Clip" → `setView('render')`
- Log: `workspace_action: quick_create`

### D — Favorites Gallery

Full-width card spanning the grid. Shows up to 12 favorited clips from `review_queue_v1`.

Each card: thumbnail (9:16 aspect, graceful fallback), name, relative timestamp. Clicking navigates to Review tab.

Empty state: "Mark clips as Favorite in Review to see them here."

---

## Nav Simplification

| Before | After |
|---|---|
| Render | Create (same `data-view="render"`, label changed) |
| Download | Batch (same `data-view="download"`, label changed) |
| History | Removed from top nav |
| Review | Review (unchanged) |
| — | Home (new, `data-view="workspace"`, default) |

History is still accessible via the History view (`setView('history')`) but not in the primary nav.

---

## Files Changed

### New Files

| File | Purpose |
|---|---|
| `backend/static/js/workspace.js` | `CreatorWorkspace` IIFE — workspace data + render |
| `backend/static/partials/workspace-view.html` | Workspace view shell partial |

### Modified Files

| File | Change |
|---|---|
| `backend/static/css/v3/review.css` | UP31 chip styles added (v3ChipSeries, v3TrustSeries, cpSeriesHint) + full UP32 workspace CSS |
| `backend/static/index.html` | Nav: Home/Create/Review/Batch; `partial_workspace_view` div; `workspace.js` script tag |
| `backend/static/js/partials-loader.js` | `partial_workspace_view` → `workspace-view.html` mapping |
| `backend/static/js/nav.js` | `isWorkspace` routing: view toggle, body class, `CreatorWorkspace.init()` call |
| `backend/static/js/init.js` | Default landing: `setView('workspace')` instead of `setView('render')` |

---

## Observability

| Log event | When | Note |
|---|---|---|
| `workspace_opened` | Every time workspace view becomes active | On `CreatorWorkspace.init()` |
| `workspace_action: continue_series` | Creator clicks Continue on series card | |
| `workspace_action: quick_create` | Creator clicks New Clip | |
| `workspace_action: review_click` | Creator clicks a favorites card | |
| `workspace_continue_series` | Same as continue_series action | |
| `workspace_review_click` | Same as review_click action | |

---

## Manual QA Checklist

### A — Default landing is workspace

- [ ] Open app fresh (no cached view state)
- [ ] Default view is "Home" (workspace) — nav Home button active
- [ ] Workspace loads immediately with no spinner or delay
- [ ] No console errors

### B — Status strip accuracy

- [ ] No renders today: strip shows "No renders yet today" empty state
- [ ] 1+ renders today: strip shows "X rendered today" grey chip
- [ ] 1+ items in STATE.NEW: strip shows "X to review" blue chip; clicking navigates to Review tab
- [ ] Series active (confidence ≥ 35%): cyan "Series: {prefix}" or "Series style" chip appears

### C — Continue Series card

- [ ] Series NOT active: card is absent — no empty placeholder
- [ ] Series active: card shows series name, confidence pct, preset + platform metas
- [ ] "Continue" button → navigates to Create tab; log: `workspace_continue_series`
- [ ] Card is absent when confidence drops below 35% (e.g. after clearing localStorage)

### D — Quick Create card

- [ ] Always visible
- [ ] Preset hint shows when `CreatorPresets.getActive()` returns a label
- [ ] Preset hint absent when no active preset — card still renders cleanly
- [ ] "New Clip" button → navigates to Create tab; log: `workspace_action: quick_create`

### E — Favorites gallery

- [ ] No favorites: empty state "Mark clips as Favorite in Review to see them here."
- [ ] 1+ favorites: thumbnails shown in grid (9:16 aspect ratio)
- [ ] Thumbnail load error: graceful fallback (▶ icon placeholder)
- [ ] Clicking a card → navigates to Review tab; log: `workspace_review_click`
- [ ] Max 12 cards shown (most recent first)

### F — Nav simplification

- [ ] Top nav shows: Home / Create / Review / Batch (4 items)
- [ ] "History" is NOT in top nav
- [ ] "Create" button → setView('render') works as before
- [ ] "Batch" button → setView('download') works as before
- [ ] Active nav button highlights correctly for each view

### G — No regressions

- [ ] Create (render) view fully functional — all form fields, editor, batch queue
- [ ] Review tab works — keep/favorite/dismiss/retry all function
- [ ] Batch (download) tab works — URL paste and download queue
- [ ] History accessible via `setView('history')` (even if not in primary nav)
- [ ] Series chip/hint in editor panel still appears when series active
- [ ] Trust bar chips in output panel unaffected
- [ ] No console errors in any view

### H — Instant performance

- [ ] Workspace renders in < 50ms (pure localStorage read, no network)
- [ ] Switching between Home and Create: no flicker, no loading spinner
- [ ] Returning to Home after render completes: workspace refreshes with new data
