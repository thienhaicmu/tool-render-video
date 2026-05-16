# Product State — Post P2.9

**Date:** 2026-05-16  
**Branch:** `feature/ai-output-upgrade`  
**Last phase:** P2.9 — Runtime Continuity & Creative Outcome

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed Today (P2.5 → P2.9 arc)

### Starting point: render monitor

Before the P2.x arc, `backend/static/` had a functional render dashboard. It showed:
- A progress bar and status label in a header card (`rdCard`)
- A queue grid of pending parts (`#rc_part_cards`)
- A raw event log (`#event_log_render`)
- An output grid of completed clips (`#render_output_list.clipsGrid`)

It worked. It was not memorable. It felt like a build monitor.

### P2.5 — Runtime Intelligence

Introduced `RenderAiRuntime` — a self-contained IIFE managing three new surfaces:
- **AI Process Card** (`#rc_ai_process_cards`): 12-stage pipeline with editorial labels and progress
- **Clip Evolution Feed** (`#rc_ai_evolution_feed`): live per-clip completion narrative
- **AI Reasoning Stream** (`#rc_ai_reason_feed`): stage-transition editorial sentences
- **Completion Intelligence** (`#rc_benchmark_insight`): avg/top viral score + editorial summary

The raw queue and log still showed. Three surfaces competed for attention with no hierarchy.

### P2.7 — Runtime UX Consolidation

Established a visual hierarchy. Queue rows demoted to 0.72 opacity. Log text demoted to 9px. AI card elevated with glow animation. Shimmer on queue bar killed. Completion bar narrative added. Motion restricted to the AI card only.

The AI orchestration surface was now the primary visual object — but the layout still felt like panels stacked vertically with no spatial logic.

### P2.8 — Runtime Spatial Orchestration

Four zones established via CSS border-left + background tint:
1. Hero (rdCard + rcAiProcCard)
2. Evolution Heart (rcAiEvolutionFeed)
3. AI Thinking (rcAiReasonFeed)
4. Infrastructure (queue rows + logs)

Engineering language replaced with editorial language across all 12 stage labels, 12 reasoning messages, and the evolution feed. `_evolEditorialMsg(pNo, tier)` introduced three message pools per tier.

Best clip card promoted to horizontal full-width hero layout in the output gallery (P2.8-F). Output sync pulse added (`p28ClipMoment`). Cognitive load reduction: rcActiveCard and duplicate % displays demoted during running.

The runtime now looked alive. It did not yet feel alive.

### P2.9 — Runtime Continuity & Creative Outcome

The missing link: causal continuity between runtime events and output consequences.

Five concrete changes:
1. **Stage transitions stopped being hard cuts** — `_updateProcessCard` now detects same-stage ticks and only updates the progress bar; stage changes use a fade-morph via `p29Morphing`
2. **Clip completion now has consequence** — `_syncOutputCard` adds causal elevation (translateY -4px, indigo shadow) and for high-tier clips a green editorial highlight, both settling after 2.6s
3. **Best clip confidence grows visibly** — `_applyConfidenceEvolution` sets `data-p29-confidence` on the isBestClip card; CSS strengthens the border/glow through `emerging → rising → strong → peak`
4. **Completion is a cinematic arrival** — `_triggerCompletionArrival` fires `p29OutputRise` (output gallery slides up), `p29RuntimeRecede` (runtime fades to 38%), and `p29CompBarArrival` (completion bar scales in), all one-shot
5. **Territory switches by lifecycle state** — CSS `[data-render-state]` selectors shift which zone dominates: running = runtime dominant; complete = output dominant (runtime at 38%, hover-restorable)

---

## Current Maturity Assessment

### UI

**Score: 7 / 10**

What works well:
- Runtime orchestration surface is coherent and editorially voiced
- Best clip hero card is visually differentiated
- Five-step workflow rail exists in the home panel
- Output gallery sorts by score, supports inline preview, download, folder open
- AI editorial language is consistent through the pipeline

What is weak:
- No onboarding or empty-state guidance for first-time users
- Home panel ("Render workspace") feels disconnected from the workflow inside the active panel
- The workflow feels learnable but not intuitive — requires discovery
- No visual connection between the AI plan step and the runtime step
- No responsive design — layout assumes wide desktop viewport
- Source input UI is minimal (paste + local pick; no visual feedback for invalid URLs)

### Editor

**Score: 6 / 10**

What works well:
- Recipe editor exists with trim, crop, subtitle, voice, text controls
- AI plan integration (clip ranking passed into editor state)
- `EditorReviewIntelligence` annotates output cards post-render

What is weak:
- No visual inspector integration with rendered output — editor recipe and final clip are not visually compared
- Subtitle preview is not live during editing
- Audio/BGM controls exist but have no waveform preview
- AI plan output (hook score, market fit, pacing) is shown but not interactive
- Inspector panel evenness is poor — some editors are rich, others are stubs

### Runtime

**Score: 8 / 10**

What works well:
- `RenderAiRuntime` is a clean, self-contained IIFE with a clear public API
- Stage-to-editorial-label mapping covers all 12 backend stages
- Territory switching is CSS-only, no JS required
- Completion arrival is cinematic and uses real data
- Confidence evolution is data-driven from `viral_score`
- No runtime rewrites across P2.5–P2.9 — all phases built on existing DOM

