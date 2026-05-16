# Runtime Orchestration — Frontend Intelligence Layer

**Codebase:** `backend/static/` (production app shell)
**Branch:** `feature/ai-output-upgrade`
**Last updated:** 2026-05-16 (post-P2.9.1)
**Scope:** `render-ui.js`, `runtime.css`, `review.css`

> This document covers only the runtime intelligence system introduced in P2.5–P2.9.
> It does not cover the `backend/static-v2/` shell (see `frontend_ui_audit.md`).

---

## DOM Hierarchy (production)

```
#render_active_panel[data-render-state="running|complete|failed"]
  ├── .rdCard#rd_card                       — Creative Director headline
  ├── #ai_insights_panel                    — hidden; not runtime-orchestrated
  ├── #render_completion_bar                — editorial outcome summary (complete only)
  ├── #render_output_panel.renderOutputPanel
  │     └── #render_output_list.clipsGrid
  │           └── .clipCard[data-part-no][data-clip-status][data-p29-confidence?]
  └── #render_runtime_mount                 — filled by mountRenderRuntimePanel()
        ├── .abpToolbar                     — 48px status bar
        └── #rc_bottom
              └── .rcAQMain
                    ├── .rcQueuePanel (62%)
                    │     ├── #rc_active_card           — Infrastructure surface
                    │     ├── #rc_ai_process_cards      — AI Worker surface (P2.5)
                    │     ├── #rc_ai_evolution_feed     — Clip Intelligence feed (P2.5)
                    │     └── #rc_part_cards            — raw part grid
                    └── .rcLogStrip (38%)
                          ├── #rc_ai_reason_feed        — AI Reasoning stream (P2.5)
                          └── #event_log_render         — raw event log
```

---

## P2.5 — Runtime Intelligence

**Date:** pre-2026-05-14  
**Files:** `render-ui.js` (lines 4240–4529), `runtime.css` (P2.6 section)

### What exists

#### `RenderAiRuntime` IIFE (render-ui.js:4240)

A self-contained IIFE that manages the AI orchestration surface. Public API:
```js
{ mountPanels, update, reset, showCompletionIntelligence }
```

**`mountPanels()`**
Called once by `mountRenderRuntimePanel()`. Creates three elements if absent:
- `#rc_ai_process_cards.rcAiProcessCards` — inserted before `#rc_part_cards`
- `#rc_ai_evolution_feed.rcAiEvolutionFeed` — inserted before `#rc_part_cards`
- `#rc_ai_reason_feed.rcAiReasonFeed` — inserted before `#event_log_render` in the log strip

**`update(backendStage, status, parts)`**
Called on every WebSocket tick from `updateRenderMainState()`. Drives:
- `_updateProcessCard(idx, isFailed)` — renders the active AI process card
- `_updateEvolutionFeed(parts)` — adds new completed clips to the evolution list
- Stage-to-index mapping via `_stageIdx(backendStage)`

**`showCompletionIntelligence(job, summary, parts)`**
Called once on terminal completion from `updateRenderMainState()`. Computes avg/top viral scores from `parts[].viral_score` (0–1 float), renders `#rc_benchmark_insight` inside `#rc_benchmark_panel`.

**`reset()`**
Called by `resetRenderSessionUi()`. Clears all state flags, hides AI panels, empties lists, removes confidence data from best card.

#### AI Process Card (`#rc_ai_process_cards`)

12-stage pipeline mapped from backend stage strings:

| Key | Label | Backend stages |
|---|---|---|
| init | Reading the Room | queued, starting |
| source | Studying the Source | downloading |
| scene | Mapping the Story | scene_detection |
| audio | Listening for Hooks | transcribing_full |
| beat | Feeling the Rhythm | transcribing_full |
| segment | Spotting the Moments | segment_building |
| scoring | Scoring the Clips | segment_building, rendering |
| assembly | Building the Cut | rendering |
| encode | Rendering | rendering, rendering_parallel |
| validate | Checking Quality | rendering_parallel |
| report | Writing the Brief | writing_report |
| export | Finishing | done, completed |

Renders as `.rcAiProcCard[data-state="running|done|failed"]` with icon, editorial label, editorial message, and progress bar (`--w` custom property).

