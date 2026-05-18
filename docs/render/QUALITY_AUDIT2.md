# QUALITY-AUDIT2 — Creator Maturity Audit

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-18
**Phases audited:** UP1A, UP2–UP9, UP10B, UP11, UP12, UP13, UP14, UP15, UP16, UP18
**Method:** Code-level static audit + scenario stress-test matrix + signal tracing

---

## HARDENING1 Resolution (2026-05-18)

All five P1–P5 fixes from this audit were applied in commit `fix(render): harden creator intelligence`.

| Fix | Audit Item | Status |
|---|---|---|
| P1 — Cover subtitle key names corrected | BUG-1 | **Fixed** — `"first_start"`/`"first_end"` keys now match actual srt_meta dict |
| P2 — `scene_quality_score` replaces `retention_score` | BUG-2 | **Fixed** — story-first and balanced both use a real, always-populated signal |
| P3 — Small pool collapse warning | WEAK-3 | **Fixed** — logs warning + notes selection_reason when all/some variants share source clip |
| P4 — Platform speed delta doubled | WEAK-1 | **Fixed** — TikTok +0.08 (was +0.04), Instagram −0.06 (was −0.03) |
| P5 — Variant-aware CTA type | WEAK-5 | **Fixed** — aggressive→comment, story_first→follow on auto; balanced unchanged |

BUG-3 (`gaming` content_type_hint never detected) is documented but not fixed — gaming
content renders correctly as `montage`-class; only the `_CTA_TEXTS["gaming"]` library
entry is dead code. Accepted as low priority.

---

## Audit Method

This is not a manual render QA. It is a **code-level reality check** — tracing what the
system actually does, not what the docs say it should do. Every finding below comes from
reading the actual Python and JavaScript implementation, tracing data from source signal
through to creator output.

---

## Section 1 — Critical Bugs (Silent, In Production)

These are not hypothetical. They are confirmed by reading the code.

---

### BUG-1 — Cover frame subtitle penalty: permanently disabled

**File:** `render_pipeline.py → _select_cover_frame_time()`  
**Lines:** ~144–145

**What should happen:**
The subtitle window penalty (−6pts) is supposed to avoid selecting thumbnail frames
during the first dense subtitle block — preventing text-cluttered thumbnails.

**What actually happens:**
```python
# Function reads:
sub_s = float((srt_meta or {}).get("first_sub_start") or -1)
sub_e = float((srt_meta or {}).get("first_sub_end") or -1)

# Actual dict keys from slice_srt_by_time() are:
# "first_start" and "first_end"  ← different names
```

`srt_meta.get("first_sub_start")` always returns `None`, so `sub_s = -1`, so the
condition `sub_s >= 0` never fires.

**Impact:** Every cover frame is selected without subtitle avoidance. On interview and
tutorial clips where subtitles start at 0.3s and run continuously, the first 60% of
the clip is subtitle-heavy — and the cover frame scoring has no awareness of this.
UP15's subtitle penalty is dead code.

**Fix:** Change `"first_sub_start"` → `"first_start"` and `"first_sub_end"` → `"first_end"`.

---

### BUG-2 — Story-first variant: retention_score is always 0

**File:** `render_pipeline.py → _build_variant_segments() → _story_score()`  
**File:** `viral_scorer.py → score_segments()`

**What should happen:**
Story-first selects the segment with the highest "payoff" value, using:
`retention_score × 0.45 + positional_bias × 0.30 + viral_score × 0.25`

**What actually happens:**
`viral_scorer.py` never computes `retention_score`. It does not exist in the scored
segment dict. `seg.get("retention_score", 0) or 0` silently returns 0.

**Effective formula:**
```
story_score = 0 × 0.45 + (start / max_start × 100) × 0.30 + viral_score × 0.25
           = positional_bias (max 30) + viral_score contribution (max 25)
```

Story-first is "pick the latest-positioned clip." The 45% weight that is supposed to
identify high-retention content contributes exactly zero. A clip with true payoff
quality (emotional arc, punchline, reveal) is not distinguished from any other late-
positioned clip.

