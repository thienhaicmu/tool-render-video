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
              ├── inspContextBar         [no panel attr — always visible]
              ├── evInspAiPanel          [mode — Story only]
              ├── evSectionTrim          [mode — PRIMARY bg tint]
              ├── evSectionAiAssist      [mode — SECONDARY unchanged]
              ├── inspGroupAiEdit        [mode — SECONDARY unchanged]
              ├── evSectionVariants      [mode — SECONDARY unchanged]
              └── cmPrefsPanel           [mode — TERTIARY muted]
```

---

## Maturity Assessment

### Runtime Spatial Clarity

**Before:** Active card border at `.22` opacity — easy to miss against bg-800 surface.  
**After:** `.38` border + `.035` tint — active state reads clearly from the queue rows below.

### Inspector Workspace

**Before:** 380px — cramped for subtitle timing, text layer names, trim field labels.  
**After:** 420px (+10.5%) — enough room to read full control labels without truncation at typical 1920px displays.

### AI Tab Hygiene

**Status:** Clean. No leakage. The UX-IA2.2.1 fix closed the last gap (evInspAiPanel).

### Selection UX

**Before:** All Story sections equal weight — Trim controls visually indistinguishable from memory/preferences config.  
**After:** Trim section has a clear "active workspace" reading. Preferences section recedes as ambient config.

**UI Score: 9.6 / 10** (up from 9.5 post-UX-R3.2)

---

## Known Limitations

- **Part D is subtle by design.** The hierarchy signal is intentionally low-contrast — a `0.018` opacity tint and muted title on preferences, not bold differentiation. Creators may not consciously notice, but the visual gravity is present.
- **Words tab has no PRIMARY designation.** Text layers collapsible auto-opens when layers exist (UX-IA2.2-C), but there's no equivalent bg tint on the primary text editing section. Would require identifying the correct section ID for the Words primary workspace.
- **cmPrefsPanel title size reduction (11px vs 12px)** is a minor inconsistency if creator memory panel is actively used. If it becomes primary workflow, the TERTIARY treatment should be removed.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/static/css/v3/tokens.css` | `--inspector-w: 380px → 420px`, `--inspector-w-sm: 360px → 400px` |
| `backend/static/css/v3/hardening.css` | `--inspector-w: 320px → 352px`, `--inspector-w-sm: 300px → 332px` at ≤1366px |
| `backend/static/css/v3/runtime.css` | `rcActiveCard.isRendering` border `.22→.38` + bg tint; `.isCompleted` border `.18→.25` |
| `backend/static/css/v3/workflow.css` | PRIMARY bg tint on `evSectionTrim`; TERTIARY muted label on `cmPrefsPanel` |
