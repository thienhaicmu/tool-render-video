# PHASE 66 — AI RERANKER PLAN
## Clip Explainability: Surface Why the AI Picked Each Clip

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 65 AI Technical Ownership — COMPLETE, zero regressions
**Plan date:** 2026-05-19
**Planning only — no implementation in this session**

---

## 1. EXECUTIVE SUMMARY

Phase 66 removes the black-box feeling from clip selection without changing a single line of the render engine.

The ranking data already exists. The backend computes per-clip signal scores — hook quality, speech density, retention, duration fit, market match — and stores them in a `ranking_components` dict inside every `output_ranking` entry of the render result. This data reaches the frontend in every completed render. The frontend does not read it. Phase 66 reads it and shows it.

**The question creators are currently asking:** "Why did the AI pick this clip over that one?"

**The answer the engine already computes:** `{segment_viral_score: 82, hook_score: 74, retention_score: 79, speech_density_score: 61, duration_fit_score: 88, market_score: 55}`

**What Phase 66 does:** translate that dict into human language and put it where creators can see it.

**What Phase 66 does NOT do:** change rankings, add AI, call LLMs, invent signals, guess reasons.

**Implementation scope:** 2 frontend-only commits. Zero backend changes. ~50 lines of new JS in `render-ui.js`. No new dependencies.

---

## 2. EXISTING SCORING SIGNALS AUDIT

### 2A. Complete signal inventory — what the backend computes

All signals below are computed server-side. All are deterministic. None require external API calls or ML model inference beyond what already runs.

#### Layer 1: Segment-level signals (from `segment_builder.py` and `viral_scorer.py`)

These are computed for each candidate clip window before ranking:

| Signal | Field name | Range | What it measures | Source |
|---|---|---|---|---|
| Hook opening score | `hook_opening_score` | 0–100 | Quality of the clip's opening: first-scene visual quality + first-scene transition score | `segment_builder.py:_make_selection_reason()` |
| Scene quality avg | `scene_quality_avg` | 0–100 | Mean visual quality across all scenes in the segment | `segment_builder.py` |
| Momentum score | `momentum_score` | 0–100 | Scene cuts per second × 8.0, clamped — rewards energetic editing | `segment_builder.py` |
| Retention score | `retention_score` | 0–100 | Pacing stability (0.6) + continuity (0.4) — penalizes silence gaps and jarring cuts | `segment_builder.py` |
| Continuity score | `continuity_score` | 0–100 | 100 − gap_penalty (gaps >300ms between scenes) | `segment_builder.py` |
| Duration fit score | `duration_fit_score` | 0–100 | Gaussian distance from ideal duration per platform | `segment_builder.py` |
| Speech density score | `speech_density_score` | 0–100 | SRT coverage ratio when subtitle data is available; scene-count proxy otherwise | `segment_builder.py` / `silence_analyzer.py` |
| Hook text score | `hook_text_score` / `hook_timing_score` | 0–100 | Rule-based opening hook quality: strong verbs, benefit words, question marks, hook signals, length fit | `hook_analyzer.py` |
| Content type hint | `content_type_hint` | string | "interview", "commentary", "vlog", "montage", "tutorial" — inferred from scene density | `viral_scorer.py` |
| Viral score (composite) | `viral_score` | 0–100 | Weighted sum of above signals — primary sort key for candidate selection | `segment_builder.py` / `viral_scorer.py` |
| Selection reason | `selection_reason` | string | Human/machine tag explaining the top signals for this specific clip | `segment_builder.py` + `viral_scorer.py` |

#### Layer 2: Ranking components (from `render_pipeline.py:_compute_output_ranking_entry()`)

After candidate clips are selected and rendered, a second ranking pass assembles a `ranking_components` dict per output clip. These are the signals that determine the **final output rank**:

