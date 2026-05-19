# Phase 75 — Expected Friction Analysis
## Pre-QA Hypothesis Report | Code-Grounded Predictions

**Status:** PREDICTION ONLY — not observed QA data  
**Date:** 2026-05-19  
**Branch:** feature/ai-output-upgrade  
**Author:** Pre-QA analysis derived from segment_builder.py, render_pipeline.py, render-ui.js  
**Purpose:** Make real QA smarter. Not a substitute for QA.

---

## How to Read This Document

Every claim in this document is a **hypothesis derived from code**. No content was actually rendered. No creator friction was actually observed. Labels throughout:

- `[CODE-CONFIRMED]` — directly traceable to a line/formula in source
- `[PREDICTED]` — logical inference from confirmed code behavior
- `[UNKNOWN]` — depends on runtime data (scene cuts, speech timestamps) not inspectable statically

When Phase 75 QA produces real observations, friction events here should be marked **CONFIRMED**, **REFUTED**, or **PARTIAL**.

---

## Engine Reference (Confirmed Code Behavior)

These formulas are ground truth for all predictions below.

### Candidate Emission Gate (`segment_builder.py:101`)
```
candidate only emitted when:
    seg_end - seg_start >= min_len   (default min_len = 61 after Phase 73.1)
```
- `[CODE-CONFIRMED]` A moment shorter than `min_len` produces **zero dedicated candidates**
- `[CODE-CONFIRMED]` That moment can still appear as the *opening* of a longer clip, but its tail content determines whether the clip is emitted

### Viral Score v3 Formula (`segment_builder.py:111–234`)
```
score = (
  hook_opening_score  * 0.22   +    # highest weight
  visual_intensity    * 0.18   +
  speech_rate_score   * 0.18   +
  engagement_cue_score* 0.15   +
  scene_density_score * 0.12   +
  audio_energy_score  * 0.08   +
  emotional_arc_score * 0.07
) - penalties
```

**Key sub-formulas:**
```
hook_opening_score  = clamp((first_q + first_trans) / 2.0, 0, 100)
  default first_trans = 60  (transition_score=1.0 when no cut data)
  → hook_opening_score default ≈ (first_q + 60) / 2

scene_density_score = clamp(len(scene_window) / duration * 8.0, 0, 1) * 100
  → few cuts in a long clip → score approaches 0

silence_penalty     = up to −20 pts, fires when speech_density < 20%
  → ONLY active when speech_data_active = True
```

**Active penalties:**
- `weak_open_penalty`  (−0.5 × weight) when `hook_opening_score < 40`
- `silence_penalty`    when `speech_density < 20%` AND `speech_data_active`
- `low_motion_penalty` when visual content is near-static
- `compression_penalty` when clip has encoding artifacts (heuristic)

### Quality Floor (`render_pipeline.py:2383–2388`, Phase 73.3)
```python
if len(scored) > 2:
    filtered = [s for s in scored if viral_score >= 25]
    scored = filtered if filtered else scored[:1]
```
- `[CODE-CONFIRMED]` Floor is SKIPPED when pool ≤ 2 (sparse content safety)
- `[CODE-CONFIRMED]` When ALL clips score below 25, result = **exactly 1 clip** (worst-case fallback)
- `[CODE-CONFIRMED]` Floor fires BEFORE `max_export_parts` slice — the count the creator sees is post-floor

### UX-R3 Tier Labels (`render-ui.js`)
```
Strong threshold = bestScore * 0.85
If all clips are within 1.5 raw points → ALL tier as "Strong Candidates"
```
- `[CODE-CONFIRMED]` Narrow-spread advisory (Phase 73.4) is NOT deployed — this branch still outputs misleading "Strong Candidates" for undifferentiated pools

---

## Content Type Analysis

### 1. Podcast / Long-Form Interview Audio

**Format signature:** 30–90 min source, mostly static or slow-panning shots, continuous speech, low scene cuts per minute.

