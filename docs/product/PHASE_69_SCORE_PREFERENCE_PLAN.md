# PHASE 69 — SCORE PREFERENCE LEARNING PLAN
## Learn Taste From Ranking Signals + Creator Actions

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 68 Feedback Visibility — COMPLETE, zero regressions
**Plan date:** 2026-05-19
**Planning only — no implementation in this session**

---

## 1. EXECUTIVE SUMMARY

Phase 68 made learning effects **visible**. Phase 69 asks the next question: can the tool actually **learn what kind of clips the creator prefers** based on which clips they Keep, Avoid, and Download?

The answer is yes — but only if we tie the creator action to the ranking signal that characterizes the clip they acted on. That link is missing today.

**The gap:**

- Phase 66 surfaces `ranking_components` per clip (`hook_score`, `speech_density_score`, `retention_score`, `duration_fit_score`)
- Phase 67 captures Keep/Avoid/Rerender actions in `ClipSteering`
- These two systems never talk. Keep/Avoid stores timestamps. It never stores *what kind of clip* was Kept or Avoided.

**Phase 69 closes this gap:**

When creator clicks Keep on a 78-hook, 62-speech clip, record: "kept a hook-heavy clip." After 6+ consistent keep/download patterns of high-hook clips, surface: "Hook-heavy preference."

**What Phase 69 does NOT do:**

- Rerank clips
- Override any creator setting
- Auto-apply preferences
- Invent signals that aren't in ranking_components

**Implementation scope:** 3 commits. New `score-preference.js` module, 2 wiring edits. ~90 lines total. One new localStorage key.

---

## 2. EXISTING SIGNAL AUDIT

### 2A. Creator actions — what already exists

| Action | File | When fired | Current data captured | Missing |
|---|---|---|---|---|
| Keep (csKeepClip) | `render-ui.js` | Creator clicks Keep button | `start_sec`, `end_sec`, `label` → ClipSteering | Ranking component signals for that clip |
| Avoid (csAvoidClip) | `render-ui.js` | Creator clicks Avoid button | `start_sec`, `end_sec`, `label` → ClipSteering | Ranking component signals for that clip |
| Rerender (csKeepAndRerender) | `render-ui.js` | Creator clicks Rerender | `start_sec`, `end_sec`, `label` → ClipSteering | Ranking component signals |
| Download | `render-ui.js` clip card | Creator clicks Download link | `rk.rank` → `CreatorTaste.recordDownload()` | Ranking component signals for that clip |
| Rank-1 download | `creator-taste.js` | Post-download EMA | `download_rank.rank_1` / `rank_other` | Which *kind* of clip was downloaded |
| Subtitle style select | `creator-taste.js` | Per render | Subtitle style → EMA | N/A (separate preference) |

### 2B. Ranking signals — what already exists at clip-card time

All six `ranking_components` fields are available in `rk.rankingComponents` at clip card render time:

| Field | Range | Meaning | Available in rk? |
|---|---|---|---|
| `hook_score` | 0–100 | Opening hook quality | **YES** — `rk.rankingComponents.hook_score` |
| `speech_density_score` | 0–100 | Spoken content density | **YES** |
| `retention_score` | 0–100 | Pacing stability | **YES** |
| `duration_fit_score` | 0–100 | How close to platform-ideal duration | **YES** |
| `market_score` | 0–100 | Market fit (50 = no MV scoring) | **YES** (skip when 50.0) |
| `segment_viral_score` | 0–100 | Overall primary score | **YES** (too broad to be a preference signal — excluded) |

### 2C. The data link problem

**Problem:** `csKeepClip(startSec, endSec, label)` fires in a click handler. At that moment, `rk.rankingComponents` is not in scope — it exists only in the `ranking` Map inside the render loop that built the clip card.

**Solution:** Store the render-time `ranking` Map globally as `window._r69RankMap = ranking` at the end of each render cycle. Then in `csKeepClip(startSec, endSec, label, partNo)`, look up `window._r69RankMap.get(partNo)?.rankingComponents`. The `partNo` is added as a 4th parameter to `csKeepClip` and `csAvoidClip` (backwards-compatible — existing callers without it get `undefined`, handled with `Number(partNo) || 0`).

**Why `partNo` not `startSec/endSec`?** The rank map is indexed by `part_no`, not by timestamp. Lookup by partNo is O(1) and unambiguous.

