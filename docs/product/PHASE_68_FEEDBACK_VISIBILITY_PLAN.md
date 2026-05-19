# PHASE 68 — FEEDBACK VISIBILITY PLAN
## Make Learning Effects Visible In The Render Output

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 67 Creator Memory Visibility — COMPLETE, zero regressions
**Plan date:** 2026-05-19
**Planning only — no implementation in this session**

---

## 1. EXECUTIVE SUMMARY

Phase 67 made memory preferences visible **before** render: creators could see the 🧠 chip, the rerender banner, and the duration hint. The output still didn't explain what the tool actually **did differently** because of those preferences.

Phase 68 closes the second half of that gap: making learning effects visible **in** the render output.

**The primary creator question Phase 68 answers:**

> "I see the DNA chip. Did it actually change which clip ranked first?"
> "I always download Clip #2. Does the tool know that?"
> "Has my export behavior changed how the AI ranks things?"

**What Phase 67 left invisible:**

1. **CreatorDNA hook-sort effect** — The "+3 hook-sort bonus" is a real ranking change applied by `render_pipeline.py` when `creator_dna.confident === true`. The pre-render chip says "DNA active." The clip cards never say "hook-forward sort was applied."

2. **Alternative clip preference** — `CreatorTaste.recordDownload(rank)` tracks every download. If a creator consistently downloads Clip #2 or #3 over many sessions, `prefersAlternativeClip === true` in `CreatorTaste.getPreferences()`. This signal exists, accumulates, and is never shown.

3. **FeedbackLearning backend patterns** — `feedback_memory.json` accumulates `total_exports`, `avg_export_rank`, `dominant_subtitle_style`, `dominant_pacing_style` across AI Director renders. These patterns drive real `subtitle_weighting_bias` and `pacing_weighting_bias` applied during ranking. Creator has zero visibility. No frontend system reads this file.

**What Phase 68 does:** surface these three invisible influences where they are relevant — in the clip output area, not buried above it.

**What Phase 68 does NOT do:** change ranking, add new learning, add new AI, add new storage, invent explanations.

**Implementation scope:** 3 commits. 2 frontend-only. 1 adds a single read-only GET endpoint to the backend. ~50 lines total.

---

## 2. EXISTING INVISIBLE INFLUENCE AUDIT

### Complete inventory — all systems biasing output, with creator visibility rating

| System | Signal source | Where applied | Real output effect | Creator visibility today |
|---|---|---|---|---|
| ClipSteering lock | `clip_steering_v1` localStorage | `render_pipeline.py` — promoted to segment pool front | Direct: locked clips ranked first | **VISIBLE** — Phase 67 rerender banner, Keep button, 🔒 chip |
| ClipSteering exclude | `clip_steering_v1` localStorage | `render_pipeline.py` — filtered before scoring | Direct: excluded clips never appear | **VISIBLE** — 🚫 chip, Avoid button |
| CreatorDNA hook-sort | `creator_dna_v1` localStorage | `render_pipeline.py` — `_dna_hook_bonus=3` applied to hook sort key | **Real: changes sort order** when hook_forward ≥ 0.5 | **PARTIAL** — "DNA active" chip pre-render. Effect on output: **INVISIBLE** |
| CreatorTaste subtitle auto-set | `ct_taste_v1` localStorage | Auto-sets `evSubStyle` selector → affects subtitle render | Real: subtitle style changes if auto-set accepted | **VISIBLE** — inline `#ctSubtitleHint` next to selector |
| CreatorFeedback platform auto-set | `cl_feedback_v1` localStorage | Auto-sets `evTargetPlatform` + aspect ratio (Phase 65) | Real: platform + AR changes if auto-set accepted | **VISIBLE** — inline `#cfPlatformHint` next to selector |
| CreatorMemory taste model | `cm_prefs_v1` localStorage + SQLite | Personalizes AI suggestion confidence text | Display only — affects suggestion labels | **PARTIAL** — shown in AI editor panel, not in render result |
| CreatorSeries fingerprint | `creator_series_v1` localStorage | Sent in render payload; influences preset/platform recommendations | Indirect: nudges defaults toward detected pattern | **VISIBLE** — "Series" chip pre-render |
| CreatorDNA download rank | `creator_taste_v1` `download_rank` | Not yet applied to ranking | Accumulated but unused | **INVISIBLE** — never surfaced |
| **FeedbackLearning biases** | `data/feedback/render_feedback/feedback_memory.json` | `_build_ranking_biases()` → `subtitle_weighting_bias`, `pacing_weighting_bias`, `output_ranking_bias`, `retrieval_weighting_bias` (when AI Director active) | **Real: weighting bias up to 0.25× on subtitle/pacing scoring** | **INVISIBLE** — backend-only, no frontend reads this file |
| **AdaptiveMemory profile** | `data/adaptive/creator_profiles/default.json` | AI Director `_attach_adaptive_creator_intelligence()` → pacing/subtitle/camera enhancement weights | Real: amplifies FeedbackLearning biases when adaptive and feedback agree | **INVISIBLE** — backend-only, no frontend reads this file |
| `ai_ux.safe_influence.items` | result_json → `ai_ux.safe_influence` | Already human-readable, computed from safe_influence_pack | Display metadata: "Bold viral subtitle style applied", "Smoother subject tracking bias" | **PARTIAL** — shown in AI Strategy panel above clips, gated on `ai_ux.available === true`, never connected to specific clips |