**Predicted score behavior:**
- `scene_density_score` → structurally LOW (`[PREDICTED]` — few cuts per 61s window → numerator small)
- `hook_opening_score` → depends on first 10s question quality; opener clips that start with host question will depress this
- `speech_rate_score` → HIGH when guest speaks at natural conversational pace; can offset scene_density deficit
- `silence_penalty` → INACTIVE if `speech_data_active=False`; ACTIVE and variable if enabled

**Predicted friction events:**

| Event | Probability | Root Cause |
|---|---|---|
| Creator receives 8–15 clips with similar scores | HIGH | `max_export_parts=0` default = unlimited; long source → many 61s windows pass gate |
| All clips labeled "Strong Candidates" | HIGH | Narrow spread: all clips within 2–4 pts when scene_density and audio_energy are uniformly low |
| Best moment (a specific story beat) is NOT clip #1 | MEDIUM | If best beat starts mid-sentence, hook_opening_score is lower than a clip that happens to open with high vocal energy |
| Creator cannot tell which clip to use first | MEDIUM | No ranking differentiation signal when all scores within 1.5 pts |

**Expected QA observation:**
> Creator scrolls through 10+ clips, all labeled "Strong," clicks each thumbnail, picks one by intuition. Does not use K/F/D keyboard shortcuts — has not read them. Review queue fills without resolution.

---

### 2. Education / Screen Recording / Tutorial

**Format signature:** Screen + face-cam or screen-only, low visual intensity, high speech rate, infrequent scene transitions, possibly slides with static visuals.

**Predicted score behavior:**
- `visual_intensity` → LOW (`[PREDICTED]` — screen content has low motion variance vs. live video)
- `scene_density_score` → LOW to MEDIUM depending on slide transitions (each slide change = 1 scene boundary)
- `hook_opening_score` → depends entirely on whether first 10s is a hook statement or preamble ("Today we're going to look at...")
- `speech_rate_score` → MEDIUM to HIGH if instructor speaks consistently

**Predicted friction events:**

| Event | Probability | Root Cause |
|---|---|---|
| Top-ranked clip opens with "So today I want to show you..." | MEDIUM-HIGH | Preamble clips pass gate if 61s+ but hook_opening_score is low — still scored above floor because speech_rate offsets |
| Floor doesn't fire but output clips are weak | MEDIUM | Clips score 26–35 (above floor, below ideal) — quality floor passes them through; creator sees mediocre results |
| Creator wants "the moment where I showed the key formula" | HIGH | `[UNKNOWN]` — depends on whether that moment has visual complexity change. Static slides → scene_density doesn't peak there |

**Expected QA observation:**
> Creator identifies correct clip manually ("that's the one where I showed the diagram") but it is ranked 4th. Creator expects it to be #1. Does not understand why the explainer intro ranked higher.

---

### 3. Finance / Business Talking Head (Low-Energy)

**Format signature:** Single speaker, professional background, controlled lighting, slow delivery, few gestures, no B-roll cuts, 10–60 min source.

**Predicted score behavior:**
- `visual_intensity` → LOW (static background, minimal motion)
- `scene_density_score` → NEAR ZERO (`[CODE-CONFIRMED]` formula: `len(scene_window) / duration * 8.0` — no cuts → numerator = 1 or 0 → score approaches 0)
- `audio_energy_score` → LOW to MEDIUM (controlled professional delivery)
- `hook_opening_score` → depends on whether speaker opens with data/claim vs. greeting
- Composite score pool → likely clusters 22–34

**Predicted friction events:**

| Event | Probability | Root Cause |
|---|---|---|
| Quality floor fires → creator gets 1 clip | MEDIUM | If pool scores are 18–24 (all below floor, pool > 2) → fallback-to-top-1 → single clip exported |
| Creator gets 1 clip that feels generic | MEDIUM | Top-1 fallback is the highest-scoring clip by formula, not by creator intent |
| Creator rerenders with same settings, same result | HIGH | No settings change → same candidate pool → same floor behavior → same output |
| Creator doesn't know what changed or what to change | HIGH | UI shows "1 clip" without explaining floor behavior |

