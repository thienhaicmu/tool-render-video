# PRODUCT STATE — QUALITY-UP13: Multi-Variant Intelligence

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): multi-variant intelligence`
**Status:** Shipped

---

## Summary

One render job now produces three purposeful edit options — Aggressive, Balanced,
and Story-first — instead of one. Creator sees why each exists and can pick without
re-rendering blindly.

No LLM. No random rerolls. No pipeline rewrite. No queue redesign.
Shared compute for everything before encoding; 3x encoding in parallel.

---

## Part A — Purposeful Variants

Three variants. Each has a specific intent, a specific segment selection strategy,
a subtitle bias, and a speed bias.

### Variant A — Aggressive
- **Goal:** Hook strength, energy, retention
- **Good for:** TikTok, reaction, commentary, fast Shorts
- **Segment selection:** `hook_score × 0.50 + viral_score × 0.30 + motion_score × 0.20`
- **Subtitle bias:** `viral` (interview/commentary/vlog/tutorial) or `gaming` (montage)
- **Speed bias:** `+0.05` (e.g. 1.07 → 1.12)

### Variant B — Balanced
- **Goal:** Best-overall smart edit (current default behavior)
- **Good for:** General creator workflow, YouTube Shorts
- **Segment selection:** `viral×0.35 + hook×0.20 + scene_quality×0.20 + speech×0.10 + market×0.10 + duration_fit×0.05`
  - Note (HARDENING1): `scene_quality_score` replaced `retention_score` — retention was never
    computed by the viral scorer (always 0). scene_quality_score is always populated.
- **Subtitle bias:** Creator's payload choice (inherits `subtitle_style`, taste-aware from UP12)
- **Speed bias:** No change (exact payload `playback_speed`)

### Variant C — Story-first
- **Goal:** Flow, coherence, payoff protection
- **Good for:** Vlog, education, storytelling, YouTube Shorts
- **Segment selection:** `scene_quality_score × 0.45 + (start / max_start) × 100 × 0.30 + viral_score × 0.25`
  - Note (HARDENING1): `scene_quality_score` replaced `retention_score` — retention was never
    computed by the viral scorer. scene_quality reflects visual clarity and transition quality,
    a real proxy for payoff-worthy content. Positional bias preserved: story-first still tends
    toward later-in-source clips with high visual quality.
- **Subtitle bias:** `story` (commentary/vlog/montage) or `clean` (interview/tutorial)
- **Speed bias:** `−0.05` (e.g. 1.07 → 1.02)

---

## Part B — Shared Computation

All expensive pipeline stages run once and are shared across all three variants:

| Stage | Shared? |
|---|---|
| Source download / prepare | ✓ Shared |
| Scene detection | ✓ Shared |
| Viral / hook / retention scoring | ✓ Shared |
| Tutorial detection (UP10B) | ✓ Shared |
| Market-viral scoring | ✓ Shared |
| Whisper transcription | Per-variant clip (3× only if variants pick different segments) |
| FFmpeg cut | Per-variant (3×) |
| FFmpeg final encode | Per-variant (3×) |

Variants run in parallel using the existing `ThreadPoolExecutor` render pool.
Expected total overhead: **~1.5–1.8× baseline** single-clip render time.

---

## Part C — Taste Memory Integration

The **Balanced** variant inherits `payload.subtitle_style` exactly as submitted.
Because UP12's `CreatorTaste` pre-populates `subtitle_style` with the creator's
preferred style before render submission, the Balanced variant automatically
reflects the creator's taste preference.

Aggressive and Story-first variants have their own subtitle logic (defined in
`_VARIANT_AGGRESSIVE_SUB` and `_VARIANT_STORY_SUB` maps). Taste does not override
variant-specific subtitle intent.

---

## Part D — Output Experience

### Output file naming (multi_variant=True)
```
{stem}_aggressive.mp4
{stem}_balanced.mp4
{stem}_story_first.mp4
```

### Output file naming (multi_variant=False — unchanged)
```
{stem}_part_001.mp4
{stem}_part_002.mp4
{stem}_part_003.mp4
```

### Clip card variant badges
Each clip card in the render output panel shows a variant badge:
- **Aggressive** — hook/energy focused
- **Balanced** — smart default
- **Story-first** — coherence / payoff

### Part ordering
Variants appear as parts 1 (Aggressive), 2 (Balanced), 3 (Story-first).
The existing output ranking still runs and can surface a different "Best" clip
if the scoring data differs between variants.

---

## Part E — Performance Safety

- Story arc reordering is **skipped** in multi-variant mode (each variant is a single
  clip, not a sequence — arc ordering has no meaning)
- Encoding runs in parallel via existing worker pool — no additional threads created
- `_build_variant_segments()` is a pure function operating on existing score fields —
  zero external calls, negligible overhead

---

## Part F — Observability

A `multi_variant_selected` event is emitted after variant selection:
```
event: multi_variant_selected
context: {
  variant_types: ["aggressive", "balanced", "story_first"],
  variants: [
    {variant, start, hook_score, speed, subtitle},
    ...
  ]
}
```

Per-part `visual_finish_applied` event already includes `variant_type` via `part_name`.

Grep: `multi_variant_selected` in job log for QA.

---

## Schema Changes

`backend/app/models/schemas.py`:
```python
multi_variant: bool = False  # default off — backward compatible
```

When `multi_variant=True`:
- `max_export_parts` is effectively overridden to 3 (one per variant)
- Story arc is skipped
- Output filenames use `_{variant_type}` suffix

---

## Files Changed

| File | Change |
|---|---|
| `backend/app/models/schemas.py` | `multi_variant: bool = False` field added |
| `backend/app/orchestration/render_pipeline.py` | `_VARIANT_AGGRESSIVE_SUB`, `_VARIANT_STORY_SUB`, `_build_variant_segments()`; variant injection after score cap; story arc guard; variant-aware filename, subtitle, speed; `variant_type` in ranking entry. **HARDENING1:** `scene_quality_score` replaces `retention_score` in `_bal_score` and `_story_score`; small-pool collapse warning added. |
| `backend/static/index.html` | Multi-variant checkbox in editor render settings |
| `backend/static/js/editor-view.js` | `payload.multi_variant` from checkbox |
| `backend/static/js/render-ui.js` | `variantType` in `_rankMap`; variant badge in clip cards |
| `docs/render/PRODUCT_STATE_QUALITY_UP13.md` | This file |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|---|---|
| More than 3 variants | Creator overwhelm; 3 is the right cognitive limit |
| Per-variant max_export_parts | Would create 9+ clips; render explosion |
| Variant-specific audio normalization | Same loudnorm target across all variants is correct |
| Variant-specific CRF/quality | UP11 content-type CRF delta already handles quality; variant shouldn't change codec quality |
| Shared transcription cache across variants | Complex; variants often pick different segments; benefit marginal |
| Variant comparison UI (A/B panel) | R8.2.1 compare mode already works for any two clips |
| Creator preference for which variant "won" | UP12 already tracks download rank; no additional UI needed |
| "Custom variant" (creator-defined weights) | Too complex for UP13; deferred to future |

---

## Manual QA Checklist

### Toggle
- [ ] Editor render settings shows "Multi-variant" checkbox with "Aggressive · Balanced · Story-first" hint
- [ ] Checkbox unchecked → render behaves exactly as before (no regression)
- [ ] Checkbox checked → 3 output files produced

### Output files
- [ ] `{stem}_aggressive.mp4` exists in output dir
- [ ] `{stem}_balanced.mp4` exists in output dir
- [ ] `{stem}_story_first.mp4` exists in output dir
- [ ] No `_part_001.mp4` etc. when multi-variant mode active

### Clip cards
- [ ] 3 clip cards shown in output panel
- [ ] Each card has variant badge: "Aggressive", "Balanced", "Story-first"
- [ ] Preview, Download, Compare buttons all work per card

### Variant correctness
- [ ] Aggressive clip: starts at a strong hook moment (not necessarily chronologically first)
- [ ] Story-first clip: starts later in source video (payoff bias); typically softer feel
- [ ] Balanced clip: best overall score (matches what single render would produce)
- [ ] Log shows `multi_variant_selected` event with 3 variant entries

### Subtitle bias
- [ ] Aggressive clip: check `visual_finish_applied` log — subtitle_style is `viral` (or `gaming` for montage)
- [ ] Story-first clip: subtitle_style is `story` or `clean` (by content type)
- [ ] Balanced clip: subtitle_style matches creator's payload choice (taste-aware)

### Speed bias
- [ ] Aggressive: `variant_playback_speed` in log = base + 0.05 (capped at 1.15)
- [ ] Story-first: `variant_playback_speed` = base − 0.05 (floored at 0.95)
- [ ] Balanced: `variant_playback_speed` = payload.playback_speed unchanged

### Story arc
- [ ] Log does NOT show `story_arc_applied` when multi-variant mode active

### Performance
- [ ] 3-variant render completes in ≤ 1.8× the time of a single-clip render
- [ ] Cancel still works during multi-variant render
- [ ] Resume still works for interrupted multi-variant renders

### Safety
- [ ] Single-variant render (multi_variant=False): zero regression on all UP1A–UP12 behavior
- [ ] No backend errors in queue or concurrent renders
- [ ] `output_ranking` API response includes `variant_type` field for each entry
