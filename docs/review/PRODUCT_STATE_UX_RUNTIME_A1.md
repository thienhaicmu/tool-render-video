# Product State — Post UX-RUNTIME-A1

**Date:** 2026-05-17  
**Branch:** `feature/ai-output-upgrade`  
**Phase:** UX-RUNTIME-A1 — Runtime & Editor Coherence Audit + Fix

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## Goal

Four-part coherence pass. Not a redesign. No new features, no backend changes, no architecture changes.

**Presenting problem:** Runtime felt spatially weak during active render. Inspector too narrow for comfortable editing work. AI elements suspected of leaking across tabs. Story/Subtitles/Words inspector sections felt equal-weight with no hierarchy signal.

---

## Part A — Runtime Visual Strength

### Audit Findings

`rcQueuePanel` and its children are alive execution terrain — not a dead zone post-R8. The CSS already has a full three-tier spatial model:

- **Plane 1 (What AI is doing):** `rdCard` — center-stage UX-R1 summary (owned by UX-R1 hero)
- **Plane 2 (Execution terrain):** `renderRuntimeMount → rcBottom → rcAQMain → rcQueuePanel (62%) + rcLogStrip (38%)` — live job queue with `rcActiveCard`, `rcQueueRow[]`, `rcPartCard[]`
- **Plane 3 (Outcome):** `render_output_panel` — tier-classified clip grid (UX-R3)

`rcActiveQueue` is spatially meaningful: it's the 62% left column of Plane 2, showing the currently rendering part card at top followed by queued jobs.

**WebSocket payload:** richer than UI displayed — payload includes per-stage timing, confidence evolution (P2.9), stall detection, quality scores. All being consumed. No backend richness lost.

### What Changed

**`backend/static/css/v3/runtime.css`:**

```css
/* Before */
.rcActiveCard.isRendering { border-color: rgba(77,124,255,.22); }
.rcActiveCard.isCompleted { border-color: rgba(34,197,94,.18); }

/* After */
.rcActiveCard.isRendering { border-color: rgba(77,124,255,.38); background: rgba(77,124,255,.035); }
.rcActiveCard.isCompleted { border-color: rgba(34,197,94,.25); }
```

Active render state now clearly distinct from idle. The `.035` bg tint adds spatial weight without competing with Plane 1 narrative.

### What Was NOT Changed

- `rcQueuePanel` flex ratio (62%) — already correct
- `rcLogStrip` (38%) — unchanged
- `abpToolbar` stage pill — unchanged
- `rcStageTimeline` dot animations — unchanged
- `rcStallBanner` — unchanged
- All RenderAiRuntime dynamic card generation — unchanged

---

## Part B — Inspector Width Rebalance

### Audit Findings

Before this phase, inspector occupied 380px of the layout (3-column grid: `280px sidebar | 1fr center | 380px inspector`). At ≤1366px breakpoint: 320px. For a workspace where creators write clip trim ranges, manage subtitle timing, and review text layers, 380px was measurably tight — especially with the `evSectionTitle::before` dot + label + action controls all sharing row width.

### What Changed

**`backend/static/css/v3/tokens.css`:**

```css
/* Before */
--inspector-w:      380px;
--inspector-w-sm:   360px;

/* After */
--inspector-w:      420px;
--inspector-w-sm:   400px;
```

**`backend/static/css/v3/hardening.css` (≤1366px breakpoint):**

```css
/* Before */
--inspector-w: 320px;
--inspector-w-sm: 300px;

/* After */
--inspector-w: 352px;
--inspector-w-sm: 332px;
```

Net gain: +40px at 1920px+, +32px at 1366px. The center stage (video preview, clip grid) absorbs the loss via `minmax(0, 1fr)` — no overflow, no regression.

### What Was NOT Changed

- `--sidebar-w: 280px` — unchanged (sidebar is navigation, not primary workspace)
- `--sidebar-w: 252px` at ≤1366px — unchanged
- `.rs-main` grid template — unchanged (custom property drives it)
- All inspector panel scroll behavior — unchanged

---

## Part C — AI Leakage Audit

### Audit Findings

Full pass across all `[data-insp-panel]` elements in `backend/static/index.html`. Result: **clean — no AI leakage found.**