What is weak:
- `populateRenderOutputPanel` full re-render can wipe transient elevation classes mid-animation
- Confidence evolution uses `parts.length` as total count, which may be incomplete early in the pipeline
- The log strip (`#event_log_render`) still shows raw engineering events — no editorial filtering
- `#rc_part_cards` (raw part mini-cards) shows in the queue panel alongside the AI evolution feed — redundant with `.clipsGrid`
- `pointer-events: none` on the receded runtime mount at completion is not discoverable

### AI Collaboration

**Score: 6 / 10**

What works well:
- Viral score drives tier classification, evolution feed, confidence evolution, and hero card
- `_rankMap` maps `output_ranking` into rank/score/isBest/reason per part
- `reason` from `_rankMap` is displayed in the output card (`clipCardReason`)
- Completion intelligence shows avg + top score with editorial context

What is weak:
- AI plan output (pre-render) is separate from runtime — no live "AI expectation vs. result" comparison
- `reason` text from `output_ranking` is truncated to 64 chars in the card (hardcoded)
- No adaptive feedback loop — user actions (what they download, preview, export) are not fed back to the AI
- No conversational interface — AI output is read-only

### Production Readiness

**Score: 6 / 10**

What works well:
- FFmpeg render pipeline is functional
- WebSocket + polling transport with reconnect
- Part-level retry and error surface
- Output file download and folder open
- Batch render support

What is weak:
- Dual semaphore mismatch (job_manager vs. render_pipeline) — silent thread exhaustion risk (P0, documented in backend_render_audit.md)
- Batch render bypasses concurrency control (P0)
- No mobile support
- No offline error boundary at shell level
- Setup friction: requires local FFmpeg install, no guided setup flow
- No export format selection (always renders to the configured pipeline format)

---

## Biggest Risks Remaining

### Runtime complexity
The runtime panel is now rich enough that it requires user education. A user starting their first render will see three AI surfaces (process card, evolution feed, reasoning stream) simultaneously, plus the queue grid. This is cognitively coherent to someone who built it; it may not be obvious to a new user.

### Inspector unevenness
Different editor panels have very different levels of completion. The crop editor, subtitle editor, and voice panel have real controls; other panels are closer to stubs. A user who discovers an unfinished panel experiences a trust break.

### Review/export polish
After the runtime completes, the output gallery is functional but not polished. There is no comparison view, no side-by-side diff between clips, no batch export, no "export to platform" flow. The user's journey ends at "download the file."

### No Figma fidelity
The UI was not built against a locked Figma spec. There is no visual design review benchmark. "Does this look right?" has no objective answer.

### Onboarding and setup
There is no first-run experience. A user who installs the app must discover: FFmpeg is required, where to paste a URL, what the AI plan step outputs, why the runtime looks complex. All of this is undocumented in the UI.

---

## What Has Not Changed

Backend render pipeline (Python/FFmpeg) is unchanged across P2.x.
`backend/static-v2/` (the V2 shell prototype) is unchanged and uninvoked.
API surface (`/api/render/*`, `/api/jobs/*`) is unchanged.
WebSocket transport (`/api/jobs/{jobId}/ws`) is unchanged.

---

## Next Phase Direction

### Likely: P3 — Product Intelligence Layer

If the goal is "AI is progressively shaping the best final outcome," P2.9 delivered the runtime side of that feeling. What is still missing is the creative side:

- **Creator memory** — does the system remember what the user exported, rated, or skipped?
- **Adaptive editing** — does the recipe editor suggest changes based on past output quality?
- **Taste modeling** — can the AI learn that this user prefers hook-first pacing over emotional arcs?
- **Conversational AI** — can the user say "make it shorter" or "try a different hook"?
- **Pre-render expectation setting** — can the AI show what it predicts before rendering?

P3 would require backend changes (user preference storage, feedback loop API) and a new frontend surface (AI dialogue or suggestion card). It is a significant scope expansion beyond the current CSS/JS surface work.

### Alternative: P2.10 — Output Review & Export

A narrower next step that stays within the current scope:
- Side-by-side clip comparison
- Batch export with format selection
- "Share for review" link generation
- Inspector panel completion (finish the stub panels)

This would complete the product loop without requiring backend AI changes.

---

## Commit Grouping (suggested)

The following commits represent the P2.8 + P2.9 work on this branch:

**Commit 1 — P2.8 runtime spatial orchestration (CSS)**
- `runtime.css`: zone architecture, lifecycle ambient, evolution items, cognitive load
- `review.css`: hero output card layout (P2.8-F), p28ClipMoment pulse

**Commit 2 — P2.8 editorial language (JS)**
- `render-ui.js`: `_STAGES` and `_REASONING` editorial copy, `_evolEditorialMsg` function, `_updateEvolutionFeed` rich items, `_syncOutputCard` initial

**Commit 3 — P2.9 runtime continuity (CSS + JS)**
- `runtime.css`: P2.9 territory switching, morph continuity, completion arrival, deduplication
- `review.css`: P2.9 causality styles, confidence evolution CSS
- `render-ui.js`: `_updateProcessCard` morph, `_syncOutputCard` causal, `_applyConfidenceEvolution`, `_triggerCompletionArrival`, `showCompletionIntelligence` editorial completion, `reset()` cleanup

**Commit 4 — Documentation**
- `docs/review/frontend/RUNTIME_ORCHESTRATION.md` (new)
- `docs/review/PRODUCT_STATE_P2_9.md` (new)
- `docs/review/frontend_ui_audit.md` (appended P2.x section)
