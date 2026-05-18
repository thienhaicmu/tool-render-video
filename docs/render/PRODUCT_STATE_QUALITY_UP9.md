# PRODUCT STATE — QUALITY-UP9: Truthful AI / Creator Trust

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): truthful AI creator trust`
**Status:** Shipped

---

## Summary

Five surgical improvements to ranking transparency and AI explainability.
No ranking rewrite. No UI redesign. No LLM. No fake confidence. No marketing language.

Each part replaces a vague or threshold-restating signal with a statement
that is truthful about what actually drove the AI's clip selection.

---

## Part A — Contribution-Weighted Ranking Reason

**File:** `backend/app/orchestration/render_pipeline.py`

### Problem

`_output_ranking_reason()` used simple threshold gates independent of contribution
weights. A clip where `hook_score=72` drove less than 5% of the score still generated
"Strong spoken hook" even when `segment_viral_score=80` (weight 0.35) dominated.

### Fix: Materiality threshold on contribution weight

New `_RANKING_WEIGHTS` module-level constant mirrors the scoring formula exactly:

```python
_RANKING_WEIGHTS = {
    "segment_viral_score":  0.35,
    "hook_score":           0.20,
    "retention_score":      0.20,
    "speech_density_score": 0.10,
    "market_score":         0.10,
    "duration_fit_score":   0.05,
}
```

New `_output_ranking_detail(components)` computes per-signal weighted contributions
and applies a materiality gate: a signal must contribute ≥60% of the top contributor's
weighted value to be surfaced as a reason.

```python
def _output_ranking_detail(components: dict) -> dict:
    contribs = {k: components.get(k, 50.0) * w for k, w in _RANKING_WEIGHTS.items()}
    ...
    material = [s for s, c in ranked if c >= top_contrib * 0.60]
    suppressed = [s for s, c in ranked[1:] if c < top_contrib * 0.60 and components.get(s, 50.0) >= 65]
```

`_output_ranking_reason()` iterates only `material_signals`, generating at most 2 reasons.
The old 3-reason cap is reduced to 2 — max one sentence of honest context.

---

## Part B — Dominant Signal + Suppressed Signals in Ranking Entry

**File:** `backend/app/orchestration/render_pipeline.py`

`_compute_output_ranking_entry()` now includes `dominant_signal` and `suppressed_signals`
in the returned dict. These are computed by `_output_ranking_detail()` and flow through
the API to the frontend.

```python
_detail = _output_ranking_detail(components)
return {
    ...
    "dominant_signal": _detail["dominant_signal"],
    "suppressed_signals": _detail["suppressed_signals"],
    ...
}
```

`suppressed_signals` lists signals that scored ≥65 but were not material to the ranking
decision — visible in the API for debugging, not shown directly in UI copy.

---

## Part C — Confidence Tier

**File:** `backend/app/orchestration/render_pipeline.py`

After `_rank_entries.sort()`, a confidence tier is computed from the score margin
between the best and second-best clip:

| Margin | Tier | Label |
|---|---|---|
| ≥ 8 pts | `strong` | Strong candidate |
| 4–8 pts | `worth_testing` | Worth testing |
| < 4 pts | `experimental` | Experimental pick |

```python
_confidence_tier = (
    "strong" if _conf_margin >= 8 else
    "worth_testing" if _conf_margin >= 4 else
    "experimental"
)
_rank_entries[0]["confidence_tier"] = _confidence_tier
_rank_entries[0]["score_margin"] = round(_conf_margin, 1)
```

Only the best clip receives `confidence_tier` — it describes AI confidence in the
selection, not a property of individual clips.

Also emits `ranking_truth_audit` log line per render with confidence, margin, dominant,
and suppressed signals for QA grep.

---

## Part D — Badge Cleanup

**File:** `backend/app/ai/visibility/ai_visibility_summary.py`

### Problem

`build_ai_visibility_summary()` generated up to 5 badges using threshold gates
("Strong hook", "Good retention", "Market fit", "Good duration", "Strong output rank")
and added threshold-restating reasons ("High hook score", "Good retention score",
"Strong output score") that duplicated what was already in `ranking_reason`.

### Fix: Max 2 contribution-weighted badges + confidence_tier

Badges now come from `dominant_signal` (if raw score ≥60) and at most one
`suppressed_signals` entry (if raw score ≥65). Max 2 badges total.

Threshold-restating reasons ("High hook score", etc.) are removed.
`ranking_reason` and `selection_reason` remain the primary reason text.

`confidence_tier` and `confidence_label` are now included in the summary:

```python
if confidence_tier and confidence_tier in _CONFIDENCE_LABELS:
    summary["confidence_tier"] = confidence_tier
    summary["confidence_label"] = _CONFIDENCE_LABELS[confidence_tier]