---

## 3. STRONG VS WEAK SIGNAL MATRIX

### Signal strength definition

**Strong signal:** Creator deliberately chose to export or invest time — expressing clear preference.
**Medium signal:** Creator marked the clip as "want" but didn't necessarily download.
**Weak/negative signal:** Creator chose to remove the clip from consideration.

| Action | Preference weight | Why |
|---|---|---|
| **Download** | **+2** | Strongest: creator exported this clip — actual production choice |
| **Keep (csKeepClip)** | **+1** | Medium: marked for prioritisation in next render, but not yet exported |
| **Avoid (csAvoidClip)** | **−1** | Negative: deliberately excluded — reveals what creator doesn't want |
| **Rerender (csKeepAndRerender)** | **+1** | Same weight as Keep — it locks the clip AND rerenders |
| Rerender without lock | 0 | Pure dissatisfaction signal — doesn't tell us what they preferred |

### Ranking component thresholds — "high" definition

A component is considered **high** for a clip when it signals a meaningful characteristic above neutral:

| Component | "High" threshold | Rationale |
|---|---|---|
| `hook_score` | > 65 | Clearly above neutral (50 = default); 65+ = measurably strong hook |
| `speech_density_score` | > 65 | Same reasoning; below 40 = sparse speech |
| `retention_score` | > 65 | Stable pacing; captures the consistently well-edited clip type |
| `duration_fit_score` | > 70 | Higher threshold — duration fit is more context-specific |
| `market_score` | > 65 AND ≠ 50.0 | Skip when exactly 50 (no MV scoring active — not a real signal) |

`segment_viral_score` is **excluded** as a preference signal — it is the primary ranking composite and would dominate, producing a tautological "prefers highly ranked clips" that adds nothing.

### What the signal combination means

| Keep/Download + high dimension | Preference inference |
|---|---|
| Hook > 65 on 3+ kept/downloaded clips | Hook-heavy preference |
| Speech > 65 on 3+ kept/downloaded clips | Speech-heavy preference |
| Retention > 65 on 3+ kept/downloaded clips | Smooth-paced preference |
| Duration fit > 70 on 3+ kept/downloaded clips | Well-timed preference |
| Avoid + high hook on 2+ avoided clips | Disprefers hook-forward |
| No consistent pattern across 8+ signals | No preference (show nothing) |

---

## 4. PREFERENCE LEARNING MODEL

### Storage schema — `score_pref_v1`

New localStorage key `score_pref_v1`:

```json
{
  "signals": [
    {
      "action": "download",
      "ts": 1716123456000,
      "hook_high": true,
      "speech_high": false,
      "retention_high": true,
      "duration_high": false,
      "market_high": false
    }
  ],
  "total": 7,
  "dim_scores": {
    "hook": 5.0,
    "speech": -1.0,
    "retention": 4.0,
    "duration": 1.0,
    "market": 0.0
  }
}
```

**Signal cap:** last 30 signals (oldest pruned). **TTL:** 30 days per signal (`Date.now() - ts > 30 * 86400000`). Both caps applied on every write.

### Score accumulation

When a signal arrives with `action` and `rankingComponents`:

```
weight = download → 2, keep → 1, avoid → −1
for each tracked dimension d:
  if component[d] is "high":
    dim_scores[d] += weight
```

Negative scores are allowed (active avoidance pattern). Scores are not EMA-decayed — they accumulate naturally with recency bias from the 30-signal cap (old signals fall off, preference updates with recent behavior).

### Reading the preference

```
getPreference() → { confident: bool, dimension: string, label: string } | null

confident when:
  total >= 5
  AND top dim_score >= 3.0 (net positive — 3+ download-weight events)
  AND top dim_score > second_dim_score * 1.5 (clear leader, not noise)

dimension labels:
  "hook"       → "Hook-heavy clips"
  "speech"     → "Speech-heavy clips"
  "retention"  → "Smooth-paced clips"
  "duration"   → "Well-timed clips"
  "market"     → "Market-fit clips"
```

If no dimension meets the threshold, return `null`. Never fabricate.

### Public API

```javascript
const ScorePreference = (() => {
  // ...internal...
  return {
    recordSignal(action, components),  // 'keep'|'avoid'|'download', rankingComponents dict
    getPreference(),                    // → { confident, dimension, label } | null
    getCount(),                         // → { total, signals: n }
    reset(),
  };
})();
```