| Component | Field name | Weight in final rank | Range | What it measures |
|---|---|---|---|---|
| Segment viral score | `segment_viral_score` | **35%** | 0–100 | Primary clip score from Layer 1 |
| Hook score | `hook_score` | **20%** | 0–100 | Opening hook quality (from hook_text_score, hook_timing_score, or hook_opening_score — best available) |
| Retention score | `retention_score` | **20%** | 0–100 | Pacing stability and continuity |
| Speech density | `speech_density_score` | **10%** | 0–100 | Spoken content density |
| Market score | `market_score` | **10%** | 0–100 | Market viral score if MV scoring enabled; 50 (neutral) otherwise |
| Duration fit | `duration_fit_score` | **5%** | 0–100 | How close the clip duration is to the platform ideal |
| Continuity | `continuity_score` | *(detail only)* | 0–100 | Silence gap penalty — informs dominant_signal |
| Content type | `content_type_hint` | *(label only)* | string | Used to make reason text content-aware |

These components are stored in `ranking_components` and already included in every `output_ranking` entry returned by the backend.

#### Layer 3: Derived ranking fields (from `render_pipeline.py`)

These are computed from the ranking components and are already parsed by the frontend (but not fully surfaced):

| Field | Currently used? | What it contains |
|---|---|---|
| `ranking_reason` | ✓ Shown (80-char truncated, 1 line) | Up to 2 human-readable reasons: "Strong opening hook, Good retention" |
| `dominant_signal` | ✗ Parsed, not displayed | Field name of top weighted signal e.g. `"segment_viral_score"` |
| `suppressed_signals` | ✗ Not parsed | Signals with high raw score but low weight contribution |
| `selection_reason` | ✓ Only checked for "limited source variety" | Machine tags ("strong_hook+stable_pacing") or human text ("Strong opening hook, Fast-paced editing") |
| `confidence_tier` | ✓ Parsed, not visually displayed | "strong" / "worth_testing" / "experimental" — only set on #1 clip |
| `ranking_components` | ✗ **NOT PARSED** | Full signal dict — the primary Phase 66 opportunity |

#### Layer 4: AI Director explainability module (from `backend/app/ai/explainability/`)

An existing, fully implemented explainability module:

| Module | API | Output |
|---|---|---|
| `reason_builder.py` | `build_clip_reasons(segments, memory_ctx)` | Up to 5 human-readable clip selection reasons |
| `confidence.py` | `calculate_ai_confidence(edit_plan)` | Confidence scores (0–100) per dimension: clip_selection, semantic, memory, pacing, camera, subtitle |
| `summary.py` | `build_ai_summary(edit_plan, confidence)` | Headline + summary_lines + strengths + warnings dict |

These are used by the AI Director pipeline when the director is active. Their output flows into `result_json.ai_ux`. The `ai_ux.best_export.why` list powers the existing "Why this output?" section on the best clip card (currently gated behind `ai_ux.available === true`).

---

## 3. SAFE SIGNALS TO EXPOSE

Not every computed signal is safe to show creators. Safety criteria:

1. **Deterministic** — same input always produces same explanation
2. **Real** — derived from actual clip measurement, not proxy or estimate
3. **Interpretable** — a non-technical creator can understand the plain-language label
4. **Bounded** — no invented context, no hallucinated reasons
5. **Present** — only shown when the value is actually in the data

### Safe to expose — PRIMARY tier (always show when available)

| Signal | Field | Human label | Why safe |
|---|---|---|---|
| Hook quality | `ranking_components.hook_score` | "Opening hook" | Clear meaning, reliable score, primary ranking signal |
| Pacing quality | `ranking_components.retention_score` | "Pacing quality" | Composite of stability + continuity — measurable, interpretable |
| Speech density | `ranking_components.speech_density_score` | "Speech density" | Real SRT coverage ratio; proxy when no subtitle data |
| Duration fit | `ranking_components.duration_fit_score` | "Duration fit" | Gaussian distance from platform ideal — fully deterministic |
| Overall clip score | `ranking_components.segment_viral_score` | "Overall score" | Primary ranking score — safe to expose as the summary number |
| Confidence tier | `confidence_tier` | "High confidence" / "Close call" / "Experimental" | Already computed; only shown on #1 clip where it's set |

### Safe to expose — SECONDARY tier (show when score is meaningful, i.e., ≠ neutral 50)

