# PHASE UX-1B — Video Editor Reduction Plan

**Type:** UI/UX Reduction Plan — NOT implementation, NOT redesign
**Date:** 2026-05-20
**Source of truth:** PHASE_UX1A_VIDEO_EDITOR_AUDIT.md + PHASE_UX1A_R2_EDITOR_REDUCTION_AND_VIDEOLOCAL_AUDIT.md
**Constraint:** Every decision ties back to a named audit finding. Nothing invented.

---

## 1. Executive Summary

The Video Editor has 6 tabs, ~17 visible decision points in the Export tab alone, three unrelated preset systems with no hierarchy, and core controls (Min/Max duration, Aspect Ratio) buried inside an Advanced fold most creators never open. The editor works. The pipeline is solid. The friction is structural.

**This plan reduces visible complexity through four mechanisms:**

1. **Collapse 6 tabs → 4 tabs** by merging three low-use tabs (Words, Audio, AI) and creating a "More" bucket for rarely-needed settings. No controls are removed — they are relocated.
2. **Clean Export tab internals** by moving non-render concerns out (Render Settings, Editor Performance, Batch Queue) and improving visual hierarchy of what remains.
3. **Fix Subtitle tab** by replacing the misleading static preview with a live-preview callout, hiding the X Position slider from primary view, and relabeling Y Pos to something meaningful.
4. **Label and tooltip pass** on all controls that currently require product vocabulary to interpret.

**What this plan explicitly does NOT do:**
- Consolidate the three preset systems (Quick Presets / Creator Presets / Expert Preset) — separate phase
- Surface Min/Max duration above the Advanced fold — requires dirty-flag infrastructure that does not exist
- Change any backend behavior
- Touch the VideoLocal render flow
- Remove any control from the product entirely

**Expected result:** Creator opening the editor sees 4 tabs with clear names. Export tab shows 5–6 primary controls instead of 17. Subtitle tab shows live preview context instead of a misleading static block. Every label reads in plain creator language.

---

## 2. Final Tab Model

### 2.1 Decision Table

```
CURRENT: Story
DECISION: Rename → Edit + absorb Words + absorb AI
WHY: "Story" is conceptual vocabulary. Creators think "trim" and "edit." Words and AI are both editorial actions — they belong alongside Trim and Quick Styles, not as separate tabs. (UX1A §3.1, UX1A-R2 §3.1, §3.3, §3.6)
RISK: LOW — Rename is text-only. AI merge has no runtime side effects. Words merge requires EditorTextRuntime.onTabActivate() to move to 'mode' trigger; documented in UX1A-R2 §4.2.

CURRENT: Subtitles
DECISION: Keep — unchanged tab identity
WHY: 9+ visible controls. Cannot merge into Export (already overloaded) or Edit (different mental model — styling is output, not editorial). (UX1A-R2 §3.2)
RISK: NONE — no structural change to this tab's identity. Internal cleanup is in Section 5.

CURRENT: Words
DECISION: Merge into Edit tab
WHY: Consistently low use. AI Narration is off by default and requires voice setup — not a first-session concern. Text Layers is a power feature. Both belong in an editorial tab, not a dedicated one. (UX1A-R2 §3.3)
RISK: LOW — data-insp-panel attribute change + EditorTextRuntime.onTabActivate() trigger must move to 'mode'. Text-layers auto-open behavior must NOT fire on every Edit tab entry (UX1A-R2 §4.2 detail).

CURRENT: Audio
DECISION: Merge into More tab
WHY: Low use. Source audio volume is rarely changed. BGM is off by default. Loudness normalization is always-on and never manually changed. Audio is a technical output concern, not an editorial concern. (UX1A-R2 §3.4)
RISK: MEDIUM — EditorAudioRuntime.onTabActivate() currently fires on 'audio' tab entry. Must fire on 'more' tab entry instead. If omitted, BGM and volume controls appear but fail to initialize. (UX1A-R2 §10, specific JS block at §4.3)

CURRENT: Export (internal ID: 'performance')
DECISION: Keep — move non-render content out, keep render config in
WHY: High use for QS Bar and Max clips. The tab is overloaded, but the solution is removing non-render concerns (Render Settings, Editor Performance, Batch Queue), not removing the tab. (UX1A-R2 §3.5)
RISK: MEDIUM — Moving Render Settings out requires EditorPerformanceRuntime triggers to move. Existing auto-expand behavior (evSetInspGroupOpen('performance', true)) must stop firing on Export tab. (UX1A-R2 §4.3)

CURRENT: AI
DECISION: Merge into Edit tab — place conversational panel at bottom of Edit
WHY: Low use. Most creators don't know this tab exists. The conversational panel belongs at the end of a natural editorial flow: Trim → Quick Styles → AI Actions → Chat. (UX1A-R2 §3.6)
RISK: LOW — No runtime tab-switch side effects for AI tab. Safest merge in the plan. (UX1A-R2 §4.1)

NEW: More
DECISION: Create — receives Audio + Render Settings + Editor Performance + Batch Queue
WHY: Known UX pattern for rarely-needed settings. Creators accept a "More" bucket. This removes low-priority items from the primary work surface without deleting them. (UX1A-R2 §2, §5.5)
RISK: LOW — Adding new tab to validTabs/tabTitles. No existing code breaks. EditorAudioRuntime and EditorPerformanceRuntime triggers must be updated to fire on 'more'.
```

