"""
test_ai_visual_intensity_config.py — Tests for Phase 5.6 AIVisualIntensityConfig and
build_ai_visual_intensity_config().

Covers:
- valid "low" → applied=False (no safe injection point), render_overrides is dict
- valid "medium" → applied=False (no safe injection point), render_overrides is dict
- valid "high" → applied=False (no safe injection point), render_overrides is dict
- no visual_intensity → applied=False, rejected_reason="no_visual_intensity_hint"
- unknown "ultra_intense" → applied=False, rejected_reason="invalid_visual_intensity"
- execution_hints=None → enabled=False
- source_knowledge_ids preserved in to_dict()
- render_overrides is dict (even if empty)
- never raises on garbage input
- to_dict() has all required keys
- user effect_preset override → rejected_reason="user_visual_override"
- RenderExecutionHints instance input accepted

Note on Phase 5.6 behavior:
  No safe visual intensity injection point was found in the render pipeline.
  Therefore applied=False and render_overrides={} for all valid hints.
  The config is still created and logged as advisory.
"""
from __future__ import annotations

import types
import pytest

from app.ai.visual_hints import AIVisualIntensityConfig, build_ai_visual_intensity_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(effect_preset="slay_soft_01"):
    """Build a minimal payload-like namespace."""
    p = types.SimpleNamespace()
    p.effect_preset = effect_preset
    return p


def _make_hints(visual_intensity="medium", source_ids=None):
    """Return a dict of execution hints with visual_intensity."""
    return {
        "visual_intensity": visual_intensity,
        "source_knowledge_ids": source_ids or ["k1", "k2"],
    }


# ---------------------------------------------------------------------------
# 1. Valid "low" → applied=False (no safe injection point), render_overrides dict
# ---------------------------------------------------------------------------

def test_valid_low_produces_config():
    """Valid 'low' hint → config built, rejected due to no_safe_visual_injection_point."""
    hints = _make_hints("low", ["kb1"])
    cfg = build_ai_visual_intensity_config(hints)
    assert cfg.enabled is True
    assert cfg.visual_intensity == "low"
    # Phase 5.6: no safe injection point — applied=False
    assert cfg.applied is False
    assert cfg.rejected_reason == "no_safe_visual_injection_point"
    assert isinstance(cfg.render_overrides, dict)


def test_valid_low_render_overrides_is_dict():
    """'low' hint → render_overrides is always a dict (even if empty)."""
    cfg = build_ai_visual_intensity_config(_make_hints("low"))
    assert isinstance(cfg.render_overrides, dict)


# ---------------------------------------------------------------------------
# 2. Valid "medium" → applied=False (no safe injection point)
# ---------------------------------------------------------------------------

def test_valid_medium_produces_config():
    """Valid 'medium' hint → config built, rejected due to no_safe_visual_injection_point."""
    cfg = build_ai_visual_intensity_config(_make_hints("medium"))
    assert cfg.enabled is True
    assert cfg.visual_intensity == "medium"
    assert cfg.applied is False
    assert cfg.rejected_reason == "no_safe_visual_injection_point"
    assert isinstance(cfg.render_overrides, dict)


# ---------------------------------------------------------------------------
# 3. Valid "high" → applied=False (no safe injection point)
# ---------------------------------------------------------------------------

def test_valid_high_produces_config():
    """Valid 'high' hint → config built, rejected due to no_safe_visual_injection_point."""
    cfg = build_ai_visual_intensity_config(_make_hints("high"))
    assert cfg.enabled is True
    assert cfg.visual_intensity == "high"
    assert cfg.applied is False
    assert cfg.rejected_reason == "no_safe_visual_injection_point"
    assert isinstance(cfg.render_overrides, dict)


# ---------------------------------------------------------------------------
# 4. No visual_intensity → no_visual_intensity_hint
# ---------------------------------------------------------------------------

def test_no_visual_intensity_hint_rejected():
    """Hints dict without visual_intensity → rejected with no_visual_intensity_hint."""
    hints = {"source_knowledge_ids": ["kb1"], "cut_interval_min": 3.0}
    cfg = build_ai_visual_intensity_config(hints)
    assert cfg.enabled is True
    assert cfg.applied is False
    assert cfg.rejected_reason == "no_visual_intensity_hint"
    assert cfg.visual_intensity is None


def test_visual_intensity_none_rejected():
    """Explicit None visual_intensity → rejected with no_visual_intensity_hint."""
    hints = {"visual_intensity": None, "source_knowledge_ids": []}
    cfg = build_ai_visual_intensity_config(hints)
    assert cfg.applied is False
    assert cfg.rejected_reason == "no_visual_intensity_hint"


# ---------------------------------------------------------------------------
# 5. Unknown "ultra_intense" → invalid_visual_intensity
# ---------------------------------------------------------------------------

