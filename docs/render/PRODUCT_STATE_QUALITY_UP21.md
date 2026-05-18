# PRODUCT STATE — QUALITY-UP21: Creator Style Presets

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): creator presets`
**Status:** Shipped

---

## Summary

Adds 1-click creator workflow bundles. Creator saves their render configuration once;
applies it in one click on every future render. Local only. No backend. No sync.

After UP13 (variants) + UP14 (platform) + UP16 (CTA) + UP20 (DNA), there are
too many knobs. Presets reduce that to: pick your style, start rendering.

---

## Part A — Preset Model

A creator preset saves a **render configuration bundle** — not project state, not
source files, not job history. Just the settings that define the creator's editorial style.

### Saveable fields

| Field | Form element | Type |
|---|---|---|
| `target_platform` | `evTargetPlatform` | select |
| `multi_variant` | `evMultiVariant` | checkbox |
| `subtitle_style` | `evSubStyle` | select |
| `cta_enabled` | `evCtaEnabled` | checkbox |
| `cta_type` | `evCtaType` | select |
| `render_profile` | `evRenderProfile` | select |
| `add_subtitle` | `evAddSubtitle` | checkbox |
| `reframe_strategy` | `evReframeStrategy` | select |

### NOT saved in a preset

Source file, session ID, trim in/out, volume, text layers, title overlay text,
BGM path, voice text, job state, render history. These are source-specific or
session-specific and must never be bundled into a style preset.

---

## Part B — Default Presets

Four tasteful defaults shipped with the product. Always present. Cannot be deleted.
Editable settings not locked — creator can change anything after applying.

### TikTok Fast
- Platform: TikTok | Multi-variant: on | Subtitle: Viral Bounce
- CTA: off | Profile: Fast | Reframe: Fast Center

### YouTube Clean
- Platform: YouTube Shorts | Multi-variant: off | Subtitle: Clean
- CTA: off | Profile: Balanced | Reframe: Fast Center

### Story Creator
- Platform: Instagram Reels | Multi-variant: on | Subtitle: Clean
- CTA: on (follow) | Profile: Quality | Reframe: Fast Center

### Tutorial Pro
- Platform: YouTube Shorts | Multi-variant: off | Subtitle: Clean
- CTA: on (part_2) | Profile: Balanced | Reframe: Fast Center

Built-in preset IDs are prefixed `__` (e.g., `__tiktok_fast`) to avoid collisions
with custom preset IDs (which use `cp_` + random suffix).

---

## Part C — Custom Presets

Creator can save, overwrite, and delete custom presets:

- **Save**: Click "Save" → prompt for name. If name matches existing custom preset,
  prompt to overwrite. Otherwise creates new.
- **Overwrite**: Save with same name as existing custom preset → confirmation → overwrites.
- **Delete**: Select a custom preset → "✕" button appears → confirmation → deleted.
- **Rename**: Delete old + save new (no explicit rename UI in v1 — kept minimal).
- **Duplicate**: Apply built-in, Save under new name (natural flow).

Custom presets are stored in `creator_presets_v1.custom` array. Built-in presets are
never stored — they exist only in code and are always current.

---

## Part D — Apply Preset

Applying a preset:
1. Fills the form fields from the preset's settings object
2. Triggers dependent UI updates (`evCtaTypeWrap` visibility, subtitle preview)
3. Records `activeId` in localStorage
4. Logs `preset_applied: <name>` via `addEvent()`

**Preset does NOT trigger render**. Creator still reviews all settings and clicks
"Start Render" manually. Preset is form-fill only.

---

## Part E — Hierarchy

```
1. Manual creator change (after preset applied) — always wins
2. Preset-filled form fields                    — from applyPreset()
3. DNA nudges (UP20)                            — backend-only, gentle
4. Platform bias (UP14)                         — below DNA in subtitle tier
5. System defaults
```

Applying a preset fills form fields (step 2). DNA then reads those fields indirectly
at render time and adds gentle backend nudges on top. Manual changes after applying
a preset simply overwrite the form values — no preset-locking, no automatic reset
to "custom" on field change (unlike the existing Strategy Preset system).

---

## Part F — Storage

**`creator_presets_v1`** — localStorage key.

```json
{
  "custom": [
    {
      "id":       "cp_abc123",
      "name":     "Podcast Clean",
      "builtIn":  false,
      "settings": { "target_platform": "youtube_shorts", "multi_variant": false, ... }
    }
  ],
  "activeId": "cp_abc123"
}
```

Built-in presets are NOT stored. `custom` array contains only creator-saved presets.
`activeId` tracks which preset was last selected (for dropdown restoration on re-open).

On `init()`: loads LS, rebuilds dropdown, restores `activeId` selection. Does NOT
re-apply the preset on editor open — form fields retain their last state.

---

## Part G — UI

Located at the top of the Output section, above the existing Strategy Preset row:

```
[ YouTube Clean ▼  ] [ Save ] [ ✕ ]
```

- Dropdown shows "Defaults" optgroup (4 built-in) + "My Presets" optgroup (custom, if any)
- "Save" button: always visible; prompts for name
- "✕" button: only visible when a CUSTOM preset is selected; hidden for built-ins
- Selecting from dropdown immediately applies the preset (fills fields)
- "— No Preset —" option always at top (deselects active preset)

No additional panel. No modal. No settings explosion.

---

## Part H — Observability

| Event | When | Via |
|---|---|---|
| `preset_applied: <name>` | Creator selects from dropdown | `addEvent()` in `applyPreset()` |
| `preset_applied: <name>` | At render submit (active preset) | `addEvent()` in render submit |
| `preset_saved: <name>` | Creator saves new preset | `addEvent()` in `promptSave()` |
| `preset_modified: <name>` | Creator overwrites existing preset | `addEvent()` in `promptSave()` |

---

## Files Changed

| File | Change |
|---|---|
| `backend/static/js/creator-presets.js` | New module: `BUILT_IN`, `PRESET_FIELDS`, `init()`, `applyPreset()`, `promptSave()`, `deleteActive()`, `getActive()` |
| `backend/static/index.html` | `<script src="creator-presets.js">` after creator-dna.js; `.cpBar` UI at top of Output section |
| `backend/static/css/app.css` | `.cpBar`, `.cpSelect`, `.cpSaveBtn`, `.cpDeleteBtn` styles |
| `backend/static/js/editor-view.js` | `CreatorPresets.init()` in both editor open paths; `preset_applied` log at render submit |
| `docs/render/PRODUCT_STATE_QUALITY_UP21.md` | This file |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|---|---|
| Rename preset (explicit UI) | Delete + re-save accomplishes the same; keeps friction low |
| Drag-to-reorder custom presets | Premature for v1; order is creation order |
| Import/export preset JSON | Creator can inspect `creator_presets_v1` in DevTools if needed |
| Preset sharing / cloud sync | Local only — no backend, no cloud |
| Preset thumbnails / descriptions | Visual noise for a text-based settings panel |
| Aspect ratio in preset | Creator sets aspect ratio per-video, not per-style |
| Playback speed in preset | Source-specific preference, not editorial identity |
| Min/max clip duration in preset | Source-specific |
| Strategy Preset integration | The existing "Strategy Preset" (scoring/market) is a different concern |
| Backend preset_applied event | Frontend-only logging is sufficient; no backend change needed |

---

## Manual QA Checklist

### Apply preset

- [ ] Select "TikTok Fast" → Platform = TikTok, Multi-variant checked, Subtitle = Viral Bounce
- [ ] Select "Tutorial Pro" → CTA checked, CTA type = Series / Part 2, Platform = YouTube Shorts
- [ ] Select "Story Creator" → Platform = Instagram Reels, Multi-variant checked, CTA = follow
- [ ] Select "YouTube Clean" → Multi-variant unchecked, Subtitle = Clean, CTA unchecked

### Manual override wins

- [ ] Apply "TikTok Fast" → Change subtitle to Karaoke → Render → subtitle is Karaoke (not Viral Bounce)
- [ ] No automatic reset to "No Preset" when creator changes a field

### Save custom preset

- [ ] Current settings → Save → name "Podcast Clean" → preset appears in "My Presets"
- [ ] Preset persists after page reload (check localStorage `creator_presets_v1`)
- [ ] Apply "Podcast Clean" → fields populate correctly

### Overwrite

- [ ] Modify settings → Save → use same name "Podcast Clean" → confirm overwrite → settings updated

### Delete

- [ ] Select "Podcast Clean" → ✕ button visible → click → confirm → preset removed
- [ ] Select any built-in → ✕ button NOT visible

### DNA still works

- [ ] Apply preset → Render → `dna_confidence:` still in job log
- [ ] DNA nudges apply on top of preset settings (backend-level, not form-level)

### No render regression

- [ ] Zero regression on: cancel / resume / retry / queue / render speed
- [ ] `preset_applied: Tutorial Pro` appears in event log at render submit
