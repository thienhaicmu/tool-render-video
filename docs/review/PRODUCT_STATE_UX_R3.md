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

## Next Phase Direction

### UX-R3.1 — Relative strong tier
Replace absolute score-8 threshold with relative: top N non-best done clips (where N = min(3, floor(doneCount × 0.33))). Fixes the case where all clips score 5-7.

### UX-R3.2 — Sort-change tier refresh
Add `_applyUxR3Tiers()` call to `sortClipsView()` after DOM re-sort, so headers re-appear when switching back to score-sort.

### UX-R3.3 — Compare tool
Build a side-by-side compare view. UX-R3-H seeded the `.isSelected` infrastructure. Compare would:
1. Add explicit "Compare" toggle buttons to non-best cards
2. Show a split-view panel (2 center previews) when exactly 2 clips are selected
3. Provide direct export from compare view