### 2.2 Resulting Tab Structure

```
Before: Story | Subtitles | Words | Audio | Export | AI     (6 tabs)
After:  Edit  | Subtitles | Export | More                    (4 tabs)
```

```
Edit tab contains:
  - Trim section (from Story)
  - Quick Styles — 4 looks (from Story)
  - AI Edit Actions — collapsed group (from Story)
  - Edit History — collapsed group (from Story)
  - Creator Memory panel (from Story)
  - AI Narration — collapsed (from Words)
  - Text Layers — collapsed group (from Words)
  - Conversational AI panel — at bottom (from AI)

Subtitles tab contains: (unchanged structure, internal cleanup in §5)
  - Auto subtitle toggle
  - Style / Font / Size / Color / Highlight / Y Position / Outline controls
  - Live preview callout (replaces static preview — see §5)
  - AI Fix Subs, Translate

Export tab contains: (non-render concerns removed — see §4)
  - Quick Presets — collapsed (stays)
  - Creator Presets bar — cpBar (stays)
  - QS Bar: Platform / Subtitle / Structure (stays)
  - Max clips (stays)
  - Aspect Ratio read-only badge (new — §4 above fold)
  - Duration range read-only hint (new — §4 above fold)
  - Advanced fold (stays — contents in §4)

More tab contains: (new — receives relocated items)
  - Audio group: Source volume, BGM, Loudness (from Audio tab)
  - Render Settings: Device, FPS, Smart Crop (from Export tab)
  - Editor Performance: health banner, hover previews, filmstrip, waveform (from Export tab)
  - Batch Queue: drag-drop file queue (from Export tab)
```

---

## 3. Inside Each Tab — Full Cleanup Plan

### 3.1 Edit Tab (was: Story)

All original Story tab content stays. Words and AI content is added below.

```
CURRENT: Tab label "Story"
DECISION: Rename → "Edit"
STATE: visible (tab button text only)
REPLACEMENT: "Edit"
WHY: "Story" is product-internal vocabulary. Creators think "I need to edit / trim." (UX1A §3.1, UX1A-R2 §3.1)
RISK: LOW — text change to tab button only; data-insp-tab="mode" value unchanged

CURRENT: Trim section (always visible)
DECISION: Keep — no change
STATE: visible
REPLACEMENT: n/a
WHY: Core control, high use, correct placement. (UX1A §6.1)
RISK: NONE

CURRENT: Quick Styles — 4 look cards
DECISION: Keep — no change
STATE: visible
REPLACEMENT: n/a
WHY: Core editorial control. High use. Correct placement. (UX1A §6.1)
RISK: NONE

CURRENT: AI Edit Actions — collapsed group
DECISION: Keep — no change
STATE: collapsed (default unchanged)
REPLACEMENT: n/a
WHY: Secondary feature, correct position. (UX1A §6.1)
RISK: NONE

CURRENT: Edit History — collapsed group
DECISION: Keep — no change
STATE: collapsed (default unchanged)
REPLACEMENT: n/a
WHY: Passive reference, fine where it is.
RISK: NONE

CURRENT: Creator Memory panel (bottom of Story tab)
DECISION: Keep — no change
STATE: as-is
REPLACEMENT: n/a
WHY: Locked. Not in audit scope for restructuring.
RISK: NONE

CURRENT: AI Narration section (data-insp-panel="text")
DECISION: Move to Edit tab — data-insp-panel="text" → "mode"
STATE: collapsed (do NOT auto-expand on Edit tab entry)
REPLACEMENT: Same controls, same behavior, new tab home
WHY: Low use. Off by default. Correct to have in Edit alongside other creative controls, not a dedicated tab. (UX1A-R2 §3.3)
RISK: LOW — attribute change + EditorTextRuntime.onTabActivate() must fire on 'mode' tab entry (not 'text')

CURRENT: Text Layers — collapsed group (data-insp-panel="text")
DECISION: Move to Edit tab — data-insp-panel="text" → "mode"
STATE: collapsed — do NOT auto-open text layers group when creator enters Edit tab
REPLACEMENT: Same controls, same behavior, new tab home
WHY: Power-user feature, correct in Edit tab. Auto-open on tab entry would surprise creators who are not using text layers. (UX1A-R2 §4.2)
RISK: LOW — attribute change + remove auto-open behavior from Edit tab activation (keep only conditional auto-open when creator explicitly expands)

CURRENT: Conversational AI panel (data-insp-panel="ai")
DECISION: Move to Edit tab — data-insp-panel="ai" → "mode" — place at bottom of tab
STATE: visible — placed below AI Edit Actions, at bottom of tab scroll
REPLACEMENT: Same controls, same behavior, new tab home
WHY: No runtime side effects. Low use. Natural flow: Trim → Styles → Actions → Chat. (UX1A-R2 §3.6, §4.1)
RISK: LOW — safest merge in the plan

CURRENT: Words tab button in tabbar
DECISION: Remove button
STATE: removed
REPLACEMENT: Content merged to Edit tab
WHY: No standalone tab needed for Words content (UX1A-R2 §3.3)
RISK: LOW

CURRENT: AI tab button in tabbar
DECISION: Remove button
STATE: removed
REPLACEMENT: Content merged to Edit tab
WHY: No standalone tab needed for conversational panel (UX1A-R2 §3.6)
RISK: LOW
```