| Signal | Field | Human label | Gate condition |
|---|---|---|---|
| Market match | `ranking_components.market_score` | "Market fit" | Only show when `market_score != 50` (50 = no MV scoring active) |
| Content type | `ranking_components.content_type_hint` | "Interview", "Tutorial", etc. | Only show when the value is a non-empty, non-default string |
| Selection reason | `selection_reason` | Translated (see Section 4B) | Only show when value is non-empty and non-generic |
| Dominant signal | `dominant_signal` | Used to bold the top-scoring label | Only for UI emphasis, not a standalone field |

### NOT safe to expose

| Signal | Why not |
|---|---|
| `suppressed_signals` list | Creator-confusing — signals that scored high but were weighted out are not intuitive |
| `continuity_score` (raw) | Too granular; already folded into `retention_score` |
| Internal feature vector (`_features`) | Raw ML feature dict — meaningless to creators |
| `scoring_mode` | Internal routing flag |
| AI confidence sub-dimensions (semantic, memory, pacing, camera, subtitle) | Too granular and system-facing |
| Any signal with value = 50 when 50 is the neutral/fallback default | Fabricated confidence — 50 means "no data", not "average" |

---

## 4. EXPLANATION MODEL

### 4A. Per-clip explanation panel

Each rendered clip card gets an explanation panel built from `ranking_components`. The panel is generated entirely in the frontend from data already in the render result. No backend call required.

**Structure:**

```
Clip #2
Score: 7.4/10  #2

Why selected:
  ✓ Strong opening hook   [Hook 74%]
  ✓ High pacing quality   [Pacing 79%]
  ✓ Dense speech          [Speech 61%]
  Duration: 72s — ideal for TikTok

Confidence: High
```

**Rules for which signals to show:**
- Always show top 2 signals by contribution (weighted contribution = score × weight)
- Show a 3rd signal only if it scores ≥ 65 (meaningfully above neutral)
- Never show a signal if its value is the default 50.0 (no data present)
- Never show more than 3 signals
- Never show confidence unless it's `confidence_tier` on the #1 clip
- For non-best clips: show top 2 signals only, no confidence

**Human labels translation table:**

| Field key | Human label | Score interpretation |
|---|---|---|
| `segment_viral_score` | "Overall score" | ≥75 "Strong" / ≥55 "Good" / <40 "Weak" |
| `hook_score` | "Opening hook" | ≥70 "Strong" / ≥50 "Moderate" / <40 "Weak" |
| `retention_score` | "Pacing quality" | ≥70 "High" / ≥50 "Steady" / <40 "Unstable" |
| `speech_density_score` | "Speech density" | ≥70 "Dense" / ≥45 "Good" / <25 "Low" |
| `duration_fit_score` | "Duration fit" | ≥80 "Ideal" / ≥60 "Good" / <40 "Off-target" |
| `market_score` | "Market fit" | ≥70 "Strong" / ≥50 "Good" / <40 "Weak" |

**Score bar representation (visual):**
No bar charts. Tags only. Format: `"Strong opening hook"` with the numeric in parentheses `(74%)` for creators who want the number. Numeric in parentheses is optional — show when score ≥ 60 or ≤ 40 (when signal is decisive or flagged).

### 4B. Selection reason translation

`selection_reason` comes in three formats depending on which code path ran:

**Format 1 — machine tags (from `segment_builder.py`):**
```
"strong_hook+stable_pacing"
"speech_rich+ideal_length"
"high_quality+top_viral"
"best_available"
```

Translation dictionary:
```
strong_hook      → "Strong opening hook"
stable_pacing    → "Stable pacing"
speech_rich      → "Dense speech content"
ideal_length     → "Ideal clip duration"
high_quality     → "High visual quality"
top_viral        → "Top ranked clip"
best_available   → not shown (generic fallback)
```

**Format 2 — already human-readable (from `viral_scorer.py`):**
```
"Strong opening hook, Fast-paced editing"
"High-quality spoken content, Ideal duration"
"Steady instructional pacing"
```
These are safe to show directly. No translation needed.

**Format 3 — variant labels (from `render_pipeline.py`):**
```
"Aggressive: hook-forward selection"
"Balanced: overall best-quality selection"
"Story-first: payoff-forward selection"
```
These are safe to show directly. Already creator-readable.

