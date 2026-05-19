# Phase 73 — First Render Confidence Plan
**Post-72 Review Velocity | REVISED per Phase 73-A Audit**
**Status:** PLANNING — not yet implemented
**Branch target:** feature/ai-output-upgrade
**Date:** 2026-05-19
**Supersedes:** Original Phase 73 plan (2026-05-19)
**Audit source:** docs/product/PHASE_73A_MIN_61S_DEFAULT_AUDIT.md

---

## Executive Summary

Phase 72 added keyboard-driven review velocity (K/A/D shortcuts, auto-next, counter). The bottleneck is now upstream: creators spend review cycles correcting clips that should not have been output in the first place — too many low-value clips, no quality floor, and a global minimum duration that suppresses valid candidates in the 61–70s range.

**Goal:** Reduce the time between "first render" and "confident share" by fixing systematic first-render misses through small deterministic improvements: correcting the default minimum duration, reducing output noise, adding a backend quality floor, and surfacing honest confidence context.

**What changed from the original plan:**

The original Phase 73 commit 73.1 proposed auto-linking TikTok platform pill → min=30s duration. The Phase 73-A audit rejected this. The audit found:
1. The hard emission gate in `_generate_candidates()` means min_len is not a preference — it controls which candidates are discovered at all
2. Forcing min=30 when TikTok is selected produces 30–45s clips that are ineligible for TikTok Creator Rewards (which requires 60s+)
3. Platform selection does not equal duration intent — a creator selecting TikTok may want monetizable long-form TikTok content, not viral short clips
4. The product direction is explicitly 61s+, monetizable output — not viral spam clips

The revised 73.1 is a single default value change: `evMinPart 70 → 61`. No auto-linking. No platform overrides. Creator always owns min/max.

**Scope guardrails (unchanged):**
- DO NOT change the ranking engine formula or weights
- DO NOT add LLM calls, new AI models, or cloud round-trips
- DO NOT change creator workflow (same steps, same UI)
- DO NOT redesign any existing feature
- DO NOT invent scoring systems not already present in the codebase
- DO NOT add platform-to-duration auto-linking (rejected by audit — requires dirty flag infrastructure first)

---

## First Render Failure Audit

Grounded in code audit of `segment_builder.py`, `render_pipeline.py`, `editor-view.js`, and `index.html`. Confirmed by Phase 73-A duration audit.

### Root Cause 1 — Global minimum is 70s when 61s is better (HIGH IMPACT)

**File:** `backend/static/index.html` lines 1115/1119 — `evMinPart` default value

The current global default is `evMinPart=70`. The `_generate_candidates()` sliding window in `segment_builder.py` (line 101) only emits a candidate when `seg_end - seg_start >= min_len`. This means any story arc that naturally completes at 61–69s produces zero candidates under the current default.

The 61–70s range is real content: a speaker who makes a complete point in 65s, an interview answer that resolves in 63s, a tutorial step that ends at 68s. Under the current 70s floor, these strong arcs are either forced to extend into weaker scenes or are subsumed into the 70s+ candidate where they appear as the weaker opening of a longer arc.

Lowering to 61s gives the engine 9 additional seconds of candidate window with zero risk: 61s is above the monetization threshold for all major platforms (TikTok Creator Rewards, YouTube standard RPM pool, LinkedIn algorithm signal).

**Changing evMinPart from 70 → 61 is a strict improvement with no tradeoffs.**

### Root Cause 2 — Default clip count is unlimited (HIGH IMPACT)

**File:** `backend/static/index.html` line 1076: `value="0"` on `evMaxExportParts`

`max_export_parts=0` means "render all candidates." A typical 15-minute source produces 8–15 candidate segments. Creators receive a wall of clips on first render, most weak. The review queue fills immediately with noise.

The `autoBestClips` option (forces 5) exists but lives in the collapsed Market section and is not discoverable on first use.

**A sensible first render should show the top 6 clips, not everything.**

