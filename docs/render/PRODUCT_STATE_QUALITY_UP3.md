# PRODUCT STATE — QUALITY-UP3: Story Arc Intelligence

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): story arc intelligence`
**Status:** Shipped

---

## Summary

A lightweight hook → build → payoff sequencing pass applied after clip scoring.
No LLM, no embeddings — pure heuristic using existing `hook_score`, `start`,
`viral_score`, and `content_type_hint` fields already present on each segment.

The result: selected clips are reordered so the strongest opener leads, the
most emotionally/narratively satisfying clip closes, and the middle plays in
a logical build order driven by content type.

---

## Root Cause

QUALITY-AUDIT1 identified "stitched clip" feeling as a primary signal that a
video was AI-generated. The scoring passes (QUALITY-UP1A through UP2) improved
individual clip quality but left ordering purely to score rank. High-scoring
clips at ranks 2–5 could appear in any sequence, producing videos that felt
like a list of highlights rather than a story.

---

## Part A — Arc Structure

**File:** `backend/app/orchestration/render_pipeline.py`

Applied as a post-selection ordering pass on the `scored` list.

Three roles:

### Hook (position 1)
The clip with the highest `hook_score` among all selected clips.

```
hook_score = starts_at_cut × 40 + position_score × 40 + duration_score × 20
```

This naturally selects clips that:
- Begin at a hard scene cut (instant attention capture)
- Appear early in the source video (natural openers)
- Run for a viewer-retaining duration (not too short, not too long)

### Payoff (position N — last clip)
The selected clip with the latest `start` timestamp in the source video
(excluding the hook).

Rationale: reveals, punchlines, before/after moments, and emotional crescendos
tend to be placed late in the original video. This recovers that material from
score-rank burial and ensures the export ends on its strongest narrative beat.

### Build (positions 2 through N−1)
All remaining clips ordered by content type:

| Content type | Build order | Rationale |
|-------------|-------------|-----------|
| `interview` | Chronological (`start` asc) | Preserves Q&A and dialogue structure |
| `tutorial` | Chronological | Preserves step-by-step instructional flow |
| `vlog` | Chronological | Preserves the day/narrative timeline |
| `commentary` | Score descending (`viral_score`) | Strongest supporting evidence first |

---

## Part B — Skip Conditions

The arc pass is skipped silently (no reorder) when any of the following apply:

| Condition | Why |
|-----------|-----|
| `part_order == "timeline"` | Creator explicitly chose chronological — respect it |
| `len(scored) < 3` | No meaningful arc with 1-2 clips |
| Dominant content type is `"montage"` | Energy-first order is already correct; reordering by arc harms flow |

"Dominant content type" is the most-frequent `content_type_hint` among the
selected clips (ties go to whichever key `max()` returns first — stable for
any given selection).

Log line on skip: `story_arc_skipped reason=montage clips=N`

---

## Part C — Observability

On success:

```
story_arc_applied dominant=vlog clips=5 hook_start=12.3s payoff_start=187.0s hook_score=98.4
```

Emit event: `story_arc_applied`

Context payload:
```json
{
  "dominant_content_type": "vlog",
  "total_clips": 5,
  "hook_start_sec": 12.3,
  "hook_score": 98.4,
  "payoff_start_sec": 187.0,
  "build_order": "chronological"
}
```

`build_order` is `"chronological"` for interview/tutorial/vlog or `"score_desc"`
for commentary and any other content type.

---

## Part D — Safety and Determinism

- **No LLM, no embeddings, no network calls.** Pure Python list sorting.
- **Deterministic.** Same input clips → same output order every time.
- **No clip dropped.** All `len(scored)` clips appear in output; only order changes.
- **No score mutation.** `hook_score`, `viral_score`, and `start` are read-only.
- **No base config mutation.** `scored` is reassigned, not mutated in place.
- **Explainable to creators.** "We open with your strongest hook, close with your late reveal, and keep the middle in logical order."

---

## Part E — Hook Score Field Origin

`hook_score` is computed by QUALITY-UP1A's scoring pass and is already present
on every segment dict. Story arc does not compute it — it only reads it.
If `hook_score` is missing or `None` on a segment, `float(s.get("hook_score", 0) or 0)`
defaults to 0.0 safely — no KeyError, no crash.

Same safety pattern applies to `start` and `viral_score`.

---

## Part F — Edge Cases

| Case | Behavior |
|------|----------|
| All clips have `hook_score=0` | Hook = first clip in `scored` list (stable `max`) |
| Two clips with identical `start` | `max()` returns first found — stable |
| Hook and payoff are the same clip (1-clip edge) | Guarded by `len(scored) >= 3` |
| `content_type_hint` missing on a segment | Defaults to `"vlog"` via `or "vlog"` |
| `dominant_ct` not in build-order table | Falls to `else` branch → `score_desc` |

---

## Parameter Comparison

| Scenario | Before | After |
|----------|--------|-------|
| 5-clip commentary job | Score-rank order (best first) | Hook (best opener) → 3 build clips by viral score → Payoff (latest source time) |
| 5-clip vlog job | Score-rank order | Hook → 3 build clips chronological → Payoff |
| 5-clip montage job | Score-rank order | Score-rank order (arc skipped — energy-first correct) |
| Timeline mode | Chronological | Chronological (arc skipped — creator intent preserved) |
| 2-clip job | Score-rank order | Score-rank order (arc skipped — no meaningful arc) |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| Semantic payoff detection (emotion/language signals) | Would require ML inference; deterministic `start`-based selection is sufficient and explainable |
| Per-clip arc role annotation in export metadata | UI/product decision; backend emits `dominant_content_type` and `build_order` in event context |
| Multi-arc support (sub-arcs within build section) | 3-role arc is sufficient for typical 3–8 clip exports |
| `"montage"` arc variant (energy spike → low → high) | Montage energy-first is already correct; richer arc is QUALITY-UP7+ scope |
| `interview` dominant type with commentary subtype clips | Current: whole arc uses dominant type's build order; per-clip override not yet supported |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/orchestration/render_pipeline.py` | Story arc block after clip selection; `_dominant_ct` computation; hook/payoff/build selection; skip guards for timeline mode, <3 clips, montage |
| `docs/render/PRODUCT_STATE_QUALITY_UP3.md` | This file |

---

## Manual QA Checklist

### Commentary job (3+ clips, no timeline mode)
- [ ] Log shows `story_arc_applied dominant=commentary`
- [ ] First clip in export is the strongest opener (hard cut start, early in source)
- [ ] Last clip in export is the latest-timestamped clip from source
- [ ] Build clips appear in descending viral score order

### Vlog / tutorial / interview job (3+ clips)
- [ ] Log shows `story_arc_applied dominant=vlog` (or tutorial/interview)
- [ ] Build clips appear in chronological source order
- [ ] First and last clips are hook and payoff respectively

### Montage job (3+ clips)
- [ ] Log shows `story_arc_skipped reason=montage`
- [ ] Clip order is unchanged from score-rank order

### Timeline mode (any content type)
- [ ] Arc pass does not fire
- [ ] Clips appear in source chronological order

### 1-clip and 2-clip jobs
- [ ] Arc pass does not fire (no log line)
- [ ] No crash, no error

### Regression
- [ ] Render completes without errors on all content types
- [ ] Subtitle, motion crop, and audio behavior unchanged
- [ ] Cancel still works during render