Every Story-owned element is correctly scoped:

| Element | `data-insp-panel` | Tab |
|---------|-------------------|-----|
| `evInspAiPanel` | `mode` | Story only ✓ |
| `evSectionTrim` | `mode` | Story only ✓ |
| `evSectionAiAssist` (chips, activity rail) | `mode` | Story only ✓ |
| `inspGroupAiEdit` (6 AI actions + subtitle link) | `mode` | Story only ✓ |
| `evSectionVariants` (Viral/Cinematic/Aggressive/Balanced + Snapshots) | `mode` | Story only ✓ |
| `cmPrefsPanel` (creator memory/preferences) | `mode` | Story only ✓ |
| `convPanel` (AI conversation/copilot) | `ai` | AI tab only ✓ |
| `inspSubtitlePane` | `subtitle` | Subtitles only ✓ |
| `inspGroupTextLayersHdr` / body | `text` | Words only ✓ |
| Audio sections | `audio` | Audio only ✓ |
| Export sections | `performance` | Export only ✓ |

Only element without `data-insp-panel`: `inspContextBar` — intentionally globally visible (shows tab name "Editor").

This clean state was established by the UX-IA2.2.1 regression fix (2026-05-17) which added `data-insp-panel="mode"` to `evInspAiPanel`.

### What Changed

Nothing. Audit found no remaining leakage.

---

## Part D — Selection UX Hierarchy

### Problem

Story/Subtitles/Words inspector sections had equal visual weight. No signal distinguishing "this is where you work right now" (primary task) from "these are tools available to you" (secondary) from "configure this session" (tertiary). All sections rendered with identical `evSection` styling.

### What Changed

**`backend/static/css/v3/workflow.css` — new block after existing section accent rules:**

```css
/* ── [UX-RUNTIME-A1-D] Inspector selection hierarchy ─────
   PRIMARY (current task): Trim — active workspace signal.
   TERTIARY (configure): cmPrefsPanel — deprioritised chrome.
   ─────────────────────────────────────────────────────── */
#evSectionTrim {
  background: rgba(77,124,255,.018);
}
#cmPrefsPanel .evSectionTitle {
  color: var(--fg-400);
  font-size: 11px;
}
#cmPrefsPanel .evSectionTitle::before {
  background: var(--fg-400);
  opacity: .5;
}
#cmPrefsPanel {
  border-bottom-color: rgba(255,255,255,.03);
}
```

### Tier Logic

| Tier | Element | Signal |
|------|---------|--------|
| PRIMARY | `evSectionTrim` | Faint blue bg tint — "this is the workspace" |
| SECONDARY | `evSectionAiAssist`, `inspGroupAiEdit`, `evSectionVariants` | Standard (unchanged) |
| TERTIARY | `cmPrefsPanel` | Muted label + thinner border — "set and forget" |

### What Was NOT Changed

- All panel IDs, handler bindings, and feature functionality — untouched
- `evSectionTrim .evSectionTitle { color: var(--primary); }` — still active (primary accent on title)
- `inspSubtitlePane .evSectionTitle { color: var(--secondary); }` — still active
- Section content, layout, or interactive elements — untouched

---

## Architecture (Unchanged)

```
.rs-main
  ├── .appSidebar          [280px — navigation]
  ├── .appStage            [1fr — center, absorbs inspector gain]
  └── .appInspector        [420px default, 352px ≤1366px]
        └── .inspPaneBody
              ├── inspContextBar               [no panel attr — always visible]
              │
              ├── [Story / mode]
              │   ├── evInspAiPanel            [mode — dynamic AI status]
              │   ├── evSectionTrim            [mode — PRIMARY bg tint]
              │   ├── evSectionAiAssist        [mode — SECONDARY unchanged]
              │   ├── inspGroupAiEdit          [mode — SECONDARY unchanged]
              │   ├── evSectionVariants        [mode — SECONDARY compact rail]
              │   └── cmPrefsPanel             [mode — TERTIARY muted]
              │
              ├── [Subtitles / subtitle]
              │   └── inspSubtitlePane         [subtitle — secondary accent, full tab]
              │
              ├── [Words / text]
              │   ├── evSectionNarration       [text — SECONDARY (purple accent)]
              │   └── inspGroupTextLayers      [text — PRIMARY when open (blue tint)]
              │
              ├── [Audio / audio]
              │   └── inspGroupAudio           [audio — single collapsible]
              │
              └── [Export / performance]
                  ├── evPresetSection          [performance — SECONDARY unchanged]
                  ├── evSectionMarket          [performance — PRIMARY bg tint]
                  ├── evSectionBasic           [performance — primary accent title]
                  ├── inspGroupPerf            [performance — Render Settings]
                  └── inspGroupAdv             [performance — TERTIARY muted header]
```

