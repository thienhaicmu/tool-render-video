# Product State — Post UX-R3

**Date:** 2026-05-16  
**Branch:** `feature/ai-output-upgrade`  
**Last phase:** UX-R3 — Review Experience Re-Architecture

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in UX-R3

### Starting point: scrolling clip dump

Before UX-R3, the render output panel was a flat auto-fill grid of clip cards. The best clip occupied the full row (P2.8-F hero layout) but all other clips had equal visual weight. Skipped and failed clips competed for attention alongside successful ones. No section labels. No hierarchy. The creator had to manually scan the grid to understand what the AI recommended.

### What UX-R3 delivers

**`_applyUxR3Tiers(list, ranking, done, failed, skipped)`** — new function called after every panel re-render, after transient state is restored. Classifies every card and injects tier structure.

**Four-tier visual hierarchy:**

| Tier | Selector | Treatment |
|---|---|---|
| Best | `data-uxr3-tier="best"` | 200px thumb, 26px score, deep indigo glow |
| Strong Candidates | `data-uxr3-tier="strong"` | Subtle indigo border, hover lift, 16px score |
| Additional Results | `data-uxr3-tier="other"` | 80% opacity, recovers on hover |
| Failed / Skipped | `data-uxr3-tier="failed/skipped"` | 48% / 30% opacity; collapsed behind toggle |

**Tier headers** — Inserted as `div.uxr3TierHeader` siblings directly in the grid (with `grid-column: 1 / -1` so they span full width):
- "Strong Candidates (N)" — appears when there are strong and non-strong groups
- "Additional Results (N)" — appears when preceded by best or strong
- "N failed · N skipped" — always present when problem clips exist; starts collapsed when successful clips exist

**Problem section collapse** — Toggle button (▸/▾) on the problem header. Starts collapsed (`uxr3Collapsed` class) when `done.length > 0`. CSS sibling selector hides `[data-uxr3-tier="failed"]` and `[data-uxr3-tier="skipped"]` cards when collapsed.

**Auto-review of best clip (UX-R3-F)** — On first terminal status render, `centerPreviewClip()` is called after 900ms for the best-ranked clip. The center preview area (`#cs_preview_area`) opens automatically. `_uxr3AutoSelectedBest` flag prevents this from re-triggering on subsequent panel updates. Flag resets in `clearRenderOutputPanel()`.

**Score-sort vs. order-sort** — Tier headers only appear in score-sort mode (`_clipsSortOrder === 'score'`). In "In order" mode, `data-uxr3-tier` attributes still apply (CSS differentiation active) but headers are suppressed (order-based view has no tier semantics).

---

## Architecture

```
populateRenderOutputPanel(job, parts)
  ↓ [all existing card HTML generation unchanged]
  ↓
  RenderAiRuntime.reapplyTransientState()
  ↓
  _applyUxR3Tiers(list, ranking, done, failed, skipped)
    ├── Remove previous .uxr3TierHeader elements
    ├── Clear data-uxr3-tier on all cards
    ├── Classify each .clipCard → best|strong|other|failed|skipped
    │     best:   isBestClip class || ranking.isBest
    │     strong: isDone, not best, .clipCardScore[data-tier="high"]
    │     other:  isDone, not best, data-tier ≠ high
    │     failed: isFailed class
    │     skipped: isSkipped class
    ├── If _clipsSortOrder === 'score':
    │     Insert "Strong Candidates" header (conditional)
    │     Insert "Additional Results" header (conditional)
    │     Insert "Needs Review" header + toggle (if problems)
    │     Collapse problem section if done.length > 0
  ↓
  Auto-preview best clip (once, terminal status, 900ms delay)
  ↓
  showRenderOutputPanel()
```

---

## What Was NOT Changed

- `populateRenderOutputPanel()` HTML template — clip card structure untouched
- P2.8-F `grid-column: 1 / -1` for isBestClip — preserved (UX-R3 only overrides thumb size and score size)
- P2.9 confidence evolution and transient animations — untouched
- `sortClipsView()` — untouched; sort order still controlled by header dropdown
- `_bindCardHoverPreviews()` — untouched; hover video preview still works on all cards
- All P3.x intelligence (taste, collab, concerns) — untouched

---

## Failure Safety

