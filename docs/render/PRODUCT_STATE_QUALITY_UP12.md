# PRODUCT STATE — QUALITY-UP12: Creator Taste Memory

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): creator taste memory`
**Status:** Shipped

---

## Summary

Lightweight behavioral preference layer that learns from real creator render choices.
No ML. No embeddings. No cloud sync. No black-box ranking.

After 3+ renders, the tool gently pre-populates subtitle style with the creator's
observed preference and shows a subtle hint. Creator can always override — manual
choice always wins.

---

## What Gets Tracked

| Signal | What it measures | How captured |
|---|---|---|
| Subtitle style | Which style creator uses per render | Recorded at render submit in editor-view.js |
| Download rank | Which ranked clip creator exports | Recorded on Download button click in render-ui.js |

**What is NOT tracked:** personal identity, behavior profiles, screen content,
clip content analysis, creator demographics, or any signals outside of the two
explicit render actions above.

---

## Part A — EMA-Based Taste Signals

**File:** `backend/static/js/creator-taste.js`

Preferences are stored using Exponential Moving Average (EMA) counts per style key.

**EMA update rule (α = 0.85):**
```
For each recorded render choosing style X:
  for all styles s: count[s] *= 0.85   // decay old behavior
  count[X] += 1.0                      // reinforce current choice