---

## 5. THRESHOLD RULES

### Minimum signal requirements

| Threshold | Value | Rationale |
|---|---|---|
| Minimum total signals before ANY inference | 5 | Below 5 actions is not yet a pattern — could be any upload's quirks |
| Minimum net score for confident dimension | 3.0 | Equivalent to 3 downloads or 6 keeps of high-scoring clips in that dimension |
| Top dimension must lead second by | ≥ 1.5× | Clear preference, not statistical noise |
| Minimum "high" component count per dimension | 3 (implied by score ≥ 3.0) | Prevents single-download outsized influence |

### Anti-overfitting rules

| Rule | Implementation |
|---|---|
| Rolling window of 30 signals | Old signals expire by count; stale signals expire by TTL |
| No single-render preference lock | Signal must accumulate across at least 2 separate timestamp clusters (≥ 2 distinct `ts` values > 60s apart) |
| Hard reset | `ScorePreference.reset()` clears all signals. Available via Preferences Reset (existing system) |
| No inference during a single session before signal count crosses 5 | Gate is on total stored signals, not current session only |

### When to suppress

| Condition | Action |
|---|---|
| All dim_scores are within 1.5× of each other | No dominant preference — show nothing |
| `total < 5` | Insufficient data — show nothing |
| No ranking_components available for a clip (all zero or empty) | Do not record signal for that clip |
| market_score === 50.0 exactly | Skip market dimension for that signal (no MV scoring was active) |

---

## 6. SAFE INFLUENCE MODEL

### Phase 69 influence level: display-only

Phase 69 surfaces preference as a chip. It does **not** rerank clips. It does not change `evMinPart`/`evMaxPart`. It does not auto-apply any setting.

The chip is informational only:
```
[🎯 Hook-heavy clips]
```

Shown in the same pre-render chip row as `[DNA active]`, `[Series]`, `[🧠 Learned]`.

### Why no reranking in Phase 69

Ranking reranking based on learned preference creates a **feedback loop risk**: the tool shows hook-heavy clips → creator keeps a hook-heavy clip → hook preference score increases → tool shows even more hook-heavy clips → narrowing spiral. This is the "filter bubble" problem in miniature.

Phase 69 avoids this by surfacing the preference transparently without acting on it. Creator can see "hook-heavy preference is active" and choose to Keep a speech-heavy clip explicitly — overriding the learned pattern with a stronger signal.

If a ranking nudge is implemented in a future phase, it must be:
- Hard-capped (max +2 on a 0–100 scale, max 0.05 weight on a 0–10 score)
- Togglable by creator
- Decayed per render (not compounding)

### Phase 69 safe influence summary

| Influence | Phase 69 | Notes |
|---|---|---|
| Chip in pre-render area | **YES** | Informational, no action taken |
| Ranking change | **NO** | Deferred to Phase 70 if justified |
| Auto-set any control | **NO** | Creator controls all inputs |
| Changing clip selection | **NO** | Backend selection untouched |
| FeedbackLearning bias amplification | **NO** | Out of scope |

---

## 7. TRUST AND UX RULES

### Hard limits

| Rule | Rationale |
|---|---|
| Never show preference after < 5 signals | Single-render patterns are coincidental |
| Never claim the tool "knows" creator's taste | Only claim a pattern was observed |
| Never show raw scores (hook: 78%) | The label is enough; the number feels surveillance-like |
| Never show which clips contributed to preference | "Based on 3 recent downloads" not "Based on clips at 23s, 78s, 145s" |
| Never auto-set any filter based on preference | Preference is observed, not acted on in Phase 69 |
| Always show "Reset preferences" path | `ScorePreference.reset()` accessible (wired to existing preference reset button or ChipMemory tooltip) |
| Never create a feedback loop | Display only; no reranking from this signal |

### Trust language rules

| Creator reads | Trust level | Use? |
|---|---|---|
| "Hook-heavy clips" | HIGH — plain description of a clip type | YES |
| "You prefer hook-heavy clips" | MEDIUM — implies certainty | AVOID — use "Preference: Hook-heavy clips" |
| "AI detected your hook preference" | LOW — surveillance-like | NO |
| "Preference: Speech-heavy clips" | HIGH — factual, non-prescriptive chip label | YES |
| "You have a hook_score bias of 0.72" | VERY LOW — technical junk | NEVER |