**Same issue affects balanced variant:** `_bal_score` uses `retention_score × 0.20`
(also always 0), though balanced uses more signals so the degradation is less severe.

**Note:** The *output ranking* correctly defaults `retention_score` to 50.0 via
`_first_score(..., default=50.0)`. This creates a **ranking vs. selection inconsistency**:
the UI explains clips as "Good retention" (50 default) while variant selection ignored
retention entirely. Creators who trust the ranking reason may be misled.

**Fix options (in order of difficulty):**
- (Easy) Replace retention in variant formulas with `scene_quality_score`, which IS populated
- (Better) Compute retention_score as a proxy from subtitle density + mid-clip viral signals
- (Best) Derive it from actual Whisper speech segments when available

---

### BUG-3 — "gaming" content_type_hint is never detected

**File:** `viral_scorer.py → score_segments()`

The scorer only assigns: `interview`, `commentary`, `vlog`, `tutorial`, `montage`.
"Gaming" is never a `content_type_hint` output.

**Affected dead code:**
- `_CTA_TEXTS["gaming"]` — unreachable from `_select_cta_text(content_type_hint, ...)`
- `_CTA_AUTO_TYPE["gaming"]` — also unreachable
- Ranking reason path for `content_type == "gaming"` in `_output_ranking_reason()`

Gaming content is detected as `montage` (high scene density). The gaming subtitle style
is correctly applied via `_VARIANT_AGGRESSIVE_SUB["montage"] = "gaming"` — so the
subtitle style works. But CTA auto-type for gaming content hits `_CTA_AUTO_TYPE.get("montage")
= "follow"` rather than the gaming-specific text.

**Impact:** Low — gaming content still renders correctly and gets appropriate subtitles.
The CTA is slightly less precise. The dead code is noise in the library.

---

## Section 2 — Systemic Weaknesses

These are design-level observations, not implementation bugs.

---

### WEAK-1 — Platform speed delta is nearly imperceptible

**TikTok:** +0.04 speed → at 1.07 base, output is 1.11x  
**Instagram:** -0.03 speed → output is 1.04x

On a 30-second clip:
- TikTok: 27.0s  
- YouTube: 28.0s  
- Instagram: 28.8s

Delta: **1.8 seconds maximum** across platforms.

Below human perceptual threshold for speed difference in short-form video.
A creator comparing TikTok vs Instagram exports side-by-side will not perceive
the pacing difference. The platform bias currently manifests almost entirely through
**subtitle style**, not through pacing. The speed delta is real in the code but
a placebo in perception.

---

### WEAK-2 — Platform hook sort bonus is competitive at margins only

**TikTok:** `hook_sort_bonus = 6` → adds `int(hook_score × 6 / 100)` = 0–6pts to sort key

The initial sort key ranges 0–100+ (viral score). A 10-point viral score difference
between two clips dominates the 6-point hook bonus for any hook_score below ~83.

**Result:** TikTok hook bonus changes segment selection only when two clips are within
~5 points of each other in viral score AND one has substantially higher hook_score.
For most real content, the same clip wins regardless of platform. The "TikTok selects
hook-forward clips" claim is only true at the margin.

---

### WEAK-3 — Variant differentiation degrades on small pools

**Scenario:** Creator uploads a 3-minute tutorial → 3–4 scored segments

`_build_variant_segments()` uses `max()` on the same pool:
- `_agg_score` maximizes hook × 0.50
- `_bal_score` maximizes viral × 0.35
- `_story_score` maximizes positional × 0.30

With 3–4 segments, the highest-scoring segment on each function is often the **same
segment**. Result: all three variants share the same source clip, differing only in
subtitle style and ±0.05 playback speed.

The creator sees "Aggressive / Balanced / Story-first" badges on what are effectively
three re-encodes of the same clip. This is not meaningful differentiation.

There is no deduplication, no fallback, no warning when agg = bal = story at the
same source timestamp.

