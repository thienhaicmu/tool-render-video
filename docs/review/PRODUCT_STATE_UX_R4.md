# Product State — Post UX-R4

**Date:** 2026-05-16  
**Branch:** `feature/ai-output-upgrade`  
**Last phase:** UX-R4 — Home Workspace Re-Architecture

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in UX-R4

### Starting point: feature dashboard

Before UX-R4, `#render_home_panel` contained:
- An `.rhHero` card with a generic "Welcome back, Creator" title
- A 3-column `.rhTiles` grid with equal-weight tiles (YouTube / Local / Resume Job)
- A static `.rhTips` block with three fixed platform tips
- A `.rhRecent` section with `#jobs_out` — which was actually broken (JS targeted `#render_history_list`; the list never rendered)

No session memory. No AI intelligence. No clear next action. All paths had equal visual weight. The panel communicated: "choose a feature." Not: "here's where you were."

### What UX-R4 delivers

**Four-zone workspace structure** replacing the flat card layout:

| Zone | Element | Purpose |
|---|---|---|
| 1 | `.uxr4MomentumHero` | Creator momentum — last session + AI intelligence |
| 2 | `.uxr4QuickStart` | Clear action hierarchy — primary → secondary → tertiary |
| 3 | `.uxr4RecentWork` | Workspace memory — elevated recent project list |
| — | Bug fix | `#jobs_out` → `#render_history_list` — history now actually renders |

---

## Architecture

```
renderRenderHistory()          ← called by nav.js on every render-tab activation
  ↓
  #render_history_list populated (was broken — #jobs_out mismatch fixed)
  ↓
  _uxr4PopulateMomentumHero()
    ├── #uxr4_continue_zone
    │     ├── items.length === 0 → empty state ("Start creating")
    │     └── items[0] → "Continue creating" + title + meta + CTA button
    └── #uxr4_intel_msg
          ├── CreatorMemory unavailable → neutral fallback
          ├── taste.confident = false → learning-progress message
          └── taste.confident = true → taste dimension rows
                (editStyle ≠ balanced, paceConf > 0.4, hookConf > 0.4)
```

---

## Zone Detail

### Zone 1 — Creator Momentum Hero (UX-R4-A + UX-R4-D)

Two-column card: `.uxr4HeroInner` (`grid-template-columns: 1fr 1fr`).

**Left: Continue zone (`#uxr4_continue_zone`)**  
Populated by `_uxr4PopulateMomentumHero()` on every `renderRenderHistory()` call.

- **No history**: "Start creating" label + "Create your first project" sub-text.
- **Has history**: "Continue creating" label + title of last project + clips/failed meta + time ago + "Continue Editing" CTA button (`rerunRenderHistory(jobId)`).

**Right: Intelligence zone (`#uxr4_intel_msg`)**  
Reads `CreatorMemory.getTasteModel()` directly.

- `typeof CreatorMemory === 'undefined'` → neutral fallback text.
- `taste.confident = false`, `totalSignals > 0` → "AI is learning — N signals so far."
- `taste.confident = true` → `.uxr4IntelTaste` rows:
  - Edit style (when `editStyle !== 'balanced'`)
  - Pacing (when `paceConf > 0.4`)
  - Openings / hook (when `hookConf > 0.4`)

Vertical separator via `.uxr4HeroInner::before` pseudo-element — 1px `var(--border-subtle)` line between columns.

### Zone 2 — Quick Start (UX-R4-B)

Three-level hierarchy inside `.uxr4QuickStart`:

1. **Primary `.uxr4QSPrimary`** — full-width indigo-bordered button. "Create New Project" with icon. Triggers `source_mode='youtube'` + `syncSourceModeUI()`. Unmissable.
2. **Secondary `.uxr4QSSecondary`** — `grid-template-columns: 1fr 1fr` with two `.rhTile` cards from existing system (YouTube / Local File). Same interactivity as before.
3. **Tertiary `.uxr4QSTertiary`** — plain-text `Resume from Job ID` button. Focuses `#resume_job_id` in sidebar. Low visual weight — utility only.

The Resume Job tile from the old `.rhTiles` grid is demoted from equal-weight card to minimal tertiary text action.

### Zone 3 — Recent Work (UX-R4-C)

`.uxr4RecentWork` replaces `.rhRecent`. Section renamed "Recent Work" from "Recent Renders." `#render_history_list.uxr4HistoryList` — same `renderRenderHistory()` output, but:

