# RC CENTER STAGE — LAYOUT ROOT CAUSE AUDIT

**Date:** 2026-05-18  
**Branch:** feature/ai-output-upgrade  
**Scope:** Read-only audit. No CSS changes. No patches.  
**Goal:** Find the structural root causes behind clipped content, dead scroll, and competing scroll regions.

---

## 1. HEIGHT CHAIN DIAGRAM

### Outer grid: `.appShell`

```
html  (height: 100%)
└── body  (height: 100%; overflow: hidden)
    └── .appShell  (100vw × 100vh; display: grid !important)
        │
        │  grid-template-rows:
        │    Row 1:  var(--topbar-h)        =  48px   ← .appTopBar (grid-row: 1)
        │    Row 2:  minmax(0, 1fr)                   ← .rs-main   (grid-row: 2)
        │    Row 3:  var(--abp-h) = 56px              ← *** ALWAYS EMPTY ***
        │    Row 4:  var(--statusbar-h)     =  24px   ← .appStatusBar (grid-row: 4)
        │
        ├── Row 1 → .appTopBar
        ├── Row 2 → .rs-main  (display: grid; cols: sidebar | 1fr | inspector; min-height: 0)
        │           └── Col 2 → .mainArea.rs-center-panel
        │                       (display: flex; flex-direction: column; min-height: 0; overflow: hidden)
        │                       └── .rs-center-stage
        │                           (display: flex; flex-direction: column;
        │                            flex: 1; min-height: 0; overflow: hidden)
        │                           │
        │                           [SEE FULL CHAIN BELOW]
        │
        ├── Row 3 → EMPTY — no appShell direct child placed here
        └── Row 4 → .appStatusBar
```

**Row 3 is always empty.** `layout.css` intended `.appBottomPanel` at `grid-row: 3`, but the HTML
nests `.appBottomPanel` four levels deep (inside `.rs-main → .mainArea → .rs-center-stage`).
CSS grid placement is silently ignored for non-direct-children. The row still allocates 56 px.

---

### Inner column: `.rs-center-stage` — full flex chain

```
.rs-center-stage  (flex col; flex: 1; min-height: 0; overflow: hidden)
│
├── A  .rs-preview-stage
│       flex: 0 0 auto  [HOTFIX-1]        ← 0 px in render mode (editor hidden)
│
├── B  #partial_render_home
│       flex: 1  [workflow.css:662]        ← RISK: see RC-2
│       flex: 0 0 auto  [:has(>.hiddenView) — hardening.css:658]
│
├── C  #render_active_panel.renderActivePanel
│       flex: 1; min-height: 0; overflow: hidden  [runtime.css:27]
│       │
│       ├── .uxr1AiHero            (flex-shrink: 0)
│       ├── .rdCard                (flex-shrink: 0; ~100 px content)
│       ├── .aiInsightsPanel       (flex-shrink: 0; hidden when no insights)
│       └── .renderRuntimeMount
│               display: flex; flex-direction: column; overflow: hidden  [runtime.css:297]
│               flex: 1; min-height: 0  [via parent rule runtime.css:34]
│               │
│               ├── .abpToolbar         (flex-shrink: 0; height: 48 px)
│               └── .rcBottom.rcActiveQueue
│                       (flex: 1; min-height: 0; overflow: hidden;
│                        display: flex; flex-direction: column)
│                       └── .rcAQMain
│                               (display: flex; flex: 1; min-height: 0; overflow: hidden)
│                               [row direction — default]
│                               │
│                               ├── .rcQueuePanel
│                               │       flex: 0 0 62%; flex-direction: column;
│                               │       min-height: 0; overflow: hidden
│                               │       ├── .rcPanelHeader   (flex-shrink: 0; 42 px)
│                               │       ├── #rc_active_card  (flex-shrink: 0)
│                               │       └── #rc_part_cards.rcQueueGrid
│                               │               flex: 1; min-height: 0
│                               │               overflow-y: auto  ← SCROLL OWNER B ✓
│                               │
│                               └── .rcLogStrip
│                                       flex: 1; flex-direction: column;
│                                       min-height: 0; overflow: hidden
│                                       ├── .rcLogStripHeader (flex-shrink: 0)
│                                       └── .rcLogList
│                                               flex: 1; min-height: 0
│                                               overflow-y: auto  ← SCROLL OWNER C ✓
│
├── D  #render_completion_bar.renderCompletionBar
│       flex-shrink: 0  [runtime.css:1086]    ← content height when visible
│
├── E  #uxr2_completion_hero.uxr2CompletionHero
│       NO flex property  → default flex: 0 1 auto
│       display: grid                         ← content height when visible
│
├── F  #render_output_panel.renderOutputPanel
│       flex: 1; min-height: 0               [review.css:28 + hardening.css:601]
│       overflow-y: auto; overflow-x: hidden  ← SCROLL OWNER A ✓
│       │
│       ├── .renderOutputHeader   (position: sticky; top: 0; flex-shrink: 0)
│       ├── #render_output_path
│       ├── #mvRenderSummary
│       ├── .csPreviewArea
│       └── #render_output_list.renderOutputList.clipsGrid
│               display: grid; align-content: start
│               NO overflow; NO height; grows naturally
│               ← content grows; parent provides scroll containment
│
└── G  .appBottomPanel.rs-bottom-panel
        height: var(--abp-h) = 56 px  [base: workflow.css:1067]
        height: var(--abp-h-expanded) = clamp(260px,40vh,420px)
                 [when: .appShell:not(.abpCollapsed) — workflow.css:1075]
        flex-shrink: 0; overflow: hidden
        display: flex; flex-direction: column  [layout.css:410]
        │
        ├── .abpToolbar         (flex-shrink: 0; height: 48 px)
        └── .rcBottom           (flex: 1; min-height: 0; IDLE MODE only)
            └── .rcAQMain → [same subtree as C above]
```