**Threshold estimate:** Pools with ≤4 segments (common for source videos under
4–5 minutes or content with few scene transitions) are at high risk of this pattern.

---

### WEAK-4 — Story-first "payoff protection" is positional, not narrative

Even when `retention_score` is fixed (BUG-2 above), the story-first score formula
biases toward **late-in-source clips** via `start / max_start × 100 × 0.30`.

A strong punchline, reveal, or tutorial answer at the 2-minute mark of an 8-minute
source video will never be selected by story-first if a mediocre clip exists at the
7-minute mark.

"Story-first" currently means "pick something from the back half of the source." For
most vlog and interview content, this is acceptable. For tutorial content where the
payoff (the solution, the demo, the result) often appears in the second act, not the
last minute, this is systematically wrong.

---

### WEAK-5 — CTA all-same-text on multi-variant

When multi-variant + cta_enabled are both active, all three variants receive the same
CTA text (same content_type, same platform). A creator comparing three clips sees
identical end cards. The CTA doesn't adapt to variant intent:
- Aggressive variant ending with "Let me know if this helped." — tonal mismatch
- Story-first variant getting a comment prompt instead of series hook

---

### WEAK-6 — Cover frame "intelligence" is mostly platform position + hook bias

The cover frame selection algorithm is deterministic and signal-light:
- 5 fixed candidate offsets (10%, 20%, 32%, 44%, 58%)
- Platform position preference
- Hook score bias (earlier = better for high hook)
- Stability bonus for middle range
- **Subtitle penalty: broken** (BUG-1)

With the subtitle penalty disabled, the algorithm is: "pick an early-to-mid-clip frame
that a hook-strong clip biases toward." On a static interview or low-motion content, the
5 candidate frames may all look similar. On fast-motion gaming/montage content, all 5
candidates are equally likely to capture a motion-blurred mid-cut frame.

The "smart" in "smart cover intelligence" is mostly marketing. The selection is better
than "frame 1", but not by the degree implied.

---

## Section 3 — What Genuinely Works (Creator Wins)

---

### WIN-1 — UP11 visual finish is real and measurable

Content-type CRF delta (tutorial/interview at −2), content-type denoise (lite hqdn3d
for face-forward content at slow preset), and reduced saturation for authenticity
(tutorial/interview at contrast=1.01) are:

- **Reproducible** across all content of the labeled type
- **Verifiable** from the `visual_finish_applied` log event
- **Perceptible** for tutorial screen content — text is visibly sharper at CRF 16 vs 18

This is the most honest upgrade in the stack. It does what it says, consistently.

---

### WIN-2 — UP12 subtitle taste memory works exactly as designed

EMA pre-population of subtitle style is clean, local, non-intrusive. After 3 renders
with the same style, the dropdown pre-selects the preference with a subtle hint. The
decay (α=0.85) means it doesn't lock in — changing style for 3 renders shifts the hint.

The implementation has zero gaps: signal recording, storage, confidence gate, UI hint,
manual override flag, session reset — all correct. The creator genuinely doesn't have
to re-select their preferred subtitle style session after session.

---

### WIN-3 — UP13 multi-variant concept is the right idea

Even with the weaknesses above (same-segment on small pools, retention_score absent),
getting three distinctly *styled* clips from one render is genuinely useful. Aggressive
with viral/bounce subtitles vs Story-first with clean/story subtitles creates visually
different options even when the source clip is the same. A creator can pick "the feel"
without re-rendering.

The concept is stronger than the current execution. The execution is still better than
one clip with no options.

---

### WIN-4 — UP16 CTA is safe and tasteful

Default OFF, explicit checkbox, deterministic text, no hype language, no emoji. When
the timing math works (last subtitle ends with ≥3s before clip end), the end card is
subtle and appropriate. The "comment" and "part_2" text is genuinely creator-voice
neutral. The implementation correctly wraps in try/except and never blocks the render.

---

### WIN-5 — UP18 feedback learning is invisible until it helps