**Detection logic:** if `selection_reason` contains `+` → machine tags format → apply translation dict. Otherwise → show directly.

### 4C. Confidence display

`confidence_tier` is set only on the #1 ranked clip. Three values:

| Value | Display label | Color hint | Meaning |
|---|---|---|---|
| `"strong"` | "High confidence" | Green | Score gap to #2 clip is substantial (clear winner) |
| `"worth_testing"` | "Worth testing" | Yellow | Score gap is close — both clips are viable |
| `"experimental"` | "Experimental" | Dim | Ranking is uncertain; limited signal data |

For non-best clips: derive a soft confidence from the score gap to the best clip. If `gap > 2.0/10` → no label (the best clip is the confident choice). If `gap < 1.0/10` → "Close to best". This is a display-level heuristic, not a new signal.

### 4D. What the panel looks like for a weak clip

Low-scoring clips (score < 5.0/10) do not get the explanation panel. They already have the `clipCardReason` short line if signals exist. The explanation panel is reserved for clips where the ranking data is actually informative.

Rationale: explaining why a weak clip was still exported ("it was the only available segment") does not build trust. Silence is better than a confusing explanation.

---

## 5. CONFIDENCE MODEL

### 5A. Source of truth for confidence

The backend already computes confidence in two ways:

**1. Output ranking tier** (`confidence_tier` in output_ranking entry):
- Set on the #1 clip only
- Based on score distribution across all rendered clips
- Three states: "strong" / "worth_testing" / "experimental"
- Already in the frontend's `rk.confidenceTier` field — just not displayed

**2. AI Director confidence** (`ai_ux.confidence` in result_json):
- Multi-dimensional: clip_selection, semantic, memory, pacing, camera, subtitle, overall
- From `confidence.py:calculate_ai_confidence()`
- Only available when AI Director ran (not guaranteed for every render)

### 5B. What Phase 66 uses

Phase 66 uses only the `confidence_tier` from the output ranking entry. It is:
- Always computed (no AI Director required)
- Deterministic
- Already in the frontend's rank map

The AI Director confidence scores are NOT used in Phase 66 — they are system-facing dimensions (semantic, memory, pacing) that are not interpretable as "why did THIS clip rank first".

### 5C. Confidence display rules

| Condition | Display |
|---|---|
| `rk.isBest === true` AND `rk.confidenceTier === 'strong'` | "High confidence" badge on best clip card |
| `rk.isBest === true` AND `rk.confidenceTier === 'worth_testing'` | "Close call — test both" note on best clip card |
| `rk.isBest === true` AND `rk.confidenceTier === 'experimental'` | "Uncertain ranking" dim note |
| `!rk.isBest` AND `(bestScore - thisScore) < 1.0` | "Close to best" on non-best card |
| All other non-best clips | No confidence display |

---

## 6. UI RECOMMENDATION

### 6A. Clip card layout after Phase 66

**Current clip card structure:**
```
[thumbnail | Best badge | duration tag]
[title: Clip #2]
[variant badge — if applicable]
[CTA chip — if applicable]
[score: 7.4 /10  #2  ● done]
[reason line: "Strong opening hook, high motion energy."]
[signal chips: Hook 74%  Motion 67%]
[Why this output? — only best clip, only when ai_ux active]
[Keep / Avoid / Rerender]
[Preview  Download  Folder  Cover  Compare]
```

**After Phase 66:**
```
[thumbnail | Best badge | duration tag]
[title: Clip #2]
[variant badge — if applicable]
[CTA chip — if applicable]
[score: 7.4 /10  #2  ● done]
[reason line: "Strong opening hook, Good retention."]          ← unchanged
[explain panel: ✓ Opening hook · ✓ Pacing quality · Duration fit]  ← NEW
[confidence: High confidence]                                  ← NEW (best clip only)
[signal chips: Hook 74%  Motion 67%]                           ← unchanged
[Why this output? — only best clip, only when ai_ux active]    ← unchanged
[Keep / Avoid / Rerender]
[Preview  Download  Folder  Cover  Compare]
```