#### Clip Evolution Feed (`#rc_ai_evolution_feed`)

Label: "Clip Intelligence" (becomes "Creative Outcome" on completion).

Tracks `_lastPartCount`. On each `update()`, detects newly completed parts (status: done/completed/complete), creates `.p28EvolItem.tier-{high|mid|low}` elements with:
- `.p28EvolSignal` — color-coded dot (green/amber/gray by tier)
- `.p28EvolHead` — clip name + score %
- `.p28EvolWhy` — editorial message from `_evolEditorialMsg(pNo, tier)`

Tier thresholds: high ≥ 75%, mid ≥ 50%, low < 50% (from `viral_score × 100`).
Max 6 items visible; oldest pushed out. Items cascade to opacity 1 / 0.52 / 0.28.

Editorial message pools (3 messages per tier, cycled by `pNo % 3`):
- high: "Strong hook from the first frame — this one is a keeper." etc.
- mid: "Solid clip — good bones, room to sharpen the hook." etc.
- low: "Lower signal — may not crack the top picks." etc.

#### AI Reasoning Stream (`#rc_ai_reason_feed`)

Tracks `_reasonItems` (max 10). Pushes a new item from `_REASONING[stageKey]` on each stage change. Rendered as `.rcAiReasonItem` with dot + text. Most recent shown first.

`_REASONING` messages are editorial sentences, not engineering copy:
```
init:     'Workspace open. Source parameters locked and ready to begin.'
encode:   'Clips rendering now — your vision is being written to file.'
export:   'Delivery complete. Your clips are ready to review and export.'
```

#### Completion Intelligence (`#rc_benchmark_insight`)

Rendered inside `#rc_benchmark_panel`. Shows:
- Avg viral score (0–100%) with `[data-tier]` attribute
- Top clip score with `[data-tier]`
- Clips rendered count (completed / total)
- Editorial summary message (tier-dependent)

---

## P2.7 — Runtime UX Consolidation

**Date:** pre-2026-05-16  
**Files:** `runtime.css` (P2.7 section, lines 1690–1820)

### Hierarchy corrections

**Queue demotion**
- `.rcQueueRow:not(.isRendering)`: opacity 0.72, border muted during active render
- `.rcQueueRow.isRendering`: `transition: background .3s, border-color .3s` only — no shimmer

**Log demotion**
- `.logLine`: 9px font, 18px line height
- `.logMessage`: `--fg-400` (muted)
- `.logTime`: opacity 0.35, 8px

**AI card elevation**
- `.rcAiProcCard[data-state="running"]`: `p27ProcGlow` keyframe (border glow), `p27IconPulse` on icon

**Evolution prominence**
- `.rcAiEvolutionFeed` gets elevated visual weight via zone border

**Motion hierarchy**
- `.rcQueueBar > span { animation: none !important }` — kills pre-P2.7 shimmer loop

**Completion narrative**
- `.renderCompletionMsg`: 13px
- `.renderCompletionSummary`: 11px, `--fg-300`

---

## P2.8 — Runtime Spatial Orchestration

**Date:** 2026-05-16  
**Files:** `runtime.css` (P2.8 section, lines 1823–2092), `review.css` (P2.8-F section)

### Editorial language system

All stage labels and messages replaced with editorial copy (no engineering jargon). `_REASONING` object uses human sentences. `_EVOL_MSGS` array replaced with `_evolEditorialMsg(pNo, tier)` function with tier-specific pools.

### Orchestration zones (CSS-only)

Four zones defined by existing DOM structure, separated by border-left + background tint:
- **Zone 1 — Hero**: `.rdCard` + `.rcAiProcCard` — indigo left border, subtle tint
- **Zone 2 — Evolution Heart**: `.rcAiEvolutionFeed` — violet left border, subtle tint
- **Zone 3 — AI Thinking**: `#rc_ai_reason_feed` — indigo left border (lighter)
- **Zone 4 — Infrastructure**: `.rcQueuePanel` rows + `.rcLogStrip` — no territory marker

Terrain separators (1px border-top) between zones.

### Lifecycle ambient field

`#render_active_panel[data-render-state]` gets a radial gradient background:
- running: indigo tint at top
- complete: green tint at top
- failed: red tint at top (very faint)