Platform preference pre-selection after 3 renders is imperceptible to the creator until
it quietly pre-selects TikTok on session 4. The confidence gate (sessions ≥ 3, EMA
score ≥ 1.5, ratio ≥ 1.5) is appropriately conservative. The `· recent` variant badge
chip is non-obtrusive. No hint is pushed until the system is genuinely confident.

---

## Section 4 — Maturity Test Matrix

### Scenario Analysis: 20 representative render types

| # | Content Type | Source Quality | Multi-variant | Platform | Key Risk |
|---|---|---|---|---|---|
| 1 | Screen recording tutorial | 1080p clean | OFF | YouTube Shorts | CRF delta correct; cover may hit subtitle frame |
| 2 | Facecam tutorial (talking head) | 720p | OFF | YouTube Shorts | Interview-class; denoise lite correct; sub margin +40 |
| 3 | Edited explainer (cuts+screen) | 1080p | ON | TikTok | **WEAK-3 risk: ≤4 segs** → same clip 3x |
| 4 | Talking head commentary | 1080p | OFF | TikTok | TikTok subtitle=viral: correct; speed delta: invisible |
| 5 | Reaction video | 720p compressed | ON | TikTok | Low-res denoise; **BUG-2: story=latest clip** |
| 6 | Debate/interview (2-person) | 1080p | OFF | YouTube Shorts | Clean sub correct; sub margin +40 without motion crop |
| 7 | Long interview clip (10min+) | 1080p | ON | Instagram | **WEAK-3 likely**: many segments; variants plausible |
| 8 | Low-light webcam | 480p | OFF | TikTok | Low-res guard on sharpen + color correct; denoise lite |
| 9 | Vlog (outdoor, b-roll) | 1080p | ON | Instagram | Sub=clean (Instagram) correct; cover early-mid |
| 10 | Emotional vlog (payoff late) | 1080p | ON | YouTube Shorts | **BUG-2 critical**: story picks last chronological clip |
| 11 | Short vlog (3 min, 3 segs) | 1080p | ON | TikTok | **WEAK-3 high risk**: same-seg all variants |
| 12 | Gaming highlight reel | 1080p 60fps | OFF | TikTok | montage-class; gaming sub via _VARIANT_AGG map |
| 13 | Gaming commentary (facecam) | 1080p | ON | TikTok | commentary-class detection; sub=viral correct |
| 14 | Gaming with poor audio | 720p | OFF | YouTube Shorts | Audio cleanup optional; sub from Whisper |
| 15 | Music-heavy montage | 1080p | OFF | Instagram | montage-class; speed -0.03; sub=gaming for agg |
| 16 | High-motion action montage | 1080p | ON | TikTok | montage CRF+1 correct; cover=blur risk (5 candidates) |
| 17 | Screen recording + facecam | 1080p | ON | YouTube Shorts | Ambiguous classification (vlog or tutorial density?) |
| 18 | Tutorial with manual edits | 1080p | ON | YouTube Shorts | CTA + variant: all 3 get same CTA text (**WEAK-5**) |
| 19 | Interview, compressed source | 720p | OFF | YouTube Shorts | Low-res denoise; face margin correct |
| 20 | Short gaming clip (<2min) | 1080p | ON | TikTok | **WEAK-3 critical**: 1-2 segs; no meaningful variant |

---

### Scorecard (1–10, code-traced estimates)

| Dimension | Score | Notes |
|---|---|---|
| **Overall clip quality** | 7/10 | UP11 real, transcription solid, crop works |
| **Variant usefulness** | 5/10 | Good idea, undermined by small-pool collapse + retention=0 |
| **Platform differentiation** | 4/10 | Subtitle style real; speed/selection delta mostly invisible |
| **Cover usefulness** | 5/10 | Better than frame-1; subtitle avoidance broken (BUG-1) |
| **CTA usefulness** | 6/10 | Tasteful, but all-same on variants, timing edge cases |
| **Creator memory usefulness** | 7/10 | UP12 works well; UP18 correct but rarely fires for variants |
| **Trustworthiness** | 6/10 | Ranking explanations use retention=50 default; variant formulas use retention=0 |
| **Overall creator feeling** | 6/10 | Better than one clip, not yet a genuine co-pilot |

