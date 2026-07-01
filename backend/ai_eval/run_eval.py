"""
run_eval.py — CLI to score a golden dataset and gate on quality.

Usage (from backend/):
    python -m ai_eval.run_eval --dataset tests/fixtures/quality --provider gemini
    python -m ai_eval.run_eval --dataset tests/fixtures/quality \
        --provider claude --baseline ai_eval/baselines/main.json --out /tmp/run.json

Exit codes (CI-friendly):
    0  all judged cases passed their rubric AND no regression vs baseline
    1  one or more cases failed a gate / ship bar
    2  a regression vs baseline exceeded tolerance
    3  no cases judged (dataset empty / all judge calls failed)

The judge provider SHOULD differ from the provider that generated the
artifacts (reduces self-preference bias); pass --provider accordingly.
"""
from __future__ import annotations

import argparse
import logging
import sys

from ai_eval.dataset import (
    DEFAULT_REGRESSION_TOLERANCE,
    compare_to_baseline,
    load_cases,
    load_report,
    save_report,
)
from ai_eval.judge import score_case

logger = logging.getLogger("ai_eval.run")


def _fmt_scores(scores: dict) -> str:
    return " ".join(f"{k}={v:g}" for k, v in scores.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI content-quality eval harness")
    parser.add_argument("--dataset", default="tests/fixtures/quality",
                        help="directory of *.json golden cases")
    parser.add_argument("--provider", default="gemini",
                        choices=("gemini", "openai", "claude"),
                        help="JUDGE provider (use a different one than the generator)")
    parser.add_argument("--model", default=None, help="override judge model")
    parser.add_argument("--baseline", default=None, help="baseline report JSON to compare against")
    parser.add_argument("--out", default=None, help="write the run report JSON here")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_REGRESSION_TOLERANCE,
                        help="max allowed weighted-mean drop vs baseline")
    parser.add_argument("--only", default=None, help="only run cases whose feature == this")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cases = load_cases(args.dataset)
    if args.only:
        cases = [c for c in cases if str(c.get("feature", "")).lower() == args.only.lower()]
    if not cases:
        print(f"[ai_eval] no cases found in {args.dataset}")
        return 3

    print(f"[ai_eval] scoring {len(cases)} case(s) with judge={args.provider}")
    results = []
    judged = 0
    for case in cases:
        res = score_case(case, provider=args.provider, model=args.model)
        results.append(res.to_dict())
        if res.ok:
            judged += 1
            status = "PASS" if res.passed else "FAIL"
            print(f"  [{status}] {res.case_id} ({res.feature}) "
                  f"weighted={res.weighted:g}  {_fmt_scores(res.scores)}")
            if res.gate_failures:
                print(f"         gate: {'; '.join(res.gate_failures)}")
            if res.flags:
                print(f"         flags: {', '.join(res.flags)}")
        else:
            print(f"  [ERR ] {res.case_id} ({res.feature}) — {res.error}")

    if args.out:
        save_report(results, args.out)
        print(f"[ai_eval] report -> {args.out}")

    if judged == 0:
        print("[ai_eval] no cases were successfully judged")
        return 3

    # Regression gate.
    regressions = []
    if args.baseline:
        baseline = load_report(args.baseline)
        regressions = compare_to_baseline(results, baseline, tolerance=args.tolerance)
        for r in regressions:
            print(f"  [REGRESSION] {r['case_id']} {r['baseline']:g} -> {r['current']:g} "
                  f"(delta {r['delta']:g})")

    failed = [r for r in results if r.get("ok") and not r.get("passed")]
    n_pass = sum(1 for r in results if r.get("passed"))
    print(f"[ai_eval] passed={n_pass}/{judged} judged  regressions={len(regressions)}")

    if regressions:
        return 2
    if failed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
