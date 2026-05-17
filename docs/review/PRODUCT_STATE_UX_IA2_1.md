# Product State — Post UX-IA2.1

**Date:** 2026-05-17
**Branch:** `feature/ai-output-upgrade`
**Phase:** UX-IA2.1 — Editor Workflow Re-Architecture (P0)

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed

Information architecture refactor of the editor inspector panel. Tab renames, content migration between tabs, and hierarchy cleanup. No logic was rewritten, no handlers were changed, no payload fields were modified.

---

## Tab Renames

| Old Name | New Name | Internal ID | Why |
|----------|----------|-------------|-----|
| Cut | **Story** | `mode` | Reflects the creative goal: shaping a story |
| Text & Voice | **Words** | `text` | Honest: covers both text overlays and voice narration now |
| Render | **Export** | `performance` | Matches creator mental model: "setting up the export" |
| Talk | **AI** | `ai` | Undersells → renames to the actual capability |
| Subtitles | Subtitles | `subtitle` | Unchanged — already honest |
| Audio | Audio | `audio` | Unchanged — now more accurate (sound mixing only) |

**Changes in code:**
- `index.html` — 4 tab button labels
- `editor-view.js` `setInspectorTab.tabTitles` map updated

---

## Content Moves

### Story tab — CLEANED

**Removed from Story:**
- Quick Start Presets → Export
- Output Settings (aspect ratio, output profile, clip size, title overlay) → Export
- Strategy Preset dropdown → Export
- Duplicate Undo button (was in AI Edit Actions grid, kept in AI Assist header)
- Language & Voice separator (was never showing — `_sep` panel never matched any tab)

**Restructured in Story:**
- Creator Memory panel (`#cmPrefsPanel`) — demoted from top of panel to below AI actions
- Timeline Variants and Snapshots — promoted from inside collapsed "AI Edit Actions" body to their own always-visible section (`#evSectionVariants`)

**Story tab order (top → bottom):**
1. Trim controls
2. AI Assist (chips + activity rail + single Undo)
3. AI Edit Actions (collapsed — 7 buttons, Undo removed)
4. Timeline Variants (4 variant buttons — always visible)
5. Snapshots (always visible)
6. Creator Memory (demoted)

---

### Subtitles tab — FIX SUBS ADDED

Added "✦ Fix Subs — AI cleanup" button at the top of the translate/cleanup section. Calls `EditorAiActions?.subtitleCleanup?.()` — same handler as the Fix Subs button in Story's AI actions grid. Two entry points, one action.

---

### Words tab — VOICE MOVED IN

**Added to Words:**
- AI Narration section (`#evSectionNarration`) — moved from Audio collapsed group
  - `evVoiceEnable` checkbox
  - `edVoiceControls` / `evVoiceFields` container (populated by `evInitVoiceFields()`)
  - Handlers unchanged: `EditorAudioRuntime.onVoiceToggle()`

**Removed from compat div:**
- Duplicate `evVoiceFields` container in `#evEditorCompat` (was hidden legacy compat, now real element is in Words panel)

**Words tab order:**
1. AI Narration (voice toggle + voice config)
2. Text Layers (full text overlay editor — unchanged)

---

### Audio tab — SOUND MIXING ONLY

**Removed from Audio:**
- AI Narration / Voice section (→ Words tab)

**Added to Audio:**
- Loudness normalization visible toggle (`#edAudioLoudnorm`)
  - `onchange` writes to hidden `#evLoudnormEnabled` input (the existing render payload field)
  - `payload.loudnorm_enabled` read path unchanged in `startRenderFromEditor()`

**Audio tab is now:** Source Audio + Background Music + Loudness Normalization. Clean sound mixing scope.

---

### Export tab — OUTPUT CONFIG CONSOLIDATED