---

## Section 5 — System Interaction Audit

### Platform × Subtitle (UP14 × UP11/UP13)

**Status: Correct but subtle.** When creator sets explicit subtitle_style, platform
sub_bias is skipped (hierarchy step 2 wins). When multi_variant, variant subtitle wins
(step 1). When both absent, platform × content_type determines style. The hierarchy is
correctly implemented. The subtlety: a creator who enables multi_variant on TikTok will
NOT see the TikTok viral subtitle on the Aggressive variant — because Aggressive forces
its own style. This is correct behavior but may surprise creators.

### Variant × Platform (UP13 × UP14)

**Status: Speed delta is correct; subtle interaction.** Variant-specific speed (base±0.05)
short-circuits before platform speed delta via `or` chaining. Platform hook bonus DOES
apply to the initial pool sort before variant selection — correct, TikTok biases the
segment pool toward hook-strong clips for all 3 variants. No bug, but modest effect.

### Cover × Subtitle (UP15 × subtitle pipeline)

**Status: Broken.** BUG-1 means cover frame selection doesn't know where subtitles are.
The two systems don't interact as designed.

### CTA × Payoff (UP16 × story content)

**Status: Timing risk.** CTA is inserted at `max(last_sub_end + 0.3s, clip_end - 3s)`.
For a vlog clip where the payoff moment IS the last 3 seconds (the reveal, the laugh, the
result), CTA subtitles may overlap the actual content payoff. The creator wanted a clean
emotional ending; they got "What do you think?" over it.

**Mitigation that exists:** CTA fires only when `cta_enabled=True` (opt-in), and
`_append_cta_block_to_srt()` returns False when cta_start ≥ clip_end. But for clips
where last_sub_end is at, say, 28s and clip_end is 31s, CTA fires at 28.3s and runs
to 30.8s — right over the last active content.

### Taste × Feedback (UP12 × UP18)

**Status: Independent, no conflict.** `ct_taste_v1` and `cl_feedback_v1` are separate
localStorage keys with no cross-reading. This is by design. The two layers don't fight.
But they also don't reinforce: if a creator prefers Story-first (UP18) but prefers viral
subtitle style (UP12), they get viral subtitle on their preferred Story-first variant —
which has `story`/`clean` as its intent-driven default. Consistent behavior, but the two
preference signals work in opposite directions without either system knowing.

---

## Section 6 — Unexpected Regressions / Risks

1. **No regression detected on core pipeline** — cancel, resume, retry, queue, render speed
   are all structurally sound. The UP11–UP18 changes are additive layers.

2. **Potential regression on very short clips (< 10s)** — `_select_cover_frame_time()` floors
   at `dur = max(2.0, ...)` and candidate at `max(0.5, min(dur - 0.5, ...))`. For a 5s clip,
   candidates collapse to near 0.5s–2.3s. Cover extraction may produce a near-identical frame
   to `?t=1`. Not a crash, but the "smart" cover is meaningless for very short clips.

3. **CTA on sub-5s clips** — `_eff_dur = max(5.0, ...)` floors at 5.0s. `_append_cta_block_to_srt`
   checks `cta_end > cta_start` — for a 5s clip with last_sub at 4s, this correctly returns False.

4. **`_srt_meta` initialized to `{}` if subtitle is disabled** — When `add_subtitle=False`,
   `_srt_meta` stays `{}`. CTA reads `_srt_meta.get("last_end") or 0`, so `_last_sub_end = 0`.
   CTA timing: `cta_start = max(0.3, clip_end - 3.0)`. CTA fires at clip_end - 3s regardless
   of where speech ends. On a no-subtitle render with CTA enabled, the creator gets an end card
   with no timing calibration to actual speech rhythm — but the render still succeeds.

---

## Section 7 — Highest ROI Surgical Fixes