**Dual containment:** Queue content (`.rcBottom` + children) lives in `.appBottomPanel` (idle) OR
`.renderRuntimeMount` (active render). JS switches by adding `.renderCompatWrapper` to
`.appBottomPanel` (`height: 0 !important`) and mounting the toolbar + rcBottom inside
`.renderRuntimeMount`.

---

## 2. SCROLL OWNERSHIP MAP

| Region | Expected Scroll Owner | Actual Scroll Owner | Status |
|--------|-----------------------|---------------------|--------|
| Render output clips | `#render_output_panel` | `#render_output_panel` (overflow-y: auto; flex: 1; min-height: 0) | ✓ Correct — but only when `flex: 1` resolves to non-zero height |
| Render queue cards | `#rc_part_cards.rcQueueGrid` | `#rc_part_cards.rcQueueGrid` (overflow-y: auto; flex: 1; min-height: 0) | ✓ Correct — but only when chain from `renderRuntimeMount` → `rcQueuePanel` is properly bounded |
| Render logs | `.rcLogList` | `.rcLogList` (overflow-y: auto; flex: 1; min-height: 0) | ✓ Correct — same caveat |
| `#render_output_list` inner grid | none needed | none (display: grid; grows naturally) | ✓ Correct — parent scrolls |
| `.renderOutputHeader` | sticky-fixed | `position: sticky; top: 0` inside `#render_output_panel` | ✓ Correct |

**Ownership on paper is correct.** The failures are upstream: scroll owners never receive bounded
height because their ancestor chain is broken. Scroll without a bounded ancestor = element grows to
content height, scroll bar never appears, content clips at viewport edge.

---

## 3. CSS CONFLICT TABLE

### `.appBottomPanel` — 3 files, 3 competing intents

| File | Selector | Specificity | Key declarations |
|------|----------|-------------|-----------------|
| layout.css:407 | `.appBottomPanel` | 0,1,0 | `grid-row: 3; grid-column: 1/-1;` ← **DEAD** |
| layout.css:407 | `.appBottomPanel` | 0,1,0 | `display: flex; flex-direction: column; min-height: 0; overflow: hidden; z-index: 50` |
| workflow.css:1063 | `.appBottomPanel.rs-bottom-panel` | 0,2,0 | `grid-row: unset; grid-column: unset; height: var(--abp-h); flex-shrink: 0; overflow: hidden` |
| workflow.css:1075 | `.appShell:not(.abpCollapsed) .appBottomPanel.rs-bottom-panel` | 0,3,0 | `height: var(--abp-h-expanded)` |
| hardening.css:232 | `.appBottomPanel.rs-bottom-panel` | 0,2,0 | `transition: height var(--t-base), min-height var(--t-base)` |

**Winner cascade (when `.rs-bottom-panel` class present):** workflow.css overrides layout.css for
`grid-row`/`height`/`flex-shrink`. The `display: flex; flex-direction: column` bleeds through from
layout.css (not overridden) — this is intentional and correct.

