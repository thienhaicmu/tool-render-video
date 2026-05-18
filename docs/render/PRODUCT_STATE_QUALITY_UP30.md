# PRODUCT STATE — QUALITY-UP30: Creator Review Queue

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(ui): creator review queue`
**Status:** Shipped

---

## Summary

Creator morning review workflow. Moves from "render done, creator hunts files" to a **review-first workflow** where every completed clip lands in a single, persistent queue — ready for a yes/no decision at any time.

**Creator experience:** "Every clip I render waits for me to decide what to keep. I don't lose work in the file system."

---

## Philosophy

- **NOT a media library.** Not a DAM. Not a timeline editor. A decision queue.
- **Local only.** LocalStorage. No server state, no sync, no cloud.
- **Review-first.** New clips land in "Ready to Review" immediately after render completes.
- **Manual choice always wins.** Keep/Favorite/Dismiss/Retry are irreversible creator intent — never auto-resolved by the system.
- **Gentle feedback only.** Keep/Favorite reinforces taste via existing EMA; Dismiss slightly weakens. No overfit.
- **Zero new dependencies.** Pure JS + existing CSS token system.
- **No regression.** Cancel / resume / retry / render queue / websocket / history all untouched.

---

## Parts

### Part A — Queue Model

| Property | Value |
|---|---|
| Storage | `localStorage['review_queue_v1']` |
| Max items | 200 (FIFO eviction) |
| States | `new` → `kept` / `favorited` / `dismissed` / `failed` |
| Persistence | Survives page reload, app restart |
| No duplicates | `jobId` deduplication on `addJob()` |

**State transitions:**
- `new` → `kept`: creator clicked K or Keep
- `new` → `favorited`: creator clicked F or Favorite
- `new` → `dismissed`: creator clicked D or Dismiss
- `new` → `failed`: render job failed (set at add time)
- `kept/favorited` → re-openable via Retry button on same job in history

### Part B — Review Actions

| Action | Shortcut | Effect |
|---|---|---|
| Keep | K | State → kept. Reinforces taste (rank 1). |
| Favorite | F (★) | State → favorited. Reinforces taste + variant. |
| Dismiss | D | State → dismissed. Weakens taste (rank 99). |
| Retry | R (↻) | Toast: "Switch to Render tab to retry." Log: `review_retry`. |
| Open Folder | 📁 | Calls `openStoredOutputPath(outputDir)`. |

All transitions complete under 2 seconds. State written to localStorage immediately.

### Part C — Morning Review View

New top-nav tab **"Review"** (after History). Full-width view, same layout as history.

**Sections (top to bottom):**
1. **Ready to Review** — largest, shows all `new` state clips. Empty state: "All caught up."
2. **Favorites** — amber accent header, `favorited` clips.
3. **Kept** — collapsed by default, `kept` clips. Click header to expand.
4. **Needs Retry** — red accent header, `failed` clips.

Dismissed clips not shown — intentionally hidden to reduce noise.

### Part D — Smart Sorting

Within each section:
1. Recovered clips (partial render) float to top (warning-first)
2. Newest first (`addedAt` descending)

### Part E — Trust Layer

Compact chips per clip from stored render payload:

| Chip | Source | Color |
|---|---|---|
| Preset name | `payload.preset_name` | Blue |
| Creator DNA | `payload.creator_dna.confident` | Purple |
| Structure bias | `payload.structure_bias` (if not "balanced") | Muted |
| Assets | `asset_logo_path` or `asset_intro_path` present | Green |
| Recovered | `opts.recovered = true` | Amber |

### Part F — Keyboard Shortcuts

Shortcuts fire on `keydown` within focused card. Blocked if focus is inside `INPUT/TEXTAREA/SELECT`.

| Key | Action |
|---|---|
| K | Keep |
| F | Favorite |
| D | Dismiss |
| R | Retry |

### Part G — Observability

| Log event | When |
|---|---|
| `review_kept: {name} ({jobId})` | Creator clicks Keep |
| `review_favorited: {name} ({jobId})` | Creator clicks Favorite |
| `review_dismissed: {name} ({jobId})` | Creator clicks Dismiss |
| `review_retry: {name} ({jobId})` | Creator clicks Retry |

All log events go through `addEvent()` if available — non-fatal if absent.

### Part H — Steering Feedback

| Creator action | Taste effect |
|---|---|
| Keep | `CreatorTaste.recordDownload(1)` |
| Favorite | `CreatorTaste.recordDownload(1)` + `CreatorFeedback.recordVariantDownload(variant)` |
| Dismiss | `CreatorTaste.recordDownload(99)` |
| Retry / Open / Dismissed | No feedback |

Never overwrites; EMA weight is gentle. All calls wrapped in `try/catch` — safe if modules absent.

---

## Files Changed

### New Files

| File | Purpose |
|---|---|
| `backend/static/js/review-queue.js` | `ReviewQueue` IIFE module — all queue logic |
| `backend/static/partials/review-view.html` | Review workspace HTML partial |

### Modified Files

| File | Change |
|---|---|
| `backend/static/index.html` | Added "Review" nav button with `#rqNavBadge`, `#partial_review_view` div, `review-queue.js` script tag |
| `backend/static/js/partials-loader.js` | Added `partial_review_view: '/static/partials/review-view.html'` |
| `backend/static/js/nav.js` | Added `isReview` flag, `view_review` toggle, `ReviewQueue.init()` + `renderView()` on open, `is-review-active` body class |
| `backend/static/js/batch-queue.js` | `_submitItem`: saves `item._payload = payload`; `_fetchJobStatus`: calls `ReviewQueue.addJob()` on `completed` and `completed_with_errors` |
| `backend/static/css/v3/review.css` | Appended full UP30 Review Queue CSS section |

