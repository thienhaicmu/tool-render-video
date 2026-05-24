# RENDER UI AUDIT — SCROLL + LAYOUT INTEGRITY

**Branch:** `feature/ai-output-upgrade`  
**Date:** 2026-05-18  
**Scope:** rcQueuePanel, render_output_panel, render_output_list, cs_preview_area, rqWorkspace  
**Method:** Read-only — no fixes applied. All findings are from `css/v3/` (the only loaded stylesheet chain).

> **Note:** `backend/static/css/app.css` (root level, ~17 000 lines) is **not linked** from `index.html`.  
> The live stylesheet is `css/v3/app.css` → imports tokens → layout → components → workflow → runtime → review → download → history → hardening → editor-engine.

---

## STEP 0 — REAL DOM / LAYOUT TREE

### Served CSS load order (cascade-relevant)

```
tokens.css
layout.css
components.css
workflow.css       ← rs-center-stage, rs-preview-stage, mainArea.rs-center-panel
runtime.css        ← renderActivePanel, rcBottom, rcQueuePanel, rcQueueGrid
review.css         ← renderOutputPanel, renderOutputList, csPreviewArea, rqWorkspace
download.css
history.css
hardening.css      ← last override layer — wins over all above at equal specificity
editor-engine.css
```

### Actual DOM hierarchy for render surfaces

```
html
└─ .appShell  (CSS grid, implicitly full viewport via grid rows)
    └─ .mainArea.rs-center-panel            [workflow.css:1045–1051]
       display: flex; flex-direction: column;
       overflow: hidden;   ← clips ALL overflow from children
       min-height: 0; flex: 1;
       │
       └─ .rs-center-stage                  [workflow.css:1054–1060]
          display: flex; flex-direction: column;
          flex: 1; min-height: 0;
          overflow: hidden;   ← second clip boundary
          │
          ├─ .rs-preview-stage              [workflow.css + hardening]
          │   flex: 0 0 auto (hardening H-HOTFIX-1 override)
          │   Only active in editorMode
          │
          ├─ #partial_render_home           (hidden during/after render)
          │
          ├─ #render_active_panel           (DURING render — see §rcQueuePanel below)
          │
          ├─ #render_completion_bar         (flex: 0 0 auto)
          │
          └─ #render_output_panel           (AFTER render complete)
             .renderOutputPanel
             display: flex; flex-direction: column;
             flex: 0 0 auto;   ← content-sized, NO flex growth   [review.css:32]
             min-height: 0;
             overflow: visible;  ← hardening.css:601 explicit; same as default
             │
             ├─ .renderOutputHeader        position: sticky; top: 0; z-index: 10
             ├─ #render_output_path
             ├─ #mvRenderSummary
             ├─ .csPreviewArea             (see §cs_preview_area below)
             └─ #render_output_list        display: grid; min-height: 0; NO overflow
```

---

## STEP 1 — SCROLL OWNERSHIP AUDIT

### rcQueuePanel (during active render)

```
renderActivePanel                [runtime.css:24–31]
  display: flex; flex-direction: column;
  flex: 1; min-height: 0; overflow: hidden;
  │
  ├─ .rdCard                     flex-shrink: 0
  ├─ .aiInsightsPanel            flex-shrink: 0
  └─ .renderRuntimeMount         flex: 1; min-height: 0
      │
      ├─ .abpToolbar             flex-shrink: 0
      └─ .rcBottom               flex: 1; overflow: hidden; flex-direction: row
          │
          ├─ .rcQueuePanel       flex: 0 0 62%;
          │   display: flex; flex-direction: column;
          │   min-height: 0; overflow: hidden;
          │   │
          │   ├─ .rcPanelHeader  flex-shrink: 0 (+ sticky/position rules)
          │   ├─ .rcActiveCard   flex-shrink: 0
          │   └─ #rc_part_cards.rcQueueGrid
          │       flex: 1; min-height: 0;
          │       overflow-y: auto; overflow-x: hidden;   ✓ SCROLL OWNER
          │
          └─ .rcLogStrip         flex: 1 (remainder)
```

**Scroll owner:** `#rc_part_cards.rcQueueGrid`  
**Height chain terminates:** YES — bounded by rcBottom → renderRuntimeMount → renderActivePanel → rs-center-stage  
**Status:** CLEAN ✓

---

### render_output_panel + render_output_list (after render complete)

```
.rs-center-stage  overflow: hidden; flex: 1; min-height: 0
  │
  └─ #render_output_panel.renderOutputPanel
      flex: 0 0 auto;           ← CONTENT-SIZED (no growth cap)
      overflow: visible;
      │
      ├─ .renderOutputHeader    sticky, top: 0
      ├─ ... fixed children ...
      └─ #render_output_list.renderOutputList
          display: grid; min-height: 0;
          NO overflow property   ← expands to natural grid height
```

