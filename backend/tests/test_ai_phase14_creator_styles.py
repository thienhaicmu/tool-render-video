"""
test_ai_phase14_creator_styles.py — Phase 14: Creator Style Intelligence tests.

All tests are unit-level — no API keys, no GPU, no external models, no rendering.
Style classification is deterministic heuristic-only.
"""
from __future__ import annotations

import pytest
from typing import Optional


# ── Context builders ──────────────────────────────────────────────────────────

def _pacing(
    energy: float = 0.6,
    style: str = "fast",
    emotion: str = "urgency",
    bpm: Optional[float] = 120.0,
) -> dict:
    return {"energy_level": energy, "pacing_style": style, "emotion": emotion, "bpm": bpm}


def _story(flow: str = "hook_to_climax", arc: str = "curiosity_build", retention: float = 70.0) -> dict:
    return {"narrative_flow": flow, "dominant_arc": arc, "retention_score": retention}


def _transcript(text: str = "Stop right now and listen!", chunk_count: int = 15) -> dict:
    return {"text": text, "chunk_count": chunk_count}


# ── Import modules ────────────────────────────────────────────────────────────

from app.ai.styles.style_schema import (
    CreatorStyleProfile, StyleClassification, StyleRecommendation,
)
from app.ai.styles.style_profiles import (
    get_profile, get_all_profiles, STYLE_IDS, STYLE_DURATION_HINTS,
)
from app.ai.styles.style_classifier import classify_creator_style
from app.ai.styles.style_recommender import recommend_style_adjustments


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestStyleSchema:
    def test_creator_style_profile_fields(self):
        p = CreatorStyleProfile(
            style_id="test", display_name="Test", pacing_style="fast",
            subtitle_style="bold", camera_behavior="static", hook_style="urgency",
            story_arc_style="linear_build", energy_level="high",
        )
        assert p.style_id == "test"
        assert p.notes == []

    def test_style_classification_defaults(self):
        sc = StyleClassification()
        assert sc.available is True
        assert sc.dominant_style == "unknown"
        assert sc.confidence == 0.0
        assert sc.secondary_styles == []
        assert sc.matched_traits == []
        assert sc.warnings == []

    def test_style_recommendation_defaults(self):
        sr = StyleRecommendation()
        assert sr.recommended_style is None
        assert sr.confidence == 0.0
        assert sr.suggested_adjustments == {}
        assert sr.reasons == []
        assert sr.warnings == []

    def test_style_classification_to_dict_has_all_keys(self):
        sc = StyleClassification(dominant_style="podcast_viral", confidence=75.0)
        d = sc.to_dict()
        for key in ("available", "dominant_style", "confidence",
                    "secondary_styles", "matched_traits", "warnings"):
            assert key in d

    def test_style_recommendation_to_dict_has_all_keys(self):
        sr = StyleRecommendation(recommended_style="podcast_viral", confidence=70.0)
        d = sr.to_dict()
        for key in ("recommended_style", "confidence", "suggested_adjustments",
                    "reasons", "warnings"):
            assert key in d

    def test_classification_to_dict_caps_traits_at_6(self):
        sc = StyleClassification(matched_traits=[f"trait_{i}" for i in range(10)])
        d = sc.to_dict()
        assert len(d["matched_traits"]) <= 6

    def test_classification_to_dict_caps_secondary_at_3(self):
        sc = StyleClassification(secondary_styles=[f"style_{i}" for i in range(10)])
        d = sc.to_dict()
        assert len(d["secondary_styles"]) <= 3

    def test_recommendation_to_dict_caps_reasons_at_5(self):
        sr = StyleRecommendation(reasons=[f"reason_{i}" for i in range(10)])
        d = sr.to_dict()
        assert len(d["reasons"]) <= 5


# ── Style profiles tests ──────────────────────────────────────────────────────

