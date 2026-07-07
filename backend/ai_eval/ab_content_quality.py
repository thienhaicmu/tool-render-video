"""
ab_content_quality.py — measure CM-7 (CONTENT_PLAN_MODE=quality) impact.

Content Mode's single-shot plan is weakest on narration flow + scene-length fit.
CM-7's "quality" mode adds ONE narration-refine pass. This A/B isolates that
pass on a fixed base plan (mirrors ab_recap_editorial sharing the StoryModel):

  1. Generate ONE base ContentPlan (fast mode) from the source script.
  2. Arm A (fast)    = the base plan as-is.
  3. Arm B (quality) = a COPY of the base plan with the refine pass applied
     (select_content_narration — the exact call CM-7's quality mode makes).
  4. Judge both with the ai_eval `content` rubric; print the narration_fluency /
     time_fit delta.

Only the refine pass differs between arms, so the delta attributes cleanly to
CM-7. n is small — treat as a directional signal, re-run to build confidence.

Usage (from backend/, with a Gemini key in .env):
    python -m ai_eval.ab_content_quality --script ai_eval/samples/content_napoleon_vi.txt
    python -m ai_eval.ab_content_quality --script <path> --provider gemini --judge gemini --runs 3
"""
from __future__ import annotations

import argparse
import copy
import sys
import time

import app.core.config  # noqa: F401 — loads .env (API keys) before anything reads them
from app.domain.content_plan import ContentPlan
from app.features.render.ai.llm import select_content_plan, select_content_narration
from ai_eval.judge import score_case
from ai_eval.rubrics import get_rubric


def _clear_llm_cache() -> None:
    """Bust the content-addressable LLM disk cache so the next generation call
    re-hits the provider (needed to sample stochastic variation). Never raises."""
    try:
        from app.core.config import APP_DATA_DIR
        from pathlib import Path as _P
        for _f in (_P(APP_DATA_DIR) / "cache" / "llm").glob("*.txt"):
            _f.unlink()
    except Exception:
        pass


def _plan_to_case(plan, case_id: str, script_excerpt: str, target_dur: float) -> dict:
    scenes = [
        {"role": s.role, "narration": s.narration, "planned_sec": round(s.est_duration_sec, 1)}
        for s in plan.scenes
    ]
    return {
        "id": case_id, "feature": "content",
        "inputs": {"target_duration_sec": round(target_dur, 1),
                   "source_script_excerpt": script_excerpt},
        "output": {"topic": plan.topic, "scene_count": plan.scene_count(),
                   "total_target_sec": plan.total_target_sec, "scenes": scenes},
    }


def _apply_refine(base: ContentPlan, provider: str, language: str, api_key: str) -> ContentPlan:
    """Return a COPY of ``base`` with CM-7's narration-refine pass applied. On any
    failure returns the copy unchanged (→ degenerate Δ, rejected by the caller)."""
    plan_b = ContentPlan.from_json(base.to_json()) or copy.deepcopy(base)
    payload = [
        {"index": i, "role": (s.role or ""),
         "seconds": float(getattr(s, "est_duration_sec", 0.0) or 0.0),
         "narration": (s.narration or "")}
        for i, s in enumerate(base.scenes)
    ]
    refined = select_content_narration(
        provider=provider, scenes=payload, topic=(base.topic or ""),
        tone="", target_language=language, api_key=api_key,
    )
    if refined:
        for i, s in enumerate(plan_b.scenes):
            t = refined.get(i)
            if t and t.strip():
                s.narration = t.strip()
    return plan_b