**Scroll owner:** NONE  
**Height chain terminates:** NO — `flex: 0 0 auto` + no overflow means content grows freely, then rs-center-stage clips it at `overflow: hidden`  
**Status:** **P0 BROKEN** — clips are hidden, not scrollable

---

### cs_preview_area (inside render_output_panel)

```
.csPreviewArea
  display: flex; flex-direction: column;
  flex-shrink: 0; overflow: hidden;
  margin: 12px 16px 0;
  │
  ├─ .csPreviewVideoWrap
  │   aspect-ratio: (data-driven);
  │   width: clamp(200px, 34vh, 52%);   ← portrait example
  │   overflow: hidden;
  │   └─ video / overlays (position: absolute, inset: 0)
  │
  └─ #cs_preview_bar
      flex-shrink: 0; display: flex;
```

**Scroll owner:** N/A (fixed-size inline block, not a scroll surface)  
**Status:** Functionally correct. P2 issue: `34vh` in `clamp()` creates viewport-height-relative layout instability (see §5).

---

### rqWorkspace / Review Queue

```
.rqWorkspace                     [review.css:2222–2228]
  display: flex; flex-direction: column;
  flex: 1; min-height: 0; overflow: hidden;
  │
  ├─ .rqHeader                   flex-shrink: 0
  └─ .rqBody                     [review.css:2276–2283]
      flex: 1; overflow-y: auto;
      display: flex; flex-direction: column; gap: 20px;
      /* overflow-x: not set → implicit auto */
```

**Scroll owner:** `.rqBody` — correct IF `.rqWorkspace` itself is bounded (flex: 1 inside a height-constrained parent).  
**Status:** LIKELY CORRECT. P1 minor: missing `overflow-x: hidden` on `.rqBody` (see §4).

---

## STEP 2 — FLEX INTEGRITY AUDIT

| Element | display | flex props | min-height | overflow | missing? |
|---------|---------|-----------|------------|----------|----------|
| `.mainArea.rs-center-panel` | flex col | flex: 1 | 0 | hidden | — |
| `.rs-center-stage` | flex col | flex: 1 | 0 | hidden | — |
| `.renderActivePanel` | flex col | flex: 1 | 0 | hidden | — |
| `.renderRuntimeMount` | flex col | flex: 1 | 0 | — | — |
| `.rcBottom` | flex row | flex: 1 | — | hidden | — |
| `.rcQueuePanel` | flex col | flex: 0 0 62% | 0 | hidden | — |
| `#rc_part_cards.rcQueueGrid` | block | flex: 1 | 0 | y:auto | — ✓ |
| `.renderOutputPanel` | flex col | **flex: 0 0 auto** | 0 | visible | **needs flex: 1 + overflow-y: auto** |
| `#render_output_list` | grid | — | 0 | visible | scroll owner above it |
| `.csPreviewArea` | flex col | flex-shrink: 0 | — | hidden | — |
| `.rqWorkspace` | flex col | flex: 1 | 0 | hidden | — |
| `.rqBody` | flex col | flex: 1 | — | y:auto | **overflow-x missing** |
| `.csPreviewInfo` | flex | flex: 1 | — | — | min-width: 0 ✓ |

---

## STEP 3 — CSS OVERRIDE COLLISION AUDIT

### Collision A — renderOutputPanel flex value (P0 contributor)

| File | Line | Selector | Rule | Specificity |
|------|------|----------|------|-------------|
| `review.css` | 32 | `.renderOutputPanel` | `flex: 0 0 auto` | (0,1,0) |
| — | — | — | No ID override in v3 files | — |

**Result:** `flex: 0 0 auto` wins unchallenged. Panel never grows to fill available stage space.

### Collision B — renderOutputPanel overflow (P1 — misleading comment)

| File | Line | Selector | Rule |
|------|------|----------|------|
| `review.css` | — | `.renderOutputPanel` | (overflow not set in review.css) |
| `hardening.css` | 600–602 | `.renderOutputPanel` | `overflow: visible` |

**Comment in hardening.css says:** "ensure flex children scroll correctly"  
**Reality:** `overflow: visible` is the CSS default — this rule has no effect. The actual clipping is done by `.rs-center-stage { overflow: hidden }` two levels up.

### Collision C — rs-preview-stage flex (P0 hotfix — CORRECT)

| File | Line | Selector | Rule |
|------|------|----------|------|
| `workflow.css` | 1039 | `.rs-preview-stage` | `flex: 1` |
| `hardening.css` | 642–644 | `.rs-preview-stage` | `flex: 0 0 auto` |

**Result:** hardening.css wins (later load, same specificity). Intentional. Prevents preview stage stealing render panel space. ✓