class TestStyleProfiles:
    def test_all_10_archetypes_exist(self):
        expected = {
            "podcast_viral", "high_energy_reaction", "storytelling_cinematic",
            "documentary_clean", "educational_focus", "anime_edit",
            "gameplay_highlight", "motivation_short", "interview_clip", "calm_minimal",
        }
        assert expected == set(STYLE_IDS)

    def test_get_profile_returns_correct_type(self):
        p = get_profile("podcast_viral")
        assert isinstance(p, CreatorStyleProfile)

    def test_get_profile_unknown_returns_none(self):
        assert get_profile("nonexistent_style") is None

    def test_all_profiles_have_required_fields(self):
        for sid, profile in get_all_profiles().items():
            assert profile.style_id == sid
            assert isinstance(profile.display_name, str) and profile.display_name
            assert isinstance(profile.pacing_style, str) and profile.pacing_style
            assert isinstance(profile.subtitle_style, str) and profile.subtitle_style
            assert isinstance(profile.camera_behavior, str) and profile.camera_behavior
            assert isinstance(profile.energy_level, str) and profile.energy_level

    def test_no_copyrighted_creator_names_in_display_names(self):
        """Display names must not reference real creator names."""
        copyrighted_names = {"pewdiepie", "mr beast", "mrbeast", "mkbhd", "kurzgesagt"}
        for profile in get_all_profiles().values():
            assert profile.display_name.lower() not in copyrighted_names

    def test_no_copyrighted_names_in_notes(self):
        copyrighted_names = {"pewdiepie", "mr beast", "mrbeast", "mkbhd", "kurzgesagt"}
        for profile in get_all_profiles().values():
            for note in profile.notes:
                for name in copyrighted_names:
                    assert name not in note.lower()

    def test_style_duration_hints_all_positive(self):
        for style_id, hint in STYLE_DURATION_HINTS.items():
            assert hint > 0, f"Duration hint for {style_id} is not positive"

    def test_get_all_profiles_returns_copy(self):
        profiles1 = get_all_profiles()
        profiles2 = get_all_profiles()
        assert profiles1 is not profiles2

    def test_profile_to_dict_has_required_keys(self):
        p = get_profile("podcast_viral")
        d = p.to_dict()
        for key in ("style_id", "display_name", "pacing_style", "subtitle_style",
                    "camera_behavior", "hook_style", "story_arc_style", "energy_level"):
            assert key in d


# ── Classifier safety ─────────────────────────────────────────────────────────

class TestClassifierSafety:
    def test_never_raises_on_no_args(self):
        result = classify_creator_style()
        assert isinstance(result, StyleClassification)

    def test_never_raises_on_none_args(self):
        result = classify_creator_style(
            transcript_context=None,
            pacing_context=None,
            emotion_context=None,
            story_context=None,
        )
        assert isinstance(result, StyleClassification)

    def test_never_raises_on_garbage_pacing(self):
        result = classify_creator_style(pacing_context="bad_value")
        assert isinstance(result, StyleClassification)

    def test_never_raises_on_garbage_story(self):
        result = classify_creator_style(story_context=42)
        assert isinstance(result, StyleClassification)

    def test_never_raises_on_empty_dicts(self):
        result = classify_creator_style(
            transcript_context={}, pacing_context={},
            emotion_context={}, story_context={},
        )
        assert isinstance(result, StyleClassification)

    def test_dominant_style_is_string(self):
        result = classify_creator_style(pacing_context=_pacing())
        assert isinstance(result.dominant_style, str)

    def test_dominant_style_is_valid_style_id_or_unknown(self):
        result = classify_creator_style(pacing_context=_pacing())
        assert result.dominant_style in STYLE_IDS or result.dominant_style == "unknown"

    def test_confidence_in_valid_range(self):
        result = classify_creator_style(pacing_context=_pacing())
        assert 0.0 <= result.confidence <= 100.0

    def test_available_true_with_signals(self):
        result = classify_creator_style(pacing_context=_pacing(energy=0.8, style="fast"))
        assert result.available is True


# ── High urgency → podcast / high-energy styles ───────────────────────────────

class TestHighUrgencyClassification:
    def test_high_energy_fast_pacing_maps_toward_podcast_or_high_energy(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.85, style="fast", emotion="urgency", bpm=130.0),
        )
        assert result.dominant_style in (
            "podcast_viral", "high_energy_reaction", "anime_edit", "gameplay_highlight"
        ), f"Expected high-energy style, got: {result.dominant_style}"

    def test_urgency_emotion_favors_podcast_viral(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.70, style="fast", emotion="urgency", bpm=115.0),
            story_context=_story(flow="hook_to_climax", arc="curiosity_build"),
        )
        high_energy_styles = {
            "podcast_viral", "high_energy_reaction", "motivation_short",
            "anime_edit", "gameplay_highlight",
        }
        assert result.dominant_style in high_energy_styles

    def test_very_high_energy_bpm_maps_toward_reaction_or_anime(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.92, style="fast", emotion="excitement", bpm=155.0),
        )
        assert result.dominant_style in ("high_energy_reaction", "anime_edit", "podcast_viral")

    def test_matched_traits_nonempty_for_strong_signals(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.80, style="fast", emotion="urgency"),
        )
        assert len(result.matched_traits) > 0


