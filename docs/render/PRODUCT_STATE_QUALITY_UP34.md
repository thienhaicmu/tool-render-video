# PRODUCT STATE — QUALITY-UP34: Quality Consistency

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): quality consistency`
**Status:** Shipped

---

## Summary

Predictability phase. Moves from "sometimes incredible, sometimes slightly off" to "consistently creator-grade."

Adds a quality consistency layer (`CreatorConsistency`) that reads approved clips from the review queue (kept + favorited) and derives the creator's **style baseline** — which subtitle feel and energy level have consistently produced results they liked. Publishes this as an advisory nudge in the steering panel.

**Creator experience:** "I trust what this tool will output."

---

## Philosophy

- **No new AI.** No ML. No LLM. No cloud.
- **No architecture rewrite.** No pipeline reorder. No new models.
- **Reads real approvals.** Kept + favorited clips are the creator's explicit signal — not inferred preference.
- **Advisory only.** Nudges are informational. Creator choice always wins.
- **No lock-in.** The hint disappears if the creator's pattern changes naturally.
- **Silent when uncertain.** Below MIN_APPROVED (2 kept/favorited items): no nudge at all.
- **Pure frontend.** All computation in localStorage reads. Zero backend changes.

---

## Drift Audit — Root Causes Found (STEP 0)

| Dimension | Drift Source | Fix |
|---|---|---|
| Subtitle style | No feedback loop from review approvals to subtitle selector. Form defaults to preset default on each new session. | Consistency baseline derived from approved items' subtitle_style. Advisory hint fires when pattern is clear. |
| Structure bias | `qsStructureBias` defaults to "balanced" every session. No memory of what creative direction produced kept clips. | Consistency baseline includes structure_bias dimension. |
| Cover frame vibe | `_select_cover_frame_time()` uses `variant_type` + platform + `hook_score`. Without a stable `structure_bias` anchor, cover position varies. | structure_bias consistency nudge keeps the creator's cover vibe tendency stable. |
| Variant personality | `_build_variant_segments()` uses `base_sub` from payload. If `subtitle_style` drifts, the aggressive/story variant subtitle character drifts with it. | Subtitle consistency nudge keeps the variant subtitle stable. |

### What is NOT drift (confirmed correct)
- CTA logic — fully deterministic, maps correctly to variant type and content type
- Platform profiles — stable and well-defined
- Hook scoring — correctly varies by content (this is feature, not drift)
- DNA module — already handles session-persistent style preference

---

## Architecture

### Storage (read-only)

| Key | Used for |
|---|---|
| `review_queue_v1` | Kept + favorited items → payload.subtitle_style, payload.structure_bias |
| `creator_series_v1` | Series fingerprint → cross-validates subtitle_style dimension |

`CreatorConsistency` does NOT write to any localStorage key. It is a computation-only layer.

### Confidence algorithm

```
approved = queue items with state == 'kept' or 'favorited' that have a payload

subConf = count(dominant subtitle_style) / total approved (with subtitle_style)
strConf = count(dominant structure_bias) / total approved (with structure_bias)

series cross-validation:
  if series.fingerprint.subtitle_style == approved dominant:
    subFinal = min(1.0, subConf + 0.10)   ← series agrees: +10%
  else if series exists but disagrees:
    subFinal = max(0.0, subConf - 0.10)   ← series disagrees: -10%

consistency_confidence = (subFinal + strConf) / 2
```

### Confidence gates

| Gate | Threshold | Effect |
|---|---|---|
| `DETECT_GATE` | 0.35 | `cpConsistencyHint` fires; steering panel "Consistent" chip |
| `CHIP_GATE` | 0.55 | Output trust bar chip fires ("Consistent creator style" / "Style consistent") |
| `MIN_APPROVED` | 2 | Minimum kept/favorited items before any detection attempt |

---

## Consistency Hierarchy

Signal order (advisory, not enforcement):

```
manual
  > preset
    > series  (UP31)
      > consistency  (UP34)  ← new
        > DNA  (UP20)
          > platform (UP14)
            > default