### Orphaned CSS — `.renderOutputScrollArea` never reaches DOM

| File | Lines | Rule |
|------|-------|------|
| `hardening.css` | 603–607 | `.renderOutputScrollArea { flex: 1 1 auto; min-height: 0; overflow-y: auto; }` |

**DOM search:** No `renderOutputScrollArea` in `index.html` or any partial.  
**Diagnosis:** A scroll-wrapper solution was designed (correct properties) but the wrapper `<div>` was never added to the HTML. The CSS is dead.

---

## STEP 4 — HEIGHT CHAIN AUDIT

### render_output_panel height resolution

```
appShell (grid rows, total ~100vh — height is defined ✓)
  └─ mainArea.rs-center-panel (grid child → defined height ✓)
      overflow: hidden — is a scroll/clip boundary
      └─ rs-center-stage (flex: 1 → fills mainArea ✓)
          min-height: 0 — CAN shrink
          overflow: hidden — clips at this boundary
          └─ renderOutputPanel (flex: 0 0 auto)
                                 ↑
                     NATURAL HEIGHT — NOT bounded by parent

Consequence: when renderOutputPanel.naturalHeight > rs-center-stage.height
             → excess content clipped by rs-center-stage { overflow: hidden }
             → user cannot scroll to clipped content
```

**`100%` height chains** — all panels use flex sizing (no `height: 100%` anti-patterns found in v3 files). ✓

---

## STEP 5 — OVERFLOW POLICY AUDIT

| Element | overflow | Intent | Issue |
|---------|----------|--------|-------|
| `.mainArea.rs-center-panel` | hidden | clip edge | correct — outer clip boundary |
| `.rs-center-stage` | hidden | clip content | **clips render output panel content** |
| `.renderOutputPanel` | visible | (default) | no scroll set — content bleeds then clips |
| `#render_output_list` | (default visible) | grid expands | correct, expects parent to scroll |
| `.rcQueuePanel` | hidden | contains rcQueueGrid scroll | correct ✓ |
| `#rc_part_cards.rcQueueGrid` | y:auto | **SCROLL OWNER** | correct ✓ |
| `.rqBody` | y:auto | **SCROLL OWNER** | correct; x implicit auto |

---

## STEP 6 — INTERACTION LAYER AUDIT

### .renderOutputHeader — sticky collision risk

```css
.renderOutputHeader {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--bg-850);
}
```

**Issue:** `position: sticky` only works if an ancestor IS a scroll container. Since `renderOutputPanel` currently has no scroll (P0), the sticky header has no scroll container to stick in — it will behave like `position: static`. Once the scroll fix is applied (renderOutputPanel becomes the scroll container), sticky will work correctly.

### cs_preview_area width units

```css
/* portrait 9:16 example */
.csPreviewVideoWrap[data-orient="portrait"] {
  width: clamp(200px, 34vh, 52%);
  aspect-ratio: 9 / 16;
}
```

**Issue:** `34vh` is viewport-height-relative. At 900px viewport height → 306px wide → 544px tall preview. At 1400px height → 476px wide → 847px tall. Unpredictable layout contribution. The preview's height drives renderOutputPanel's total height, which is already unbounded.

---

## STEP 7 — WINDOW RESIZE TEST (static analysis)

| Viewport | Expected | Risk |
|----------|----------|------|
| Small (<900px) | render output scrolls | P0: no scroll at any width |
| Mid (900–1280px) | stable flex layout | P0: clips still broken |
| Maximized (>1280px) | cards fill width nicely | P0 + P2: preview may be very tall |
| Resize while output visible | layout reflows | Preview height shifts due to `vh` units |

---

## FINDINGS SUMMARY

### P0 — Broken layout (blocking)

#### ROP-1: render_output_panel has no scroll container

**Affected:** All users after render completes with multiple clips.

**Cause chain:**
1. `css/v3/workflow.css:1059` — `.rs-center-stage { overflow: hidden }` — correct clip for editor mode, but also clips render output
2. `css/v3/review.css:32` — `.renderOutputPanel { flex: 0 0 auto }` — panel is content-sized, not bounded
3. No element in the chain between stage and grid has `overflow-y: auto`
4. When `renderOutputPanel.height > rs-center-stage.height` → content clipped, not scrollable

**Symptom:** User renders 10+ clips. Only the top N that fit in viewport are visible. Scrolling does nothing. Clips below fold are permanently hidden.

**Planned fix was never wired:** `hardening.css:603–607` has a correct `.renderOutputScrollArea` scroll container defined, but the wrapper `<div>` was never added to `index.html`.

**Recommended fix (Option A — minimal, 3 CSS lines in hardening.css):**
```css
/* H-HOTFIX-2: render_output_panel — make panel the scroll container */
#render_output_panel {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
```

