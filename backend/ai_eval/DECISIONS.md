# AI Quality — Decision & Verification Log

Living record of the AI-quality flags added on branch `ai-quality-p0`: what was
decided, the evidence behind it, and the exact recipe to re-verify. Update the
"Status" and "Last verified" fields when new measurement arrives.

Measurement caveats that apply to EVERYTHING below (read first):
- The `ai_eval` judge is **single-provider (Gemini judging Gemini)** → self-
  preference bias. Absolute scores are soft; relative deltas (ON vs OFF, same
  judge) are more trustworthy.
- All recap measurement so far is on **ONE film** (91-min Chinese wuxia,
  `data/cache/transcription/2dac...srt`). One film ≠ generalisable.
- A judge score of "no effect" is **not** the same as "no viewer benefit" — the
  judge can't measure real-world retention/watchability.
- To make ANY verdict trustworthy: add a **cross-provider judge**
  (OpenAI/Anthropic) + **≥3 different films**, then re-run the accumulation.

---

## D-1 — RECAP_EDITORIAL_PASS · Decision: **KEEP ON** (2026-07-01)

**Flag:** `RECAP_EDITORIAL_PASS=1` (currently set in `.env`). Runs the pass-2
Editorial Blueprint (episodes + pacing + per-beat narrate/hold) before scene
selection.

**Evidence (n=9, 1 film, Gemini judge):**
- Δ weighted mean **+0.021 ± 0.178 SE** → statistically **no net effect**
  (the initial n=1 "+0.44" was noise). ON wins 5/9.
- Per-criterion: narration_fluency **+0.33**, emotion **+0.33** (ON better);
  chronology **−0.22**, faithfulness **−0.22** (ON worse) → nets ~0.
- CONSISTENT structural effect: ON = 2–3 tight episodes / ~20–48 scenes;
  OFF = 36–91 sprawling scenes.

**Why keep ON despite Δ≈0:** the value is **structural discipline**, not a
judge-measurable quality bump. OFF produces long, choppy, unstructured recaps;
ON reliably yields clean multi-episode structure with pacing + beat metadata.
That discipline plausibly helps real viewers (less choppy) even though this
single-provider judge doesn't reward it. Now cheap thanks to Gemini key
rotation (+1 LLM call/recap).

**⚠️ Watch — the one real risk:** ON dents **faithfulness −0.22**. Faithfulness
is a hard rubric gate (≥4.5) — hallucination risk. If production recaps show
factual drift, revisit immediately.

**Re-verify / conditions to flip to OFF:**
1. Add a cross-provider judge + ≥3 films, then:
   `python -m ai_eval.ab_recap_editorial --srt f1.srt f2.srt f3.srt --runs 3 \
     --judge claude --store ai_eval/measurements/recap_editorial.jsonl`
   Review: `... --aggregate-only --store ai_eval/measurements/recap_editorial.jsonl`
2. **Flip OFF if:** faithfulness mean Δ stays ≤ −0.3, OR production shows
   factual drift, OR the content line prioritises accuracy over structure, OR
   recaps are short/single-episode (editorial adds little).
3. **Confirm ON if:** narration/emotion/structure gains hold AND faithfulness
   recovers to ~0 with a fairer (cross-provider) judge.

Accumulation store: `ai_eval/measurements/recap_editorial.jsonl` (n=9).

---

## Status of the other AI-quality flags

| Flag | Default | Status | Verify with |
|------|---------|--------|-------------|
| `RECAP_EDITORIAL_PASS` | ON (.env) | **Kept ON** — Δ≈0, structural (D-1) | ab_recap_editorial --store |
| `GEMINI_STORY_MAX_TOKENS`/`_THINKING_BUDGET` | 16384/2048 | **Shipped** — fixes StoryModel truncation (0→10 chars, 0→14 beats) | direct story call char/beat count |
| `CLIP_DEDUP_IOU` | 0.7 (active) | **Shipped** — deterministic; unit-tested | test_clip_parser_dedup.py |
| 0D downsampling | active | **Proven** — coverage 42%→85%, reaches 84min | ab_clip_downsample |
| `CLIP_STORY_INTELLIGENCE_DEFAULT` | OFF | **Gated, unmeasured** — 0C not fairly judgeable on foreign-lang film | ab_clip_story_intel (needs EN source) |
| `RANKING_DETERMINISTIC_SPEECH_DENSITY` | OFF | **Gated, unmeasured** — P1-1' | needs clip-quality judge |
| `RECAP_PER_EPISODE_NARRATION` | OFF | **Gated, unmeasured** — P1-2 | ab_recap (narration_fluency delta) |
| `CLIP_PROMPT_FOCUSED` | OFF | **Gated, unmeasured** — P1-4 | ab_clip (clip-quality judge) |

**General rule:** flip a gated flag ON only after a measured gain (cross-provider
judge + ≥3 sources). Until then they ship OFF = byte-identical, zero risk.
