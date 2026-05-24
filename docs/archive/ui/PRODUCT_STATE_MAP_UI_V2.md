# PRODUCT STATE — MAP-UI-V2: Creator Workflow UI

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(ui): creator workflow v2`
**Status:** Shipped

---

## Summary

Reorganizes the Output section from a settings-heavy grid into a creator workflow
interface. Same underlying form fields; new layout makes the most common choices
immediately visible and one-click reachable.

**Not:** a visual redesign, a CSS rewrite, or a feature addition.
**Yes:** a structural reorder of existing controls.

---

## What Changed

### Section 1 — Workflow Header

The UP21 Creator Preset bar (`cpBar`) remains at the top. A new `cpDnaHint` line
appears below it when the DNA confidence gate is met — same text as the clip list
hint ("Using recent creator style") but surfaced at the point of render configuration.

- `id="cpDnaHint"` — hidden by default, shown by `evSyncQsBar()` when `CreatorDNA.getAppliedHint()` returns a string.

### Section 2 — Quick Strategy Bar

A horizontal pill bar with four groups. Each pill updates the real form field
underneath. All underlying `<select>` / `<input type=checkbox>` elements remain
in the DOM in the Advanced section — pills are shortcuts, not replacements.

| Group | Pills | Updates |
|---|---|---|
| Platform | YouTube · TikTok · Reels | `evTargetPlatform` |
| Variant | Multi-variant (toggle) | `evMultiVariant` |
| Subtitle | Off · Clean · Viral · Karaoke | `evAddSubtitle` + `evSubStyle` |
| CTA | End Card (toggle) | `evCtaEnabled` |

Subtitle pill → style mapping:
- Clean → `story_clean_01`
- Viral → `tiktok_bounce_v1`
- Karaoke → `pro_karaoke`
- Off → unchecks `evAddSubtitle`

### Section 3 — Advanced Panel (collapsed by default)

The existing Strategy Preset row and full settings grid (Aspect Ratio, Output Profile,
Min/Max clip, Max clips, Multi-variant, Platform, CTA, Title Overlay) move inside a
collapsible `qsAdvBody` div. Default: `display:none`. Toggled by `evToggleAdvancedOutput()`.

The Advanced panel contains the canonical form fields. The Quick Strategy Bar pills
write to these same fields.

### Section 4 — Output Review: Limited Source Variety Note

When the render pipeline detects that all multi-variant clips share the same source
segment (HARDENING1 P3 — `multi_variant_collapsed`), the `selection_reason` field
on each clip is annotated with `[limited source variety — all variants share same
source clip]`. This annotation is now surfaced in the clip card as a small
`.clipVarietyNote` chip.

Previously: log-only (`logger.warning("multi_variant_collapsed ...")`).
Now: visible in the clip card output review.

---

## Files Changed

| File | Change |
|---|---|
| `backend/static/index.html` | Reorganized `evSectionBasic`: added `cpDnaHint`, `qsBar`, `qsAdvHeader`, `qsAdvBody`; moved grid inside Advanced section; added `evSyncQsBar()` to `onchange` of `evMultiVariant`, `evTargetPlatform`, `evCtaEnabled` |
| `backend/static/css/app.css` | New: `.qsBar`, `.qsGroup`, `.qsLabel`, `.qsPills`, `.qsPill`, `.qsPill.active`, `.qsAdvHeader`, `.qsAdvBody`, `.qsAdvArrow`, `.cpDnaHint`, `.clipVarietyNote` |
| `backend/static/js/editor-view.js` | New functions: `evSyncQsBar()`, `evQsSet()`, `evQsToggle()`, `evToggleAdvancedOutput()`; `evSyncQsBar()` called in both `openEditorView` paths and at end of `evApplyOutputPreset()` |
| `backend/static/js/creator-presets.js` | `_applySettingsToForm()` now calls `evSyncQsBar()` after applying settings |
| `backend/static/js/render-ui.js` | Ranking map adds `selectionReason` from `r.selection_reason`; clip card shows `.clipVarietyNote` when `selectionReason` contains "limited source variety" |
| `docs/ui/PRODUCT_STATE_MAP_UI_V2.md` | This file |

---

## Sync Behavior

`evSyncQsBar()` is called:
1. On both `openEditorView` and `openEditorView_withSession` paths (after module inits)
2. At the end of `evApplyOutputPreset()` (Strategy Preset applies a new config)
3. At the end of `_applySettingsToForm()` in `creator-presets.js` (Creator Preset applies)
4. On `onchange` of `evMultiVariant`, `evTargetPlatform`, `evCtaEnabled` in the Advanced panel
5. Inside `evQsSet()` and `evQsToggle()` after updating the form field

This guarantees pills and form fields are always in sync regardless of how the value was changed.

---

## Hierarchy (unchanged)

```
1. Manual creator change (after preset applied) — always wins
2. Preset-filled form fields                    — from applyPreset()
3. DNA nudges (UP20)                            — backend-only, gentle
4. Platform bias (UP14)                         — below DNA in subtitle tier
5. System defaults
```

---

## What Was Intentionally Not Changed

| Not Changed | Reason |
|---|---|
| Render pipeline | Pure frontend restructure |
| Form field IDs | All IDs unchanged — render submit reads by ID |
| Aspect ratio in Quick Strategy Bar | Per-video, not per-style; kept in Advanced |
| Subtitle font/size/color in Quick Strategy Bar | Power user settings; kept in Subtitle Style section |
| Strategy Preset row (evOutputPreset) | Moved inside Advanced; still accessible |
| DNA hint in clip list (clipsDnaHint) | Unchanged; cpDnaHint is a separate editor-side hint |

---

## Manual QA Checklist

### Quick Strategy Bar

- [ ] Platform pills reflect current `evTargetPlatform` value on editor open
- [ ] Clicking TikTok pill → `evTargetPlatform` = `tiktok`; pill highlights
- [ ] Variant pill toggles `evMultiVariant` checked state bidirectionally
- [ ] Subtitle Off → `evAddSubtitle` unchecked
- [ ] Subtitle Clean → `evAddSubtitle` checked + `evSubStyle` = `story_clean_01`
- [ ] Subtitle Viral → `evSubStyle` = `tiktok_bounce_v1`
- [ ] Subtitle Karaoke → `evSubStyle` = `pro_karaoke`
- [ ] CTA toggle syncs with `evCtaEnabled`; button text "CTA On" / "End Card"

### Preset apply syncs pills

- [ ] Apply "TikTok Fast" preset → TikTok pill active, Variant pill active, Viral pill active
- [ ] Apply "YouTube Clean" preset → YouTube pill active, Variant pill inactive, Clean pill active
- [ ] Apply Strategy Preset "TikTok US Viral" → pills update to match applied fields

### Advanced panel

- [ ] Advanced section hidden on editor open (display:none)
- [ ] Click "Advanced ▸" → shows Strategy Preset + full grid, arrow becomes "▾"
- [ ] Click "Advanced ▾" → hides again
- [ ] Changing Platform select inside Advanced → platform pill updates immediately
- [ ] Changing Multi-variant checkbox inside Advanced → Variant pill updates

### DNA hint

- [ ] With DNA confident + hook_forward ≥ 0.5 → cpDnaHint visible in Output section
- [ ] With DNA not confident → cpDnaHint hidden

### Output Review — Limited source variety

- [ ] Multi-variant render with short source → "Limited source variety" note on clip cards
- [ ] Long source with distinct variants → note absent

### No render regression

- [ ] All form field IDs unchanged — startRenderFromEditor() reads correct values
- [ ] Render payload includes correct platform, variant, CTA, subtitle settings
- [ ] Cancel / resume / retry / queue / websocket unaffected
