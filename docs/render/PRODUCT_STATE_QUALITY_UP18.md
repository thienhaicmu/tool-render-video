# PRODUCT STATE — QUALITY-UP18: Creator Feedback Learning

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): creator feedback learning`
**Status:** Shipped

---

## Summary

The tool now learns from what the creator actually keeps — not just what they set at
the start. Download a Story-first variant three times? The badge shows `· recent`
the next time it appears. Always render for TikTok? The platform dropdown
pre-selects it next session.

No ML. No cloud sync. No secret ranking changes. Same EMA pattern as UP12.
Two new signals. Two new gentle hints.

---

## What Gets Tracked

| Signal | Trigger | Storage |
|---|---|---|
| Variant download | Creator clicks Download on a variant clip | EMA per variant_type |
| Platform choice | Creator submits a render | EMA per platform key |

**What is NOT tracked:** clip content, video metadata, creator identity,
session timestamps, which video was rendered, personal behavior outside
these two explicit render actions.

**Storage:** localStorage key `cl_feedback_v1` — browser-local only. No backend
route. No database. No API calls.

---

## Part A — Variant Preference

### Signal: Download click on variant card
Recorded in `creator-feedback.js → recordVariantDownload(variantType)`.
Called by the Download button onclick in the multi-variant clip card.

Only fires for multi-variant renders (where `rk.variantType` is non-empty).
Regular single-clip downloads do not increment variant preference.

### EMA decay (same α=0.85 as UP12):
```
On each variant download of type X:
  for all variants v: count[v] *= 0.85
  count[X] += 1.0
```

After 2 consistent downloads of the same variant: count ≈ 1.85 (above threshold).
After 3 downloads: count ≈ 2.57 (strong signal). Different variant → preference shifts.

### Confidence gate:
- `top_score >= 1.5` — EMA score must indicate ≥ 2 consistent recent downloads
- `top_score >= second_score * 1.5` — clear preference, not noise
- No session minimum for variants (download is already a strong intent signal)

### Output: `· recent` badge
When the clip card's variant matches the learned preference, the variant badge
gains a subtle `· recent` suffix:

```
[Balanced · recent]    ← creator's downloaded variant 3+ times
[Aggressive]
[Story-first]
```

The suffix is rendered as a `<span class="cfVariantPref">` — 9px, 65% opacity,
no additional weight. Creator can read it or ignore it.

No ranking reorder. No variant suppression. Order is always: Aggressive → Balanced →
Story-first regardless of preference. The `· recent` is informational only.

---

## Part B — Platform Preference

### Signal: Render submit
Recorded in `creator-feedback.js → recordPlatformChoice(platform)`.
Called at every render submit in `editor-view.js`, alongside `recordSubtitleStyle`.

### EMA decay (same as variant):
```
On each render submit with platform X:
  for all platforms p: count[p] *= 0.85
  count[X] += 1.0
sessions += 1
```

### Confidence gate:
- `sessions >= 3` — minimum renders before platform hint fires (same as UP12 subtitle)
- `top_score >= 1.5`
- `top_score >= second_score * 1.5`

### Output: Platform dropdown pre-selection + hint
Same mechanism as UP12 subtitle hint. On editor open:
1. `CreatorFeedback.init()` is called
2. If confident platform preference exists AND creator hasn't manually changed the dropdown:
   - `evTargetPlatform` dropdown value is set to preferred platform
   - A hint span appears: `Using TikTok (recent preference)`
3. Creator changes dropdown → hint disappears, `data-cfManual` flag set, no re-application this session

---

## Part C — Learning Hierarchy

Full hierarchy for all editorial decisions (UP18 adds layer 3):

```
1. Creator manual choice (always wins — explicit UI action)
2. Creator taste memory — UP12 (subtitle style EMA)
3. Creator feedback learning — UP18 (variant + platform EMA)     ← NEW
4. Platform bias — UP14 (editorial nudges per platform)
5. System default
```

Layer 3 never overrides layers 1 or 2. Platform hint pre-populates only when
creator hasn't explicitly changed the dropdown this session.

---

## Part D — Safe Storage

**`cl_feedback_v1` schema:**
```json
{
  "variants": {
    "aggressive":  0.72,
    "balanced":    0.61,
    "story_first": 3.84
  },
  "platforms": {
    "tiktok":         4.10,
    "youtube_shorts": 0.72,
    "instagram_reels": 0.21
  },
  "sessions": 9
}
```

**What each value means:** EMA-weighted count of times the creator chose that
variant/platform. Higher = more recent and more frequent. Decays at 0.85× per
session.

**Reset:** `CreatorFeedback.reset()` clears all feedback data immediately.

---

## Part E — Observability

**Browser console:**
```javascript
// Read learned preferences:
CreatorFeedback.getPreferences()
// → { variantPreference: { variant: 'story_first', label: 'Story-first', confident: true },
//     platformPreference: { platform: 'tiktok', label: 'TikTok', confident: true },
//     sessions: 9 }

