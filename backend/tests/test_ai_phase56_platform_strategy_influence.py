"""
test_ai_phase56_platform_strategy_influence.py — Phase 56 Platform-Aware Strategy Influence tests.

Covers:
  - Platform strategy influence context creation (full plan)
  - Missing/unavailable platform_render_strategy → fallback
  - Subtitle bias support (values, confidence_delta, reasoning)
  - Camera bias support (values, confidence_delta, reasoning)
  - Ranking bias support (values, confidence_delta, reasoning)
  - Confidence delta bounds (per-domain ≤ 0.05, total ≤ 0.10)
  - Creator-vs-platform conflict behavior (trust creator already resolved in 55E)
  - Safety gate preservation (confidence_delta is metadata only)
  - No direct execution flags in output
  - Deterministic output (same inputs → same output)
  - No crash on empty/None input
  - No unsafe/internal fields exposed
  - Enrich subtitle/camera/ranking reasoning (additive only)
  - Edit plan schema: field presence + to_dict() backward compat
  - Duck-typed object (AIEditPlan-like) acceptance
"""
from __future__ import annotations

from typing import Any

import pytest

from app.ai.knowledge.platform_strategy_influence_context import (
    build_platform_strategy_influence,
    enrich_subtitle_influence_reasoning,
    enrich_camera_influence_reasoning,
    enrich_ranking_influence_reasoning,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _prs(
    available: bool = True,
    platform: str = "tiktok",
    creator_type: str = "podcast",
    confidence: float = 0.83,
    subtitle_strategy: dict = None,
    camera_strategy: dict = None,
    hook_strategy: dict = None,
    ranking_strategy: dict = None,
) -> dict:
    """Build a platform_render_strategy dict."""
    return {
        "available": available,
        "platform": platform,
        "creator_type": creator_type,
        "confidence": confidence,
        "strategy": {
            "subtitle": subtitle_strategy or {
                "style_bias": "clean_pro",
                "density_bias": "compact",
                "keyword_emphasis": "selective",
                "readability_priority": "high",
            },
            "camera": camera_strategy or {
                "motion_energy": "low_medium",
                "stability_priority": "high",
                "crop_aggressiveness": "low",
                "jitter_sensitivity": "high",
            },
            "hook": hook_strategy or {
                "first_3s_priority": "high",
                "retention_priority": "high",
                "hook_energy": "moderate",
                "curiosity_style": "soft_direct",
            },
            "ranking": ranking_strategy or {
                "priority": "retention_creator_fit",
            },
        },
        "reasoning": [],
    }


def _plan(prs_dict: dict, extra: dict = None) -> dict:
    """Wrap a platform_render_strategy into a minimal plan dict."""
    d = {"platform_render_strategy": prs_dict}
    if extra:
        d.update(extra)
    return d


def _tiktok_podcast_plan() -> dict:
    return _plan(_prs())


def _youtube_educational_plan() -> dict:
    return _plan(_prs(
        platform="youtube_shorts",
        creator_type="educational",
        confidence=0.78,
        subtitle_strategy={
            "style_bias": "clean_pro",
            "density_bias": "balanced",
            "keyword_emphasis": "selective",
            "readability_priority": "high",
        },
        camera_strategy={
            "motion_energy": "low_medium",
            "stability_priority": "high",
            "crop_aggressiveness": "low",
            "jitter_sensitivity": "high",
        },
        hook_strategy={
            "first_3s_priority": "medium",
            "retention_priority": "high",
            "hook_energy": "moderate",
            "curiosity_style": "soft_direct",
        },
        ranking_strategy={"priority": "retention_creator_fit"},
    ))


def _tiktok_viral_plan() -> dict:
    return _plan(_prs(
        platform="tiktok",
        creator_type="viral_short_form",
        confidence=0.85,
        subtitle_strategy={
            "style_bias": "viral_bold",
            "density_bias": "compact",
            "keyword_emphasis": "moderate",
            "readability_priority": "high",
        },
        camera_strategy={
            "motion_energy": "medium_high",
            "stability_priority": "medium",
            "crop_aggressiveness": "medium",
            "jitter_sensitivity": "high",
        },
        hook_strategy={
            "first_3s_priority": "high",
            "retention_priority": "high",
            "hook_energy": "high",
            "curiosity_style": "direct",
        },
        ranking_strategy={"priority": "retention"},
    ))


# ---------------------------------------------------------------------------
# Fallback tests
# ---------------------------------------------------------------------------

class TestBuildFallback:

    def test_empty_dict_returns_fallback(self):
        result = build_platform_strategy_influence({})
        psi = result["platform_strategy_influence"]
        assert psi["available"] is False
        assert psi["confidence"] == 0.0

    def test_none_returns_fallback(self):
        result = build_platform_strategy_influence(None)
        psi = result["platform_strategy_influence"]
        assert psi["available"] is False

    def test_unavailable_prs_returns_fallback(self):
        plan = _plan(_prs(available=False))
        result = build_platform_strategy_influence(plan)
        psi = result["platform_strategy_influence"]
        assert psi["available"] is False

    def test_missing_prs_returns_fallback(self):
        result = build_platform_strategy_influence({"other_field": "x"})
        psi = result["platform_strategy_influence"]
        assert psi["available"] is False

    def test_empty_strategy_dict_returns_fallback(self):
        plan = {"platform_render_strategy": {"available": True, "platform": "tiktok", "strategy": {}}}
        result = build_platform_strategy_influence(plan)
        psi = result["platform_strategy_influence"]
        assert psi["available"] is False

    def test_all_unknown_values_returns_fallback(self):
        plan = _plan(_prs(
            subtitle_strategy={"style_bias": "unknown", "density_bias": "unknown", "keyword_emphasis": "unknown"},
            camera_strategy={"motion_energy": "unknown", "stability_priority": "unknown", "crop_aggressiveness": "unknown"},
            hook_strategy={"first_3s_priority": "unknown", "retention_priority": "unknown"},
            ranking_strategy={"priority": "unknown"},
        ))
        result = build_platform_strategy_influence(plan)
        psi = result["platform_strategy_influence"]
        # ranking with "balanced" also falls back, "unknown" definitely does
        assert psi["available"] is False

    def test_no_crash_on_malformed_prs(self):
        plan = {"platform_render_strategy": {"available": True, "strategy": None}}
        result = build_platform_strategy_influence(plan)
        assert "platform_strategy_influence" in result

    def test_fallback_has_required_keys(self):
        result = build_platform_strategy_influence({})
        psi = result["platform_strategy_influence"]
        assert "available" in psi
        assert "confidence" in psi


# ---------------------------------------------------------------------------
# Full strategy influence structure
# ---------------------------------------------------------------------------

class TestFullStructure:

    def test_available_is_true_for_tiktok_podcast(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        assert result["platform_strategy_influence"]["available"] is True

    def test_top_level_keys(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        psi = result["platform_strategy_influence"]
        assert "available" in psi
        assert "platform" in psi
        assert "creator_type" in psi
        assert "confidence" in psi
        assert "platform_strategy_influence_reasoning" in psi

    def test_platform_matches_input(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        assert result["platform_strategy_influence"]["platform"] == "tiktok"

    def test_creator_type_matches_input(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        assert result["platform_strategy_influence"]["creator_type"] == "podcast"

    def test_three_domains_supported(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        psi = result["platform_strategy_influence"]
        assert "subtitle" in psi
        assert "camera" in psi
        assert "ranking" in psi

    def test_subtitle_domain_shape(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        sub = result["platform_strategy_influence"]["subtitle"]
        assert sub["supported"] is True
        assert "bias" in sub
        assert "confidence_delta" in sub
        assert "reasoning" in sub

    def test_camera_domain_shape(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        cam = result["platform_strategy_influence"]["camera"]
        assert cam["supported"] is True
        assert "bias" in cam
        assert "confidence_delta" in cam
        assert "reasoning" in cam

    def test_ranking_domain_shape(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        rank = result["platform_strategy_influence"]["ranking"]
        assert rank["supported"] is True
        assert "bias" in rank
        assert "confidence_delta" in rank
        assert "reasoning" in rank

    def test_reasoning_is_list(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        psi = result["platform_strategy_influence"]
        assert isinstance(psi["platform_strategy_influence_reasoning"], list)
        assert len(psi["platform_strategy_influence_reasoning"]) > 0


# ---------------------------------------------------------------------------
# Subtitle bias support
# ---------------------------------------------------------------------------

class TestSubtitleBiasSupport:

    def test_subtitle_bias_style_matches_strategy(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["subtitle"]["bias"]
        assert bias["style"] == "clean_pro"

    def test_subtitle_bias_density_matches_strategy(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["subtitle"]["bias"]
        assert bias["density"] == "compact"

    def test_subtitle_bias_keyword_emphasis_included_when_non_none(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["subtitle"]["bias"]
        assert bias["keyword_emphasis"] == "selective"

    def test_subtitle_bias_keyword_emphasis_excluded_when_none(self):
        plan = _plan(_prs(subtitle_strategy={
            "style_bias": "clean_pro",
            "density_bias": "compact",
            "keyword_emphasis": "none",
        }))
        result = build_platform_strategy_influence(plan)
        bias = result["platform_strategy_influence"]["subtitle"]["bias"]
        assert "keyword_emphasis" not in bias

    def test_subtitle_bias_no_style_when_unknown(self):
        plan = _plan(_prs(subtitle_strategy={
            "style_bias": "unknown",
            "density_bias": "compact",
            "keyword_emphasis": "selective",
        }))
        result = build_platform_strategy_influence(plan)
        bias = result["platform_strategy_influence"]["subtitle"]["bias"]
        assert "style" not in bias
        assert "density" in bias

    def test_subtitle_reasoning_is_list_with_content(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        reasoning = result["platform_strategy_influence"]["subtitle"]["reasoning"]
        assert isinstance(reasoning, list)
        assert len(reasoning) > 0

    def test_subtitle_reasoning_no_internal_paths(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        text = " ".join(result["platform_strategy_influence"]["subtitle"]["reasoning"])
        assert ".py" not in text
        assert "traceback" not in text.lower()

    def test_viral_bold_subtitle_style_surfaced(self):
        result = build_platform_strategy_influence(_tiktok_viral_plan())
        bias = result["platform_strategy_influence"]["subtitle"]["bias"]
        assert bias["style"] == "viral_bold"


# ---------------------------------------------------------------------------
# Camera bias support
# ---------------------------------------------------------------------------

class TestCameraBiasSupport:

    def test_camera_bias_motion_energy(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["camera"]["bias"]
        assert bias["motion_energy"] == "low_medium"

    def test_camera_bias_stability_priority(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["camera"]["bias"]
        assert bias["stability_priority"] == "high"

    def test_camera_bias_crop_aggressiveness(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["camera"]["bias"]
        assert bias["crop_aggressiveness"] == "low"

    def test_camera_reasoning_mentions_stable_framing_for_podcast(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        text = " ".join(result["platform_strategy_influence"]["camera"]["reasoning"]).lower()
        assert "stable" in text or "framing" in text or "stability" in text

    def test_camera_bias_unknown_values_excluded(self):
        plan = _plan(_prs(camera_strategy={
            "motion_energy": "unknown",
            "stability_priority": "high",
            "crop_aggressiveness": "unknown",
        }))
        result = build_platform_strategy_influence(plan)
        bias = result["platform_strategy_influence"]["camera"]["bias"]
        assert "motion_energy" not in bias
        assert "stability_priority" in bias
        assert "crop_aggressiveness" not in bias

    def test_viral_camera_bias_high_motion(self):
        result = build_platform_strategy_influence(_tiktok_viral_plan())
        bias = result["platform_strategy_influence"]["camera"]["bias"]
        assert bias["motion_energy"] == "medium_high"


# ---------------------------------------------------------------------------
# Ranking bias support
# ---------------------------------------------------------------------------

class TestRankingBiasSupport:

    def test_ranking_bias_priority_for_tiktok_podcast(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["ranking"]["bias"]
        assert bias["priority"] == "retention_creator_fit"

    def test_ranking_reasoning_mentions_retention_creator_fit(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        text = " ".join(result["platform_strategy_influence"]["ranking"]["reasoning"]).lower()
        assert "retention" in text or "creator" in text

    def test_ranking_bias_for_viral_tiktok(self):
        result = build_platform_strategy_influence(_tiktok_viral_plan())
        bias = result["platform_strategy_influence"]["ranking"]["bias"]
        assert bias["priority"] == "retention"

    def test_ranking_bias_for_youtube_educational(self):
        result = build_platform_strategy_influence(_youtube_educational_plan())
        bias = result["platform_strategy_influence"]["ranking"]["bias"]
        assert bias["priority"] == "retention_creator_fit"

    def test_ranking_not_supported_when_priority_balanced(self):
        plan = _plan(_prs(
            ranking_strategy={"priority": "balanced"},
            hook_strategy={"first_3s_priority": "unknown", "retention_priority": "unknown"},
        ))
        result = build_platform_strategy_influence(plan)
        psi = result["platform_strategy_influence"]
        # "balanced" ranking + unknown hook → ranking domain not supported
        ranking = psi.get("ranking") or {}
        assert not ranking.get("supported", False)


# ---------------------------------------------------------------------------
# Confidence delta bounds
# ---------------------------------------------------------------------------

class TestConfidenceDeltaBounds:

    def test_subtitle_delta_within_max(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        delta = result["platform_strategy_influence"]["subtitle"]["confidence_delta"]
        assert 0.0 <= delta <= 0.05

    def test_camera_delta_within_max(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        delta = result["platform_strategy_influence"]["camera"]["confidence_delta"]
        assert 0.0 <= delta <= 0.05

    def test_ranking_delta_within_max(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        delta = result["platform_strategy_influence"]["ranking"]["confidence_delta"]
        assert 0.0 <= delta <= 0.05

    def test_total_delta_does_not_exceed_max(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        psi = result["platform_strategy_influence"]
        total = 0.0
        for domain in ("subtitle", "camera", "ranking"):
            d = psi.get(domain) or {}
            if d.get("supported"):
                total += float(d.get("confidence_delta") or 0.0)
        assert total <= 0.10 + 1e-9  # float tolerance

    def test_confidence_clamped_0_to_1(self):
        # Use prs_confidence > 1.0 to verify clamping
        plan = _plan(_prs(confidence=1.5))
        result = build_platform_strategy_influence(plan)
        assert result["platform_strategy_influence"]["confidence"] <= 1.0

    def test_confidence_is_from_prs(self):
        plan = _plan(_prs(confidence=0.82))
        result = build_platform_strategy_influence(plan)
        conf = result["platform_strategy_influence"]["confidence"]
        assert abs(conf - 0.82) < 0.001


# ---------------------------------------------------------------------------
# Creator-vs-platform conflict (trust creator safety already in 55E)
# ---------------------------------------------------------------------------

class TestConflictBehavior:

    def test_podcast_creator_gets_clean_pro_not_viral_bold(self):
        """Trust creator style wins — 55E already resolved this, 56 surfaces it faithfully."""
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["subtitle"]["bias"]
        assert bias.get("style") == "clean_pro"

    def test_podcast_creator_camera_motion_is_low_medium(self):
        """Trust creator caps high motion energy — surfaces as low_medium from 55E strategy."""
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["camera"]["bias"]
        assert bias.get("motion_energy") == "low_medium"

    def test_podcast_creator_camera_stability_is_high(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["camera"]["bias"]
        assert bias.get("stability_priority") == "high"

    def test_podcast_creator_crop_aggressiveness_is_low(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["camera"]["bias"]
        assert bias.get("crop_aggressiveness") == "low"

    def test_podcast_creator_ranking_is_retention_creator_fit(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        bias = result["platform_strategy_influence"]["ranking"]["bias"]
        assert bias.get("priority") == "retention_creator_fit"

    def test_viral_creator_ranking_is_retention(self):
        result = build_platform_strategy_influence(_tiktok_viral_plan())
        bias = result["platform_strategy_influence"]["ranking"]["bias"]
        assert bias.get("priority") == "retention"


# ---------------------------------------------------------------------------
# Safety gate preservation
# ---------------------------------------------------------------------------

class TestSafetyGatePreservation:

    def test_confidence_delta_is_metadata_not_gate_input(self):
        """Verify confidence_delta is present as metadata field only, not a gate bypass."""
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        psi = result["platform_strategy_influence"]
        # No "gate" field should exist — this module doesn't touch the safety gate
        assert "gate" not in psi
        assert "gate_passed" not in psi

    def test_no_safety_gate_fields_in_output(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        psi = result["platform_strategy_influence"]
        assert "gate" not in psi
        assert "tier" not in psi
        assert "safety_passed" not in psi

    def test_output_contains_no_execution_commands(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        all_keys = _collect_all_keys(result)
        assert not (all_keys & _FORBIDDEN_KEYS)

    def test_no_executor_override(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        all_keys = _collect_all_keys(result)
        assert "executor_override" not in all_keys

    def test_no_direct_execution_flag(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        all_keys = _collect_all_keys(result)
        assert "direct_execution" not in all_keys


_FORBIDDEN_KEYS = frozenset({
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
    "crop_coordinates", "direct_execution", "executor_override",
    "output_path", "queue_priority",
})


def _collect_all_keys(obj: Any) -> set:
    keys: set = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _collect_all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _collect_all_keys(item)
    return keys


# ---------------------------------------------------------------------------
# No unsafe/internal fields exposed
# ---------------------------------------------------------------------------

class TestNoInternalLeakage:

    def test_no_py_file_paths_in_reasoning(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        text = str(result)
        assert ".py" not in text

    def test_no_traceback_in_reasoning(self):
        result = build_platform_strategy_influence(_tiktok_podcast_plan())
        text = str(result).lower()
        assert "traceback" not in text
        assert "exception" not in text

    def test_no_forbidden_keys_in_full_output(self):
        for plan_fn in [_tiktok_podcast_plan, _youtube_educational_plan, _tiktok_viral_plan]:
            result = build_platform_strategy_influence(plan_fn())
            forbidden = _collect_all_keys(result) & _FORBIDDEN_KEYS
            assert not forbidden, f"Forbidden keys found for {plan_fn.__name__}: {forbidden}"


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

class TestDeterministicOutput:

    def test_same_plan_same_output(self):
        plan = _tiktok_podcast_plan()
        r1 = build_platform_strategy_influence(plan)
        r2 = build_platform_strategy_influence(plan)
        assert r1 == r2

    def test_youtube_educational_deterministic(self):
        plan = _youtube_educational_plan()
        r1 = build_platform_strategy_influence(plan)
        r2 = build_platform_strategy_influence(plan)
        assert r1 == r2

    def test_confidence_same_on_repeated_calls(self):
        plan = _tiktok_podcast_plan()
        c1 = build_platform_strategy_influence(plan)["platform_strategy_influence"]["confidence"]
        c2 = build_platform_strategy_influence(plan)["platform_strategy_influence"]["confidence"]
        assert c1 == c2


# ---------------------------------------------------------------------------
# Enrich subtitle influence reasoning
# ---------------------------------------------------------------------------

class TestEnrichSubtitleReason:

    def _support(self) -> dict:
        return {
            "supported": True,
            "bias": {"style": "clean_pro"},
            "reasoning": ["Platform strategy supports compact clean subtitles"],
        }

    def test_appends_to_existing_reasoning(self):
        original = {"reasoning": ["Existing line"]}
        enriched = enrich_subtitle_influence_reasoning(original, self._support())
        assert "Existing line" in enriched["reasoning"]
        assert "Platform strategy supports compact clean subtitles" in enriched["reasoning"]

    def test_does_not_change_bias_values(self):
        original = {"style_bias": "viral_bold", "reasoning": []}
        enriched = enrich_subtitle_influence_reasoning(original, self._support())
        assert enriched["style_bias"] == "viral_bold"

    def test_caps_total_reasoning_at_6(self):
        original = {"reasoning": [f"line {i}" for i in range(5)]}
        support = {"supported": True, "reasoning": ["new 1", "new 2", "new 3"]}
        enriched = enrich_subtitle_influence_reasoning(original, support)
        assert len(enriched["reasoning"]) <= 6

    def test_unsupported_returns_original(self):
        original = {"reasoning": ["existing"]}
        enriched = enrich_subtitle_influence_reasoning(original, {"supported": False})
        assert enriched == original

    def test_empty_influence_dict_returns_empty(self):
        enriched = enrich_subtitle_influence_reasoning({}, self._support())
        assert isinstance(enriched, dict)

    def test_none_influence_dict_returns_empty(self):
        enriched = enrich_subtitle_influence_reasoning(None, self._support())  # type: ignore
        assert isinstance(enriched, dict)

    def test_no_crash_on_missing_reasoning_in_support(self):
        enriched = enrich_subtitle_influence_reasoning({"reasoning": []}, {"supported": True, "reasoning": []})
        assert isinstance(enriched, dict)


# ---------------------------------------------------------------------------
# Enrich camera influence reasoning
# ---------------------------------------------------------------------------

class TestEnrichCameraReason:

    def _support(self) -> dict:
        return {
            "supported": True,
            "bias": {"motion_energy": "low_medium"},
            "reasoning": ["Platform strategy supports stable podcast framing"],
        }

    def test_appends_to_existing_reasoning(self):
        original = {"reasoning": ["Existing camera line"]}
        enriched = enrich_camera_influence_reasoning(original, self._support())
        assert "Existing camera line" in enriched["reasoning"]
        assert "Platform strategy supports stable podcast framing" in enriched["reasoning"]

    def test_does_not_change_tuning_values(self):
        original = {"motion_bias": "smoothing", "reasoning": []}
        enriched = enrich_camera_influence_reasoning(original, self._support())
        assert enriched["motion_bias"] == "smoothing"

    def test_caps_total_reasoning_at_6(self):
        original = {"reasoning": [f"line {i}" for i in range(5)]}
        support = {"supported": True, "reasoning": ["cam 1", "cam 2"]}
        enriched = enrich_camera_influence_reasoning(original, support)
        assert len(enriched["reasoning"]) <= 6

    def test_unsupported_returns_original(self):
        original = {"reasoning": ["existing"]}
        enriched = enrich_camera_influence_reasoning(original, {"supported": False})
        assert enriched == original

    def test_no_crash_on_empty_inputs(self):
        enriched = enrich_camera_influence_reasoning({}, {"supported": True, "reasoning": []})
        assert isinstance(enriched, dict)


# ---------------------------------------------------------------------------
# Enrich ranking influence reasoning
# ---------------------------------------------------------------------------

class TestEnrichRankingReason:

    def _support(self) -> dict:
        return {
            "supported": True,
            "bias": {"priority": "retention_creator_fit"},
            "reasoning": ["Platform strategy supports retention and creator-fit ranking"],
        }

    def test_appends_to_existing_reasoning_key(self):
        original = {"reasoning": ["existing ranking line"]}
        enriched = enrich_ranking_influence_reasoning(original, self._support())
        assert "existing ranking line" in enriched["reasoning"]
        assert "Platform strategy supports retention and creator-fit ranking" in enriched["reasoning"]

    def test_appends_to_explainability_key_when_present(self):
        original = {"explainability": ["existing explainability"]}
        enriched = enrich_ranking_influence_reasoning(original, self._support())
        assert "existing explainability" in enriched["explainability"]
        assert "Platform strategy supports retention and creator-fit ranking" in enriched["explainability"]

    def test_does_not_change_ranking_priority(self):
        original = {"ranking_priority_bias": "hook_strength", "reasoning": []}
        enriched = enrich_ranking_influence_reasoning(original, self._support())
        assert enriched["ranking_priority_bias"] == "hook_strength"

    def test_caps_total_at_6(self):
        original = {"reasoning": [f"line {i}" for i in range(5)]}
        support = {"supported": True, "reasoning": ["r1", "r2", "r3"]}
        enriched = enrich_ranking_influence_reasoning(original, support)
        assert len(enriched["reasoning"]) <= 6

    def test_unsupported_returns_original(self):
        original = {"reasoning": ["existing"]}
        enriched = enrich_ranking_influence_reasoning(original, {"supported": False})
        assert enriched == original

    def test_no_crash_on_empty_inputs(self):
        enriched = enrich_ranking_influence_reasoning({}, {"supported": True, "reasoning": []})
        assert isinstance(enriched, dict)

    def test_no_crash_on_none(self):
        enriched = enrich_ranking_influence_reasoning(None, self._support())  # type: ignore
        assert enriched is None or isinstance(enriched, dict)


# ---------------------------------------------------------------------------
# Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:

    def test_edit_plan_has_platform_strategy_influence_field(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "platform_strategy_influence")
        assert plan.platform_strategy_influence == {}

    def test_to_dict_includes_platform_strategy_influence(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.platform_strategy_influence = {"available": True, "platform": "tiktok"}
        d = plan.to_dict()
        assert "platform_strategy_influence" in d
        assert d["platform_strategy_influence"]["platform"] == "tiktok"

    def test_default_is_empty_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert d["platform_strategy_influence"] == {}

    def test_backward_compat_all_55_fields_still_present(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for key in (
            "platform_context", "platform_subtitle_context",
            "platform_camera_context", "platform_hook_context",
            "platform_render_strategy", "platform_strategy_influence",
        ):
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Duck-typed plan object
# ---------------------------------------------------------------------------

class TestDuckTypedPlanObject:

    def test_accepts_object_with_attributes(self):
        class FakePlan:
            platform_render_strategy = _prs()

        result = build_platform_strategy_influence(FakePlan())
        psi = result["platform_strategy_influence"]
        assert psi["available"] is True
        assert psi["platform"] == "tiktok"

    def test_object_with_unavailable_prs_returns_fallback(self):
        class FakePlan:
            platform_render_strategy = _prs(available=False)

        result = build_platform_strategy_influence(FakePlan())
        assert result["platform_strategy_influence"]["available"] is False

    def test_object_with_no_prs_attribute_returns_fallback(self):
        class FakePlan:
            pass

        result = build_platform_strategy_influence(FakePlan())
        assert result["platform_strategy_influence"]["available"] is False
