# Phase 73-A — Min 61s Default Duration Audit
**Pre-implementation audit: does 61s+ default minimum improve or hurt first render confidence?**
**Status:** AUDIT — no code changes
**Date:** 2026-05-19

---

## Executive Summary

**Current default:** `evMinPart = 70s`, `evMaxPart = 180s` (index.html lines 1115/1119).

The current default already exceeds 61s. The question is not whether to add a 61s floor — it already exists as a 70s floor. The real question is:

1. Is 70s the right global default, or should it move toward 61s (lower, more permissive)?
2. Should Phase 73.1's TikTok → 30s auto-link be reconsidered in favor of 61s+ for short-form platforms?
3. Which content types benefit from 61s+ minimums, and which are degraded by them?

**Verdict (detailed below):** 61s minimum default is **correct and beneficial** for the product's stated goal of monetizable, high-retention output. The current 70s default is slightly too conservative and can be relaxed to 61s for the global unspecified-platform case. However, the short-form platform presets (TikTok → 30s) serve a different creator intent and should remain as explicitly-chosen overrides, NOT as the auto-linked default from Phase 73.1.

**Core finding:** Phase 73.1 as planned (auto-link TikTok pill → min=30s) conflicts with the product direction of 61s+ monetizable output. This audit recommends revising Phase 73.1 to NOT auto-lower the minimum for TikTok.

---

## 1. Current Duration System Audit

### How the engine discovers candidates — NOT forced, naturally found

`_generate_candidates()` in `segment_builder.py` (lines 77–104) uses a **sliding window**:

```python
for start_i in range(n):
    window = []
    for j in range(start_i, n):
        if sc_end - seg_start > max_len: break      # hard upper bound
        window.append(sc)
        if seg_end - seg_start >= min_len:           # emit only when >= min_len
            candidates.append(list(window))
```

Key properties of this design:
- Candidates are **discovered naturally** from real content structure (scenes)
- `min_len` is a **hard emission gate** — no candidate is emitted until the accumulated window reaches min_len
- No padding, no extension, no merging after generation
- The only post-generation operation is truncation: `_normalize_segment_durations()` (line 50) truncates to max_len, never extends

### What happens to a strong 35–45s moment under 61s+ minimum

If a genuinely strong moment spans 35–45s:

1. The sliding window starts at that moment's first scene
2. Scenes accumulate: 35s (no emit), 45s (no emit), 55s (no emit)
3. First emit happens when window reaches ≥ 61s — this includes the strong moment PLUS 16-26s of follow-up material
4. The follow-up material may contain: weaker scenes, speech gaps, lower-energy content

**The strong 35s clip does not exist.** It only appears as the first 35s of a 61s+ clip.

**Score impact on that 61s clip:**
- `hook_opening_score` (weight 0.22): **PRESERVED** — hook is still the opening scene
- `avg_scene_quality` (weight 0.18): **DEGRADED** — averaged across all scenes including the appended weaker ones
- `pacing_stability` (weight 0.10): **DEGRADED** — more scenes = more variance in scene duration
- `ending_strength` (weight 0.13): **UNCERTAIN** — depends on the last scene of the 61s window
- `speech_density_score` (weight 0.05): **POTENTIALLY DEGRADED** — silence after peak moment common
- `silence_penalty`: **ACTIVATED** if speech_density < 20% in appended scenes

### No merge / no extension / no fallback stretch

The fallback (`_FALLBACK_FIELDS`, lines 329–404) creates `[0, min(total_duration, max_len)]` at `viral_score=50.0`. This is activated only when the entire sliding-window pass produces zero valid candidates. Under 61s minimum, fallback fires for any source video shorter than 61s, or any source where scene coverage is so sparse no 61s window accumulates. Fallback score is neutral (50.0) — it passes quality floor checks but ranks last.

### The continuity bonus does NOT help here

A `+3.0 viral_score` continuity bonus applies when a candidate starts within 2s of the previous selected segment's end (line 317). This is a selection-time bonus, not a candidate-generation bonus. It does not cause weak appended scenes to score higher.

---

## 2. Impact Analysis of 61s+ Defaults

### Scenario A — Content with dense 61s+ natural story arcs (BENEFIT)

Podcast, education, interview, commentary: content where the speaker develops a complete thought over 60–120s.