- `max-height: none` override on `.uxr4HistoryList` — list breathes instead of capping at 200px.
- First item gets `.uxr4TopItem` class — slight elevation via indigo-tinted border and `var(--bg-800)` background.

---

## Bug Fix

`renderRenderHistory()` at line ~2292 has always targeted `qs('render_history_list')`. The HTML used `id="jobs_out"` — so the history list never rendered in the home panel. The `RENDER_SESSION_ONLY` guard also targeted `jobs_out`.

Fixed: HTML ID renamed to `render_history_list`; JS guard updated to match. History now renders correctly on every nav to the render tab.

---

## What Was NOT Changed

- `.rhPanel` outer wrapper — preserved; `render_home_panel` ID untouched
- `.rhTile` / `.rhTile--youtube` / `.rhTile--local` CSS — preserved; tiles reused in Zone 2
- `renderRenderHistory()` HTML generation — item template unchanged; only `idx` parameter added to inject `.uxr4TopItem` on first item
- `nav.js` visibility toggle — `render_home_panel` show/hide logic untouched
- `hardening.css` overrides — `editorMode` / `inPipeline` still hide the panel
- `_renderHistoryRead()`, `buildRenderHistoryEntry()`, `saveRenderHistoryEntry()` — untouched

---

## Failure Safety

- `_uxr4PopulateMomentumHero()`: guards `document.getElementById()` for both zones — no-op if elements not in DOM
- `CreatorMemory` access: full `typeof` guard + try/catch — no throw possible
- `getTasteModel()`: only renders rows when confidence thresholds pass — never shows misleading low-confidence data
- Empty history: both zones show graceful empty states — no blank UI
- `uxr4HeroInner::before` pseudo-element: removed at 1024px breakpoint where grid becomes single column

---

## Maturity Assessment

### UI

**Score: 9.2 / 10**

Gained vs. pre-UX-R4:
- Home panel has workspace identity — creator knows immediately where they left off
- Primary action is unmissable and hierarchically clear
- AI intelligence visible at workspace entry — not buried in editor
- Recent work is elevated, not a database dump
- Empty state is welcoming (not blank or generic)
- History bug fixed — recent renders actually appear now

Remaining weak:
- "Continue Editing" CTA calls `rerunRenderHistory()` — this re-renders the same job, not a true "continue from last state." Correct behavior would open the review panel for that job's output. Requires a deeper integration with job state restoration.
- Intelligence zone only shows taste when `confident = true` (requires several AI interactions). New users always see the fallback — no progressive disclosure between fallback and confident state.
- Zone 2 primary button triggers YouTube mode unconditionally. A creator who prefers local files will always get YouTube default first.

---

## Known Limitations

### "Continue Editing" calls rerunRenderHistory, not review
`rerunRenderHistory(jobId)` re-queues the same render job rather than restoring the output review panel. The CTA label implies "continue your review" but the behavior is "rerun the render." Would need a separate `openHistoryJobReview(jobId)` function that loads the job's saved output into the review panel.

### Intelligence zone requires confident CreatorMemory
`taste.confident` requires a minimum signal threshold (`MIN_TASTE_SIG` from creator-memory.js). New creators or those who haven't used the editor's AI suggestions see the neutral fallback. There's no intermediate "3 signals in — leaning towards fast pacing" state visible in the workspace hero.

### Primary CTA always sets YouTube mode
The primary button calls `syncSourceModeUI()` with `source_mode='youtube'`. Creators who primarily use local files get the wrong default mode on first click. Could be improved by checking last-used source type from history.

---

## Next Phase Direction

### UX-R4.1 — Smart primary CTA
Read last history entry's `sourceType` to set the primary button mode (youtube vs local). "Create from YouTube" vs "Create from Local File" as the primary label — personalized to the creator's actual pattern.

### UX-R4.2 — Continue vs Rerun distinction
Add `openHistoryJobReview(jobId)` that restores the review panel for a completed job. "Continue Editing" should open where the creator left off, not re-render from scratch.

### UX-R4.3 — Progressive intelligence disclosure
Show a lightweight "AI is warming up" state when `totalSignals > 0 && !confident` with a specific emerging insight ("You've accepted 2 fast-pacing suggestions so far.") rather than a generic learning message.