**Recommended fix (Option B — wires existing intent):**
1. In `index.html`, wrap `#render_output_list` in `<div class="renderOutputScrollArea">`
2. Change `review.css:32` `.renderOutputPanel { flex: 0 0 auto }` → `flex: 1`
3. The hardening.css rule for `.renderOutputScrollArea` already has the correct properties

---

### P1 — Friction / degraded UX

#### ROP-2: `.renderOutputScrollArea` dead CSS (hardening.css:603–607)

**Issue:** CSS rule for a scroll container wrapper exists with correct properties (`flex: 1 1 auto; min-height: 0; overflow-y: auto`) but the DOM element does not exist in `index.html`.

**Risk:** Maintenance confusion — looks like scrolling is handled but it isn't.

**Fix:** Either wire up the DOM element (Option B above), or remove the dead CSS rule once Option A is applied.

---

#### ROP-3: Misleading `overflow: visible` comment in hardening.css:599–602

**Issue:**
```css
/* Render output panel: ensure flex children scroll correctly */
.renderOutputPanel {
  overflow: visible;
}
```

Comment claims this ensures scroll. It does not. `overflow: visible` is the default. The actual scroll is blocked two levels up by `rs-center-stage { overflow: hidden }`.

**Fix:** Remove this rule (it's a no-op) or replace it with the real scroll fix (Option A).

---

#### ROP-4: `.rqBody` missing `overflow-x: hidden`

**File:** `css/v3/review.css:2278`

```css
.rqBody {
  flex: 1;
  overflow-y: auto;   /* ← overflow-x defaults to auto */
  ...
}
```

CSS spec: when `overflow-y` is set to non-visible and `overflow-x` is not set, `overflow-x` computes to `auto`. Result: horizontal scrollbar may appear if any `.rqSection` child is wider than the container.

**Fix:** Add `overflow-x: hidden` to `.rqBody`.

---

### P2 — Cleanup

#### ROP-5: cs_preview_area — `clamp()` uses viewport-height units

**File:** `css/v3/review.css` (portrait video wrap)

`clamp(200px, 34vh, 52%)` creates a preview height that shifts with viewport height, not just container width. This unpredictably affects renderOutputPanel's total natural height (since csPreviewArea is `flex-shrink: 0`).

**Fix:** Consider replacing `34vh` with a `%` or `cqi` (container-relative) unit so the preview size is stable relative to its parent container.

---

## ROOT CAUSE MAP

```
PRIMARY ROOT CAUSE
══════════════════
.rs-center-stage { overflow: hidden }   [workflow.css:1059]
  clips ALL content that exceeds the stage height
  ↓
  renderOutputPanel { flex: 0 0 auto }  [review.css:32]
  natural size = unbounded by parent
  ↓
  no scroll owner exists between stage and grid
  ↓
  RESULT: clips beyond viewport are invisible, not scrollable

SECONDARY — Incomplete implementation
══════════════════════════════════════
hardening.css:603-607 defines correct scroll wrapper CSS
  but DOM element (.renderOutputScrollArea) was never added to index.html
  → the fix was designed but not wired

TERTIARY — Misleading code
══════════════════════════
hardening.css:599-602 comment says "ensure scroll"
  but rule has zero effect
  → future contributors may trust it and stop looking for the real problem
```

---

## MANUAL QA CHECKLIST

These scenarios must pass after any patch is applied:

- [ ] **A.** Render 8+ clips → output panel scrolls vertically → no clipping
- [ ] **B.** Render 50+ clips → all cards reachable via scroll → no duplicate scrollbars
- [ ] **C.** Render complete → active panel (rcQueuePanel) → queue scrolls independently of output
- [ ] **D.** Resize window from narrow → full-screen → layout stable, no panel collapse
- [ ] **E.** Mouse wheel over output panel → wheel moves output, not parent page
- [ ] **F.** Portrait video preview → preview not taller than ~60% of viewport height
- [ ] **G.** Sticky output header stays pinned while scrolling clip grid
- [ ] **H.** Review queue (rqWorkspace) → rqBody scrolls → no horizontal scrollbar on standard sections

---

## FILES TO PATCH (minimal surgical list)

| File | Change | Priority |
|------|--------|----------|
| `css/v3/hardening.css:599–607` | Replace no-op `overflow: visible` + dead `.renderOutputScrollArea` with real scroll fix for `#render_output_panel` | P0 |
| `css/v3/review.css:32` | Change `flex: 0 0 auto` → `flex: 1` on `.renderOutputPanel` | P0 |
| `css/v3/review.css:2278` | Add `overflow-x: hidden` to `.rqBody` | P1 |
| `css/v3/review.css` (portrait video wrap) | Replace `34vh` with container-relative unit | P2 |

> Implementation deferred — see audit rule: patch after audit, not during.
