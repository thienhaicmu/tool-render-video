"""
dataset.py — load golden cases + compare a run against a baseline.

A golden case is a single JSON file:
    {
      "id": "clip_podcast_01",
      "feature": "clip" | "recap" | "reaction" | "rewrite",
      "source": {"kind": "...", "duration_sec": 0, "language": "..."},
      "inputs": { ... grounding context for faithfulness ... },
      "output": { ... the generated artifact to score ... }
    }

The dataset is the frozen definition of "the content we test against." Add
cases by dropping new JSON files in the dataset dir (default
``tests/fixtures/quality``). Never mutate an existing case — a changed case
invalidates the baseline it was measured against.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_eval.dataset")

# Regression tolerance: a per-case weighted-mean drop larger than this vs the
# baseline is a FAIL (blocks a prompt change from shipping a quality regression).
DEFAULT_REGRESSION_TOLERANCE = 0.3


def load_cases(dataset_dir: str | Path) -> list[dict[str, Any]]:
    """Load every ``*.json`` case from a directory (non-recursive). Skips
    unreadable / malformed files with a warning rather than aborting the run."""
    d = Path(dataset_dir)
    cases: list[dict[str, Any]] = []
    if not d.is_dir():
        logger.warning("ai_eval: dataset dir not found: %s", d)
        return cases
    for path in sorted(d.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("ai_eval: skipping unreadable case %s — %s", path.name, exc)
            continue
        if not isinstance(data, dict) or "feature" not in data or "output" not in data:
            logger.warning("ai_eval: skipping malformed case %s (need feature+output)", path.name)
            continue
        data.setdefault("id", path.stem)
        cases.append(data)
    return cases


def save_report(results: list[dict[str, Any]], out_path: str | Path) -> None:
    """Persist a run report (list of JudgeResult.to_dict())."""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def load_report(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load a saved report keyed by case_id. Returns {} when the file is
    absent (first run has no baseline)."""
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("ai_eval: baseline unreadable %s — %s", p, exc)
        return {}
    return {str(r.get("case_id")): r for r in rows if isinstance(r, dict)}


def compare_to_baseline(current: list[dict[str, Any]],
                        baseline: dict[str, dict[str, Any]],
                        tolerance: float = DEFAULT_REGRESSION_TOLERANCE) -> list[dict[str, Any]]:
    """Return a per-case regression list: cases whose weighted mean dropped by
    more than ``tolerance`` vs baseline. Empty list = no regressions."""
    regressions: list[dict[str, Any]] = []
    for row in current:
        cid = str(row.get("case_id"))
        base = baseline.get(cid)
        if not base:
            continue
        cur_w = float(row.get("weighted", 0.0))
        base_w = float(base.get("weighted", 0.0))
        delta = round(cur_w - base_w, 3)
        if delta < -abs(tolerance):
            regressions.append({
                "case_id": cid, "baseline": base_w,
                "current": cur_w, "delta": delta,
            })
    return regressions