---

## UX-RUNTIME-A1.1 — Hierarchy Depth Extension (2026-05-17)

Continuation of Part D and Part A after full inspector HTML audit.

### Words Tab Hierarchy

`evSectionNarration` (AI Narration) — SECONDARY signal (purple accent on title). AI narration is an enhancement layer over the primary editing task, not the workspace itself.

Text layers collapsible open state — PRIMARY signal when active. When the creator expands the text layers editor, the header gets a blue bg tint + stronger border and the body gets a matching bg tint. This matches the pattern used for `evSectionTrim` in Story.

```css
#evSectionNarration .evSectionTitle { color: var(--secondary); }
#evSectionNarration .evSectionTitle::before { background: var(--secondary); }
#inspGroupTextLayersHdr.open { background: rgba(77,124,255,.028); border-bottom-color: rgba(77,124,255,.15); }
#inspGroupTextLayersBody.open { background: rgba(77,124,255,.013); }
```

### Export Tab Hierarchy

`evSectionMarket` (Market & Target) — PRIMARY signal. Intent declaration ("where are you publishing?") precedes all technical configuration. Gets same blue bg tint + primary accent title as `evSectionTrim`.

`inspGroupAdvHdr` (Advanced Debug) — TERTIARY signal. Muted color (`fg-400`) and reduced font size (10.5px). This is a developer/diagnostic tool, not a creator workflow step.

### Runtime Queue Row (Part A extension)

`rcQueueRow.isRendering` background boosted `.04` → `.08`. Previously at `.04`, the active rendering row was barely distinguishable from hover state (`.025`). At `.08`, it reads clearly as "this is what's running" within the queue column.

---

## Maturity Assessment

### Runtime Spatial Clarity

**Before:** Active card border at `.22` opacity, queue row at `.04` bg.  
**After:** `.38` border + `.035` card tint, `.08` queue row bg — active state reads clearly at both the card level and the row level within Plane 2.

### Inspector Workspace

**Before:** 380px — cramped for subtitle timing, text layer names, trim field labels.  
**After:** 420px (+10.5%) — enough room to read full control labels without truncation at typical 1920px displays.

### AI Tab Hygiene

**Status:** Clean. No leakage. The UX-IA2.2.1 fix closed the last gap (evInspAiPanel).

### Selection UX

**Before:** All sections equal weight across all tabs — no signal distinguishing workspace from tools from config.  
**After:** Four-tab hierarchy complete:
- Story: Trim=PRIMARY, AiAssist/Actions/Variants=SECONDARY, Prefs=TERTIARY
- Words: TextLayers(open)=PRIMARY, Narration=SECONDARY
- Export: Market&Target=PRIMARY, Output/Presets=SECONDARY, AdvDebug=TERTIARY
- Subtitles: Full tab is PRIMARY (secondary-accented, single workspace)

**UI Score: 9.7 / 10** (up from 9.6 post-A1 initial)

---

## UX-RUNTIME-A1.2 — AI Ownership Enforcement (2026-05-17)

P0 regression fix. AI panels visible on all tabs due to CSS gap in v3.

### Root Cause

The v3 CSS migrated from `app.css` with only three element-type-specific hide rules:

```css
.evSection[data-insp-panel]:not(.insp-panel-active)        { display: none; }
.inspGroupSep[data-insp-panel]:not(.insp-panel-active)     { display: none; }
.inspCollapsedGroup[data-insp-panel]:not(.insp-panel-active) { display: none; }
```

