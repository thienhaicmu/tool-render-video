"""
ab_story_plan.py — measure the Story super-plan across a config ablation, scored by
the judge-free structural instrument (structural_story). No LLM judge → no quota
beyond the plan calls themselves, and the verdict never moves between arms.

Default ablation: F-05 native JSON Schema ON (arm A) vs OFF (arm B), everything
else held constant. Both arms regenerate the plan (the LLM cache is cleared between
them) and record the full structural report + config vector to a JSONL store, so the
accumulation file becomes an ablation database (query later, no re-run).

Usage (from backend/, OPENAI_API_KEY in .env):
    python -m ai_eval.ab_story_plan                       # all samples, schema on/off
    python -m ai_eval.ab_story_plan --sample story_revenge_vi --runs 2
    python -m ai_eval.ab_story_plan --provider openai --model gpt-4o \
        --store ai_eval/measurements/story_schema.jsonl

n<5 is a directional signal, not a statistic (see DECISIONS.md). This is a
measurement tool, not a pytest — the scorers themselves are unit-tested in
tests/test_structural_story.py.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import app.core.config  # noqa: F401 — loads .env (API keys) before anything reads them
from app.features.render.ai.llm import generate_story_plan_v2
from app.features.render.ai.llm.cache import llm_cache_clear
from ai_eval.runmeta import config_vector
from ai_eval.structural_story import story_structural_report, summarize_story_structural

_SAMPLES_DIR = Path(__file__).with_name("samples")
_LANG = {"vi": "vi", "en": "en", "ja": "ja"}


def _sample_text(name: str) -> tuple[str, str]:
    """Return (text, language) for a sample stem. Language inferred from the _xx suffix."""
    path = _SAMPLES_DIR / f"{name}.txt"
    text = path.read_text(encoding="utf-8")
    lang = "vi"
    for code in _LANG:
        if name.endswith(f"_{code}"):
            lang = code
            break
    return text, lang


def _one_arm(*, provider, model, chapter, language, use_schema, api_key) -> dict:
    """Generate a plan with json_schema forced on/off, score it structurally."""
    os.environ["OPENAI_STORY_JSON_SCHEMA"] = "1" if use_schema else "0"
    llm_cache_clear()   # force a fresh call (cache is namespaced by prompt+schema ver)
    t0 = time.perf_counter()
    plan = generate_story_plan_v2(
        provider=provider, source="paste", chapter=chapter, language=language,
        api_key=api_key, model=model,
    )
    dt = round(time.perf_counter() - t0, 2)
    report = story_structural_report(plan)
    return {
        "arm": "schema_on" if use_schema else "schema_off",
        "usable": plan is not None,
        "latency_sec": dt,
        "structural": report,
        "config": config_vector(OPENAI_STORY_JSON_SCHEMA=("1" if use_schema else "0")),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Story super-plan structural A/B (F-05 schema on/off)")
    ap.add_argument("--sample", default="", help="sample stem (default: all in ai_eval/samples/story_*)")
    ap.add_argument("--provider", default=os.getenv("STORY_AI_PROVIDER", "openai"))
    ap.add_argument("--model", default=os.getenv("STORY_SUPER_MODEL", "gpt-4o"))
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--store", default="ai_eval/measurements/story_schema.jsonl")
    args = ap.parse_args()

    api_key = (os.getenv("OPENAI_API_KEY", "") or "").strip()
    if not api_key and args.provider == "openai":
        print("!! OPENAI_API_KEY not set — cannot run", flush=True)
        return 2

    if args.sample:
        stems = [args.sample]
    else:
        stems = sorted(p.stem for p in _SAMPLES_DIR.glob("story_*.txt"))
    if not stems:
        print("!! no samples found in", _SAMPLES_DIR, flush=True)
        return 2

    store = Path(args.store)
    store.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with store.open("a", encoding="utf-8") as fh:
        for stem in stems:
            chapter, language = _sample_text(stem)
            print(f"\n=== {stem} (lang={language}, {len(chapter)} chars) ===", flush=True)
            for run in range(1, args.runs + 1):
                for use_schema in (True, False):
                    arm = _one_arm(provider=args.provider, model=args.model,
                                   chapter=chapter, language=language,
                                   use_schema=use_schema, api_key=api_key)
                    print(f"  run{run} {arm['arm']:10s} usable={arm['usable']} "
                          f"{summarize_story_structural(arm['structural'])} ({arm['latency_sec']}s)",
                          flush=True)
                    fh.write(json.dumps({"sample": stem, "language": language, "run": run,
                                         **arm}, ensure_ascii=False) + "\n")
                    rows += 1
    print(f"\nwrote {rows} row(s) → {store}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
