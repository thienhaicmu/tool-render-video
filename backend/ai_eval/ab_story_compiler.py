"""Paired Story A/B: legacy single-pass versus the Story Compiler.

This runner spends real provider quota. It persists both plans, compact runtime
traces, deterministic quality reports and a blinded human-review package. The
answer key is stored separately so reviewers cannot infer the arm from filenames.

Run from backend/:
    python -m ai_eval.ab_story_compiler --sample revenge_vi --runs 2
    python -m ai_eval.ab_story_compiler --runs 1 --out-dir ai_eval/measurements/compiler_ab
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import time
from pathlib import Path
from typing import Any

import app.core.config  # noqa: F401 - load .env before reading provider keys
from app.domain.story_plan_v2 import StoryPlan
from app.features.render.ai.llm import generate_story_plan_v2
from app.features.render.ai.llm.cache import llm_cache_clear
from ai_eval.runmeta import config_vector
from ai_eval.structural_story import story_structural_report

_HERE = Path(__file__).resolve().parent
_CASES_PATH = _HERE / "story_golden_cases.json"
_KEY_ENV = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


def load_cases(path: Path = _CASES_PATH) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("story golden dataset must be a JSON array")
    out = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        case = dict(item)
        sample_file = str(case.pop("sample_file", "") or "")
        if sample_file:
            case["chapter"] = (_HERE / "samples" / sample_file).read_text(encoding="utf-8")
        out.append(case)
    return out


def _provider_key(provider: str) -> str:
    return (os.getenv(_KEY_ENV.get(provider, ""), "") or "").strip()


def _compact_trace(events: list[dict]) -> dict:
    calls = [event for event in events if event.get("event") == "call_completed"]
    selected = next((event for event in reversed(events)
                     if event.get("event") == "provider_selected"), {})
    authored = next((event for event in reversed(events)
                     if event.get("event") == "authoring_selected"), {})
    return {
        "actual_llm_calls": len(calls),
        "latency_ms": round(sum(float(event.get("latency_ms") or 0) for event in calls), 1),
        "selected_provider": selected.get("provider", ""),
        "selected_model": selected.get("model", ""),
        "role_routes": selected.get("role_routes", {}),
        "authoring_mode": authored.get("mode", ""),
        "calls": [{k: event.get(k) for k in
                   ("stage", "provider", "model", "status", "latency_ms", "input_chars", "output_chars")}
                  for event in calls],
        "fallback": any(event.get("event") == "compiler_fallback" for event in events),
    }


def _spoken_text(plan) -> str:
    if plan is None:
        return ""
    lines = []
    for beat in plan.timeline:
        lines.extend(line.text for line in beat.effective_lines() if (line.text or "").strip())
    return "\n".join(lines)


def run_arm(case: dict, arm: str, *, provider: str, model: str | None) -> tuple[dict, Any]:
    previous = os.environ.get("STORY_COMPILER")
    os.environ["STORY_COMPILER"] = "1" if arm == "compiler" else "0"
    events: list[dict] = []
    llm_cache_clear()
    started = time.perf_counter()
    try:
        plan = generate_story_plan_v2(
            provider=provider, source=str(case.get("source") or "paste"),
            chapter=str(case.get("chapter") or "") or None,
            idea=str(case.get("idea") or "") or None,
            duration_sec=int(case.get("duration_sec") or 0),
            genre=str(case.get("genre") or ""), language=str(case.get("language") or "vi"),
            art_style=str(case.get("art_style") or ""), api_key=_provider_key(provider),
            model=model, resolve_key=_provider_key, observer=events.append,
        )
    finally:
        if previous is None:
            os.environ.pop("STORY_COMPILER", None)
        else:
            os.environ["STORY_COMPILER"] = previous
    elapsed = round(time.perf_counter() - started, 3)
    structural = story_structural_report(plan, float(case.get("duration_sec") or 0))
    runtime = _compact_trace(events)
    arm_valid = bool(plan is not None and (
        arm == "legacy" or (
            runtime.get("authoring_mode") == "compiler" and not runtime.get("fallback"))))
    return ({
        "arm": arm, "usable": plan is not None, "wall_latency_sec": elapsed,
        "arm_valid": arm_valid, "structural": structural, "runtime": runtime,
        "config": config_vector(STORY_COMPILER=("1" if arm == "compiler" else "0")),
    }, plan)


def paired_summary(rows: list[dict]) -> dict:
    groups: dict[tuple[str, int], dict[str, dict]] = {}
    for row in rows:
        groups.setdefault((row["case_id"], int(row["run"])), {})[row["arm"]] = row
    deltas = []
    wins = ties = losses = 0
    unusable_pairs = invalid_pairs = unknown_provenance_pairs = 0
    failed_arms = sum(1 for row in rows if not bool(row.get("usable", True)))
    for pair in groups.values():
        if "compiler" not in pair or "legacy" not in pair:
            continue
        if not pair["compiler"].get("usable") or not pair["legacy"].get("usable"):
            unusable_pairs += 1
            continue
        validity = (pair["compiler"].get("arm_valid"), pair["legacy"].get("arm_valid"))
        if None in validity:
            unknown_provenance_pairs += 1
            continue
        if not all(validity):
            invalid_pairs += 1
            continue
        delta = float(pair["compiler"]["structural"].get("overall_score") or 0) - float(
            pair["legacy"]["structural"].get("overall_score") or 0)
        deltas.append(delta)
        if delta > 0.5: wins += 1
        elif delta < -0.5: losses += 1
        else: ties += 1
    return {
        "pairs": len(groups), "qualified_pairs": len(deltas), "usable_pairs": len(deltas),
        "unusable_pairs": unusable_pairs, "invalid_arm_pairs": invalid_pairs,
        "unknown_provenance_pairs": unknown_provenance_pairs,
        "failed_arms": failed_arms,
        "compiler_wins": wins, "ties": ties, "compiler_losses": losses,
        "mean_score_delta": round(statistics.mean(deltas), 2) if deltas else None,
        "median_score_delta": round(statistics.median(deltas), 2) if deltas else None,
        "ship_signal": bool(len(deltas) >= 10 and wins > losses and statistics.mean(deltas) >= 3.0),
        "note": "n<10 is directional; ship_signal also requires blind human review agreement",
    }


def _write_rows(path: Path, rows: list[dict]) -> None:
    """Atomic per-arm checkpoint so a timeout never discards completed calls."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                   encoding="utf-8")
    tmp.replace(path)


