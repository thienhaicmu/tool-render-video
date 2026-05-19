# PHASE 70 — DURATION PREFERENCE LEARNING PLAN
## Learn Moment Length Taste From Keep / Avoid / Download Signals

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 69 Score Preference Learning — COMPLETE, zero regressions
**Plan date:** 2026-05-19
**Planning only — no implementation in this session**

---

## 1. EXECUTIVE SUMMARY

Phase 69 taught the tool to recognise what *kind* of clip the creator prefers (hook-heavy, speech-heavy, etc.) by watching which ranking dimensions appear on kept and downloaded clips. Phase 70 asks the complementary question: does the creator consistently prefer *shorter* or *longer* moments?

A creator who always ends up keeping 35–55s tight edits and a creator who always downloads 140–160s retention-style moments are using the same tool with different expectations. Today the tool has no memory of this across sessions — every render starts fresh with `evMinPart=70`, `evMaxPart=180`.

**The gap:**

Phase 67 introduced `ClipSteering.getDurationHint()`, which reads the current session's locked clips and proposes a duration range. This is genuinely useful — but `clip_steering_v1` has a 72-hour TTL. By the next session, the signal is gone. There is no cross-session accumulation of "creator consistently keeps short clips."

**Phase 70 closes this gap:**

When a creator downloads a 48s clip, record: "downloaded a tight clip." After 5+ consistent tight-clip downloads/keeps, surface a persistent hint near the `evMinPart`/`evMaxPart` controls: `"You often keep shorter clips · 45–90s [Apply] [×]"`. Clicking Apply sets the inputs and dismisses the hint.

**What Phase 70 does NOT do:**

- Auto-set `evMinPart`/`evMaxPart`
- Override creator input
- Affect clip selection or ranking
- Replace Phase 67's session-level hint (both can coexist — Phase 67 remains the current-session signal; Phase 70 is the cross-session memory)

**Implementation scope:** 3 commits. New `duration-preference.js` module, 2 wiring edits. ~85 lines total. One new localStorage key. Zero backend changes.

---

## 2. EXISTING SIGNAL AUDIT

### 2A. What duration signals already exist

| Signal | Duration available? | Persistence | Cross-session? | Notes |
|---|---|---|---|---|
| `ClipSteering.lockClip(startSec, endSec, label)` | YES — `endSec - startSec` = clip length | 72h TTL | **NO** | Source for Phase 67's hint |
| `ClipSteering.getDurationHint()` | YES — reads locked clip list | 72h | **NO** | Only fires when avg is outside 70–120s |
| `csKeepClip(startSec, endSec, label, partNo)` | YES — first two args | Not stored | **NO** | Phase 69 wired these; `startSec`/`endSec` available |
| `csAvoidClip(startSec, endSec, label, partNo)` | YES — first two args | Not stored | **NO** | Same |
| `csKeepAndRerender(startSec, endSec, label, partNo)` | YES — first two args | Not stored | **NO** | Same |
| Download button template | YES — `startSec`/`endSec` at line 4600–4601 of render-ui.js | Not stored | **NO** | Template literals can embed values |
| `ScorePreference.recordSignal()` `duration_fit_score` dim | **NO** | 30 days | YES | Platform-ideal closeness, NOT clip length — wrong signal |
| `evMinPart`/`evMaxPart` input values | Indirect | Not accumulated | NO | User's last-set value; not a history |
| `CreatorTaste.recordDownload(rank)` | NO — only records rank_1 vs rank_other | 15-session EMA | YES | No duration captured |

### 2B. Critical finding: `duration_fit_score` ≠ clip length

Phase 69 tracks `duration_fit_score` as one of its five preference dimensions. This score measures how close a clip's actual length is to the platform-ideal duration — a high score means "this clip is a good length for TikTok/Shorts" — not that the creator prefers long or short clips. Phase 70 uses raw `endSec - startSec` (actual clip length in seconds). These are distinct signals. No overlap.

### 2C. Why `rk` (rankMap entry) cannot carry duration

`_rankMap(job)` builds entries from `result_json.output_ranking`. These entries have `rank`, `score`, `isBest`, `rankingComponents`, etc. — but NOT `start_sec`/`end_sec`. Those are in the WS payload (`p.start_sec`, `p.end_sec`) not in `output_ranking`. Duration must come from:
- Function args (`startSec`, `endSec` in `csKeepClip` etc.)
- Template-time embedding in onclick attributes (for the download button)