**Added to Export:**
- Quick Start Presets (was in Story)
- Output Settings: strategy preset, aspect ratio, output profile, clip duration limits, title overlay (was in Story)
- Market Viral panel (`#evSectionMarket`) — was `data-insp-panel="market"` (ghost panel, never shown). Now `data-insp-panel="performance"`, fully surfaced.

**Restructured in Export:**
- Render Settings collapsed group (`#inspGroupPerfHdr`): Device, FPS, Transform, Reframe. Renamed from "Performance" to "Render Settings". Auto-opens when Export tab activates.
- Advanced Debug collapsed group (`#inspGroupAdvHdr`, `#inspGroupAdvBody`): Runtime Diagnostics (FPS meter, DOM nodes, cache stats), dev tools (Dev overlay, Clear thumbs, Clear waves), Quality Controls. **Collapsed by default.** Does NOT auto-open on tab switch (removed `evSetInspGroupOpen('advanced', true)` from `setInspectorTab`).

**Export tab order:**
1. Quick Start Presets
2. Output Settings (aspect ratio, output profile, clip limits, title overlay, strategy preset)
3. Render Settings (collapsed, auto-opens — device, FPS, transform, reframe)
4. Advanced Debug (collapsed, stays collapsed — diagnostics, dev tools)
5. Market Viral (always visible)

---

### AI tab — BRIDGE COPY ADDED

Added a muted bridge line at top of conversation panel:
> "Same editing assistant used in Story · richer reasoning here"

Clarifies the relationship between Story's AI chips and the AI tab's conversational editing. No functional change to `EditorConverse`.

---

## Preserved Without Change

| System | Preserved |
|--------|-----------|
| All `EditorAiActions` handlers | ✓ — no JS logic changed |
| All `startRenderFromEditor()` payload fields | ✓ — same IDs, same read paths |
| `EditorConverse` engine | ✓ — no conversational logic changed |
| `EditorAudioRuntime` voice handlers | ✓ — same IDs, handler still fires |
| `CreatorMemory` panel | ✓ — same ID, same JS lifecycle |
| Trim system | ✓ — unchanged |
| Subtitle preview (libass) | ✓ — unchanged |
| Text layer editor | ✓ — unchanged |
| Market Viral (`_mvState`, `mvHandleChange`) | ✓ — panel surfaced, no logic changed |
| Batch mode panel | ✓ — unchanged |
| Start Render (footer) | ✓ — unchanged |
| `evSetInspGroupOpen` / `evToggleInspGroup` | ✓ — 'advanced' group now wired to real HTML IDs |

---

## Mental Model Fixes

| Problem | Fix |
|---------|-----|
| Output settings in Story, not Export | Moved to Export |
| "Text & Voice" tab had no Voice | Voice moved in; tab renamed Words |
| Render tab was mostly dev tools | Dev tools collapsed in Advanced Debug; creator settings moved in |
| Talk tab felt dead/unclear | Renamed AI; bridge copy added |
| Fix Subs only in Story | Added entry point in Subtitles tab |
| Market Viral inaccessible (ghost panel) | Surfaced in Export tab |
| Two Undo buttons | One Undo (AI Assist header only) |
| Variants/Snapshots buried | Promoted to always-visible section |
| Creator Memory competing with editing tools | Demoted to bottom of Story |
| Loudness normalization hidden | Visible toggle in Audio |

---

## Remaining Friction (Honest)

- **Translate → Narration still spans two tabs**: Setting translate language in Subtitles, configuring voice in Words. A cross-tab hint was considered but not added — low impact.
- **Loudness sync**: The visible `edAudioLoudnorm` checkbox does not initialize from the hidden `evLoudnormEnabled` value on editor open. If a preset sets loudness to true, the checkbox won't reflect it. Future fix: read initial value in `evInitVoiceFields` or `openEditorView`.
- **AI tab name**: "AI" is accurate but generic. "Assistant" or "Converse" might be more distinctive in a future pass.
- **Story still has 5 sections**: Trim + AI Assist + AI Actions + Variants + Memory. Still more than ideal, but all sections are directly editing-relevant.
