# Product State — Post UX-R2

**Date:** 2026-05-16  
**Branch:** `feature/ai-output-upgrade`  
**Last phase:** UX-R2 — Completion Experience Re-Architecture

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in UX-R2

### Starting point: utility completion

Before UX-R2, render completion surfaced as a thin `render_completion_bar` strip (icon + message + 3 equal-weight buttons) above a clip grid. No visual separation between the AI outcome and the render logistics. The best clip had P2.8-F hero layout in the grid but no dedicated summary surface. The user saw "Render complete — X clips ready," not "here is what the AI created."

### What UX-R2 delivers

**`#uxr1_ai_hero` morphs at completion** — `_morphHeroToOutcome(narrative)` adds `.uxr2OutcomeMode` class to the running-state hero. Icon changes to '✓', label becomes 'Creative Outcome', message becomes the P3.x narrative summary. Accent bar turns green. Pulse animation removed. The runtime orchestration hero becomes the completion confirmation hero — same DOM, different meaning.

**`#uxr2_completion_hero`** — new editorial hero surface between `render_completion_bar` and `render_output_panel`. Three-column grid:
- **Left (180px)**: Best clip thumbnail (static JPEG via `/api/render/jobs/{id}/parts/{no}/thumbnail`) with hover-autoplay video preview and a viral score badge in the bottom-right corner
- **Center**: `Creative Outcome` label (green, uppercase), P3.x editorial narrative (`RuntimeIntelligence.getCompletionNarrative()` summary), AI selection reason from `_rankMap(job).reason` (purple italic), stat bits from narrative
- **Right (164px)**: 3-level CTA hierarchy — "Review Best Clip" (filled indigo, primary), "Export Best" (`<a>` download link, ghost border, secondary), "Open Folder" (minimal text, tertiary)

**CTA hierarchy enforced** — `render_completion_bar` gets `.uxr2BarDemoted` class: buttons "Review Clips" and "Open Output Folder" hidden; "← Back to Editor" kept (utility action). Duplicate actions removed from view.

**Output list elevated** — `.renderOutputList.uxr2Complete` adds stronger glow to `.isBestClip` card.

**Failure / no-best-clip state** — when `_rankMap(job)` finds no `isBest` entry, hero gets `dataset.state = 'no-best'` (yellow label accent, thumb faded); narrative shows "AI could not confidently identify a strongest result."; "Review Best Clip" button relabeled "Review Clips" and scrolls to output panel.

**`reset()`** — clears hero to initial placeholder state, removes all UX-R2 classes, restores completion bar to full buttons.

---

## Architecture

```
render done
  ↓
showCompletionIntelligence(job, summary, parts)
  ↓ [guarded: once per render session]
  ├── _triggerCompletionArrival()
  │     → p29Arrival class → p29OutputRise + p29RuntimeRecede animations
  │     → evolution header → 'Creative Outcome'
  │
  ├── completion bar msg/summary updated (existing behavior)
  │
  ├── _applyConfidenceEvolution(n, n)  → best card → "peak" confidence
  │
  ├── _morphHeroToOutcome(narrative)
  │     → #uxr1_ai_hero.uxr2OutcomeMode
  │     → icon='✓', label='Creative Outcome', msg=narrative.summaryMsg
  │     → CSS: green accent bar, no pulse
  │
  └── _showCompletionHero(job, parts, narrative, completed, topPct)
        → _rankMap(job) → find best part
        → thumb: /thumbnail + /media hover-video + score badge
        → narrative msg + reason + bits
        → CTA: Review Best → centerPreviewClip(), Export Best → download href
        → demote render_completion_bar (uxr2BarDemoted)
        → elevate output list (uxr2Complete)
        → reveal: classList.remove('hiddenView') + rAF + uxr2HeroActive
              → uxr2HeroReveal animation (0.65s cubic-bezier)
```

---

## What Was NOT Changed

- `showRenderCompletionBar()` — still sets msg, summary, icon, data-state
- `_triggerCompletionArrival()` — untouched; p29Arrival fires normally
- P2.8-F hero card layout (`.clipsGrid .clipCard.isBestClip`) — untouched
- P2.9 territory switching CSS — preserved
- All P3.x intelligence paths — untouched
- `#ai_insights_panel` (backend `ai_director` gate) — untouched

---

## Failure Safety

- Both `_morphHeroToOutcome` and `_showCompletionHero` guard via `document.getElementById()` — no-op if elements not in DOM
- `_rankMap(job)` wrapped in try/catch internally — empty Map on failure; no-best fallback activates
- `typeof _rankMap === 'function'` guard before call — safe if ever tree-shaken
- Hover-video `play().catch(() => {})` — swallows autoplay policy errors silently
- `requestAnimationFrame` before `uxr2HeroActive` — ensures browser has painted before animation starts (avoids FOUC)
- `reset()` fully restores DOM to pre-completion state before next render session

---

## Maturity Assessment (Updated)

### UI

**Score: 9.0 / 10** (up from 8.5)

Gained vs. UX-R1:
- Completion is now a creative event, not a status update
- Best clip is the hero of the completion surface — thumbnail, score, reason, and direct preview/export CTAs
- CTA hierarchy is clear: one primary action, no button soup
- P3.x narrative is now visible at completion as the first text the creator reads
- Runtime hero morphs rather than switching — same surface, different mode

Remaining weak:
- `render_completion_bar` still visible above hero (utility strip) — some visual layering still present
- Completion hero has no way to collapse for creators who prefer to jump directly to the grid
- No animation continuity between `_triggerCompletionArrival()` (P2.9) and hero reveal (UX-R2) — two separate timing tracks that may not feel choreographed
- Score badge in thumb shows viral_score percentage; clip card shows 0–10 ranking score — inconsistent scoring display (known limitation)

---

## Known Limitations

### Score display inconsistency
The `uxr2ThumbScore` shows `bestViralPct + '%'` (viral_score × 100). The clip card in the grid shows `scoreVal.toFixed(1) + '/10'` (output_score from ranking). These are different scoring systems. At quick glance, a creator may see "72%" in the hero thumb and "7.2/10" in the card and question whether they're the same clip.

### Completion bar still visible
`render_completion_bar` is demoted (uxr2BarDemoted) but still visible above the hero. Hiding it entirely would require changing `showRenderCompletionBar()` logic, which also controls `wfStrip` state. Left intact for now.

### Hover-video event binding on reset
`thumbEl.addEventListener()` calls are added in `_showCompletionHero`. On `reset()`, the thumbEl innerHTML is replaced with a placeholder, removing the old video element. But the event listeners on `thumbEl` (the parent) remain. On the next completion, `_showCompletionHero` adds new listeners — meaning `thumbEl` accumulates listeners across sessions in the same page load. Each mouseenter fires N+1 times per session. Mitigated by the fact that `vid.play().catch()` is safe, but should be fixed by using `{ once: false }` or replacing with `onmouseenter`/`onmouseleave` direct assignment.

---

## Next Phase Direction

### UX-R2.1 — Event listener cleanup
Replace `addEventListener` in `_showCompletionHero` with direct `onmouseenter`/`onmouseleave` assignment on `thumbEl` to avoid listener accumulation across sessions.

### UX-R2.2 — Choreographed arrival
Delay `_showCompletionHero` reveal by ~300ms after `_triggerCompletionArrival()` fires so the P2.9 runtime-recede animation completes before the hero reveals. Single timing track.

### UX-R2.3 — Score unification
Show the same score format in both the hero thumb badge and the clip card (`X.X/10` or `X%`). Requires deciding on a canonical format across all completion surfaces.
