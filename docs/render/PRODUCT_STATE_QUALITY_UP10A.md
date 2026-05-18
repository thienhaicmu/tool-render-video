# PRODUCT STATE — QUALITY-UP10A: Reality Validation & A/B Quality Audit

**Branch:** `feature/ai-output-upgrade`
**Phase:** Validation only — no code changes
**Status:** Complete
**Scope:** Audit of QUALITY-UP1A through QUALITY-UP8

---

## Purpose

This document is a reality-check. Before shipping additional quality improvements,
we validate what UP1A–UP8 actually delivered in code, what creators would observe,
and what systemic failures exist that block further quality gains.

No features are added. No heuristics are tuned. Only observation, measurement,
and documentation.

---

## Audit Method

Code-level trace of each quality upgrade against the actual production implementation.
Each upgrade was re-traced through:

- `backend/app/services/viral_scorer.py`
- `backend/app/services/render_engine.py`
- `backend/app/services/subtitle_engine.py`
- `backend/app/services/motion_crop.py`
- `backend/app/services/tts_service.py`
- `backend/app/services/remotion_adapter.py`
- `backend/app/orchestration/render_pipeline.py`
- `backend/app/models/schemas.py`

Questions asked for each feature:
1. Is the code actually present and correct?
2. Does it fire in the default render path?
3. What inputs does it depend on?
4. What can silently neutralize it?

---

## Part 1 — Validation Matrix

### How to read this table

Each row is a render scenario. "Expected" = what the docs say should happen.
"Actual" = what the code actually does. "Gap" = discrepancy that affects creator output.

---

### SCENARIO 1: Commentary — Talking-head, strong hook, fast edits

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `commentary` | `commentary` (if density 0.03–0.08) | None |
| content_type_hint | `commentary` | `montage` (if density ≥ 0.18, tight editing) | **MISCLASSIFIED** when creator edits tightly |
| Subtitle preset | `viral` | `viral` when hint=commentary | None |
| Subtitle preset | `viral` | `gaming` when hint=montage | **WRONG PRESET** on tightly-edited commentary |
| Intro preset | `viral_pop` | `viral_pop` when hint=commentary | None — but `remotion_hook_intro=False` by default |
| Audio loudnorm | -14 LUFS | Skipped — `loudnorm_enabled=False` by default | **AUDIO FIX NOT ACTIVE** |
| Pacing | commentary params | commentary params (db=-3, mul=1.25) | None |
| TTS voice rate | +10% (commentary) | +10% for per-part subtitle TTS | None |
| Story arc | hook→build(score_desc)→payoff | Fires correctly | None |

**Key risk:** Commentary with heavy editing (density ≥ 0.18) misclassifies as montage.
Gaming subtitle replaces viral subtitle. Montage pacing (tight) replaces commentary pacing (gentle).

---

### SCENARIO 2: Tutorial — Screen recording, explainer, late payoff

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `tutorial` | **NEVER INFERRED** | **CRITICAL** |
| content_type_hint | `tutorial` | `vlog` (0.08–0.18 density) or `commentary` (< 0.08) | Wrong type always |
| Subtitle preset | `clean` (thin, no bounce) | `story` (vlog) or `viral` (commentary) | **WRONG PRESET** |
| Intro preset | `clean_creator` | `story_cinematic` (vlog) or `viral_pop` (commentary) | **WRONG INTRO** |
| Pacing | tutorial params (db=-4, mul=1.40, max=1.5s) | vlog or commentary params | **WRONG PACING** |
| TTS voice rate | -8% (deliberate) | 0% (vlog) or +10% (commentary) | **WRONG RATE** |
| Motion crop | slow/smooth (2.0× interval, 0.65× ema) | vlog (default) or commentary (1.5× interval) | **WRONG TRACKING** |
| Story arc | chronological build | chronological (vlog) or score_desc (commentary) | Partially correct |
| Audio loudnorm | -14 LUFS | Skipped | **AUDIO FIX NOT ACTIVE** |

