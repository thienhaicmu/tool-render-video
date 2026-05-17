# Product State — Post UX-IA2.2

**Date:** 2026-05-17
**Branch:** `feature/ai-output-upgrade`
**Phase:** UX-IA2.2 — Editor Workflow Polish (P1)

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed

Density and hierarchy refinements on top of the UX-IA2.1 re-architecture. No tab renames, no content moves between tabs. Changes are ordering, visual weight, and collapsibility improvements.

---

## IA2.2-A — Story: Fix Subs Demoted from Grid

**Before:** 7-button AI Edit Actions grid (6 editing tools + Fix Subs).  
**After:** 6-button grid (editing tools only) + subtle de-emphasised "quick subtitle fix →" link below.

Rationale: Fix Subs is a subtitle operation, not a creative edit. Removing it from the equal-weight grid reduces visual noise and redirects users to the dedicated Subtitles tab entry point.

```html
<!-- 6-button grid -->
<div class="aiActionGrid">...</div>
<!-- Subtle secondary entry point -->
<div class="evStorySubtleAction">
  <button class="evTinyBtn" onclick="EditorAiActions?.subtitleCleanup?.()">quick subtitle fix →</button>
</div>
```

Handler unchanged: `EditorAiActions?.subtitleCleanup?.()` — same action, two entry points.

---

## IA2.2-B — Export: Market & Target Section Ordering

**Before:** Quick Start Presets → Output Settings → Market Viral (at bottom)  
**After:** Quick Start Presets → Market & Target → Output Settings → Render Settings → Advanced Debug

Rationale: "Where are you publishing?" (Market & Target) is a creator-intent decision that logically precedes technical output configuration (aspect ratio, profile, clip limits). Moved before Output Settings.

Also renamed: "🌍 Market Viral (All Clips)" → "🌍 Market & Target" (clearer scope).

---

## IA2.2-C — Words: Text Layers Collapsible Wrapper

Text Layers wrapped in a collapsible `inspCollapsedGroup`. Collapsed by default. Auto-opens on Words tab activation when `_ev.textLayers.length > 0` (layers already exist).

```html
<div class="inspCollapsedGroup" data-insp-panel="text">
  <div class="inspGroupHdr" id="inspGroupTextLayersHdr" onclick="evToggleInspGroup('text-layers')">
    <span>Text Layers <span id="evSummaryTextLayers" ...></span></span>
    <span class="inspGroupArrow">▸</span>
  </div>
  <div class="inspGroupBody" id="inspGroupTextLayersBody">
    <div class="evSection" id="evSectionTextLayers" ...>
      ...full text layers editor unchanged...
    </div>
  </div>
</div>
```

`evSummaryTextLayers` span is in the header (shows layer count when populated — filled by `EditorTextRuntime`). The content below the header is the complete, unmodified text layers editor.

Auto-open JS in `setInspectorTab` (Words tab):
```javascript
const hasLayers = typeof _ev !== 'undefined' && Array.isArray(_ev.textLayers) && _ev.textLayers.length > 0;
evSetInspGroupOpen('text-layers', hasLayers);
```

`groupMap` in both `evToggleInspGroup` and `evSetInspGroupOpen` updated:
```javascript
'text-layers': { body: 'inspGroupTextLayersBody', hdr: 'inspGroupTextLayersHdr' },
```

---

## IA2.2-D — Story: Variants Compact Rail

**Before:** `#evSectionVariants` used `evSection` class — full card chrome (background gradient, border, 12px 14px padding). Included a "Timeline Variants" label.  
**After:** Uses `evCompactRail` class — no card chrome, tight 4px/6px padding. "Timeline Variants" label removed (buttons are self-describing). "Snapshots" label kept with reduced opacity.

```css
.evCompactRail {
  padding: 4px 2px 6px;
}
```

The gap between variants grid and snapshots reduced from `margin-top:10px` to `margin-top:6px`. Snapshots label opacity lowered to `.55`.

Visibility system unchanged — element retains `data-insp-panel="mode"` and `insp-panel-active` toggling.

---

## IA2.2-E — CSS Micro Hierarchy

Added to `workflow.css`:

```css
/* Compact variant rail */
.evCompactRail { padding: 4px 2px 6px; }

/* Story subtle action — de-emphasised secondary entry point */
.evStorySubtleAction { margin-top: 4px; text-align: right; }
.evStorySubtleAction .evTinyBtn {
  background: none; border: none;
  font-size: 10px; color: rgba(255,255,255,.28);
  padding: 2px 4px; letter-spacing: .02em;
}
.evStorySubtleAction .evTinyBtn:hover { color: rgba(255,255,255,.5); }
```

Existing `.evTinyBtn` base styles (trim controls, debug buttons) are unaffected — the scoped override only applies inside `.evStorySubtleAction`.

---

## Hierarchy Rules Established

| Rule | Applied in |
|------|-----------|
| Creator tools before developer tools | Export: Output Settings before Advanced Debug |
| Intent before configuration | Export: Market & Target before Output Settings |
| Primary entry points in dedicated tabs | Fix Subs primary in Subtitles; subtle hint in Story |
| Collapsible for infrequent-use content | Text Layers (Words), Advanced Debug (Export), AI Edit Actions (Story) |
| Compact rail for always-visible navigational tools | Variants + Snapshots in Story |

---

## Preserved Without Change

| System | Preserved |
|--------|-----------|
| All `EditorAiActions` handlers | ✓ |
| `EditorTextRuntime` — all IDs, all handlers | ✓ |
| `EditorAudioRuntime` — voice handlers, `evVoiceEnable`, `evVoiceFields` | ✓ |
| `evToggleInspGroup` / `evSetInspGroupOpen` group resolution | ✓ — `text-layers` entry added |
| Tab visibility system (`data-insp-panel` + `insp-panel-active`) | ✓ |
| Snapshot system (`aiSnapshotList`) | ✓ |
| Variant system (`EditorAiSessions?.applyVariant`) | ✓ |
| Market Viral handlers (`mvHandleChange`, `_mvState`) | ✓ |

---

## Remaining Friction (Honest)

- **Text Layers count in header**: `evSummaryTextLayers` is populated by `EditorTextRuntime` — if that module doesn't call update on open, the count won't show. This is a future `EditorTextRuntime.onTabActivate` responsibility, not a regression.
- **Variants without a label**: Removing "Timeline Variants" label assumes creators will discover what the 4 buttons do. The button labels (Viral, Cinematic, Aggressive, Balanced) are self-describing, but context for "these are timeline variants, not style presets" is lost.
- **Market & Target above Output Settings**: Creators who want to go straight to aspect ratio must scroll past Market & Target. Acceptable given the intent-first ordering principle.
