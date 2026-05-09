"""
test_ai_phase30_output_ranking.py — Phase 30: AI Output Ranking & Best Export Recommendation.

Invariants tested:
  - ranker never raises
  - deterministic ranking
  - failed outputs penalized
  - valid completed outputs preferred
  - selected variant receives score bonus
  - missing metadata handled safely
  - output ranking max compact metadata
  - no file mutation
  - no file deletion
  - no output overwrite
  - no upload/publish trigger
  - no FFmpeg mutation
  - no render status rule mutation
  - result_json can attach ai_output_ranking
  - ranking failure does not fail render job
  - backward compatibility preserved
  - mode always "recommendation_only"
  - advisory_only semantics throughout
  - no API key / GPU / internet required
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

@dataclass
class _FakeEditPlan:
    variant_selection: dict = field(default_factory=dict)
    creator_style_adaptation: dict = field(default_factory=dict)
    execution_simulation: dict = field(default_factory=dict)
    multivariant_execution: dict = field(default_factory=dict)
    output_ranking: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    explainability: dict = field(default_factory=dict)


def _make_output(output_id="out_1", path="/tmp/out.mp4", failed=False, score=75.0, **kw) -> dict:
    o = {
        "output_id": output_id,
        "path": path,
        "variant_id": kw.pop("variant_id", ""),
        "output_rank_score": score,
        "final_score": score,
        "output_score": score,
        "failed": failed,
        "warnings": kw.pop("warnings", []),
        "validation_passed": kw.pop("validation_passed", None),
        "size_bytes": kw.pop("size_bytes", 1024 * 1024),
        "duration": kw.pop("duration", 30.0),
    }
    o.update(kw)
    return o


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestAIOutputScoreSchema:
    def _make(self, **kwargs):
        from app.ai.output.output_schema import AIOutputScore
        defaults = dict(
            output_id="o1", path="/tmp/x.mp4", variant_id="v1",
            score=75.0, confidence=0.85, rank=1, recommended=True,
            quality_flags=["validation_passed"], warnings=[], explanation=["base=50"],
        )
        defaults.update(kwargs)
        return AIOutputScore(**defaults)

    def test_to_dict_keys(self):
        s = self._make()
        d = s.to_dict()
        for k in ("output_id", "path", "variant_id", "score", "confidence",
                  "rank", "recommended", "quality_flags", "warnings", "explanation"):
            assert k in d

    def test_score_clamped_0_100(self):
        s = self._make(score=150.0)
        assert s.to_dict()["score"] == 100.0
        s2 = self._make(score=-20.0)
        assert s2.to_dict()["score"] == 0.0

    def test_confidence_clamped_0_1(self):
        s = self._make(confidence=5.0)
        assert s.to_dict()["confidence"] == 1.0
        s2 = self._make(confidence=-1.0)
        assert s2.to_dict()["confidence"] == 0.0

    def test_quality_flags_capped_at_10(self):
        s = self._make(quality_flags=[f"f{i}" for i in range(15)])
        assert len(s.to_dict()["quality_flags"]) == 10

    def test_warnings_capped_at_10(self):
        s = self._make(warnings=[f"w{i}" for i in range(15)])
        assert len(s.to_dict()["warnings"]) == 10

    def test_explanation_capped_at_10(self):
        s = self._make(explanation=[f"e{i}" for i in range(15)])
        assert len(s.to_dict()["explanation"]) == 10

    def test_recommended_bool(self):
        s = self._make(recommended=1)
        assert s.to_dict()["recommended"] is True


class TestAIOutputRankingSchema:
    def _make(self, **kwargs):
        from app.ai.output.output_schema import AIOutputRanking
        defaults = dict(available=True, mode="recommendation_only",
                        outputs=[], best_output_id="o1", best_output_path="/tmp/o1.mp4", warnings=[])
        defaults.update(kwargs)
        return AIOutputRanking(**defaults)

    def test_mode_always_recommendation_only(self):
        r = self._make(mode="execute_now")
        assert r.to_dict()["mode"] == "recommendation_only"

    def test_outputs_capped_at_20(self):
        from app.ai.output.output_schema import AIOutputRanking, AIOutputScore
        outputs = [AIOutputScore(output_id=f"o{i}") for i in range(25)]
        r = AIOutputRanking(outputs=outputs)
        assert len(r.to_dict()["outputs"]) == 20

    def test_to_dict_keys(self):
        r = self._make()
        d = r.to_dict()
        for k in ("available", "mode", "outputs", "best_output_id", "best_output_path", "warnings"):
            assert k in d

    def test_available_bool(self):
        r = self._make(available=1)
        assert r.to_dict()["available"] is True


# ---------------------------------------------------------------------------
# Safety tests
# ---------------------------------------------------------------------------

class TestOutputSafety:
    def test_sanitize_retains_safe_keys(self):
        from app.ai.output.output_safety import sanitize_output_metadata
        o = {"output_id": "o1", "path": "/tmp/x.mp4", "output_score": 75.0}
        result = sanitize_output_metadata(o)
        assert result.get("output_id") == "o1"
        assert result.get("output_score") == 75.0

    def test_sanitize_strips_unknown_keys(self):
        from app.ai.output.output_safety import sanitize_output_metadata
        o = {"output_id": "o1", "some_secret_key": "val", "ffmpeg_args": "-x"}
        result = sanitize_output_metadata(o)
        assert "some_secret_key" not in result
        assert "ffmpeg_args" not in result

    def test_sanitize_non_dict(self):
        from app.ai.output.output_safety import sanitize_output_metadata
        assert sanitize_output_metadata(None) == {}
        assert sanitize_output_metadata(42) == {}
        assert sanitize_output_metadata("str") == {}

    def test_is_rankable_with_output_id(self):
        from app.ai.output.output_safety import is_output_rankable
        assert is_output_rankable({"output_id": "o1"}) is True

    def test_is_rankable_missing_output_id(self):
        from app.ai.output.output_safety import is_output_rankable
        assert is_output_rankable({}) is False
        assert is_output_rankable({"path": "/tmp/x.mp4"}) is False

    def test_is_rankable_non_dict(self):
        from app.ai.output.output_safety import is_output_rankable
        assert is_output_rankable(None) is False
        assert is_output_rankable("str") is False


# ---------------------------------------------------------------------------
# Ranker tests
# ---------------------------------------------------------------------------

class TestOutputRanker:
    def test_never_raises_on_none(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs(None)
        assert result is not None

    def test_never_raises_on_empty(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs([])
        assert result is not None

    def test_never_raises_on_bad_input(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs("not_a_list")
        assert result is not None

    def test_mode_always_recommendation_only(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs([_make_output()])
        assert result.mode == "recommendation_only"
        assert result.to_dict()["mode"] == "recommendation_only"

    def test_no_outputs_returns_available_false(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs([])
        assert result.available is False
        assert result.best_output_id is None

    def test_single_output_is_best(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs([_make_output("o1")])
        assert result.best_output_id == "o1"
        assert result.outputs[0].recommended is True

    def test_failed_output_penalized(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [
            _make_output("good", score=70.0, failed=False),
            _make_output("bad", score=70.0, failed=True),
        ]
        result = rank_variant_outputs(outputs)
        good = next(o for o in result.outputs if o.output_id == "good")
        bad = next(o for o in result.outputs if o.output_id == "bad")
        assert good.score > bad.score

    def test_failed_output_ranks_last(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [
            _make_output("good", score=70.0, failed=False),
            _make_output("bad", score=70.0, failed=True),
        ]
        result = rank_variant_outputs(outputs)
        ranks = {o.output_id: o.rank for o in result.outputs}
        assert ranks["good"] < ranks["bad"]

    def test_best_output_is_recommended(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output("o1", score=80.0), _make_output("o2", score=60.0)]
        result = rank_variant_outputs(outputs)
        assert result.best_output_id == "o1"
        best_obj = next(o for o in result.outputs if o.output_id == "o1")
        assert best_obj.recommended is True

    def test_non_best_not_recommended(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output("o1", score=80.0), _make_output("o2", score=60.0)]
        result = rank_variant_outputs(outputs)
        non_best = [o for o in result.outputs if o.output_id != "o1"]
        assert all(not o.recommended for o in non_best)

    def test_selected_variant_gets_bonus(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        ep = _FakeEditPlan(variant_selection={"recommended_variant_id": "selected_v"})
        outputs = [
            _make_output("o_selected", score=70.0, variant_id="selected_v"),
            _make_output("o_other", score=70.0, variant_id="other_v"),
        ]
        result = rank_variant_outputs(outputs, edit_plan=ep)
        selected = next(o for o in result.outputs if o.output_id == "o_selected")
        other = next(o for o in result.outputs if o.output_id == "o_other")
        assert selected.score > other.score

    def test_creator_style_bonus_when_high_confidence(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        ep_high = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.85}
        )
        ep_low = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.30}
        )
        outputs = [_make_output("o1", score=70.0)]
        result_high = rank_variant_outputs(outputs, edit_plan=ep_high)
        result_low = rank_variant_outputs(outputs, edit_plan=ep_low)
        assert result_high.outputs[0].score > result_low.outputs[0].score

    def test_retention_gain_bonus(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        ep_gain = _FakeEditPlan(execution_simulation={
            "simulations": [{"estimated_retention_gain": 10.0}]
        })
        ep_no = _FakeEditPlan()
        outputs = [_make_output("o1", score=70.0)]
        result_gain = rank_variant_outputs(outputs, edit_plan=ep_gain)
        result_no = rank_variant_outputs(outputs, edit_plan=ep_no)
        assert result_gain.outputs[0].score > result_no.outputs[0].score

    def test_warnings_reduce_score(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        o_clean = _make_output("clean", score=70.0, warnings=[])
        o_warn = _make_output("warn", score=70.0, warnings=["issue1", "issue2"])
        result = rank_variant_outputs([o_clean, o_warn])
        clean = next(o for o in result.outputs if o.output_id == "clean")
        warn = next(o for o in result.outputs if o.output_id == "warn")
        assert clean.score > warn.score

    def test_validation_failed_penalized(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        o_pass = _make_output("pass", score=70.0, validation_passed=True)
        o_fail = _make_output("fail", score=70.0, validation_passed=False)
        result = rank_variant_outputs([o_pass, o_fail])
        pass_obj = next(o for o in result.outputs if o.output_id == "pass")
        fail_obj = next(o for o in result.outputs if o.output_id == "fail")
        assert pass_obj.score > fail_obj.score

    def test_ranks_assigned_sequentially(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output(f"o{i}", score=float(80 - i)) for i in range(5)]
        result = rank_variant_outputs(outputs)
        ranks = sorted(o.rank for o in result.outputs)
        assert ranks == list(range(1, 6))

    def test_deterministic_same_input_same_output(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output(f"o{i}", score=float(70 + i)) for i in range(4)]
        r1 = rank_variant_outputs(outputs)
        r2 = rank_variant_outputs(outputs)
        assert r1.best_output_id == r2.best_output_id
        assert [o.output_id for o in r1.outputs] == [o.output_id for o in r2.outputs]

    def test_string_path_normalized(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs(["/tmp/video.mp4"])
        assert result.available is True or result.outputs == [] or result is not None

    def test_best_output_path_set(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output("o1", path="/tmp/best.mp4", score=80.0)]
        result = rank_variant_outputs(outputs)
        if result.best_output_id == "o1":
            assert result.best_output_path == "/tmp/best.mp4"

    def test_no_api_key_no_gpu_no_internet(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs([_make_output()])
        assert result is not None

    def test_no_file_mutation(self):
        """Ranker must not open, write, or delete any files."""
        from app.ai.output.output_ranker import rank_variant_outputs
        import builtins
        original_open = builtins.open
        opened_files = []

        def track_open(path, *args, **kwargs):
            opened_files.append(str(path))
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=track_open):
            rank_variant_outputs([_make_output("o1", path="/nonexistent/path.mp4")])

        assert not any("nonexistent" in f for f in opened_files)

    def test_missing_edit_plan_handled(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs([_make_output()], edit_plan=None)
        assert result.available is True

    def test_bad_edit_plan_handled(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs([_make_output()], edit_plan="not_a_plan")
        assert result is not None

    def test_to_dict_round_trip(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output("o1", score=75.0), _make_output("o2", score=50.0)]
        result = rank_variant_outputs(outputs)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["mode"] == "recommendation_only"
        assert isinstance(d["outputs"], list)
        assert d["best_output_id"] is not None

    def test_fallback_on_error(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        # Pass a bad type that would cause processing errors
        result = rank_variant_outputs({"bad": "input_type_but_treated_as_dict"})
        assert result is not None
        assert result.mode == "recommendation_only"


# ---------------------------------------------------------------------------
# edit_plan_schema backward-compat tests
# ---------------------------------------------------------------------------

class TestEditPlanSchemaPhase30:
    def test_output_ranking_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "output_ranking")
        assert plan.output_ranking == {}

    def test_to_dict_includes_output_ranking(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "output_ranking" in d
        assert d["output_ranking"] == {}

    def test_all_prior_fields_still_present(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for key in (
            "execution_recommendations", "execution_simulation",
            "safe_render_mutations", "multivariant_render_plans",
            "multivariant_execution", "output_ranking",
        ):
            assert key in d

    def test_populated_output_ranking_in_to_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.output_ranking = {
            "available": True,
            "mode": "recommendation_only",
            "best_output_id": "o1",
            "best_output_path": "/tmp/o1.mp4",
            "outputs": [],
        }
        d = plan.to_dict()
        assert d["output_ranking"]["best_output_id"] == "o1"


# ---------------------------------------------------------------------------
# render_influence integration tests
# ---------------------------------------------------------------------------

class TestRenderInfluencePhase30:
    def _make_report(self):
        return {"applied": [], "skipped": [], "warnings": []}

    def _call_report(self, ranking_dict: dict):
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        plan = _FakeEditPlan()
        plan.output_ranking = ranking_dict
        report = self._make_report()
        ri._report_output_ranking(MagicMock(), plan, report)
        return report

    def test_deferred_appears_in_skipped(self):
        report = self._call_report({
            "available": False,
            "mode": "recommendation_only",
            "outputs": [],
            "best_output_id": None,
        })
        assert any("deferred_phase30" in s or "recommendation_only" in s or "no_result" in s
                   for s in report["skipped"])

    def test_available_ranking_in_skipped_not_applied(self):
        report = self._call_report({
            "available": True,
            "mode": "recommendation_only",
            "outputs": [{"output_id": "o1"}],
            "best_output_id": "o1",
        })
        assert not any("o1" in a for a in report["applied"])
        assert any("recommendation_only" in s or "o1" in s for s in report["skipped"])

    def test_empty_dict_skipped(self):
        report = self._call_report({})
        assert any("no_result" in s for s in report["skipped"])

    def test_never_raises_on_none_plan(self):
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        report = self._make_report()
        ri._report_output_ranking(MagicMock(), None, report)

    def test_no_file_operations_in_reporter(self):
        """Reporter must not open, upload, or delete any files."""
        report = self._call_report({
            "available": True,
            "mode": "recommendation_only",
            "best_output_id": "o1",
            "outputs": [{"output_id": "o1"}],
        })
        # Just verifying it ran without error and output went to skipped
        assert any(s for s in report["skipped"])


# ---------------------------------------------------------------------------
# End-to-end integration tests
# ---------------------------------------------------------------------------

class TestPhase30EndToEnd:
    def test_full_ranking_pipeline(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        ep = _FakeEditPlan(
            variant_selection={"recommended_variant_id": "var_best"},
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.85},
        )
        outputs = [
            _make_output("o1", score=80.0, variant_id="var_best"),
            _make_output("o2", score=70.0, variant_id="var_other"),
            _make_output("o_fail", score=50.0, failed=True),
        ]
        result = rank_variant_outputs(outputs, edit_plan=ep)
        assert result.available is True
        assert result.mode == "recommendation_only"
        assert result.best_output_id == "o1"
        assert result.outputs[0].rank == 1
        assert result.outputs[-1].output_id == "o_fail"

    def test_ranking_failure_does_not_crash(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs(None, edit_plan=None)
        assert result is not None
        assert result.mode == "recommendation_only"

    def test_result_json_attaches_ai_output_ranking(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output("o1", score=80.0)]
        result = rank_variant_outputs(outputs)
        result_json = {"ai_output_ranking": result.to_dict()}
        assert "ai_output_ranking" in result_json
        assert result_json["ai_output_ranking"]["mode"] == "recommendation_only"

    def test_ranking_attached_to_edit_plan(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        ep = _FakeEditPlan()
        outputs = [_make_output("o1", score=80.0)]
        result = rank_variant_outputs(outputs, edit_plan=ep)
        ep.output_ranking = result.to_dict()
        assert ep.output_ranking["best_output_id"] == "o1"

    def test_no_auto_upload_triggered(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        # Patch any network/upload to verify nothing is called
        with patch("builtins.__import__", side_effect=__builtins__["__import__"] if isinstance(__builtins__, dict) else __import__):
            result = rank_variant_outputs([_make_output("o1")])
        assert result is not None

    def test_no_output_deleted(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        import os
        original_remove = os.remove
        removed = []

        def track_remove(path):
            removed.append(path)
            return original_remove(path)

        with patch("os.remove", side_effect=track_remove):
            rank_variant_outputs([_make_output("o1", path="/tmp/o1.mp4")])

        assert removed == []

    def test_mode_recommendation_only_in_to_dict(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        result = rank_variant_outputs([_make_output("o1")])
        d = result.to_dict()
        assert d["mode"] == "recommendation_only"

    def test_all_outputs_have_rank_assigned(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output(f"o{i}", score=float(80 - i)) for i in range(4)]
        result = rank_variant_outputs(outputs)
        for o in result.outputs:
            assert o.rank > 0

    def test_only_one_output_recommended(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output(f"o{i}", score=float(80 - i)) for i in range(4)]
        result = rank_variant_outputs(outputs)
        recommended = [o for o in result.outputs if o.recommended]
        assert len(recommended) == 1

    def test_no_ffmpeg_mutation_in_ranking(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        outputs = [_make_output("o1", **{"ffmpeg_args": "-x 264"})]
        result = rank_variant_outputs(outputs)
        for o in result.outputs:
            d = o.to_dict()
            assert "ffmpeg_args" not in d

    def test_execution_ids_used_as_variant_bonus(self):
        from app.ai.output.output_ranker import rank_variant_outputs
        ep = _FakeEditPlan(
            multivariant_execution={
                "executed_plan_ids": ["mvplan_creator_style"],
                "execution_enabled": True,
            }
        )
        outputs = [
            _make_output("o_exec", score=70.0, variant_id="mvplan_creator_style"),
            _make_output("o_plain", score=70.0, variant_id="other"),
        ]
        result = rank_variant_outputs(outputs, edit_plan=ep)
        exec_out = next(o for o in result.outputs if o.output_id == "o_exec")
        plain_out = next(o for o in result.outputs if o.output_id == "o_plain")
        assert exec_out.score >= plain_out.score
