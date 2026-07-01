"""
ab_recap_editorial.py — measure P0-2 (Editorial Blueprint / pass-2) impact.

Runs a controlled A/B on ONE real film transcript:
  1. Generate a single StoryModel (pass-1) — shared by both arms so the only
     variable is pass-2.
  2. Arm A: select_recap_plan with editorial pass OFF.
  3. Arm B: select_recap_plan with editorial pass ON (pass-2 runs from the
     shared StoryModel).
  4. Judge both with the ai_eval recap rubric and print the delta.

Both recap prompts embed the freshly-generated StoryModel text, so neither
arm collides with any previously cached render — a clean miss on both.

Usage (from backend/, with GEMINI_API_KEY in .env):
    python -m ai_eval.ab_recap_editorial --srt data/cache/transcription/<hash>.srt
    python -m ai_eval.ab_recap_editorial --srt <path> --provider gemini --judge gemini

n=1 experiment: treat as a directional signal, not a statistic. Re-run on
several films to build confidence.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time

import app.core.config  # noqa: F401 — loads .env (API keys) before anything reads them
import app.features.render.ai.llm as llm
from app.features.render.ai.llm import select_recap_plan, select_story_model
from app.features.render.ai.llm.recap_prompts import _fit_transcript
from ai_eval.judge import score_case
from ai_eval.rubrics import get_rubric

_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})")


def _last_timestamp_sec(srt: str) -> float:
    last = 0.0
    for m in _TS.finditer(srt):
        h, mi, s, ms = (int(x) for x in m.groups()[4:])
        last = max(last, h * 3600 + mi * 60 + s + ms / 1000)
    return last


def _plan_to_case(plan, case_id: str, transcript_excerpt: str, video_duration: float) -> dict:
    scenes = []
    for ep in plan.episodes:
        for act in ep.acts:
            for sc in act.scenes:
                scenes.append({
                    "start": round(sc.start, 1), "end": round(sc.end, 1),
                    "title": sc.title, "audio_mode": sc.audio_mode,
                    "is_climax": sc.is_climax, "narration": sc.narration,
                })
    return {
        "id": case_id, "feature": "recap",
        "inputs": {
            "film_duration_sec": round(video_duration, 1),
            "transcript_excerpt_downsampled": transcript_excerpt,
        },
        "output": {
            "story_model": plan.story.to_public_dict(),
            "editorial": plan.editorial.to_public_dict(),
            "episode_count": plan.episode_count(),
            "scene_count": plan.scene_count(),
            "total_target_sec": plan.total_target_sec,
            "scenes": scenes,
        },
    }


def _summ(plan) -> str:
    ed = plan.editorial
    return (f"episodes={plan.episode_count()} scenes={plan.scene_count()} "
            f"editorial(episode_count={ed.episode_count}, beats={len(ed.beats)}, "
            f"pacing={'yes' if ed.pacing else 'no'})")


def _clear_llm_cache() -> None:
    """Bust the content-addressable LLM disk cache so the next generation call
    actually re-hits the provider (needed to sample stochastic variation across
    repeated runs). Never raises."""
    try:
        from app.core.config import APP_DATA_DIR
        from pathlib import Path as _P
        for _f in (_P(APP_DATA_DIR) / "cache" / "llm").glob("*.txt"):
            _f.unlink()
    except Exception:
        pass


def _make_story(provider, srt, dur, language, api_key):
    """Pass-1 StoryModel with retries (the story call is high-variance). Returns
    a usable StoryModel (characters+beats present) or None."""
    for _attempt in range(1, 6):
        print(f"    pass-1 StoryModel (attempt {_attempt}/5) ...")
        story = select_story_model(provider=provider, srt_content=srt,
                                   video_duration=dur, target_language=language,
                                   api_key=api_key)
        if story is not None and not story.is_empty() and story.beats and story.characters:
            return story
        _clear_llm_cache()
    return None


def _one_ab(provider, judge, srt, dur, language, api_key, story, excerpt, run_idx):
    """Run one OFF/ON pair against a fixed StoryModel + judge both. Returns
    (res_off, res_on, plan_off, plan_on) or (None, None, ...) on generation fail."""
    llm._RECAP_EDITORIAL_PASS = False
    plan_off = select_recap_plan(provider=provider, srt_content=srt, video_duration=dur,
                                 target_language=language, story_model=story, api_key=api_key)
    llm._RECAP_EDITORIAL_PASS = True
    plan_on = select_recap_plan(provider=provider, srt_content=srt, video_duration=dur,
                                target_language=language, story_model=story, api_key=api_key)
    if plan_off is None or plan_on is None:
        return None, None, plan_off, plan_on
    print(f"    OFF: {_summ(plan_off)}")
    print(f"    ON : {_summ(plan_on)}")
    res_off = score_case(_plan_to_case(plan_off, f"OFF_r{run_idx}", excerpt, dur), provider=judge)
    res_on = score_case(_plan_to_case(plan_on, f"ON_r{run_idx}", excerpt, dur), provider=judge)
    return res_off, res_on, plan_off, plan_on


def _append_sample(store_path: str, record: dict) -> None:
    """Append one sample to the accumulation store (JSONL) — one line per run,
    so samples gathered across days/runs build one growing distribution."""
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
    """Aggregate ALL accumulated samples in the store (across every run/day)."""
    rows = _load_samples(store_path)
    n = len(rows)
    if n == 0:
        print(f"\n[ab] store {store_path} has no samples yet.")
        return

    def _mean(xs):
        return sum(xs) / len(xs) if xs else 0.0

    deltas = [float(r.get("delta", 0)) for r in rows]
    off = [float(r.get("off_weighted", 0)) for r in rows]
    on = [float(r.get("on_weighted", 0)) for r in rows]
    print(f"\n=== GRAND AGGREGATE (accumulated) — {n} sample(s) · {store_path} ===")
    print(f"{'criterion':<22}{'mean Δ':>9}")
    for c in rubric.criteria:
        cds = [float(r.get("crit_deltas", {}).get(c.key, 0)) for r in rows]
        print(f"{c.key:<22}{_mean(cds):>+9.3f}")
    print(f"{'-'*31}")
    print(f"{'OFF weighted mean':<22}{_mean(off):>9.3f}")
    print(f"{'ON  weighted mean':<22}{_mean(on):>9.3f}")
    print(f"{'Δ weighted (mean)':<22}{_mean(deltas):>+9.3f}")
    print(f"{'Δ weighted (min..max)':<22}{min(deltas):>+.3f} .. {max(deltas):+.3f}")
    wins = sum(1 for d in deltas if d > 0)
    print(f"{'ON wins / samples':<22}{wins}/{n}")
    if n >= 2:
        import statistics as _st
        se = _st.pstdev(deltas) / (n ** 0.5)
        verdict = ("inconclusive (|mean| < 2·SE)" if abs(_mean(deltas)) < 2 * se
                   else ("ON better" if _mean(deltas) > 0 else "ON worse"))
        print(f"{'Δ mean ± SE':<22}{_mean(deltas):+.3f} ± {se:.3f}  → {verdict}")
    print("(accumulate more samples over days for a trustworthy verdict.)")


def main(argv=None) -> int:
    # Output uses Δ / — etc.; force UTF-8 so a bare Windows console (cp1252)
    # doesn't crash the aggregate print.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="A/B measure recap Editorial Blueprint (P0-2)")
    ap.add_argument("--srt", required=True, nargs="+",
                    help="one or more full-film SRT transcripts (each = a film)")
    ap.add_argument("--runs", type=int, default=1,
                    help="repeated OFF/ON samples per film (cache cleared between) "
                         "to measure effect stability")
    ap.add_argument("--provider", default="gemini", help="recap generation provider")
    ap.add_argument("--judge", default="gemini", help="judge provider (ideally != --provider)")
    ap.add_argument("--language", default="vi-VN", help="narration target language")
    ap.add_argument("--store", default=None,
                    help="JSONL file to append each sample to (accumulate across days)")
    ap.add_argument("--aggregate-only", action="store_true",
                    help="print the accumulated aggregate from --store and exit (uses no quota)")
    args = ap.parse_args(argv)

    # 0-quota path: just summarise whatever has accumulated in the store.
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
    if args.judge == args.provider:
        print(f"[ab] WARNING: judge == generator ({args.judge}) — self-preference bias.")

    rubric = get_rubric("recap")
    deltas: list[float] = []                      # weighted-mean Δ per sample
    crit_deltas: dict[str, list[float]] = {c.key: [] for c in rubric.criteria}
    off_w: list[float] = []
    on_w: list[float] = []
    n_films = len(args.srt)

    for film_i, srt_path in enumerate(args.srt, start=1):
        srt = open(srt_path, encoding="utf-8").read()
        dur = _last_timestamp_sec(srt)
        excerpt = _fit_transcript(srt, 12000)
        print(f"\n[ab] FILM {film_i}/{n_films}: {srt_path}")
        print(f"     chars={len(srt)} duration={dur:.0f}s (~{dur/60:.0f} min)")
        # Shared StoryModel per film — regenerated fresh so each film is clean,
        # but reused across that film's runs so the only variable is generation
        # stochasticity in the recap arms.
        _clear_llm_cache()
        story = _make_story(args.provider, srt, dur, args.language, api_key)
        if story is None:
            print(f"[ab] SKIP film {film_i}: StoryModel unusable after retries.")
            continue
        print(f"     StoryModel: characters={len(story.characters)} beats={len(story.beats)} "
              f"emotional_curve={len(story.emotional_curve)}")

        for run_i in range(1, args.runs + 1):
            print(f"  run {run_i}/{args.runs}:")
            _clear_llm_cache()  # force fresh recap generation each run
            res_off, res_on, plan_off, plan_on = _one_ab(
                args.provider, args.judge, srt, dur, args.language, api_key,
                story, excerpt, f"{film_i}_{run_i}")
            if not (res_off and res_on and res_off.ok and res_on.ok):
                print("    [skip] generation or judge failed this run.")
                continue
            # A valid 0B sample REQUIRES pass-2 to have actually run on the ON
            # arm. If the editorial call failed (503/429), ON degrades to OFF
            # (Sacred Contract #3) → a degenerate Δ≈0 that would pollute the
            # accumulation with a false "no effect". Reject it.
            if not (plan_on.editorial.beats or plan_on.editorial.episode_count):
                print("    [skip] editorial pass did NOT run on ON arm "
                      "(503/quota) — degenerate ON==OFF, not recorded.")
                continue
            d = round(res_on.weighted - res_off.weighted, 3)
            deltas.append(d)
            off_w.append(res_off.weighted)
            on_w.append(res_on.weighted)
            _crit = {c.key: res_on.scores.get(c.key, 0) - res_off.scores.get(c.key, 0)
                     for c in rubric.criteria}
            for c in rubric.criteria:
                crit_deltas[c.key].append(_crit[c.key])
            print(f"    weighted OFF={res_off.weighted:g} ON={res_on.weighted:g} Δ={d:+g}")
            if args.store:
                _append_sample(args.store, {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "film": srt_path, "provider": args.provider, "judge": args.judge,
                    "off_weighted": res_off.weighted, "on_weighted": res_on.weighted, "delta": d,
                    "off_scenes": plan_off.scene_count(), "on_scenes": plan_on.scene_count(),
                    "on_editorial_beats": len(plan_on.editorial.beats),
                    "crit_deltas": _crit,
                })

    # ── Aggregate ────────────────────────────────────────────────────────────
    n = len(deltas)
    if n == 0:
        print("\n[ab] no successful samples — cannot aggregate.")
        return 3

    def _mean(xs): return sum(xs) / len(xs) if xs else 0.0

    print(f"\n=== RECAP EDITORIAL PASS — AGGREGATE ({n} sample(s), {n_films} film(s)) ===")
    print(f"{'criterion':<22}{'mean Δ':>9}")
    for c in rubric.criteria:
        print(f"{c.key:<22}{_mean(crit_deltas[c.key]):>+9.3f}")
    print(f"{'-'*31}")
    print(f"{'OFF weighted mean':<22}{_mean(off_w):>9.3f}")
    print(f"{'ON  weighted mean':<22}{_mean(on_w):>9.3f}")
    print(f"{'Δ weighted (mean)':<22}{_mean(deltas):>+9.3f}")
    print(f"{'Δ weighted (min..max)':<22}{min(deltas):>+.3f} .. {max(deltas):+.3f}")
    wins = sum(1 for d in deltas if d > 0)
    print(f"{'ON wins / samples':<22}{wins}/{n}")

    # Grand aggregate over ALL accumulated samples (this run + prior days).
    if args.store:
        _print_grand_aggregate(args.store, rubric)
    return 0


if __name__ == "__main__":
    sys.exit(main())