### Chip label copy

| Dimension | Chip label |
|---|---|
| `hook` | `Preference: Hook clips` |
| `speech` | `Preference: Speech clips` |
| `retention` | `Preference: Smooth pacing` |
| `duration` | `Preference: Short clips` (if duration_fit_score on short clips) or `Preference: Long clips` — see note below |
| `market` | `Preference: Market-fit clips` |

**Duration note:** `duration_fit_score` measures closeness to platform ideal — a high score means "close to ideal for the platform," not inherently short or long. The chip should say "Preference: Duration-fit clips" (concise: "Duration fit"). This avoids misleading the creator about clip length.

---

## 8. UI RECOMMENDATION

### Chip placement

The preference chip belongs in the `v3SteeringPanel` chip row, built by `v3RefreshSteeringPanel()` in `editor-view.js`. It appears alongside existing chips: `[🧠 Learned]`, `[DNA active]`, `[Series]`, etc.

**After Phase 69:**
```
[Hook pref] [DNA active] [Series] [🔒 2 kept]
```

The preference chip uses CSS class `v3Chip v3ChipPref`. New CSS entry in `app.css`:
```css
.v3ChipPref { color:#2dd4bf; border-color:rgba(45,212,191,.3); background:rgba(45,212,191,.08); }
```

(Teal — distinct from existing purple/green/amber/red chip colors. Signals "learned taste" vs "active steering".)

### Tooltip content

Chip tooltip (on hover): `"Based on your Keep and Download patterns"` — factual, non-specific about count or timestamps.

### When it appears / disappears

- **Appears:** `ScorePreference.getPreference()` returns non-null AND is confident
- **Disappears:** Preference reset OR `getPreference()` returns null (signals fall below threshold after rolling window prunes old data)
- **Ordering:** shown as first chip in the pre-render row (most relevant to clip selection)

### What it does NOT do

- Clicking the chip does nothing actionable — it is display-only in Phase 69
- It does not expand to a detail panel
- It does not offer "disable this preference" — the existing "Reset preferences" button handles that

---

## 9. SAFE ROLLOUT PLAN

### Pre-implementation verification

**Before 69.1:**
- Confirm `ranking_components` fields are populated in the rank map (`rk.rankingComponents`) for recent renders
- Confirm `window.CreatorTaste` is globally accessible from `render-ui.js`
- Confirm `score_pref_v1` is not already a used localStorage key anywhere in the codebase

**Before 69.2:**
- Confirm `csKeepClip` is only called from clip card onclick attributes (no other callers that would break with 4-param signature)
- Confirm `csAvoidClip` is only called from clip card onclick attributes (same check)
- Confirm `partNo` is available in scope at the point where the onclick is built in the clip card template

**Before 69.3:**
- Confirm `v3RefreshSteeringPanel()` is the canonical chip-building function
- Confirm `ScorePreference` is loaded (in `index.html`) before `editor-view.js`

### Stop conditions

Stop if:
- `ranking_components` is consistently empty (`{}`) in recent renders — no data to learn from
- `csKeepClip` has callers outside the clip card template that would break with the new 4th param

---

### Commit 69.1 — `pref(69.1): score-preference.js — signal recorder and preference model`

**Files:**
- New: `backend/static/js/score-preference.js`
- Modified: `backend/static/index.html` — add `<script src="/static/js/score-preference.js"></script>` before `editor-view.js`
- Modified: `backend/static/css/app.css` — add `.v3ChipPref` rule

**`score-preference.js` structure:**

