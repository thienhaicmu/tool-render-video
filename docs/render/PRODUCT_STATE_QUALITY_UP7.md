# PRODUCT STATE — QUALITY-UP7: Humanized Narration

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): humanized narration`
**Status:** Shipped

---

## Summary

Two targeted layers that eliminate the primary "robotic AI voice" signals from
edge_tts output — without changing the TTS provider, without voice cloning,
and without expensive inference.

1. **Content-type voice profiles** — content-aware rate adjustment. Tutorial
   voices slow down for clarity; commentary speeds up for energy; story softens
   pace. Fires only when the creator has not set a custom voice rate.

2. **Text humanization pass** — pre-TTS text preprocessing that adds natural
   pause signals (ellipsis after emphatic statements, comma-based breath points
   in long sentences, colon-to-pause conversion for tutorial content). Produces
   more natural prosody from the same neural TTS model.

---

## Root Cause

edge_tts (Microsoft Azure Neural TTS) synthesizes high-quality speech but its
prosody depends heavily on input text structure. Without explicit pause signals:
- Long sentences are read at uniform pace without breathing room
- Short emphatic statements (`"This is incredible!"`) have no post-statement pause
- All content types run at the same rate regardless of context
- Tutorial content reads at commentary pace (too fast for instruction following)

These are all text-level fixable without any provider change.

---

## Part A — Content-Type Voice Profiles

**File:** `backend/app/services/tts_service.py`

Table `_CONTENT_TYPE_VOICE_PROFILES`:

| content_type | rate_nudge | pause_style | Rationale |
|-------------|-----------|-------------|-----------|
| `commentary` | `+10%` | `light` | Energetic, fast-paced, minimal pause insertion |
| `vlog` | `+0%` | `normal` | Natural neutral baseline |
| `story` | `-3%` | `normal` | Softer pacing, slightly slower delivery |
| `tutorial` | `-8%` | `deliberate` | Clear and steady; slower aids instruction recall |
| `interview` | `-5%` | `deliberate` | Conversational clarity; phrase breaks on long answers |
| `montage` | `+12%` | `light` | High-energy; minimal pause insertion |
| `gaming` | `+12%` | `light` | Same as montage |

**Override safety:** `_effective_rate_for(creator_rate, content_type)` —
if `creator_rate` is non-empty and not `"+0%"` (the system default), the creator's
rate is used exactly. The content-type nudge fires only on the default.

---

## Part B — Text Humanization Pass

**File:** `backend/app/services/tts_service.py`

`humanize_narration_text(text, pause_style)` — pure Python, no dependencies,
deterministic. Three pause styles, applied per content-type.

### Transformation 1: Long-sentence phrase breaks

Sentences longer than the threshold get a comma inserted before the first
natural conjunction that appears after a minimum number of words.

| pause_style | long_threshold | min_before |
|-------------|---------------|------------|
| `light` | 20 words | 12 words |
| `normal` | 15 words | 9 words |
| `deliberate` | 11 words | 7 words |

Conjunctions: `and`, `but`, `so`, `because`, `while`, `when`, `although`,
`however`, `therefore`.

If the sentence already has a comma before the conjunction, no change.
If no qualifying conjunction is found, no change.

**Example (tutorial — deliberate):**
```
Before: "In this section we will learn about React hooks and how they can
         simplify your component logic while keeping code readable."
After:  "In this section we will learn about React hooks, and how they can
         simplify your component logic while keeping code readable."
```

### Transformation 2: Colon-to-pause (deliberate only)

`"Label: explanation"` → `"Label... explanation"` where the label is 2–19
characters. The ellipsis replaces the colon, signaling a deliberate pause
before the explanation.

Pattern: `^([A-Za-z][^:]{1,18}):\s+(.+)$`

**Example (tutorial):**
```
Before: "Step one: add two cups of water to the pot."
After:  "Step one... add two cups of water to the pot."
```

### Transformation 3: Emphatic pause (normal + deliberate)

Short sentences (≤ 7 words) ending with `!` get `...` appended to signal
a dramatic pause before the next thought.

**Example (vlog/commentary):**
```
Before: "This is incredible! The results speak for themselves."
After:  "This is incredible!... The results speak for themselves."
```

Only on short declarations — avoids over-dramatizing longer emphatic sentences.

---

## Part C — Sentence Splitting

`_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")` splits the input text
into individual sentences before processing. Processed sentences are joined
back with a single space.

False splits on abbreviations (e.g., `"Mr. Smith"`) are harmless — the
split fragments are too short to trigger any transformation, and they rejoin
correctly.

---

## Part D — Call Sites and Content-Type Propagation

**File:** `backend/app/orchestration/render_pipeline.py`

Three `generate_narration_mp3` call sites:

| Path | content_type passed |
|------|---------------------|
| Manual voice (`voice_source == "manual"`) | `"vlog"` — no segment context available at this point in the pipeline; neutral safe default |
| Per-part subtitle TTS (`voice_source == "subtitle"`) | `seg.get("content_type_hint") or "vlog"` |
| Per-part translated subtitle TTS (`voice_source == "translated_subtitle"`) | `seg.get("content_type_hint") or "vlog"` |

For per-part TTS, `seg` is the scored segment dict inside `_process_one_part(idx, seg)`,
which has full `content_type_hint` context from QUALITY-UP2.

---

## Part E — Observability

Log line on every TTS call:
```
tts_humanized job_id=abc123 content_type=tutorial rate=-8% pause_style=deliberate
```

Tells you: what content type was detected, what rate was applied, which
humanization mode ran.

---

## Part F — Failure Safety

`humanize_narration_text` is pure Python with no I/O, no network calls, and
no external dependencies. Any exception in the humanization layer is caught by
the existing `generate_narration_mp3` try/except, which logs
`tts_generation_failed` and raises `RuntimeError`. The caller's existing
fallback (render continues without narration) is fully preserved.

The text transformation functions return the original `sent` unchanged on any
code path that does not find a match — no mutation occurs on mismatch.

---

## Parameter Comparison

| | Before | After (tutorial) | After (commentary) | After (vlog) |
|--|--------|-----------------|-------------------|-------------|
| Rate | `+0%` (uniform) | `-8%` (clearer) | `+10%` (energetic) | `+0%` (unchanged) |
| Long-sentence break | None | At 11+ words | At 20+ words | At 15+ words |
| Colon pause | None | Yes | No | No |
| Emphatic pause | None | Yes (`!` ≤ 7w) | No | Yes (`!` ≤ 7w) |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| SSML injection (`<break>`, `<emphasis>`) | edge_tts `Communicate` class does not expose SSML input — text level is the safe layer |
| Per-sentence rate variation | Requires splitting into multiple `Communicate` calls and concatenating audio — architecture change; QUALITY-UP8 scope |
| Silence-concatenation audio assembly | Would allow precise ms-level pauses but requires FFmpeg per-sentence — out of scope |
| `+12%` cap | No cap needed: Azure Neural TTS handles rate gracefully up to `+50%` without quality collapse |
| Pitch variation | edge_tts `pitch` parameter available but no meaningful content-type mapping exists |
| Dominant content type for manual voice | Manual TTS fires before segment scoring; requires pipeline reorder or payload field — deferred |
| `"auto"` rate sentinel on payload | Would allow explicit "use content-type default" signal from frontend — requires API change |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/tts_service.py` | `import re`; `_CONTENT_TYPE_VOICE_PROFILES`; `_DEFAULT_VOICE_RATE`; `_effective_rate_for`; `_break_sentence_if_long`; `humanize_narration_text`; `content_type` param + humanization in `generate_narration_mp3` |
| `backend/app/orchestration/render_pipeline.py` | `content_type=` added to all 3 `generate_narration_mp3` call sites |
| `docs/render/PRODUCT_STATE_QUALITY_UP7.md` | This file |

---

## Manual QA Checklist

### Commentary job
- [ ] Log shows `tts_humanized content_type=commentary rate=+10% pause_style=light`
- [ ] Narration feels noticeably more energetic than neutral vlog voice
- [ ] Creator with custom `voice_rate="+5%"` → log shows `rate=+5%` (not `+10%`)

### Tutorial job
- [ ] Log shows `tts_humanized content_type=tutorial rate=-8% pause_style=deliberate`
- [ ] Narration feels slower, clearer — easier to follow step by step
- [ ] Sentences with `"Step N: explanation"` pattern deliver a natural pause at the colon

### Vlog / Story job
- [ ] Log shows `rate=+0% pause_style=normal` (vlog) or `rate=-3% pause_style=normal` (story)
- [ ] Long sentences (>15 words) with natural conjunctions have a slight breath pause

### Montage / Gaming job
- [ ] Log shows `rate=+12% pause_style=light`
- [ ] Narration is fast and energetic — no heavy pause insertion

### Manual voice (voice_source=manual)
- [ ] Log shows `content_type=vlog` (neutral fallback)
- [ ] Render completes without error
- [ ] Custom `voice_rate` on payload is respected exactly

### Timing / sync regression
- [ ] Subtitle timing unchanged across all content types
- [ ] No subtitle drift after render with humanized narration
- [ ] No audio overlap between narration and source

### Failure path
- [ ] Simulate TTS failure — render continues without narration (existing behavior preserved)
- [ ] No crash, no broken export on any path

### Safety regression
- [ ] All content types render without backend errors
- [ ] Cancel still works during TTS phase
- [ ] No new console errors