# ── Calm pacing → documentary / calm styles ───────────────────────────────────

class TestCalmPacingClassification:
    def test_calm_pacing_maps_toward_documentary_or_calm(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.20, style="slow", emotion="neutral", bpm=None),
        )
        calm_styles = {"documentary_clean", "calm_minimal", "interview_clip"}
        assert result.dominant_style in calm_styles, (
            f"Expected calm style, got: {result.dominant_style}"
        )

    def test_very_low_energy_maps_to_calm_minimal(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.10, style="slow", emotion="neutral", bpm=None),
            story_context=_story(flow="flat", arc="informational", retention=40.0),
        )
        assert result.dominant_style in ("calm_minimal", "documentary_clean", "interview_clip")

    def test_neutral_emotion_low_energy_not_podcast(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.15, style="slow", emotion="neutral", bpm=None),
        )
        assert result.dominant_style not in ("podcast_viral", "high_energy_reaction", "anime_edit")

    def test_calm_matched_traits_reflect_low_energy(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.15, style="slow", emotion="neutral", bpm=None),
        )
        all_traits = " ".join(result.matched_traits).lower()
        assert any(word in all_traits for word in ("energy", "pacing", "calm", "neutral", "low"))


# ── Storytelling arc → cinematic style ────────────────────────────────────────

class TestStorytellingCinematicClassification:
    def test_narrative_arc_maps_to_cinematic(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.45, style="medium", emotion="curiosity", bpm=None),
            story_context=_story(flow="hook_to_payoff", arc="curiosity_build"),
        )
        cinematic_styles = {"storytelling_cinematic", "documentary_clean", "educational_focus"}
        assert result.dominant_style in cinematic_styles

    def test_setup_payoff_arc_favors_cinematic(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.40, style="slow_build", emotion="curiosity", bpm=None),
            story_context=_story(flow="hook_to_payoff", arc="setup_payoff"),
        )
        assert result.dominant_style in ("storytelling_cinematic", "documentary_clean", "educational_focus")

    def test_curiosity_emotion_structured_flow_not_high_energy(self):
        result = classify_creator_style(
            pacing_context=_pacing(energy=0.45, style="medium", emotion="curiosity", bpm=None),
            story_context=_story(flow="linear_build", arc="curiosity_build"),
        )
        assert result.dominant_style not in ("anime_edit", "high_energy_reaction")


# ── Recommender safety ────────────────────────────────────────────────────────

class TestRecommenderSafety:
    def test_never_raises_on_none_classification(self):
        result = recommend_style_adjustments(None)
        assert isinstance(result, StyleRecommendation)

    def test_never_raises_on_unavailable_classification(self):
        sc = StyleClassification(available=False)
        result = recommend_style_adjustments(sc)
        assert isinstance(result, StyleRecommendation)
        assert result.confidence == 0.0

    def test_never_raises_on_unknown_style(self):
        sc = StyleClassification(available=True, dominant_style="unknown", confidence=0.0)
        result = recommend_style_adjustments(sc)
        assert isinstance(result, StyleRecommendation)

    def test_does_not_suggest_playback_speed(self):
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=75.0)
        result = recommend_style_adjustments(sc)
        assert "playback_speed" not in result.suggested_adjustments

    def test_does_not_suggest_timing_changes(self):
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=75.0)
        result = recommend_style_adjustments(sc)
        assert "timing" not in result.suggested_adjustments
        assert "segment_start" not in result.suggested_adjustments
        assert "segment_end" not in result.suggested_adjustments

    def test_does_not_suggest_ffmpeg_changes(self):
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=75.0)
        result = recommend_style_adjustments(sc)
        assert "ffmpeg" not in result.suggested_adjustments
        assert "codec" not in result.suggested_adjustments

    def test_reasons_capped_at_5(self):
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=75.0)
        result = recommend_style_adjustments(sc)
        assert len(result.reasons) <= 5

    def test_confidence_in_valid_range(self):
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=75.0)
        result = recommend_style_adjustments(sc)
        assert 0.0 <= result.confidence <= 100.0

    def test_only_safe_adjustment_fields_returned(self):
        sc = StyleClassification(available=True, dominant_style="anime_edit", confidence=80.0)
        result = recommend_style_adjustments(sc)
        allowed = {"subtitle_style", "pacing_style", "camera_behavior",
                   "hook_style", "target_duration_hint"}
        for key in result.suggested_adjustments:
            assert key in allowed, f"Unsafe key: {key}"

    def test_no_copyrighted_creator_in_reasons(self):
        copyrighted = {"pewdiepie", "mr beast", "mrbeast", "mkbhd"}
        for style_id in STYLE_IDS:
            sc = StyleClassification(available=True, dominant_style=style_id, confidence=70.0)
            result = recommend_style_adjustments(sc)
            for reason in result.reasons:
                for name in copyrighted:
                    assert name not in reason.lower()

    def test_advisory_only_no_mutation(self):
        """recommend_style_adjustments returns a new object; it does not mutate anything."""
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=75.0)
        original_confidence = sc.confidence
        recommend_style_adjustments(sc)
        assert sc.confidence == original_confidence  # classification unchanged