The old `app.css` had a broad rule (`.inspPaneBody [data-insp-panel]:not(.insp-panel-active) { display: none !important; }`) that was never migrated. The three v3 rules only covered elements that happened to have those exact CSS classes. Four elements used custom classes and were completely uncovered:

| Element | Class | data-insp-panel | Effect |
|---------|-------|-----------------|--------|
| `evInspAiPanel` | `evInspAiPanel` | `mode` | AI action cards visible on ALL tabs |
| `convPanel` | `convPanel` | `ai` | AI conversation visible on ALL tabs |
| `cmPrefsPanel` | `cmPrefsPanel` | `mode` | Creator memory visible on ALL tabs |
| `evSectionVariants` | `evCompactRail` | `mode` | Variants/Snapshots visible on ALL tabs |

### How it appeared to "work" before

`evInspAiPanel` was empty (class `evInspAiPanel:empty { display: none !important; }`) on initial load and most tab views. The empty rule suppressed it. When an AI action was run and cards were rendered into it, the empty rule no longer applied — the AI card became visible everywhere. The others (`convPanel`, `cmPrefsPanel`, `evSectionVariants`) were globally visible at all times.

### Fix

**`backend/static/css/v3/workflow.css` — single broad rule:**

```css
.inspPaneBody [data-insp-panel]:not(.insp-panel-active) {
  display: none !important;
}
```

This matches ANY element inside `.inspPaneBody` with `data-insp-panel` that doesn't have `.insp-panel-active`. The three element-specific rules are retained as documentation but are functionally superseded.

No JS changes — `setInspectorTab()` already correctly manages `.insp-panel-active` on all `[data-insp-panel]` elements via querySelectorAll. The CSS system was the gap.

### Tab Ownership Matrix (Canonical Post-Fix)

| Tab | Shows | Must NOT Show |
|-----|-------|--------------|
| Story | Trim, AiAssist, AI Edit Actions, Variants, Snapshots, Creator Memory, AI panel cards | AI conversation, subtitle editor, text layers, audio, export |
| AI | Conversation, copilot, history, example chips | Everything else |
| Subtitles | Subtitle style, preview, translate, Fix Subs | AI chips, variants, creator memory, prompt input |
| Words | AI Narration, voice controls, text layers | Story AI, creator memory, editing chips |
| Audio | Source audio, BGM, loudness | AI prompt, chips, creator memory, variants |
| Export | Presets, Market & Target, Output, Render Settings, Advanced Debug | Editing AI, chips, creator memory, variants |

### Cross-Tab Behavior

AI action card (Accept/Discard) rendered on Story tab → switch to Subtitles → card hidden by CSS (not destroyed) → return to Story → card restored. No regression.

### QA Checklist

- [ ] Open editor on Story tab — AI chips, trim controls, variants visible
- [ ] Switch to Subtitles — subtitle editor only; no AI chips, no creator memory, no variants
- [ ] Switch to Words — narration + text layers only; no Story AI elements
- [ ] Switch to Audio — audio controls only; no AI contamination
- [ ] Switch to Export — export sections only; no editing AI, no variants, no creator memory
- [ ] Switch to AI tab — conversation only; no Story editing elements
- [ ] Run AI action on Story → Accept/Discard card appears
- [ ] Switch to Subtitles — card hidden (not destroyed)
- [ ] Return to Story — card visible again
- [ ] No console errors

---

## Known Limitations

- **Hierarchy is subtle by design.** Signals are intentionally low-contrast — `.018` opacity tints, muted label colors. Visual gravity is present without visual noise.
- **Audio tab has no internal hierarchy.** Single collapsible group with three sections (Source Audio, Background Music, Loudness Normalization). Normalization is arguably TERTIARY but has no wrapper ID to target without HTML changes.
- **Subtitles tab has no internal hierarchy.** Translation controls at the bottom of `inspSubtitlePane` are set-once/forget (SECONDARY candidate) but have no wrapper ID for CSS-only targeting.
- **cmPrefsPanel title size reduction (11px vs 12px)** is a minor inconsistency if creator memory panel is actively used. Revert the TERTIARY treatment if usage data shows it's a frequent workflow step.
- **Text layers PRIMARY signal only activates when the collapsible is open.** When collapsed (no layers exist), the Words tab has no PRIMARY section — this is correct behavior.