```javascript
/* score-preference.js — Phase 69: Learn clip type preference from Keep/Avoid/Download signals */
'use strict';

window.ScorePreference = (() => {
  const LS_KEY      = 'score_pref_v1';
  const MAX_SIGNALS = 30;
  const TTL_MS      = 30 * 24 * 60 * 60 * 1000; // 30 days
  const MIN_TOTAL   = 5;
  const MIN_SCORE   = 3.0;
  const MIN_RATIO   = 1.5;
  const HIGH_THRESH = 65;
  const DUR_THRESH  = 70;

  const _DIMS = ['hook', 'speech', 'retention', 'duration', 'market'];
  const _LABELS = {
    hook:      'Preference: Hook clips',
    speech:    'Preference: Speech clips',
    retention: 'Preference: Smooth pacing',
    duration:  'Preference: Duration fit',
    market:    'Preference: Market-fit clips',
  };
  const _WEIGHTS = { download: 2, keep: 1, avoid: -1 };

  function _empty() {
    return { signals: [], total: 0, dim_scores: { hook:0, speech:0, retention:0, duration:0, market:0 } };
  }

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      return raw ? Object.assign(_empty(), JSON.parse(raw)) : _empty();
    } catch (_) { return _empty(); }
  }

  function _save(d) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(d)); } catch (_) {}
  }

  function _prune(d) {
    const now = Date.now();
    d.signals = d.signals
      .filter(s => (now - (s.ts || 0)) < TTL_MS)
      .slice(-MAX_SIGNALS);
    return d;
  }

  function _isHigh(components, dim) {
    const thresh = dim === 'duration' ? DUR_THRESH : HIGH_THRESH;
    const key = dim === 'hook'      ? 'hook_score'
              : dim === 'speech'    ? 'speech_density_score'
              : dim === 'retention' ? 'retention_score'
              : dim === 'duration'  ? 'duration_fit_score'
              : dim === 'market'    ? 'market_score'
              : null;
    if (!key) return false;
    const val = Number(components[key] || 0);
    if (dim === 'market' && val === 50.0) return false; // no MV scoring — skip
    return val > thresh;
  }

  function recordSignal(action, components) {
    if (!_WEIGHTS.hasOwnProperty(action)) return;
    if (!components || typeof components !== 'object') return;
    const w = _WEIGHTS[action];
    const d = _prune(_load());
    const sig = { action, ts: Date.now() };
    _DIMS.forEach(function(dim) {
      const high = _isHigh(components, dim);
      sig[dim + '_high'] = high;
      d.dim_scores[dim] = (d.dim_scores[dim] || 0) + (high ? w : 0);
    });
    d.signals.push(sig);
    d.total = (d.total || 0) + 1;
    _save(d);
  }

  function getPreference() {
    const d = _prune(_load());
    if ((d.total || 0) < MIN_TOTAL) return null;
    const entries = _DIMS
      .map(function(dim) { return [dim, d.dim_scores[dim] || 0]; })
      .filter(function(e) { return e[1] > 0; })
      .sort(function(a, b) { return b[1] - a[1]; });
    if (!entries.length || entries[0][1] < MIN_SCORE) return null;
    if (entries.length > 1 && entries[0][1] < entries[1][1] * MIN_RATIO) return null;
    const dim = entries[0][0];
    return { confident: true, dimension: dim, label: _LABELS[dim] };
  }

  function getCount() { return { total: _load().total || 0 }; }
  function reset() { _save(_empty()); }

  return { recordSignal, getPreference, getCount, reset };
})();
```

**CSS addition in `app.css`** (after `.v3ChipAsset` rule, around line 17676):
```css
.v3ChipPref { color:#2dd4bf; border-color:rgba(45,212,191,.3); background:rgba(45,212,191,.08); }
```

**`index.html` script tag:** Add before the `editor-view.js` script tag:
```html
<script src="/static/js/score-preference.js"></script>
```

**Validation checklist:**
- [ ] `ScorePreference.recordSignal('download', {hook_score:78, speech_density_score:45, retention_score:70, duration_fit_score:82, market_score:50})` runs without error
- [ ] `ScorePreference.getPreference()` returns null when total < 5
- [ ] `ScorePreference.getPreference()` returns `{confident: true, dimension: 'hook', label: 'Preference: Hook clips'}` after 5+ download signals of hook-heavy clips
- [ ] market_score === 50.0 is correctly skipped (not counted as "market_high")
- [ ] `ScorePreference.reset()` clears all data
- [ ] localStorage `score_pref_v1` is written correctly
- [ ] No JS errors on load before any signals recorded

---

### Commit 69.2 — `pref(69.2): wire ranking signals at Keep/Avoid/Download actions`

**File:** `backend/static/js/render-ui.js`

**Changes:**

**1. Store rank map globally at render time** (one line, after the `ranking` Map is built):
```javascript
window._r69RankMap = ranking;
```
Placed at the top of the clip list render function, after `const ranking = _rankMap(job);`.

