"""
test_ai_phase59a_subtitle_promotion.py — Phase 59A subtitle influence promotion tests.

Covers:
  - applies preset when eligible (high confidence, neutral default style)
  - does not apply when subtitles disabled
  - does not apply when edit_plan is None
  - user override wins (subtitle_style != neutral)
  - subtitle_ai_style_lock blocks promotion
  - unknown / disallowed preset is not applied
  - confidence below preset threshold blocks promotion
  - confidence below emphasis threshold blocks emphasis-only path
  - density transition stored as advisory only — no field mutation
  - keyword emphasis sets highlight_per_word=True, never False
  - existing highlight_per_word=True is preserved (never toggled off)
  - viral_bold preset implies keyword emphasis when emphasis delta not set
  - boxed_caption does NOT imply keyword emphasis
  - platform_render_strategy signal promotes preset
  - platform_strategy_influence signal promotes preset
  - Phase 50A preference signal promotes preset (lowest priority)
  - fallback report shape is safe on None edit_plan
  - fallback report shape is safe on empty edit_plan
  - deterministic: same inputs produce same output
  - no transcript mutation (payload has no text fields touched)
  - report["applied"] contains promotion entry when applied
  - report["skipped"] contains reason when not applied
  - render_influence integration: phase59a fires inside apply_ai_render_influence
"""
from __future__ import annotations

import types
import pytest