**Expected QA observation:**
> Creator runs render on 20-minute finance explainer. Gets 1 clip. Assumes this is normal. Doesn't know 11 candidates were scored and 10 were filtered below the floor. Rerenders. Gets same 1 clip. Files feedback: "tool only finds one highlight."

**Severity classification:** `P0 if confirmed` — silent quality floor with no UI explanation produces creator confusion that reads as engine failure.

---

### 4. Commentary / Reaction (45–65s Peak Moments)

**Format signature:** Host reacts to clips/news, best emotional moments are 45–65 seconds of continuous reaction, high vocal energy, high motion, but source structure means peak moments don't extend naturally to 70s.

> **Note:** Phase 73.1 moved global min from 70s → 61s. This changes the analysis from the original Phase 73 plan.

**Predicted score behavior:**
- Best peaks are 45–60s → `[CODE-CONFIRMED]` gate now allows 61s+ → a 45s peak STILL misses
- A 61s window starting 5s before the peak will score high hook + high engagement in the window's first half
- Tail of clip (sec 62–71 of a 71s clip) may be lower-energy recovery content, but clip still passes gate

**Predicted friction events:**

| Event | Probability | Root Cause |
|---|---|---|
| Strong 45–60s reaction peak is NOT exported as its own clip | HIGH | `[CODE-CONFIRMED]` emission gate = 61s; 45–60s moment still below gate |
| Peak moment appears as MIDDLE of a 75s clip | MEDIUM-HIGH | Candidate window starts before peak → peak is in sec 15–50 of clip → clip starts and ends with weaker content |
| Creator's "obvious clip" is not in output | MEDIUM | If source has sparse scene cuts, the 61s window around the peak may score lower than a calmer but visually-denser section |

**Expected QA observation:**
> Creator watches output clip. Recognizes best reaction starting at 0:15 and ending at 0:52 of the exported clip. Feels clip starts too early (low energy) and ends with cool-down content. Wants to trim. Trimming in the tool (if available) resolves; if not, friction.

---

### 5. Interview (Two-Person, Q&A Structure)

**Format signature:** Host asks question (10–20s), guest answers (40–90s). Natural arc = question sets up answer. Both on screen, or cut between them.

**Predicted score behavior:**
- Question segments: low visual intensity (cut to reaction), speech content is interrogative not assertive → `hook_opening_score` variable
- Answer segments: higher speech rate, higher engagement cues → score higher in formula
- Candidate window often starts at question → hook of window = question → depresses hook_opening_score for that candidate

**Predicted friction events:**

| Event | Probability | Root Cause |
|---|---|---|
| Best Q+A exchange is split across two candidates | MEDIUM | If Q is 15s + A is 60s = 75s total → one candidate starts at Q (scores lower), next starts at A (scores higher but loses context) |
| Top-ranked clip starts with answer, no context | MEDIUM | Answer-start clips score higher on hook_opening_score when answer opens with strong assertion → but lacks Q setup |
| Creator's favorite "whole exchange" is not exported | MEDIUM | Q+A combined > 61s but the Q prefix depresses hook score → ranked below a pure-answer clip |
| Interview feels fragmented in output | MEDIUM | Without Q, answer clips lose editorial context; creator must manually pair |

**Expected QA observation:**
> Creator watches clip that starts with "Absolutely, I think the key thing is..." — recognizes it as the great answer but notes it feels abrupt without the question. Wants the Q included. Tool has no editorial control for this.

---

### 6. Mixed Content (B-roll + Talking Head)

**Format signature:** Produced video with B-roll cutaways, lower thirds, graphics, mixed speaker + environmental footage.

**Predicted score behavior:**
- B-roll windows: HIGH scene_density (many cuts), HIGH visual_intensity → formula rewards them
- Talking-head windows: lower scene_density, lower visual_intensity → formula scores lower even if content is stronger
- `[PREDICTED]` B-roll clips will systematically rank above talking-head clips in mixed-source content

**Predicted friction events:**

