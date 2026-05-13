from app.ai.visibility.ai_visibility_summary import (
    attach_ai_visibility_summaries,
    build_ai_visibility_summary,
)


def test_summary_empty_when_no_metadata():
    assert build_ai_visibility_summary({}) == {}
    assert build_ai_visibility_summary({"label": "unrelated"}) == {}


def test_badges_generated_from_real_scores():
    summary = build_ai_visibility_summary(
        {
            "part_no": 1,
            "output_score": 91.2345,
            "ranking_components": {
                "hook_score": 84,
                "retention_score": 76,
                "market_score": 70,
                "duration_fit_score": 80,
            },
        }
    )

    assert summary["badges"] == [
        "Strong hook",
        "Good retention",
        "Market fit",
        "Good duration",
        "Strong output rank",
    ]
    assert "High hook score" in summary["reasons"]
    assert summary["signals"]["output_score"] == 91.234
    assert summary["signals"]["hook_score"] == 84


def test_no_fake_reasons_when_score_missing():
    summary = build_ai_visibility_summary({"part_no": 2, "output_score": 42})

    assert "Strong hook" not in summary.get("badges", [])
    assert "High hook score" not in summary.get("reasons", [])
    assert "hook_score" not in summary.get("signals", {})


def test_best_clip_headline_only_when_is_best_true():
    part = {"part_no": 1, "output_score": 72}

    not_best = build_ai_visibility_summary(part, is_best=False)
    best = build_ai_visibility_summary(part, is_best=True)

    assert "headline" not in not_best
    assert best["is_best"] is True
    assert best["headline"] == "AI recommended clip"


def test_malformed_part_metadata_does_not_raise():
    summary = build_ai_visibility_summary(
        {
            "part_no": "not-an-int",
            "output_score": "not-a-score",
            "ranking_components": "bad-components",
            "warnings": [None, "low subtitle confidence"],
            "quality_penalty": "bad-penalty",
        },
        is_best=True,
    )

    assert summary["headline"] == "AI recommended clip"
    assert summary["warnings"] == ["low subtitle confidence"]
    assert "signals" not in summary


def test_warning_metadata_is_preserved_as_warning_text():
    summary = build_ai_visibility_summary(
        {
            "part_no": 1,
            "partial_failure_warning": "1 of 3 selected part(s) failed.",
            "ranking_components": {"quality_penalty": 12},
        }
    )

    assert summary["warnings"] == [
        "1 of 3 selected part(s) failed.",
        "Quality penalty applied: -12",
    ]


def test_attach_preserves_existing_result_json_fields():
    entry = {
        "part_no": 1,
        "output_file": "clip.mp4",
        "output_score": 88.4,
        "is_best_clip": True,
        "ranking_reason": "Best ranked clip from existing scores.",
    }

    attached = attach_ai_visibility_summaries([entry])

    assert "ai_visibility_summary" not in entry
    assert attached[0]["part_no"] == entry["part_no"]
    assert attached[0]["output_file"] == entry["output_file"]
    assert attached[0]["output_score"] == entry["output_score"]
    assert attached[0]["ranking_reason"] == entry["ranking_reason"]
    assert attached[0]["ai_visibility_summary"]["headline"] == "AI recommended clip"
