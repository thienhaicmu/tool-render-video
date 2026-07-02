"""
ab_model_upgrade.py — measure a generator-model swap (default: gemini-2.5-flash
→ gemini-3.5-flash) on the recap path, everything else held constant.

Design (mirrors ab_recap_editorial, but the A/B variable is the MODEL):
  Arm A: pass-1 StoryModel + pass-2 editorial + recap plan, all with --model-a.
  Arm B: same three calls with --model-b.
  Both arms judged by the SAME fixed judge model (--judge-model, default
  gemini-2.5-flash) so the verdict instrument never moves between arms.
  Deterministic structural metrics recorded per arm (judge-free).

Each arm regenerates its own StoryModel because a production model switch
(GEMINI_DEFAULT_MODEL) affects pass-1 too — this measures the full stack.

Degenerate-sample guard: if the editorial pass ran on one arm but not the
other (quota/503), the arms are not comparable — the sample is rejected.

Usage (from backend/, GEMINI_API_KEY in .env):
    python -m ai_eval.ab_model_upgrade --srt data/cache/transcription/<hash>.srt
    python -m ai_eval.ab_model_upgrade --srt <path> --runs 2 \
        --store ai_eval/measurements/model_35flash.jsonl

n<5 is a directional signal, not a statistic (see DECISIONS.md caveats —
single-provider judge, one film). Judge model == arm A's model, so any
self-preference bias favours arm A; a B win is therefore conservative.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import app.core.config  # noqa: F401 — loads .env (API keys) before anything reads them
from app.features.render.ai.llm import select_recap_plan, select_story_model
from app.features.render.ai.llm.recap_prompts import _fit_transcript
from ai_eval.ab_recap_editorial import (
    _clear_llm_cache,
    _last_timestamp_sec,
    _plan_to_case,
    _summ,
)
from ai_eval.judge import score_case
from ai_eval.rubrics import get_rubric
from ai_eval.runmeta import config_vector
from ai_eval.structural import structural_report, summarize_structural


def _make_story(provider, srt, dur, language, api_key, model):
    """Pass-1 StoryModel with retries, pinned to ``model``. Returns a usable
    StoryModel (characters+beats present) or None."""
    for _attempt in range(1, 6):
        print(f"    pass-1 StoryModel [{model}] (attempt {_attempt}/5) ...")
        story = select_story_model(provider=provider, srt_content=srt,
                                   video_duration=dur, target_language=language,
                                   api_key=api_key, model=model)
        if story is not None and not story.is_empty() and story.beats and story.characters:
            return story
        _clear_llm_cache()
    return None


def _one_arm(provider, srt, dur, language, api_key, model):
    """Generate one full-stack arm (story + recap) with ``model``. Returns
    (plan, story) — either may be None on failure."""
    story = _make_story(provider, srt, dur, language, api_key, model)
    if story is None:
        return None, None
    plan = select_recap_plan(provider=provider, srt_content=srt, video_duration=dur,
                             target_language=language, story_model=story,
                             api_key=api_key, model=model)
    return plan, story


def _append_sample(store_path: str, record: dict) -> None:
    try:
        with open(store_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"    [warn] store append failed: {exc}")


def _load_samples(store_path: str) -> list:
    out = []
    try:
        with open(store_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return out


def _print_grand_aggregate(store_path: str, rubric) -> None:
    rows = _load_samples(store_path)
    n = len(rows)
    if n == 0:
        print(f"\n[ab] store {store_path} has no samples yet.")
        return

    def _mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    deltas = [float(r.get("delta", 0)) for r in rows]
    a_w = [float(r.get("a_weighted", 0)) for r in rows]
    b_w = [float(r.get("b_weighted", 0)) for r in rows]
    model_a = rows[-1].get("model_a", "A")
    model_b = rows[-1].get("model_b", "B")
    print(f"\n=== GRAND AGGREGATE (accumulated) — {n} sample(s) · {store_path} ===")
    print(f"A = {model_a}   B = {model_b}   (Δ = B − A)")
    print(f"{'criterion':<22}{'mean Δ':>9}")
    for c in rubric.criteria:
        cds = [float(r.get("crit_deltas", {}).get(c.key, 0)) for r in rows]
        print(f"{c.key:<22}{_mean(cds):>+9.3f}")
    print(f"{'-'*31}")
    print(f"{'A weighted mean':<22}{_mean(a_w):>9.3f}")
    print(f"{'B weighted mean':<22}{_mean(b_w):>9.3f}")
    print(f"{'Δ weighted (mean)':<22}{_mean(deltas):>+9.3f}")
    print(f"{'Δ weighted (min..max)':<22}{min(deltas):>+.3f} .. {max(deltas):+.3f}")
    wins = sum(1 for d in deltas if d > 0)
    print(f"{'B wins / samples':<22}{wins}/{n}")
    if n >= 2:
        import statistics as _st
        se = _st.pstdev(deltas) / (n ** 0.5)
        verdict = ("inconclusive (|mean| < 2·SE)" if abs(_mean(deltas)) < 2 * se
                   else ("B better" if _mean(deltas) > 0 else "B worse"))
        print(f"{'Δ mean ± SE':<22}{_mean(deltas):+.3f} ± {se:.3f}  → {verdict}")

    def _pick(rows_, arm, *path):
        vals = []
        for r in rows_:
            node = r.get(f"{arm}_structural")
            for key in path:
                node = node.get(key) if isinstance(node, dict) else None
            if isinstance(node, (int, float)):
                vals.append(float(node))
        return vals

    s_a = _pick(rows, "a", "fatigue", "discipline_score")
    if s_a:
        print(f"\n--- STRUCTURAL (deterministic, {len(s_a)} sample(s)) ---")
        print(f"{'metric':<26}{'A':>8}{'B':>8}")
        for label, path in (
            ("discipline_score", ("fatigue", "discipline_score")),
            ("fragment_rate", ("fatigue", "fragment_rate")),
            ("scene_count", ("fatigue", "scene_count")),
            ("hold_precision", ("holds", "hold_precision")),
            ("beat_coverage", ("beats", "coverage_pct")),
            ("episode_balance", ("episodes", "balance_score")),
            ("duration_ratio", ("duration", "ratio")),
            ("duration_ratio_score", ("duration", "ratio_score")),
        ):
            a, b = _pick(rows, "a", *path), _pick(rows, "b", *path)
            fa = f"{_mean(a):.2f}" if a else "-"
            fb = f"{_mean(b):.2f}" if b else "-"
            print(f"{label:<26}{fa:>8}{fb:>8}")
    print("(accumulate more samples over days for a trustworthy verdict.)")


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="A/B measure a generator-model swap (recap path)")
    ap.add_argument("--srt", required=True, nargs="+",
                    help="one or more full-film SRT transcripts (each = a film)")
    ap.add_argument("--runs", type=int, default=1,
                    help="repeated A/B samples per film (cache cleared between)")
    ap.add_argument("--provider", default="gemini", help="generation provider")
    ap.add_argument("--model-a", default="gemini-2.5-flash", help="baseline model")
    ap.add_argument("--model-b", default="gemini-3.5-flash", help="candidate model")
    ap.add_argument("--judge", default="gemini", help="judge provider")
    ap.add_argument("--judge-model", default="gemini-2.5-flash",
                    help="judge model — FIXED for both arms")
    ap.add_argument("--language", default="vi-VN", help="narration target language")
    ap.add_argument("--store", default=None,
                    help="JSONL file to append each sample to (accumulate across days)")
    ap.add_argument("--aggregate-only", action="store_true",
                    help="print the accumulated aggregate from --store and exit (uses no quota)")
    args = ap.parse_args(argv)

    if args.aggregate_only:
        if not args.store:
            print("[ab] --aggregate-only requires --store")
            return 3
        _print_grand_aggregate(args.store, get_rubric("recap"))
        return 0

    from ai_eval.llm_client import resolve_api_key
    api_key = resolve_api_key(args.provider)
    if not api_key:
        print(f"[ab] FAILED: no API key for provider {args.provider} (set it in .env).")
        return 3

    rubric = get_rubric("recap")
    deltas: list[float] = []
    crit_deltas: dict[str, list[float]] = {c.key: [] for c in rubric.criteria}
    a_w: list[float] = []
    b_w: list[float] = []
    n_films = len(args.srt)

    for film_i, srt_path in enumerate(args.srt, start=1):
        srt = open(srt_path, encoding="utf-8").read()
        dur = _last_timestamp_sec(srt)
        excerpt = _fit_transcript(srt, 12000)
        print(f"\n[ab] FILM {film_i}/{n_films}: {srt_path}")
        print(f"     chars={len(srt)} duration={dur:.0f}s (~{dur/60:.0f} min)")
        print(f"     A={args.model_a}  B={args.model_b}  judge={args.judge}:{args.judge_model}")

        for run_i in range(1, args.runs + 1):
            print(f"  run {run_i}/{args.runs}:")
            _clear_llm_cache()
            plan_a, story_a = _one_arm(args.provider, srt, dur, args.language,
                                       api_key, args.model_a)
            _clear_llm_cache()
            plan_b, story_b = _one_arm(args.provider, srt, dur, args.language,
                                       api_key, args.model_b)
            if plan_a is None or plan_b is None:
                print("    [skip] generation failed on one arm — not comparable.")
                continue
            print(f"    A: {_summ(plan_a)}")
            print(f"    B: {_summ(plan_b)}")
            # Editorial parity guard — if pass-2 silently degraded (503/quota)
            # on exactly one arm, the sample measures editorial, not the model.
            ed_a = bool(plan_a.editorial.beats or plan_a.editorial.episode_count)
            ed_b = bool(plan_b.editorial.beats or plan_b.editorial.episode_count)
            if ed_a != ed_b:
                print(f"    [skip] editorial ran on one arm only (A={ed_a} B={ed_b}) "
                      "— not comparable, not recorded.")
                continue
            res_a = score_case(_plan_to_case(plan_a, f"A_r{film_i}_{run_i}", excerpt, dur),
                               provider=args.judge, model=args.judge_model)
            res_b = score_case(_plan_to_case(plan_b, f"B_r{film_i}_{run_i}", excerpt, dur),
                               provider=args.judge, model=args.judge_model)
            if not (res_a and res_b and res_a.ok and res_b.ok):
                print("    [skip] judge failed this run.")
                continue
            d = round(res_b.weighted - res_a.weighted, 3)
            deltas.append(d)
            a_w.append(res_a.weighted)
            b_w.append(res_b.weighted)
            _crit = {c.key: res_b.scores.get(c.key, 0) - res_a.scores.get(c.key, 0)
                     for c in rubric.criteria}
            for c in rubric.criteria:
                crit_deltas[c.key].append(_crit[c.key])
            print(f"    weighted A={res_a.weighted:g} B={res_b.weighted:g} Δ={d:+g}")
            _struct_a = structural_report(plan_a, film_duration_sec=dur)
            _struct_b = structural_report(plan_b, film_duration_sec=dur)
            print(f"    struct A: {summarize_structural(_struct_a)}")
            print(f"    struct B: {summarize_structural(_struct_b)}")
            if args.store:
                _append_sample(args.store, {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "film": srt_path, "provider": args.provider,
                    "model_a": args.model_a, "model_b": args.model_b,
                    "judge": args.judge, "judge_model": args.judge_model,
                    "a_weighted": res_a.weighted, "b_weighted": res_b.weighted, "delta": d,
                    "a_scenes": plan_a.scene_count(), "b_scenes": plan_b.scene_count(),
                    "crit_deltas": _crit,
                    "a_structural": _struct_a,
                    "b_structural": _struct_b,
                    "config": config_vector(ab_variable="GEMINI_DEFAULT_MODEL"),
                })

    n = len(deltas)
    if n == 0:
        print("\n[ab] no successful samples — cannot aggregate.")
        return 3

    def _mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    print(f"\n=== MODEL SWAP {args.model_a} → {args.model_b} — "
          f"AGGREGATE ({n} sample(s), {n_films} film(s)) ===")
    print(f"{'criterion':<22}{'mean Δ':>9}")
    for c in rubric.criteria:
        print(f"{c.key:<22}{_mean(crit_deltas[c.key]):>+9.3f}")
    print(f"{'-'*31}")
    print(f"{'A weighted mean':<22}{_mean(a_w):>9.3f}")
    print(f"{'B weighted mean':<22}{_mean(b_w):>9.3f}")
    print(f"{'Δ weighted (mean)':<22}{_mean(deltas):>+9.3f}")
    print(f"{'Δ weighted (min..max)':<22}{min(deltas):>+.3f} .. {max(deltas):+.3f}")
    wins = sum(1 for d in deltas if d > 0)
    print(f"{'B wins / samples':<22}{wins}/{n}")

    if args.store:
        _print_grand_aggregate(args.store, rubric)
    return 0


if __name__ == "__main__":
    sys.exit(main())