- Sliding window naturally finds candidates that are 70–120s with high scene quality throughout
- 61s minimum aligns with natural arc completion
- `avg_scene_quality` stays high because all scenes are semantically connected
- `pacing_stability` is stable (consistent speaking pace)
- `ending_strength` is strong (thought completes at natural resolution)
- **Result:** 61s+ default produces the BEST clip from this content type

### Scenario B — Content with isolated viral peaks (DEGRADED)

Reaction, meme, sports, motivational quote, news highlight: content where the best moment is 15–45s.

- The strong 35s moment becomes: a 61s clip where the last 26s is the speaker's post-reaction commentary, setup for the next reaction, or silence
- `avg_scene_quality` pulled down by appended scenes
- `silence_penalty` may fire
- `ending_strength` is weak (clip ends mid-setup rather than at a natural peak)
- **Result:** 61s+ default produces a WORSE clip than the strong 35s original

### Scenario C — Mixed content (longer video with both types)

A 20-minute video combining interview segments + viral moments:
- 61s minimum means viral peak moments only appear as openings of longer clips
- Those clips score lower than the pure peak
- BUT: the interview segments that span natural arcs still surface correctly
- Creator gets clips where "strong" is defined by full story arc, not individual peaks
- **Result:** Different output, not worse — but reflects the product's stated preference for arc-complete content

### Quality risks at 61s minimum

| Risk | Mechanism | Severity |
|---|---|---|
| Hook followed by dead air | silence_penalty fires; speech_density < 20% for appended scenes | HIGH for sparse content |
| Filler dilutes score | avg_scene_quality reduced by weaker appended scenes | MEDIUM for most content |
| Clip ends mid-thought | ending_strength based on last scene quality; may be low | MEDIUM |
| Forced continuation of short-form peak | Appended scenes that don't belong to the original moment | HIGH for viral/reaction |
| No candidates at all | Fallback fires for short videos < 61s | LOW (fallback still produces output) |

---

## 3. Benefit Analysis

### What 61s+ defaults improve

**Monetization alignment:**
- YouTube Partner Program mid-roll ads: eligible at 8 minutes+ but watch time accrued per video
- YouTube Shorts monetization (RPM pool): not applicable — shorts are < 60s
- YouTube standard video: 61s qualifies as non-short, enters standard RPM pool
- TikTok Creator Rewards Program (2024+): requires **videos 1 minute or longer** for full payout eligibility
- LinkedIn video: 60s+ signals "professional content" to algorithm
- Facebook Reels monetization: 60s+ required for Stars and in-stream ads

**Retention arc:**
- Retention curves for 60s+ content differ from sub-60s. A 61s clip that holds 70% at the 60s mark signals "high-quality" to platform algorithms
- Sub-30s clips rarely develop a retention arc — they're evaluated on completion rate

**Story completeness:**
- 61s is the minimum viable unit for complete narrative structure: setup → conflict → resolution
- Below 61s, clips often end at conflict without resolution → lower save rate, lower share rate

**Context preservation:**
- Clips 61s+ contain enough context for the viewer to understand without knowing the source video
- Sub-30s clips frequently require source context, leading to "what is this from?" reactions rather than engagement

### For which content types

| Content Type | Benefit from 61s+ | Mechanism |
|---|---|---|
| Podcast | Very High | Natural arc completion; speaker thought structure |
| Education / Tutorial | Very High | Step-based learning needs setup + payoff |
| Finance / Business | High | Claims need evidence (setup + data + conclusion) |
| Interview | High | Question + answer arc = natural 60–90s unit |
| Commentary | High | Point + argument + conclusion arc |
| Storytelling | High | Narrative arc completion |
| Fitness | Medium | Depends on demo length |
| Reaction | Low–Negative | Peak is 10-30s; 61s dilutes with setup/post-reaction |
| Sports highlights | Low–Negative | Action peak is 5–20s; forced extension adds dead time |
| Meme / Viral clips | Negative | Humor/impact is immediate; extension kills punchline timing |

---

## 4. Content Type Analysis

### _EV_PRESETS (actual code, editor-view.js lines 2106–2139)

The existing presets reveal the product's own decision about content-to-duration mapping:

```
tiktok:   min=30,  max=90   → explicitly for viral/hook content
podcast:  min=60,  max=180  → natural arc content
business: min=60,  max=180  → professional arc content
hq:       min=60,  max=240  → long-form quality content
```

The product already knows: **60s+ is the right floor for arc content; 30s is for pure viral format.**

The current global default (70s) reflects an implicit choice of "arc content" as the default. It is correct for the product's stated goal.

