# UI FINAL AUDIT — Production UX Alignment
**Branch:** `feature/ai-output-upgrade`  
**Date:** 2026-05-18  
**Scope:** UP23 → UP35 cumulative. Read from real HTML, JS, and CSS — no assumptions.

---

## Verdict

> **Not yet creator-grade.** The architecture is sound and the intelligence layer is well-implemented. But there is one navigation-level mismatch that blocks a primary workflow, and several control duplication issues in the editor inspector that create genuine confusion. The trust/hint system is the right balance. The workspace landing is good. The issues below are real — none are invented.

---

## P0 — Blocks Workflow (1 issue)

### P0-1: "Batch" nav tab opens the YouTube downloader, not the batch render queue

**What the creator expects:** Click "Batch" in the top nav → see overnight render status, stalled items, completed jobs.

**What actually happens:** `data-view="download"` opens `card_download_setup` — the YouTube/Instagram/Facebook link downloader. The sidebar shows "Build a source inbox" with a link paste field.

**Where the batch render queue actually is:** Inside the editor inspector panel, under `data-insp-panel="performance"` as `bqSection`. Only accessible by opening a video in the editor first, then finding it in the performance tab.

**Why this blocks:** A creator who ran an overnight batch and comes back the next morning clicks "Batch" to check status. They see the YouTube downloader. They cannot find their rendered files. The stall warnings and recovery chips from UP35 are invisible because they're in the wrong view.

**Fix:** Rename nav tab from "Batch" to "Sources" (or "Download"). The concept is "source inbox," not batch render. The batch render queue belongs in a different surface.

---

## P1 — Creates Friction (7 issues)

### P1-1: Platform control appears in two places

In the editor inspector:
- **qsBar** (always visible, Output section): YouTube | TikTok | Reels pills → `evQsSet('platform', val)`
- **Advanced panel** (collapsed): `<select id="evTargetPlatform">` with YouTube Shorts / TikTok / Instagram Reels

Both control the same payload field (`target_platform`), synced via `evSyncQsBar()`. But the creator sees two platform selectors with slightly different labels (qsBar: "YouTube" / Advanced: "YouTube Shorts"). First-time users touch the qsBar pill, then open Advanced and see the dropdown in an unexpected state or change it again.

**Fix:** Remove the `evTargetPlatform` dropdown from Advanced. The qsBar pills are the canonical control. Advanced doesn't need a duplicate.

---

### P1-2: Variant control appears in two places

- **qsBar**: "Multi-variant" toggle pill → `evQsToggle('variant')` → sets `evMultiVariant` checkbox
- **Advanced panel**: `<input type="checkbox" id="evMultiVariant">` with label "Multi-variant"

Identical setting, same underlying element ID, two UI controls. Creator checking Advanced after using qsBar sees the checkbox but doesn't know it's the same as the pill they already toggled.

**Fix:** Remove the `evMultiVariant` checkbox from Advanced. The qsBar toggle is the canonical control.

---

### P1-3: Subtitle is fragmented across three surfaces

**Surface 1 — qsBar** (always visible, Output section):  
Off | Clean | Viral | Karaoke  (4 options)

**Surface 2 — Subtitle tab** (separate inspector tab):  
Full `evSubStyle` dropdown: Viral Bounce / Karaoke / Bold Cap / Boxed / Clean (5 options, different labels)  
Plus: Font, Size, Color, Y pos, X pos, Outline — 6 more controls

**Surface 3 — Market & Target panel** (performance tab):  
`mvSubtitleTone` dropdown: Clean | Bold | Karaoke — a different "subtitle" concept (market tone modifier)

A creator setting up a TikTok clip touches qsBar "Viral", then opens the Subtitle tab and sees "Viral Bounce" — not immediately obvious they're the same. They also see Bold Cap and Boxed which the qsBar doesn't offer at all. And there's a third "Subtitle Tone" in Market that sounds related but isn't the same field.

**This is the most confusing part of the editor inspector.**

**Fix:** 
- qsBar subtitle pills should be the fast path and should match label-for-label with the Subtitle tab (e.g., "Viral Bounce" not "Viral"). 
- "Subtitle Tone" in Market & Target is a different concept — rename it explicitly so creators understand it doesn't replace the Subtitle Style setting.
- Optionally: remove qsBar subtitle pills entirely and let the Subtitle tab be the canonical source with its full labels. The qsBar platform/structure pills are more unique; subtitle already has a dedicated tab.

---

### P1-4: Review queue retry button is a ghost

