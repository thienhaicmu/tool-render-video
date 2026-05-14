"""
test_ai_phase61a_creator_archetype_strategy.py — Tests for Phase 61A Creator Archetype Strategy.

Coverage:
  - All 7 supported archetypes produce correct strategy shape
  - Unknown archetype → available=False fallback
  - Allowed value normalization (invalid values normalized)
  - Confidence clamping to [0.0, 1.0]
  - Mode compatibility metadata present for all modes
  - No execution flags or unsafe fields exposed
  - No crash on None/empty edit_plan
  - Deterministic output (same inputs → same output)
  - creator_preference_profile confidence modulates archetype confidence
  - Advisory-only: no render mutations, no execution fields

Required execution-style tests:
  test_execution_podcast_strategy       — full podcast strategy shape with correct values
  test_execution_unknown_fallback       — unknown creator → available=False, no strategy
  test_execution_all_archetypes_build   — all 7 supported archetypes build without error
"""
import pytest
from types import SimpleNamespace

from app.ai.creator_archetype.creator_archetype_engine import (
    build_creator_archetype_strategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edit_plan(creator_type: str = "podcast", profile_confidence: float = 0.85):
    return SimpleNamespace(
        creator_preference_profile={
            "creator_type": creator_type,
            "confidence":   profile_confidence,
        },
        ai_execution_mode={},
    )


def _edit_plan_empty():
    return SimpleNamespace()


# ---------------------------------------------------------------------------
# Required execution tests
# ---------------------------------------------------------------------------

def test_execution_podcast_strategy():
    """Full podcast strategy: correct shape, values, confidence, mode_compatibility."""
    plan = _edit_plan("podcast")
    result = build_creator_archetype_strategy(plan, context={"job_id": "test"})
    cs = result["creator_archetype_strategy"]

    assert cs["available"] is True,                 "available must be True for known archetype"
    assert cs["creator_type"] == "podcast",         "creator_type must be preserved"
    assert cs["confidence"] > 0.0,                  "confidence must be positive"
    assert cs["confidence"] <= 1.0,                 "confidence must be <= 1.0"
    assert len(cs["reasoning"]) > 0,               "reasoning must not be empty"

    strategy = cs["strategy"]
    assert "subtitle" in strategy,                  "strategy must have subtitle domain"
    assert "camera" in strategy,                    "strategy must have camera domain"
    assert "hook" in strategy,                      "strategy must have hook domain"
    assert "ranking" in strategy,                   "strategy must have ranking domain"

    # Podcast subtitle expectations
    assert strategy["subtitle"]["style_bias"] == "clean_pro",      "podcast → clean_pro subtitle"
    assert strategy["subtitle"]["readability_priority"] == "high",  "podcast → high readability"
    # Podcast camera expectations
    assert strategy["camera"]["motion_energy"] == "low",            "podcast → low motion"
    assert strategy["camera"]["stability_priority"] == "high",      "podcast → high stability"
    # Mode compatibility
    mc = cs["mode_compatibility"]
    assert mc["off"]        == "advisory_only",        "off mode → advisory_only"
    assert mc["safe"]       == "conservative_guidance"
    assert mc["balanced"]   == "full_guidance"
    assert mc["aggressive"] == "full_guidance_extended"


def test_execution_unknown_fallback():
    """Unknown creator type → available=False, empty strategy, confidence=0.0."""
    plan = _edit_plan("streamer")
    result = build_creator_archetype_strategy(plan)
    cs = result["creator_archetype_strategy"]

    assert cs["available"] is False,            "available must be False for unknown archetype"
    assert cs["creator_type"] == "streamer",    "creator_type should be preserved even when unknown"
    assert cs["strategy"] == {},                "strategy must be empty for unknown archetype"
    assert cs["confidence"] == 0.0,            "confidence must be 0.0 for unknown archetype"


def test_execution_all_archetypes_build():
    """All 7 supported archetypes build successfully without errors."""
    archetypes = [
        "podcast", "talking_head", "educational", "viral_short_form",
        "storytelling", "interview", "motivation",
    ]
    for archetype in archetypes:
        plan = _edit_plan(archetype)
        result = build_creator_archetype_strategy(plan)
        cs = result["creator_archetype_strategy"]
        assert cs["available"] is True,    f"{archetype} must be available"
        assert cs["creator_type"] == archetype
        assert "subtitle" in cs["strategy"], f"{archetype} must have subtitle strategy"
        assert "camera"   in cs["strategy"], f"{archetype} must have camera strategy"
        assert "hook"     in cs["strategy"], f"{archetype} must have hook strategy"
        assert "ranking"  in cs["strategy"], f"{archetype} must have ranking strategy"


# ---------------------------------------------------------------------------
# Per-archetype strategy value tests
# ---------------------------------------------------------------------------

def test_educational_strategy_moderate_keyword_emphasis():
    """Educational archetype uses moderate keyword emphasis for concept clarity."""
    plan = _edit_plan("educational")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    assert cs["strategy"]["subtitle"]["keyword_emphasis"] == "moderate"
    assert cs["strategy"]["camera"]["stability_priority"] == "high"
    assert cs["strategy"]["hook"]["curiosity_style"] == "curiosity_driven"
    assert cs["strategy"]["ranking"]["priority"] == "retention_readability"


def test_viral_short_form_strategy_high_energy():
    """Viral short-form archetype: compact subtitles, high hook energy, pattern_interrupt."""
    plan = _edit_plan("viral_short_form")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    assert cs["strategy"]["subtitle"]["density_bias"] == "compact"
    assert cs["strategy"]["subtitle"]["keyword_emphasis"] == "strong"
    assert cs["strategy"]["hook"]["hook_energy"] == "high"
    assert cs["strategy"]["hook"]["curiosity_style"] == "pattern_interrupt"
    assert cs["strategy"]["ranking"]["priority"] == "hook_strength_retention"


def test_motivation_strategy_bold_impact():
    """Motivation archetype: bold_impact subtitle, high hook, emotional curiosity."""
    plan = _edit_plan("motivation")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    assert cs["strategy"]["subtitle"]["style_bias"] == "bold_impact"
    assert cs["strategy"]["subtitle"]["keyword_emphasis"] == "strong"
    assert cs["strategy"]["hook"]["hook_energy"] == "high"
    assert cs["strategy"]["hook"]["curiosity_style"] == "emotional"
    assert cs["strategy"]["camera"]["motion_energy"] == "medium_high"


def test_interview_strategy_no_keyword_emphasis():
    """Interview archetype: no keyword emphasis, trust_curiosity, trust_clarity ranking."""
    plan = _edit_plan("interview")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    assert cs["strategy"]["subtitle"]["keyword_emphasis"] == "none"
    assert cs["strategy"]["hook"]["curiosity_style"] == "trust_curiosity"
    assert cs["strategy"]["ranking"]["priority"] == "trust_clarity"


def test_storytelling_strategy_narrative_ranking():
    """Storytelling archetype: soft curiosity, retention_narrative ranking."""
    plan = _edit_plan("storytelling")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    assert cs["strategy"]["hook"]["curiosity_style"] == "soft_direct"
    assert cs["strategy"]["ranking"]["priority"] == "retention_narrative"
    assert cs["strategy"]["camera"]["motion_energy"] == "low_medium"


# ---------------------------------------------------------------------------
# Allowed value normalization tests
# ---------------------------------------------------------------------------

def test_allowed_value_normalization_invalid_style_bias():
    """An archetype with an invalid style_bias value would be normalized to a fallback."""
    from app.ai.creator_archetype.creator_archetype_engine import _normalize, _ALLOWED
    # Valid value passes through
    result = _normalize("clean_pro", _ALLOWED["subtitle.style_bias"], "unknown")
    assert result == "clean_pro"
    # Invalid value returns fallback
    invalid = _normalize("neon_rainbow", _ALLOWED["subtitle.style_bias"], "unknown")
    assert invalid == "unknown"


def test_all_archetype_strategy_values_in_allowed_sets():
    """All values in all archetype strategies must be in their allowed sets."""
    from app.ai.creator_archetype.creator_archetype_engine import _ALLOWED, _ARCHETYPE_STRATEGIES
    archetypes = ["podcast", "talking_head", "educational", "viral_short_form",
                  "storytelling", "interview", "motivation"]
    for archetype in archetypes:
        data = _ARCHETYPE_STRATEGIES[archetype]
        for domain in ("subtitle", "camera", "hook", "ranking"):
            for key, value in data.get(domain, {}).items():
                allowed_key = f"{domain}.{key}"
                if allowed_key in _ALLOWED:
                    assert value in _ALLOWED[allowed_key], \
                        f"{archetype}.{domain}.{key}={value!r} not in allowed set"


# ---------------------------------------------------------------------------
# Confidence tests
# ---------------------------------------------------------------------------

def test_confidence_clamped_to_one():
    """Confidence is always clamped to [0.0, 1.0]."""
    plan = _edit_plan("podcast", profile_confidence=2.0)
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    assert cs["confidence"] <= 1.0

def test_confidence_zero_for_unknown():
    plan = _edit_plan("unknown_type")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    assert cs["confidence"] == 0.0


def test_confidence_positive_for_known():
    plan = _edit_plan("podcast", profile_confidence=0.0)
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    assert cs["confidence"] > 0.0


def test_confidence_modulated_by_profile():
    """Higher profile confidence yields higher archetype confidence."""
    plan_low  = _edit_plan("podcast", profile_confidence=0.30)
    plan_high = _edit_plan("podcast", profile_confidence=0.95)
    conf_low  = build_creator_archetype_strategy(plan_low)["creator_archetype_strategy"]["confidence"]
    conf_high = build_creator_archetype_strategy(plan_high)["creator_archetype_strategy"]["confidence"]
    assert conf_high > conf_low, "higher profile confidence → higher archetype confidence"


# ---------------------------------------------------------------------------
# No execution flags / no unsafe fields
# ---------------------------------------------------------------------------

def test_no_execution_flags_in_strategy():
    """Strategy must not contain any execution promotion flags."""
    plan = _edit_plan("podcast")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    strategy_str = str(cs["strategy"])
    forbidden = ("highlight_per_word", "reframe_mode", "payload", "promote", "execute",
                 "segment_selection", "apply_", "mutation")
    for term in forbidden:
        assert term not in strategy_str, f"Strategy must not contain execution term: {term!r}"


def test_no_internal_keys_exposed():
    """Internal-only keys (prefixed _) must not appear in strategy output."""
    plan = _edit_plan("podcast")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    for domain_key, domain_val in cs["strategy"].items():
        if isinstance(domain_val, dict):
            for k in domain_val:
                assert not k.startswith("_"), f"Internal key {k!r} exposed in {domain_key}"


def test_mode_compatibility_covers_all_modes():
    """mode_compatibility must cover all four execution modes."""
    plan = _edit_plan("educational")
    cs = build_creator_archetype_strategy(plan)["creator_archetype_strategy"]
    mc = cs["mode_compatibility"]
    assert "off"        in mc
    assert "safe"       in mc
    assert "balanced"   in mc
    assert "aggressive" in mc


# ---------------------------------------------------------------------------
# Deterministic output test
# ---------------------------------------------------------------------------

def test_deterministic_output():
    plan = _edit_plan("motivation", profile_confidence=0.87)
    result_a = build_creator_archetype_strategy(plan)
    result_b = build_creator_archetype_strategy(plan)
    assert result_a == result_b


# ---------------------------------------------------------------------------
# Safety / fallback tests
# ---------------------------------------------------------------------------

def test_never_raises_on_none_edit_plan():
    result = build_creator_archetype_strategy(None)
    assert "creator_archetype_strategy" in result
    cs = result["creator_archetype_strategy"]
    assert cs["available"] is False
    assert cs["confidence"] == 0.0


def test_never_raises_on_empty_edit_plan():
    result = build_creator_archetype_strategy(_edit_plan_empty())
    assert "creator_archetype_strategy" in result


def test_never_raises_on_dict_edit_plan():
    plan = {"creator_preference_profile": {"creator_type": "interview", "confidence": 0.80}}
    result = build_creator_archetype_strategy(plan)
    cs = result["creator_archetype_strategy"]
    assert cs["available"] is True
    assert cs["creator_type"] == "interview"


def test_fallback_shape_complete():
    result = build_creator_archetype_strategy(None)
    cs = result["creator_archetype_strategy"]
    required = {"available", "creator_type", "strategy", "confidence", "reasoning"}
    assert required.issubset(cs.keys()), f"Missing keys: {required - cs.keys()}"
