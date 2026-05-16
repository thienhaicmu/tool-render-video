# Product State — Post UX-R1

**Date:** 2026-05-16  
**Branch:** `feature/ai-output-upgrade`  
**Last phase:** UX-R1 — Runtime Center Stage Re-Architecture

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in UX-R1

### Starting point: render monitor

Before UX-R1, the render active panel led with `rdCard` — a progress badge, title, segment bar, and percentage. The AI orchestration surface (P3.x concerns, stage reasoning) lived inside `#render_runtime_mount`, below the fold, inside the bottom panel. Creators watched a render status card, not an AI experience.

### What UX-R1 delivers

**`#uxr1_ai_hero`** (`index.html`) — new `div` inserted directly before `#rd_card` in `#render_active_panel`. Always-visible during render. Not inside `#render_runtime_mount`, so unaffected by P2.9-B territory switching.

**Hero structure:**
- `.uxr1HeroStage` — icon + label + message; populated live from `_STAGES[idx]` as backend stage advances
- `#uxr1_concerns` — P3.x concerns from `RuntimeIntelligence.getConcerns(parts)`; updated each `update()` tick with hash dedup

**`_updateHero(idx, isFailed, parts)`** (`render-ui.js`) — new function in `RenderAiRuntime`:
- Reads `_STAGES[idx]` to populate icon/label/msg; sets `dataset.stage` / `dataset.failed`
- Calls `RuntimeIntelligence.getConcerns()` and renders concern items only when content hash changes
- Called from `update()` after `_renderConcernItems(parts)`

**`_lastHeroConcernHash`** — dedup variable preventing DOM churn on rapid WS ticks

**Hero reset in `reset()`** — restores `_STAGES[0]` defaults on new render start

**rdCard demotion** (`runtime.css`) — `#render_active_panel > .rdCard` overrides P2.8 padding to compact form (9px 18px 8px). Lower contrast background. P2.8 `::before` glow suppressed during running. `p28CardComplete` animation suppressed.

**Log strip recede** — `.rcLogStrip` at 60% opacity during `[data-render-state="running"]`. P2.8 doesn't target this element's overall opacity, so no conflict.

**Completion hero fade** — `.uxr1AiHero` fades to 80% opacity at completion — acknowledges the render is over while keeping the summary visible.

**Responsive** — two breakpoints: 1366px (label 16px, reduced padding) and 1024px (label 14px, body text 11.5px).

---

## Architecture

```
Plane 1 — AI Hero     #uxr1_ai_hero
  ├── .uxr1HeroStage  icon + stage label + stage message  (from _STAGES[idx])
  └── #uxr1_concerns  P3.x concern items                 (from RuntimeIntelligence.getConcerns)

Plane 2 — Status      .rdCard (demoted strip)
  ├── .rdCardHead     badge + title + log button
  ├── .rdStep         active stage title
  ├── .rdSegBar       segment progress bar
  └── .rdMeta         percentage + meta text

Plane 3 — Queue       .rcQueuePanel (unchanged)
  ├── #rc_ai_process_cards
  ├── #rc_ai_evolution_feed
  └── #rc_part_cards

Plane 4 — Logs        .rcLogStrip (receded to 60% during running)
```

**Data flow:**

```
WS tick → RenderAiRuntime.update(backendStage, status, parts)
  ↓
_updateHero(newIdx, isFailed, parts)
  ├── _STAGES[idx] → hero icon/label/msg
  └── RuntimeIntelligence.getConcerns(parts)
        ├── EditorConsensus.resolve(signals)     [P3.6]
        │     └── CreatorMemory.getCollabProfile()  [P3.7 collab note]
        └── → concern items rendered in #uxr1_concerns
```

---

## What Was NOT Changed

- `#render_runtime_mount` mounting logic — untouched
- P2.9-B territory switching (`..[data-render-state="complete"] #render_runtime_mount { opacity: 0.38 }`) — preserved
- `RenderAiRuntime.mountPanels()`, `_updateProcessCard()`, `_updateEvolutionFeed()` — untouched
- `#ai_insights_panel` (backend `ai_director.enabled` gate) — untouched
- All P2.x / P3.x CSS rules — untouched; UX-R1 CSS appended last and wins only on rdCard specificity

Per the brief: no DOM destruction, no compatibility break, no giant rewrite.

---

## Failure Safety

- `document.getElementById('uxr1_ai_hero')` guard at top of `_updateHero()` — no-op if hero not in DOM
- `_lastHeroConcernHash` dedup — prevents unnecessary DOM writes on rapid ticks
- `typeof RuntimeIntelligence !== 'undefined'` guard — falls back to empty concerns array
- `_STAGES[0]` fallback in `reset()` — literal strings if stages array somehow empty
- Hero is `flex-shrink: 0` — won't collapse in constrained flex layouts

---

## Maturity Assessment (Updated)

### UI

**Score: 8.5 / 10** (up from 7.5)

Gained vs. P3.7:
- AI orchestration now holds the primary visual position during render
- P3.x intelligence (consensus, collab history) surfaces in the hero, above the fold, on every tick
- rdCard correctly demoted to secondary status strip — no longer hero
- Spatial planes clearly separated: AI hero → status → queue → logs

Remaining weak:
- Hero stage label/msg are the same English as `rcAiProcCard` — two surfaces now show the same text in different styles (acceptable for now; P3.x differentiation will diverge them over time)
- `#uxr1_concerns` and `#rc_ai_evolution_list` both call `RuntimeIntelligence.getConcerns(parts)` independently — two separate calls per tick (deduped via hashing, but could be a single shared result)
- Completion state could do more — hero currently just fades; no summary or handoff message

---

## Known Limitations

### Duplicate `getConcerns()` call
`_updateHero()` and `_renderConcernItems()` both call `RuntimeIntelligence.getConcerns(parts)` on each `update()` tick. Both deduplicate via hash, so DOM writes are minimal. The underlying concern computation runs twice. A shared resolved concern array could eliminate this.

### Hero hidden before first `update()`
`#uxr1_ai_hero` is always in the DOM and visible from page load. Before `update()` is first called, it shows the static HTML defaults ("Reading the Room"). CSS could hide it until `[data-stage]` is set, but this would require JS to set the attribute before the first meaningful stage. Not yet implemented.

### No dismiss or collapse
The hero has no user control to collapse it. For long renders, creators have no way to shrink the hero zone to see more of the queue below.

---

## Next Phase Direction

### UX-R1.1 — Hero Pre-Render State
Hide `#uxr1_ai_hero` before render starts (no `[data-stage]` set); reveal via CSS when first stage arrives. Eliminates the static default visible on page load.

### UX-R1.2 — Completion Intelligence Panel
At `[data-render-state="complete"]`, expand the hero with a completion summary using `RuntimeIntelligence.getCompletionNarrative()` — currently only used by `showCompletionIntelligence()` in the bottom panel.

### UX-R2 — Review Screen Co-Pilot
Apply the same spatial-plane architecture to the review screen — promote the editor conversation above the output card list during active editing sessions.