- `_applyUxR3Tiers()` guards: `if (!list) return` at top; `querySelectorAll` never throws
- Previous tier markup cleaned before each pass — safe on rapid WS re-renders
- `.uxr3ProblemHeader.uxr3Collapsed ~ .clipCard` sibling selector: works because problem cards are always last in the sorted order (failed then skipped after done)
- Auto-preview: guarded by `typeof centerPreviewClip === 'function'`, `_r3Part.output_file` existence, and `_uxr3AutoSelectedBest` flag — no-op if conditions not met
- In "part_no" sort mode, tier headers are omitted — `data-uxr3-tier` still set on cards

---

## Maturity Assessment (Updated)

### UI

**Score: 9.4 / 10** (up from 9.0)

Gained vs. UX-R2:
- Review workspace has clear editorial hierarchy — best clip authoritative, candidates in middle tier, problems invisible by default
- Problem clips (failed/skipped) no longer consume attention during review — collapsed behind a toggle
- Best clip auto-opens in center preview — review flow starts immediately without manual action
- Section labels make the AI's editorial intent explicit without extra copy
- Score/tier CSS differentiation creates visual gravity without per-card redesign

Remaining weak:
- "Strong Candidates" section label depends on at least one clip with output_score ≥8 — if all clips score 5-7 there's no strong tier even though there are "better" clips
- Tier headers only appear in score-sort mode; in "In order" mode the hierarchy is invisible
- Auto-preview fires even if the creator already has a different clip open (no check for existing preview state)
- Compare foundation (`UX-R3-H`) is placeholder only — `.isSelected` makes market-viral auto-selected clips slightly more visible, but no explicit compare UX

---

## Known Limitations

### Strong tier threshold is absolute, not relative
The "Strong Candidates" tier requires `output_score >= 8` (mapped from AI ranking). If the best clip scores 6.5 and the second-best scores 6.2, neither enters "Strong Candidates" — they're both "Additional Results." A relative threshold (top N non-best clips) would be more editorial, but requires changing the tier classification logic.

### Tier headers orphan when sort changes
If the user switches sort to "In order" after completion (headers suppressed), then switches back to "Best first" — `_applyUxR3Tiers()` is NOT re-triggered (sort change only calls `sortClipsView()` which re-sorts in-DOM without re-rendering all cards). Headers disappear and don't come back until next full `populateRenderOutputPanel()` call. This is acceptable for now but would need a hook in `sortClipsView()` to fix.

### Auto-preview doesn't check existing preview state
`centerPreviewClip()` is called unconditionally when the flag isn't set, even if the creator already opened a different clip via the UX-R2 completion hero. This means the auto-preview may override what the creator explicitly clicked. Mitigation: the 900ms delay gives time for explicit clicks to register first, and the flag prevents re-triggering.