### Cognitive load reduction (P2.8-H)

During `[data-render-state="running"]`:
- `#rc_active_card`: opacity 0.52 (rcAiProcCard is the primary status surface)
- `.abpPct`, `#rc_active_card .rcActivePercent`: opacity 0.35
- `.rcPanelHeader`: opacity 0.45, letter-spacing

### Output sync pulse (P2.8-B)

`_syncOutputCard(partNo, tier)` is called per completed clip. Applies `.p28ClipMoment` (pulse keyframe) to `.clipCard[data-part-no="${partNo}"]` with 2600ms auto-remove.

### Hero output card (P2.8-F, `review.css`)

`.clipsGrid .clipCard.isBestClip` becomes a full-width horizontal layout:
- `grid-column: 1 / -1` — spans entire clipsGrid row
- `grid-template-columns: 160px 1fr` — thumbnail left, editorial body right
- Thumbnail maintains 9/16 aspect ratio at 160px width
- `.clipCardScore`: 22px (hero scale)
- `.clipCardReason`: white-space normal, full text (not truncated)
- Entrance animation: `p28HeroReveal` (0.55s slide-up + scale)

---

## P2.9 — Runtime Continuity & Creative Outcome

**Date:** 2026-05-16  
**Files:** `render-ui.js` (RenderAiRuntime, lines 4359–4580), `runtime.css` (P2.9 section), `review.css` (P2.9 section)

### Runtime → Output Causality (P2.9-A + P2.9-D)

`_syncOutputCard(partNo, tier)` now applies three effects simultaneously:
1. `.p28ClipMoment` — pulse animation (existing P2.8)
2. `.p29Elevated` — `translateY(-4px)` + elevated shadow for 2.6s, then settles via CSS transition
3. `.p29Causal` — green border-color on high-tier clips only, for 2.6s

All three classes are removed after 2600ms via `setTimeout`. The CSS settle curve is `cubic-bezier(.22,1,.36,1)`.

### Stage Transition Continuity (P2.9-C)

`_updateProcessCard(idx, isFailed)` now checks the current DOM label before rebuilding:

```js
const prevCard = el.querySelector('.rcAiProcCard');
if (prevCard && prevCard.querySelector('.rcAiProcLabel')?.textContent === stg.label) {
  // Same stage — update bar and % only, no innerHTML replacement
  fill.style.setProperty('--w', pct + '%');
  pctEl.textContent = pct + '%';
  return;
}
// Stage changed — morph: add p29Morphing → rAF → swap innerHTML → remove p29Morphing
```

CSS: `.rcAiProcessCards.p29Morphing { opacity: 0; transform: translateY(4px); }` with 0.2s transition.

**Effect:** Progress bar increments smoothly within a stage. Stage changes use a brief fade-morph rather than a hard cut.

### Territory Switching (P2.9-B)

Controlled entirely via `#render_active_panel[data-render-state]` CSS:

| State | Runtime mount | rdCard | Output panel | Completion bar |
|---|---|---|---|---|
| running | full opacity | full opacity | 0.78 opacity | `display: none` |
| complete | 0.38 opacity (hover: 0.72), `pointer-events: none` | 0.55 opacity | 1.0 opacity | visible |
| failed | 1.0 opacity | — | — | — |

`pointer-events: none` on the receded runtime mount at completion ensures clicks reach the output gallery, not the hidden runtime panel. Hover restores it to 0.72 for manual inspection.

### Completion Arrival Moment (P2.9-E)

`_triggerCompletionArrival()` is called once from `showCompletionIntelligence()`:
1. Adds `.p29Arrival` to `#render_active_panel`
2. CSS fires three simultaneous keyframe animations:
   - `p29OutputRise` on `#render_output_panel` — translateY(8px → 0) + opacity
   - `p29RuntimeRecede` on `#render_runtime_mount` — opacity 1 → 0.38
   - `p29CompBarArrival` on `.renderCompletionBar` — scale + translateY, 150ms delayed
3. `.p29Arrival` removed after 1500ms (transitions settle naturally)

Completion bar editorial copy (set once, not repeated):
- `.renderCompletionMsg` → "AI finished shaping your output." (high tier only)
- `.renderCompletionSummary` → e.g. "Best clip 94% — strong hook · 8 clips AI-scored · avg 78%"