### Visibility rating summary

| Visibility level | Systems |
|---|---|
| **VISIBLE** | ClipSteering lock/exclude, platform hint, subtitle hint, Series chip |
| **PARTIAL** | DNA chip (pre-render only, no post-render attribution), AI Strategy panel (gated, above clips), CreatorMemory (AI editor only) |
| **INVISIBLE** | DNA sort effect on clip ranking, download rank preference, FeedbackLearning biases, AdaptiveMemory profile |

---

## 3. SAFE SIGNALS TO SURFACE

### Safe signals — Phase 68 targets

| Signal | Source | Human meaning | Why safe to show |
|---|---|---|---|
| **DNA hook-sort active on best clip** | `CreatorDNA.getDNAContext().hook_forward >= 0.5` + `confident === true` | "Hook-forward ordering was applied to this render" | Deterministic: if DNA is confident, the backend applied the bonus. Not speculation. |
| **Creator prefers alternatives** | `CreatorTaste.getPreferences().prefersAlternativeClip` | "Based on your exports, you often prefer Clip #2 or #3" | Real behavioral signal: `download_rank` EMA tracks actual download choices. Only shown when `rank_other` EMA is dominant. |
| **FeedbackLearning export summary** | `GET /api/feedback/summary` → `total_exports`, `avg_export_rank`, `biases_active` | "Your export history has influenced ranking weights" | Gate: only shown when `total_exports >= 3` (MIN_RELIABLE_COUNT). Factual count, not invented inference. |

### What must stay hidden — not surfaced in Phase 68

| Signal | Why hidden |
|---|---|
| Raw EMA scores (0.35, 0.82) | Internal weighting noise — not interpretable |
| `_dna_hook_bonus` value (3) | Internal constant — meaningless to creator |
| `subtitle_weighting_bias = 0.14` | Raw decimal bias — confusing, not actionable |
| `pacing_confidence = 0.32` | Internal confidence decimal — not creator-facing |
| `adaptive_influences.pacing_enhancement_weight` | Internal metadata — creator doesn't need this |
| AdaptiveMemory full profile JSON | Internal state dump — surveillance-feeling |
| FeedbackLearning per-signal records | Raw history list — too granular |
| `suppressed_signals` list | Internal DNA signals that didn't fire — confusing |
| `avg_export_rank` when < 3 exports | Not reliable; showing premature patterns damages trust |
| `ai_render_influence.applied[]` items | Internal string codes like `"adaptive_creator_intelligence:enabled"` — not creator-readable |

---

## 4. VISIBILITY MODEL

### 4A. DNA attribution note (Commit 68.1)

**What it says:** A single short line inside the best clip's explain panel area:

```
↑ Hook-forward ordering was applied (Creator DNA)
```