---

### 3.2 Subtitles Tab — Structural Items

Content cleanup is covered separately in Section 5. Only tab-level structural decisions here.

```
CURRENT: Subtitles tab — standalone
DECISION: Keep as standalone tab
STATE: unchanged
REPLACEMENT: n/a
WHY: 9+ controls, distinct mental model from Edit and Export. (UX1A-R2 §3.2)
RISK: NONE
```

---

### 3.3 Export Tab — Structural Items

Internal content is covered in Section 4. Only structural decisions (what moves out).

```
CURRENT: Render Settings — collapsed group (data-insp-panel="performance")
DECISION: Move to More tab — data-insp-panel="performance" → "more"
STATE: collapsed (default unchanged in More tab)
REPLACEMENT: Same controls (Device, FPS, Reframe Mode) in More tab
WHY: Render Settings is an advanced technical concern. It has no reason to share space with QS Bar and platform selection. (UX1A §6.1, UX1A-R2 §3.5)
RISK: MEDIUM — EditorPerformanceRuntime.onTabActivate() currently fires on 'performance' tab entry via auto-expand trigger. Must move to 'more' tab trigger. Existing evSetInspGroupOpen('performance', true) auto-expand on Export tab entry must be removed.

CURRENT: Editor Performance section — always visible in Export tab (data-insp-panel="performance")
DECISION: Move to More tab — data-insp-panel="performance" → "more"
STATE: visible in More tab (retains always-visible behavior)
REPLACEMENT: Same controls (health banner, hover previews, filmstrip, waveform) in More tab
WHY: Editor performance tuning is an advanced/support concern. It does not belong on the same tab as platform selection and preset configuration. (UX1A §6.1, §8.3 point 8)
RISK: MEDIUM — EditorPerformanceRuntime.onTabDeactivate() must fire when creator leaves 'more' tab (not 'performance' tab). IDs must remain unchanged: edPerfHealthBanner, edPerfHoverPreview, edPerfFilmstrip, edPerfWaveform.

CURRENT: Batch Queue section — bqSection (data-insp-panel="performance")
DECISION: Move to More tab — data-insp-panel="performance" → "more"
STATE: visible in More tab
REPLACEMENT: Same drag-drop file queue in More tab
WHY: Batch Queue is a power feature. Placing it alongside QS Bar and platform pills creates visual confusion between primary render controls and multi-file batch processing. (UX1A §3.7, UX1A-R2 §4.4)
RISK: LOW — BatchQueue module addresses bqSection by ID, not by tab. Moving preserves the ID. Drag-over behavior is attribute-bound, not tab-bound.

CURRENT: Market & Target — collapsed group (top area of Export tab, before cpBar)
DECISION: Move inside Advanced fold
STATE: collapsed inside Advanced fold (below Expert Preset section)
REPLACEMENT: Same controls (mvMarket, mvAutoBestClips, mvKeywordHighlight, mvBestExportEnabled) moved deeper
WHY: Market & Target is used by regional/professional creators. It has no place above the Creator Presets bar for a general creator audience. Moving it inside Advanced with Expert Preset reduces top-of-tab clutter. (UX1A §8.3 point 9)
RISK: MEDIUM — mvMarket, mvAutoBestClips, mvKeywordHighlight, mvBestExportEnabled IDs must remain in DOM. mvHandleChange() and mvHandleAutoBestClips() event handlers are ID-based — moving the section is safe if IDs are preserved.
```

---

### 3.4 More Tab — New Tab Contents

