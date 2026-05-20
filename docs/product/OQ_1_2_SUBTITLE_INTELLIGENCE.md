# OQ-1.2 — Subtitle Intelligence Layer
## CapCut Readability Foundation

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** INTELLIGENCE ONLY — no style changes, no animation changes, no preset changes

---

## 1. Current Subtitle Audit

### Segmentation logic (traced)

**Segment-level path (`highlight_per_word=False`):**
- `_write_segment_level_srt()` (subtitle_engine.py:391) — writes Whisper segments verbatim.
- No word-count limit. Whisper often produces 8-15 word segments at 2-4s duration.
- **No splitting logic.** One SRT block = one Whisper segment = whatever Whisper decides.

**Word-level path (`highlight_per_word=True`):**
- `_write_word_level_srt()` (subtitle_engine.py:328) — one block per word with normalization.
- Same path via `_write_fw_srt()` for faster-whisper.
- Merges ultra-short words (<0.11s) into pairs. No phrase grouping.

### Line-break logic (traced)

| Function | Where | What it does | Problem |
|---|---|---|---|
| `_break_by_visual_width()` | subtitle_engine.py:692 | Split at visual-width midpoint when text exceeds `max_em` | No phrase awareness — "I think you\nshould" |
| `_semantic_wrap_block()` | subtitle_engine.py:1536 | Orphan/widow-aware midpoint wrap | Only changes line display, does NOT create new SRT blocks |
| `apply_market_line_break_to_srt()` | subtitle_engine.py:1079 | Max words/line from market policy (US=4, EU=6, JP=3) | Market-optional — only fires when `_mv_cfg` is set |

### Caption density behavior

- **No density control in the core pipeline.** The market line-break policy sets word-count limits but only activates when `market_payload` is provided — which most renders do not use.
- Segment-level blocks can contain 10-15 words with 2.5-4s display time → 3.5-6 words/second → too dense for comfortable reading.
- No minimum display time per block. A 3-word block with 0.4s timing disappears before it can be read.

### Current timing behavior

- Segment-level: raw Whisper timestamps, no extension, no smoothing.
- `apply_market_line_break_to_srt()` has timing extension (start -0.10s, end +0.12/0.20s) but market-optional.
- No gap-filling. 20-50ms gaps between consecutive blocks cause flicker.
- No minimum display time enforcement anywhere.

### Subtitle renderer constraints

| Constraint | Value | Evidence |
|---|---|---|
| ASS WrapStyle | 0 (auto-wrap) | subtitle_engine.py:807 |
| Max lines enforced | 2 (via `_break_by_visual_width max_lines=2`) | subtitle_engine.py:692 |
| Line-width limit | `preset.wrap_max_em` (viral=13em, clean=18em, story=19em) | _PRESETS table |
| Bounce animation | Per SRT block, word-level only | BOUNCE_FX at subtitle_engine.py:406 |
| ASS escape | `_ass_escape_text()` handles braces, newlines, HL markers | subtitle_engine.py:641 |

---

## 2. Problems Discovered

| # | Problem | Severity | Evidence |
|---|---|---|---|
| P1 | Segment-level SRT has no word-count or reading-speed limit | CRITICAL | `_write_segment_level_srt()` line 391 — verbatim Whisper segments |
| P2 | Line breaks are purely visual-width-based — no phrase awareness | HIGH | `_break_by_visual_width()` line 692 — midpoint only |
| P3 | No minimum display time per block | HIGH | Absent from all write/slice functions |
| P4 | No gap-filling between consecutive blocks | MEDIUM | 20-50ms gaps cause flicker |
| P5 | Word-count limit only fires with market_payload (optional) | MEDIUM | `apply_market_line_break_to_srt()` gated on `_mv_cfg` |
| P6 | Fixed `words_per_group=4` in karaoke mode | LOW | `srt_to_ass_karaoke()` line 868 |

---

## 3. Current Segmentation Weaknesses