**When it appears:**
- `CreatorDNA.getDNAContext().confident === true`
- `CreatorDNA.getDNAContext().hook_forward >= 0.5`
- The clip is the best-ranked clip (`rk.isBest === true`)
- Render is complete (`isDone === true`)

**Visual placement:** After the Phase 66 explain panel tags, before the confidence tier badge. Same subtle styling as `clipCardSelReason`.

**What it does NOT say:**
- Does not claim DNA "won" the clip — only that the ordering was influenced
- Does not show the magnitude (+3 sort bonus)
- Does not appear on non-best clips (the sort effect is global, but attribution on #1 is honest and non-confusing)

**Trust principle:** "Hook-forward ordering was applied" is always true when DNA is confident. We're not speculating about causation — we're reporting that a known influence was active.

---

### 4B. Alternative preference nudge (Commit 68.2)

**What it says:** A single short line on the Clip #2 card (first non-best clip), if the creator's preference is for alternatives:

```
Based on your export history, you often prefer alternatives
```

**When it appears:**
- `CreatorTaste.getPreferences().prefersAlternativeClip === true`
- `CreatorTaste.getPreferences().sessions >= 3` (same confidence gate as subtitle preference)
- The clip is rank 2 AND score ≥ 6.0/10 (only meaningful to highlight a viable alternative)

**Visual placement:** Below the Phase 66 explain panel on the rank-2 clip card only. Same styling as `clipCardSelReason`.

**What it does NOT say:**
- Does not override or suggest the rank-2 clip is "better"
- Does not show download counts or percentages ("you downloaded rank 2 seven times")
- Does not appear on rank 3+ (too aggressive; rank 2 is the most relevant alternative)
- Does not appear if rank-2 clip scores below 6.0 (weak clip nudge is misleading)

**Trust principle:** This is a behavioral observation, not a recommendation. The note text is factual ("you often prefer alternatives") and creator-verifiable — they know their own download habits.

---

### 4C. FeedbackLearning summary note (Commit 68.3)

**What it says:** A compact note below the clip list, shown after render completes, if FeedbackLearning has accumulated enough history:

```
Ranking adapted from your export history (14 renders)
```

And optionally (if `avg_export_rank > 1.5`):
```
Ranking adapted from your export history (14 renders) · You often pick Clip #2
```

**When it appears:**
- A `GET /api/feedback/summary` response has `total_exports >= 3`
- `biases_active === true` (at least one weighting bias > 0.0)
- The clip list has rendered at least one completed clip
- Note is dismissible and does not reappear after dismissal in this session

**Data source:** New read-only `GET /api/feedback/summary` endpoint. Reads `feedback_memory.json` only. No writes. Falls back silently if file missing.

**What it does NOT say:**
- Does not show which specific bias values are active
- Does not show the raw dominant styles (too technical)
- Does not claim the AI "knows" the creator's preferences (only that patterns have accumulated)
- Does not show if total_exports < 3 (below threshold is below trust boundary)

**Trust principle:** "14 renders" is a fact. "Ranking adapted" is accurate when biases_active. The note is a summary, not a breakdown.

---

## 5. TIMING MODEL

| Signal | When to show | Duration |
|---|---|---|
| DNA attribution note | After render completes AND clip cards have rendered | Persistent in clip card (same lifecycle as clip card) |
| Alternative preference nudge | After render completes AND rank-2 clip card has rendered | Persistent in clip card |
| FeedbackLearning summary note | After render completes AND first clip card appears | Session-persistent (dismissed per session) |
| All three above | Only after render is DONE (not while streaming) | N/A — these are post-render states |

### Timing constraints

**Never show before render completes.** All three signals require final clip data to determine:
- Which clip is best (for DNA attribution)
- Which clip is rank 2 with score ≥ 6 (for alternative nudge)
- Render has completed (for feedback summary fetch)

**Never show during partial results.** If clips are still streaming (status = pending/running), wait until all are done or the result_json has arrived.

**FeedbackLearning note timing:** Fetch `GET /api/feedback/summary` once after the first render completes for the session. Cache the result. Do not refetch on rerender.

---

## 6. TRUST AND UX RULES

### Hard limits

| Rule | Rationale |
|---|---|
| Never claim DNA caused the clip to rank #1 | The sort bonus influences order but is not the sole determinant. Use "was applied" not "determined this ranking" |
| Never show alternative nudge if rank-2 clip scores < 6.0 | Nudging toward a weak clip damages trust |
| Never show FeedbackLearning note if total_exports < 3 | Premature pattern attribution is fabrication |
| Never show raw bias decimals | "subtitle_weighting_bias: 0.14" is meaningless to creators and feels surveillance-like |
| Never show FeedbackLearning note if biases_active === false | The system is active but no biases fired — showing a note would be misleading |
| Never auto-apply alternative preference | Only inform. Creator decides which clip to download. |
| Always gate DNA note on DNA being confident | `confident === false` → DNA was NOT applied. Showing a note would be false. |
| Always make the FeedbackLearning note dismissible | It's informational, not critical. One-tap dismiss. |

### What "honest" means in Phase 68

| Phrase | Honest? | Why |
|---|---|---|
| "Hook-forward ordering was applied" | **YES** — DNA confident + hook_forward ≥ 0.5 means backend applied it | Factual |
| "DNA made this clip win" | **NO** | Causation beyond what we can prove |
| "You often prefer alternatives" | **YES** — download_rank EMA shows this | Behavioral fact |
| "Clip #2 is better for you" | **NO** | Value judgment beyond the signal |
| "Ranking adapted from your export history (14 renders)" | **YES** — total_exports is a count | Factual |
| "The AI knows your taste" | **NO** | Anthropomorphization and overclaiming |
| "Your pacing preference was applied (bias: 0.19)" | **NO** | Raw internal value shown to creator |

---

## 7. WHAT MUST STAY HIDDEN

### Hidden from Phase 68 UI

| Item | Why hidden |
|---|---|
| `_dna_hook_bonus` value | Internal constant; magnitude is not creator-relevant |
| `hook_forward` numeric (0.5, 1.0) | EMA decimal — not interpretable; "DNA active" already conveys the fact |
| `subtitle_weighting_bias = 0.14` | Internal scale; "adapted from your export history" is sufficient |
| `adaptive_influences.*_weight` | Sub-component of a sub-component of bias calculation |
| `avg_export_rank` as a decimal | Show "you often pick alternatives" not "avg rank: 1.7" |
| Per-signal feedback records | Individual signal history list — too granular |
| `pattern_counts` dict | Internal accumulator — creator doesn't need to see the raw counters |
| `creator_style_count`, `pacing_style_count` | Count of pattern occurrences — not creator-interpretable |
| AdaptiveMemory `style_confidence`, `pacing_confidence` | Internal confidence floats |
| `safe_influence_pack` full dict | Safe influence items are already surfaced by `ai_ux.safe_influence.items` in the AI Strategy panel; do not duplicate with raw dict |
| Any signal with zero accumulation | Empty signal = "no data" = nothing to say |

### Why the AI Strategy panel is not changed

`renderAiStrategyPanel()` already renders `ai_ux.safe_influence.items` when `ai_ux.available === true`. Phase 68 does not add new items to this panel, nor move it. The panel is correct for AI Director renders. Phase 68 adds COMPLEMENTARY signals that work for standard renders too (DNA, download preference).

---

## 8. SAFE ROLLOUT PLAN

### Pre-implementation verification

**Before 68.1:** Verify `CreatorDNA.getDNAContext()` is globally accessible in `render-ui.js`. Confirm `hook_forward` and `confident` are in the return object. Check that `getDNAContext()` never throws when called before DNA has loaded.

**Before 68.2:** Verify `CreatorTaste.getPreferences()` is accessible from `render-ui.js`. Confirm `prefersAlternativeClip` is in the return object. Confirm `sessions` is accessible or checkable.

**Before 68.3:** Verify `data/feedback/render_feedback/feedback_memory.json` exists on a system that has run AI Director renders. Confirm it is readable by the FastAPI process. Design the endpoint to return `{available: false}` when file is missing.

---

### Commit 68.1 — `visibility(68.1): DNA ranking attribution on best clip`

**File:** `backend/static/js/render-ui.js`
**Change:** In the clip card template, after `_r66BuildExplainPanel(rk)` and before `_r66ConfidenceBadge(rk)`, inject a DNA attribution note when conditions are met.

**New function:** `_r68DnaNote(rk)`:
```javascript
function _r68DnaNote(rk) {
  if (!rk.isBest) return '';
  if (typeof CreatorDNA === 'undefined') return '';
  var ctx = CreatorDNA.getDNAContext();
  if (!ctx || !ctx.confident || (ctx.hook_forward || 0) < 0.5) return '';
  return '<div class="clipCardSelReason" style="opacity:0.75">'
    + '↑ Hook-forward ordering was applied (Creator DNA)</div>';
}
```

**Insertion in clip card template:**
```javascript
${isDone && rk.isBest ? _r68DnaNote(rk) : ''}
```
Placed after `_r66BuildExplainPanel(rk)` line.

**Validation checklist:**
- [ ] Note appears on best clip when DNA is confident and hook_forward ≥ 0.5
- [ ] Note absent when `confident === false`
- [ ] Note absent when `hook_forward < 0.5` (DNA confident but not hook-forward)
- [ ] Note absent on non-best clips
- [ ] Note absent when CreatorDNA is undefined (safe no-op)
- [ ] No JS errors when getDNAContext() is called before DNA load
- [ ] Existing Phase 66 explain panel, confidence badge, and selection reason unchanged

---

### Commit 68.2 — `visibility(68.2): alternative preference nudge on rank-2 clip`

**File:** `backend/static/js/render-ui.js`
**Change:** In the clip card template, add an alternative preference note for rank-2 clips only.

**New function:** `_r68AltNote(rk)`:
```javascript
function _r68AltNote(rk) {
  if (rk.isBest || (rk.rank || 0) !== 2) return '';
  if (typeof CreatorTaste === 'undefined') return '';
  var prefs = CreatorTaste.getPreferences();
  if (!prefs || !prefs.prefersAlternativeClip || (prefs.sessions || 0) < 3) return '';
  return '<div class="clipCardSelReason" style="opacity:0.75">'
    + 'Based on your export history, you often prefer alternatives</div>';
}
```

**Insertion in clip card template:**
```javascript
${isDone && (rk.rank || 0) === 2 && scoreVal >= 6 ? _r68AltNote(rk) : ''}
```
Placed after the Phase 66 `_r66BuildExplainPanel(rk)` line (same level as DNA note).

**Validation checklist:**
- [ ] Note appears on rank-2 clip when `prefersAlternativeClip === true` AND `sessions >= 3` AND `scoreVal >= 6.0`
- [ ] Note absent when `prefersAlternativeClip === false`
- [ ] Note absent when sessions < 3 (not confident yet)
- [ ] Note absent on best clip (rank 1)
- [ ] Note absent on rank 3+ clips
- [ ] Note absent when rank-2 clip scores < 6.0
- [ ] Note absent when CreatorTaste is undefined
- [ ] No regression in existing clip card layout for rank-2 clips

---

### Commit 68.3 — `visibility(68.3): feedback learning summary note`

**Backend file:** `backend/app/routes/creator.py`
**Frontend file:** `backend/static/js/render-ui.js`

**Backend change — new read-only endpoint:**

```python
@router.get("/api/feedback/summary")
def api_get_feedback_summary():
    """Return a creator-facing summary of accumulated feedback patterns.
    
    Reads feedback_memory.json. Falls back to zeros if missing or corrupt.
    Never raises.
    """
    try:
        from app.ai.feedback.feedback_memory import load_feedback_memory
        memory = load_feedback_memory()
        patterns = memory.get("pattern_counts", {}) or {}
        total_exports = int(memory.get("total_exports", 0))
        total_signals = int(memory.get("total_signals", 0))
        
        exported_ranks = list(patterns.get("exported_ranks", []))
        avg_rank = round(sum(exported_ranks) / len(exported_ranks), 1) if exported_ranks else 0.0
        
        def _top(cat):
            d = patterns.get(cat, {})
            return max(d, key=lambda k: d[k]) if d else ""
        
        biases_active = total_exports >= 3  # mirrors _MIN_RELIABLE_COUNT
        
        return {
            "available": True,
            "total_signals": total_signals,
            "total_exports": total_exports,
            "avg_export_rank": avg_rank,
            "dominant_subtitle_style": _top("subtitle_style"),
            "dominant_pacing_style": _top("pacing_style"),
            "dominant_creator_style": _top("creator_style"),
            "biases_active": biases_active,
        }
    except Exception:
        return {"available": False, "total_exports": 0, "biases_active": False}
```

**Frontend change — fetch and display:**

New function `_r68FetchFeedbackSummary()` called once after render completes:

```javascript
var _r68FeedbackSummaryCache = null;

function _r68FetchFeedbackSummary(onResult) {
  if (_r68FeedbackSummaryCache !== null) { onResult(_r68FeedbackSummaryCache); return; }
  fetch('/api/feedback/summary')
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      _r68FeedbackSummaryCache = data || { available: false };
      onResult(_r68FeedbackSummaryCache);
    })
    .catch(function() { _r68FeedbackSummaryCache = { available: false }; });
}

function _r68ShowFeedbackNote(summary) {
  if (!summary || !summary.available || !summary.biases_active) return;
  if (summary.total_exports < 3) return;
  if (document.getElementById('r68FeedbackNote')) return;
  
  var list = document.getElementById('render_output_list');
  if (!list) return;
  
  var el = document.createElement('div');
  el.id = 'r68FeedbackNote';
  el.style.cssText = 'font-size:11px;color:var(--fg2,#888);padding:6px 12px;margin:4px 0;display:flex;align-items:center;gap:8px';
  
  var label = 'Ranking adapted from your export history (' + summary.total_exports + ' renders)';
  if (summary.avg_export_rank > 1.5) label += ' · You often pick alternatives';
  
  el.innerHTML = '<span>' + esc(label) + '</span>'
    + '<button onclick="document.getElementById(\'r68FeedbackNote\').remove()" '
    + 'style="background:none;border:none;color:var(--fg2,#888);cursor:pointer;font-size:12px;padding:0 4px">×</button>';
  
  list.parentNode.insertBefore(el, list);
}
```

Called from the post-render clip list render pass (after result_json arrives and clips are shown).

**Validation checklist:**
- [ ] `GET /api/feedback/summary` returns `{available: true, ...}` when feedback_memory.json exists with ≥ 3 exports
- [ ] `GET /api/feedback/summary` returns `{available: false}` when file missing or corrupt
- [ ] Frontend fetches once per session (cache prevents repeat fetches on rerender)
- [ ] Summary note appears below the clip list only when `biases_active === true` AND `total_exports >= 3`
- [ ] Note absent when `total_exports < 3`
- [ ] Note absent when `available === false`
- [ ] Note is dismissible via × button
- [ ] Note does not reappear after dismiss (no localStorage needed — session only)
- [ ] `avg_export_rank > 1.5` line only appended when that condition is met
- [ ] No regression in clip list rendering
- [ ] Endpoint never raises — always returns a JSON response

---

## 9. COMMIT PLAN

| # | Commit message | Files | Change description | Est. lines |
|---|---|---|---|---|
| 1 | `visibility(68.1): DNA ranking attribution on best clip` | `render-ui.js` | `_r68DnaNote(rk)` function + clip card insertion | ~15 |
| 2 | `visibility(68.2): alternative preference nudge on rank-2 clip` | `render-ui.js` | `_r68AltNote(rk)` function + clip card insertion | ~15 |
| 3 | `visibility(68.3): feedback learning summary note` | `creator.py`, `render-ui.js` | `GET /api/feedback/summary` endpoint + `_r68FetchFeedbackSummary()` + `_r68ShowFeedbackNote()` | ~40 |

**Total: 3 commits, 2 files. ~70 lines. Zero new AI. Zero new storage. One new read-only GET endpoint.**

---

## 10. DEFINITION OF DONE

Phase 68 is complete when:

- [ ] Best clip card shows "↑ Hook-forward ordering was applied (Creator DNA)" when DNA is confident and hook_forward ≥ 0.5
- [ ] DNA note absent when DNA is not confident or hook_forward < 0.5
- [ ] Rank-2 clip shows "Based on your export history, you often prefer alternatives" when `prefersAlternativeClip === true`, `sessions >= 3`, and clip score ≥ 6.0
- [ ] Alternative note absent for rank 1, rank 3+, weak clips, or insufficient sessions
- [ ] `GET /api/feedback/summary` returns correct summary when `feedback_memory.json` exists with ≥ 3 exports
- [ ] Endpoint returns `{available: false}` when file missing — no 500 errors
- [ ] FeedbackLearning summary note appears below clip list after render when `biases_active === true`
- [ ] Summary note is dismissible and does not reappear within the session
- [ ] All notes use subtle styling (opacity 0.75, small font) — not alarming
- [ ] Zero regressions: Phase 66 explain panel, confidence badge, selection reason, Phase 67 rerender banner, all unchanged
- [ ] Zero regressions: Keep/Avoid/Rerender flow, clip card layout, download links

### Creator experience after Phase 68

Creator has 15+ actions logged (DNA confident, hook_forward ≥ 0.5), always downloads Clip #2, has run 8 AI Director renders:

```
Render completes. Clip list appears.

─── Clip #1  8.1/10  #1  ● done ───────────────────────────
"Strong opening hook, High retention."
  ✓ Opening hook  ✓ Pacing quality  ✓ Duration fit
  High confidence
  ↑ Hook-forward ordering was applied (Creator DNA)
  [Keep] [Avoid] [Rerender]

─── Clip #2  7.3/10  #2  ● done ───────────────────────────
"Dense speech, Good overall score."
  ✓ Speech density  ✓ Overall score
  Based on your export history, you often prefer alternatives
  [Keep] [Avoid] [Rerender]

─── Clip #3  5.4/10  #3  ● done ───────────────────────────
"Moderate hook."
  [Keep] [Avoid] [Rerender]

Ranking adapted from your export history (8 renders) · You often pick alternatives  [×]
```

Creator now understands:
1. Clip #1 ranked first partly because hook-forward sort was active
2. Clip #2 has a note acknowledging their pattern — they might want to start there
3. The ranking engine has observed their behavior across 8 renders and is adapting

Creator stops asking: "Did DNA actually do anything?" and "Does it know I always pick Clip #2?"

---

## What Phase 68 does NOT change

| Item | Status |
|---|---|
| Clip ranking algorithm | Unchanged |
| CreatorDNA behavior | Unchanged — Phase 68 adds visibility only |
| ClipSteering behavior | Unchanged |
| `render_pipeline.py` | Unchanged |
| `ai_ux_metadata.py` | Unchanged |
| AI Strategy panel | Unchanged |
| Phase 66 explain panel | Unchanged |
| Phase 67 rerender banner | Unchanged |
| Phase 67 duration hint | Unchanged |
| Phase 67 memory summary chip | Unchanged |
| Any Phase 63–67 wins | Unchanged |

## What Phase 68 defers

| Item | Why deferred |
|---|---|
| Surfacing AdaptiveMemory profile to creator | Overlaps significantly with CreatorTaste/CreatorFeedback localStorage signals; adds complexity without new insight for standard renders |
| FeedbackLearning per-style breakdown ("Preferring Clean subtitles, Fast pacing") | Duplicate of what CreatorTaste/CreatorFeedback already show; value is marginal |
| Memory timeline / confidence decay UI | "Learned X sessions ago" — useful but requires timestamp tracking in existing memory stores; not currently stored |
| Interactive "explain why DNA changed ranking" | Requires score comparison before/after DNA bonus — would need backend to return both sorted orders; significant scope |
| Cross-render hook score preference from ClipSteering | Requires reading Phase 66 rankingComponents at Keep-time and storing hook_score — architectural dependency (deferred from Phase 67 also) |

---

*Phase 68 plan based on live code audit of creator-dna.js, creator-taste.js, feedback_learning.py, feedback_memory.py, adaptive_memory.py, ai_ux_metadata.py, render_pipeline.py, render-ui.js, and creator.py.*
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*