### 6B. Explain panel HTML structure

```html
<!-- Phase 66: per-clip explanation panel -->
<div class="clipCardExplain">
  <span class="clipCardExplainTag">Strong opening hook</span>
  <span class="clipCardExplainTag">High pacing quality</span>
  <span class="clipCardExplainTag">Dense speech</span>
</div>
<!-- Optional confidence badge (best clip only) -->
<div class="clipCardConfTier" data-tier="strong">High confidence</div>
```

**CSS guidance:**
- Tags: small pill style, same weight as the existing `clipCardSig` chips
- No new CSS classes needed if reusing `clipCardSig` — just different label text
- Confidence tier: single line below the explain tags, colored by tier (green/yellow/dim)
- Do not add `<details>` collapse — the panel is short (2–3 tags) and always readable

### 6C. When to show the explain panel

| Condition | Show explain panel? |
|---|---|
| Clip is `done` AND `ranking_components` present AND `scoreVal >= 5.0` | Yes |
| Clip is `done` AND `ranking_components` present AND `scoreVal < 5.0` | No |
| Clip is `done` AND no `ranking_components` in the rank map entry | No |
| Clip is `failed` or `skipped` | No |
| Clip is still rendering (status = pending/running) | No |

### 6D. What "best clip" gets vs. others