---

### `.appShell` grid rows — 3 states, 1 never fires

| File | Selector | Condition | Row 3 value |
|------|----------|-----------|-------------|
| layout.css:134 | `.appShell` | default | `var(--abp-h)` = 56 px |
| layout.css:150 | `.appShell.abp-expanded` | JS adds `abp-expanded` class | `var(--abp-h-expanded)` = 260–420 px |
| workflow.css:644 | `.appShell.abpCollapsed` | JS adds `abpCollapsed` class | `var(--abp-h)` = 56 px (same as default) |

**`abp-expanded` is DEAD CODE.** Grep of all JS files finds zero use of `abp-expanded` class toggle. JS only toggles `abpCollapsed`. The `layout.css.abp-expanded` rule never fires in production.

---

### `#render_output_panel` / `.renderOutputPanel` — hotfix overwrites base

| File | Selector | Specificity | Key declarations |
|------|----------|-------------|-----------------|
| review.css:28 | `.renderOutputPanel` | 0,1,0 | `display: flex; flex-direction: column; min-height: 0; flex: 1` |
| hardening.css:601 | `#render_output_panel` | 1,0,0 | `flex: 1; min-height: 0; overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain` |

**Winner:** hardening.css wins on specificity (ID selector). Both agree on `flex: 1; min-height: 0` — no conflict. The `overflow-y: auto` added by the hotfix is the critical fix for scroll.

---

### `.renderOutputPanel.r8StudioActive` — layout model change

| File | Selector | Key change |
|------|----------|------------|
| review.css:1857 | `.renderOutputPanel.r8StudioActive` | Switches from `display: flex` → `display: grid; grid-template-columns: 1fr 220px; grid-template-rows: auto` |

When `r8StudioActive` is active, `#render_output_panel` becomes a grid container. The
`overflow-y: auto; flex: 1; min-height: 0` from hardening.css still applies (those are layout-
participation properties, not display-type properties). The switch is safe **as long as the
ancestor chain still bounds the height** — which requires RC-2 to be fixed.

---

### `.rcQueuePanel` — two valid state variants, no conflict

| File | Selector | Condition | Value |
|------|----------|-----------|-------|
| runtime.css:514 | `.rcQueuePanel` | default | `flex: 0 0 62%` |
| runtime.css:539 | `.renderActivePanel.logsCollapsed .rcQueuePanel` | logs hidden (active panel) | `flex: 0 0 100%` |
| runtime.css:540 | `.appBottomPanel.logsCollapsed .rcQueuePanel` | logs hidden (idle panel) | `flex: 0 0 100%` |
| runtime.css:2932 | `#render_active_panel[data-render-state="running"] .rcQueuePanel` | running | `flex: 0 0 70%` |

No conflicts. Both containment paths handled. ✓

---

## 4. DEAD CSS

| Rule | File:Line | Why it's dead |
|------|-----------|--------------|
| `.appShell.abp-expanded { grid-template-rows: ... var(--abp-h-expanded) ... }` | layout.css:150 | JS never adds `abp-expanded` class to `.appShell`. Only `abpCollapsed` is toggled. |
| `.appBottomPanel { grid-row: 3; grid-column: 1 / -1 }` | layout.css:407 | `.appBottomPanel` is nested 4 levels inside `.rs-main` — CSS grid placement only works for direct children of the grid container. The declarations have zero effect. |
| `#render_active_panel[...] #render_output_panel { opacity: .78/.55/1 }` | runtime.css:2111,2136,2152 | `#render_output_panel` is a SIBLING of `#render_active_panel` in the HTML (not a descendant). The descendant selector never matches. These rules from Phase P2.9 target a DOM relationship that does not exist. |
| `.appShell.abpCollapsed { grid-template-rows: ... var(--abp-h) ... }` | workflow.css:644 | Row values are identical to the default `.appShell` rule (56 px). Overriding with the same value is a no-op. |

---

## 5. WINNING SELECTORS (effective computed values)

### `.appBottomPanel.rs-bottom-panel` — expanded state (default)

```css
/* From layout.css .appBottomPanel (0,1,0) — NOT overridden */
display: flex;
flex-direction: column;
background: var(--bg-800);
border-top: 1px solid var(--border-subtle);
overflow: hidden;
min-height: 0;
z-index: 50;
position: relative;

/* From workflow.css .appBottomPanel.rs-bottom-panel (0,2,0) */
grid-row: unset;      /* cancels layout.css grid-row: 3 */
grid-column: unset;   /* cancels layout.css grid-column: 1/-1 */
flex-shrink: 0;       /* WINS over default flex-shrink: 1 */
overflow: hidden;     /* same as layout.css */

/* From workflow.css :not(.abpCollapsed) rule (0,3,0) — when panel expanded */
height: clamp(260px, 40vh, 420px);
```