In the review queue, each card has 5 action buttons: K / ★ / D / ↻ / 📁

`↻` calls `ReviewQueue.retry(jobId)` which does:
```javascript
function retry(jobId) {
  _showToast('Switch to the Render tab to retry', 'info');
}
```

It shows a toast and does nothing. The "Needs Retry" section also exists for failed items with the same retry button — equally inert.

A creator clicking the retry button on a failed clip expects it to retry. Instead they get a toast telling them to go somewhere else, with no guidance on what to do when they get there.

**Fix:** Either (a) remove the retry button from review cards entirely and explain in the "Needs Retry" section label that retries happen from the Create tab, or (b) make the button navigate directly to Create tab with the source file pre-filled (if possible). At minimum, the "Needs Retry" section should have inline text explaining what action is needed rather than relying on a dead button.

---

### P1-5: Keep / Avoid / ↻ Similar are visually deprioritized

These are the three most powerful actions in the rerender loop:
```html
<button class="clipCardBtnKeep">&#10003; Keep</button>
<button class="clipCardBtnAvoid">&#10007; Avoid</button>
<button class="clipCardBtnSimilar">&#8635; Similar</button>
```

They appear as small text buttons at the bottom of each clip card, visually identical in weight to "Preview", "Download", "Folder", "Cover", "Compare". A creator reviewing clips may not notice them at all. They're the answer to "how do I tell it what I liked?" but they don't look like the answer.

**Fix:** Give Keep/Avoid/↻ Similar a distinct visual treatment — heavier weight, a different grouping, or a short label like "↻ Rerender with this". These actions are P0 UX — they should look like it.

---

### P1-6: Two preset systems exist without clear relationship

**System 1 — Quick Start Preset** (performance tab, always visible):  
4 cards: TikTok / Reels, Podcast Clip, Clean Business, High Quality. These apply a combination of settings via `evApplyPreset()`.

**System 2 — Strategy Preset** (inside Advanced, collapsed):  
`<select id="evOutputPreset">`: Manual/Custom, TikTok US Viral, EU Clean Review, JP Storytelling, Clean Subtitle Focus, Fast Batch Ranking. These apply via `evApplyOutputPreset()`.

**System 3 — Creator Presets** (cpBar, Output section):  
Saved user presets dropdown. These are the user's own saved configurations.

Three preset systems in one inspector panel. The Quick Start presets and Strategy presets overlap in purpose (both set multiple output settings at once) and appear near each other in the same inspector tab, but are never explained in relation to each other.

**Fix:** The Quick Start Preset cards are a good fast-path and should stay. Consider removing or merging the Strategy Preset dropdown into the Quick Start cards (add more cards rather than a hidden dropdown). The Creator Presets dropdown is distinct enough (user-saved) and should stay.

---

### P1-7: "Open Editor" entry point is buried in the sidebar

The main area of the Create view shows a large hero panel with YouTube and Local File tiles. These tiles switch the source mode dropdown in the sidebar. But the "Open Editor" button — the primary action that starts the workflow — is at the **bottom of the sidebar setup card**, below the source fields and the output folder picker.

A creator interacting with the main hero panel clicks a tile, fills in the URL or file path (also in the sidebar), and then needs to scroll the sidebar to find "Open Editor". The main panel has no primary CTA.

The `render_home_panel` hero has two zones: "Continue creating" and "Your Workspace". Neither leads to the editor directly.

**Fix:** Add a "Start / Open Editor" button in the main panel hero, or at minimum make the hero CTA ("Create New Project") button directly trigger the Open Editor flow rather than just switching the source mode dropdown.

---

## P2 — Polish (3 issues)

### P2-1: Dismissed clips are invisible and unrecoverable

Review queue sections: Ready to Review / Favorites / Kept / Needs Retry.

`dismissed` state items are not rendered in any section. If a creator accidentally dismisses a clip, there is no way to find it or undo the action. The dismissed section exists in code (`byState.dismissed`) but is never rendered.

**Fix:** Add a "Dismissed" section (collapsed by default, like Kept) so creators can recover accidental dismissals. Or add an undo/toast mechanism immediately after dismiss.

---

### P2-2: "Loading models..." topbar chip may never resolve

`<div class="pill" id="warmup_chip">Loading models...</div>` is the default text. It updates via `toggleWarmupPanel()` — presumably as warmup events fire. But if warmup is instant (already cached) or the event never fires, the chip reads "Loading models..." indefinitely.

This chips away at trust: the topbar says the tool is loading something but the creator is using it normally. Not broken, but creates unease.