| Event | Probability | Root Cause |
|---|---|---|
| Top clips are all B-roll montages | MEDIUM-HIGH | scene_density + visual_intensity bias → montage windows outscore interview windows |
| Creator's intended "hero clip" (interview statement) ranked 3rd–5th | MEDIUM | Interview window at lower formula score than B-roll windows of same source |
| Quality floor removes interview clip but keeps B-roll clip | LOW-MEDIUM | If interview window scores 22 (below floor) and B-roll scores 30 (above) → floor removes interview |

**Expected QA observation:**
> Creator exports 5 clips. Clips 1, 2, 4 are B-roll montages. Creator's intended hero soundbite is clip 3. Creator feels the tool "doesn't understand what the video is about."

---

### 7. Low-Energy Talking Head (All Scores Within Narrow Band)

**Format signature:** Solo speaker, calm delivery, minimal gestures, no scene cuts, consistent audio level. E.g., product walkthrough, calm vlog, business update.

This type directly tests UX-R3 tier label behavior when all scores cluster.

**Predicted score behavior:**
```
All clips share:
  scene_density_score  ≈ 2–8   (near-zero cuts)
  visual_intensity     ≈ 10–20
  audio_energy_score   ≈ 25–40
  speech_rate_score    ≈ 40–65 (varies by segment)
```
Expected composite range: `22–38`. Spread: `< 16 points`. UX-R3 Strong threshold = `bestScore * 0.85` → if best = 38, threshold = 32.3 → clips 32–38 are "Strong." `[CODE-CONFIRMED]` if spread < 1.5 raw points, ALL tier as "Strong Candidates."

**Predicted friction events:**

| Event | Probability | Root Cause |
|---|---|---|
| All clips labeled "Strong Candidates" | HIGH | Narrow-spread formula behavior, 73.4 not deployed |
| Creator cannot identify which clip to use | HIGH | No differentiation → creator must watch all clips → review fatigue |
| Creator rerenders expecting different ranking | MEDIUM | No structural reason for different ranking → same output |
| Creator reports "all clips look the same" | HIGH | Content is structurally similar → clips ARE similar; formula has no editorial preference signal |

**Expected QA observation:**
> Creator produces 8 exported clips. Opens Review queue. All say "Strong." Watches 3, picks one, doesn't know if it's actually best. Calls feedback: "the AI picks randomly."

**Severity classification:** `P1` — label inflation erodes creator trust in the ranking signal.

---

### 8. Bad Audio / Inconsistent Audio

**Format signature:** Background noise, inconsistent mic distance, silent gaps > 5s, audio spikes. Common in field recordings, mobile recordings, older archival footage.

**Predicted score behavior — two paths depending on `speech_data_active`:**

**Path A: `speech_data_active = False`** (speech analysis not available)
- `silence_penalty` is INACTIVE (`[CODE-CONFIRMED]`)
- `speech_rate_score` uses fallback or is neutral
- Bad audio clips are NOT penalized for silence or speech inconsistency
- `[PREDICTED]` Bad-audio clips score comparably to good-audio clips of same visual content

**Path B: `speech_data_active = True`** (speech analysis available)
- `silence_penalty` fires when `speech_density < 20%`
- Clips with long silences → penalty up to −20pts → may drop below quality floor
- `[PREDICTED]` Silent segments aggressively filtered; only continuous-speech clips survive floor

**Predicted friction events:**

| Event | Probability | Root Cause |
|---|---|---|
| Bad audio clips rank normally (Path A) | MEDIUM | If speech_data not available, formula blind to audio quality → creator gets clips with bad audio |
| Good storytelling clip filtered by silence penalty (Path B) | MEDIUM | Dramatic pause > 20% of clip duration → penalty fires → clip drops below floor → removed |
| Creator's preferred clip is missing from output | MEDIUM | Silence penalty removed a clip with meaningful pause that creator values |
| Inconsistent penalty behavior across rerenders | UNKNOWN | `speech_data_active` state depends on runtime analysis availability; may differ by source file |

**Expected QA observation (Path A):**
> Creator exports clips from field recording. Top clip has noticeable wind noise. Creator expected tool to avoid it. Tool has no signal to differentiate — both clips scored similarly on visual + speech signals.