# ── Recommender produces useful suggestions ────────────────────────────────────

class TestRecommenderSuggestions:
    def test_returns_style_recommendation(self):
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=78.0)
        result = recommend_style_adjustments(sc)
        assert isinstance(result, StyleRecommendation)

    def test_recommended_style_matches_dominant(self):
        sc = StyleClassification(available=True, dominant_style="documentary_clean", confidence=65.0)
        result = recommend_style_adjustments(sc)
        assert result.recommended_style == "documentary_clean"

    def test_adjustments_are_nonempty_for_known_style(self):
        sc = StyleClassification(available=True, dominant_style="motivation_short", confidence=70.0)
        result = recommend_style_adjustments(sc)
        assert len(result.suggested_adjustments) > 0

    def test_reasons_nonempty_for_known_style(self):
        sc = StyleClassification(available=True, dominant_style="anime_edit", confidence=80.0)
        result = recommend_style_adjustments(sc)
        assert len(result.reasons) > 0

    def test_target_duration_hint_present_for_known_style(self):
        sc = StyleClassification(available=True, dominant_style="motivation_short", confidence=70.0)
        result = recommend_style_adjustments(sc)
        assert "target_duration_hint" in result.suggested_adjustments
        assert result.suggested_adjustments["target_duration_hint"] == 30.0


# ── AIEditPlan creator_style field ────────────────────────────────────────────

