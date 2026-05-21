# Creator QA Mini Sprint Report

**Branch:** `feature/ai-output-upgrade`
**Sprint:** Creator QA Mini Sprint
**Date:** 2026-05-21
**Status:** ✅ Complete

---

## 1. Purpose

Validate whether lowering `S3_STRUCTURE_DETECT_THRESHOLD` to 0.42 improves creator experience
for the 5 weakest scenarios from the Benchmark Sprint, without introducing false positives.
Produce one final recommendation.

---

## 2. Tested Scenarios

| # | Name | Goal | Reason Selected |
|---|------|------|-----------------|
| 8 | B-roll montage | viral | No speech → no structure detected at any threshold |
| 10 | Mixed VN/EN creator | podcast | Vietnamese markers; confidence borderline concern |
| 11 | Low-energy podcast | podcast | Calm pacing; hook absence penalty was primary complaint |
| 15 | Bad audio / heavy filler | education | Fragmented speech; opening phase absent |
| 20 | Weak hook / no opener | viral | Missing opening phase throughout |

---

## 3. False Positive Analysis

**Formula (no-marker path, when position=0):**
```
c = marker(0.40) + pos×0.35 + transition×0.25
  = 0.40 + 0×0.35 + 0.20×0.25   # pos=0 (outside active range); nat_start=0.20 (first chunk)
  = 0.450
```

**Confirmed false positive at 0.42, not at 0.50:**

| Signal | Value |
|--------|-------|
| Development/payoff marker present | 0.40 |
| Position score (ratio=0, outside Phase2 range [0.10–0.80]) | 0.00 |
| Transition: nat_start (always 0.20 for first chunk × weight 0.25) | 0.05 |
| **Total confidence** | **0.450** |

- At threshold 0.42: **detected** ← FALSE POSITIVE
- At threshold 0.50: **not detected** ← CORRECT