```
CURRENT: (no More tab)
DECISION: Create More tab with data-insp-tab="more" button in tabbar
STATE: new tab visible in tabbar
REPLACEMENT: n/a (new)
WHY: Standard pattern for rarely-needed settings. Avoids deleting any controls while cleaning primary surface. (UX1A-R2 §2)
RISK: LOW — validTabs + tabTitles update in setInspectorTab()

CURRENT: Audio tab content (data-insp-panel="audio")
DECISION: Move to More tab — data-insp-panel="audio" → "more"
STATE: Audio group collapsed by default (or opened on More tab entry — see below)
REPLACEMENT: Same controls (Source volume, BGM, Loudness) in More tab under "Audio" group header
WHY: Low use. Defaults work for most creators. Audio mix is a technical output concern. (UX1A-R2 §3.4)
RISK: MEDIUM — EditorAudioRuntime.onTabActivate() currently fires on 'audio' tab entry. After move, must fire on 'more' tab entry. If this call is omitted, audio controls render but fail to initialize (lazy-init not called). This is the highest-risk single JS update in the plan.

CURRENT: Audio tab button in tabbar
DECISION: Remove button
STATE: removed
REPLACEMENT: Audio content moved to More tab
WHY: No standalone tab needed (UX1A-R2 §3.4)
RISK: LOW (after EditorAudioRuntime trigger update is confirmed)

CURRENT: Render Settings in Export tab
DECISION: Receives render settings content from Export tab
STATE: collapsed in More tab
REPLACEMENT: Device, FPS, Smart Crop (relabeled from Reframe Mode)
WHY: Follows from Export tab structural cleanup (see §3.3 above)
RISK: MEDIUM (same as Export tab side — EditorPerformanceRuntime triggers)

CURRENT: Editor Performance in Export tab
DECISION: Receives editor performance content from Export tab
STATE: visible in More tab (retains always-visible behavior)
REPLACEMENT: health banner, hover previews, filmstrip, waveform controls
WHY: Follows from Export tab structural cleanup
RISK: MEDIUM (EditorPerformanceRuntime.onTabDeactivate() must fire on More tab exit)

CURRENT: Batch Queue in Export tab
DECISION: Receives batch queue from Export tab
STATE: visible in More tab
REPLACEMENT: drag-drop file queue section, same behavior
WHY: Follows from Export tab structural cleanup
RISK: LOW (ID-based, not tab-based)
```

---

## 4. Export Tab Simplification

The Export tab remains the most complex single panel in the product. This section defines the three-layer visual hierarchy within it after all non-render concerns are removed.

### 4.1 Layer Definition

```
ABOVE FOLD (always visible, primary decisions):
─────────────────────────────────────────────────
  Creator Presets bar (cpBar)          — user's saved configurations (always visible)
  QS Bar:
    Platform:   [YouTube] [TikTok] [Reels]
    Subtitle:   [Off] [Clean] [Viral] [Karaoke]
    Structure:  [More Hook] [Balanced] [More Story]  ← with tooltips (see below)
  Max clips:  [  6  ]
  ─────────────────────────────────────
  Aspect Ratio:  (read-only badge — shows current value, e.g. "9:16 ✓")
  Clip length:   (read-only hint — e.g. "Clips: 61s – 180s")

SECONDARY (collapsed <details>, visible but not open by default):
─────────────────────────────────────────────────────────────────
  [▸ Quick Presets — starting points (4)]    ← relabeled for clarity

ADVANCED fold (user must open — existing Advanced fold):
────────────────────────────────────────────────────────
  Expert Preset:     [— Manual —  ▾]
  Market & Target:   (moved in from top of Export — see §3.3)
  Aspect Ratio:      [16:9 ▾]           ← actual control (badge above is read-only display)
  Render quality:    [Balanced ▾]        ← relabeled from "Output Profile"
  Shortest clip:     [61]               ← relabeled from "Min clip (s)"
  Longest clip:      [180]              ← relabeled from "Max clip (s)"
  Multi-variant render:  [ ] checkbox
  Add ending CTA:        [ ] checkbox + type select
  Title Overlay:         [ ] checkbox + text input
  Creator Assets:        Logo / Intro / Outro / Music
  Batch Mode (URLs):     [ ] checkbox + URL textarea
```

### 4.2 Above-Fold Changes in Detail

**QS Bar — reorder:** QS Bar moves above cpBar in visual order (QS Bar is used more frequently than cpBar). HTML reorder only — no JS change. IDs unchanged.

**Structure pill tooltips:**
```
CURRENT: More Hook / Balanced / More Story — no explanation visible
DECISION: Add title="..." attributes to each pill
WHY: "Hook" and "Story" require product vocabulary. A creator unfamiliar with the product will guess randomly. title= attribute is zero-risk — pure HTML, no JS. (UX1A §3.6)
RISK: LOW

Specific tooltip text:
  More Hook:   title="Selects more clips from the intro — stronger attention-grabbing opening segments"
  More Story:  title="Selects more clips from the body — narrative arc over hook density"
  Balanced:    title="Default — equal weight between hook and story clips"
```

**Aspect Ratio read-only badge (above fold):**
```
CURRENT: Aspect Ratio is in Advanced fold. Creator clicks TikTok → ratio changes to 9:16 → no visible feedback in Export tab without opening Advanced.
DECISION: Add a read-only display badge above fold showing current evAspectRatio value.
  Example: "9:16 ✓" when TikTok/Reels is selected; "16:9" for YouTube; custom value otherwise.
WHY: Silent state change is the problem (UX1A §3.4). A read-only badge confirms to the creator that the pill click updated something without exposing the actual control above fold.
RISK: LOW — pure HTML display element, no form value, no payload impact. JS to update it reads evAspectRatio.value on QS Bar interaction (evQsSet already fires on pill click — add badge update there).
```