Evolution header switches from "Clip Intelligence" to "Creative Outcome" via:
```js
document.querySelector('.rcAiEvolutionHeader span').textContent = 'Creative Outcome';
```

### Confidence Evolution System (P2.9-F)

`_applyConfidenceEvolution(doneCount, totalCount)` runs after each `_updateEvolutionFeed` batch:

```js
const ratio = totalCount > 0 ? doneCount / totalCount : 0;
const level = ratio < 0.3 ? 'emerging' : ratio < 0.62 ? 'rising' : ratio < 0.88 ? 'strong' : 'peak';
bestCard.dataset.p29Confidence = level;
```

CSS progressively strengthens the `.isBestClip` card's border + shadow:
- `emerging`: 0.22 opacity border, minimal shadow
- `rising`: 0.36 opacity border, light glow
- `strong`: 0.52 opacity border, moderate glow
- `peak`: 0.68 opacity border, full glow + `p29ConfidencePeak` animation (ring burst) + Best flag shifts to green-indigo gradient

At completion, `_applyConfidenceEvolution(completed.length, completed.length)` is called (ratio = 1.0 → peak) with 200ms delay.

`reset()` removes `data-p29Confidence` from any lingering best card and restores the evolution header text.

### Status Deduplication (P2.9-G)

Three surfaces, clarified roles:

| Surface | Element | Role | Behavior at `running` |
|---|---|---|---|
| rdCard | `.rdCard` | Creative Director — editorial headline | full opacity; `#render_active_pct` opacity 0 |
| AI Worker | `#rc_ai_process_cards` | AI pipeline status + progress % | primary status surface |
| Infrastructure | `#rc_active_card` | raw part counts / active clip | opacity 0.52 (P2.8), further receded |

