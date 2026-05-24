# PRODUCT STATE — MAP-UI-V3: Creator Steering Workspace

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(ui): creator steering workspace`
**Status:** Shipped

---

## What Changed and Why

**Before (MAP-UI-V2):** Render settings UI. Creator fills out fields, hits render, waits.

**After (MAP-UI-V3):** Creator steering workspace. Creator reviews output, guides AI, rerenders in seconds.

This is a **workflow remap**, not a visual redesign. All existing components reused. No new backend. No new panels. No CSS rewrite.

The mental model shift:

| Before | After |
|---|---|
| Setup render | Review |
| Wait | Guide |
| Done | Rerender |
| — | Approve |

---

## Three-Zone Workspace

### Zone A — Create (right sidebar, top)

The existing Output section (`evSectionBasic`). Fast setup under 10 seconds.

Contains: Preset selector, Quick Strategy Bar (Platform / Variant / Subtitle / CTA / Structure), Advanced (collapsible).

No structural change. The render button stays in the sticky footer.

### Zone B — Review (center panel)

Clip cards become review cards. Priority: scan speed.

**Card changes:**
- Keep / Avoid buttons (UP26) now also have **↻ Similar** — one click keeps the clip AND triggers an immediate rerender if editor is active
- Trust bar above the card list shows what influenced this specific render (platform, DNA, structure bias, lock/avoid counts, recovery)

### Zone C — Guide AI (right sidebar, inline)

**New: `v3SteeringPanel`** — appears inside the Output section only when something is actively steering the render. Hidden when everything is default.

Shows chips for:
- Active preset name
- DNA active (if confident signals fired)
- Structure bias (if not Balanced)
- Subtitle emphasis (if not Balanced)
- 🔒 N kept / 🚫 N avoided (from ClipSteering)

Two action buttons:
- **Reset Steering** — clears ClipSteering lock/avoid, resets structure bias and subtitle emphasis to Balanced, calls evSyncQsBar()
- **↻ Rerender** — calls startRenderFromEditor() if editor session is active, otherwise shows a toast

---

## Batch Review UX

`BatchQueue._render()` now groups cards into labeled sections:

| Group | Statuses |
|---|---|
| (no label — pending items at top) | pending |
| Running | running, queued |
| Ready to Review | completed, recovered |
| Failed | failed, cancelled |

Groups only appear when that section has items. Labels are small, uppercase, low-contrast — guide the eye without adding clutter.

---

## Rerender Loop

Workflow:
1. Creator reviews clip cards
2. Clicks **↻ Similar** on a clip they liked → ClipSteering.lockClip() fires + v3TriggerRerender() fires
3. If editor session is active → render starts immediately
4. If not → toast: "Open a video in the editor first, then use ▶ Start Render"

The Keep and Avoid buttons still work independently (no immediate rerender) for creators who want to queue up several steering decisions before rerendering.

---

## Trust Layer

Two surfaces:

**Zone C panel (steering panel):** Shows what WILL influence the NEXT render. Updates live as creator changes settings or clicks Keep/Avoid.

**Trust bar above clip list:** Shows what DID influence THIS render. Reads from `getCurrentJobPayload(job)` so it reflects the job that produced the clips, not the current settings.

Chips in trust bar: Platform (if not YouTube Shorts) · Creator DNA · More Hook / More Story · 🔒 N kept · 🚫 N avoided · Recovered

---

## Files Changed

### `backend/static/index.html`
- Added `v3SteeringPanel` div inside `evSectionBasic`, between `cpDnaHint` and `qsBar`
- Contains: `v3SteeringChips` (dynamic chip row) + two action buttons (Reset Steering, ↻ Rerender)

### `backend/static/js/editor-view.js`
- `v3RefreshSteeringPanel()` — reads ClipSteering state, preset, structure bias, subtitle emphasis, DNA; renders chips; hides panel when nothing active
- `v3ResetSteering()` — clears ClipSteering, resets hidden inputs, calls evSyncQsBar()
- `v3TriggerRerender()` — calls startRenderFromEditor() if session active
- `evSyncQsBar()` — now calls `v3RefreshSteeringPanel()` at end

### `backend/static/js/render-ui.js`
- `window.csKeepClip` / `window.csAvoidClip` — now call `v3RefreshSteeringPanel()` after mutating ClipSteering
- `window.csKeepAndRerender` — new global: lockClip + v3TriggerRerender
- Trust bar (`v3TrustBar`) generated from job payload and inserted before clip card list
- `_platformBanner` and `_dnaHint` removed; replaced by unified trust bar
- Clip card steer row: added **↻ Similar** button (`clipCardBtnSimilar`) calling `csKeepAndRerender()`

### `backend/static/js/batch-queue.js`
- `_render()` refactored: cards grouped into Running / Ready to Review / Failed, with `bqGroupLabel` dividers
- Pending items rendered first (no group label — they haven't started yet)

### `backend/static/css/app.css`
- `.clipCardBtnSimilar` — purple tint, same pill style as Keep/Avoid
- `.v3SteeringPanel`, `.v3SteeringChips`, `.v3Chip` + variants (Preset/DNA/Steer/Lock/Exclude)
- `.v3SteeringActions`, `.v3SteeringResetBtn`, `.v3SteeringRerunBtn`
- `.v3TrustBar`, `.v3TrustChip` + variants (Platform/DNA/Steer/Lock/Exclude/Recovered)
- `.bqGroupLabel` — batch queue section separators

---

## What Was Intentionally NOT Changed

| Not changed | Reason |
|---|---|
| Clip card DOM structure | Additions only; no reorder that could break existing selectors |
| evSectionBasic layout | Steering panel is additive (display:none when inactive) |
| Any render pipeline | Pure UI remap |
| evStartBtn / evFooter | Render button unchanged; v3TriggerRerender delegates to it |
| Batch queue job lifecycle | Only the visual grouping changed |
| Advanced settings content | Unchanged; subtitle emphasis already there from UP26 |
| Any CSS variable or design token | Only new classes added |

---

## Manual QA Checklist

### A — Steering panel: inactive by default
- [ ] Open editor with no presets, no Keep/Avoid, Balanced structure → `v3SteeringPanel` is hidden

### B — Steering panel: appears on preset apply
- [ ] Apply a preset → panel shows preset name chip

### C — Steering panel: appears on structure change
- [ ] Click "More Hook" pill → panel shows "More Hook" chip

### D — Steering panel: Keep/Avoid
- [ ] Click "✓ Keep" on a clip card → panel shows "🔒 1 kept"
- [ ] Click "✕ Avoid" on a clip card → panel shows "🚫 1 avoided"
- [ ] Panel updates without page reload

### E — Reset Steering
- [ ] Click "Reset Steering" → ClipSteering cleared, Structure back to Balanced, panel hides
- [ ] Toast: "Steering reset"

### F — ↻ Rerender (panel)
- [ ] With editor session active: click ↻ Rerender → render starts immediately
- [ ] Without session: toast shown

### G — ↻ Similar (clip card)
- [ ] Click "↻ Similar" → clip locked + rerender triggered (or toast if no session)
- [ ] Panel updates to show "🔒 1 kept"

### H — Trust bar
- [ ] After render with TikTok platform → trust bar shows "TikTok" chip
- [ ] After render with DNA fired → "Creator DNA" chip
- [ ] After recovered render → "Recovered" chip
- [ ] After render with More Story + Keep → "More Story" + "🔒 1 kept" chips

### I — Batch queue grouping
- [ ] Queue 3 files; 1 running, 1 complete, 1 failed
- [ ] Three group labels appear: "Running", "Ready to Review", "Failed"
- [ ] Pending items (not yet submitted) appear above groups with no label

### J — No regressions
- [ ] Normal single render: all settings apply correctly
- [ ] Batch render: all items submit, steering fields carried in payload
- [ ] Preset apply: all fields sync, steering panel updates

### K — 30-second review-to-rerender
- [ ] Creator can review clips, click ↻ Similar, and have a new render running in < 30 seconds