### `#render_output_panel` — clips showing state

```css
/* From review.css .renderOutputPanel (0,1,0) */
display: flex;
flex-direction: column;
/* flex: 1 — OVERRIDDEN by hardening.css (same value, no fight) */

/* From hardening.css #render_output_panel (1,0,0) — wins all */
flex: 1;
min-height: 0;
overflow-y: auto;
overflow-x: hidden;
overscroll-behavior: contain;
```

### `#rc_part_cards.rcQueueGrid` — queue scroll owner

```css
/* From runtime.css #rc_part_cards.rcQueueGrid (1,1,0) */
flex: 1;
overflow-y: auto;
overflow-x: hidden;
min-height: 0;
scrollbar-width: thin;
scrollbar-color: rgba(255,255,255,.09) transparent;
```

---

## 6. ROOT CAUSE ANALYSIS

### RC-1 [CRITICAL] — Empty grid row 3 permanently steals 56 px

**Location:** layout.css:134–156  
**Mechanism:**

```
.appShell grid:  Row 1 (48px) + Row 2 (1fr) + Row 3 (56px) + Row 4 (24px)
                                                     ↑
                           ALWAYS EMPTY — no direct .appShell child placed here
```

`.rs-main` (row 2) gets `1fr = viewport − 48 − 56 − 24 = viewport − 128 px`.

With the bottom panel also living *inside* row 2 (taking up to 420 px), the effective render
output panel height on a 900 px viewport is:

```
900 − 128 (grid overhead) − 360 (panel at 40 vh) = 412 px
```

If `.abp-expanded` were ever applied (dead code), row 3 would also balloon to 260–420 px, reducing
`.rs-main` to `viewport − 128 − 420 = 352 px` — then the panel ALSO takes 420 px, leaving the
output panel with approximately 0 px.

**Impact:** 56 px permanently stolen. On small viewports (768 px), every pixel matters.

---

### RC-2 [CRITICAL] — `#partial_render_home` flex:1 not reliably suppressed

**Location:** workflow.css:660–666 + hardening.css:658–660  

**Mechanism:**

```css
/* workflow.css — base rule */
#partial_render_home { flex: 1; ... }

/* hardening.css HOTFIX-2 — override */
#partial_render_home:has(> .hiddenView) { flex: 0 0 auto; }
```

The `:has(> .hiddenView)` override fires ONLY when `#partial_render_home`'s **direct child**
(`#render_home_panel`) has `hiddenView` class. If JS adds `hiddenView` to the wrapper
(`#partial_render_home` itself) rather than the child, or if the panel is removed/emptied without
the `hiddenView` class being set on the child, the override never fires.

**Failure chain when override doesn't fire:**

```
#partial_render_home   flex: 1  — steals ~50% of rs-center-stage
#render_active_panel   flex: 1  — gets remaining ~50%
  → renderRuntimeMount gets (50% − rdCard height)
    → rcBottom gets (small bounded height)
      → rcQueuePanel too short to scroll → dead scroll
      
OR

#render_output_panel   flex: 1  — gets ~50% instead of ~100%
  → clips grid fits ~4 rows before clipping
```

**This is the primary scroll ownership conflict.** Two `flex: 1` siblings share the height that
should belong to one owner.

---

### RC-3 [HIGH] — Dual containment architecture: queue content changes parent at runtime

**Location:** runtime.css (E-0, E-4), workflow.css (appBottomPanel.renderCompatWrapper)

**Two modes for the same DOM subtree:**

| Mode | Container | Height source |
|------|-----------|--------------|
| IDLE / post-render | `.appBottomPanel.rs-bottom-panel` | `height: clamp(260px,40vh,420px); flex-shrink: 0` |
| ACTIVE RENDER | `.renderRuntimeMount` inside `#render_active_panel` | `flex: 1; min-height: 0` (via parent rule) |

JS switches modes by:
1. Adding `.renderCompatWrapper` to `.appBottomPanel` → `height: 0 !important; overflow: hidden; visibility: hidden`  
2. Moving `.abpToolbar + .rcBottom` into `.renderRuntimeMount`