**Expected QA observation (Path B):**
> Creator's source has a deliberate dramatic pause before a reveal. Silence penalty treats it as dead air. Clip scores 18 → below floor → not exported. Creator doesn't see it in output and doesn't know why.

---

## Top 10 Predicted Friction Events (Cross-Type Priority)

Ranked by probability × creator impact. All PREDICTED, none observed.

| Rank | Event | Types Affected | Probability | Impact | Root Cause |
|---|---|---|---|---|---|
| 1 | All clips labeled "Strong Candidates" — no differentiation signal | Talking head, podcast, interview | HIGH | HIGH | 73.4 not deployed; narrow-spread formula behavior |
| 2 | Unlimited clip output → review fatigue | Podcast, education, interview | HIGH | HIGH | `max_export_parts=0` default, long sources |
| 3 | Best 45–60s peak not exported as standalone clip | Commentary, reaction | HIGH | HIGH | Emission gate = 61s; sub-gate moments subsumed |
| 4 | Silent quality floor → 1-clip output, no explanation | Finance, low-energy talking head | MEDIUM | HIGH | Floor fires silently; UI shows count but not reason |
| 5 | Best clip in position 3–5 not position 1 | Interview, mixed, education | MEDIUM | MEDIUM | Formula bias toward scene density + visual hook |
| 6 | Rerender produces same result — creator can't improve | Low-energy, finance | HIGH | MEDIUM | No source content change → same candidate pool |
| 7 | Silence penalty removes intentional pause clip | Bad audio (Path B) | MEDIUM | MEDIUM | Silence penalty threshold too aggressive for dramatic content |
| 8 | B-roll clips ranked above interview clips | Mixed content | MEDIUM | MEDIUM | scene_density + visual_intensity formula bias |
| 9 | Interview Q+A arc split — answer clip loses question context | Interview | MEDIUM | MEDIUM | Emission gate doesn't consider editorial arc |
| 10 | Bad audio clips rank normally — creator expects filtering | Bad audio (Path A) | MEDIUM | LOW-MEDIUM | `speech_data_active=False` → silence_penalty inactive |

---

## QA Instrumentation Recommendations

Based on these predictions, QA observers should capture the following data points per session:

**Per render:**
- Number of clips exported (check against source length expectation)
- Positions of clips labeled "Strong Candidates" vs. other tiers
- Whether creator's self-identified "best moment" is in position 1
- Whether quality floor appears to have fired (1-clip result on long source)

**Per content type:**
- Does scene-density-heavy content systematically rank first?
- Does audio quality appear to influence clip ranking?

**Creator signals to watch:**
- Rewatching same clip multiple times (confusion signal)
- Scrolling through Review queue without acting (fatigue signal)
- Asking "why is this one first?" (ranking expectation mismatch signal)
- "I wanted the one where I said X" (self-identified best moment signal)

---

## Known Unknowns

These predictions cannot be resolved without running actual renders:

1. **`speech_data_active` state** — which test renders will have speech analysis available? This determines whether silence_penalty fires.
2. **Actual scene cut density** — predictions about scene_density_score depend on how many cuts yt-dlp/ffmpeg detects per content type.
3. **hook_opening_score per content type** — predictions assume opener quality varies; actual scores depend on specific source content.
4. **Quality floor trigger rate** — 73.3 was designed to fire rarely. Actual trigger frequency is unknown until real renders are run.
5. **Candidate count per content type** — how many 61s+ windows does a 30-min podcast produce? This determines whether review fatigue materializes.

---

## Document Status

This document is a **pre-QA hypothesis only**. It will be updated with observed data after Phase 75 QA sessions complete.

| Section | After QA |
|---|---|
| Each content type friction table | Add CONFIRMED / REFUTED / PARTIAL per event |
| Top 10 priority table | Re-rank based on actual observed frequency |
| Known unknowns | Resolve with actual render output data |
| Root causes confirmed | Mark CODE-CONFIRMED predictions that matched observation |

---

*Generated: 2026-05-19 | Branch: feature/ai-output-upgrade*  
*Code sources: segment_builder.py (lines 77–234), render_pipeline.py (lines 2374–2390), render-ui.js (UX-R3 tier logic)*