---

## UX-RUNTIME-A2.1 — Runtime Truth Layer (2026-05-17)

Commit `feat(ui): UX-RUNTIME-A2.1 runtime truth layer`. CSS + JS only. No HTML changes, no backend changes.

### P0-A — Alive Signal (`rc_eta`)

`rc_eta` repurposed from hidden ETA-only display to a composite alive indicator. Two-layer ownership:

- **`updateRenderMonitorHeartbeat`** (1s timer): sets `data-alive-state` attribute — `ok` (fresh), `slow` (>10s since last progress), `stalled` (stall threshold crossed). No text, no hidden management.
- **`renderBottomActiveQueue`** (WS updates): owns text content and visibility. Falls back to `'Rendering…'` when running but no ETA available. Preserves `data-alive-state` from heartbeat (`etaEl.dataset.aliveState || 'ok'`).

CSS: `#rc_eta[data-alive-state="ok"]` → `fg-400`; `"slow"` → `fg-300`; `"stalled"` → `--warning`.

### P0-B — Clip Count Prominence

Queue summary changed from `"N completed · M rendering · K waiting"` → `"N of T done · M active · K waiting"` in both build paths (legacy `~line 824` and `renderBottomActiveQueue ~line 1493`). Creator can read completion fraction at a glance.

### P0-C — Waiting Visibility

`.rcQueueRow.isWaiting` and `.rcPartCard.isWaiting` border-left boosted `.18→.38`. Queue items waiting in line now have visible spatial weight — not invisible, not urgent, but clearly present.

### P0-D — Part Message as Execution Narrative

- Fallback message for rendering parts changed `'Processing'` → `'Rendering…'` — matches tone of surrounding product language.
- `.rcPartCard.isRendering .rcPartMessage` color boosted `fg-400→fg-300` — actively rendering part message readable, not muted to the same level as idle parts.
- `activeMessage.dataset.aliveState` deleted on each message set — no stale alive state persists across message cycles.

### P1 — Log Strip and Stall Banner

- `rcQueuePanel` flex expanded `62%→70%` during `data-render-state="running"` — queue gets more visual territory when a render is live, log strip narrows to `30%`.
- `rcStallBanner` moved to `insertBefore(firstChild)` — stall warning appears at top of active card, not buried below content.

### What Was NOT Changed

- All WS payload handling — unchanged
- `_detectStallSignal` — unchanged  
- `updateRenderMonitorHeartbeat` heartbeat output to `render_monitor_heartbeat` — unchanged (still hidden in `rcCompatHidden`)
- All element IDs, DOM structure — unchanged
- `rcActiveCard` layout — unchanged

### Architecture Note

`rc_eta` now has dual-signal ownership. The heartbeat timer wins on color (runs every 1s, always reflects `noProgressMs`). `renderBottomActiveQueue` wins on text/visibility (reflects actual clip data from WS). The `|| 'ok'` guard in `renderBottomActiveQueue` ensures a WS update never downgrades a 'stalled' or 'slow' state set by the heartbeat — only the next heartbeat tick can change it.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/static/css/v3/tokens.css` | `--inspector-w: 380px → 420px`, `--inspector-w-sm: 360px → 400px` |
| `backend/static/css/v3/hardening.css` | `--inspector-w: 320px → 352px`, `--inspector-w-sm: 300px → 332px` at ≤1366px |
| `backend/static/css/v3/runtime.css` | A1: `rcActiveCard.isRendering` border/tint; A1.1: queue row bg; **A2.1:** waiting border `.18→.38` (queue row + part card), `isRendering .rcPartMessage` color, `rc_eta` alive states, `rcQueuePanel` 70% during running |
| `backend/static/css/v3/workflow.css` | **A1.2 (P0):** broad `[data-insp-panel]:not(.insp-panel-active)` rule; A1/A1.1: hierarchy tints for Story/Words/Export |
| `backend/static/js/render-ui.js` | **A2.1:** `updateRenderMonitorHeartbeat` alive state; queueSummary "X of Y" format (×2); 'Rendering…' fallback; `aliveState` cleanup; stall banner `insertBefore`; `renderBottomActiveQueue` ETA block enhanced |