**Duration range read-only hint (above fold):**
```
CURRENT: Min/Max duration hidden in Advanced fold. Creator never sees the range unless they open Advanced.
DECISION: Add a single read-only line above fold: "Clips: 61s – 180s" (reflecting evMinPart and evMaxPart current values). Updates when Advanced is changed.
WHY: Core discovery parameters buried in Advanced. When clips come out wrong length, creator doesn't know where to look. The read-only line surfaces the current state without elevating the control. (UX1A §3.5, §6.2)
RISK: LOW — display only. JS reads evMinPart.value and evMaxPart.value to populate. No form value. No payload impact. These inputs already fire on change; add display update there.
NOTE: Full elevation of evMinPart/evMaxPart above the fold (as actual controls) requires _evMinPartTouched/_evMaxPartTouched dirty flag infrastructure that does not yet exist. That is out of scope. (UX1A §10.3)
```

**Quick Presets label update:**
```
CURRENT: <summary>Quick Presets (4)</summary>
DECISION: <summary>Quick Presets — starting points (4)</summary>
WHY: Three preset systems exist with no hierarchy. Adding a parenthetical description ("starting points" vs "your saved settings" vs "named technical configs") provides basic differentiation without restructuring. (UX1A §3.3, §8.1)
RISK: LOW — summary text change only
```

### 4.3 Export Tab — What Moves Out vs What Stays

| Item | Before | After | Why |
|---|---|---|---|
| Quick Presets | top, collapsed | stays — above fold as secondary | Low risk, gives starting-point context |
| Market & Target | top, collapsed | moves into Advanced fold | Rarely used; clutters top area (UX1A §8.3 point 9) |
| Creator Presets bar (cpBar) | always visible | stays — above fold, primary | High use, power-user anchor |
| QS Bar | always visible | stays — above fold, primary; moves above cpBar | Primary control surface |
| Max clips | always visible | stays — above fold, primary | Core setting |
| Aspect Ratio badge (new) | absent | added — read-only display above fold | Silent state change fix |
| Duration hint (new) | absent | added — read-only display above fold | Buried core params made visible |
| Advanced fold | stays | stays — contents updated (Market & Target added) | Unchanged mechanism |
| Batch Queue | after Render Settings | moves to More tab | Non-render concern |
| Render Settings | collapsed, after Advanced | moves to More tab | Technical/rarely-used |
| Editor Performance | always visible, after Render Settings | moves to More tab | Support/advanced concern |

---

## 5. Subtitle UX Plan

Grounded in UX1A §4 findings. No control is removed from the product — only relabeled or repositioned.

### 5.1 Static Preview — Remove in Favor of Live Video Callout

```
CURRENT: Static "Preview subtitle" text at bottom of Subtitles tab, styled with current font/size/color.
PROBLEM: The live subtitle overlay (evSubOverlay) on the video frame IS rendering subtitles in real time. The creator is reading the small static inspector preview instead of the large video on the left. The live preview exists but is invisible in practice. (UX1A §4.2)
DECISION: Remove the static preview block. Replace with a pointed callout.
REPLACEMENT:
  A short callout block where the static preview was:
  "↑ Live preview in the video on the left — adjust controls above to see changes in real time."
  Styled as an inspHint (low visual weight — consistent with existing hint pattern).
WHY: The static preview gives no position context, no animation preview, and no background contrast context. The live overlay does all three. The callout redirects creator attention to the better preview that already exists. (UX1A §4.2)
RISK: LOW — removing static preview block is a DOM delete. Adding callout is a DOM add. evSubOverlay JS is unchanged. evSubModeLabel text should also be updated: "Live preview ↑" instead of "Preview sample."
```

### 5.2 X Position Slider — Move to Collapsed Section

```
CURRENT: X Pos slider (5–95%, default 50%) visible in Subtitles tab alongside Y Pos slider.
PROBLEM: For 95% of creators, center (50%) is always correct. Having both X and Y sliders creates the impression that subtitles must be manually positioned. X Pos was flagged as FP-4 in Phase 63 and deferred. (UX1A §4.3)
DECISION: Move X Pos slider into a collapsed "Advanced Position" section within the Subtitles tab.
  Structure:
    Y Pos: [slider]                        ← remains visible
    [▸ Advanced Position]
      └─ X Pos: [slider]                   ← moved inside collapsed group
REPLACEMENT: Collapsed group with summary "Advanced Position"
WHY: The control must remain in DOM (evSubPosX is read by startRenderFromEditor). Collapsing it removes the decision point for creators who do not need it without breaking the payload chain. (UX1A §9.2, §5.3 risk table)
RISK: LOW — evSubPosX element stays in DOM with same ID. Wrapping in a <details> is safe for this control (it is not in the Phase 64 prohibition list — only evEffectPreset and evLoudnormEnabled are prohibited from <details>). (UX1A-R2 source of truth for Phase 64 constraint)
```

### 5.3 Y Position Slider — Relabel

```
CURRENT: "Y Pos: 15%"
DECISION: Relabel → "Position from bottom: 15%"
REPLACEMENT: Label text change only
WHY: "Y Pos" is a coordinate-space concept. "Position from bottom" tells the creator what 15% actually means in the video frame. (UX1A §7.3 label table)
RISK: LOW — label text only; evSubPos ID unchanged
```