CreatorFeedback.getVariantPreference()
// → { variant: 'story_first', label: 'Story-first', confident: true } or null

CreatorFeedback.getPlatformPreference()
// → { platform: 'tiktok', label: 'TikTok', confident: true } or null

// Raw EMA counts:
JSON.parse(localStorage.getItem('cl_feedback_v1'))
```

No server-side logs (storage is frontend-only). Console is the observability surface.

---

## Files Changed

| File | Change |
|---|---|
| `backend/static/js/creator-feedback.js` | New module — EMA variant+platform tracking, platform hint injection, public API |
| `backend/static/index.html` | `<script>` tag for creator-feedback.js (after creator-taste.js) |
| `backend/static/js/editor-view.js` | `CreatorFeedback.init()` in both editor open paths; `recordPlatformChoice()` at render submit |
| `backend/static/js/render-ui.js` | `_cfVariantPref` computed before clip map; `recordVariantDownload()` in Download onclick; `· recent` in variant badge |
| `backend/static/css/app.css` | `.cfVariantPref` style (9px, 65% opacity) |
| `docs/render/PRODUCT_STATE_QUALITY_UP18.md` | This file |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|---|---|
| Speed/pacing preference | Speed is continuous, not categorical — EMA on raw values needs binning logic; deferred until there's a clear signal |
| Rerender pattern detection | Requires cross-session state comparison (what was downloaded before re-render); complex with marginal benefit over simple download EMA |
| Subtitle preference from downloaded variant | Variant subtitle is set by variant intent (UP13), not by creator direct choice — inferring creator's subtitle preference from variant downloads would be indirect and confusing |
| Variant ordering / rerank | Explicitly excluded — NO hidden ranking rewrite. The `· recent` badge is informational; order is always Aggressive → Balanced → Story-first |
| Cross-device sync | Out of scope for local-first design |
| "Preference profile" UI panel | CreatorMemory already has a panel; UP18 data can feed into it in a future phase |
| Backend storage of feedback | localStorage is sufficient; backend sync adds complexity with no benefit for single-device workflow |

---

## Manual QA Checklist

### Variant preference

- [ ] First variant download: `cl_feedback_v1.variants` updated in localStorage
- [ ] After 2–3 downloads of same variant: `getVariantPreference()` returns non-null
- [ ] Clip card shows `· recent` suffix on the preferred variant badge
- [ ] `· recent` suffix does NOT appear on non-preferred variant cards
- [ ] Downloading a different variant shifts the preference (EMA decay moves score)
- [ ] Non-variant renders: Download button does not add to `cl_feedback_v1.variants`
- [ ] Variant order in output panel unchanged: still Aggressive → Balanced → Story-first

### Platform preference

- [ ] First 2 renders: no platform hint shown (below MIN_SESS=3)
- [ ] After 3 renders with same platform: hint appears next to evTargetPlatform dropdown
- [ ] Hint text: `Using TikTok (recent preference)` (or matching platform name)
- [ ] Hint correctly pre-selects the `evTargetPlatform` dropdown on editor open
- [ ] Creator changes dropdown: hint disappears immediately
- [ ] `getPreferences().platformPreference` returns correct platform in console

### Creator manual always wins

- [ ] Pre-set platform can be changed freely — no lock, no confirmation prompt
- [ ] After manual change, hint disappears and does NOT reappear this session
- [ ] Re-opening editor for new video: manual flag clears, preference re-applied fresh

### Decay

- [ ] After 3 "story_first" then 3 "aggressive" downloads: aggressive score exceeds story_first
- [ ] Sessions counter increments on each render submit

### Safety

- [ ] Zero regression on: ranking, variant selection, subtitle rendering, render speed
- [ ] Cancel / resume / retry / queue all unaffected
- [ ] `ct_taste_v1` (UP12) data unchanged — separate key, no interference
- [ ] `cl_feedback_v1` absent before first render (clean install)
- [ ] No backend errors

### Reset

- [ ] `CreatorFeedback.reset()` clears all feedback data; hint disappears
- [ ] Does NOT affect `ct_taste_v1` (UP12 taste data)
