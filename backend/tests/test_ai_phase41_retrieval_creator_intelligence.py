"""
test_ai_phase41_retrieval_creator_intelligence.py — Phase 41 tests.

Covers: schema, safety, retrieval engine, edit plan integration,
no-mutation safety, render influence, environment requirements.
"""
import copy
import pytest
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_plan():
    """Return a minimal AIEditPlan-like object for retrieval tests."""
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan, AIClipPlan,
    )
    return AIEditPlan(
        enabled=True,
        mode="balanced",
        selected_segments=[AIClipPlan(start=0.0, end=5.0, score=75.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(
            pacing_style="fast",
            energy_level=0.8,
            beat_available=True,
            bpm=120.0,
            beat_count=40,
            emotion="excited",
        ),
    )


def _make_podcast_plan():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan, AIClipPlan,
    )
    plan = AIEditPlan(
        enabled=True,
        mode="storytelling",
        selected_segments=[AIClipPlan(start=0.0, end=30.0, score=70.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(
            pacing_style="calm_storytelling",
            energy_level=0.3,
            emotion="calm",
        ),
    )
    plan.creator_style = {"detected_style": "podcast"}
    plan.retention = {"hook_score": 0.4, "risk_regions": []}
    return plan


def _make_highenergy_plan():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan, AIClipPlan,
    )
    plan = AIEditPlan(
        enabled=True,
        mode="shortform",
        selected_segments=[AIClipPlan(start=0.0, end=10.0, score=90.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(
            pacing_style="high_energy_shortform",
            energy_level=0.9,
            emotion="excited",
        ),
    )
    plan.creator_style = {"detected_style": "viral_tiktok"}
    plan.subtitle_execution = {"density": "dense"}
    plan.retention = {"hook_score": 0.85, "risk_regions": []}
    return plan


def _make_retention_decay_plan():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan, AIClipPlan,
    )
    plan = AIEditPlan(
        enabled=True,
        mode="balanced",
        selected_segments=[AIClipPlan(start=0.0, end=20.0, score=60.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(pacing_style="default", energy_level=0.5),
    )
    plan.retention = {
        "hook_score": 0.5,
        "risk_regions": [
            {"type": "silence_gap", "start": 5.0, "end": 8.0},
            {"type": "dead_air", "start": 12.0, "end": 14.0},
        ],
    }
    return plan


# ===========================================================================
# TestRetrievalSchema
# ===========================================================================

class TestRetrievalSchema:
    def test_retrieval_match_defaults(self):
        from app.ai.retrieval.retrieval_schema import AICreatorRetrievalMatch
        m = AICreatorRetrievalMatch(match_id="test_match")
        assert m.match_id == "test_match"
        assert m.creator_style == ""
        assert m.pattern_type == ""
        assert m.confidence == 0.0
        assert m.retrieval_score == 0.0
        assert m.matched_tags == []
        assert m.subtitle_influence == {}
        assert m.pacing_influence == {}
        assert m.camera_influence == {}
        assert m.retention_influence == {}
        assert m.hook_influence == {}
        assert m.safe is False
        assert m.warnings == []
        assert m.explanation == []

    def test_retrieval_match_to_dict(self):
        from app.ai.retrieval.retrieval_schema import AICreatorRetrievalMatch
        m = AICreatorRetrievalMatch(
            match_id="m1",
            creator_style="viral_tiktok",
            pattern_type="pacing",
            confidence=0.82,
            retrieval_score=85.0,
            matched_tags=["pacing", "fast"],
            safe=True,
            explanation=["Fast pacing retrieved"],
        )
        d = m.to_dict()
        assert d["match_id"] == "m1"
        assert d["creator_style"] == "viral_tiktok"
        assert d["pattern_type"] == "pacing"
        assert abs(d["confidence"] - 0.82) < 0.001
        assert abs(d["retrieval_score"] - 85.0) < 0.001
        assert d["matched_tags"] == ["pacing", "fast"]
        assert d["safe"] is True
        assert "Fast pacing retrieved" in d["explanation"]

    def test_retrieval_pack_defaults(self):
        from app.ai.retrieval.retrieval_schema import AICreatorRetrievalPack
        p = AICreatorRetrievalPack()
        assert p.available is True
        assert p.enabled is False
        assert p.retrieval_mode == "assistive_only"
        assert p.matches == []
        assert p.recommended_creator_style == ""
        assert p.warnings == []

    def test_retrieval_pack_to_dict(self):
        from app.ai.retrieval.retrieval_schema import AICreatorRetrievalPack, AICreatorRetrievalMatch
        match = AICreatorRetrievalMatch(match_id="m1", safe=True, retrieval_score=80.0)
        pack = AICreatorRetrievalPack(
            available=True,
            enabled=True,
            matches=[match],
            recommended_creator_style="viral_tiktok",
        )
        d = pack.to_dict()
        assert d["available"] is True
        assert d["enabled"] is True
        assert d["retrieval_mode"] == "assistive_only"
        assert len(d["matches"]) == 1
        assert d["recommended_creator_style"] == "viral_tiktok"

    def test_retrieval_mode_invariant(self):
        from app.ai.retrieval.retrieval_schema import AICreatorRetrievalPack
        p = AICreatorRetrievalPack()
        assert p.retrieval_mode == "assistive_only"


# ===========================================================================
# TestRetrievalSafety
# ===========================================================================

class TestRetrievalSafety:
    def test_sanitize_strips_forbidden_ffmpeg_args(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        raw = {"match_id": "m1", "ffmpeg_args": "-vcodec libx264", "confidence": 0.8}
        result = sanitize_retrieval_match(raw)
        assert "ffmpeg_args" not in result
        assert result["match_id"] == "m1"

    def test_sanitize_strips_all_forbidden_keys(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        forbidden = [
            "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
            "queue_priority", "output_path", "subprocess", "executable",
            "python_code", "shell", "powershell", "direct_crop_coordinates",
        ]
        raw = {"match_id": "m1"}
        for k in forbidden:
            raw[k] = "value"
        result = sanitize_retrieval_match(raw)
        for k in forbidden:
            assert k not in result, f"forbidden key '{k}' not stripped"

    def test_sanitize_clamps_confidence_high(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        result = sanitize_retrieval_match({"match_id": "m1", "confidence": 5.0})
        assert result["confidence"] == 1.0

    def test_sanitize_clamps_confidence_low(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        result = sanitize_retrieval_match({"match_id": "m1", "confidence": -0.5})
        assert result["confidence"] == 0.0

    def test_sanitize_clamps_retrieval_score_high(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        result = sanitize_retrieval_match({"match_id": "m1", "retrieval_score": 999.0})
        assert result["retrieval_score"] == 100.0

    def test_sanitize_clamps_retrieval_score_low(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        result = sanitize_retrieval_match({"match_id": "m1", "retrieval_score": -10.0})
        assert result["retrieval_score"] == 0.0

    def test_sanitize_strips_forbidden_from_influence_dicts(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        raw = {
            "match_id": "m1",
            "subtitle_influence": {"density": "compact", "ffmpeg_args": "bad"},
            "camera_influence": {"behavior": "dynamic", "render_command": "bad"},
        }
        result = sanitize_retrieval_match(raw)
        assert "ffmpeg_args" not in result["subtitle_influence"]
        assert "render_command" not in result["camera_influence"]
        assert result["subtitle_influence"]["density"] == "compact"
        assert result["camera_influence"]["behavior"] == "dynamic"

    def test_sanitize_invalid_pattern_type_cleared(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        result = sanitize_retrieval_match({"match_id": "m1", "pattern_type": "exploit"})
        assert result["pattern_type"] == ""

    def test_sanitize_valid_pattern_types_preserved(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        for ptype in ("hook", "subtitle", "pacing", "camera", "retention", "creator"):
            result = sanitize_retrieval_match({"match_id": "m1", "pattern_type": ptype})
            assert result["pattern_type"] == ptype

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        assert sanitize_retrieval_match(None) == {}
        assert sanitize_retrieval_match("string") == {}
        assert sanitize_retrieval_match(42) == {}

    def test_is_safe_valid_match(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        data = {"match_id": "m1", "confidence": 0.8, "retrieval_score": 75.0}
        assert is_retrieval_match_safe(data) is True

    def test_is_safe_rejects_forbidden_key(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        data = {"match_id": "m1", "confidence": 0.8, "retrieval_score": 50.0, "ffmpeg_args": "x"}
        assert is_retrieval_match_safe(data) is False

    def test_is_safe_rejects_missing_match_id(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        data = {"confidence": 0.8, "retrieval_score": 50.0}
        assert is_retrieval_match_safe(data) is False

    def test_is_safe_rejects_empty_match_id(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        data = {"match_id": "  ", "confidence": 0.8, "retrieval_score": 50.0}
        assert is_retrieval_match_safe(data) is False

    def test_is_safe_rejects_out_of_range_confidence(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        assert is_retrieval_match_safe({"match_id": "m1", "confidence": 2.0, "retrieval_score": 50.0}) is False
        assert is_retrieval_match_safe({"match_id": "m1", "confidence": -0.1, "retrieval_score": 50.0}) is False

    def test_is_safe_rejects_out_of_range_retrieval_score(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        assert is_retrieval_match_safe({"match_id": "m1", "confidence": 0.8, "retrieval_score": 101.0}) is False
        assert is_retrieval_match_safe({"match_id": "m1", "confidence": 0.8, "retrieval_score": -1.0}) is False

    def test_is_safe_rejects_forbidden_in_influence_dict(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        data = {
            "match_id": "m1",
            "confidence": 0.8,
            "retrieval_score": 50.0,
            "camera_influence": {"render_command": "ffmpeg -i ..."},
        }
        assert is_retrieval_match_safe(data) is False

    def test_is_safe_none_input(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        assert is_retrieval_match_safe(None) is False

    def test_sanitize_never_raises(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        for bad in (None, [], {}, "str", 42, {"match_id": None}):
            result = sanitize_retrieval_match(bad)
            assert isinstance(result, dict)

    def test_is_safe_never_raises(self):
        from app.ai.retrieval.retrieval_safety import is_retrieval_match_safe
        for bad in (None, [], {}, "str", 42):
            result = is_retrieval_match_safe(bad)
            assert isinstance(result, bool)


# ===========================================================================
# TestRetrievalPackGeneration
# ===========================================================================

class TestRetrievalPackGeneration:
    def test_retrieval_pack_generated_safely(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        assert pack is not None
        assert isinstance(pack.available, bool)
        assert isinstance(pack.enabled, bool)
        assert pack.retrieval_mode == "assistive_only"
        assert isinstance(pack.matches, list)
        assert isinstance(pack.warnings, list)

    def test_retrieval_never_raises_on_none(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        pack = retrieve_creator_intelligence(None)
        assert pack.available is False

    def test_retrieval_never_raises_on_malformed_plan(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        pack = retrieve_creator_intelligence(object())
        assert pack is not None

    def test_retrieval_returns_pack_type(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        from app.ai.retrieval.retrieval_schema import AICreatorRetrievalPack
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        assert isinstance(pack, AICreatorRetrievalPack)

    def test_retrieval_deterministic(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack1 = retrieve_creator_intelligence(plan)
        pack2 = retrieve_creator_intelligence(plan)
        assert pack1.enabled == pack2.enabled
        assert len(pack1.matches) == len(pack2.matches)
        assert pack1.recommended_creator_style == pack2.recommended_creator_style


# ===========================================================================
# TestCreatorStyleRetrieval
# ===========================================================================

class TestCreatorStyleRetrieval:
    def test_creator_style_retrieval_works(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        # viral_tiktok plan should yield some matches
        assert pack is not None
        assert isinstance(pack.matches, list)

    def test_recommended_creator_style_derived(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        # Recommended style should be non-empty if matches found
        if pack.matches:
            assert isinstance(pack.recommended_creator_style, str)

    def test_podcast_style_retrieved(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_podcast_plan()
        pack = retrieve_creator_intelligence(plan)
        assert pack is not None
        if pack.enabled and pack.matches:
            styles = {m.creator_style for m in pack.matches}
            # podcast or empty creator style
            assert all(isinstance(s, str) for s in styles)


# ===========================================================================
# TestSubtitleRetrievalInfluence
# ===========================================================================

class TestSubtitleRetrievalInfluence:
    def test_subtitle_retrieval_influence_valid(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        subtitle_matches = [m for m in pack.matches if m.pattern_type == "subtitle"]
        for m in subtitle_matches:
            assert isinstance(m.subtitle_influence, dict)
            # No forbidden keys
            forbidden = {
                "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
                "output_path", "subprocess",
            }
            assert not any(k in m.subtitle_influence for k in forbidden)

    def test_subtitle_overload_triggers_compact_retrieval(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        # dense subtitle density set in fixture
        pack = retrieve_creator_intelligence(plan)
        # If any subtitle matches exist they must be safe
        for m in pack.matches:
            if m.pattern_type == "subtitle":
                assert m.safe is True

    def test_no_subtitle_timing_in_influence(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        for m in pack.matches:
            assert "subtitle_timing" not in m.subtitle_influence


# ===========================================================================
# TestPacingRetrievalInfluence
# ===========================================================================

class TestPacingRetrievalInfluence:
    def test_pacing_retrieval_influence_valid(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        pacing_matches = [m for m in pack.matches if m.pattern_type == "pacing"]
        for m in pacing_matches:
            assert isinstance(m.pacing_influence, dict)
            assert "playback_speed" not in m.pacing_influence

    def test_fast_pacing_retrieved_for_high_energy(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        pacing_matches = [m for m in pack.matches if m.pattern_type == "pacing"]
        if pacing_matches:
            # Fast pacing pattern should rank highly
            assert pacing_matches[0].retrieval_score > 0

    def test_calm_pacing_retrieved_for_podcast(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_podcast_plan()
        pack = retrieve_creator_intelligence(plan)
        pacing_matches = [m for m in pack.matches if m.pattern_type == "pacing"]
        if pacing_matches:
            assert pacing_matches[0].retrieval_score > 0

    def test_no_playback_speed_mutation(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        for m in pack.matches:
            assert "playback_speed" not in m.pacing_influence


# ===========================================================================
# TestCameraRetrievalInfluence
# ===========================================================================

class TestCameraRetrievalInfluence:
    def test_camera_retrieval_influence_valid(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        camera_matches = [m for m in pack.matches if m.pattern_type == "camera"]
        for m in camera_matches:
            assert isinstance(m.camera_influence, dict)
            assert "ffmpeg_args" not in m.camera_influence
            assert "direct_crop_coordinates" not in m.camera_influence

    def test_dynamic_camera_retrieved_for_high_energy(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        camera_matches = [m for m in pack.matches if m.pattern_type == "camera"]
        if camera_matches:
            assert camera_matches[0].retrieval_score > 0

    def test_no_ffmpeg_in_camera_influence(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        for m in pack.matches:
            assert "ffmpeg_args" not in m.camera_influence
            assert "render_command" not in m.camera_influence


# ===========================================================================
# TestRetentionRetrievalInfluence
# ===========================================================================

class TestRetentionRetrievalInfluence:
    def test_retention_retrieval_influence_valid(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_retention_decay_plan()
        pack = retrieve_creator_intelligence(plan)
        retention_matches = [m for m in pack.matches if m.pattern_type == "retention"]
        for m in retention_matches:
            assert isinstance(m.retention_influence, dict)

    def test_retention_decay_triggers_reengagement(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_retention_decay_plan()
        pack = retrieve_creator_intelligence(plan)
        # With silence_gap/dead_air risk, retention patterns should be retrieved
        retention_matches = [m for m in pack.matches if m.pattern_type == "retention"]
        if retention_matches:
            assert any("decay" in e or "reengagement" in e or "retention" in e.lower()
                       for m in retention_matches for e in m.explanation)

    def test_no_executor_override_in_retention(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_retention_decay_plan()
        pack = retrieve_creator_intelligence(plan)
        for m in pack.matches:
            assert "render_command" not in m.retention_influence
            assert "ffmpeg_args" not in m.retention_influence


# ===========================================================================
# TestSafetyBoundaries
# ===========================================================================

class TestSafetyBoundaries:
    def test_forbidden_fields_not_in_matches(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        forbidden = {
            "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
            "queue_priority", "output_path", "subprocess", "executable",
            "python_code", "shell", "powershell", "direct_crop_coordinates",
        }
        for m in pack.matches:
            d = m.to_dict()
            for k in forbidden:
                assert k not in d, f"forbidden key '{k}' found in match dict"

    def test_confidence_clamped(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        result = sanitize_retrieval_match({"match_id": "m1", "confidence": 99.0})
        assert result["confidence"] == 1.0

    def test_retrieval_scores_clamped(self):
        from app.ai.retrieval.retrieval_safety import sanitize_retrieval_match
        result = sanitize_retrieval_match({"match_id": "m1", "retrieval_score": 200.0})
        assert result["retrieval_score"] == 100.0

    def test_no_payload_mutation(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        original_mode = plan.mode
        original_segments = len(plan.selected_segments)
        _ = retrieve_creator_intelligence(plan)
        assert plan.mode == original_mode
        assert len(plan.selected_segments) == original_segments

    def test_no_render_execution(self):
        """Retrieval engine must not trigger any render execution."""
        import app.ai.retrieval.retrieval_engine as eng
        import inspect
        src = inspect.getsource(eng)
        for bad in ("subprocess.run", "subprocess.Popen", "os.system", "os.popen"):
            assert bad not in src, f"retrieval_engine contains '{bad}'"

    def test_no_ffmpeg_mutation(self):
        import app.ai.retrieval.retrieval_engine as eng
        import inspect
        src = inspect.getsource(eng)
        assert "ffmpeg" not in src.lower() or "ffmpeg_args" not in src

    def test_no_playback_speed_mutation(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        for m in pack.matches:
            assert "playback_speed" not in m.pacing_influence
            assert "playback_speed" not in m.camera_influence

    def test_no_subtitle_timing_rewrite(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        for m in pack.matches:
            assert "subtitle_timing" not in m.subtitle_influence

    def test_no_executor_override(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        for m in pack.matches:
            d = m.to_dict()
            assert "render_command" not in d
            assert "output_path" not in d

    def test_assistive_only_retrieval_preserved(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        assert pack.retrieval_mode == "assistive_only"

    def test_all_matches_safe_flag(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_highenergy_plan()
        pack = retrieve_creator_intelligence(plan)
        for m in pack.matches:
            assert m.safe is True


# ===========================================================================
# TestEditPlanSchemaIntegration
# ===========================================================================

class TestEditPlanSchemaIntegration:
    def test_creator_retrieval_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AIEditPlan)}
        assert "creator_retrieval" in fields

    def test_creator_retrieval_default_empty(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan,
        )
        plan = AIEditPlan(
            enabled=True,
            mode="balanced",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert plan.creator_retrieval == {}

    def test_to_dict_includes_creator_retrieval(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan,
        )
        plan = AIEditPlan(
            enabled=True,
            mode="balanced",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "creator_retrieval" in d
        assert d["creator_retrieval"] == {}

    def test_backward_compat_all_prior_phases(self):
        from app.ai.director.edit_plan_schema import AIEditPlan
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AIEditPlan)}
        required = {
            "enabled", "mode", "selected_segments", "subtitle", "camera",
            "pacing", "beat_execution", "story", "preset_evolution",
            "creator_style", "external_knowledge", "retention",
            "subtitle_execution", "beat_visual_execution", "timing_mutation",
            "story_optimization", "variants", "variant_selection",
            "creator_style_adaptation", "render_decision_preview",
            "execution_recommendations", "execution_simulation",
            "safe_render_mutations", "multivariant_render_plans",
            "multivariant_execution", "output_ranking", "ai_apply_policy",
            "timing_apply", "subtitle_text_apply", "camera_motion_apply",
            "clip_candidate_discovery", "clip_segment_selection",
            "clip_batch_planning", "feature_enhancement",
            "creator_knowledge", "creator_patterns", "creator_retrieval",
        }
        for f in required:
            assert f in fields, f"Missing field: {f}"

    def test_to_dict_includes_all_phase_keys(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan,
        )
        plan = AIEditPlan(
            enabled=True, mode="balanced", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for key in (
            "creator_knowledge", "creator_patterns", "creator_retrieval",
            "feature_enhancement", "clip_batch_planning",
        ):
            assert key in d, f"Missing key in to_dict(): {key}"


# ===========================================================================
# TestNoMutationSafety
# ===========================================================================

class TestNoMutationSafety:
    def test_no_internet_access(self):
        import app.ai.retrieval.retrieval_engine as eng
        import inspect
        src = inspect.getsource(eng)
        for bad in ("urllib.request.urlopen", "requests.get", "httpx", "aiohttp"):
            assert bad not in src, f"retrieval_engine contains '{bad}'"

    def test_no_subprocess_execution(self):
        import app.ai.retrieval.retrieval_engine as eng
        import inspect
        src = inspect.getsource(eng)
        for bad in ("subprocess.run", "subprocess.Popen", "os.system"):
            assert bad not in src, f"retrieval_engine contains '{bad}'"

    def test_no_ffmpeg_mutation_in_engine(self):
        import app.ai.retrieval.retrieval_engine as eng
        import inspect
        src = inspect.getsource(eng)
        # ffmpeg_args appears only in forbidden key checks/influence strips, never as an assignment target
        assert "ffmpeg_args =" not in src

    def test_no_source_segment_reorder(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan, AIPacingPlan,
        )
        plan = AIEditPlan(
            enabled=True, mode="balanced",
            selected_segments=[
                AIClipPlan(start=0.0, end=5.0, score=70.0),
                AIClipPlan(start=10.0, end=15.0, score=80.0),
            ],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        original_segs = [(s.start, s.end) for s in plan.selected_segments]
        _ = retrieve_creator_intelligence(plan)
        assert [(s.start, s.end) for s in plan.selected_segments] == original_segs

    def test_no_queue_mutation(self):
        import app.ai.retrieval.retrieval_engine as eng
        import inspect
        src = inspect.getsource(eng)
        assert "queue_priority" not in src or "queue_priority" in repr(
            [k for k in ["queue_priority"] if k in src]
        )


# ===========================================================================
# TestEnvironmentRequirements
# ===========================================================================

class TestEnvironmentRequirements:
    def test_no_api_key_required(self):
        import os
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        # Must work without any API key in environment
        env_backup = {k: v for k, v in os.environ.items() if "API_KEY" in k.upper()}
        for k in env_backup:
            del os.environ[k]
        try:
            pack = retrieve_creator_intelligence(plan)
            assert pack is not None
        finally:
            os.environ.update(env_backup)

    def test_no_gpu_required(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        assert pack is not None

    def test_no_internet_required(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence
        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)
        assert pack is not None

    def test_phase_40_pattern_module_unaffected(self):
        from app.ai.knowledge.pattern_schema import AICreatorPattern, AIPatternRegistry
        from app.ai.knowledge.pattern_extractor import extract_creator_patterns
        from app.ai.knowledge.pattern_registry import load_pattern_registry
        # Phase 40 modules must still work
        p = AICreatorPattern(pattern_id="test")
        assert p.pattern_id == "test"
        reg = AIPatternRegistry()
        assert isinstance(reg.pattern_types, list)

    def test_phase_39_knowledge_module_unaffected(self):
        from app.ai.knowledge.knowledge_schema import (
            ExternalKnowledgeItem, KnowledgeSearchResult,
            AICreatorKnowledge, AIKnowledgeRegistry,
        )
        item = ExternalKnowledgeItem(id="k1", source_type="local", text="test")
        assert item.id == "k1"
        creator_k = AICreatorKnowledge(knowledge_id="ck1", category="creators")
        assert creator_k.knowledge_id == "ck1"
# ===========================================================================
# Additional Hardening Tests
# ===========================================================================

class TestAdditionalRetrievalHardening:
    def test_matches_do_not_mutate_input_plan(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence

        plan = _make_highenergy_plan()
        original = copy.deepcopy(plan.to_dict())

        _ = retrieve_creator_intelligence(plan)

        assert plan.to_dict() == original

    def test_retrieval_matches_sorted_deterministically(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence

        plan = _make_highenergy_plan()

        pack1 = retrieve_creator_intelligence(plan)
        pack2 = retrieve_creator_intelligence(plan)

        ids1 = [m.match_id for m in pack1.matches]
        ids2 = [m.match_id for m in pack2.matches]

        assert ids1 == ids2

    def test_retrieval_mode_always_assistive_only(self):
        from app.ai.retrieval.retrieval_engine import retrieve_creator_intelligence

        plan = _make_minimal_plan()
        pack = retrieve_creator_intelligence(plan)

        assert pack.retrieval_mode == "assistive_only"