**Fix:** Ensure a default fallback updates the chip after page load if no warmup events arrive (e.g., "Ready" after 3s).

---

### P2-3: Advanced panel mixes inline styles with field/label patterns

Within `qsAdvBody`, some controls use `<label class="field">` with a grid, while others use raw `<div style="display:flex;...">` wrappers with inline dimension/color specs. The Subtitle Size block is `<div style="display:flex;align-items:center;gap:10px;...">` while Aspect Ratio two lines above is a `<label class="field">`.

This is purely cosmetic but noticeable when scrolling the Advanced panel.

**Fix:** When Advanced is next touched, normalize to `<label class="field">` + CSS classes. No rush — this is polish.

---

## Keep As-Is

These are working correctly and should not be changed:

| Element | Why it's fine |
|---|---|
| **Home/Workspace (UP32)** | Four-section layout is well-considered. Status strip, Continue Series, Quick Create, Favorites is the right hierarchy. Empty states are guided. |
| **Trust bar chips** (render output) | Platform, DNA, Series, Consistency, Structure bias, Keep/Avoid counts, Recovered, Assets — right balance of information. Not noisy. |
| **Hint system** (DNA / Series / Consistency) | Italic advisory text below preset selector. Subtle, informational, non-blocking. Correct placement. |
| **Steering panel** | `v3SteeringPanel` with Reset Steering + ↻ Rerender is clean. Hidden until relevant. |
| **qsBar structure pills** | More Hook / Balanced / More Story — clean, non-duplicated. Keep. |
| **Recovery + stall warning (UP35)** | "Review suggested" and amber stall line on batch cards are the right weight. |
| **Review queue sections** | Ready to Review / Favorites / Kept / Needs Retry structure is correct. Kept collapsed is right. |
| **Clip card layout** | Thumbnail + score + rank + reason + steering row. Good information density. |
| **Empty states** | Review, workspace, batch drop zone, history — all give clear next-action guidance. |
| **Nav simplification (UP32)** | 4 items (Home/Create/Review/Batch) is the right count. The Batch label is the only problem (P0-1). |
| **Keyboard shortcuts in review** | K/F/D/R key handlers — correct. The R handler is the ghost (P1-4) but the other three are fine. |

---

## Recommended MAP-UI-FINAL Plan

**Do in order of priority:**

### 1. Rename "Batch" nav tab (P0-1)
```
Before: <button data-view="download">Batch</button>
After:  <button data-view="download">Sources</button>
```
One-line fix. Resolves the primary workflow mismatch.

### 2. Fix review retry UX (P1-4)
Remove the ↻ button from review cards or replace with a "Go to Create" action. Update the "Needs Retry" section to explain the retry path explicitly in copy, not just as a dead button.

### 3. Deduplicate Platform and Variant in Advanced (P1-1, P1-2)
Remove `evTargetPlatform` dropdown and `evMultiVariant` checkbox from `qsAdvBody`. The qsBar is the canonical control. Advanced remains for Aspect Ratio, Output Profile, clip duration limits, CTA, Title Overlay, Subtitle Size, Creator Assets — none of which are in qsBar.

### 4. Reconcile subtitle labels (P1-3)
Align qsBar pill labels with Subtitle tab dropdown values. Rename "Viral" → "Viral Bounce", "Karaoke" → "Karaoke". Remove "Clean" pill if it maps ambiguously (Bold Cap and Boxed are also "clean-ish"). Rename `mvSubtitleTone` label in Market & Target to "Market Tone" to distinguish it from subtitle style.

### 5. Promote Keep/Avoid/↻ (P1-5)
Give the steer row at the bottom of clip cards a visual accent — heavier border-top, slightly larger text, or a distinct background row. These are the rerender loop entry points and should not look like tertiary actions.

### 6. Add dismissed section to review (P2-1)
Collapsed by default. Shows count. Allows recovery.

### 7. Warmup chip fallback (P2-2)
After 3-5 seconds with no update, set chip text to "Ready" or "AI engine active".

---

## Not Recommended

- Merging the batch render queue into the "Batch" nav view would require showing `bqSection` outside the editor context, which it currently doesn't support. The simpler fix is the rename (step 1 above).
- Removing Market & Target entirely — it covers different fields (market scoring, hook optimization) even where it overlaps in label.
- Rewriting the qsBar or inspector panel tab structure — the architecture is correct; only the label and duplication issues need fixing.
- Adding "retry from review" as a full resubmit flow — the architectural reason it's a toast (can't re-ingest source from review context) is sound. Clear copy beats a fake button.