`window._r69RankMap.get(partNo)` alone is not sufficient for duration — cannot use Phase 69's pattern directly.

### 2D. `_r67ApplyDuration(mn, mx)` — reusable in Phase 70

Phase 67 added `window._r67ApplyDuration(mn, mx)` to `editor-view.js`. This function sets `evMinPart.value = mn` and `evMaxPart.value = mx`. Phase 70 reuses this function for the [Apply] button — no new setter needed.

### 2E. Phase 67 neutral zone alignment

`ClipSteering.getDurationHint()` treats 70–120s as "neutral" (returns `null` when avg is in range). Phase 70 adopts the same bounds as bucket boundaries: `tight < 70s`, `mid 70–120s`, `long > 120s`. This ensures Phase 67 and Phase 70 never contradict each other — they read the same meaning of "short" and "long."

---

## 3. STRONG VS WEAK SIGNAL MATRIX

### Signal strength definition

| Action | Weight | Rationale |
|---|---|---|
| **Download** | **+2** | Strongest: creator exported this clip — the actual production choice |
| **Keep** (`csKeepClip`) | **+1** | Medium: marked for next render, but not yet exported |
| **Rerender** (`csKeepAndRerender`) | **+1** | Same weight as Keep — locks the clip AND rerenders |
| **Avoid** (`csAvoidClip`) | **−1** | Negative: deliberately excluded; reveals what length creator rejects |
| Clip rendered automatically | **0** | No creator action — not preference signal |

### Duration buckets

| Bucket | Range | Meaning | Suggestion when confident |
|---|---|---|---|
| `tight` | `< 70s` | Creator prefers tight, punchy edits | Set min=45, max=90 |
| `mid` | `70–120s` | Default range (matches Phase 67 neutral zone) | **Never surfaced** — it's already the default |
| `long` | `> 120s` | Creator prefers long-form retention moments | Set min=90, max=180 |

**Why `mid` is never surfaced:** The default `evMinPart=70`, `evMaxPart=180` already covers the mid bucket. Telling the creator "you prefer 70–120s clips" while the tool already suggests that range adds no value. If `mid` is the dominant bucket, show nothing — the defaults are already appropriate. However, `mid` scores are still tracked internally so the leader-ratio test correctly prevents `tight` or `long` from being falsely declared confident when `mid` is dominant.

### What the signal combination means

| Pattern | Inference |
|---|---|
| 3+ downloads of `< 70s` clips | Tight-clip preference |
| 3+ downloads of `> 120s` clips | Long-form preference |
| Mix of `tight` and `long` keeps | No clear preference (show nothing) |
| Avoids mostly `> 120s` clips | Negative long preference |
| All clips in `mid` bucket | Default preference — show nothing |
| 5+ signals, no bucket at 1.5× lead | No preference — show nothing |

---

## 4. DURATION PREFERENCE MODEL

### Storage schema — `dur_pref_v1`

New localStorage key `dur_pref_v1`:

```json
{
  "signals": [
    {
      "action": "download",
      "dur_sec": 48.2,
      "bucket": "tight",
      "ts": 1716123456000
    }
  ],
  "total": 7,
  "bucket_scores": {
    "tight": 5.0,
    "mid": 1.0,
    "long": -1.0
  }
}
```

**Signal cap:** last 30 signals (oldest pruned). **TTL:** 30 days per signal (`Date.now() - ts > 30 * 86400000`). Both caps applied on every write. Exact same pattern as `score_pref_v1` from Phase 69.

### Bucket classification

```
bucket(durationSec):
  if durationSec < 70  → 'tight'
  if durationSec > 120 → 'long'
  else                 → 'mid'
```

### Score accumulation

When a signal arrives with `action` and `durationSec`:

```
if durationSec <= 0: discard (no timing data)
weight = download→2, keep→1, avoid→−1
bucket = classify(durationSec)
bucket_scores[bucket] += weight
```

Negative scores are allowed. Old signals prune naturally via the 30-signal cap.

### Reading the preference