class TestEditPlanCreatorStyleField:
    def test_ai_edit_plan_has_creator_style_field(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "creator_style")
        assert isinstance(plan.creator_style, dict)

    def test_creator_style_defaults_to_empty(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert plan.creator_style == {}

    def test_ai_edit_plan_to_dict_includes_creator_style(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.creator_style = {"dominant_style": "podcast_viral", "confidence": 75.0}
        d = plan.to_dict()
        assert "creator_style" in d
        assert d["creator_style"]["dominant_style"] == "podcast_viral"


# ── AI Director integration ───────────────────────────────────────────────────

class TestAIDirectorStyleIntegration:
    def _make_plan(self, mode="viral_tiktok"):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode=mode, selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        return plan

    def test_attach_creator_style_sets_creator_style_dict(self):
        from app.ai.director.ai_director import _attach_creator_style
        plan = self._make_plan()
        _attach_creator_style(plan, [], _pacing(), "test_job")
        assert isinstance(plan.creator_style, dict)

    def test_attach_creator_style_never_raises_on_empty_chunks(self):
        from app.ai.director.ai_director import _attach_creator_style
        plan = self._make_plan()
        _attach_creator_style(plan, [], {}, "test_job")
        assert isinstance(plan.creator_style, dict)

    def test_attach_creator_style_never_raises_on_none_pacing(self):
        from app.ai.director.ai_director import _attach_creator_style
        plan = self._make_plan()
        _attach_creator_style(plan, [], None, "test_job")
        assert isinstance(plan.creator_style, dict)

    def test_creator_style_includes_recommendation(self):
        from app.ai.director.ai_director import _attach_creator_style
        plan = self._make_plan()
        pacing = _pacing(energy=0.8, style="fast", emotion="urgency")
        _attach_creator_style(plan, [], pacing, "test_job")
        assert "recommendation" in plan.creator_style

    def test_explainability_append_never_raises(self):
        from app.ai.director.ai_director import _append_style_explainability
        plan = self._make_plan()
        plan.explainability = {"summary": {"summary_lines": ["Existing line"]}}
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=75.0)
        _append_style_explainability(plan, sc)
        lines = plan.explainability["summary"]["summary_lines"]
        assert "Existing line" in lines

    def test_explainability_line_added_for_known_style(self):
        from app.ai.director.ai_director import _append_style_explainability
        plan = self._make_plan()
        plan.explainability = {"summary": {"summary_lines": []}}
        sc = StyleClassification(available=True, dominant_style="podcast_viral", confidence=75.0)
        _append_style_explainability(plan, sc)
        lines = plan.explainability["summary"]["summary_lines"]
        assert len(lines) > 0

    def test_explainability_no_duplicate_lines(self):
        from app.ai.director.ai_director import _append_style_explainability
        plan = self._make_plan()
        plan.explainability = {"summary": {"summary_lines": []}}
        sc = StyleClassification(available=True, dominant_style="storytelling_cinematic", confidence=70.0)
        _append_style_explainability(plan, sc)
        _append_style_explainability(plan, sc)
        lines = plan.explainability["summary"]["summary_lines"]
        assert len(lines) == len(set(lines))

    def test_explainability_never_raises_on_missing_explainability(self):
        from app.ai.director.ai_director import _append_style_explainability
        plan = self._make_plan()
        sc = StyleClassification(available=True, dominant_style="anime_edit", confidence=80.0)
        _append_style_explainability(plan, sc)


# ── Result JSON compactness ───────────────────────────────────────────────────

class TestResultJsonCompactness:
    def test_classification_to_dict_is_compact(self):
        sc = StyleClassification(
            available=True,
            dominant_style="podcast_viral",
            confidence=78.0,
            secondary_styles=["motivation_short", "gameplay_highlight"],
            matched_traits=["high energy", "fast pacing", "urgency signal"],
        )
        d = sc.to_dict()
        assert len(d["matched_traits"]) <= 6
        assert len(d["secondary_styles"]) <= 3

    def test_recommendation_to_dict_is_compact(self):
        sc = StyleClassification(available=True, dominant_style="anime_edit", confidence=80.0)
        rec = recommend_style_adjustments(sc)
        d = rec.to_dict()
        assert len(d["reasons"]) <= 5

    def test_full_creator_style_dict_has_recommendation_key(self):
        from app.ai.director.ai_director import _attach_creator_style
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        _attach_creator_style(plan, [], _pacing(), "job")
        assert "recommendation" in plan.creator_style


# ── No external dependencies ──────────────────────────────────────────────────

class TestNoExternalDependencies:
    def test_no_api_key_required(self):
        import os
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result = classify_creator_style(pacing_context=_pacing())
            assert isinstance(result, StyleClassification)
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved

    def test_no_gpu_required(self):
        result = classify_creator_style(pacing_context=_pacing())
        assert isinstance(result, StyleClassification)

    def test_no_external_models_required(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "sentence_transformers", None)
        monkeypatch.setitem(sys.modules, "torch", None)
        result = classify_creator_style(pacing_context=_pacing())
        assert isinstance(result, StyleClassification)

    def test_no_real_rendering_required(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = classify_creator_style(pacing_context=_pacing())
        assert isinstance(result, StyleClassification)

    def test_style_modules_import_safely(self):
        from app.ai.styles import style_schema, style_profiles, style_classifier, style_recommender

    def test_recommender_no_api_key_required(self):
        import os
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            sc = StyleClassification(available=True, dominant_style="calm_minimal", confidence=60.0)
            result = recommend_style_adjustments(sc)
            assert isinstance(result, StyleRecommendation)
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved

    def test_no_network_calls_in_classifier(self, monkeypatch):
        """Classifier must not attempt any socket/network operations."""
        import socket
        original = socket.socket
        called = []

        class NoSocket:
            def __init__(self, *a, **kw):
                called.append(True)

        monkeypatch.setattr(socket, "socket", NoSocket)
        classify_creator_style(pacing_context=_pacing())
        assert not called, "Classifier attempted a network connection"