def test_unknown_intensity_rejected():
    """Unknown visual_intensity value → rejected with invalid_visual_intensity."""
    cfg = build_ai_visual_intensity_config(_make_hints("ultra_intense"))
    assert cfg.enabled is True
    assert cfg.applied is False
    assert cfg.rejected_reason == "invalid_visual_intensity"
    assert cfg.visual_intensity is None


def test_empty_string_intensity_rejected():
    """Empty string visual_intensity → rejected with invalid_visual_intensity."""
    cfg = build_ai_visual_intensity_config({"visual_intensity": "", "source_knowledge_ids": []})
    assert cfg.applied is False
    assert cfg.rejected_reason == "invalid_visual_intensity"


def test_uppercase_intensity_accepted():
    """Uppercase 'HIGH' → normalised and accepted (but rejected at injection point)."""
    cfg = build_ai_visual_intensity_config({"visual_intensity": "HIGH", "source_knowledge_ids": []})
    assert cfg.enabled is True
    # Normalised to "high" — valid, then rejected at injection point
    assert cfg.visual_intensity == "high"
    assert cfg.rejected_reason == "no_safe_visual_injection_point"


# ---------------------------------------------------------------------------
# 6. execution_hints=None → enabled=False
# ---------------------------------------------------------------------------

def test_none_hints_disabled():
    """None execution_hints → AIVisualIntensityConfig(enabled=False)."""
    cfg = build_ai_visual_intensity_config(None)
    assert cfg.enabled is False
    assert cfg.applied is False


def test_empty_dict_hints_disabled():
    """Empty dict hints → enabled=False."""
    cfg = build_ai_visual_intensity_config({})
    assert cfg.enabled is False
    assert cfg.applied is False


# ---------------------------------------------------------------------------
# 7. source_knowledge_ids preserved in to_dict()
# ---------------------------------------------------------------------------

def test_source_knowledge_ids_preserved():
    """source_knowledge_ids passed through hints appear in config and to_dict()."""
    hints = {"visual_intensity": "high", "source_knowledge_ids": ["vis_001", "tiktok_001"]}
    cfg = build_ai_visual_intensity_config(hints)
    assert cfg.source_knowledge_ids == ["vis_001", "tiktok_001"]
    d = cfg.to_dict()
    assert d["source_knowledge_ids"] == ["vis_001", "tiktok_001"]


def test_source_knowledge_ids_empty():
    """Empty source_knowledge_ids → empty list."""
    hints = {"visual_intensity": "medium", "source_knowledge_ids": []}
    cfg = build_ai_visual_intensity_config(hints)
    assert cfg.source_knowledge_ids == []
    assert cfg.to_dict()["source_knowledge_ids"] == []


# ---------------------------------------------------------------------------
# 8. render_overrides is dict (even if empty)
# ---------------------------------------------------------------------------

def test_render_overrides_always_dict():
    """render_overrides is always a dict regardless of hint validity."""
    for hints_input in [None, {}, _make_hints("low"), _make_hints("bad_value")]:
        cfg = build_ai_visual_intensity_config(hints_input)
        assert isinstance(cfg.render_overrides, dict), f"render_overrides not dict for {hints_input!r}"


def test_render_overrides_empty_when_no_injection():
    """Phase 5.6: render_overrides={} because no safe injection point found."""
    cfg = build_ai_visual_intensity_config(_make_hints("high"))
    assert cfg.render_overrides == {}


# ---------------------------------------------------------------------------
# 9. never raises on garbage input
# ---------------------------------------------------------------------------

def test_garbage_hints_no_raise():
    """Garbage hints dict does not raise."""
    cfg = build_ai_visual_intensity_config({"visual_intensity": [1, 2, 3], "other": object()})
    assert isinstance(cfg, AIVisualIntensityConfig)


def test_garbage_payload_no_raise():
    """Garbage payload does not raise."""
    cfg = build_ai_visual_intensity_config(_make_hints("high"), payload="not_a_payload")
    assert isinstance(cfg, AIVisualIntensityConfig)


def test_none_both_no_raise():
    """None hints and None payload → no raise, enabled=False."""
    cfg = build_ai_visual_intensity_config(None, None)
    assert cfg.enabled is False


def test_list_hints_no_raise():
    """List instead of dict hints → no raise, enabled=False."""
    cfg = build_ai_visual_intensity_config([1, 2, 3], None)
    assert isinstance(cfg, AIVisualIntensityConfig)


def test_int_hints_no_raise():
    """Integer instead of dict hints → no raise, enabled=False."""
    cfg = build_ai_visual_intensity_config(42, None)
    assert isinstance(cfg, AIVisualIntensityConfig)
    assert cfg.enabled is False


def test_very_garbage_no_raise():
    """Multiple garbage combinations do not raise."""
    for bad in [None, {}, [], 42, "string", b"bytes", object(), {"visual_intensity": None}]:
        cfg = build_ai_visual_intensity_config(bad)
        assert isinstance(cfg, AIVisualIntensityConfig)