def _recover_rows(root: Path, cases: list[dict]) -> list[dict]:
    """Recover structural rows from plan checkpoints when an old run died pre-summary."""
    measurements = root / "measurements.jsonl"
    rows: list[dict] = []
    if measurements.exists():
        for line in measurements.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict): rows.append(row)
            except json.JSONDecodeError:
                continue
    known = {(str(row.get("case_id")), int(row.get("run") or 0), str(row.get("arm")))
             for row in rows}
    by_id = {str(case["id"]): case for case in cases}
    pattern = re.compile(r"^(?P<case>.+)_r(?P<run>\d+)_(?P<arm>legacy|compiler)\.json$")
    for path in sorted((root / "plans").glob("*.json")):
        match = pattern.match(path.name)
        if not match:
            continue
        key = (match.group("case"), int(match.group("run")), match.group("arm"))
        if key in known or key[0] not in by_id:
            continue
        plan = StoryPlan.from_json(path.read_text(encoding="utf-8"))
        if plan is None:
            continue
        case = by_id[key[0]]
        rows.append({
            "case_id": key[0], "run": key[1], "arm": key[2], "usable": True,
            "arm_valid": (True if key[2] == "legacy" else None),
            "wall_latency_sec": None, "recovered_from_plan": True,
            "structural": story_structural_report(plan, float(case.get("duration_sec") or 0)),
            "runtime": {"actual_llm_calls": None, "latency_ms": None, "recovered": True,
                        "authoring_mode": ("single_pass" if key[2] == "legacy" else "unknown")},
            "config": config_vector(STORY_COMPILER=("1" if key[2] == "compiler" else "0")),
        })
        known.add(key)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Story compiler vs legacy paired A/B")
    parser.add_argument("--dataset", default=str(_CASES_PATH))
    parser.add_argument("--sample", default="", help="case id; default runs the full golden set")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--provider", default=os.getenv("STORY_AI_PROVIDER", "openai"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--out-dir", default="ai_eval/measurements/story_compiler_ab")
    parser.add_argument("--resume-dir", default="",
                        help="resume/checkpoint into an existing timestamp directory")
    parser.add_argument("--order-seed", type=int, default=20260715)
    args = parser.parse_args(argv)

    provider = str(args.provider).strip().lower()
    if not _provider_key(provider):
        print(f"!! {_KEY_ENV.get(provider, 'provider API key')} not set - cannot run real A/B", flush=True)
        return 2
    all_cases = load_cases(Path(args.dataset))
    cases = list(all_cases)
    if args.sample:
        cases = [case for case in cases if case["id"] == args.sample]
    if not cases:
        print("!! no matching story golden cases", flush=True)
        return 2

    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = Path(args.resume_dir) if args.resume_dir else Path(args.out_dir) / stamp
    plans_dir = root / "plans"
    blind_dir = root / "blind_review"
    plans_dir.mkdir(parents=True, exist_ok=True)
    blind_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.order_seed)
    rows = _recover_rows(root, all_cases)
    measurements_path = root / "measurements.jsonl"
    _write_rows(measurements_path, rows)
    answer_key_path = root / "answer_key.json"
    try:
        answer_key = json.loads(answer_key_path.read_text(encoding="utf-8"))
        if not isinstance(answer_key, dict): answer_key = {}
    except Exception:
        answer_key = {}
    completed_keys = {(str(row.get("case_id")), int(row.get("run") or 0), str(row.get("arm")))
                      for row in rows}

    for case in cases:
        for run in range(1, max(1, args.runs) + 1):
            order = ["legacy", "compiler"]
            if rng.random() < 0.5:
                order.reverse()
            completed: dict[str, tuple[dict, Any]] = {}
            for arm in order:
                key = (str(case["id"]), run, arm)
                plan_path = plans_dir / f"{case['id']}_r{run}_{arm}.json"
                if key in completed_keys:
                    row = next(row for row in rows if
                               (str(row.get("case_id")), int(row.get("run") or 0), str(row.get("arm"))) == key)
                    plan = StoryPlan.from_json(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else None
                    completed[arm] = (row, plan)
                    print(f"[{case['id']} run={run}] {arm} (checkpoint)", flush=True)
                    continue
                print(f"[{case['id']} run={run}] {arm}", flush=True)
                result, plan = run_arm(case, arm, provider=provider, model=args.model)
                row = {"case_id": case["id"], "run": run, **result}
                rows.append(row)
                completed_keys.add(key)
                completed[arm] = (row, plan)
                if plan is not None:
                    plan_path.write_text(plan.to_json(), encoding="utf-8")
                _write_rows(measurements_path, rows)

            labels = ["A", "B"]
            rng.shuffle(labels)
            review_id = f"{case['id']}_r{run}"
            review = {"review_id": review_id, "source": case, "candidates": {}}
            for label, arm in zip(labels, ("legacy", "compiler")):
                row, plan = completed[arm]
                review["candidates"][label] = {
                    "usable": row["usable"], "narration": _spoken_text(plan),
                    "plan": (json.loads(plan.to_json()) if plan is not None else None),
                }
                answer_key[f"{review_id}:{label}"] = arm
            (blind_dir / f"{review_id}.json").write_text(
                json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
            answer_key_path.write_text(json.dumps(answer_key, indent=2), encoding="utf-8")
            (root / "summary.json").write_text(
                json.dumps(paired_summary(rows), indent=2), encoding="utf-8")

    summary = paired_summary(rows)
    _write_rows(measurements_path, rows)
    (root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    answer_key_path.write_text(json.dumps(answer_key, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    print(f"artifacts -> {root}", flush=True)
    return 0 if summary.get("usable_pairs", 0) else 3


if __name__ == "__main__":
    raise SystemExit(main())
