# Golden Dataset — AI Content-Quality Eval (P0-1)

Frozen inputs the `ai_eval` harness scores AI output against, so every prompt
or flag change can be measured objectively instead of by feel.

## How it works

1. Each `*.json` file in this directory is one **golden case**.
2. `python -m ai_eval.run_eval --dataset tests/fixtures/quality --provider gemini`
   scores every case with an LLM-as-Judge against its feature rubric
   (`ai_eval/rubrics.py`) and prints PASS/FAIL + weighted scores.
3. Snapshot a run as a baseline (`--out ai_eval/baselines/main.json`), then on
   any prompt change re-run with `--baseline ai_eval/baselines/main.json`. A
   weighted-mean drop > tolerance (default 0.3) fails the run (exit 2).

> Run the JUDGE on a **different** provider than the one that generated the
> artifact (reduces self-preference bias), e.g. generate with gemini, judge
> with claude.

## Case schema

```json
{
  "id": "clip_podcast_01",
  "feature": "clip",              // clip | recap | reaction | rewrite
  "source":  {"kind": "podcast", "duration_sec": 3600, "language": "en-US"},
  "inputs":  { "transcript_excerpt": "..." },   // grounding for faithfulness
  "output":  { ... the generated artifact to score ... }
}
```

`output` shapes (what to paste from a real job's `result_json` /
`render_plan_json` / recap plan):

- **clip** — `{ "clips": [{"start","end","title","reason"}], "transcript_excerpt": "..." }`
- **recap** — `{ "story_model": {...}, "scenes": [{"start","end","narration","audio_mode"}], "coverage_pct": 0.0 }`
- **reaction** — `{ "segments": [{"kind","start","end","text?"}] }`
- **rewrite** — `{ "target_language": "vi-VN", "tone": "", "segments": [{"start","end","source_text","rewritten_text"}] }`

## Growing the set

Target: **25 cases** — 5 each of film / podcast / talking-head / gaming /
non-English. Pull real `output` blobs from completed jobs (they persist in
`data/app.db` `result_json` and `render_plan_json`). **Never edit an existing
case** — it invalidates the baseline; add a new file instead.