### 5.4 QS Bar ↔ Subtitles Tab Disconnect — Partial Fix

```
CURRENT: Creator picks "Viral" in QS Bar (Export tab) → switches to Subtitles tab → Style dropdown shows "Viral" but there's no confirmation the pill click caused it. (UX1A §4.5)
DECISION (limited scope): Add a small read-only note in the Subtitles tab near the Style dropdown:
  "Style is also set by the Subtitle pill in the Export tab."
  Styled as inspHint.
WHY: This is a visibility fix — not a reconnection of the state machine. Full reconnection (visual feedback between QS Bar pill state and Subtitle tab) requires JS changes outside this plan's scope. The hint gives the creator enough context to understand the relationship without new code. (UX1A §4.5)
RISK: LOW — text-only addition
```

### 5.5 Subtitle Controls — Full Inventory After Plan

| Control | Before | After | Change |
|---|---|---|---|
| Auto subtitle toggle | visible | visible | unchanged |
| Style dropdown (5 options) | visible | visible | + inspHint about QS Bar connection |
| Font select (8 options) | visible | visible | unchanged |
| Size slider | visible | visible | unchanged |
| Color / Highlight pickers | visible | visible | unchanged |
| Y Pos slider | visible | visible | relabeled → "Position from bottom" |
| X Pos slider | visible | collapsed inside "Advanced Position" | moved behind details |
| Outline slider | visible | visible | unchanged |
| Static preview block | visible | removed | replaced with live-preview callout |
| Live-preview callout (new) | absent | visible | points creator to video frame |
| AI Fix Subs button | visible | visible | unchanged |
| Translate checkbox + language select | visible | visible | unchanged |

---

## 6. What Gets Removed From the Primary Flow

"Removed from primary flow" means hidden behind a collapse, moved to a secondary tab, or replaced with a callout. Nothing is deleted from the product.

| Item | Current Visibility | After This Plan | Rationale |
|---|---|---|---|
| AI tab (conversational panel) | Standalone tab | Edit tab bottom (merged) | Low use, no tab needed (UX1A-R2 §3.6) |
| Words tab (AI Narration + Text Layers) | Standalone tab | Edit tab, collapsed groups (merged) | Low use, no tab needed (UX1A-R2 §3.3) |
| Audio tab (Source vol, BGM, Loudness) | Standalone tab | More tab (merged) | Low use, technical output concern (UX1A-R2 §3.4) |
| Render Settings (Device, FPS, Smart Crop) | Export tab, collapsed | More tab | Non-primary render concern (UX1A-R2 §3.5) |
| Editor Performance | Export tab, always visible | More tab | Support/advanced, wrong tab (UX1A §8.3 point 8) |
| Batch Queue | Export tab, after Render Settings | More tab | Power feature, wrong location (UX1A §3.7) |
| Market & Target | Export tab top, collapsed | Advanced fold inside Export | Rarely used, clutters primary surface (UX1A §8.3 point 9) |
| X Position slider | Subtitles tab, visible | Collapsed in "Advanced Position" | 95% default correct, creates false complexity (UX1A §4.3) |
| Static subtitle preview | Subtitles tab, always visible | Removed | Misleading; live overlay is better (UX1A §4.2) |

**Nothing in the list above affects payload values, render behavior, or VideoLocal flow.**

---

## 7. Label and Vocabulary Changes

Full pass on all controls using technical vocabulary. Text changes only — no ID or DOM changes.

| Current Label | New Label | Tab | WHY | Source |
|---|---|---|---|---|
| Story (tab) | Edit | Tab button | Task-based language | UX1A §3.1 |
| "Min clip (s)" | "Shortest clip" | Export → Advanced | Plain language for duration constraint | UX1A §7.3 |
| "Max clip (s)" | "Longest clip" | Export → Advanced | Plain language for duration constraint | UX1A §7.3 |
| "Output Profile" | "Render quality" | Export → Advanced | Describes what the setting does | UX1A §7.3, Phase 65 recommendation |
| "Reframe Mode" | "Smart Crop" | More tab (from Export) | Plain language for vertical reframe | UX1A §7.3, Phase 65 recommendation |
| "Y Pos" | "Position from bottom" | Subtitles | Coordinate-system label has no meaning without context | UX1A §7.3 |
| "X Pos" | "Horizontal position" | Subtitles → collapsed | Moved to Advanced Position; label updated for parity | UX1A §7.3 |
| "Multi-variant render" | "Render with multiple style variations" | Export → Advanced | Explains what happens | UX1A §7.3 |
| "More Hook" (tooltip) | title="Selects more clips from the intro…" | QS Bar pill | Product vocabulary without context | UX1A §3.6 |
| "More Story" (tooltip) | title="Selects more clips from the body…" | QS Bar pill | Product vocabulary without context | UX1A §3.6 |
| "Balanced" (tooltip) | title="Default — equal weight between hook and story clips" | QS Bar pill | Provide parity with other pill tooltips | UX1A §3.6 |
| "Quick Presets (4)" | "Quick Presets — starting points (4)" | Export, collapsed summary | Differentiates from Creator Presets and Expert Preset | UX1A §3.3 |

