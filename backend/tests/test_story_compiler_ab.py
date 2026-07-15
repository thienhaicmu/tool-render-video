from __future__ import annotations

from app.domain.story_plan_v2 import Beat, StoryPlan, Visual
from ai_eval.ab_story_compiler import _recover_rows, load_cases, paired_summary


def test_story_golden_dataset_has_ten_diverse_cases():
    cases = load_cases()
    assert len(cases) >= 10
    assert {case["source"] for case in cases} == {"paste", "idea"}
    assert {case["language"] for case in cases} >= {"vi", "en"}
    assert all(case.get("chapter") or case.get("idea") for case in cases)


def test_paired_summary_reports_direction_and_ship_floor():
    rows = []
    for index in range(10):
        for arm, score in (("legacy", 60), ("compiler", 65)):
            rows.append({"case_id": f"c{index}", "run": 1, "arm": arm,
                         "usable": True, "arm_valid": True,
                         "structural": {"overall_score": score}})
    summary = paired_summary(rows)
    assert summary["pairs"] == 10
    assert summary["usable_pairs"] == 10
    assert summary["compiler_wins"] == 10
    assert summary["mean_score_delta"] == 5
    assert summary["ship_signal"] is True


def test_recover_rows_from_plan_checkpoint(tmp_path):
    case = {"id": "checkpoint_case", "source": "idea", "idea": "x",
            "duration_sec": 10, "language": "en"}
    plans = tmp_path / "plans"
    plans.mkdir()
    plan = StoryPlan(language="en", visuals=[Visual(id="v1")],
                     timeline=[Beat(id="b1", narration="hello", visual_id="v1")])
    (plans / "checkpoint_case_r1_compiler.json").write_text(plan.to_json(), encoding="utf-8")
    rows = _recover_rows(tmp_path, [case])
    assert len(rows) == 1
    assert rows[0]["recovered_from_plan"] is True
    assert rows[0]["usable"] is True
    assert rows[0]["arm_valid"] is None


def test_paired_summary_excludes_fallback_and_unknown_provenance():
    rows = [
        {"case_id": "fallback", "run": 1, "arm": "legacy", "usable": True,
         "arm_valid": True, "structural": {"overall_score": 70}},
        {"case_id": "fallback", "run": 1, "arm": "compiler", "usable": True,
         "arm_valid": False, "structural": {"overall_score": 80}},
        {"case_id": "unknown", "run": 1, "arm": "legacy", "usable": True,
         "arm_valid": True, "structural": {"overall_score": 70}},
        {"case_id": "unknown", "run": 1, "arm": "compiler", "usable": True,
         "arm_valid": None, "structural": {"overall_score": 80}},
    ]
    summary = paired_summary(rows)
    assert summary["qualified_pairs"] == 0
    assert summary["invalid_arm_pairs"] == 1
    assert summary["unknown_provenance_pairs"] == 1