**Best clip (#1):**
- Explain panel: top 2–3 signals
- Confidence tier badge ("High confidence" / "Close call" / "Experimental")
- Existing `_r7SignalRow` unchanged (Hook % + Motion % chips)
- Existing "Why this output?" unchanged (when ai_ux available)

**Non-best clips (score ≥ 6.0/10):**
- Explain panel: top 2 signals only
- No confidence tier badge
- Existing `_r7SignalRow` unchanged (shows when score ≥ 6.0)

**Non-best clips (score < 5.0/10):**
- No explain panel
- Existing `clipCardReason` unchanged (1-line reason if available)

**Failed/skipped clips:**
- No explain panel
- Existing behavior unchanged

---

## 7. REVIEW QUEUE PLACEMENT

### 7A. Where the explain panel lives in the render output flow

The render output flow is:
1. Creator starts render
2. Clips appear as they complete (WebSocket streaming)
3. Each clip card renders with available data
4. Final result_json arrives → output_ranking parsed → rank map built → cards re-rendered with ranking data

Phase 66 data (ranking_components) is only available in step 4 (final result_json). This is the same timing as the existing rank score and reason display. No additional latency introduced.

### 7B. Progressive disclosure

Cards show in two phases:
- **While rendering:** basic card (thumbnail, status dot, duration) — no explain panel
- **After ranking data arrives:** score + reason + explain panel (same re-render as today)

This is the existing behavior — Phase 66 adds to the second render pass only.

### 7C. Interaction model

The explain panel is **always visible** (not collapsed). Rationale: the panel is 2–3 short tags, not a wall of text. Forcing creators to click to see "why" defeats the purpose of explainability. The panel is smaller than the existing Keep/Avoid/Rerender row.

Exception: if screen width is below a threshold (mobile), the explain panel wraps to the same line as the signal chips. No special mobile handling needed — existing CSS flex/wrap handles this.

---

## 8. RISK ASSESSMENT

### 8A. Data integrity risks

| Risk | Assessment | Mitigation |
|---|---|---|
| `ranking_components` absent from older render results | Some renders pre-Phase 66 will lack this key | Gate: only show explain panel when `ranking_components` is present |
| Signal value = 50 (default/neutral, not real data) | Showing "Moderate hook (50%)" as if measured is misleading | Rule: skip any signal whose score is exactly 50.0 — that is the neutral fallback default, not a measured value |
| `speech_density_score` = proxy estimate (45 + scene_count × 3) | This estimate appears when no SRT data exists. It's not a real measurement. | No mitigation needed from UI side — proxy values are indistinguishable from real ones in the data. The proxy is explicitly designed to be plausible. Acceptable risk. |
| `selection_reason` in machine tag format shown raw | "strong_hook+stable_pacing" shown to creator | Mitigation: detect `+` character → translate; otherwise show raw |
| `confidence_tier` shown on non-best clip | Only set on #1 clip by backend | Gate: `rk.isBest === true` before showing confidence tier |

### 8B. Trust risks

| Risk | Assessment |
|---|---|
| Creator sees "Dense speech" on a clip that felt sparse | `speech_density_score` uses SRT coverage ratio, which can differ from perceived density (fast speech = sparse SRT). Creator may disagree. | LOW — the signal is real. Creator disagreement with a real measurement is acceptable. |
| Creator sees "Strong opening hook" but the hook felt weak | `hook_score` uses rule-based text analysis on the first chunk (strong verbs, benefit words). A technically strong hook can feel weak on delivery. | LOW — explain panels are descriptive, not prescriptive. Creators can still override via Keep/Avoid. |
| Creator interprets confidence as a quality guarantee | "High confidence" means the engine is confident in its ranking, not that the clip is objectively great. | MEDIUM — mitigate via copy: "High confidence" not "Perfect clip". Never use "Best clip" language in the explain panel — that's already handled by the "Best" badge. |
| Two clips both show "Strong opening hook" | Can happen when two clips have similar hook scores. | NOT A RISK — each clip's signals are real and independent. Similar readings are accurate. |

### 8C. Regression risks

| Risk | Assessment |
|---|---|
| Existing `clipCardReason` line duplicates explain panel content | `clipCardReason` shows `ranking_reason` (e.g., "Strong opening hook, Good retention."). The explain panel shows tags from `ranking_components`. They will sometimes say the same thing in different forms. | LOW — `clipCardReason` is 1 line of prose; explain panel is 2–3 brief tags. Different density, not duplication. Keep both. |
| Signal chips (`_r7SignalRow`: Hook % / Motion %) conflict with explain panel | Hook % already shows on best clip and high-scoring clips. Phase 66 adds hook as explain panel tag. | LOW — different format: `_r7SignalRow` shows Hook % as a colored chip from parts payload (`hook_score` 0–1). Explain panel shows from `ranking_components.hook_score` 0–100. Different source. Check for value reconciliation in commit plan. |
| Phase 64 QS Bar pills / Phase 65 auto-aspect ratio interact | Phase 66 is display-only. It does not touch QS Bar, aspect ratio, or any input. | ZERO RISK |

---

## 9. SAFE ROLLOUT PLAN

### Before Commit 66.1

Verify the data is actually present:
- Open a completed render job
- In browser DevTools, run: `JSON.parse(document.querySelector('[data-job-id]')?.dataset?.resultJson || '{}')?.output_ranking?.[0]?.ranking_components`
- Expected: dict with `segment_viral_score`, `hook_score`, `retention_score`, `speech_density_score`, `duration_fit_score`
- If absent: the specific render job predates the field. Try a new render — `ranking_components` is produced by the current backend.

### Commit 66.1 validation checklist

- [ ] `_rankMap()` now extracts `rankingComponents` from each output_ranking entry
- [ ] `_r66BuildExplainPanel(rk)` returns empty string when `rankingComponents` is absent or empty
- [ ] Signals with value = 50.0 are skipped (not shown as "Moderate X")
- [ ] At most 3 tags shown
- [ ] Panel is absent for failed/skipped/pending clips
- [ ] Panel is absent for clips with `scoreVal < 5.0`
- [ ] Existing `clipCardReason` line unchanged
- [ ] Existing `_r7SignalRow` chips unchanged
- [ ] Existing "Why this output?" section unchanged
- [ ] Keep / Avoid / Rerender buttons unchanged
- [ ] No JS errors in browser console

### Commit 66.2 validation checklist

- [ ] `confidence_tier` badge appears only on the best clip (`rk.isBest === true`)
- [ ] "High confidence" shows for `confidence_tier === 'strong'`
- [ ] "Close call" shows for `confidence_tier === 'worth_testing'`
- [ ] No badge when `confidence_tier` is absent or `"experimental"`
- [ ] Machine-tag `selection_reason` ("strong_hook+stable_pacing") is translated to "Strong opening hook · Stable pacing"
- [ ] Human-readable `selection_reason` ("Strong opening hook, Fast-paced editing") shows unchanged
- [ ] Variant selection_reason ("Balanced: overall best-quality selection") shows unchanged
- [ ] Selection reason not shown when value is `"best_available"` or empty
- [ ] No regression in `clipVarietyNote` (limited source variety check unchanged)

### Stop conditions

Stop if:
- `ranking_components` values are all exactly 50.0 on every clip (suggests fallback mode — data is not real)
- Hook score in `ranking_components` (0–100 scale) visibly contradicts the Hook % chip from `_r7SignalRow` (0–1 scale × 100) by more than 15 points — indicates a data source mismatch that needs investigation before surfacing

---

## 10. COMMIT PLAN

| # | Commit message | File | Change description | Lines |
|---|---|---|---|---|
| 1 | `explain(66.1): surface ranking components in clip card` | `render-ui.js` | Parse `rankingComponents` in `_rankMap()`; add `_r66BuildExplainPanel(rk)` function; insert panel into clip card HTML | ~35 lines |
| 2 | `explain(66.2): confidence tier badge + selection reason translation` | `render-ui.js` | Add confidence tier badge to best clip; translate machine-tag `selection_reason`; show human-readable selection reason | ~20 lines |

**Total: 1 file, ~55 lines. Zero backend changes. Zero new AI systems.**

### Commit 66.1 — detailed change description

**In `_rankMap()` function (~line 977):**
```javascript
// ADD to the map entry:
rankingComponents: (typeof r.ranking_components === 'object' && r.ranking_components !== null)
  ? r.ranking_components
  : {},
```

**New function `_r66BuildExplainPanel(rk)`:**
```javascript
function _r66BuildExplainPanel(rk) {
  const comps = rk.rankingComponents;
  if (!comps || typeof comps !== 'object') return '';

  const _LABELS = {
    hook_score:           'Opening hook',
    retention_score:      'Pacing quality',
    speech_density_score: 'Speech density',
    duration_fit_score:   'Duration fit',
    segment_viral_score:  'Overall score',
    market_score:         'Market fit',
  };
  const _WEIGHTS = {
    segment_viral_score: 0.35,
    hook_score:          0.20,
    retention_score:     0.20,
    speech_density_score:0.10,
    market_score:        0.10,
    duration_fit_score:  0.05,
  };

  // Compute weighted contribution per signal; skip neutrals (== 50.0)
  var entries = [];
  for (var key in _LABELS) {
    var raw = Number(comps[key]);
    if (!isFinite(raw) || raw === 50.0) continue;
    entries.push({ key: key, raw: raw, contrib: raw * (_WEIGHTS[key] || 0.05) });
  }
  // Sort by weighted contribution descending; keep top 3
  entries.sort(function(a, b) { return b.contrib - a.contrib; });
  entries = entries.slice(0, 3);
  if (!entries.length) return '';

  var tags = entries.map(function(e) {
    return '<span class="clipCardSig">' + esc(_LABELS[e.key]) + '</span>';
  });
  return '<div class="clipCardExplain">' + tags.join('') + '</div>';
}
```

**In clip card HTML (after `clipCardReason` div, before `clipVarietyNote`):**
```javascript
${scoreVal >= 5 && isDone ? _r66BuildExplainPanel(rk) : ''}
```

### Commit 66.2 — detailed change description

**New function `_r66TranslateSelectionReason(raw)`:**
```javascript
function _r66TranslateSelectionReason(raw) {
  if (!raw || raw === 'best_available' || raw === 'fallback') return '';
  if (!raw.includes('+')) return raw;  // already human-readable

  var _MAP = {
    'strong_hook':   'Strong opening hook',
    'stable_pacing': 'Stable pacing',
    'speech_rich':   'Dense speech content',
    'ideal_length':  'Ideal clip duration',
    'high_quality':  'High visual quality',
    'top_viral':     'Top ranked clip',
  };
  return raw.split('+').map(function(tag) {
    return _MAP[tag.trim()] || tag;
  }).join(' · ');
}
```

**In `_rankMap()`, update the map entry:**
```javascript
// UPDATE existing line:
selectionReason: String(r.selection_reason || '').trim(),
// ADD:
selectionReasonHuman: _r66TranslateSelectionReason(String(r.selection_reason || '').trim()),
```

**New function `_r66ConfidenceBadge(rk)`:**
```javascript
function _r66ConfidenceBadge(rk) {
  if (!rk.isBest) return '';
  var tier = rk.confidenceTier;
  if (tier === 'strong')       return '<div class="clipCardConf" data-tier="strong">High confidence</div>';
  if (tier === 'worth_testing')return '<div class="clipCardConf" data-tier="worth_testing">Close call — test both</div>';
  return '';  // 'experimental' and absent: no badge
}
```

**In clip card HTML (after explain panel, before signal chips):**
```javascript
${isDone && rk.isBest ? _r66ConfidenceBadge(rk) : ''}
${rk.selectionReasonHuman && isDone ? `<div class="clipCardSelReason">${esc(rk.selectionReasonHuman)}</div>` : ''}
```

---

## 11. DEFINITION OF DONE

Phase 66 is complete when:

- [ ] Completed clip cards show an explain panel with 2–3 human-readable signal tags derived from `ranking_components`
- [ ] Signal tags are derived from real backend data — no fabricated reasons
- [ ] Signals with neutral default value (50.0) are never shown
- [ ] Clips with score < 5.0/10 or no ranking data show no explain panel
- [ ] Best clip (#1) shows `confidence_tier` as a human-readable badge ("High confidence" / "Close call")
- [ ] Machine-tag `selection_reason` values are translated to human language
- [ ] Human-readable `selection_reason` values display unchanged
- [ ] Zero regressions: existing `clipCardReason`, signal chips, "Why this output?", Keep/Avoid/Rerender all unchanged
- [ ] No JS errors in browser console
- [ ] No backend changes required

### Creator experience after Phase 66

Creator selects TikTok → renders 3 clips → review panel shows:

```
Clip #1  7.8/10  #1  ● done
"Strong segment, Good retention."
  ✓ Opening hook  ✓ Pacing quality  ✓ Duration fit
  High confidence
  Hook 74%  Motion 67%
  [Keep] [Avoid] [Rerender]

Clip #2  6.2/10  #2  ● done
"Strong spoken content."
  ✓ Opening hook  ✓ Speech density
  Hook 61%  Motion 52%
  [Keep] [Avoid] [Rerender]

Clip #3  4.8/10  #3  ● done
"Moderate hook."
  [Keep] [Avoid] [Rerender]
```

Creator understands: Clip #1 won because its opening, pacing, and duration were all strong. Clip #2 is a viable alternative with better speech. Clip #3 is weak — no explanation panel needed.

Creator no longer asks: "Why did AI pick this?"

---

## What Phase 66 does NOT change

| Item | Status |
|---|---|
| Render ranking order | Unchanged — clips are still ranked by the existing weighted score formula |
| Clip selection algorithm | Unchanged — segment builder and viral scorer run identically |
| Backend API | Unchanged — `ranking_components` already in the response |
| `ranking_reason` display | Unchanged — still shown as `clipCardReason` |
| `_r7SignalRow` Hook/Motion chips | Unchanged |
| "Why this output?" `ai_ux` section | Unchanged |
| Keep / Avoid / Rerender steering | Unchanged |
| Any Phase 63/64/65 stable wins | Unchanged |

---

## What Phase 66 defers

| Item | Why deferred |
|---|---|
| Explain panel for in-progress clips (streaming) | `ranking_components` not available until final result_json — after render completes |
| Explaining WHY a clip was NOT selected (losers) | Requires surfacing rejected candidates — significant backend scope beyond Phase 66 |
| Interactive "Tell me more" expansion | 2–3 tags are sufficient for V1; deeper expansion is Phase 67+ |
| AI Director confidence sub-dimensions (semantic, memory) | System-facing, not creator-interpretable |
| Market score explanation ("72 US market score") | Requires surfacing market-scoring detail — Phase 66.5 candidate |

---

*Phase 66 plan based on live code audit of render_pipeline.py, render-ui.js, segment_builder.py, viral_scorer.py, and the explainability module.*
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*