`#render_active_pct` (the rdCard's raw % display) is hidden during running via:
```css
#render_active_panel[data-render-state="running"] #render_active_pct { opacity: 0; }
```
Restored to opacity 1 at complete/failed.

### Motion Continuity (P2.9-H)

Approved animations:
- `.rcAiProcCard[data-state="running"]` — `p27ProcGlow` border pulse (P2.7, kept)
- `.p28EvolItem` entrance — `p28EvolIn` translateX slide-in (P2.8, kept)
- `.p29Elevated` settle — `cubic-bezier(.22,1,.36,1)` (P2.9)
- `.p29Arrival` keyframes — one-shot cinematic, auto-removed (P2.9)
- `p29ConfidencePeak` — one-shot ring burst on best card promotion (P2.9)

Suppressed:
- `.rcQueueBar > span { animation: none !important }` — loop shimmer killed

---

## Known Weaknesses (post-P2.9)

> Items 1–3 below were resolved in P2.9.1. Items 4–5 remain open.

### Historical (resolved in P2.9.1)

1. **Card re-render wipes transient classes** — `populateRenderOutputPanel` does a full `innerHTML` replace. ~~If re-render fires within the 2600ms window, `p29Elevated`/`p29Causal` are lost.~~
   - **Fixed P2.9.1-A**: `_transientCards` Map tracks active transient state. `reapplyTransientState()` is called at the end of `populateRenderOutputPanel` to re-apply classes after re-render.

2. **Confidence evolution denominator unstable** — ~~`_applyConfidenceEvolution` uses `parts.length` which can shrink between ticks, causing confidence to regress.~~
   - **Fixed P2.9.1-B**: `_maxKnownTotal` ratchets upward only. Confidence level is monotonic (`emerging → rising → strong → peak`) — never regresses.

3. **Hero card layout breaks at narrow viewports** — ~~160px fixed thumb column overflows at ≤768px.~~
   - **Fixed P2.9.1-D**: Responsive breakpoints at 1366px (130px), 1024px (110px), and 768px (vertical stack with 16:5 cinematic crop).

### Current (open)

4. **`_triggerCompletionArrival` no-ops if DOM missing** — if `#render_active_panel` doesn't exist when `showCompletionIntelligence` fires (e.g., view switched), the arrival animation never runs. The editorial completion bar copy is never set. Low frequency in normal use.

5. **`pointer-events: none` on runtime mount at complete** — users must hover the receded zone to interact with logs. Not discoverable.

---

## P2.9.1 — Runtime Stability Hardening

**Date:** 2026-05-16

### P2.9.1-A — Output Card State Preservation

**Problem:** `populateRenderOutputPanel` replaces `list.innerHTML` completely on every WS tick, destroying transient classes (`p29Elevated`, `p29Causal`, `p28ClipMoment`) before their 2600ms window expires.

**Fix:** 
- `_transientCards = new Map()` tracks active elevations: `partNo → { elevated, causal, expiresAt }`
- `_syncOutputCard` registers each new card state into the map
- `reapplyTransientState()` iterates the map after re-render and re-applies live classes
- `populateRenderOutputPanel` calls `RenderAiRuntime.reapplyTransientState()` before `showRenderOutputPanel()`
- Expired entries are pruned on access
- `reset()` calls `_transientCards.clear()`

### P2.9.1-B — Confidence Evolution Stability

**Problem:** `_applyConfidenceEvolution(done.length, parts.length)` used `parts.length` as the total denominator. If parts arrive incrementally, the denominator can grow between ticks, causing ratio to drop and confidence to regress (e.g., peak → strong).

**Fix:**
- `_maxKnownTotal` ratchets upward only: `_maxKnownTotal = Math.max(_maxKnownTotal, totalCount)`
- `_lastConfidenceLevel` tracks the last applied level
- Level progression is monotonic: `ORDER.indexOf(newLevel) <= ORDER.indexOf(_lastConfidenceLevel)` → return without applying
- Both are reset in `reset()`

### P2.9.1-C — Completion Arrival Idempotency

**Problem:** `_triggerCompletionArrival` was called inside the `!_completionNarrativeSet` guard (already idempotent via that flag), but the function itself had no internal guard — a future caller or edge case could double-fire the animation.

**Fix:**
- `_arrivalTriggered = false` flag added to IIFE state
- `_triggerCompletionArrival` guards with `if (_arrivalTriggered) return; _arrivalTriggered = true;`
- Reset in `reset()`

### P2.9.1-D — Hero Responsive Hardening

**Problem:** `.clipsGrid .clipCard.isBestClip { grid-template-columns: 160px 1fr }` — fixed 160px breaks at narrow viewports.

**Fix (review.css):**
- `@media (max-width: 1366px)`: 130px thumb column
- `@media (max-width: 1024px)`: 110px thumb, reduced padding, 18px score
- `@media (max-width: 768px)`: vertical stack — `grid-template-columns: 1fr`, thumb uses 16:5 cinematic aspect-ratio crop (wide, not portrait), body below

### P2.9.1-E — WS Update Resilience (morph guard)

**Problem:** Rapid WS ticks with stage changes could stack `p29Morphing` class additions before the `requestAnimationFrame` callback cleared the previous one. Double-morph causes a visual stutter.

**Fix:**
- `_morphPending = false` flag in IIFE state
- `_updateProcessCard` only adds `p29Morphing` when `!_morphPending`; sets `_morphPending = true`
- `requestAnimationFrame` callback clears `p29Morphing` and resets `_morphPending = false`

### P2.9.1-F — Null Safety

All `querySelector` results already guarded with null checks across P2.8/P2.9. The `reapplyTransientState()` function guards each card lookup. The `setTimeout` callback in `_triggerCompletionArrival` checks `if (panel)` before class removal (ref to captured variable, not re-queried).

---

## Data Dependencies

| Runtime function | Reads from job | Reads from parts | Reads from summary |
|---|---|---|---|
| `updateRenderMainState` | status, stage, message | part_no, status | total_parts, processing_parts, failed_parts, active_parts |
| `_rankMap` | result_json.output_ranking[] | — | — |
| `_updateEvolutionFeed` | — | part_no, status, viral_score | — |
| `_applyConfidenceEvolution` | — | (derived count) | — |
| `showCompletionIntelligence` | — | viral_score, status | total_parts |
| `populateRenderOutputPanel` | result_json, output_ranking | part_no, part_name, status, output_file, start_sec, end_sec, viral_score, message | — |

`viral_score` is a 0–1 float. All % displays multiply by 100 and round. `output_ranking[].output_score` is 0–10 scale (different from `viral_score`).