```

---

## Parts

### Part A — Subtitle Consistency

`cpConsistencyHint` shows "Style baseline: subtitle: {style}" when the creator's approved clips show a dominant subtitle_style pattern with confidence >= 0.35.

This addresses the root cause: the form has no memory of which subtitle feel produced approved clips.

### Part B — Hook Intensity Consistency

`cpConsistencyHint` also shows "energy: {bias}" when a dominant `structure_bias` is found in approved clips and it is NOT "balanced" (balanced is the default and not meaningful as a consistency signal).

A gaming creator consistently keeping "hook" clips will see "energy: hook-forward" as a reminder; a podcast creator keeping "story" clips will see "energy: story-first."

### Part C — Cover Vibe Consistency

Not a direct UI control, but `structure_bias` consistency nudge stabilizes the `structure_bias` the creator uses — which directly feeds `_select_cover_frame_time()` via the variant type. When the creator consistently sends "story_first" structure bias, cover frames are consistently pulled later in the clip (softer, mid-frame). Aggressive creators get consistently earlier, strong-expression frames.

### Part D — Variant Trust

`subtitle_style` consistency nudge keeps `base_sub` in `_build_variant_segments()` stable across renders. When the creator has consistently approved "pro_karaoke" clips, the balanced variant will render with karaoke-style text. The aggressive variant then overlays its speed/hook selection ON TOP of that consistent base — rather than picking a random subtitle for each render.

### Part E — Trust Surface

Output trust bar chip shows:
- `"Consistent creator style"` — when `approved_count >= 5` and `confidence >= 0.55`
- `"Style consistent"` — when `approved_count >= 2` and `confidence >= 0.55`

No "AI" language. No "we detected" framing. Factual: "Consistent creator style."

### Part F — Observability

| Log event | When | Contains |
|---|---|---|
| `consistency_nudge` | Hint text fires | Full hint label |
| `subtitle_consistency` | Subtitle dimension active | Style value |
| `hook_consistency` | Structure dimension active | Bias value |
| `cover_consistency` | Hint fires + current structure_bias available | `aligned` or `drift` |
| `variant_consistency` | Hint fires + current subtitle_style available | `aligned` or `drift` |
| `consistency_suppressed` | Enough data but below DETECT_GATE | Confidence pct |

---

## Files Changed

### New Files

| File | Purpose |
|---|---|
| `backend/static/js/creator-consistency.js` | `CreatorConsistency` IIFE — consistency profile computation + nudges |

### Modified Files

| File | Change |
|---|---|
| `backend/static/css/v3/review.css` | `.v3ChipConsistency`, `.v3TrustConsistency`, `#cpConsistencyHint` styles |
| `backend/static/index.html` | `cpConsistencyHint` div; `creator-consistency.js` script tag |
| `backend/static/js/editor-view.js` | `evSyncQsBar()`: consistency hint update; `v3RefreshSteeringPanel()`: Consistent chip; payload build: `creator_consistency`; both init blocks: `CreatorConsistency.init()` |
| `backend/static/js/render-ui.js` | Trust bar: `v3TrustConsistency` chip when `CreatorConsistency.getAppliedChip()` returns non-null |

---

## Manual QA Checklist

### A — Consistency detection after 2+ kept clips

- [ ] Keep 2+ clips via Review Queue with the same `subtitle_style` (e.g. "pro_karaoke")
- [ ] Open editor — `cpConsistencyHint` shows "Style baseline: subtitle: karaoke"
- [ ] Steering panel shows "Consistent" chip (amber/gold)
- [ ] Log: `consistency_nudge: Style baseline: subtitle: karaoke`
- [ ] Log: `subtitle_consistency: pro_karaoke`

### B — Structure bias consistency

- [ ] Keep 2+ clips with `structure_bias = "hook"` 
- [ ] cpConsistencyHint shows "Style baseline: ... energy: hook-forward"
- [ ] Log: `hook_consistency: hook`

### C — Different subtitle styles → no nudge

- [ ] Keep 1 clip with "pro_karaoke", 1 clip with "tiktok_bounce_v1"
- [ ] cpConsistencyHint stays hidden — inconsistent styles, no dominant value

### D — Trust chip appears at 55%+ confidence

- [ ] Keep 5+ clips consistently with same subtitle + structure
- [ ] After render completes: output trust bar shows "Consistent creator style" (amber chip)
- [ ] Log confirms consistency chip at high confidence

### E — Below MIN_APPROVED: silent

- [ ] Only 1 kept/favorited item in review queue
- [ ] No hint, no chip, no logs — system is silent

### F — consistency_suppressed logs

- [ ] Keep 2 clips: 1 with "pro_karaoke", 1 with "tiktok_bounce_v1", 1 with "pro_karaoke" (2/3 = 0.67 sub, 0/3 str = 0.33 → conf = 0.33 → below DETECT_GATE 0.35)
- [ ] Log: `consistency_suppressed: below gate (33% < 35%)`

### G — Series cross-validation

- [ ] Series fingerprint has `subtitle_style: "pro_karaoke"`
- [ ] Approved clips also have `subtitle_style: "pro_karaoke"`
- [ ] Confidence boosted +10% vs without series agreement

### H — Creator override always wins

- [ ] Consistency says "karaoke" but creator manually sets "tiktok_bounce_v1"
- [ ] Form respects the manual change
- [ ] `variant_consistency: drift` logged
- [ ] No automatic revert; hint remains advisory

### I — Cover vibe log

- [ ] Keep 2+ clips with `structure_bias = "story"`
- [ ] Open editor with `structure_bias = "hook"`
- [ ] `cover_consistency: drift` logged (current ≠ consistent baseline)
- [ ] Change to "story" → `cover_consistency: aligned` logged

### J — 10 stable renders feel consistent (long-form QA)

- [ ] Render 10 clips with the same creator (same preset, same subtitle style)
- [ ] Keep 4-5 of them via Review Queue
- [ ] On 11th render: hint shows correct baseline
- [ ] All 10 clips' subtitle feel is stable (no sudden jump to "viral" or "clean")

### K — No regressions

- [ ] Normal render flow unchanged
- [ ] DNA hint still shows independently
- [ ] Series hint still shows independently
- [ ] No console errors: `typeof CreatorConsistency !== 'undefined'` guard works
- [ ] Batch queue, review queue, history, settings all unaffected