**Trigger condition:** Any clip starting with a development (`"because"`, `"for example"`, `"first"`, etc.)
or payoff marker (`"turns out"`, `"in the end"`, etc.) that begins at the very start of the window
(ratio=0, outside the phase's active position range) with the `nat_start` bonus active.

**Active position ranges (zero outside):**
- Phase 1 (opening): [0, 0.35]
- Phase 2 (development): [0.10, 0.80]
- Phase 3 (payoff): [0.63, 1.0]

False positives occur at ratio<0.10 for development markers and ratio<0.63 for payoff markers —
both are common clip-start positions, especially for viral content (aggressively trimmed) and
any content where the clip begins mid-thought.

---

## 4. Re-Scoring Results

Threshold tested: 0.42 (universal) vs 0.50 (current default, goal-aware)

| # | Scenario | Goal | At 0.50 | At 0.42 | Delta |
|---|----------|------|---------|---------|-------|
| 8 | B-roll montage | viral | phases=[] score=0.00 | phases=[] score=0.00 | **+0.00** |
| 10 | Mixed VN/EN | podcast | phases=[open, dev, payoff] score=8.93 | phases=[open, dev, payoff] score=8.93 | **+0.00** |
| 11 | Low-energy podcast | podcast | phases=[open, dev, payoff] score=9.92 | phases=[open, dev, payoff] score=9.92 | **+0.00** |
| 15 | Bad audio | education | phases=[dev, payoff] score=0.00 | phases=[dev, payoff] score=0.00 | **+0.00** |
| 20 | Weak hook | viral | phases=[dev, payoff] score=0.00 | phases=[dev, payoff] score=0.00 | **+0.00** |

**Key finding:** Zero scenarios improved. All confidence values already exceed 0.50 (scenarios #10,
#11) or fail for unrelated reasons (scenarios #8, #15, #20 lack an opening phase entirely —
structure coherence score requires `opening` ∈ `phases_detected` to return a nonzero bonus).

Phase confidence values at 0.50 (scenarios #10, #11):
- #10: opening=0.66, development=0.60, payoff=0.53 — all well above 0.42 AND 0.50
- #11: opening=0.66, development=0.72, payoff=0.61 — all well above 0.42 AND 0.50

Lowering the threshold to 0.42 does not change which phases are detected for these scenarios.

---

## 5. Recommendation

**KEEP 0.50**

### Justification

| Criterion | 0.42 universal | Goal-aware (podcast=0.42) | 0.50 (current) |
|-----------|---------------|---------------------------|----------------|
| Improvement for #8 | None | None | — |
| Improvement for #10 | None | None | — |
| Improvement for #11 | None | None | — |
| Improvement for #15 | None | None | — |
| Improvement for #20 | None | None | — |
| False positive risk | **Confirmed** | **Confirmed (podcast too)** | None |
| Net benefit | **Zero** | **Zero** | Baseline |

The hypothesis was that informal/casual speech (podcast, low-energy) would have phases scoring
in [0.42, 0.50), benefiting from a lower threshold. The data disproves this:

- Scenarios #10 and #11 (the podcast scenarios) already have all-phase confidence ≥ 0.53 — well
  above both thresholds. These creators naturally use clear opener markers (`được rồi`, `alright`),
  causal transitions (`vì`, `because`), and conclusive phrases (`cuối cùng`, `in the end`).

- Scenarios #8, #15, #20 fail because they lack an **opening phase** — the structure coherence
  scoring function returns 0.0 unless `opening` is detected. Lowering the threshold does not help
  if there is simply no opening marker in the clip.

- The false positive condition (c=0.450) is mathematically guaranteed to fire at any threshold < 0.45
  for clips starting with a development or payoff marker, regardless of goal.

### Infrastructure Decision

`_GOAL_DETECT_THRESHOLDS: dict = {}` — empty. Goal-aware threshold infrastructure (B2 + the
`_get_detect_threshold()` helper) is retained in `structure_analyzer.py` for future calibration
sprints. No goal currently overrides 0.50.

---

## 6. Code Changes

### `backend/app/ai/analyzers/structure_analyzer.py`

**Added (infrastructure, no behavior change):**
- `_GOAL_DETECT_THRESHOLDS: dict[str, float] = {}` — goal override map (currently empty)
- `_get_detect_threshold(goal) -> float` — helper returning goal override or `_DETECT_THRESHOLD`
- `analyze_window_structure(..., detect_threshold=_DETECT_THRESHOLD)` — optional param
- `score_structure_coherence()` calls `analyze_window_structure` with `_get_detect_threshold(goal_key)`

**Behavior:** Identical to pre-QA sprint. All goals receive threshold=0.50 (the `_GOAL_DETECT_THRESHOLDS`
dict is empty, so `_get_detect_threshold()` always returns `_DETECT_THRESHOLD=0.50`).

**Env var still works:** `S3_STRUCTURE_DETECT_THRESHOLD=0.42` still applies globally (B2). The
goal-aware layer is a refinement on top of the env var, not a replacement.

---

## 7. Updated Benchmark Scores

No code behavior changed → benchmark scores unchanged from Calibration Sprint:

| Tier | BASELINE | AFTER CAL | QA FINAL |
|------|----------|-----------|----------|
| Average | 7.09 | 7.13 | **7.13** |

**Launch readiness: Creator QA Needed (7.0–8.0)**

To reach ≥ 8.0, the primary blockers are scenarios without opening phases (#15 bad audio,
#20 weak hook, #8 B-roll) — structure scoring cannot help these without an actual opener marker
in the transcript. Improvement would require upstream changes to clip selection, not threshold tuning.

---

## 8. Failure Mode Validation

| Scenario | Expected behavior | Result |
|----------|-------------------|--------|
| No markers at all (#8 B-roll) | phases=[], score=0.0 | ✅ |
| Phases already exceed 0.50 (#10, #11) | No change from lowering threshold | ✅ |
| Missing opening (#15, #20) | score=0.0 regardless of dev/payoff detection | ✅ |
| First-chunk dev marker + nat_start | c=0.450, FP at <0.45, not at 0.50 | ✅ Confirmed |
| `S3_STRUCTURE_DETECT_THRESHOLD=0` env override | Still applies (B2 preserved) | ✅ |
| Empty goal | Falls back to `_DETECT_THRESHOLD=0.50` | ✅ |

---

## 9. Regression Guarantees

- `score_structure_coherence()` behavior bit-identical to post-Calibration Sprint (same threshold, same formula)
- `analyze_window_structure()` signature change is backward-compatible (`detect_threshold` is optional with default)
- `_GOAL_DETECT_THRESHOLDS={}` → `_get_detect_threshold()` always returns `_DETECT_THRESHOLD` → no change
- No env var changes
- No render pipeline changes
- No clip selection changes
- No scoring changes beyond the no-op threshold infrastructure

---

## 10. Post-QA Freeze Note

**CALIBRATION_FROZEN=true** — applied in Post-QA Freeze Sprint.

This report represents the terminal calibration state for the S3 production intelligence stack.
No further threshold tuning is permitted without re-opening a calibration sprint with new benchmark data.

### Locked Production Defaults

These env vars are frozen as of the Post-QA Freeze Sprint. Any deviation requires explicit
sprint approval and a benchmark re-run.

| Env Var | Frozen Value | Module | Rationale |
|---------|-------------|--------|-----------|
| `S3_RETENTION_BASE_SCORE` | `68` | S3.2 | Calibration Sprint Phase A — raised from 65 for more realistic baseline |
| `S3_RETENTION_DEAD_ZONE_THRESHOLD` | `0.26` | S3.2 | Phase A — relaxed from 0.22; "calm pacing ≠ dead zone" |
| `S3_RETENTION_PROMISE_PENALTY` | `16` | S3.2 | Phase A — reduced from 18; less punishing for partial promise fulfillment |
| `S3_RETENTION_MIN_SCORE` | `45` | S3.2 | Phase A — raised from 40; only retain higher-confidence clips |
| `S3_PLATFORM_CONFIDENCE_MIN` | `0.12` | S3.4 | Phase A — raised from 0.10; avoid near-zero confidence hints |
| `S3_STRUCTURE_DETECT_THRESHOLD` | `0.50` | S2.3 | QA Mini Sprint — 0.42 REJECTED (false positives, zero benefit) |

### Rejected Assumption — Permanent Record

**Assumption tested:** Lowering `S3_STRUCTURE_DETECT_THRESHOLD` to 0.42 for podcast/informal speech
would detect more true structure phases without false positives.

**Why rejected:**
1. **False positive confirmed** (Section 3): marker at ratio=0 + nat_start → c=0.450, detected at
   0.42 but not at 0.50. Mathematically guaranteed for any development/payoff marker at clip start.
2. **Zero benefit** (Section 4): all 5 tested scenarios showed delta=+0.00. Podcast scenarios
   (#10, #11) already exceed 0.50 with confidence 0.53–0.72.
3. **Root cause mismatch**: weak scenarios (#8, #15, #20) fail due to absent opening markers, not
   strict threshold. Threshold tuning cannot recover structure that was never spoken.

**Status:** PERMANENTLY REJECTED at this confidence level. Re-evaluation requires new benchmark
data showing scenarios with genuine phase confidence in [0.42, 0.50) that are verified true positives.