**Failure modes:**
- **Race condition:** JS adds `renderCompatWrapper` but hasn't completed the mount yet → queue content
  disappears from DOM during transition → visual flash, scroll owner briefly has 0 px height
- **Wrong container after transition:** If the JS state machine enters an unexpected path (e.g., render
  cancelled mid-start), `renderCompatWrapper` may stay on `.appBottomPanel` while the mount never
  happened → queue is invisible
- **CSS ancestor mismatch:** `.rcBottom` flex:1 resolves differently in each container. In
  `.appBottomPanel` (fixed height), `flex: 1` fills fixed space. In `.renderRuntimeMount` (flex:1),
  `flex: 1` fills proportional space. If the JS partially completes the move, the wrong CSS context
  applies.

---

### RC-4 [MEDIUM] — CSS cascade drift across phases: same selectors in 3+ files

**Mechanism:** Each phase added rules for the same selectors in different files without removing
the earlier rules. The cascade only works because specificity ordering happens to produce the right
result — but future phases can silently break this.

**Affected selectors and file count:**

| Selector | Files with rules | Winner |
|----------|-----------------|--------|
| `.appBottomPanel` layout intent | layout.css, workflow.css, hardening.css | workflow.css overrides by specificity |
| `.appShell` grid row 3 | layout.css (3 rules), workflow.css (1 rule) | workflow.css `abpCollapsed` = same value as default → effectively no winner needed |
| `#render_output_panel` / `.renderOutputPanel` | review.css, hardening.css | hardening.css wins by ID specificity |
| `.rcQueuePanel` | runtime.css (base + 3 state variants) | deterministic by specificity ✓ |

**Dead CSS left in place from layout.css Phase A intent:**
```css
/* layout.css:407 — these two lines do nothing */
grid-row: 3;
grid-column: 1 / -1;
```

---

### RC-5 [LOW] — `#uxr2_completion_hero` has no flex property

**Location:** runtime.css:2515  

When visible, `.uxr2CompletionHero` defaults to `flex: 0 1 auto` (browser default). Its
`display: grid; grid-template-columns: 180px 1fr auto` drives its intrinsic height from content.
If the grid rows auto-size to large thumbnails, this element takes uncontrolled height in the
`rs-center-stage` column, pushing `#render_output_panel` down and reducing its available height.

**Mitigation:** Adding `flex-shrink: 0` makes the behavior explicit and prevents unintended height
competition with other `flex: 1` siblings.

---

## 7. MINIMAL PERMANENT FIX

### Fix F-1: Remove empty grid row 3 from `.appShell` *(eliminates RC-1)*

**File:** layout.css  
**Change:** Collapse 4-row grid to 3-row. Remove the wasted row entirely.

```css
/* BEFORE (layout.css:137) */
.appShell {
  grid-template-rows:
    var(--topbar-h)
    minmax(0, 1fr)
    var(--abp-h)          ← DELETE THIS ROW
    var(--statusbar-h);
}

/* AFTER */
.appShell {
  grid-template-rows:
    var(--topbar-h)
    minmax(0, 1fr)
    var(--statusbar-h);
}
```

Also remove:
- `layout.css:150` — `.appShell.abp-expanded { grid-template-rows: ... }` (dead code)
- `layout.css:407` — `grid-row: 3; grid-column: 1 / -1` from `.appBottomPanel` (dead placement)
- `workflow.css:644` — `.appShell.abpCollapsed { grid-template-rows: ... }` (no-op override)

**Gain:** 56 px returned to center content at all times.

---

### Fix F-2: Replace fragile `:has()` with explicit class toggle *(eliminates RC-2)*

**Files:** hardening.css + JS that manages render state  
**Change:** Add a CSS class `is-render-active` to `.rs-center-stage` (or `body`) when a render
job is active. Use it instead of the fragile `:has()` selector.

```css
/* Replace hardening.css:658 */
#partial_render_home:has(> .hiddenView) {
  flex: 0 0 auto;
}

/* With — covers all cases: :has() + explicit class */
#partial_render_home:has(> .hiddenView),
.is-render-active #partial_render_home,
.is-render-output #partial_render_home {
  flex: 0 0 auto;
}
```

This ensures `#partial_render_home` releases its `flex: 1` claim whenever any other center-stage
panel is the primary owner, without depending on a single DOM event setting `hiddenView` on the
exact right element.

---

### Fix F-3: Remove dead CSS *(eliminates RC-4 drift)*

