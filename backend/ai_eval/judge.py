"""
judge.py — score one generated artifact against its feature rubric.

``score_case`` builds the judge prompt, calls the judge LLM (or an injected
``complete_fn`` for offline/unit-test use), parses the JSON verdict, clamps
scores to [1,5], and computes the weighted mean + hard-gate result.

Never raises: any failure yields a JudgeResult with ok=False so a batch run
records the failure and moves on.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ai_eval.judge_prompts import build_judge_prompt
from ai_eval.rubrics import get_rubric

logger = logging.getLogger("ai_eval.judge")

# A completion function: (system, user) -> raw string | None. Injectable so
# tests run without network. Default binds to ai_eval.llm_client.complete.
CompleteFn = Callable[[str, str], Optional[str]]


@dataclass
class JudgeResult:
    case_id: str
    feature: str
    ok: bool
    scores: dict[str, float] = field(default_factory=dict)
    weighted: float = 0.0
    gate_failures: list[str] = field(default_factory=list)
    rationale: str = ""
    flags: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def passed(self) -> bool:
        """Case passes iff the judge ran, no hard gate failed, and the weighted
        mean clears the rubric's ship bar."""
        if not self.ok or self.gate_failures:
            return False
        return self.weighted >= get_rubric(self.feature).accept_min_weighted

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "feature": self.feature,
            "ok": self.ok,
            "scores": self.scores,
            "weighted": self.weighted,
            "passed": self.passed,
            "gate_failures": self.gate_failures,
            "rationale": self.rationale,
            "flags": self.flags,
            "error": self.error,
        }


def _extract_json(raw: str) -> Optional[dict]:
    """Tolerant JSON-object extraction from an LLM response. Mirrors the render
    parser's forgiving strategy without importing it."""
    if not raw:
        return None
    raw = raw.strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _clamp_score(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return max(1.0, min(5.0, f))


def score_case(case: dict[str, Any], *,
               complete_fn: Optional[CompleteFn] = None,
               provider: str = "gemini",
               model: Optional[str] = None) -> JudgeResult:
    """Score one golden case. A case is:
        {"id": str, "feature": str, "output": {...}, "inputs": {...}?}

    ``complete_fn`` overrides the default network judge (for tests). When None,
    binds to ai_eval.llm_client.complete with the given ``provider``/``model``.
    """
    case_id = str(case.get("id", "") or "unknown")
    feature = str(case.get("feature", "") or "").strip().lower()
    try:
        rubric = get_rubric(feature)
    except KeyError:
        return JudgeResult(case_id, feature, ok=False,
                           error=f"unknown feature '{feature}'")

    output = case.get("output")
    if not isinstance(output, dict):
        return JudgeResult(case_id, feature, ok=False,
                           error="case.output missing or not an object")
    inputs = case.get("inputs") if isinstance(case.get("inputs"), dict) else None

    system, user = build_judge_prompt(feature, output, inputs)

    if complete_fn is None:
        from ai_eval.llm_client import complete as _complete
        def complete_fn(_s: str, _u: str) -> Optional[str]:  # type: ignore
            return _complete(provider, _s, _u, model=model)

    try:
        raw = complete_fn(system, user)
    except Exception as exc:  # defensive — a bad injected fn must not crash a batch
        return JudgeResult(case_id, feature, ok=False, error=f"judge call raised: {exc}")

    verdict = _extract_json(raw or "")
    if verdict is None:
        return JudgeResult(case_id, feature, ok=False,
                           error="judge returned no parseable JSON")

    raw_scores = verdict.get("scores")
    if not isinstance(raw_scores, dict):
        return JudgeResult(case_id, feature, ok=False,
                           error="judge JSON missing 'scores' object")

    scores = {c.key: _clamp_score(raw_scores.get(c.key)) for c in rubric.criteria}
    weighted = rubric.weighted_mean(scores)
    gate_failures = rubric.gate_failures(scores)
    flags = verdict.get("flags") if isinstance(verdict.get("flags"), list) else []

    return JudgeResult(
        case_id=case_id, feature=feature, ok=True,
        scores=scores, weighted=weighted, gate_failures=gate_failures,
        rationale=str(verdict.get("rationale", "") or ""),
        flags=[str(f) for f in flags],
    )