### `content_type_hint` is not used for duration selection today

A search of segment_builder.py and render_pipeline.py finds no branching on `content_type_hint` for duration selection. The duration window is entirely controlled by `min_part_sec` / `max_part_sec` from the payload. This means the engine cannot currently auto-adapt duration based on detected content type — the creator's explicit setting (or the default) is the only input.

---

## 5. Platform Reality Assessment (2026)

### TikTok

TikTok in 2026 is a bifurcated platform:

**Short-form (< 60s):** Viral entertainment, meme, reaction. High completion rate. Engagement signal is strong. Revenue per view: low. Monetization gate: TikTok Creator Rewards requires 1-minute+ videos.

**Long-form (61s–10min+):** Tutorial, educational, story-based. Lower completion rate. Platform rewards "series" behavior. Revenue per view: higher when in Creator Rewards. TikTok has been actively incentivizing 1-minute+ uploads since 2023.

**Key insight:** When a creator selects "TikTok" platform, their intent is ambiguous. They may mean:
- "I want viral 9:16 short clips" → prefers 30s min
- "I want monetizable TikTok content that qualifies for Creator Rewards" → prefers 60s+ min

The platform selection alone does not resolve this ambiguity.

### Instagram Reels

Reels up to 90s. Algorithm favors completion rate, which is inversely related to length. 61s Reels have lower completion rate than 30s Reels for entertainment content. However, 61s Reels with high retention signal strong content quality to Meta's algorithm (watch-time signal).

### YouTube Shorts

Strictly < 60s. A clip of 61s is NOT a Short. If creator selects YouTube Shorts as platform, 61s minimum is **technically wrong** — the clip won't be treated as a Short by YouTube.

**This is the critical exception.** YouTube Shorts REQUIRES < 60s. Any clip ≥ 60s is a standard YouTube video, not a Short.

### Standard YouTube / Podcast / Business

60s+ is unambiguously correct. No exceptions. Monetization is better, retention arcs work, context is preserved.

---

## 6. Product Direction Recommendation

### Phase 73.1 as planned creates a conflict

Phase 73.1 proposes: tap TikTok pill → auto-link min=30, max=90.

The product direction says: "many outputs should naturally land 61s+ for watch time / retention / monetization."

These two directives conflict. If the tool auto-sets min=30 when creator taps TikTok, the first render produces 30–90s clips. Some of those clips will be 30–45s — good for engagement, ineligible for TikTok Creator Rewards.

**The Phase 73.1 problem is: it conflates platform selection (TikTok) with format preference (short-form), when the product's goal is monetizable output.**

### Recommended decision model

Three distinct concepts must be separated:

1. **Platform** — where will the content be uploaded (TikTok, YouTube, etc.)
2. **Format** — what duration format (short-form < 60s, standard 60s+, long-form 180s+)
3. **Duration default** — what min/max to use for clip generation

Tapping "TikTok" should set:
- Aspect ratio: 9:16 ✓ (Phase 65, keep)
- Platform metadata: TikTok ✓
- Duration: **do NOT auto-change** — let the creator choose format explicitly

The 61s default (or current 70s) remains the global baseline. Presets remain available for creators who explicitly want short-form format.

### Recommendation choice: Option B — Platform-aware defaults, not universal 61s+

**Option A (Global 61s+):** Would break YouTube Shorts use case entirely (Shorts must be < 60s).

**Option B (Platform-aware):** Correct approach — different platforms have different monetization-optimal durations:
- No platform selected: 61s min, 180s max (OPTIMAL for product goal)
- YouTube Shorts explicitly selected: 15s min, 59s max (REQUIRED for Shorts format)
- TikTok: **do NOT auto-change duration** (ambiguous creator intent)
- Podcast / Business: 60s min, 180s max (already in presets, keep)

**Option C (Content-aware):** Not feasible without content_type_hint routing in the engine, which is not currently wired.

**Option D (Keep current 70s default):** Suboptimal — 70s is slightly too conservative; 61s allows slightly more candidates from the 61–70s range, improving output diversity.

---

## 7. Override Safety Rules

### No dirty/touched tracking exists today

Audit confirmed: `evMinPart` and `evMaxPart` are plain HTML number inputs. There are no dirty flags, no `isTouched` properties, no change-event listeners that track modification state. The inputs are treated as form values only.

### Safe override rule (recommended, not currently implemented)