Delete these rules completely:

```
layout.css:150   .appShell.abp-expanded { ... }
layout.css:408   grid-row: 3;
layout.css:409   grid-column: 1 / -1;
runtime.css:2111 #render_active_panel[data-render-state="running"] #render_output_panel { ... }
runtime.css:2136 #render_active_panel[data-render-state="complete"] #render_output_panel { ... }
runtime.css:2152 #render_active_panel.p29Arrival #render_output_panel { ... }
workflow.css:644 .appShell.abpCollapsed { grid-template-rows: ... }  (no-op)
```

---

### Fix F-4: Explicit flex-shrink on `#uxr2_completion_hero` *(eliminates RC-5)*

**File:** runtime.css:2515  
**Change:**

```css
/* BEFORE */
.uxr2CompletionHero {
  display: grid;
  grid-template-columns: 180px 1fr auto;
  ...
}

/* AFTER — add */
.uxr2CompletionHero {
  display: grid;
  grid-template-columns: 180px 1fr auto;
  flex-shrink: 0;    ← ADD: explicit, prevents height competition
  ...
}
```

---

### Fix F-5: RC-3 architecture — document the JS contract *(mitigates RC-3)*

The dual-containment model is architecturally valid but fragile. The contract that must be
enforced atomically in JS:

```
WHEN entering active-render state:
  1. Add .renderCompatWrapper to .appBottomPanel          (collapses static panel)
  2. Move .abpToolbar + .rcBottom into .renderRuntimeMount (mounts in new container)
  Both steps must complete in the SAME animation frame / microtask.

WHEN exiting active-render state:
  1. Move .abpToolbar + .rcBottom BACK to .appBottomPanel
  2. Remove .renderCompatWrapper from .appBottomPanel
  Both steps must complete in the SAME animation frame / microtask.
```

If either step is async and interleaved with a repaint, a frame will have two competing
height contexts for the queue subtree. No CSS fix can prevent a layout flash that originates
from an async JS state transition.

---

## 8. SUCCESS CRITERIA

After applying F-1 through F-4:

| Symptom | Root Cause | Expected result after fix |
|---------|-----------|--------------------------|
| `rcQueuePanel no scroll` | RC-2 (`#partial_render_home flex:1` steals height), RC-3 (wrong container) | `#rc_part_cards.rcQueueGrid` receives bounded height via a clean chain; scrollbar appears when cards overflow |
| `render_output_list clipped` | RC-1 (−56 px) + RC-2 (−50% height from competing flex:1) | `#render_output_panel` gets correct `flex: 1` share of center-stage height; clips grid fully scrollable |
| `render_output_panel broken` | Same as above + RC-4 drift | `overflow-y: auto` scroll owner properly bounded; sticky header stays pinned |
| `scroll ownership conflicts` | RC-2 — multiple `flex: 1` siblings visible simultaneously | Single `flex: 1` owner per mode; all other siblings are `flex: 0 0 auto` or `flex-shrink: 0` |
| 56 px phantom gap (subtle) | RC-1 | Removed entirely after 3-row grid fix |

---

## APPENDIX: Token values at time of audit

```
--topbar-h:         48px
--abp-h:            56px   (collapsed height, also the wasted grid row)
--abp-h-expanded:   clamp(260px, 40vh, 420px)
--statusbar-h:      24px
```

**Height budget on 900 px viewport (current — broken):**
```
Row 1 topbar:      48 px
Row 2 rs-main:    772 px   (= 900 − 48 − 56 − 24)
Row 3 empty:       56 px   ← WASTED
Row 4 statusbar:   24 px

Inside rs-main (772 px):
  bottom panel (expanded):   360 px  (40 vh at 900 px)
  render output panel:       412 px  ← what's left
```

**Height budget on 900 px viewport (after F-1 fix):**
```
Row 1 topbar:      48 px
Row 2 rs-main:    828 px   (= 900 − 48 − 24)   +56 px recovered
Row 4 statusbar:   24 px

Inside rs-main (828 px):
  bottom panel (expanded):   360 px
  render output panel:       468 px  ← 56 px more
```

**Height budget on 768 px viewport (after F-1 + F-2 fix, panel expanded):**
```
rs-main:   696 px  (= 768 − 48 − 24)
panel:     307 px  (40 vh)
output:    389 px  ← workable for clips grid
```

---

*Audit complete. No CSS was modified. All findings above are read-only analysis.*