```

This means:
- After 3 consistent choices: count ≈ 2.57 (above confidence threshold)
- After 5 consistent choices: count ≈ 4.09 (strong signal)
- If creator switches style: old style decays, new style accumulates — preference follows naturally
- After ~15 sessions of a different style: old preference is effectively forgotten

**Confidence gate:**
- `sessions >= 3` — minimum renders before any preference fires
- `top_score >= 1.5` — at least ~2 consistent recent renders
- `top_score >= second_score * 1.5` — clear preference, not ambiguous noise

**Storage:** localStorage key `ct_taste_v1` — local only. No backend sync. No cloud.

```json
{
  "subtitle": {
    "pro_karaoke": 3.84,
    "tiktok_bounce_v1": 0.72
  },
  "download_rank": {
    "rank_1": 4.10,
    "rank_other": 0.21
  },
  "sessions": 7
}
```

---

## Part B — Weighting, Not Override

**Critical design constraint.**

The taste preference is applied as a form **default pre-population only**:
- Creator opens the editor → `evSubStyle` is pre-set to their preferred style
- Creator sees the pre-set value and can change it freely
- Changing the dropdown hides the hint and sets a `data-ctManual` flag
- Manual choice always wins — the pre-set is a suggestion, not a lock

The preference is reset per editor session: opening a new video clears the manual flag,
so the preferred default is applied fresh. If the creator leaves it unchanged, it
confirms the preference. If they change it, that new choice is recorded next render.

No backend ranking changes. No ranking reorder. No render pipeline changes.

---

## Part C — Decay + Recency

The EMA α=0.85 decay means:

| Scenario | Effect |
|---|---|
| 5 consistent "viral" renders | viral score ≈ 4.09, strong preference |
| Then 3 "clean" renders | viral ≈ 2.50, clean ≈ 2.57 — preference shifts to clean |
| Then 5 more "clean" renders | clean ≈ 5.66, viral decayed to 0.84 — clear clean preference |
| 15 sessions of different style | original preference effectively forgotten |

No manual cleanup needed. No session count resets. Stale preferences naturally fade.

---

## Part D — Explainable Hint

A small hint element is injected next to the `evSubStyle` dropdown when the editor opens.

**When confident preference exists:**
```
[evSubStyle dropdown: "Karaoke ▼]  Using Karaoke (recent preference)
```

**When creator changes the dropdown:**
- Hint disappears immediately
- `data-ctManual` flag prevents re-application for this editor session
- No further prompt

**Hint text examples:**
- `Using Karaoke (recent preference)`
- `Using TikTok Bounce (recent preference)`
- `Using Clean (recent preference)`

The hint is subtle (11px, gray, italic). It appears only when the preference is
confident. It never appears during the first 3 renders. It never nags or repeats.

---

## Part E — Safe Storage

**What is stored:**
- EMA count per subtitle style key (e.g. `"pro_karaoke": 3.84`)
- EMA count of rank-1 vs rank-other downloads
- Total sessions count

**What is NOT stored:**
- Creator name, email, or identity
- Video content, titles, or metadata
- Exact timestamps or session records
- Any information that can identify the creator's content or audience

**Where it's stored:** localStorage key `ct_taste_v1` — browser-local only.
No backend route added. No database table added. No API calls.

**Reset:** `CreatorTaste.reset()` clears all taste data immediately.

---

## Part F — Observability

The following can be read for QA:

```javascript
// In browser console:
CreatorTaste.getPreferences()
// Returns: { subtitleStyle: { style, label, confident }, prefersAlternativeClip, sessions }

CreatorTaste.getSubtitleStyleHint()
// Returns: { style, label, confident } or null

JSON.parse(localStorage.getItem('ct_taste_v1'))
// Raw EMA counts
```

No server-side logs added (storage is frontend-only). For QA, the browser console
is the observability surface.

---

## Files Changed

| File | Change |
|---|---|
| `backend/static/js/creator-taste.js` | New module — EMA taste tracking, hint injection, public API |
| `backend/static/index.html` | `<script>` tag for creator-taste.js (after creator-memory.js) |
| `backend/static/js/editor-view.js` | `CreatorTaste.init()` in both editor open paths; `recordSubtitleStyle()` at render submit |
| `backend/static/js/render-ui.js` | `subtitleStyle` in `buildRenderHistoryEntry`; `recordDownload()` on Download button |
| `docs/render/PRODUCT_STATE_QUALITY_UP12.md` | This file |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|---|---|
| Backend sync of taste data | localStorage is sufficient; cross-device sync adds complexity with minimal benefit |
| Intro/hook style preference | Creator doesn't directly choose the personality — it's AI-selected from content_type |
| Pacing preference (playback_speed, cut density) | Signal too indirect; creator doesn't have a named "pacing" control |
| Render profile preference | Only 3 options (balanced/quality/fast); not enough variance to be useful |
| Clip content-type preference | Requires correlating content_type with export — adds complexity for marginal gain |
| Showing preferred clip rank in UI | "AI usually picks your preferred clip" — not enough signal to be useful yet |
| Preference sync across devices | Out of scope for local-first design |
| "Taste profile" panel | CreatorMemory already has a preference panel; UP12 data can feed into it later |

---

## Manual QA Checklist

### Subtitle preference

- [ ] First 2 renders: no hint shown (below MIN_SESSIONS=3)
- [ ] After 3 renders with same subtitle style: hint appears next to evSubStyle
- [ ] Hint text: `Using [style name] (recent preference)` — gray, italic, small
- [ ] Hint correctly pre-selects the `evSubStyle` dropdown value on editor open
- [ ] Creator changes dropdown: hint disappears immediately
- [ ] After preference change, next render records new style — hint shifts over time
- [ ] `CreatorTaste.getSubtitleStyleHint()` returns `{style, label, confident: true}` in console

### Download rank recording

- [ ] Clicking Download on rank-1 clip: `ct_taste_v1.download_rank.rank_1` increments
- [ ] Clicking Download on rank-2 clip: `ct_taste_v1.download_rank.rank_other` increments
- [ ] No download recorded when rank is 0 (no ranking data available)

### Decay

- [ ] After 3 "viral" then 3 "clean" renders: clean score exceeds viral in localStorage
- [ ] `sessions` counter increments on each render submit

### Manual override

- [ ] Pre-populated value can be changed freely — no lock, no confirmation
- [ ] Re-opening editor for new video: manual flag clears, preference re-applied
- [ ] `CreatorTaste.reset()` clears all taste data; hint disappears

### Safety

- [ ] No regression on ranking, pacing, subtitle rendering, render speed
- [ ] No backend errors from new code
- [ ] Cancel / resume / retry / queue all unaffected
- [ ] `ct_taste_v1` localStorage key is absent before first render (clean install)