---

## Integration Points

### How clips enter the queue

`batch-queue.js` → `_fetchJobStatus` → on `st === 'completed'` or `'completed_with_errors'`:
```javascript
ReviewQueue.addJob(item.jobId, item.name, item.outputDir, {
    recovered: hasRecovery,
    payload: item._payload || null,
});
```

`item._payload` is stored at submit time in `_submitItem` before the API call.

### How the view opens

`nav.js` → `setView('review')`:
```javascript
if (isReview && typeof ReviewQueue !== 'undefined') {
    ReviewQueue.init();
    ReviewQueue.renderView();
}
```

### Badge

`#rqNavBadge` (inside the Review nav button) is updated by `ReviewQueue._refreshBadge()` after every state change and on `init()`. Shown when `new` count > 0, hidden otherwise.

---

## What Was Intentionally NOT Built

| Not built | Reason |
|---|---|
| Server-side queue persistence | Local only. No server state needed. |
| Undo for dismiss | Creator intent — make the decision mean something. |
| Bulk select / bulk action | Creator overwhelm. One clip at a time. |
| Thumbnail generation API | Falls back gracefully to placeholder icon. |
| Auto-remove dismissed from storage | Dismissed items stay (just hidden) — prevents re-adds on page reload. |
| Sorting controls | Queue is implicit: recovered first, newest first. No UI clutter. |
| Search / filter | Out of scope. History view covers search. |

---

## Manual QA Checklist

### A — Queue populates on render complete
- [ ] Start a render job via batch queue or normal render
- [ ] Job completes (status = completed or completed_with_errors)
- [ ] Review nav badge appears with count = 1
- [ ] Click "Review" tab — clip card appears in "Ready to Review" section
- [ ] Card shows clip name, time, trust chips (if payload available)

### B — Keep action
- [ ] Click K or Keep button on a new card
- [ ] Toast: "Kept"
- [ ] Card moves to "Kept" section (or disappears from Ready if Kept is collapsed)
- [ ] Badge count decrements
- [ ] Log: `review_kept: {name}`

### C — Favorite action
- [ ] Click F or ★ button on a new card
- [ ] Toast: "Added to Favorites"
- [ ] Card appears in "Favorites" section
- [ ] Badge decrements
- [ ] Log: `review_favorited: {name}`

### D — Dismiss action
- [ ] Click D or Dismiss button
- [ ] Toast: "Dismissed"
- [ ] Card disappears from view (dismissed state hidden)
- [ ] Badge decrements
- [ ] Log: `review_dismissed: {name}`

### E — Retry action
- [ ] Click R or Retry button
- [ ] Toast: "Switch to the Render tab to retry"
- [ ] No state change, card remains
- [ ] Log: `review_retry: {name}`

### F — Open Folder
- [ ] Click 📁 button on a card that has outputDir
- [ ] File browser opens to render output folder
- [ ] No crash if outputDir missing

### G — Keyboard shortcuts
- [ ] Click a card to focus it (tabindex=0)
- [ ] Press K → Keep fires
- [ ] Press F → Favorite fires
- [ ] Press D → Dismiss fires
- [ ] Press R → Retry fires
- [ ] Shortcuts do NOT fire when cursor is in a text input

### H — Badge
- [ ] Badge shows new count immediately after render completes
- [ ] Badge hides when all new items are actioned
- [ ] Badge persists across page reload (re-reads localStorage)

### I — Sections collapse/expand
- [ ] Click "Kept" section header — expands kept clips
- [ ] Click again — collapses
- [ ] Collapse icon rotates on state change

### J — Recovery warning
- [ ] Render a clip that partially fails (some parts succeed)
- [ ] Card appears with "recovered" amber chip
- [ ] Card floats to top of its section

### K — Persistence across reload
- [ ] Render a clip, action some cards
- [ ] Reload the page, navigate to Review
- [ ] Queue state preserved exactly

### L — No regression
- [ ] Normal render flow works (cancel, retry, batch queue)
- [ ] History view loads normally
- [ ] Render output panel and clip cards unaffected
- [ ] No console errors from review-queue.js on pages without ReviewQueue

### M — Empty state
- [ ] Open Review with no items in queue
- [ ] "No clips in the review queue yet" message shown
- [ ] After all new items actioned: "All caught up" in Ready to Review section