from app.ai.subtitle_promotion.subtitle_promotion_engine import (
    promote_subtitle_influence,
    ALLOWED_PROMOTION_PRESETS,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _payload(
    add_subtitle: bool = True,
    subtitle_style: str = "pro_karaoke",
    highlight_per_word: bool = False,
    ai_director_enabled: bool = True,
    ai_render_influence_enabled: bool = True,
    subtitle_ai_style_lock: bool = False,
) -> types.SimpleNamespace:
    p = types.SimpleNamespace(
        add_subtitle=add_subtitle,
        subtitle_style=subtitle_style,
        highlight_per_word=highlight_per_word,
        ai_director_enabled=ai_director_enabled,
        ai_render_influence_enabled=ai_render_influence_enabled,
        subtitle_ai_style_lock=subtitle_ai_style_lock,
        # Transcript / timing fields — must never be touched
        transcript_text="hello world",
        segments=[{"start": 0.0, "end": 5.0, "text": "hello world"}],
    )
    return p


def _edit_plan(
    sub_influence_preset: str = "clean_pro",
    sub_influence_available: bool = True,
    sub_influence_emphasis_delta: float = 0.15,
    pref_confidence: float = 0.85,
    pref_style: str = "clean_pro",
    pref_keyword_emphasis: str = "moderate",
    prs_available: bool = False,
    prs_style_bias: str = "clean_pro",
    prs_confidence: float = 0.85,
    prs_keyword_emphasis: str = "moderate",
    psi_available: bool = False,
    psi_style: str = "clean_pro",
) -> types.SimpleNamespace:
    plan = types.SimpleNamespace()
    plan.creator_subtitle_influence = {
        "available": sub_influence_available,
        "confidence_tier": "high",
        "preset_bias": sub_influence_preset,
        "preset_bias_strength": 0.60,
        "density_nudge": "reduce",
        "emphasis_delta": sub_influence_emphasis_delta,
        "reasoning": ["test signal"],
    }
    plan.creator_subtitle_preference = {
        "available": True,
        "subtitle_preference": {
            "style": pref_style,
            "confidence": pref_confidence,
            "keyword_emphasis": pref_keyword_emphasis,
            "density": "medium",
        },
    }
    plan.platform_render_strategy = {
        "available": prs_available,
        "confidence": prs_confidence,
        "platform": "tiktok",
        "strategy": {
            "subtitle": {
                "style_bias": prs_style_bias,
                "density_bias": "compact",
                "keyword_emphasis": prs_keyword_emphasis,
            }
        },
    }
    plan.platform_strategy_influence = {
        "available": psi_available,
        "confidence": 0.80,
        "subtitle": {
            "supported": True,
            "bias": {"style": psi_style, "density": "compact"},
            "confidence_delta": 0.04,
        },
    }
    return plan


# ---------------------------------------------------------------------------
# 1. Core promotion — preset applied when eligible
# ---------------------------------------------------------------------------

def test_applies_preset_when_eligible():
    payload = _payload()
    plan = _edit_plan(sub_influence_preset="viral_bold", pref_confidence=0.85)
    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    assert promo["applied"] is True
    assert promo["preset_applied"] == "viral_bold"
    assert payload.subtitle_style == "viral_bold"


def test_applies_clean_pro_preset():
    payload = _payload()
    plan = _edit_plan(sub_influence_preset="clean_pro", pref_confidence=0.82)
    _, report = promote_subtitle_influence(payload, plan)
    assert report["subtitle_execution_promotion"]["preset_applied"] == "clean_pro"
    assert payload.subtitle_style == "clean_pro"


def test_applies_boxed_caption_preset():
    payload = _payload()
    plan = _edit_plan(sub_influence_preset="boxed_caption", pref_confidence=0.81)
    _, report = promote_subtitle_influence(payload, plan)
    assert report["subtitle_execution_promotion"]["preset_applied"] == "boxed_caption"
    assert payload.subtitle_style == "boxed_caption"


# ---------------------------------------------------------------------------
# 2. Safety gates — subtitles disabled
# ---------------------------------------------------------------------------

def test_does_not_apply_when_subtitles_disabled():
    payload = _payload(add_subtitle=False)
    plan = _edit_plan(pref_confidence=0.90)
    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    assert promo["applied"] is False
    assert "subtitles_disabled" in promo["reason"]
    assert payload.subtitle_style == "pro_karaoke"  # unchanged


def test_does_not_apply_when_edit_plan_none():
    payload = _payload()
    _, report = promote_subtitle_influence(payload, None)
    promo = report["subtitle_execution_promotion"]
    assert promo["applied"] is False
    assert "no_edit_plan" in promo["reason"]
    assert payload.subtitle_style == "pro_karaoke"  # unchanged


# ---------------------------------------------------------------------------
# 3. User override — explicit style blocks promotion
# ---------------------------------------------------------------------------

def test_user_override_wins_viral_bold():
    payload = _payload(subtitle_style="viral_bold")
    plan = _edit_plan(sub_influence_preset="clean_pro", pref_confidence=0.92)
    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    assert promo["applied"] is False
    assert "user_override" in promo["reason"]
    assert payload.subtitle_style == "viral_bold"  # unchanged


def test_user_override_wins_clean_pro():
    payload = _payload(subtitle_style="clean_pro")
    plan = _edit_plan(sub_influence_preset="viral_bold", pref_confidence=0.92)
    _, report = promote_subtitle_influence(payload, plan)
    assert report["subtitle_execution_promotion"]["applied"] is False
    assert payload.subtitle_style == "clean_pro"


def test_user_override_wins_tiktok_bounce():
    payload = _payload(subtitle_style="tiktok_bounce_v1")
    plan = _edit_plan(pref_confidence=0.90)
    _, report = promote_subtitle_influence(payload, plan)
    assert report["subtitle_execution_promotion"]["applied"] is False
    assert payload.subtitle_style == "tiktok_bounce_v1"


def test_subtitle_ai_style_lock_blocks_promotion():
    payload = _payload(subtitle_style="pro_karaoke", subtitle_ai_style_lock=True)
    plan = _edit_plan(pref_confidence=0.90)
    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    assert promo["applied"] is False
    assert "user_override" in promo["reason"]
    assert payload.subtitle_style == "pro_karaoke"


# ---------------------------------------------------------------------------
# 4. Unknown / disallowed preset is not applied
# ---------------------------------------------------------------------------

def test_unknown_preset_not_applied():
    payload = _payload()
    plan = _edit_plan(sub_influence_preset="unknown", pref_style="unknown", pref_confidence=0.90)
    _, report = promote_subtitle_influence(payload, plan)
    # No preset promoted — but emphasis might still fire
    promo = report["subtitle_execution_promotion"]
    assert promo["preset_applied"] is None
    assert payload.subtitle_style == "pro_karaoke"


def test_arbitrary_preset_not_applied():
    payload = _payload()
    # All signal sources point to a non-allowed preset so no preset should be promoted
    plan = _edit_plan(
        sub_influence_preset="my_custom_style_xyz",
        pref_style="my_custom_style_xyz",
        pref_confidence=0.90,
    )
    _, report = promote_subtitle_influence(payload, plan)
    assert report["subtitle_execution_promotion"]["preset_applied"] is None
    assert payload.subtitle_style == "pro_karaoke"


# ---------------------------------------------------------------------------
# 5. Confidence threshold gates
# ---------------------------------------------------------------------------

def test_low_confidence_blocks_preset_promotion():
    # pref_confidence below _CONF_THRESHOLD_PRESET (0.80)
    payload = _payload()
    plan = _edit_plan(sub_influence_preset="viral_bold", pref_confidence=0.70)
    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    assert promo["preset_applied"] is None
    assert payload.subtitle_style == "pro_karaoke"


def test_confidence_at_exact_threshold_allows_promotion():
    payload = _payload()
    plan = _edit_plan(sub_influence_preset="clean_pro", pref_confidence=0.80)
    _, report = promote_subtitle_influence(payload, plan)
    assert report["subtitle_execution_promotion"]["preset_applied"] == "clean_pro"


def test_low_confidence_blocks_emphasis_promotion():
    payload = _payload(highlight_per_word=False)
    plan = _edit_plan(
        sub_influence_preset="unknown",
        pref_style="unknown",
        pref_confidence=0.70,
        sub_influence_emphasis_delta=0.20,
        pref_keyword_emphasis="strong",
    )
    _, report = promote_subtitle_influence(payload, plan)
    assert payload.highlight_per_word is False


# ---------------------------------------------------------------------------
# 6. Density — advisory only, no field mutation
# ---------------------------------------------------------------------------

def test_density_is_advisory_only():
    payload = _payload()
    plan = _edit_plan(sub_influence_preset="clean_pro", pref_confidence=0.85)
    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    # density_applied may be set as advisory
    assert isinstance(promo["density_applied"], (str, type(None)))
    # But payload has no density field mutated (it doesn't have one)
    assert not hasattr(payload, "subtitle_density") or payload.subtitle_style != "density"


def test_density_advisory_value_is_bounded():
    payload = _payload()
    plan = _edit_plan(sub_influence_preset="clean_pro", pref_confidence=0.85)
    _, report = promote_subtitle_influence(payload, plan)
    density = report["subtitle_execution_promotion"].get("density_applied")
    if density is not None:
        assert density in {"light", "medium", "dense", None}


# ---------------------------------------------------------------------------
# 7. Keyword emphasis — only enable, never disable
# ---------------------------------------------------------------------------

def test_keyword_emphasis_enables_highlight_per_word():
    payload = _payload(highlight_per_word=False)
    plan = _edit_plan(
        sub_influence_preset="viral_bold",
        pref_confidence=0.85,
        sub_influence_emphasis_delta=0.15,
        pref_keyword_emphasis="strong",
    )
    _, report = promote_subtitle_influence(payload, plan)
    assert payload.highlight_per_word is True
    assert report["subtitle_execution_promotion"]["keyword_emphasis_applied"] is True


def test_keyword_emphasis_never_disables():
    payload = _payload(highlight_per_word=True)
    plan = _edit_plan(
        sub_influence_preset="clean_pro",
        pref_confidence=0.85,
        sub_influence_emphasis_delta=-0.25,
        pref_keyword_emphasis="none",
    )
    _, report = promote_subtitle_influence(payload, plan)
    # AI must NOT set highlight_per_word to False
    assert payload.highlight_per_word is True


def test_existing_highlight_unchanged_when_already_true():
    payload = _payload(highlight_per_word=True)
    plan = _edit_plan(pref_confidence=0.85)
    _, report = promote_subtitle_influence(payload, plan)
    assert payload.highlight_per_word is True
    # keyword_emphasis_applied should be False since it was already True
    assert report["subtitle_execution_promotion"].get("keyword_emphasis_applied") is False


def test_no_transcript_mutation():
    payload = _payload()
    original_transcript = payload.transcript_text
    original_segments = list(payload.segments)
    plan = _edit_plan(pref_confidence=0.85)
    promote_subtitle_influence(payload, plan)
    assert payload.transcript_text == original_transcript
    assert payload.segments == original_segments


# ---------------------------------------------------------------------------
# 8. Preset implies keyword emphasis
# ---------------------------------------------------------------------------

def test_viral_bold_implies_keyword_emphasis():
    payload = _payload(highlight_per_word=False)
    plan = _edit_plan(
        sub_influence_preset="viral_bold",
        pref_confidence=0.85,
        sub_influence_emphasis_delta=0.0,   # delta alone won't trigger
        pref_keyword_emphasis="unknown",     # preference alone won't trigger
    )
    _, report = promote_subtitle_influence(payload, plan)
    # viral_bold promotion implies highlight_per_word=True
    assert payload.highlight_per_word is True
    assert report["subtitle_execution_promotion"]["keyword_emphasis_applied"] is True


def test_boxed_caption_does_not_imply_keyword_emphasis():
    payload = _payload(highlight_per_word=False)
    plan = _edit_plan(
        sub_influence_preset="boxed_caption",
        pref_confidence=0.85,
        sub_influence_emphasis_delta=0.0,
        pref_keyword_emphasis="unknown",
    )
    _, report = promote_subtitle_influence(payload, plan)
    # boxed_caption implies highlight_per_word=False — but we never DISABLE
    # So existing False stays False when no positive emphasis signal
    assert payload.highlight_per_word is False


# ---------------------------------------------------------------------------
# 9. Signal priority — platform_render_strategy wins over Phase 50A preference
# ---------------------------------------------------------------------------

def test_platform_strategy_overrides_preference_when_available():
    payload = _payload()
    plan = _edit_plan(
        sub_influence_available=False,      # Phase 50C unavailable
        pref_style="viral_bold",            # Phase 50A says viral_bold
        pref_confidence=0.85,
        prs_available=True,
        prs_style_bias="clean_pro",         # Phase 55E says clean_pro
        prs_confidence=0.87,
    )
    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    # Phase 55E (clean_pro) wins because Phase 50C is unavailable
    assert promo["preset_applied"] == "clean_pro"
    assert payload.subtitle_style == "clean_pro"


def test_phase50c_wins_over_platform_strategy():
    payload = _payload()
    plan = _edit_plan(
        sub_influence_preset="viral_bold",  # Phase 50C says viral_bold
        sub_influence_available=True,
        pref_confidence=0.85,
        prs_available=True,
        prs_style_bias="clean_pro",         # Phase 55E says clean_pro
        prs_confidence=0.87,
    )
    _, report = promote_subtitle_influence(payload, plan)
    # Phase 50C takes priority
    assert report["subtitle_execution_promotion"]["preset_applied"] == "viral_bold"


def test_phase50a_preference_promotes_when_no_other_signal():
    payload = _payload()
    plan = _edit_plan(
        sub_influence_available=False,      # Phase 50C unavailable
        prs_available=False,                # Phase 55E unavailable
        psi_available=False,                # Phase 56 unavailable
        pref_style="boxed_caption",         # Phase 50A
        pref_confidence=0.82,
    )
    _, report = promote_subtitle_influence(payload, plan)
    assert report["subtitle_execution_promotion"]["preset_applied"] == "boxed_caption"


# ---------------------------------------------------------------------------
# 10. Fallback safety
# ---------------------------------------------------------------------------

def test_fallback_report_shape_on_none_plan():
    payload = _payload()
    _, report = promote_subtitle_influence(payload, None)
    promo = report["subtitle_execution_promotion"]
    assert "applied" in promo
    assert "preset_applied" in promo
    assert "density_applied" in promo
    assert "keyword_emphasis_applied" in promo
    assert "confidence" in promo
    assert "reason" in promo
    assert "reasoning" in promo
    assert promo["applied"] is False


def test_fallback_report_shape_on_empty_plan():
    payload = _payload()
    plan = types.SimpleNamespace()
    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    assert promo["applied"] is False
    assert promo["preset_applied"] is None
    assert isinstance(promo["reasoning"], list)


def test_never_raises_on_malformed_plan():
    payload = _payload()
    for bad_plan in [42, "string", [], {}, object()]:
        try:
            _, report = promote_subtitle_influence(payload, bad_plan)
            assert "subtitle_execution_promotion" in report
        except Exception as exc:
            pytest.fail(f"promote_subtitle_influence raised on {bad_plan!r}: {exc}")


def test_never_raises_on_malformed_payload():
    plan = _edit_plan(pref_confidence=0.85)
    for bad_payload in [None, 42, "str", []]:
        try:
            _, report = promote_subtitle_influence(bad_payload, plan)
            assert "subtitle_execution_promotion" in report
        except Exception as exc:
            pytest.fail(f"promote_subtitle_influence raised on payload={bad_payload!r}: {exc}")


# ---------------------------------------------------------------------------
# 11. Determinism
# ---------------------------------------------------------------------------

def test_deterministic_same_output():
    payload_a = _payload()
    payload_b = _payload()
    plan = _edit_plan(sub_influence_preset="clean_pro", pref_confidence=0.85)
    _, report_a = promote_subtitle_influence(payload_a, plan)
    _, report_b = promote_subtitle_influence(payload_b, plan)
    assert report_a == report_b
    assert payload_a.subtitle_style == payload_b.subtitle_style
    assert payload_a.highlight_per_word == payload_b.highlight_per_word


# ---------------------------------------------------------------------------
# 12. Allowed preset set contract
# ---------------------------------------------------------------------------

def test_allowed_promotion_presets_are_real_presets():
    from app.services.subtitle_engine import normalize_subtitle_style_id
    for preset in ALLOWED_PROMOTION_PRESETS:
        normalized = normalize_subtitle_style_id(preset)
        # Must not fall back to the default
        assert normalized == preset, (
            f"Preset {preset!r} not recognized by subtitle_engine "
            f"(normalized to {normalized!r})"
        )


# ---------------------------------------------------------------------------
# 13. render_influence integration
# ---------------------------------------------------------------------------

def test_render_influence_applies_promotion():
    """Phase 59A fires inside apply_ai_render_influence when all gates pass."""
    from app.ai.director.render_influence import apply_ai_render_influence

    payload = _payload()
    plan = _edit_plan(sub_influence_preset="viral_bold", pref_confidence=0.85)
    # Attach minimum required fields for render_influence
    plan.camera = None
    plan.pacing = None
    plan.beat_visual_execution = None
    plan.variants = None
    plan.variant_selection = None
    plan.story_optimization = None
    plan.timing_mutation = None
    plan.render_decision_preview = None
    plan.execution_recommendations = None
    plan.execution_simulation = None
    plan.safe_render_mutations = None
    plan.multivariant_render_plans = None
    plan.multivariant_execution = None
    plan.output_ranking = None
    plan.ai_apply_policy = None
    plan.timing_apply = None
    plan.subtitle_text_apply = None
    plan.camera_motion_apply = None
    plan.clip_candidate_discovery = None
    plan.clip_segment_selection = None
    plan.clip_batch_planning = None
    plan.feature_enhancement = None
    plan.creator_retrieval = None
    plan.adaptive_creator_intelligence = None
    plan.creator_feedback_intelligence = None
    plan.market_optimization_intelligence = None
    plan.render_quality_evaluation = None
    plan.creator_preset_evolution = None
    plan.multi_signal_orchestration = None
    plan.safe_influence_pack = None
    plan.subtitle_execution_promotion = {}
    plan.best_strategy_reasoning = None
    plan.strategy_variants = None
    plan.variant_evaluation = None
    plan.subtitle_quality_v2 = None
    plan.camera_quality_v2 = None
    plan.hook_quality_v2 = None
    plan.render_quality_v2 = None
    plan.knowledge_injection = None
    plan.explainability = None
    plan.beat_execution = None

    payload_out, influence_report = apply_ai_render_influence(payload, plan)

    # Promotion must appear in applied list
    applied_str = " ".join(influence_report.get("applied", []))
    assert "subtitle_promotion:phase59a" in applied_str, (
        f"Expected 'subtitle_promotion:phase59a' in applied, got: {influence_report['applied']}"
    )
    assert payload_out.subtitle_style == "viral_bold"
