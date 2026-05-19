# Expert Preset Output Override Audit

**Scope:** `evApplyOutputPreset()` — Expert Preset dropdown in Advanced Settings  
**Audit type:** Creator trust / silent override analysis  
**Date:** 2026-05-19

---

## 1. Fields Changed by Each Preset

All 5 Expert Presets live in [editor-view.js:2667–2717](../../backend/static/js/editor-view.js#L2667).  
Applied via `evApplyOutputPreset()` at [editor-view.js:2754–2858](../../backend/static/js/editor-view.js#L2754).  
Strategy: **partial merge** — only non-null preset fields are written; null fields are skipped.

### TikTok US Viral (`tiktok_us_viral`)

| Field | Value set | Category |
|---|---|---|
| `market` | `"US"` | Style |
| `subtitleTone` | `"bold"` | Style |
| `subtitleStyle` | `"tiktok_bounce_v1"` | Style |
| `subtitleFont` | `"Bungee"` | Style |
| `keywordHighlight` | `true` | Style |
| `renderProfile` | `"quality"` | Quality |
| `sourceQuality` | `"high_1440"` | Quality |
| `reframeStrategy` | `"fast_center"` | Quality |
| `combinedScoring` | `true` | Scoring |
| `adaptiveScoring` | `true` | Scoring |
| `autoBestClips` | `true` | Scoring |
| `partOrder` | `"viral"` | Scoring |
| `hookMode` | `"selected_suggested_only"` | Style |
| `bestExportEnabled` | `false` | Output |
| `bestExportCount` | `3` | Output |
| **`maxExportParts`** | **`5`** | **⚠ Output Quantity** |

### EU Clean Review (`eu_clean_review`)

| Field | Value set | Category |
|---|---|---|
| `market` | `"EU"` | Style |
| `subtitleTone` | `"clean"` | Style |
| `subtitleStyle` | `"story_clean_01"` | Style |
| `subtitleFont` | `"Montserrat"` | Style |
| `keywordHighlight` | `false` | Style |
| `renderProfile` | `"balanced"` | Quality |
| `sourceQuality` | `"standard_1080"` | Quality |
| `reframeStrategy` | `"fast_center"` | Quality |
| `combinedScoring` | `true` | Scoring |
| `adaptiveScoring` | `true` | Scoring |
| `autoBestClips` | `true` | Scoring |
| `partOrder` | `"viral"` | Scoring |
| `bestExportEnabled` | `false` | Output |
| `bestExportCount` | `3` | Output |
| **`maxExportParts`** | **`5`** | **⚠ Output Quantity** |

### JP Storytelling (`jp_storytelling`)

| Field | Value set | Category |
|---|---|---|
| `market` | `"JP"` | Style |
| `subtitleTone` | `"clean"` | Style |
| `subtitleStyle` | `"story_clean_01"` | Style |
| `subtitleFont` | `"Montserrat"` | Style |
| `keywordHighlight` | `false` | Style |
| `renderProfile` | `"quality"` | Quality |
| `sourceQuality` | `"high_1440"` | Quality |
| `reframeStrategy` | `"fast_center"` | Quality |
| `combinedScoring` | `true` | Scoring |
| `adaptiveScoring` | `true` | Scoring |
| `autoBestClips` | `true` | Scoring |
| `partOrder` | `"viral"` | Scoring |
| `bestExportEnabled` | `false` | Output |
| `bestExportCount` | `3` | Output |
| **`maxExportParts`** | **`5`** | **⚠ Output Quantity** |

### Clean Subtitle Focus (`clean_subtitle_focus`)

| Field | Value set | Category |
|---|---|---|
| `subtitleStyle` | `"story_clean_01"` | Style |
| `subtitleFont` | `"Montserrat"` | Style |
| `keywordHighlight` | `false` | Style |
| `hookMode` | `"off"` | Style |

No output quantity fields. Safe.

### Fast Batch Ranking (`fast_batch_ranking`)

| Field | Value set | Category |
|---|---|---|
| `renderProfile` | `"fast"` | Quality |
| `sourceQuality` | `"standard_1080"` | Quality |
| `reframeStrategy` | `"fast_center"` | Quality |
| `combinedScoring` | `true` | Scoring |
| `adaptiveScoring` | `true` | Scoring |
| `autoBestClips` | `true` | Scoring |
| `partOrder` | `"viral"` | Scoring |
| `bestExportEnabled` | `false` | Output |
| **`maxExportParts`** | **`5`** | **⚠ Output Quantity** |

---

## 2. Safe Overrides vs Dangerous Overrides

### A — Safe (Style / Quality / Scoring)

These fields describe *how* the output looks or scores. A creator applying "TikTok US Viral" expects their subtitle to bounce, their font to be Bungee, and their ranking to favor virality. No surprise.

| Fields | Why safe |
|---|---|
| `market`, `subtitleTone`, `subtitleStyle`, `subtitleFont` | Pure aesthetic — expected from a named style preset |
| `keywordHighlight`, `hookMode` | Platform-specific feature toggles — expected |
| `renderProfile`, `sourceQuality`, `reframeStrategy` | Processing quality — expected tradeoff for a preset |
| `combinedScoring`, `adaptiveScoring`, `autoBestClips`, `partOrder` | AI ranking behavior — expected for a named viral preset |
| `bestExportEnabled`, `bestExportCount` | Controls the "best export" feature, not primary clip count |

### B — Dangerous (Output Quantity)

These fields control **how many clips the creator receives**. A creator's mental model is:

> "I set Max Clips to 10. I apply a style preset. I get 10 clips in the TikTok style."

Not:

> "I set Max Clips to 10. I apply a style preset. I secretly get 5 clips."

| Field | Affected presets | Hardcoded value | Risk |
|---|---|---|---|
| **`maxExportParts`** | TikTok US Viral, EU Clean Review, JP Storytelling, Fast Batch Ranking | `5` | If creator had `0` (unlimited) or `10+`, they silently lose clips |

**4 out of 5 presets override `maxExportParts` to hardcoded `5`.**

---

## 3. Creator Trust Risks

### Risk 1 — Silent reduction (HIGH)

**Scenario:**  
Creator shoots a 20-minute review. Scene detection finds 18 good clips. Creator sets Max Clips to 0 (unlimited). Creator applies "TikTok US Viral" for the subtitle and hook style. Renders. Gets 5 clips.

Creator sees 13 clips missing with no explanation. Assumes the AI failed.

**Current mitigation:**  
After applying, the UI shows: `"Preset applied: TikTok US Viral | fields: subtitle style, max clips, ..."` — a small hint string. This is easy to miss. No alert, no toast, no confirmation.

---

### Risk 2 — Direction inversion (MEDIUM)

**Scenario:**  
Creator was set to Max Clips = 8 (they want 8 renders for A/B testing). Applies "Fast Batch Ranking" expecting it to optimize the ranking of those 8. Instead it silently reduces them to 5. Creator expected the preset to improve selection quality *within* their chosen quantity, not override it.

---

### Risk 3 — Preset identity mismatch (MEDIUM)

"TikTok US Viral" sounds like a **style** preset (bold subtitle, US market targeting, viral scoring). Creators do not expect a style preset to control *how many clips* they get. The name gives no signal that output count is in scope.

"Fast Batch Ranking" sounds like a **workflow efficiency** preset. A creator could reasonably assume it means "rank faster" not "give me fewer outputs."

---

### Risk 4 — No pre-apply preview (LOW-MEDIUM)

The `evApplyOutputPreset()` function applies immediately on `onchange` with no preview step. For style fields this is fine (instantly reversible). For output quantity it means the damage is done before the creator can read what's about to change.

---

## 4. Recommended Fix

### Rule: Presets must not silently reduce output count

A preset's job is to configure *how* a video looks and scores, not *how many* the creator gets. Output count is the creator's explicit workflow decision.

### Option A — Remove `maxExportParts` from market/style presets (Recommended)

**TikTok US Viral, EU Clean Review, JP Storytelling** have no legitimate reason to own `maxExportParts`. Their purpose is market style + subtitle + scoring. Set it to `null` in the preset definition so it is skipped during merge.

**Fast Batch Ranking** is a borderline case — it's explicitly about throughput. Keeping `maxExportParts: 5` there is defensible *only if* the preset is clearly labeled as a quantity preset (e.g., renamed to "Fast 5-Clip Draft").

**Change in [editor-view.js:2667–2717](../../backend/static/js/editor-view.js#L2667):**
```js
// TikTok US Viral, EU Clean Review, JP Storytelling:
maxExportParts: null,  // was: 5
```

### Option B — Preserve creator selection (if Option A is not viable)

If the preset must set `maxExportParts` for some technical reason, the apply function should check whether the creator has manually touched the field before overwriting:

```js
// In evApplyOutputPreset(), before writing maxExportParts:
const currentVal = parseInt(g('evMaxExportParts')?.value ?? '0');
const isCreatorSet = currentVal !== 0;  // 0 = "never explicitly set" default
if (!isCreatorSet || presetCfg._allowQuantityOverride) {
  mp.value = cfg.maxExportParts;
}
```

This is more complex and adds hidden state. Option A is cleaner.

### Option C — Warn before reducing (fallback)

If neither A nor B, add a pre-apply check: if the preset would change `maxExportParts` to a value *lower than* the current value, show a one-line confirm:

> "This preset will change Max Clips from 10 → 5. Continue?"

This is the least-breaking change but still puts friction on every apply.

---

## 5. Minimal Implementation (Option A)

Three-line change in [editor-view.js:2667–2717](../../backend/static/js/editor-view.js#L2667):

```js
// tiktok_us_viral
maxExportParts: null,   // removed — style preset should not own output count

// eu_clean_review  
maxExportParts: null,   // removed

// jp_storytelling
maxExportParts: null,   // removed

// fast_batch_ranking — keep as 5 but rename preset to signal quantity
// Consider: rename label to "Fast 5-Clip Draft" to set expectation
maxExportParts: 5,      // intentional — this is a quantity-defining preset
```

**No logic change required.** Partial merge already skips `null` fields — setting the value to `null` is all that's needed.

---

## 6. Keep / Fix / Remove

| Item | Verdict | Reason |
|---|---|---|
| Style/quality fields in presets | **Keep** | This is what presets are for |
| Scoring fields in presets | **Keep** | Expected for named viral/story presets |
| `maxExportParts` in TikTok US Viral | **Remove** | Style preset has no claim on output count |
| `maxExportParts` in EU Clean Review | **Remove** | Style preset has no claim on output count |
| `maxExportParts` in JP Storytelling | **Remove** | Style preset has no claim on output count |
| `maxExportParts` in Fast Batch Ranking | **Fix label** | Quantity intent is implied but name doesn't say it |
| Post-apply summary hint | **Keep** | Useful feedback once you know to look for it |
| Pre-apply warning for quantity reduction | **Add** | Even with Option A, still worth a one-liner for future presets |

---

## 7. One-Sentence Creator Standard

> A preset changes how your video looks and how clips are scored — it never changes how many clips you get, unless the preset name explicitly says so.

---

*Traced from: `editor-view.js` lines 2667–2858 (preset definitions + apply function), `index.html` lines 1115–1157 (UI selector + `evMaxExportParts` field)*