If Phase 73.1 is revised to set duration from platform selection, an override rule would be required:

**Rule:** Once a creator manually changes `evMinPart` or `evMaxPart`, any subsequent platform tap should NOT overwrite those values.

**Implementation feasibility:** Requires adding two module-level dirty flags:
```javascript
let _evMinPartTouched = false;
let _evMaxPartTouched = false;
```
And `onchange` listeners on the inputs to set them. Then `evQsSet('platform', ...)` would check before overwriting. This is low-effort but currently absent — it must be added BEFORE any auto-link is wired.

**Without this protection:** Auto-linking duration from platform creates a frustrating UX where creator adjusts duration, then taps a platform pill, and their value is silently overwritten.

### Explicit reset case

Creator taps "Reset to defaults" → clear dirty flags → next platform selection can auto-link again. This is the only case where the rule can be broken without user frustration.

---

## 8. Final Verdict

### Will 61s+ defaults make first render BETTER or WORSE?

**For the product's stated goal (high-retention, monetizable, usable outputs):**

**BETTER** — with one specific condition.

61s minimum produces better first renders when:
- Content has natural 60s+ story arcs (podcast, education, interview, commentary, business)
- This covers the majority of the stated product use cases
- Monetization alignment is correct (YouTube RPM pool, TikTok Creator Rewards, LinkedIn algorithm)
- Story completeness improves: setup + conflict + resolution fits in 61s+

**WORSE** — for content with isolated peaks (reaction, sports, viral moments). But these are not the product's primary target.

**Current 70s default vs 61s default:**

The 70s global default is slightly too conservative. Lowering it to 61s is a small improvement: 9 additional seconds of candidate window. Candidates in the 61–70s range that represent naturally complete story arcs will emerge. The risk is minimal — 61s is still firmly in the monetizable zone for all major platforms except YouTube Shorts (which requires a separate preset anyway).

### Revised Phase 73.1 recommendation

**REJECT** the auto-link TikTok → min=30 from Phase 73.1 as currently written.

**REASON:** It conflicts with the product's monetization goal, creates silent overwriting of creator intent, and treats "TikTok" as synonymous with "short-form" when creator intent is ambiguous.

**INSTEAD:**
- Phase 73.1 revised: set `evMinPart` from **70 → 61** globally (unspecified platform only)
- Keep TikTok aspect ratio auto-link (Phase 65) as-is
- Do NOT auto-link TikTok to min=30
- Add YouTube Shorts as the one platform that overrides duration (< 60s is a technical requirement of the format, not a preference)
- Presets remain available for creators who explicitly want short-form TikTok format

### Summary table

| Change | Direction | Verdict | Reason |
|---|---|---|---|
| Global min: 70 → 61 | Lower minimum | **APPROVE** | More candidates from 61–70s range; still monetizable |
| TikTok pill → min=30 (Phase 73.1 as written) | Auto-link short-form | **REJECT** | Conflicts with product goal; silently overrides creator |
| YouTube Shorts pill → max=59 | Technical constraint | **APPROVE** | Shorts literally cannot be 60s+; this is format compliance |
| Podcast/Business presets: min=60 | Already correct | **KEEP** | Presets serve this correctly; don't change |
| Creator manual override: always respected | UX rule | **REQUIRED** | No exception; must add dirty flags before any auto-link |

---

## Appendix — Code Locations Referenced

| Symbol | File | Line | Relevance |
|---|---|---|---|
| `_generate_candidates()` | segment_builder.py | 77–104 | min_len emission gate — hard floor |
| `_normalize_segment_durations()` | segment_builder.py | 50–70 | Truncation only, no extension |
| `_FALLBACK_FIELDS` | segment_builder.py | 329–343 | Fallback viral_score=50.0 |
| Viral score formula | segment_builder.py | 201–216 | 8 signals; hook weight=0.22 |
| `evMinPart` / `evMaxPart` HTML | index.html | 1115/1119 | Current defaults: 70/180 |
| `evQsSet()` | editor-view.js | 355–380 | Currently: platform → aspect ratio only |
| `_EV_PRESETS` | editor-view.js | 2106–2139 | tiktok=30, podcast/business/hq=60 |
| `evApplyPreset()` | editor-view.js | ~2158 | Presets set min/max correctly |
| Final output slice | render_pipeline.py | 2383–2384 | `scored[:max_export_parts]` |
| No quality floor | render_pipeline.py | — | Confirmed absent |