```
getPreference() → { confident: bool, bucket: string, label: string, applyMin: number, applyMax: number } | null

confident when:
  total >= 5
  AND (tight.score >= 3.0 OR long.score >= 3.0)
  AND top bucket score > second bucket score * 1.5
  AND top bucket is 'tight' or 'long' (mid never returned as suggestion)

bucket → suggestion:
  'tight' → { label: 'shorter clips', applyMin: 45, applyMax: 90 }
  'long'  → { label: 'longer clips', applyMin: 90, applyMax: 180 }
```

If no bucket meets the threshold, return `null`. Never fabricate.

### Public API

```javascript
const DurationPreference = (() => {
  // ...internal...
  return {
    recordSignal(action, durationSec),  // 'keep'|'avoid'|'download', seconds as number
    getPreference(),                     // → { confident, bucket, label, applyMin, applyMax } | null
    getCount(),                          // → { total }
    reset(),
  };
})();
```

---

## 5. THRESHOLD RULES

### Minimum signal requirements

| Threshold | Value | Rationale |
|---|---|---|
| Minimum total signals before any inference | **5** | Matches Phase 69; below 5 is coincidence from one render |
| Minimum net bucket score for confidence | **3.0** | ≈ 3 downloads or 6 keeps in that bucket |
| Top bucket must lead second by | **≥ 1.5×** | Prevents false confidence when creator uses both bucket types |
| `mid` bucket | **tracked but never surfaced** | Prevents false "you prefer defaults" message |

### Anti-overfitting rules

| Rule | Implementation |
|---|---|
| Rolling 30-signal window | Old signals expire by count; 30-day TTL |
| Signals with `durationSec <= 0` | Discarded immediately — no timing data |
| Rerender without explicit Keep | `csKeepAndRerender` records a keep signal because it locks the clip; bare rerender (no clip lock) does not fire here |
| Hard reset | `DurationPreference.reset()` clears all signals |

### Interaction with Phase 67's session hint

Phase 67's `getDurationHint()` reads the current session's locked clips (72h TTL). Phase 70 reads 30-day accumulated signals. When both fire simultaneously:

- Phase 67's hint `r67DurationHint` appears first (nearest to session context)
- Phase 70's hint `r70DurationHint` appears below it
- Both can coexist — they are independent hints with different sources
- If Phase 67's hint is visible, Phase 70's hint is still shown (they don't contradict each other because both use the same 70s/120s bucket boundaries)

---

## 6. SAFE USAGE MODEL

### Phase 70 influence level: suggestion only

Phase 70 surfaces a dismissible hint with an explicit [Apply] button. It does NOT auto-apply. Creator remains in full control.

```
You often keep shorter clips · 45–90s  [Apply]  [×]
```

[Apply] calls `window._r67ApplyDuration(45, 90)` — the exact same function Phase 67 uses. No new setter code.

[×] calls `_r70DismissDuration()` — hides the hint for the current session (does not delete the learned preference).

### Hint visibility lifecycle

| State | Hint |
|---|---|
| `total < 5` | Hidden |
| Confident `tight` preference | Shows "You often keep shorter clips · 45–90s [Apply] [×]" |
| Confident `long` preference | Shows "You often keep longer clips · 90–180s [Apply] [×]" |
| `mid` dominant OR no clear leader | Hidden |
| Creator clicked [Apply] or [×] | Hidden for session (preference still accumulates) |
| Creator manually changed evMinPart/evMaxPart | Hint stays visible — manual choice does not suppress the hint (creator set their own value; hint still available) |

### What Phase 70 does NOT change

| Item | Status |
|---|---|
| `evMinPart` / `evMaxPart` auto-set | **Never** — creator action only |
| Clip selection engine | **Unchanged** |
| `render_pipeline.py` | **Unchanged** |
| ClipSteering lock/exclude | **Unchanged** |
| Phase 67 session duration hint | **Unchanged** — runs independently |
| Phase 69 ScorePreference chip | **Unchanged** |

---

## 7. TRUST AND UX RULES

### Hard limits

| Rule | Rationale |
|---|---|
| Never auto-set `evMinPart`/`evMaxPart` | Creator's render settings are theirs — no silent changes |
| Never show `mid` as a preference suggestion | "You prefer the default range" is circular and useless |
| Never show below 5 signals | Fewer than 5 downloads/keeps is not a pattern — could be one upload's quirk |
| Never say "AI detected your preference" | It's a counter; not AI |
| Never show raw duration scores | "tight: 5.0 points" is noise |
| Never show which clips contributed | "Based on 3 recent downloads" is sufficient |
| Always provide [×] to dismiss | Creator can ignore the hint without resetting their history |
| `DurationPreference.reset()` is accessible | Wired to the existing preference reset flow |

### Trust language rules

| Creator reads | Trust level | Use? |
|---|---|---|
| `"You often keep shorter clips"` | HIGH — descriptive, factual | **YES** |
| `"You prefer short clips"` | MEDIUM — implies certainty | **AVOID** |
| `"AI thinks you like tight edits"` | LOW — surveillance-like | **NO** |
| `"Duration preference learned: tight"` | LOW — jargon | **NO** |
| `"Set 45–90s"` (as Apply label) | HIGH — transparent about what changes | **YES** |

### Chip label copy (for hint element, not chip)

| Bucket | Hint text | Apply text |
|---|---|---|
| `tight` | `You often keep shorter clips · 45–90s` | `[Apply]` → sets min=45, max=90 |
| `long` | `You often keep longer clips · 90–180s` | `[Apply]` → sets min=90, max=180 |
| `mid` | *(never shown)* | — |

---

## 8. UI RECOMMENDATION

### Placement

The hint appears as a small div injected adjacent to the `evMaxPart` input — the same injection point as Phase 67's `r67DurationHint`.

**After Phase 70, below `evMaxPart` label:**
```
Max clip (s): [180 ▾]
──────────────────────────────────────────
Duration: ~45s avg — suggest 45–90s [Apply][×]   ← Phase 67 (session hint)
You often keep shorter clips · 45–90s [Apply][×]  ← Phase 70 (cross-session hint)
──────────────────────────────────────────
```

Both hints can appear simultaneously. When neither applies, neither appears. The two hints are visually identical in style (same `r67DurationHint` CSS applied to both).

### New element: `r70DurationHint`

- Injected into DOM by `_r70_ensureDurationHintEl()` in `editor-view.js`
- Same CSS class and injection logic as Phase 67's `r67DurationHint`
- Inserted immediately after `r67DurationHint` element
- Visibility controlled by `_r70SyncDurationHint()`
- Called from `v3RefreshSteeringPanel()` after the existing `_r67SyncDurationHint()` call

### What it does NOT do

- Does not expand to a panel
- Does not show clip history
- Does not offer "disable this preference" — full reset via existing preference reset
- Clicking [Apply] does not close any panel — just sets the two input values and hides the hint for the session

---

## 9. SAFE ROLLOUT PLAN

### Pre-implementation verification

**Before 70.1:**
- Confirm `dur_pref_v1` not used anywhere in the codebase — **VERIFIED** (grep found no matches)
- Confirm `DurationPreference` not already declared as a global

**Before 70.2:**
- Confirm `csKeepClip`, `csAvoidClip`, `csKeepAndRerender` signatures in `render-ui.js` after Phase 69: `(startSec, endSec, label, partNo)` — **VERIFIED** (Phase 69 added `partNo`; `startSec`/`endSec` were always there)
- Confirm `startSec` and `endSec` are defined at download button template build time — **VERIFIED** (lines 4600–4601 in `render-ui.js` `.map()` callback, before line 4627 where `downloadBtn` is built)
- Confirm `endSec > startSec` is guaranteed before Keep/Avoid/Rerender buttons render — **VERIFIED** (`isDone && endSec > startSec` is the guard at the steer row template condition at line 4669)

**Before 70.3:**
- Confirm `window._r67ApplyDuration` is accessible from the hint button — **VERIFIED** (declared globally in `editor-view.js` line 289)
- Confirm `_r67_ensureDurationHintEl()` injection point (next to `evMaxPart`) works as a model for Phase 70's element

### Stop conditions

Stop if:
- `startSec`/`endSec` are zero for all clip parts in test renders (would mean no timing data, no signals possible — but this has never been observed; all rendered clips have real timing)
- `_r67ApplyDuration` is not accessible at hint click time (would mean script load order issue — easily fixed by moving the Phase 70 hint injection to `editor-view.js` where `_r67ApplyDuration` is defined)

---

## Commit 70.1 — `dur(70.1): duration-preference.js signal recorder and preference model`

**Files:**
- New: `backend/static/js/duration-preference.js`
- Modified: `backend/static/index.html` — add `<script src="/static/js/duration-preference.js"></script>` after `score-preference.js`
- Modified: `backend/static/css/app.css` — add `.r70DurationHint` rule (identical to `.r67DurationHint` inline style; or reuse existing hint CSS)

**`duration-preference.js` structure:**

```javascript
/* duration-preference.js — Phase 70: Learn clip length preference from Keep/Avoid/Download */
'use strict';

window.DurationPreference = (() => {
  const LS_KEY      = 'dur_pref_v1';
  const MAX_SIGNALS = 30;
  const TTL_MS      = 30 * 24 * 60 * 60 * 1000; // 30 days
  const MIN_TOTAL   = 5;
  const MIN_SCORE   = 3.0;
  const MIN_RATIO   = 1.5;
  const TIGHT_MAX   = 70;   // < 70s = tight
  const LONG_MIN    = 120;  // > 120s = long (aligns with Phase 67 neutral zone)

  const _WEIGHTS = { download: 2, keep: 1, avoid: -1 };

  const _SUGGEST = {
    tight: { label: 'shorter clips', applyMin: 45, applyMax: 90  },
    long:  { label: 'longer clips',  applyMin: 90, applyMax: 180 },
  };

  function _empty() {
    return { signals: [], total: 0, bucket_scores: { tight: 0, mid: 0, long: 0 } };
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
      .filter(function(s) { return (now - (s.ts || 0)) < TTL_MS; })
      .slice(-MAX_SIGNALS);
    return d;
  }

  function _bucket(dur) {
    if (dur < TIGHT_MAX)  return 'tight';
    if (dur > LONG_MIN)   return 'long';
    return 'mid';
  }

  function recordSignal(action, durationSec) {
    if (!Object.prototype.hasOwnProperty.call(_WEIGHTS, action)) return;
    const dur = Number(durationSec) || 0;
    if (dur <= 0) return; // no timing data — discard
    const w = _WEIGHTS[action];
    const d = _prune(_load());
    const b = _bucket(dur);
    const sig = { action: action, dur_sec: dur, bucket: b, ts: Date.now() };
    d.bucket_scores[b] = (d.bucket_scores[b] || 0) + w;
    d.signals.push(sig);
    d.total = (d.total || 0) + 1;
    _save(d);
  }

  function getPreference() {
    const d = _prune(_load());
    if ((d.total || 0) < MIN_TOTAL) return null;
    // Only tight and long can be surfaced — mid is default range
    const candidates = ['tight', 'long']
      .map(function(b) { return [b, d.bucket_scores[b] || 0]; })
      .filter(function(e) { return e[1] >= MIN_SCORE; })
      .sort(function(a, b) { return b[1] - a[1]; });
    if (!candidates.length) return null;
    const top = candidates[0];
    // Check leader ratio against ALL other buckets (including mid)
    const allScores = Object.values(d.bucket_scores).filter(function(v) { return v > 0; });
    const second = allScores.filter(function(v) { return v < top[1]; });
    const secondMax = second.length ? Math.max.apply(null, second) : 0;
    if (secondMax > 0 && top[1] < secondMax * MIN_RATIO) return null;
    const s = _SUGGEST[top[0]];
    return { confident: true, bucket: top[0], label: s.label, applyMin: s.applyMin, applyMax: s.applyMax };
  }

  function getCount() { return { total: _load().total || 0 }; }
  function reset() { _save(_empty()); }

  return { recordSignal: recordSignal, getPreference: getPreference, getCount: getCount, reset: reset };
})();
```

**CSS** (no new rule needed): The `r70DurationHint` element uses the same inline `style.cssText` pattern as `r67DurationHint` — a single-element inline style. No new CSS class required.

**`index.html` script tag:** Add after `score-preference.js`:
```html
<script src="/static/js/score-preference.js"></script>
<script src="/static/js/duration-preference.js"></script>
<script src="/static/js/editor-view.js"></script>
```

**Validation checklist 70.1:**
- [ ] `DurationPreference.recordSignal('download', 48)` stores to `dur_pref_v1` with `bucket: 'tight'`
- [ ] `DurationPreference.recordSignal('download', 85)` stores with `bucket: 'mid'`
- [ ] `DurationPreference.recordSignal('download', 145)` stores with `bucket: 'long'`
- [ ] `DurationPreference.recordSignal('download', 0)` is discarded (durationSec <= 0)
- [ ] `getPreference()` returns null when total < 5
- [ ] `getPreference()` returns `{confident:true, bucket:'tight', label:'shorter clips', applyMin:45, applyMax:90}` after 5+ download signals of tight clips
- [ ] `getPreference()` returns null when tight and long are both scoring (mixed pattern)
- [ ] `getPreference()` returns null when mid is dominant (mid score blocks tight from 1.5× ratio)
- [ ] `DurationPreference.reset()` clears all data
- [ ] No JS errors on load before any signals recorded

---

## Commit 70.2 — `dur(70.2): wire duration signals at Keep/Avoid/Download actions`

**File:** `backend/static/js/render-ui.js`

**Changes:**

**1. Keep signal** — add to `csKeepClip` immediately before the `ScorePreference` block:
```javascript
window.csKeepClip = function(startSec, endSec, label, partNo) {
  if (typeof DurationPreference !== 'undefined') {
    DurationPreference.recordSignal('keep', endSec - startSec);
  }
  if (typeof ScorePreference !== 'undefined' && window._r69RankMap) {
    // ... existing 69.2 code ...
  }
  // ... existing ClipSteering code ...
};
```

**2. Avoid signal** — add to `csAvoidClip` in same position:
```javascript
window.csAvoidClip = function(startSec, endSec, label, partNo) {
  if (typeof DurationPreference !== 'undefined') {
    DurationPreference.recordSignal('avoid', endSec - startSec);
  }
  // ... existing code ...
};
```

**3. Rerender signal** — add to `csKeepAndRerender` in same position:
```javascript
window.csKeepAndRerender = function(startSec, endSec, label, partNo) {
  if (typeof DurationPreference !== 'undefined') {
    DurationPreference.recordSignal('keep', endSec - startSec);
  }
  // ... existing code ...
};
```

**4. Download duration helper** — add alongside `_r69RecordDownload`:
```javascript
function _r70RecordDurationDownload(startSec, endSec) {
  if (typeof DurationPreference === 'undefined') return;
  DurationPreference.recordSignal('download', endSec - startSec);
}
```

**5. Download button template** — append to existing onclick (startSec, endSec are in scope at template build time):
```javascript
`... ;if(typeof _r70RecordDurationDownload==='function')_r70RecordDurationDownload(${startSec},${endSec})">Download</a>`
```

Note: This does NOT modify `_r69RecordDownload` — Phase 70 adds a separate helper. Each responsibility stays in its own function.

**Why `startSec`/`endSec` are reliable at download template build time:**
They are defined at line 4600–4601 as `const startSec = Number(p.start_sec || 0)` / `const endSec = Number(p.end_sec || 0)` in the `.map()` callback, before the `downloadBtn` template string at line 4627. All successfully rendered clips have real timing — `p.start_sec` and `p.end_sec` are set by the render engine.

**Why `endSec > startSec` for Keep/Avoid/Rerender:**
The steer row template condition is `isDone && endSec > startSec` — these buttons are only rendered when this is true. So `endSec - startSec > 0` is guaranteed when the onclick fires. The `DurationPreference.recordSignal` guard `if (dur <= 0) return` is an additional safety net.

**Validation checklist 70.2:**
- [ ] `window._r69RankMap` is set after each render (unchanged from 69.2)
- [ ] Clicking Keep records a `dur_pref_v1` signal with `action: 'keep'`
- [ ] Clicking Avoid records with `action: 'avoid'`
- [ ] Clicking Rerender records with `action: 'keep'`
- [ ] Clicking Download records with `action: 'download'`
- [ ] All signals contain correct `dur_sec` (computed from `endSec - startSec`)
- [ ] No regression: `ClipSteering.lockClip` still fires as before
- [ ] No regression: `ScorePreference.recordSignal` still fires as before
- [ ] No regression: `CreatorTaste.recordDownload` still fires as before
- [ ] `DurationPreference` undefined → no-op (no console error)

---

## Commit 70.3 — `dur(70.3): cross-session duration hint near clip length controls`

**File:** `backend/static/js/editor-view.js`

**Changes:**

**1. `_r70_ensureDurationHintEl()`** — inject a `r70DurationHint` div immediately after `r67DurationHint`:
```javascript
function _r70_ensureDurationHintEl() {
  var el = document.getElementById('r70DurationHint');
  if (el) return el;
  el = document.createElement('div');
  el.id = 'r70DurationHint';
  el.style.cssText = 'grid-column:1/-1;display:none;background:var(--bg2,#2a2a2a);border:1px solid var(--border,#333);border-radius:6px;padding:8px 10px;font-size:12px;color:var(--fg2,#aaa);margin-top:2px';
  var hint67 = document.getElementById('r67DurationHint');
  if (hint67 && hint67.parentNode) {
    hint67.parentNode.insertBefore(el, hint67.nextSibling);
    return el;
  }
  // Fallback: inject after evMaxPart label (same as Phase 67)
  var maxEl = document.getElementById('evMaxPart');
  if (maxEl) {
    var maxLabel = maxEl.closest('label');
    if (maxLabel && maxLabel.parentNode) {
      maxLabel.parentNode.insertBefore(el, maxLabel.nextSibling);
    }
  }
  return el;
}
```

**2. `_r70SyncDurationHint()`** — reads `DurationPreference.getPreference()`, shows/hides hint:
```javascript
function _r70SyncDurationHint() {
  if (typeof DurationPreference === 'undefined') return;
  var pref = DurationPreference.getPreference();
  var el = _r70_ensureDurationHintEl();
  if (!el) return;
  if (!pref) { el.style.display = 'none'; return; }
  el.style.display = '';
  el.innerHTML = '<span style="color:var(--fg1,#e0e0e0)">You often keep ' + pref.label + '</span>'
    + ' — <strong>' + pref.applyMin + '–' + pref.applyMax + 's</strong>'
    + ' <button onclick="window._r67ApplyDuration(' + pref.applyMin + ',' + pref.applyMax + ');window._r70DismissDuration()" style="margin-left:8px;padding:2px 8px;background:var(--primary,#6c5ce7);color:#fff;border:none;border-radius:4px;font-size:11px;cursor:pointer">Apply</button>'
    + ' <button onclick="window._r70DismissDuration()" style="margin-left:4px;padding:2px 6px;background:transparent;color:var(--fg2,#aaa);border:1px solid var(--border,#333);border-radius:4px;font-size:11px;cursor:pointer">×</button>';
}
```

**3. `window._r70DismissDuration`** — session-only dismiss (does not reset the preference):
```javascript
window._r70DismissDuration = function() {
  var el = document.getElementById('r70DurationHint');
  if (el) el.style.display = 'none';
};
```

**4. Call from `v3RefreshSteeringPanel()`** — immediately after the existing `_r67SyncDurationHint()` call at line 240:
```javascript
  _r67SyncDurationHint();
  _r70SyncDurationHint(); // Phase 70: cross-session duration hint
}
```

**Validation checklist 70.3:**
- [ ] `r70DurationHint` div appears below `r67DurationHint` in the DOM
- [ ] Hint shows "You often keep shorter clips · 45–90s [Apply] [×]" after 5+ tight downloads
- [ ] Hint shows "You often keep longer clips · 90–180s [Apply] [×]" after 5+ long downloads
- [ ] Hint hidden when `getPreference()` returns null
- [ ] Hint hidden when `DurationPreference` undefined (safe guard)
- [ ] [Apply] button calls `_r67ApplyDuration(45, 90)` and sets the inputs
- [ ] [×] button hides the hint for the session (preference still accumulates)
- [ ] Phase 67 hint (`r67DurationHint`) unaffected
- [ ] Phase 69 ScorePreference chip unaffected
- [ ] All other chips in `v3RefreshSteeringPanel()` unaffected

---

## 10. COMMIT PLAN

| # | Commit message | Files | Change description | Est. lines |
|---|---|---|---|---|
| 1 | `dur(70.1): duration-preference.js signal recorder and preference model` | `duration-preference.js` (new), `index.html` | Signal accumulator by duration bucket, preference inference model | ~75 |
| 2 | `dur(70.2): wire duration signals at Keep/Avoid/Download actions` | `render-ui.js` | Add `DurationPreference.recordSignal` calls to steering functions + download helper | ~15 |
| 3 | `dur(70.3): cross-session duration hint near clip length controls` | `editor-view.js` | Inject `r70DurationHint`, `_r70SyncDurationHint()`, `_r70DismissDuration()` | ~30 |

**Total: 3 commits, 3 files (~2 modified + 1 new). ~120 lines. Zero backend changes. One new localStorage key.**

---

## 11. DEFINITION OF DONE

Phase 70 is complete when:

- [ ] `DurationPreference.recordSignal('download', 48)` stores to `dur_pref_v1` with `bucket: 'tight'`
- [ ] After 5+ download signals of tight clips (< 70s), `getPreference()` returns `{confident:true, bucket:'tight', label:'shorter clips', applyMin:45, applyMax:90}`
- [ ] After 5+ mixed signals (tight + long, no clear 1.5× leader), `getPreference()` returns null
- [ ] After 5+ mid-bucket signals (70–120s), `getPreference()` returns null (mid never surfaced)
- [ ] Clicking Keep on a clip card records `dur_pref_v1` keep signal with correct `dur_sec`
- [ ] Clicking Avoid records an avoid signal
- [ ] Downloading a clip records a download signal (weight 2)
- [ ] `r70DurationHint` appears near `evMinPart`/`evMaxPart` when preference is confident
- [ ] Hint text: "You often keep shorter clips · 45–90s [Apply] [×]" (tight) or "longer clips · 90–180s [Apply] [×]" (long)
- [ ] [Apply] sets `evMinPart` and `evMaxPart` using existing `_r67ApplyDuration`
- [ ] [×] dismisses hint for session without clearing the preference
- [ ] `DurationPreference.reset()` clears all signals
- [ ] Zero regressions: `ClipSteering.lockClip` / `excludeClip` unchanged
- [ ] Zero regressions: `ScorePreference.recordSignal` unchanged
- [ ] Zero regressions: `CreatorTaste.recordDownload` unchanged
- [ ] Zero regressions: Phase 67 `r67DurationHint` unchanged
- [ ] Zero regressions: Phase 68 DNA note / alt note / feedback summary unchanged
- [ ] Zero regressions: Phase 69 ScorePreference chip unchanged
- [ ] No ranking change: clip ordering 100% unchanged by this phase

### Creator experience after Phase 70

Creator renders 4 uploads. On each, they consistently download the 45–65s tight clips and avoid the 130–160s clips. On the 5th render:

```
Pre-render settings (clip length controls):
Max clip (s): [180]
────────────────────────────────────────────────
You often keep shorter clips · 45–90s  [Apply]  [×]
────────────────────────────────────────────────
```

Creator clicks [Apply]. `evMinPart` becomes 45, `evMaxPart` becomes 90. The hint disappears. The render runs with their preferred duration range automatically applied — because they asked for it.

Creator stops asking: "Why does it keep suggesting clips that are way longer than I ever use?"

---

## What Phase 70 does NOT change

| Item | Status |
|---|---|
| Clip ranking order | **Unchanged** |
| Segment selection engine | **Unchanged** |
| `render_pipeline.py` | **Unchanged** |
| ClipSteering lock/exclude behavior | **Unchanged** |
| Phase 67 session duration hint | **Unchanged** — both hints can coexist |
| Phase 68 DNA note / alt note / feedback summary | **Unchanged** |
| Phase 69 ScorePreference chip and `score_pref_v1` | **Unchanged** |

## What Phase 70 defers

| Item | Why deferred |
|---|---|
| Auto-applying duration on render start (no [Apply] needed) | Trust: creator must confirm before their settings change |
| Per-session "remember last manual value" for evMinPart/evMaxPart | Separate concern; can be in Phase 71 if needed |
| Duration preference shown as a chip in v3SteeringPanel | Hint div is more contextual (adjacent to the controls it affects); a chip adds visual weight with no apply action |
| Platform-specific duration learning (TikTok tight vs YouTube long) | Phase 69 proved single-bucket inference is complex enough; cross-platform would need per-platform storage |
| Duration range preference (learning preferred min AND max separately) | Current model captures bucket preference cleanly; range decomposition adds noise at low signal counts |

---

*Phase 70 plan based on live code audit of render-ui.js, clip-steering.js, creator-taste.js, editor-view.js, score-preference.js, index.html.*
*ClipSteering `clip_steering_v1` TTL: 72h · getDurationHint neutral zone: 70–120s · evMinPart default: 70 · evMaxPart default: 180*
*`_r67ApplyDuration(mn, mx)` reused from Phase 67 — no new setter needed.*
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*