### Problem 1: Wall-of-text from Whisper
Whisper typically produces segments like:
```
1
00:00:02,340 --> 00:00:05,820
I think you should definitely try this approach because it works really well
```
That is 14 words in 3.48s = 4.0 words/second. A comfortable reading speed for TikTok/short-form is ~2.5-3.0 words/second. This block is unreadable — by the time the viewer reads "because", the subtitle is already gone.

### Problem 2: Unnatural line breaks
`_break_by_visual_width()` finds the visual midpoint and inserts a newline there. For:
```
"I think you should do this"
```
midpoint split produces `"I think you\nshould do this"` — breaking after "you" which reads awkwardly.

A phrase-aware split would give `"I think\nyou should do this"` (split at the natural subject/predicate boundary) or better: split into two blocks.

### Problem 3: Too-short blocks flash and disappear
Whisper sometimes produces short 0.3-0.5s segments (at pauses, fillers). These are technically valid but create a strobe effect in the rendered subtitle.

---

## 4. Intelligence Architecture

### OQ-1.2 pass: `resegment_srt_for_readability()`

A new post-processing function operating on the per-clip SRT (after `slice_srt_by_time()`, before market/emphasis passes). Does NOT modify the transcript cache.

**Target:** segment-level SRT only (`avg_words_per_block > 1.5`). Word-level SRT returns immediately — timing there is handled by the bounce/karaoke renderer.

**Pipeline position:**
```
slice_srt_by_time() → srt_part
  ↓
[NEW] resegment_srt_for_readability(srt_part)     ← OQ-1.2
  ↓
apply_market_line_break_to_srt()    (market-optional)
  ↓
apply_hook_subtitle_format()
  ↓
subtitle_emphasis_pass()
  ↓
srt_to_ass_bounce() / srt_to_ass_karaoke()
```

### Why per-clip (not in cache)?

The transcript cache stores raw Whisper output (source truth). Intelligence re-segmentation is clip-specific (different clips from the same video may have different durations and timing needs). Running intelligence per-clip keeps the cache clean and avoids cache invalidation.

---

## 5. Line-Breaking Strategy

### Phrase split priorities (in order)

1. **Punctuation pause** — split after a word ending in `,;:—–`. These mark natural clause boundaries in speech.
2. **Clause starter** — split before conjunctions/connectives (`and, but, because, when, that, which, so, however, nhưng, và`...). These mark the start of a new clause.
3. **Visual-weight midpoint** — fallback to `_approx_visual_width()` midpoint (same as existing `_semantic_wrap_block()`).

### Example transforms

**Before OQ-1.2 (raw Whisper):**
```
"I think you should definitely try this because it works really well"
```
**After OQ-1.2 (semantic split):**
```
Block 1: "I think you should definitely try this"
Block 2: "because it works really well"
```
Split at clause starter "because" — natural reading pause.

**Before:**
```
"You're going to see the results and it's going to blow your mind"
```
**After:**
```
Block 1: "You're going to see the results"
Block 2: "and it's going to blow your mind"
```
Split before conjunction "and".

---

## 6. Reading-Speed Rules

| Parameter | Value | Env override |
|---|---|---|
| Max words per block | 7 | `SUBTITLE_MAX_WORDS` |
| Max words/second (hard cap) | 3.8 | `SUBTITLE_MAX_WPS` |
| Min display time per block | 0.7s | — |
| Gap-fill threshold | 0.04s | — |

**Density check:** A block is flagged for splitting when `words > max_words OR words/duration > max_wps`.

**Timing redistribution:** When splitting one block into N sub-blocks, timing is redistributed proportionally to word count. Each sub-block is guaranteed at least `min_display_sec`.

**Minimum display enforcement:** Blocks shorter than `min_display_sec` are extended. The extension is clamped to avoid overlapping the next block.

---

## 7. Timing Strategy

### Gap-fill pass
After all splitting, a gap-fill pass scans consecutive block pairs. If the gap between `blocks[i].end` and `blocks[i+1].start` is ≤ 0.04s, the previous block is extended to fill it. This eliminates subtitle flicker from Whisper boundary noise.