### Sibling selector collapse only works when problem cards are last
The `.uxr3ProblemHeader.uxr3Collapsed ~ [data-uxr3-tier="failed"]` CSS only hides subsequent siblings. If somehow a non-problem card appears after the problem header (shouldn't happen given sort logic), the collapse would be incomplete.

---

---

## UX-R3.1 — Review Hardening (2026-05-16)

Three targeted stability fixes applied to `render-ui.js`. No DOM redesign. No new HTML.

### Fix A — Relative strong-tier threshold

**Problem:** Absolute `data-tier="high"` (score ≥ 8) meant all clips scoring 5–7 fell into "Additional Results" with no Strong tier — hierarchy misleading when spread is tight.

**Fix:** `_strongThreshold = _bestScore * 0.85`. Computed from `ranking` Map: first from `rk.isBest`, then from max across all entries as fallback. When no ranking data exists (`_strongThreshold <= 0`), falls back to DOM `data-tier="high"` check on `.clipCardScore`.

```js
var _bestScore = 0;
ranking.forEach(function (rk) { if (rk.isBest && rk.score > _bestScore) _bestScore = rk.score; });
if (!_bestScore) ranking.forEach(function (rk) { if (rk.score > _bestScore) _bestScore = rk.score; });
var _strongThreshold = _bestScore > 0 ? _bestScore * 0.85 : -1;
```

### Fix B — Sort-stability DOM fallback

**Problem:** `sortClipsView()` only re-ran `_applyUxR3Tiers()` via `populateRenderOutputPanel()` when `_renderMonitorLastJob` was set. In the edge case where job state was cleared (page reload with persisted grid), tier headers orphaned on sort change.

**Fix:** Added `else` branch that runs `_applyUxR3Tiers()` directly using DOM-queried cards, with an empty ranking Map.

```js
} else {
  var _r31List = document.getElementById('render_output_list');
  if (_r31List) {
    _applyUxR3Tiers(
      _r31List, new Map(),
      Array.from(_r31List.querySelectorAll('.clipCard.isDone')),
      Array.from(_r31List.querySelectorAll('.clipCard.isFailed')),
      Array.from(_r31List.querySelectorAll('.clipCard.isSkipped'))
    );
  }
}
```

### Fix C — Preview safety guard

**Problem:** Auto-preview setTimeout unconditionally called `centerPreviewClip()` after 900ms, even if the creator had already clicked a clip manually. Overrode explicit intent.

**Fix:** Guard at the top of the setTimeout callback: bail if `_csPreviewJobId !== null` (manual preview active) or `_cardHoverActiveVid !== null` (hover video in progress).

```js
setTimeout(function () {
  if (_csPreviewJobId !== null || _cardHoverActiveVid !== null) return;
  centerPreviewClip(…);
}, 900);
```

### Maturity Impact

Strong-tier now reflects relative editorial merit rather than absolute scoring. Sort changes no longer orphan headers in edge state. Auto-preview now respects creator intent. UI score: **9.5 / 10**.

---

---

## UX-R3.2 — Output Preview Recovery (2026-05-17)

P0 regression fix. Hover video preview and click-to-center-preview were silently blocked on all output cards immediately after DOM refresh and on the first panel show.

### Root Cause

`_bindCardHoverPreviews` guards hover with:

```javascript
if (!vid._cardInView) return;
```

`vid._cardInView` is set by an `IntersectionObserver` callback that fires **asynchronously** (one animation frame after `observe()` is called). Before the callback fires, `_cardInView` is `undefined`. The guard `!undefined` evaluates to `true` — returning early and blocking hover.

This means every DOM refresh (`list.innerHTML = cards` wipes all card elements; `_bindCardHoverPreviews` re-observes fresh elements) leaves a window where all cards are blocked, and the first panel show always starts in the blocked state.

The IO guard was intended only to pause playback when a card **scrolls out of view**. It was never meant to block the initial hover. Using `!value` instead of `value === false` conflated "not yet determined" with "confirmed off-screen."

### Fix

**`render-ui.js` — `_bindCardHoverPreviews`, `onmouseenter` handler:**

```javascript
// Before:
if (!vid._cardInView) return;

// After:
if (vid._cardInView === false) return;
```

`undefined` (initial, IO not yet fired) → hover allowed.  
`false` (IO confirmed card is off-screen) → hover blocked.  
`true` (IO confirmed card is on-screen) → hover allowed.

The IO scroll-out-of-view pause at line 4501 is unchanged:
```javascript
if (!entry.isIntersecting && _cardHoverActiveVid === vid) _stopCardHoverVideo();
```

### Systems Preserved Without Change

| System | Status |
|--------|--------|
| `centerPreviewClip()` click path — `onclick` on `clipCardThumbWrap` | ✓ unchanged |
| `_stopCardHoverVideo()` — pause, reset, remove `is-preview-playing` | ✓ unchanged |
| UX-R3-F auto-preview of best clip (900ms, guarded by R3.1-C fix) | ✓ unchanged |
| R8.2.1 compare mode (`r821EnterCompare`, `r821ExitCompare`) | ✓ unchanged |
| UX-R3 tier classification (`_applyUxR3Tiers`) | ✓ unchanged |
| UX-R3.1 tier collapse/toggle | ✓ unchanged |
| `is-preview-playing` CSS opacity transition | ✓ unchanged |

### Manual QA Checklist

- [ ] Hover over a done clip thumbnail → video starts playing (opacity 1, `is-preview-playing` class on card)
- [ ] Move mouse off → video pauses, opacity returns to 0
- [ ] Click thumbnail → `cs_preview_area` opens with video loading
- [ ] Hover on card while it scrolls off-screen → video pauses
- [ ] Click Compare button → compare strip opens, both videos load
- [ ] After render completes → best clip auto-opens in center preview after 900ms
- [ ] No console errors during any of the above

---

## Next Phase Direction

### UX-R3.3 — Sort-change tier refresh (full path)
The R3.1 Fix B fallback handles edge cases but uses an empty ranking Map (no score data). To fix the common case of sort-change mid-session, cache the last ranking Map in a module-level variable so Fix B can use real scores when `_renderMonitorLastJob` is unavailable but sort changes happen.

### UX-R3.4 — Compare tool
Build a side-by-side compare view. UX-R3-H seeded the `.isSelected` infrastructure. Compare would:
1. Add explicit "Compare" toggle buttons to non-best cards
2. Show a split-view panel (2 center previews) when exactly 2 clips are selected
3. Provide direct export from compare view