def _summ(plan) -> str:
    chars = sum(len(s.narration or "") for s in plan.scenes)
    return f"scenes={plan.scene_count()} narration_chars={chars} topic={plan.topic!r}"


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="A/B measure Content Mode quality planning (CM-7)")
    ap.add_argument("--script", required=True, nargs="+", help="one or more source script text files")
    ap.add_argument("--runs", type=int, default=1, help="repeated samples per script")
    ap.add_argument("--provider", default="gemini", help="content generation provider")
    ap.add_argument("--judge", default="gemini", help="judge provider (ideally != --provider)")
    ap.add_argument("--language", default="vi-VN", help="narration target language")
    ap.add_argument("--target-duration", type=float, default=90.0)
    args = ap.parse_args(argv)

    from ai_eval.llm_client import resolve_api_key
    api_key = resolve_api_key(args.provider)
    if not api_key:
        print(f"[ab] FAILED: no API key for provider {args.provider} (set it in .env).")
        return 3
    if args.judge == args.provider:
        print(f"[ab] WARNING: judge == generator ({args.judge}) — self-preference bias.")

    rubric = get_rubric("content")
    deltas: list[float] = []
    crit_deltas: dict[str, list[float]] = {c.key: [] for c in rubric.criteria}
    fast_w: list[float] = []
    qual_w: list[float] = []

    for si, path in enumerate(args.script, start=1):
        script = open(path, encoding="utf-8").read()
        excerpt = script[:6000]
        print(f"\n[ab] SCRIPT {si}/{len(args.script)}: {path}  (chars={len(script)})")
        for run_i in range(1, args.runs + 1):
            print(f"  run {run_i}/{args.runs}:")
            _clear_llm_cache()
            base = select_content_plan(
                provider=args.provider, script=script,
                target_duration_sec=args.target_duration, target_language=args.language,
                api_key=api_key,
            )
            if base is None or base.scene_count() == 0:
                print("    [skip] base plan generation failed.")
                continue
            plan_fast = base
            plan_qual = _apply_refine(base, args.provider, args.language, api_key)
            # If the refine changed nothing, ON==OFF — degenerate, don't record.
            if plan_qual.to_json() == plan_fast.to_json():
                print("    [skip] refine pass produced no change (degenerate).")
                continue
            print(f"    FAST: {_summ(plan_fast)}")
            print(f"    QUAL: {_summ(plan_qual)}")
            res_a = score_case(_plan_to_case(plan_fast, f"FAST_{si}_{run_i}", excerpt, args.target_duration),
                               provider=args.judge)
            res_b = score_case(_plan_to_case(plan_qual, f"QUAL_{si}_{run_i}", excerpt, args.target_duration),
                               provider=args.judge)
            if not (res_a.ok and res_b.ok):
                print(f"    [skip] judge failed (A.ok={res_a.ok} B.ok={res_b.ok}): "
                      f"{res_a.error or res_b.error}")
                continue
            d = round(res_b.weighted - res_a.weighted, 3)
            deltas.append(d)
            fast_w.append(res_a.weighted)
            qual_w.append(res_b.weighted)
            for c in rubric.criteria:
                crit_deltas[c.key].append(res_b.scores.get(c.key, 0) - res_a.scores.get(c.key, 0))
            print(f"    weighted FAST={res_a.weighted:g} QUAL={res_b.weighted:g} Δ={d:+g}")

    n = len(deltas)
    if n == 0:
        print("\n[ab] no successful samples — cannot aggregate.")
        return 3

    def _mean(xs): return sum(xs) / len(xs) if xs else 0.0

    print(f"\n=== CONTENT QUALITY MODE (CM-7) — AGGREGATE ({n} sample(s)) ===")
    print(f"{'criterion':<22}{'mean Δ':>9}")
    for c in rubric.criteria:
        print(f"{c.key:<22}{_mean(crit_deltas[c.key]):>+9.3f}")
    print(f"{'-'*31}")
    print(f"{'FAST weighted mean':<22}{_mean(fast_w):>9.3f}")
    print(f"{'QUAL weighted mean':<22}{_mean(qual_w):>9.3f}")
    print(f"{'Δ weighted (mean)':<22}{_mean(deltas):>+9.3f}")
    print(f"{'Δ weighted (min..max)':<22}{min(deltas):>+.3f} .. {max(deltas):+.3f}")
    wins = sum(1 for d in deltas if d > 0)
    print(f"{'QUAL wins / samples':<22}{wins}/{n}")
    if n >= 2:
        import statistics as _st
        se = _st.pstdev(deltas) / (n ** 0.5)
        verdict = ("inconclusive (|mean| < 2·SE)" if abs(_mean(deltas)) < 2 * se
                   else ("QUAL better" if _mean(deltas) > 0 else "QUAL worse"))
        print(f"{'Δ mean ± SE':<22}{_mean(deltas):+.3f} ± {se:.3f}  → {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
