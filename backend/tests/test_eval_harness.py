"""
test_eval_harness.py — offline unit tests for the ai_eval content-quality harness.

These run WITHOUT network: the judge is exercised via an injected ``complete_fn``
that returns canned JSON, so the rubric maths, gate logic, JSON extraction, and
baseline-regression comparison are all deterministic and CI-safe.
"""
from __future__ import annotations

import json

import pytest

from ai_eval.rubrics import RUBRICS, SUPPORTED_FEATURES, get_rubric
from ai_eval.judge_prompts import build_judge_prompt
from ai_eval.judge import score_case, _extract_json
from ai_eval.dataset import compare_to_baseline, load_cases


# ── rubrics ──────────────────────────────────────────────────────────────────

def test_every_feature_has_a_rubric_with_faithfulness_gate():
    assert set(SUPPORTED_FEATURES) == {"clip", "recap", "reaction", "rewrite"}
    for feature, rubric in RUBRICS.items():
        assert rubric.criteria, f"{feature} has no criteria"
        assert any(c.key == "faithfulness" for c in rubric.criteria)
        assert any(g.criterion_key == "faithfulness" for g in rubric.gates)
        assert rubric.weight_total() > 0


def test_weighted_mean_and_gate_logic():
    rubric = get_rubric("clip")
    perfect = {c.key: 5.0 for c in rubric.criteria}
    assert rubric.weighted_mean(perfect) == 5.0
    assert rubric.gate_failures(perfect) == []
    # Fail the faithfulness gate only.
    hallucinated = {**perfect, "faithfulness": 2.0}
    fails = rubric.gate_failures(hallucinated)
    assert len(fails) == 1 and "faithfulness" in fails[0]


# ── judge prompt ─────────────────────────────────────────────────────────────

def test_judge_prompt_contains_every_criterion_key():
    out = {"clips": [{"start": 1, "end": 30, "title": "t", "reason": "r"}]}
    system, user = build_judge_prompt("clip", out, {"transcript_excerpt": "x"})
    assert "score" in system.lower()
    for c in get_rubric("clip").criteria:
        assert c.key in user
    assert "SOURCE CONTEXT" in user  # inputs block rendered


# ── json extraction ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    '{"scores": {"a": 5}}',
    '```json\n{"scores": {"a": 5}}\n```',
    'here is my verdict:\n{"scores": {"a": 5}}\nthanks',
])
def test_extract_json_tolerant(raw):
    assert _extract_json(raw) == {"scores": {"a": 5}}


def test_extract_json_none_on_garbage():
    assert _extract_json("no json here") is None
    assert _extract_json("") is None


# ── scoring with an injected (offline) judge ─────────────────────────────────

def _fake_judge(scores: dict, flags=None, rationale="ok"):
    payload = json.dumps({"scores": scores, "flags": flags or [], "rationale": rationale})
    def _fn(_system: str, _user: str):
        return payload
    return _fn


def test_score_case_pass_path():
    case = {
        "id": "c1", "feature": "clip",
        "output": {"clips": [{"start": 1, "end": 30, "title": "t", "reason": "r"}]},
    }
    good = {c.key: 5.0 for c in get_rubric("clip").criteria}
    res = score_case(case, complete_fn=_fake_judge(good))
    assert res.ok and res.passed
    assert res.weighted == 5.0
    assert res.gate_failures == []


def test_score_case_gate_fail_blocks_pass_even_with_high_mean():
    case = {"id": "c2", "feature": "recap", "output": {"scenes": []}}
    scores = {c.key: 5.0 for c in get_rubric("recap").criteria}
    scores["faithfulness"] = 3.0  # below the 4.5 gate
    res = score_case(case, complete_fn=_fake_judge(scores))
    assert res.ok
    assert res.gate_failures, "faithfulness gate should have failed"
    assert res.passed is False


def test_score_case_clamps_out_of_range_scores():
    case = {"id": "c3", "feature": "rewrite", "output": {"segments": []}}
    scores = {c.key: 99.0 for c in get_rubric("rewrite").criteria}
    res = score_case(case, complete_fn=_fake_judge(scores))
    assert all(1.0 <= v <= 5.0 for v in res.scores.values())


def test_score_case_unknown_feature_is_error_not_crash():
    res = score_case({"id": "c4", "feature": "nope", "output": {}},
                     complete_fn=_fake_judge({}))
    assert res.ok is False and "unknown feature" in res.error


def test_score_case_unparseable_judge_output_is_error():
    def _bad(_s, _u):
        return "the clips look great honestly"
    res = score_case({"id": "c5", "feature": "clip", "output": {"clips": []}},
                     complete_fn=_bad)
    assert res.ok is False and "parseable" in res.error


def test_score_case_judge_exception_does_not_propagate():
    def _boom(_s, _u):
        raise RuntimeError("network down")
    res = score_case({"id": "c6", "feature": "clip", "output": {"clips": []}},
                     complete_fn=_boom)
    assert res.ok is False and "raised" in res.error


# ── baseline regression comparison ───────────────────────────────────────────

def test_compare_to_baseline_flags_regression():
    current = [{"case_id": "x", "weighted": 3.5}]
    baseline = {"x": {"case_id": "x", "weighted": 4.4}}
    regs = compare_to_baseline(current, baseline, tolerance=0.3)
    assert len(regs) == 1 and regs[0]["case_id"] == "x"


def test_compare_to_baseline_ignores_small_drop_and_improvements():
    current = [{"case_id": "x", "weighted": 4.3}, {"case_id": "y", "weighted": 5.0}]
    baseline = {"x": {"weighted": 4.4}, "y": {"weighted": 4.0}}
    assert compare_to_baseline(current, baseline, tolerance=0.3) == []


# ── fixtures load ────────────────────────────────────────────────────────────

def test_example_golden_case_loads_and_scores():
    import pathlib
    fixtures = pathlib.Path(__file__).parent / "fixtures" / "quality"
    cases = load_cases(fixtures)
    assert any(c["feature"] == "clip" for c in cases), "example clip case should load"
    good = {c.key: 4.0 for c in get_rubric("clip").criteria}
    for case in cases:
        res = score_case(case, complete_fn=_fake_judge(good))
        assert res.ok, f"{case['id']}: {res.error}"