**2. Add partNo param to csKeepClip and csAvoidClip; record signal:**
```javascript
// Old:
window.csKeepClip = function(startSec, endSec, label) {
// New:
window.csKeepClip = function(startSec, endSec, label, partNo) {
  if (typeof ScorePreference !== 'undefined' && window._r69RankMap) {
    var _r69rk = window._r69RankMap.get(Number(partNo) || 0);
    if (_r69rk) ScorePreference.recordSignal('keep', _r69rk.rankingComponents || {});
  }
  // ... existing code unchanged ...
```

```javascript
// Old:
window.csAvoidClip = function(startSec, endSec, label) {
// New:
window.csAvoidClip = function(startSec, endSec, label, partNo) {
  if (typeof ScorePreference !== 'undefined' && window._r69RankMap) {
    var _r69rk = window._r69RankMap.get(Number(partNo) || 0);
    if (_r69rk) ScorePreference.recordSignal('avoid', _r69rk.rankingComponents || {});
  }
  // ... existing code unchanged ...
```

**3. Add partNo to csKeepAndRerender:**
```javascript
// Old:
window.csKeepAndRerender = function(startSec, endSec, label) {
// New:
window.csKeepAndRerender = function(startSec, endSec, label, partNo) {
  if (typeof ScorePreference !== 'undefined' && window._r69RankMap) {
    var _r69rk = window._r69RankMap.get(Number(partNo) || 0);
    if (_r69rk) ScorePreference.recordSignal('keep', _r69rk.rankingComponents || {});
  }
  // ... existing code unchanged ...
```

**4. Pass partNo in clip card template onclick attributes:**

The three steering buttons in the clip card template currently call:
```javascript
onclick="csKeepClip(${startSec},${endSec},'${esc(...)}')"
onclick="csAvoidClip(${startSec},${endSec},'${esc(...)}')"
onclick="csKeepAndRerender(${startSec},${endSec},'${esc(...)}')"
```

Each updated to add `,${partNo}` as the 4th argument (partNo is in scope in the template loop).

**5. Wire Download onclick to record signal:**

Add a helper function `_r69RecordDownload(partNo)` called from the download link's onclick:

```javascript
function _r69RecordDownload(partNo) {
  if (typeof ScorePreference === 'undefined' || !window._r69RankMap) return;
  var rk = window._r69RankMap.get(Number(partNo) || 0);
  if (rk) ScorePreference.recordSignal('download', rk.rankingComponents || {});
}
```

And in the download button template, append to existing onclick:
```javascript
`;if(typeof _r69RecordDownload==='function')_r69RecordDownload(${partNo})`
```

**Validation checklist:**
- [ ] `window._r69RankMap` is set after each render cycle
- [ ] csKeepClip called from clip card passes correct partNo
- [ ] csAvoidClip called from clip card passes correct partNo
- [ ] csKeepAndRerender called from clip card passes correct partNo
- [ ] `ScorePreference.recordSignal('keep', ...)` is called when Keep is clicked
- [ ] `ScorePreference.recordSignal('avoid', ...)` is called when Avoid is clicked
- [ ] `ScorePreference.recordSignal('download', ...)` is called when Download is clicked
- [ ] No regression: ClipSteering lock/exclude still fires as before
- [ ] No regression: CreatorTaste.recordDownload still fires as before
- [ ] No regression: csKeepAndRerender still calls ClipSteering.lockClip + v3TriggerRerender

---

### Commit 69.3 — `pref(69.3): preference chip in pre-render steering panel`

**File:** `backend/static/js/editor-view.js`

**Change:** In `v3RefreshSteeringPanel()`, after the 🧠 Learned chip block (68.2) and before the CreatorAssets block, add:

```javascript
  // 69.3: Score preference chip — shown when consistent Keep/Download pattern emerges
  if (typeof ScorePreference !== 'undefined') {
    var _r69Pref = ScorePreference.getPreference();
    if (_r69Pref && _r69Pref.confident) {
      parts.push({ label: _r69Pref.label, cls: 'v3Chip v3ChipPref', title: 'Based on your Keep and Download patterns' });
    }
  }
```

**Validation checklist:**
- [ ] Chip appears in pre-render area after ≥ 5 keep/download signals on hook-heavy clips
- [ ] Chip absent when `ScorePreference.getPreference()` returns null
- [ ] Chip absent when `total < 5`
- [ ] Chip absent when no dimension is dominant (close scores)
- [ ] Chip label matches the dominant dimension ("Preference: Hook clips" etc.)
- [ ] Chip tooltip shows "Based on your Keep and Download patterns"
- [ ] Existing DNA, Series, 🧠 chips unaffected
- [ ] No JS error when ScorePreference is undefined