### Clamp pass
After gap-fill, a safety pass ensures:
- No block extends past its successor's start
- No block has `end ≤ start` (minimum 0.1s if this would occur)

### Timing invariants preserved
- `slice_srt_by_time()` rebasing is already applied — the intelligence pass operates on rebased (0-relative) timing.
- Speed-scale has already been applied — no double-scale.
- CTA timestamps (added AFTER emphasis pass) are not affected.

---

## 8. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Oversplit: short speech → too many tiny blocks | Low | max_wps cap only triggers on genuinely dense blocks; min_display_sec=0.7s prevents micro-blocks |
| Split creates overlap with next block | None | Clamp pass enforces no-overlap |
| Word-level SRT incorrectly processed | None | Explicit word-level detection (avg_words ≤ 1.5) returns immediately |
| Vietnamese text split at wrong point | Low | Clause starters include Vietnamese connectives; midpoint fallback is language-agnostic |
| Resume-path double-processing | None | Gated on `_srt_source_is_fresh` — only fires on fresh slice |
| Existing market/emphasis/hook passes break | None | Intelligence fires first in chain; all downstream passes operate on shorter, better blocks |
| transcript cache modified | None | Intelligence operates only on per-clip SRT, never on the full-video cache |
| Any subtitle preset visually changed | None | Only block timing and text chunking change; all ASS styling passes are unchanged |
| Karaoke words_per_group broken | None | Word-level SRT is skipped; karaoke grouping is unaffected |
| ASS render output broken | None | Output is a valid SRT with same format — only blocks are different |
| Scoring / viral score affected | Negligible | `speech_density_score` uses the full transcript text, not per-block timing |

---

## 9. Compatibility Impact

| Component | Impact |
|---|---|
| Subtitle styles / presets | None — styling unchanged |
| ASS format | None — same SRT → ASS pipeline |
| Transcript cache | None — not touched |
| Render queue / multi-render | None — stateless per-clip transform |
| S1 AI orchestrator | None |
| Market line-break pass | Improved input — shorter blocks are easier to wrap |
| Hook format pass | Improved input — first block is shorter, hook formatting more effective |
| Emphasis pass | Improved input — semantic_wrap_block less likely to need splitting |
| Scoring | Negligible — speech_density_score uses full text |

---

## 10. Manual Verification Checklist

```
[ ] Short talking-head video — English — segment-level SRT
[ ] Long podcast (>5min) — English — large block splitting observed in log
[ ] Fast speaker — high wps content — intelligence splits triggered
[ ] Slow speaker — low wps content — no unnecessary splits
[ ] Vietnamese speech — character boundaries preserved, midpoint fallback
[ ] Mixed VN/EN speech — language detection irrelevant (timing-based split)
[ ] Subtitle readability improved — shorter blocks, natural phrase boundaries
[ ] No subtitle overflow — visual width unchanged (no new long lines created)
[ ] No wall-of-text — max_words=7 enforced on long Whisper segments
[ ] No timing regression — all blocks have valid start < end
[ ] Existing subtitle presets still render — ASS output format unchanged
[ ] ASS generation stable — srt_to_ass_bounce/karaoke unchanged
[ ] Word-level mode untouched — highlight_per_word=True SRT unchanged
[ ] Multi-render stable — intelligence fires per-clip, no shared state
[ ] Log shows subtitle_intel_resegment entries
[ ] Resume path not re-processed — _srt_source_is_fresh gate works
```

---

## 11. Files Modified

| File | Change |
|---|---|
| `backend/app/services/subtitle_engine.py` | Add `_find_phrase_split()`, `_split_block_semantic()`, `resegment_srt_for_readability()`. Add `_INTEL_*` constants. |
| `backend/app/orchestration/render_pipeline.py` | Import `resegment_srt_for_readability`. Add intelligence pass call after `slice_srt_by_time()`. |

---

## 12. Commit Hash

*(to be filled)*

---

## 13. Push Confirmation

*(to be filled)*