---

## 8. Risk Analysis

### 8.1 By Risk Level

**LOW RISK — safe to implement in a single phase:**
- All label text changes (tab names, field labels, summary text)
- All title= tooltip additions (Structure pills, Balanced pill)
- Tab renames ("Story" → "Edit")
- AI tab merge into Edit — no runtime side effects (UX1A-R2 §4.1)
- Words tab merge into Edit — attribute change + EditorTextRuntime trigger move; documented (UX1A-R2 §4.2)
- Editor Performance move to More — attribute change only
- Batch Queue move to More — ID-based, not tab-based (UX1A-R2 §4.4)
- Static preview removal + callout addition in Subtitles tab
- X Pos slider collapse into "Advanced Position" section
- Y Pos relabel
- Read-only Aspect Ratio badge (above fold) — display only, no form value
- Read-only Duration hint (above fold) — display only, no form value
- Quick Presets summary label update
- QS Bar / cpBar reorder (HTML reorder only)

**MEDIUM RISK — requires targeted verification before implementation:**

| Change | Risk Source | Verification Required |
|---|---|---|
| Audio moves to More tab | EditorAudioRuntime.onTabActivate() must fire on 'more' — if missed, audio fails silently | Confirm what .onTabActivate() initializes; verify BGM + volume respond correctly after trigger moves |
| Render Settings moves to More tab | EditorPerformanceRuntime.onTabActivate() / .onTabDeactivate() must move; existing auto-expand must stop | Check that performance runtime does not need to be active from editor open; verify auto-expand removal |
| Market & Target moves into Advanced fold | mvMarket/mvAutoBestClips/mvKeywordHighlight/mvBestExportEnabled IDs must stay in DOM | Confirm mvHandleChange() and mvHandleAutoBestClips() are ID-based, not positional |

**NOT DONE IN THIS PLAN — risk too high or scope too large:**

| Item | Why Deferred |
|---|---|
| Consolidating three preset systems | Requires understanding full preset state machine; evEffectPreset read path must be fully traced; dedicated phase |
| Surfacing Min/Max duration above Advanced fold as real controls | _evMinPartTouched / _evMaxPartTouched dirty flags do not exist; implementing them without platform→duration auto-link is unsafe (UX1A §10.3) |
| Subtitle visual card preview | Requires positioned preview mock and design decision; not a label/layout-only change |
| Async H264 preview transcode | Non-trivial backend change; outside this scope (UX1A-R2 §9.2) |

### 8.2 Locked IDs — Must Not Change

These IDs are read by render-engine.js, render-config.js, or editor-view.js in payload-building paths. No rename, no removal.

| ID | Read By | Risk if Changed |
|---|---|---|
| evMinPart, evMaxPart | editor-view.js:2274-2275 | Breaks clip duration payload |
| evAspectRatio | editor-view.js:2272 | Breaks aspect ratio payload |
| evSubStyle | editor-view.js:2239 | Breaks subtitle style payload |
| evSubPos (Y) | editor-view.js | Breaks subtitle Y position payload |
| evSubPosX (X) | editor-view.js | Breaks subtitle X position payload — must remain in DOM even when collapsed |
| evEffectPreset | preset apply functions | Must stay outside `<details>` — Phase 64 prohibition |
| evLoudnormEnabled | preset apply functions | Must stay outside `<details>` — Phase 64 prohibition |
| evStartBtn | editor-view.js:2522 | Breaks render button state |
| source_video_path | render-config.js:27 | Breaks VideoLocal file path display and upload logic |
| local_video_file_picker | render-config.js | Breaks file picker trigger |
| manual_output_dir | render-engine.js | Breaks output folder resolution |
| bqSection | BatchQueue module | Must remain in DOM at same ID after tab move |
| edPerfHealthBanner, edPerfHoverPreview, edPerfFilmstrip, edPerfWaveform | EditorPerformanceRuntime | Must remain in DOM at same IDs after tab move |
| mvMarket, mvAutoBestClips, mvKeywordHighlight, mvBestExportEnabled | mvHandleChange() | Must remain in DOM at same IDs after section move |

---

## 9. Implementation Phases

### Phase A — Label, Tooltip, and Display-Only Changes (Low risk, no JS logic)

**Scope:** HTML text changes, title= attributes, read-only display elements, summary label updates.
**No JS changes. No DOM restructuring. No ID changes.**

Deliverables:
1. Tab button text: "Story" → "Edit"
2. Field labels: Min clip / Max clip / Output Profile / Reframe Mode / Y Pos / X Pos / Multi-variant
3. Structure pill title= tooltips: More Hook / Balanced / More Story
4. Quick Presets summary: "Quick Presets — starting points (4)"
5. Static preview block removed; live-preview callout added in Subtitles tab
6. evSubModeLabel text: "Live preview ↑"
7. QS Bar / Subtitle tab connection hint: inspHint near Style dropdown in Subtitles tab
8. Aspect Ratio read-only badge added above fold in Export tab
9. Duration range read-only hint added above fold in Export tab
10. QS Bar reordered above cpBar in Export tab (HTML reorder)