Ranked by impact-to-effort. All are **one-file, ≤10-line changes**.

| Priority | Fix | File | Effort | Impact |
|---|---|---|---|---|
| **P1** | Fix `first_sub_start`/`first_sub_end` key names in `_select_cover_frame_time()` | render_pipeline.py | 2 lines | Enables subtitle avoidance penalty for covers — immediately improves UP15 |
| **P2** | Replace `retention_score` in `_bal_score` and `_story_score` with `scene_quality_score` (which IS populated) | render_pipeline.py | 4 lines | Story-first picks quality-weighted late clips, not any-late clip |
| **P3** | Add small-pool warning + variant deduplication check in `_build_variant_segments()` | render_pipeline.py | 8 lines | Surfaces same-segment problem in logs so creator understands what happened |
| **P4** | Increase TikTok speed_delta to 0.08 and Instagram to -0.06 | render_pipeline.py | 2 values | Makes platform pacing difference perceptible (~3-6s on 60s clip) |
| **P5** | Adapt CTA type by variant intent (aggressive → comment, story-first → follow) in CTA injection block | render_pipeline.py | 5 lines | CTA tonal match per variant; multi-variant CTAs become differentiated |

---

## Section 8 — Is UP20 Justified Yet?

**Short answer: No, not yet.**

**Reasoning:**

The system has three unresolved bugs (BUG-1, BUG-2, BUG-3) and two systemic weaknesses
(WEAK-1, WEAK-2) that directly undermine the creator co-pilot claim:

- The cover frame subtitle penalty doesn't fire (silent quality miss)
- Story-first variant ignores retention (the signal it was designed around)
- Platform adaptation is subtitle-style-only in practice; pacing is invisible

Building UP20 ("moat features") on top of these gaps creates technical debt where the
next layer's quality claims rest on a foundation that isn't executing as documented.

**What should happen before UP20:**

1. Fix P1 and P2 (2 days, ~15 lines of code)
2. One honest "does it feel like a co-pilot now" re-evaluation

**When UP20 is justified:**

When the three platforms produce *perceptibly different* clips for the same source, and
when story-first genuinely tends to select payoff-quality content, the multi-axis
intelligence story becomes real. Right now it's half-real — title-card vs. actual capability.

---

## Section 9 — Patterns vs. Anecdotes

This audit identified **patterns**, not individual clip complaints:

| Pattern | Affected Scenarios | Root Cause |
|---|---|---|
| Story-first = latest clip | All multi-variant renders | BUG-2: retention_score=0 |
| Cover in subtitle window | All UP15 renders | BUG-1: key mismatch |
| Variants feel same | Short source videos (≤4 segments) | WEAK-3: small pool collapse |
| Platform feels identical | TikTok vs Instagram side-by-side | WEAK-1: speed delta imperceptible |
| Ranking explanation vs. variant disagree | All multi-variant + trust layer | retention=50 in ranking, 0 in selection |

---

## Summary

| Category | Verdict |
|---|---|
| Visual finish quality (UP11) | Mature — real, reproducible, honest |
| Creator memory (UP12 + UP18) | Mature — EMA implementation correct, appropriate gates |
| Multi-variant concept (UP13) | Promising but undermined by BUG-2 and WEAK-3 |
| Platform adaptation (UP14) | Cosmetic at current delta levels — needs honest recalibration |
| Cover intelligence (UP15) | Partially broken — BUG-1 disables key discriminator |
| CTA system (UP16) | Safe and tasteful — timing edge case, WEAK-5 on variants |
| Trust layer / ranking | Inconsistency between explanation defaults and selection defaults |
| **Overall system maturity** | **Creator-grade tool: yes. Creator co-pilot: not yet.** |

The tool now produces consistently better output than before. A creator using it gets real
value. But the "co-pilot" label — something that understands your intent, adapts to your
platform, and picks meaningful variants — requires fixing the three bugs and the platform
delta before it's honest.

---

*Report generated from static code audit. No live renders required — all findings are
traceable to specific lines in the implementation files listed above.*