Changed to 6 (from original plan's 5) to provide slightly more output while still capping noise.

### Root Cause 3 — No backend quality floor (MEDIUM IMPACT)

**File:** `backend/app/services/render_pipeline.py`

All segments above minimum duration pass to output regardless of `viral_score`. There is no minimum score threshold in `segment_builder.py` either — the fallback path produces a 0–max_len segment at `viral_score=50.0` when no real candidates score.

Result: experimental-tier clips (weak confidence, low viral_score) are rendered and delivered alongside strong clips. UX-R3 tiers these visually (`_applyUxR3Tiers` in render-ui.js), but they still occupy render time and review queue slots.

### Root Cause 4 — Narrow-spread score wall (LOW IMPACT, P1)

**File:** `backend/static/js/render-ui.js` — `_applyUxR3Tiers()`

Strong threshold: `_bestScore * 0.85`. When all clips score within 1.5 raw points (common for uniform talking-head content), every clip lands in "Strong Candidates." The tier labels become noise and give creators no signal for where to start their review.

---

## What Changed from Original Phase 73

| Original | Revised | Reason |
|---|---|---|
| 73.1: TikTok pill → min=30, max=90 auto-link | **REJECTED. 73.1 revised:** evMinPart 70 → 61 globally | Audit: conflicts with product goal; creator intent ambiguous; requires dirty flag infrastructure not yet built |
| 73.1: YouTube Shorts → min=15, max=60 | **REJECTED.** No platform auto-linking in this phase | Same reason as above; YouTube Shorts is an exception but needs dirty flag protection first |
| 73.2: Default max clips = 5 | **Revised:** Default max clips = 6 | Slightly more generous output; still caps noise vs unlimited |
| 73.3: Quality floor viral_score < 25 | **Kept, procedure clarified:** sort → filter → fallback | Never 0 outputs; procedure order made explicit |
| 73.4: Narrow-spread advisory (P2) | **Promoted to P1 optional** | Honest confidence signal is aligned with product direction |

### Why TikTok auto-link was rejected

The original 73.1 assumed: creator selects TikTok platform pill → they want 30–90s clips.

The audit found this assumption wrong on three counts:

1. **Intent ambiguity.** TikTok in 2026 has two distinct creator paths: viral/entertainment (short-form, < 60s) and educational/monetizable (long-form, 60s+). Tapping "TikTok" as a platform target does not indicate which path the creator is on.

2. **Monetization conflict.** TikTok Creator Rewards Program requires videos ≥ 60s for full payout eligibility. Auto-linking TikTok → min=30 produces clips that are ineligible for the program the product is optimizing for.

3. **Silent overwrite without protection.** `evMinPart` and `evMaxPart` have no dirty flag tracking. Auto-linking would silently overwrite any manual values the creator had set. The Phase 73-A audit identified this as a UX requirement (dirty flag infrastructure) that must be built before any auto-link is safe. That infrastructure is not in scope for Phase 73.

**Platform selection and duration intent are separate concepts.** Phase 65 correctly wired platform → aspect ratio because aspect ratio is a format compliance requirement (9:16 for vertical, 16:9 for landscape). Duration is a creative choice. They are not the same class of setting.

---

## Miss Type Matrix (Revised)

| Miss Type | Frequency | Cause | Fix |
|---|---|---|---|
| Story-complete 61–70s arcs missed | High | evMinPart=70 floor too conservative | 73.1: lower to 61 |
| Too many clips, no signal | High | max_export_parts=0 default | 73.2: default=6 |
| Low-score clips mixed in | Medium | No quality floor in pipeline | 73.3: floor at viral_score<25 |
| Uniform-score wall, no triage signal | Low | Narrow spread, all "Strong" | 73.4: advisory note (P1) |
| Fallback segment delivered as real clip | Rare | viral_score=50 fallback path | 73.3: floor catches fallback if weak |

---

## Commit Plan (Revised)

### Commit 73.1 — Global default evMinPart: 70 → 61 (P0)

**File:** `backend/static/index.html`
**Change:** `evMinPart` input — `value="70"` → `value="61"`. Update nearby label or hint if one exists.
**Scope:** Single value change. No platform logic. No auto-linking. No conditional behavior.
**Why:** The `_generate_candidates()` hard emission gate at `seg_end - seg_start >= min_len` means story arcs completing at 61–70s are currently invisible to the engine. Lowering to 61 unlocks this range while remaining above monetization thresholds for all target platforms.
**What does NOT change:** Creator can set any min value. Platform selection does not override this. No dirty flag logic needed because this is a starting default, not an auto-write.
**Test:** Fresh load → `evMinPart` input shows 61. Creator manually changes to 45 → value stays 45 across the session. Render with default → engine produces candidates starting at 61s.

---

### Commit 73.2 — Default max clips: 0 → 6 (P0)

**File:** `backend/static/index.html`
**Change:** `evMaxExportParts` input — `value="0"` → `value="6"`. Update nearby hint text: "Top 6 clips by default — set to 0 for all clips."
**Why:** `max_export_parts=0` (unlimited) sprays all candidates onto first render. A typical 15-minute video with dense content produces 10–15 candidates. Creator receives noise-heavy first render. Default of 6 matches ranked top output without hiding the ability to get more.
**What does NOT change:** `max_export_parts=0` (unlimited) continues to work identically. Creator can set any number. No behavioral change to ranking or filtering.
**Test:** Fresh load → input shows 6. Set to 0 → unlimited render works as before. Set to 3 → only top-3 clips render.

---

### Commit 73.3 — Backend quality floor: drop viral_score < 25 (P0)

**File:** `backend/app/services/render_pipeline.py`
**Change:** After candidate list is built and scored, before the final `[:max_export_parts]` slice:
1. Sort by viral_score descending (already done at lines 2374–2382 — confirm it runs first)
2. Filter: remove candidates where `viral_score < 25`
3. Fallback guard: if filter leaves empty list, keep the single top candidate from the unfiltered sorted list (never return 0)
4. Apply `[:max_export_parts]` slice as before

**Procedure order is mandatory:** sort → filter → fallback → slice. Never filter before sort.

**Why 25:** Score 25 is below the "experimental" confidence tier threshold. Candidates scoring < 25 have multiple weak signals — low hook score, poor scene quality, or gap penalties have compounded. They are not useful first-render output. The always-keep-1 guard ensures the pipeline never silently fails for very short or sparse content.

**Why this does not change ranking:** The quality floor only removes the weakest candidates from output. It does not change any score, any weight, any ranking formula, or any signal. The ranked order of surviving candidates is identical to today.

**Test:** Source video with 3 candidates scoring [22, 18, 12] → output is top-1 (viral_score=22, kept by fallback). Source video with candidates scoring [78, 65, 30, 19] → output is [78, 65, 30] (19 filtered). Source with one candidate scoring 80 → output is [80] (unaffected).

---

### Commit 73.4 — Narrow-spread advisory note (P1 — implement if 73.1–73.3 are clean)

**File:** `backend/static/js/render-ui.js` — in or after `_applyUxR3Tiers()`
**Change:** After tier classification, check two conditions:
- All done clips are classified as "other" / experimental tier (best clip margin < 4)
- AND score spread between best and worst done clip is < 1.5 raw points

If both conditions true: inject a single advisory line below the tier section header:
`"Clips are closely matched — trust your own watch."`

**Tone:** Calm, informational. Not alarming. Not a warning badge. Not an error state.

**Why:** When the ranking signal is weak (low spread, all experimental), the tier labels ("Strong Candidates") are technically correct but misleading — they imply the engine has a view when it does not. Honest confidence is better than false certainty. Creator makes a better decision when they know the AI is uncertain.

**What does NOT change:** No tier is hidden. No clip is removed. No score changes. Advisory is purely contextual text.

**Test:** All clips within 1-point spread + experimental tier → advisory appears. Clips with 5-point spread → no advisory. Mixed tiers (some strong, some experimental) → no advisory (condition requires ALL to be experimental/other).

---

## Safe Default Model (Unchanged)

All four improvements follow the same decision model:

1. **Match product goal** — monetizable, high-retention output at 61s+
2. **Reduce noise, keep ceiling** — fewer clips by default; unlimited still accessible
3. **Never return empty** — quality floor always keeps ≥ 1 clip
4. **Advisory, not gatekeeping** — UI notes are informational; creator can ignore
5. **No new data sources** — all signals come from values already in the payload or DOM
6. **Creator always wins** — no setting is overwritten without explicit creator action

---

## Trust & UX Rules (Unchanged)

- Creator can set `evMinPart` to any value; 61 is a starting default, not a floor enforcement
- `max_export_parts=0` (unlimited) remains fully supported and accessible
- Quality floor never removes the only clip — always-keep-1 is non-negotiable
- Advisory text (73.4) is a single line only — no modals, no badges, no error states
- No platform-to-duration auto-linking in this phase (requires dirty flag infrastructure first)
- Nothing touches ReviewQueue review actions, steering feedback, or creator DNA

---

## Priority Matrix (Revised)

| ID | Improvement | Impact | Effort | Risk | Priority |
|---|---|---|---|---|---|
| 73.1 | evMinPart default 70 → 61 | High | Minimal (1 value) | Very Low | **P0** |
| 73.2 | Default max_export_parts 0 → 6 | High | Minimal (1 value + hint) | Very Low | **P0** |
| 73.3 | Backend quality floor viral_score < 25 | Medium | Low (~10 lines) | Low | **P0** |
| 73.4 | Narrow-spread advisory note | Low | Low (~20 lines) | Very Low | **P1** |
| ~~73.1 (original)~~ | ~~TikTok pill → min=30 auto-link~~ | ~~High~~ | ~~Low~~ | ~~Medium~~ | **REJECTED** |

---

## Definition of Done (Revised)

- [ ] Fresh load: `evMinPart` input shows **61** (not 70)
- [ ] Creator manually sets `evMinPart` to any value → value persists, no override
- [ ] Platform selection (any pill) does NOT change `evMinPart` or `evMaxPart`
- [ ] Fresh load: `evMaxExportParts` input shows **6** (not 0)
- [ ] Creator sets `evMaxExportParts` to 0 → unlimited render works identically to today
- [ ] Backend: all-weak source (all candidates < 25) still returns exactly **1 clip** (top scorer)
- [ ] Backend: source with mixed scores [78, 65, 30, 19] returns [78, 65, 30] (19 filtered)
- [ ] No change to viral_score formula, signal weights, or confidence tier thresholds
- [ ] No change to ReviewQueue, CreatorSeries, CreatorTaste, ScorePreference, DurationPreference
- [ ] Phase 72 keyboard shortcuts, auto-next, and counter remain functional
- [ ] Zero new localStorage keys, zero new API endpoints
- [ ] Advisory note (73.4 if implemented): appears only under dual condition (all-experimental + spread < 1.5); does not appear for mixed or well-spread clips

---

## Appendix — Code Locations

| Symbol | File | Notes |
|---|---|---|
| `evMinPart` default | index.html line 1115 | Change `value="70"` → `value="61"` |
| `evMaxExportParts` default | index.html line 1076 | Change `value="0"` → `value="6"` |
| `_generate_candidates()` | segment_builder.py lines 77–104 | Hard emission gate at `seg_end - seg_start >= min_len` |
| `_normalize_segment_durations()` | segment_builder.py lines 50–70 | Truncation only — no extension |
| `_FALLBACK_FIELDS` | segment_builder.py lines 329–343 | Fallback viral_score=50.0; floor at 73.3 keeps this if top-1 |
| Final sort + slice | render_pipeline.py lines 2374–2384 | `scored[:max_export_parts]`; quality filter inserts before this |
| `_applyUxR3Tiers()` | render-ui.js ~line 4284 | Strong threshold: bestScore * 0.85; 73.4 advisory hooks here |
| `evQsSet()` | editor-view.js lines 355–380 | Platform pill handler; NOT changed in Phase 73 |
| `_EV_PRESETS` | editor-view.js lines 2106–2139 | Presets remain intact; tiktok=30 still available as explicit preset choice |

---

## Deferred to Future Phase

**Platform-to-duration auto-linking** (originally Phase 73.1):
- Requires dirty flag infrastructure (`_evMinPartTouched`, `_evMaxPartTouched`) on `evMinPart`/`evMaxPart` inputs
- Requires clear UX for when auto-link fires vs. respects creator intent
- When implemented: YouTube Shorts (max=59) is the one technically justified auto-link; others are preference signals only
- Do not implement until dirty flag protection is in place