**Risk check before Phase A:**
- Confirm no CSS positional assumptions on QS Bar / cpBar order
- Confirm evSubModeLabel is set by JS (check it's not hardcoded in payload logic)

---

### Phase B — Tab Merges and Content Moves (Low to Medium risk)

**Scope:** data-insp-panel attribute changes, validTabs/tabTitles updates, tab button additions/removals, JS trigger moves.
**Contains the highest-risk single change in the plan: EditorAudioRuntime.onTabActivate() trigger move.**

**Part B1 — Low risk merges (do first):**
1. Add "More" tab button to tabbar
2. Add 'more' to validTabs and tabTitles in setInspectorTab()
3. Move Editor Performance: data-insp-panel="performance" → "more" on edPerf section
4. Move Batch Queue: data-insp-panel="performance" → "more" on bqSection
5. Merge AI tab: data-insp-panel="ai" → "mode" on convPanel; remove AI tab button; remove 'ai' from validTabs
6. Merge Words tab: data-insp-panel="text" → "mode" on evSectionNarration and Text Layers group; remove Words tab button; remove 'text' from validTabs; move EditorTextRuntime.onTabActivate() to 'mode' trigger; do NOT auto-open text-layers group on 'mode' tab entry

**Part B2 — Medium risk moves (verify then do):**
1. Move Audio to More tab: data-insp-panel="audio" → "more"; remove Audio tab button; move EditorAudioRuntime.onTabActivate() trigger to 'more'; move evSetInspGroupOpen('audio', true) to 'more' entry
2. Move Render Settings to More tab: data-insp-panel change; move EditorPerformanceRuntime.onTabActivate() and .onTabDeactivate() to 'more'; remove evSetInspGroupOpen('performance', true) from Export tab entry
3. Move Market & Target into Advanced fold: reorder HTML only; confirm IDs unchanged
4. Move X Pos slider into collapsed "Advanced Position" details in Subtitles tab

**Verification gates before B2:**
- [ ] EditorAudioRuntime.onTabActivate() — confirm what it initializes; confirm BGM and volume controls respond after trigger moves to 'more'
- [ ] EditorPerformanceRuntime.onTabActivate() — confirm whether performance runtime needs to be active from editor load (not just when More tab is open)
- [ ] EditorPerformanceRuntime.onTabDeactivate() — confirm what cleanup it performs; confirm deactivate on 'more' exit is correct
- [ ] mvHandleChange() and mvHandleAutoBestClips() — confirm ID-based, not position-based

---

## 10. Out of Scope

The following are excluded from this plan. They require dedicated phases with deeper scope analysis.

**Three Preset System Consolidation:**
Quick Presets, Creator Presets (cpBar), and Expert Preset remain as-is in visual order. Consolidating them requires tracing all paths that read evEffectPreset and understanding the full preset state machine. (UX1A §3.3, §7.1)

**Min/Max Duration Above the Advanced Fold:**
evMinPart and evMaxPart cannot safely be elevated as primary controls without dirty-flag infrastructure (_evMinPartTouched / _evMaxPartTouched). These flags do not exist. Platform → duration auto-link (e.g., TikTok → suggest shorter clips) would require these flags as a prerequisite. (UX1A §10.3, UX1A-R2 §2)

**Subtitle Style Visual Cards:**
Replacing the Style dropdown with visual cards (like Quick Presets) requires a design decision and positioned mock for the card layout. Not a label/layout change. (UX1A §4.4)

**Subtitle QS Bar State Reconnection:**
Full visual feedback between QS Bar subtitle pill and Subtitles tab Style dropdown (beyond the hint text in this plan) requires JS changes to evSyncQsBar() and the active pill state machine. (UX1A §4.5)

**Async H264 Preview Transcode:**
Returning session_id immediately and transcoding in background would significantly improve editor load time for large HEVC/MKV files. Non-trivial backend + frontend change. (UX1A-R2 §9.2)

**VideoLocal Render Flow:**
The render flow is correct as-is. No copy of original local video occurs. H264 preview transcode is required for Electron/Chromium compatibility and cannot be removed. Trim creates a move (not copy) to source/ folder. No changes needed or planned. (UX1A-R2 §7, §8, §9)

**Backend Behavior:**
All changes in this plan are HTML/CSS/JS frontend only. No API, route, pipeline, or session logic changes.

**Channel Sync Code:**
Channel sync is inactive in current UI (all channel elements are hiddenView). The channel code is not touched. (UX1A §5.4)

**Rerender Flow, Review Queue, Creator Memory, Render Ranking:**
Not in scope. Not touched.

**evEffectPreset and evLoudnormEnabled Positioning:**
These two hidden inputs remain outside any `<details>` element. Phase 64 constraint is permanent. (UX1A §5.3 risk table)

---

*End of Plan — PHASE UX-1B*
*Next step: Review this plan, then implement Phase A (label + display-only changes) as the first implementation commit.*