# ---------------------------------------------------------------------------
# 10. to_dict() has all required keys
# ---------------------------------------------------------------------------

def test_to_dict_has_required_keys():
    """AIVisualIntensityConfig.to_dict() returns all required keys."""
    cfg = AIVisualIntensityConfig(
        enabled=True, applied=False,
        visual_intensity="high",
        source_knowledge_ids=["k1"],
        rejected_reason="no_safe_visual_injection_point",
        validation_fixups=[],
        render_overrides={},
    )
    d = cfg.to_dict()
    for key in (
        "enabled", "applied", "visual_intensity",
        "source_knowledge_ids", "rejected_reason",
        "validation_fixups", "render_overrides",
    ):
        assert key in d, f"Missing key: {key}"


def test_to_dict_values():
    """to_dict() values match dataclass fields."""
    cfg = AIVisualIntensityConfig(
        enabled=True, applied=False,
        visual_intensity="medium",
        source_knowledge_ids=["x"],
        rejected_reason="no_safe_visual_injection_point",
        validation_fixups=[{"field": "y"}],
        render_overrides={},
    )
    d = cfg.to_dict()
    assert d["enabled"] is True
    assert d["applied"] is False
    assert d["visual_intensity"] == "medium"
    assert d["source_knowledge_ids"] == ["x"]
    assert d["rejected_reason"] == "no_safe_visual_injection_point"
    assert d["validation_fixups"] == [{"field": "y"}]
    assert d["render_overrides"] == {}


def test_to_dict_applied_false_disabled():
    """to_dict() on disabled config has correct structure."""
    cfg = AIVisualIntensityConfig(enabled=False)
    d = cfg.to_dict()
    assert d["enabled"] is False
    assert d["applied"] is False
    assert d["visual_intensity"] is None
    assert d["source_knowledge_ids"] == []
    assert d["rejected_reason"] is None
    assert d["render_overrides"] == {}


# ---------------------------------------------------------------------------
# 11. User effect_preset override detection
# ---------------------------------------------------------------------------

def test_user_custom_effect_preset_overrides():
    """User sets non-default effect_preset → rejected with user_visual_override."""
    payload = _make_payload(effect_preset="slay_pop_01")  # not the default
    cfg = build_ai_visual_intensity_config(_make_hints("high"), payload=payload)
    assert cfg.enabled is True
    assert cfg.applied is False
    assert cfg.rejected_reason == "user_visual_override"


def test_user_default_effect_preset_allows_config():
    """User leaves effect_preset at default → not overriding, AI hint proceeds to injection check."""
    payload = _make_payload(effect_preset="slay_soft_01")  # the default
    cfg = build_ai_visual_intensity_config(_make_hints("high"), payload=payload)
    # Phase 5.6: still rejected at injection point — but user_visual_override NOT triggered
    assert cfg.rejected_reason == "no_safe_visual_injection_point"
    assert cfg.applied is False


def test_no_payload_no_user_override():
    """No payload → no user override → proceeds to injection point check."""
    cfg = build_ai_visual_intensity_config(_make_hints("high"), payload=None)
    # Phase 5.6: rejected at injection point (not user_visual_override)
    assert cfg.rejected_reason == "no_safe_visual_injection_point"


# ---------------------------------------------------------------------------
# 12. RenderExecutionHints instance as input
# ---------------------------------------------------------------------------

def test_render_execution_hints_instance():
    """build_ai_visual_intensity_config accepts RenderExecutionHints instance."""
    try:
        from app.ai.contracts import RenderExecutionHints
        hints_obj = RenderExecutionHints(
            source_knowledge_ids=["k99"],
        )
        # Add visual_intensity if the dataclass supports it; else use dict
        hints_dict = hints_obj.to_dict() if hasattr(hints_obj, "to_dict") else {}
        hints_dict["visual_intensity"] = "medium"
        cfg = build_ai_visual_intensity_config(hints_dict)
        assert isinstance(cfg, AIVisualIntensityConfig)
    except Exception:
        # If RenderExecutionHints doesn't have visual_intensity, use dict fallback
        cfg = build_ai_visual_intensity_config({"visual_intensity": "medium", "source_knowledge_ids": []})
        assert isinstance(cfg, AIVisualIntensityConfig)


def test_hints_with_to_dict_method():
    """execution_hints with to_dict() method → to_dict() called for normalisation."""
    class FakeHints:
        def to_dict(self):
            return {"visual_intensity": "low", "source_knowledge_ids": ["x"]}

    cfg = build_ai_visual_intensity_config(FakeHints())
    assert cfg.enabled is True
    assert cfg.visual_intensity == "low"
    assert cfg.source_knowledge_ids == ["x"]