```

---

## Part E — Compare Mode Truthful Fallback

**File:** `backend/static/js/render-ui.js`

### Problem

`_r821BuildTradeoffHtml()` fallback reasoning (when `refRk.reason` is absent) used
generic text: "Stronger opening retention." and "AI score reflects combined hook,
motion, and quality signals." — no numbers, no confidence context.

### Fix: Real delta numbers + confidence prefix

```javascript
const hookDelta = refHook - chalHook;
if (Math.abs(hookDelta) >= 5) {
  _parts.push(hookDelta > 0
    ? 'Hook +' + hookDelta + '% advantage.'
    : 'Challenger leads hook by ' + (-hookDelta) + '%.');
}
var confPrefix = '';
if (_confTier === 'experimental') confPrefix = 'Close call (+' + _scoreGap.toFixed(1) + ' pts). ';
else if (_confTier === 'worth_testing') confPrefix = 'Slight edge (+' + _scoreGap.toFixed(1) + ' pts). ';
reasoning = confPrefix + (_parts.join(' ') || 'Score reflects combined hook, motion, and quality signals.');
```

Thresholds: hook delta shown when ≥5%; motion delta shown when ≥8%.
Confidence prefix only fires for `experimental` and `worth_testing` tiers (not `strong`).

`_rankMap()` now also reads `confidence_tier` and `dominant_signal` from API response
into the rank map entry for downstream use.

---

## What Was Intentionally Deferred

| Deferred | Reason |
|---|---|
| Showing `confidence_label` in clip card UI | Requires UI layout change; card is already dense |
| Showing `suppressed_signals` to creator | "X scored high but didn't move the needle" is confusing without more context |
| Per-clip confidence (not just best clip) | Confidence describes selection decision, not clip quality in isolation |
| `dominant_signal` display in card | Signal name ("segment_viral_score") needs human label mapping; deferred to UP12 |
| Reason text localization | English-only; internationalization deferred |

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/orchestration/render_pipeline.py` | `_RANKING_WEIGHTS`, `_output_ranking_detail`, rewritten `_output_ranking_reason`; `dominant_signal`/`suppressed_signals` in ranking entry; confidence tier after sort; `ranking_truth_audit` log |
| `backend/app/ai/visibility/ai_visibility_summary.py` | Max 2 contribution-weighted badges; `confidence_tier`/`confidence_label`; removed threshold-restating reasons |
| `backend/static/js/render-ui.js` | `_rankMap()` reads `confidence_tier`/`dominant_signal`; `_r821BuildTradeoffHtml()` fallback uses real deltas + confidence prefix |
| `docs/render/PRODUCT_STATE_QUALITY_UP9.md` | This file |

---

## Manual QA Checklist

### Part A — Contribution-weighted reasons

- [ ] Tutorial with high viral_score (80) + modest hook (65): reason reflects viral dominance, not hook
- [ ] Interview with hook=85 and viral=60: reason shows "Strong spoken hook" (hook is material)
- [ ] Montage with viral=70, all others neutral: reason shows "High visual energy"
- [ ] Any render: max 2 reasons in `ranking_reason` field
- [ ] Fallback fires when no material signal generates a label: "Balanced clip signals"

### Part B — Dominant + suppressed signals

- [ ] API response for each ranked part includes `dominant_signal` field
- [ ] API response includes `suppressed_signals` array (may be empty)
- [ ] `dominant_signal` matches the highest-weight contributing signal
- [ ] `suppressed_signals` only lists signals that scored ≥65 but weren't material

### Part C — Confidence tier

- [ ] Best clip with clear winner (margin ≥8): `confidence_tier = "strong"`
- [ ] Best clip with slight edge (margin 4–8): `confidence_tier = "worth_testing"`
- [ ] Best clip with near tie (margin <4): `confidence_tier = "experimental"`
- [ ] Only best clip (`is_best_clip=True`) has `confidence_tier` in API response
- [ ] `score_margin` field present and correct in best clip entry
- [ ] `ranking_truth_audit` log line appears in job log after render

### Part D — Badge cleanup

- [ ] Clip with dominant_signal=hook_score (score 75): badge "Strong hook" appears
- [ ] Badge count never exceeds 2
- [ ] No badge "Strong output rank" (removed)
- [ ] No reason text "High hook score" / "Good retention score" (removed)
- [ ] `confidence_tier` and `confidence_label` present in `ai_visibility_summary` for best clip

### Part E — Compare mode

- [ ] Compare mode with hook delta ≥5%: shows "Hook +N% advantage." with real number
- [ ] Compare mode with hook delta <5%: hook not mentioned in fallback
- [ ] Experimental tier compare: fallback prefixed with "Close call (+X.X pts)."
- [ ] Worth testing tier compare: fallback prefixed with "Slight edge (+X.X pts)."
- [ ] Strong tier compare: no confidence prefix in fallback
- [ ] Fallback when no signals available: "Score reflects combined hook, motion, and quality signals."

### Safety

- [ ] Cancel still works during render phase
- [ ] Resume still works for interrupted renders
- [ ] No regression on commentary, vlog, montage, interview renders
- [ ] No backend errors in queue or concurrent renders
- [ ] Single-clip render (no comparison): `confidence_tier = "strong"` (50pt margin default)