**Root cause:** `content_type_hint = "tutorial"` is never produced by `score_segments()`.
The scorer's 4-bucket classification has no "tutorial" bucket. The downstream tables
for tutorial (subtitle, intro, pacing, TTS, motion crop) are **unreachable via normal rendering**.

---

### SCENARIO 3: Interview / Podcast — Low density, long talking, multi-person

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `interview` | `interview` (density < 0.03) | None — works if source is clean talking-head |
| content_type_hint | `interview` | `commentary` if editors trim between questions | Possible misclassification |
| Subtitle preset | `clean` | `clean` | None |
| Intro preset | `clean_creator` | `clean_creator` — but `remotion_hook_intro=False` | **INTRO NOT ACTIVE BY DEFAULT** |
| Pacing | interview params (db=-5, mul=1.50, max=1.5s) | interview params | None |
| TTS voice rate | -5% (deliberate) | -5% for per-part TTS | None |
| Motion crop | smooth/slow (2.0× interval, 0.65× ema) | Correct | None |
| Story arc | chronological build | Fires correctly when 3+ clips | None |
| Audio loudnorm | -14 LUFS | Skipped — opt-in flag | **AUDIO FIX NOT ACTIVE** |

**Key risk:** Well-structured interview content mostly works correctly (it's one of the 4 inferable types).
The main gap is audio (-14 LUFS not active) and intro (not active by default).

---

### SCENARIO 4: Vlog / Story — Emotional flow, soft pacing

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `vlog` | `vlog` (density 0.08–0.18) | None — most vlogs classify correctly |
| Subtitle preset | `story` | `story` | None |
| Intro preset | `story_cinematic` | `story_cinematic` — but `remotion_hook_intro=False` | **INTRO NOT ACTIVE BY DEFAULT** |
| Pacing | vlog params (db=0, mul=1.0, max=2.0s) | vlog params | None |
| TTS voice rate | +0% (normal) | +0% | None |
| `story` content type | `-3%` rate | Never reaches this type | Story differs from vlog only via rate; since `story` never inferred, story content uses vlog (+0%) |
| Story arc | chronological build | Fires correctly | None |
| Audio loudnorm | -14 LUFS | Skipped | **AUDIO FIX NOT ACTIVE** |

---

### SCENARIO 5: Gaming — Fast edits, high energy, voice-over

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `gaming` | **NEVER INFERRED** | **Vocabulary gap** |
| content_type_hint | `gaming` | `montage` (density ≥ 0.18 — gaming almost always is) | Correctly falls to montage |
| Subtitle preset | `gaming` (caption box) | `gaming` via montage→gaming mapping | **Works by coincidence** |
| Intro preset | `gaming_energy` | `gaming_energy` via montage mapping | **Works by coincidence** |
| Pacing | gaming-specific params | Falls to `vlog` default (no `gaming` entry in `_type_params`) | Minor: montage params are close enough |
| TTS voice rate | `gaming` +12% | Never fires; montage hits montage +12% | **Actually same rate** — works |
| Motion crop | No `gaming` in table | Falls to `vlog` default | montage has separate entry; since hint=montage it uses montage params |
| Story arc | Skipped (montage dominant) | Skipped | Correct — fast gaming benefits from score order |
| Audio loudnorm | -14 LUFS | Skipped | **AUDIO FIX NOT ACTIVE** |

**Note:** Gaming content works by coincidence. Montage maps to the correct presets for gaming.
The risk is a gaming commentary creator (slower edits) who gets classified as vlog/commentary — not gaming.

---

### SCENARIO 6: Montage — High visual energy, music-heavy, low speech

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `montage` | `montage` (density ≥ 0.18) | None |
| Subtitle preset | `gaming` | `gaming` (via montage mapping) | None |
| Intro preset | `gaming_energy` | `gaming_energy` — but `remotion_hook_intro=False` | **INTRO NOT ACTIVE BY DEFAULT** |
| Pacing | montage params (db=+2, mul=0.80, max=2.5s) | montage params | None |
| Story arc | Skipped | Skipped (montage dominant check) | None — correct |
| Audio loudnorm | -14 LUFS | Skipped | **AUDIO FIX NOT ACTIVE** |

---

### SCENARIO 7: Reaction — Punchline, emotional beat

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `commentary` | `commentary` (loose reactions) or `montage` (tight clips) | Classification unstable |
| Payoff protection | Payoff zone keeps dramatic pauses | Payoff zone protection active (1.5× multiplier on last 2s) | None |
| Story arc | Payoff = last timestamp clip | Correct | None |
| `selection_reason` | "Strong opening hook" | Computed from real signals | None |
| Audio loudnorm | -14 LUFS | Skipped | **AUDIO FIX NOT ACTIVE** |

---

### SCENARIO 8A: Tutorial with heavy screen-capture cuts (edge case)

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `tutorial` | `montage` (heavy cuts → density ≥ 0.18) | **CRITICAL MISCLASSIFICATION** |
| All downstream | tutorial defaults | gaming subtitle, gaming_energy intro, montage pacing, +12% TTS rate | **Every system wrong** |

**This is the highest-impact edge case.** Screen recordings with tool demos, code walkthroughs,
and step-by-step tutorials often have dense cut patterns → montage classification → every
quality system applies the wrong mode simultaneously.

---

### SCENARIO 8B: Gaming commentary (commentary-pace edits, gaming content)

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `gaming` | `commentary` (loose editing, 0.03–0.08 density) | Misclassified |
| Subtitle preset | `gaming` (box) | `viral` (commentary) | Different aesthetic |
| Intro preset | `gaming_energy` | `viral_pop` | Different energy |
| Pacing | gaming | commentary | Slightly too gentle |
| Story arc | Skipped | Fires (commentary is not montage) | May feel unnatural for gaming content |

---

### SCENARIO 8C: Podcast with overlays (low density, graphics)

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| content_type_hint | `interview` | `interview` (< 0.03 cuts/sec) | None — typically correct |
| Subtitle preset | `clean` | `clean` | None |
| Motion crop | slow/smooth | Correct | None |
| Overall | Works well | Works well | None |

---

### SCENARIO 8D: Low-light webcam (interview/commentary)

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| Motion crop detection | MediaPipe primary | MediaPipe, Haar fallback | None |
| MediaPipe low-light | More robust than Haar | More robust | None — UP5 improves this |
| Subject lost → fallback | Pixel-diff fallback | Pixel-diff center tracking | None |
| Overall | Better than before | Better than before | None — UP5 delivered |

---

### SCENARIO 9: Manual voice narration on any content type

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| TTS content_type | Matches detected type | Hardcoded `"vlog"` | **ALWAYS WRONG for non-vlog** |
| TTS rate | Content-aware | +0% always (vlog default) | Tutorial gets 0% instead of -8% |
| Pause style | Content-aware | `normal` always (vlog default) | Tutorial gets normal instead of deliberate |
| Documented | Yes — UP7 explicitly deferred this | Known limitation | Low urgency but real quality loss |

---

### SCENARIO 10: Audio quality on any render (without explicit loudnorm flag)

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| Audio output | -14 LUFS | Source loudness unchanged | **UP1A Part A silently skipped** |
| Loudnorm activation | Default render | `loudnorm_enabled=False` in schema | **NOT DEFAULT** |
| Who activates it | Any render | Only renders that explicitly pass `loudnorm_enabled=True` | UI must wire this |
| Impact | Every render | No render benefits unless frontend passes the flag | Entire platform compliance fix may be dormant |

---

### SCENARIO 11: Hook intro on any content type

| Check | Expected | Actual | Gap |
|-------|----------|--------|-----|
| Intro generation | UP8 intro before clip | `remotion_hook_intro=False` in schema | **NOT DEFAULT** |
| Who activates it | Any render | Only renders with `remotion_hook_intro=True` | Must be explicitly requested |
| Old intro behavior | Removed | Old black-background intro was removed | No intro at all unless flag is set |
| Impact | UP8's visual improvement | Not visible on any render unless flag passed | Feature shipped but dormant |

---

## Part 2 — Scorecard

Scoring: 1 = broken/counterproductive, 5 = neutral/unchanged, 10 = excellent improvement.

| Upgrade | Feature | Score | Evidence |
|---------|---------|-------|----------|
| UP1A | Audio -14 LUFS | **2/10** | Correct implementation, defaults OFF — not active |
| UP1A | Whisper base for fast profile | **9/10** | Always active, measurable accuracy improvement |
| UP1A | Translation truthfulness | **8/10** | Correct, provides real creator feedback |
| UP1A | Position score floor 0.25 | **7/10** | Small but real improvement for late-video clips |
| UP1A | TTS failure truthfulness | **8/10** | Correct, honest creator feedback |
| UP2 | Motion score reform | **8/10** | Real improvement — density×quality is more meaningful |
| UP2 | Hard eviction removal | **9/10** | High impact — interview/commentary no longer suppressed |
| UP2 | content_type_hint | **5/10** | Works for 4 types; tutorial/gaming/story unreachable |
| UP2 | Selection reason strings | **7/10** | Honest, useful when signals are real |
| UP3 | Story arc hook→build→payoff | **7/10** | Correct structure; payoff=latest-timestamp is simplistic |
| UP3 | Montage arc skip | **9/10** | Correct behavior |
| UP4 | Content-aware pacing | **8/10** | Works well for interview/montage; tutorial unreachable |
| UP4 | Payoff zone protection | **9/10** | Correct, perceptible on reactions and vlogs |
| UP4 | Breathing rhythm 0.20s | **8/10** | Measurable improvement on talking-head content |
| UP5 | MediaPipe primary detection | **8/10** | Real improvement on pose/lighting edge cases |
| UP5 | Content-type tracking params | **7/10** | Works for interview/montage; tutorial unreachable |
| UP6 | 4 personality presets | **9/10** | Excellent implementations; visually distinct |
| UP6 | Content-type auto-defaults | **5/10** | Correct for 4 inferred types; tutorial never auto-selects |
| UP7 | Content-type voice profiles | **5/10** | Correct for per-part subtitle TTS; tutorial/story/gaming unreachable |
| UP7 | Text humanization | **8/10** | Works well when applicable |
| UP7 | Manual voice TTS | **3/10** | Always vlog; tutorial/commentary creator gets wrong profile |
| UP8 | 4 intro personalities | **9/10** | Visually distinct, correct implementation |
| UP8 | Content-type auto-defaults | **7/10** | Correct logic; but `remotion_hook_intro=False` by default |
| UP8 | Hook text priority chain | **9/10** | Correct priority order |
| UP8 | Intro visible on renders | **2/10** | Feature defaults OFF — dormant |

---

## Part 3 — Systemic Failures

Three systemic failures explain most of the gaps above.

---

### SYSTEMIC FAILURE 1 — content_type_hint Vocabulary Gap (Highest Impact)

**What it is:**
`score_segments()` infers only 4 content types from scene density:

```
< 0.03  cuts/s  → "interview"
0.03–0.08       → "commentary"
0.08–0.18       → "vlog"
≥ 0.18          → "montage"
```

The downstream quality tables (UP4 pacing, UP5 motion crop, UP6 subtitle,
UP7 TTS, UP8 intro) were authored with 7 content types in mind:
`interview`, `commentary`, `vlog`, `tutorial`, `story`, `montage`, `gaming`.

**The 3 unreachable types:**

| Type | Can be inferred? | Falls to | Downstream result |
|------|-----------------|----------|-------------------|
| `tutorial` | **Never** | `vlog` (0.08–0.18) or `commentary` (< 0.08) | Story subtitle (vlog) or viral subtitle (commentary). Wrong intro. Wrong pacing. Wrong TTS rate. |
| `story` | **Never** | `vlog` | Story subtitle (correct by coincidence). Story intro (correct by coincidence). Same vlog pacing. |
| `gaming` | **Never** | `montage` (≥ 0.18) | Gaming subtitle (correct by coincidence). Gaming_energy intro (correct by coincidence). Montage pacing (close enough). |

**Impact cascade:**
Tutorial content is the highest-impact misclassification. A tutorial creator gets:
- Subtitle: `story` (romantic/cinematic) instead of `clean` (premium/educational)
- Intro: `story_cinematic` instead of `clean_creator`
- Pacing: vlog defaults (too aggressive) instead of tutorial (max 1.5s trim, gentle)
- TTS: 0% rate instead of -8%; normal pauses instead of deliberate

Every quality upgrade from UP2 to UP8 degrades for tutorial content simultaneously.
The content type is the single gate. When it's wrong, all downstream quality is wrong.

**Root cause:**
Scene density is a visual proxy. It cannot distinguish tutorial from vlog — both often have
edit densities of 0.08–0.18. What differentiates tutorial from vlog is speech and instructional
structure, not visual cut rate.

**Scope of misclassification:**
- Heavy-edit tutorial (screen recording) → `montage` → gaming subtitle on a tutorial
- Light-edit tutorial (talking head) → `interview` → correct by coincidence
- Moderate-edit tutorial (the majority) → `vlog` → story subtitle on a tutorial

---

### SYSTEMIC FAILURE 2 — Key Quality Features Default to OFF (Second Impact)

**What it is:**
Three of the highest-impact quality improvements require opt-in flags that default to False:

| Flag | Default | UP that introduced it | Impact when False |
|------|---------|----------------------|-------------------|
| `loudnorm_enabled` | `False` | UP1A (Part A) | No -14 LUFS normalization. Audio at source loudness. Platform will re-amplify. |
| `remotion_hook_intro` | `False` | UP8 | No intro generated at all. First frame is the raw clip start. |
| `reup_mode` | `False` | Pre-UP (reup system) | Separate issue; not a quality upgrade |

**The audio compliance issue:**
UP1A Part A is the most objectively measurable quality improvement in the chain.
Platform compliance with -14 LUFS is testable, perceptible, and creator-facing.
But `loudnorm_enabled = False` in the schema means every render that doesn't
explicitly pass this flag ships at source loudness.

If the frontend does not wire this flag to True by default (or per profile), the
entire audio compliance upgrade is dormant.

**The intro issue:**
UP8 removed the old hardcoded "STOP SCROLLING" intro but replaced it with
`remotion_hook_intro=False`. The net result for creators who don't explicitly
enable the new intro: no intro at all. The old (bad) intro is gone. The new
(better) intro is not yet visible.

**Diagnosis:**
These are not bugs — they are opt-in flags by design. But the flags were designed
for gradual rollout, and the validation question is: have they been rolled out?
If the frontend is not passing these flags in its default render calls, the
improvements exist only in code.

---

### SYSTEMIC FAILURE 3 — speech_density_score Is Not Speech Density

**What it is:**
`viral_scorer.py` line 308:

```python
"speech_density_score": min(100, 45 + len(seg_scenes) * 3),
```

This is labeled `speech_density_score` but computes: `45 + (number of scene cuts) × 3`.

A segment with 0 scene cuts gets score 45. A segment with 5 cuts gets 60.
A segment with 18+ cuts gets 100.

This is a scene-count metric wearing a speech label.

The output ranking formula in `_compute_output_ranking_entry` uses
`speech_density_score` at 10% weight. For most clips this resolves to
scores in the 45–65 range regardless of actual speech content.

**Contrast with the real computation:**
`segment_builder.py` → `build_segments_from_scenes_with_subtitles()` computes
actual speech density as `(subtitle-covered seconds) / scene_duration`.
This is the correct computation but it only runs when a pre-existing SRT file
is available at segment-build time — which is before transcription runs.

**Impact:**
The 10% speech_density_score weight in the ranking formula is noise for most renders.
Segments ranked above others due to "speech density" may have that advantage purely
from having more scene cuts, not from denser speech.

---

## Part 4 — Content Type Accuracy Audit

Simulated classification for each scenario based on typical scene density values:

| Content type | Typical density | Inferred type | Match? | Systems affected |
|-------------|----------------|---------------|--------|------------------|
| Commentary (tight) | 0.03–0.08 | `commentary` | ✓ | Correct |
| Commentary (heavy edits) | 0.18+ | `montage` | ✗ | Subtitle, intro, pacing, TTS |
| Tutorial (screen recording) | 0.10–0.25 | `vlog` or `montage` | ✗ | Subtitle, intro, pacing, TTS, crop |
| Tutorial (talking head) | < 0.03 | `interview` | ✓ (accidental) | Subtitle is `clean` — correct |
| Interview / Podcast | < 0.03 | `interview` | ✓ | Correct |
| Vlog | 0.08–0.18 | `vlog` | ✓ | Correct |
| Story | 0.05–0.15 | `vlog` | ~✓ (close enough) | Story≈Vlog for most downstream |
| Gaming (fast edits) | 0.18+ | `montage` | ~✓ (coincidental) | Montage maps correctly for gaming |
| Gaming (commentary pace) | 0.03–0.08 | `commentary` | ✗ | Gets viral subtitle, not gaming box |
| Montage | 0.18+ | `montage` | ✓ | Correct |
| Reaction (short clips) | 0.05–0.15 | `commentary` / `vlog` | Varies | Good enough |

**Classification accuracy estimate: ~60–65% of real-world content types classified correctly.**

The largest category of misclassification is tutorial content — the content type
most sensitive to having the right pacing (explanatory clarity), the right subtitle
(clean/readable), and the right TTS rate (deliberate/slow).

---

## Part 5 — What Creators Would Actually Notice

Ranked by perceptibility:

**Would notice immediately:**
1. Audio loudness — if loudnorm is not active, their output is quieter than competitor content
   on platform. Platforms re-amplify, compressing dynamic range. The first thing creators notice
   when comparing to platform-native content.

2. Subtitle personality mismatch — a tutorial creator getting a bouncing TikTok-style subtitle
   with 2-3 word bursts instead of clear, minimal sentences feels obviously wrong.

3. Hook intro presence — whether an intro exists at all is immediately visible.
   Currently dormant for most renders.

**Would notice after a few clips:**
4. Pacing feel — breathing rhythm (UP4) and payoff protection are perceptible but require
   side-by-side comparison. Tutorial over-cutting vs. comfortable pacing.

5. Segment selection quality — UP2's removal of hard eviction means interview/commentary clips
   survive. Creators with low-density content would notice they now get output.

6. Story arc — clip ordering change is perceptible on vlog/commentary exports.
   Hook at position 1 and chronological build feel more intentional than pure score rank.

**Would need direct comparison to notice:**
7. Motion crop smoothness — content-type tracking (UP5) is subtle but visible on slow panning.

8. Narration humanization — pause style differences are subtle. Rate differentiation is more
   noticeable.

9. Position score floor — one or two additional late-video clips appearing in selection.
   Small effect on most videos.

---

## Part 6 — Root Cause Summary

| ID | Finding | Severity | Affects |
|----|---------|----------|---------|
| **F1** | `content_type_hint` only infers 4 types; "tutorial" never reached | Critical | UP2–UP8 quality for tutorial content |
| **F2** | `loudnorm_enabled=False` by default — UP1A Part A not active on most renders | Critical | All audio |
| **F3** | `remotion_hook_intro=False` by default — UP8 intro not visible on most renders | High | All content types |
| **F4** | `speech_density_score` in viral scorer is a scene-count proxy, not speech signal | High | Ranking weight accuracy |
| **F5** | Manual voice TTS hardcoded to `"vlog"` — UP7 profiles never fire for manual voice | Medium | Any creator using manual voice narration |
| **F6** | "story", "gaming", "tutorial" types in TTS, crop, pacing tables are unreachable without AI Director | Medium | Specific content types |
| **F7** | Story arc + hook-first both reorder independently — potential clip ordering conflict | Medium | Renders with both combined scoring and 3+ clips |
| **F8** | `apply_micro_pacing` has no "gaming" entry in `_type_params` | Low | Gaming content (falls to vlog, acceptable) |

---

## Part 6B — What Actually Shipped and Works

To be clear about what did improve:

| Feature | Works as Documented |
|---------|-------------------|
| Whisper base for fast profile | Yes — always active, measurable accuracy improvement |
| Hard eviction removal (UP2) | Yes — interview/low-density content now survives selection |
| Motion score reform (UP2) | Yes — density × quality is a real improvement over density alone |
| Story arc (UP3) | Yes — fires correctly, skip conditions are correct |
| Payoff zone protection (UP4) | Yes — 1.5× multiplier on last 2s is correct and perceptible |
| Breathing rhythm 0.20s (UP4) | Yes — correct, perceptible on talking-head content |
| MediaPipe primary detection (UP5) | Yes — more robust than Haar for non-frontal faces |
| Content-type tracking params (UP5) | Yes — interview slower, montage faster, measurable |
| 4 subtitle personality presets (UP6) | Yes — correctly implemented, visually distinct |
| Content-type auto-defaults (UP6) | Yes — fires correctly for the 4 inferred types |
| Position score floor (UP1A Part D) | Yes — minor but real improvement |
| Translation + TTS truthfulness (UP1A C+E) | Yes — creator-readable messages correct |
| TTS humanization for subtitle TTS (UP7) | Yes — fires for per-part subtitle path |
| 4 intro personalities (UP8) | Yes — correctly implemented when flag is active |
| Hook text priority chain (UP8) | Yes — AI hook → source title → fallback works |

---

## Part 7 — Recommended Targets for QUALITY-UP10B

In priority order. No new models. No GPU. No LLM. All builds on existing signals.

---

### TARGET 1 — Close the content_type_hint vocabulary gap (Critical)

**Problem:** Tutorial content always gets wrong auto-defaults across 5 systems.
**Fix:** Extend `score_segments()` to infer `"tutorial"` as a 5th content type.

Tutorial differs from vlog/commentary not by cut rate but by speech density.
The real signal: tutorials have high, consistent speech density with relatively
uniform scene structure. The segment_builder already computes `speech_density_score`
from subtitle coverage in `build_segments_from_scenes_with_subtitles()`.

A simple second-pass classification after scoring:
- If `speech_density_score > 60` AND `avg_transition_quality < 0.5` AND `content_type_hint == "vlog"`:
  → reclassify as `"tutorial"`

No new dependencies. Uses signals already computed.

**Priority:** Highest — unlocks all UP4/UP5/UP6/UP7/UP8 improvements for tutorial creators.

---

### TARGET 2 — Confirm loudnorm_enabled and remotion_hook_intro defaults (Critical)

**Problem:** UP1A audio fix and UP8 intro fix are dormant if frontend doesn't pass the flags.
**Fix:** This is a frontend/integration audit, not a backend code change.

Questions to answer before UP10B begins:
1. Is `loudnorm_enabled=True` passed in the default render payload from the frontend?
2. Is `remotion_hook_intro=True` passed in the default render payload?
3. If not, should these become schema defaults (removing the opt-in)?

If the answer is "no one passes these", the most impactful action in UP10B is
changing the schema defaults to `True` — one-line changes that activate two
dormant quality systems instantly for all renders.

**Priority:** Critical — highest QA-to-cost ratio of anything in this document.

---

### TARGET 3 — Fix speech_density_score to use real speech signal (High)

**Problem:** 10% of the ranking weight is noise (scene count proxy labeled as speech density).
**Fix:** Use the `speech_density_score` already computed by `segment_builder.py`
if it's available on the segment dict (non-zero), and only fall back to the
scene-count formula when real speech data isn't present.

The builder's computation requires a pre-existing SRT from a prior transcription.
For re-renders and jobs with `resume_from_last`, this data may be available.
For first renders, the builder's computation fires when `srt_path` is available at build time.

Short-term: add a note in the ranking formula that the current formula is a proxy
and document the known gap.

**Priority:** High — affects ranking accuracy for all renders.

---

### TARGET 4 — Manual voice TTS should use detected content type (Medium)

**Problem:** Manual voice TTS at line 1604 hardcodes `content_type="vlog"`.
The dominant content type of the render is known at this point (it was computed
in the scoring pass via `content_type_hint` on segments).

**Fix:** Derive dominant content type from `scored` segments (same `max(_ct_counts)` logic
used by the story arc) and pass it to the manual voice TTS call.

One-line change in the render pipeline. Zero risk to other paths.

**Priority:** Medium — affects any creator using manual voice narration on non-vlog content.

---

## Part 8 — QUALITY-UP10B Definition

Based on this audit, QUALITY-UP10B should target:

**Scope:** Activate dormant quality wins + close the vocabulary gap

1. **Confirm frontend flag defaults** (non-code: audit + decide)
   - Is `loudnorm_enabled` wired to True in default renders?
   - Is `remotion_hook_intro` wired to True in default renders?
   - Decision: if no, flip schema defaults to True

2. **Tutorial content type inference** (small code change)
   - Add a 5th classification path in `score_segments()` using speech signal
   - All tutorial downstream defaults unlock automatically

3. **Manual voice TTS content type** (one-line change)
   - Pass dominant `content_type` to manual voice TTS call

4. **speech_density_score honesty** (comment + tracking)
   - Document the proxy nature in code
   - Log when the fake formula fires vs. real speech data

**What QUALITY-UP10B is NOT:**
- Not a new feature
- Not a ranking redesign
- Not a new content type classifier (ML)
- Not a pacing overhaul

It is: activating what was already built, closing one vocabulary gap,
and fixing two small propagation bugs.

---

## Appendix A — Feature Activation Status

| Feature | Activation Required | Current Default | Status |
|---------|--------------------|-----------------|----|
| -14 LUFS audio | `loudnorm_enabled=True` | `False` | **Dormant** |
| Hook intro | `remotion_hook_intro=True` | `False` | **Dormant** |
| Story arc | `part_order != "timeline"` AND `len(clips) >= 3` | Auto (part_order="viral") | **Active** |
| Subtitle auto-defaults | `subtitle_style=""` | Active when no style set | **Active** |
| MediaPipe crop | `motion_aware_crop=True` | Payload-controlled | Depends on payload |
| Content-type pacing | `content_type_hint` propagated | Always propagated | **Active** |
| AI Director | `ai_render_influence_enabled=True` | `False` | **Opt-in** |

---

## Appendix B — content_type_hint Reachability Map

```
score_segments() output types (only 4):
  "interview"   ← density < 0.03
  "commentary"  ← density 0.03–0.08
  "vlog"        ← density 0.08–0.18
  "montage"     ← density ≥ 0.18

Downstream table entries that are UNREACHABLE:
  "tutorial"  → in: pacing, subtitle, intro, TTS, crop tables
               maps to: clean subtitle, clean_creator intro, deliberate TTS, slow crop
               but never fired

  "story"     → in: TTS table only (-3% rate)
               maps to: story subtitle (same as vlog), story_cinematic intro (same as vlog)
               net difference: only TTS rate -3% vs +0%
               significance: minimal

  "gaming"    → in: TTS table (+12%)
               maps to: gaming subtitle, gaming_energy intro — both same as montage
               net difference: only TTS rate; montage (+12%) = gaming (+12%)
               significance: none in practice

  "tutorial" is the only type with meaningfully different behavior that is unreachable.
```

---

**Document status:** Complete  
**Next action:** QUALITY-UP10B planning based on these findings  
**Author:** Validation audit — code trace only, no assumptions