---

## 10. COMMIT PLAN

| # | Commit message | Files | Change description | Est. lines |
|---|---|---|---|---|
| 1 | `pref(69.1): score-preference.js signal recorder and preference model` | `score-preference.js` (new), `index.html`, `app.css` | Signal accumulator, preference inference model, CSS chip color | ~75 |
| 2 | `pref(69.2): wire ranking signals at Keep/Avoid/Download actions` | `render-ui.js` | Store rank map globally, pass partNo to steering functions, record signals | ~20 |
| 3 | `pref(69.3): preference chip in pre-render steering panel` | `editor-view.js` | Add ScorePreference chip to v3RefreshSteeringPanel | ~8 |

**Total: 3 commits, 4 files (~3 modified + 1 new). ~103 lines. Zero backend changes. One new localStorage key.**

---

## 11. DEFINITION OF DONE

Phase 69 is complete when:

- [ ] `ScorePreference.recordSignal('download', {hook_score:78, ...})` stores correctly to `score_pref_v1`
- [ ] After 5+ download signals on hook-heavy clips, `getPreference()` returns `{confident:true, dimension:'hook', label:'Preference: Hook clips'}`
- [ ] After 5 mixed signals (no clear dominant), `getPreference()` returns null
- [ ] Clicking Keep on a clip card records a 'keep' signal with that clip's ranking components
- [ ] Clicking Avoid on a clip card records an 'avoid' signal
- [ ] Downloading a clip records a 'download' signal (strongest weight)
- [ ] Pre-render chip "Preference: Hook clips" appears after crossing the confidence threshold
- [ ] Chip absent when threshold is not met
- [ ] `ScorePreference.reset()` clears the preference
- [ ] Zero regressions: ClipSteering Keep/Avoid/Rerender still functions identically
- [ ] Zero regressions: CreatorTaste.recordDownload still fires on Download
- [ ] Zero regressions: Phase 68 DNA note, alt note, feedback summary unchanged
- [ ] Zero regressions: Phase 66/67 explain panel, confidence badge, duration hint unchanged
- [ ] No ranking change: clip ordering is 100% unchanged by this phase

### Creator experience after Phase 69

Creator renders 3 uploads. On each, they consistently Keep and Download clips that have strong speech density scores. On the 4th render:

```
Pre-render steering panel:
[Preference: Speech clips] [DNA active] [🧠 Learned]
                  ↑ NEW
```

Creator sees their pattern recognized and labeled. They understand the tool is noticing what they prefer. No clip was ranked differently. Nothing was auto-changed. The label is accurate and dismissible through preference reset.

Creator stops asking: "Does this tool have any idea what I actually like?"

---

## What Phase 69 does NOT change

| Item | Status |
|---|---|
| Clip ranking order | **Unchanged** |
| Segment selection engine | **Unchanged** |
| `render_pipeline.py` | **Unchanged** |
| ClipSteering lock/exclude behavior | **Unchanged** |
| FeedbackLearning backend | **Unchanged** |
| CreatorDNA hook bonus | **Unchanged** |
| Phase 66 explain panel | **Unchanged** |
| Phase 67 duration hint / rerender banner | **Unchanged** |
| Phase 68 DNA note / alt note / feedback summary | **Unchanged** |

## What Phase 69 defers

| Item | Why deferred |
|---|---|
| Ranking nudge from preference (e.g., +2 weight on speech clips when speech preference is confident) | Feedback loop risk; needs careful anti-spiral design; separate phase |
| Cross-render preference retention (beyond 30-signal/30-day window) | Current window is sufficient for MVP; long-term accumulation introduces creep risk |
| Preference shown in clip card result (e.g., "This matches your speech preference") | Phase 70 candidate — connect the chip to the result output |
| Per-dimension preference reset (reset only hook preference, not all) | UX complexity; full reset sufficient for V1 |
| Preference influence on `evMinPart`/`evMaxPart` based on duration_fit pattern | Duration fit and clip length are distinct; deferred to avoid confusing the two signals |

---

*Phase 69 plan based on live code audit of render-ui.js, creator-taste.js, creator-dna.js, clip-steering.js, score-preference.js (not yet created), editor-view.js, app.css.*
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*
