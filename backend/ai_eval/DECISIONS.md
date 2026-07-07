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

**ADDENDUM 2026-07-02 — structural evidence at n=5 (deterministic scorers,
`ai_eval/structural.py`) REINFORCES the KEEP-ON decision and localises the
defect.** Editorial ON is better on 5/7 judge-free metrics (scene_count
48→24, hold_precision 0.17→0.59, beat_coverage 0.38→0.49, discipline 75→82,
episode_balance 61→69) and broken on exactly two: **total-duration control**
(recap/film ratio ranged 0.04–0.96 across samples; ratio_score 81→42 vs the
prompt's own 10–25% band) and **fragment_rate** (0.08→0.18). The LLM judge
remains unreliable for this construct — it gave its highest-ever delta
(+0.937, faithfulness +2) to a "recap" covering 96% of the film's runtime.

**Next action (replaces "flip OFF" consideration):** prompt fix in the
editorial-ON path (pass-2/3) anchoring the 10–25% duration band + minimum
scene length; verify before/after with `duration_ratio_score` +
`fragment_rate` on ≥3 samples. Judge n=14: +0.165 ± 0.160 (inconclusive).

**ADDENDUM 2026-07-02 (later) — defect CLOSED in two layers:**
1. *Prompt anchor* (`RECAP_DURATION_ANCHOR=1`, PROMPT_VERSION 2): post-fix
   n=2 — fragment_rate FIXED (0.18→0.0/0.0), discipline 100/100,
   beat_coverage 0.49→~0.78; duration variance narrowed but band still not
   guaranteed (0.69 sample — the LLM ignores even a HARD budget).
2. *Deterministic reconciler* (`RECAP_TRIM_TO_BAND=1`,
   `RecapPlan.trim_to_duration_band`): cap scenes at 40s → drop non-essential
   scenes globally longest-first (never climax / holds / last-of-episode) until
   the 10–25% band holds. Unit-proven (8 tests); the production guarantee.
Editorial's one measured defect is now governed the same way as shot
boundaries (snap) and beat bindings: prompt guides, determinism guarantees.

**ADDENDUM 2026-07-02 (final, post model-switch) — D-1 rationale UPDATED at
3.5-cell n=7.** On gemini-3.5-flash BOTH arms are structurally near-perfect
(OFF: 18.7 scenes, frag 0, discipline 100, ratio 0.21 in-band; ON: 18.4 /
0 / 100 / 0.18). The OFF-sprawl that motivated "keep for structural
discipline" was largely a **2.5-flash weakness**, not an intrinsic pipeline
need. Editorial's remaining measured edge on the production stack is modest:
beat_coverage +0.09, episode_balance +11; judge +0.125 ± 0.230 (inconclusive,
ON 2/7). **Decision stands: KEEP ON** (small positive, no measured harm,
cheap — and only one 91-min film tested; longer/harder sources may still
sprawl where editorial matters). But the strong discipline rationale is now
historical; re-evaluate if a future model change or cost pressure makes the
extra pass worth questioning. This addendum exists because the harness's job
is to UPDATE conclusions when evidence changes.

---

## D-2 — GEMINI_DEFAULT_MODEL 2.5→3.5 Flash · Decision: **RECOMMEND SWITCH** (2026-07-02)

**Measurement:** `ai_eval/ab_model_upgrade.py` — full-stack recap A/B
(story + editorial + recap all pinned per arm), judge FIXED at
`gemini-2.5-flash` for both arms (self-preference bias favours arm A,
so a B win is conservative). Store:
`ai_eval/measurements/model_35flash.jsonl` (n=3, 1 film).

**Evidence (n=3, 1 film, judge=2.5-flash):**
- Δ weighted **+0.416 ± 0.119 SE** → **B better** (|mean| > 2·SE). B wins 3/3.
- Per-criterion: pacing_suspense **+1.0**, story_coverage **+0.667**,
  faithfulness **+0.667** (the hard-gate criterion improves — the D-1
  editorial faithfulness dent does not reproduce on 3.5).
- Structural (judge-free): scene_count 24.7→16.7 (tighter),
  beat_coverage 0.67→0.87, episode_balance 77→92, duration ratio in
  band on both arms. Only regression: hold_precision 0.89→0.61.
- Compat smoke: 3.5-flash accepts the provider's existing
  `thinking_config.thinking_budget` + `temperature` config unchanged
  (backward-compat per Google docs; `thinking_level` migration optional).
- Quota: free-tier 2.5-flash is now **20 req/day/key**
  (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`); 3.5-flash quota
  is per-model → switching also relieves 2.5 quota pressure.

**How to switch:** `GEMINI_DEFAULT_MODEL=gemini-3.5-flash` in `.env`
(zero code change). Flipping the hardcoded default in
`providers/gemini.py` is HIGH-tier + requires updating
`tests/test_gemini_default_model.py`.

**Caveats (same as D-1):** one film, single-provider judge, n=3. Meets
the directional bar, not the "cross-provider judge + ≥3 films" ship bar.
Revisit if production recaps regress (esp. hold_precision — 3.5 marks
fewer hold scenes).

---

## CM-7 — Content Mode quality planning (`CONTENT_PLAN_MODE=quality`), 2026-07-07

**What:** an opt-in second narration-refine pass over the Content Mode plan,
reusing the existing refine prompt via `content_director` (no new prompt).
Measured with `ab_content_quality` (new harness): Arm A = fast (base plan),
Arm B = the SAME base plan with the refine applied, so the delta isolates the
refine pass alone.

**Result (n=3, 1 script, gemini judge == generator):** NO measured gain.
- Δ weighted = **−0.111 ± 0.091 → inconclusive**; QUAL wins **0/3**.
- narration_fluency / time_fit / engagement Δ = **+0.000**; faithfulness **−0.333**.
- The refine consistently SHORTENS narration (e.g. 1241→967 chars); one run
  dropped a fact → a faithfulness dip, with no fluency/time-fit uplift to offset.

**Decision:** keep `CONTENT_PLAN_MODE=fast` (default). Per the general rule
below, a gated flag flips ON only on a measured gain — this shows none (and a
slight faithfulness-regression risk). Ships OFF = byte-identical, zero risk.

**Caveats:** n=3, single script/topic, single-provider judge (self-preference
bias). Directional only — re-run with a cross-provider judge + ≥3 scripts before
any reconsideration.

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
| `CONTENT_PLAN_MODE` | fast (OFF) | **Gated, measured NO-gain** — CM-7 (Δ−0.11, 0/3, faithfulness dip) | ab_content_quality |

**General rule:** flip a gated flag ON only after a measured gain (cross-provider
judge + ≥3 sources). Until then they ship OFF = byte-identical, zero risk.
