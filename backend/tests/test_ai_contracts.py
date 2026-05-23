"""
test_ai_contracts.py — Tests for Phase 5.3 AI contract models.

Verifies:
- Default construction of each model
- to_dict() output has expected keys
- Missing optional fields are safe (None or [])
- source_knowledge_ids preserved in to_dict
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# CreativeBrief
# ---------------------------------------------------------------------------

def test_creative_brief_default_construction():
    from app.ai.contracts import CreativeBrief
    cb = CreativeBrief()
    assert cb.pacing_style is None
    assert cb.subtitle_emphasis is None
    assert cb.hook_strategy is None
    assert cb.visual_energy is None
    assert cb.cta_strategy is None


def test_creative_brief_to_dict_has_expected_keys():
    from app.ai.contracts import CreativeBrief
    cb = CreativeBrief(pacing_style="fast", hook_strategy="problem_hook")
    d = cb.to_dict()
    assert "pacing_style" in d
    assert "subtitle_emphasis" in d
    assert "hook_strategy" in d
    assert "visual_energy" in d
    assert "cta_strategy" in d
    assert d["pacing_style"] == "fast"
    assert d["hook_strategy"] == "problem_hook"


def test_creative_brief_optional_fields_safe():
    from app.ai.contracts import CreativeBrief
    cb = CreativeBrief()
    d = cb.to_dict()
    for key in ("pacing_style", "subtitle_emphasis", "hook_strategy", "visual_energy", "cta_strategy"):
        assert d[key] is None


# ---------------------------------------------------------------------------
# RenderExecutionHints
# ---------------------------------------------------------------------------

def test_render_execution_hints_default_construction():
    from app.ai.contracts import RenderExecutionHints
    h = RenderExecutionHints()
    assert h.cut_interval_min is None
    assert h.cut_interval_max is None
    assert h.playback_speed_hint is None
    assert h.subtitle_emphasis_style is None
    assert h.hook_overlay_enabled is None
    assert h.visual_intensity is None
    assert h.source_knowledge_ids == []
    assert h.validation_notes == []


def test_render_execution_hints_to_dict_has_expected_keys():
    from app.ai.contracts import RenderExecutionHints
    h = RenderExecutionHints(
        cut_interval_min=2.0,
        cut_interval_max=4.0,
        playback_speed_hint=1.1,
        subtitle_emphasis_style="strong",
        hook_overlay_enabled=True,
        visual_intensity="high",
        source_knowledge_ids=["item_001"],
        validation_notes=["clamped speed"],
    )
    d = h.to_dict()
    assert d["cut_interval_min"] == 2.0
    assert d["cut_interval_max"] == 4.0
    assert d["playback_speed_hint"] == 1.1
    assert d["subtitle_emphasis_style"] == "strong"
    assert d["hook_overlay_enabled"] is True
    assert d["visual_intensity"] == "high"
    assert d["source_knowledge_ids"] == ["item_001"]
    assert d["validation_notes"] == ["clamped speed"]


def test_render_execution_hints_source_knowledge_ids_preserved():
    from app.ai.contracts import RenderExecutionHints
    ids = ["abc", "def", "ghi"]
    h = RenderExecutionHints(source_knowledge_ids=ids)
    d = h.to_dict()
    assert d["source_knowledge_ids"] == ids


def test_render_execution_hints_optional_none_safe():
    from app.ai.contracts import RenderExecutionHints
    h = RenderExecutionHints()
    d = h.to_dict()
    for key in (
        "cut_interval_min", "cut_interval_max", "playback_speed_hint",
        "subtitle_emphasis_style", "hook_overlay_enabled", "visual_intensity",
    ):
        assert d[key] is None
    assert d["source_knowledge_ids"] == []
    assert d["validation_notes"] == []


def test_render_execution_hints_list_fields_are_copies():
    """Mutating to_dict() output does not affect the model."""
    from app.ai.contracts import RenderExecutionHints
    h = RenderExecutionHints(source_knowledge_ids=["x"])
    d = h.to_dict()
    d["source_knowledge_ids"].append("y")
    assert h.source_knowledge_ids == ["x"]


# ---------------------------------------------------------------------------
# AIValidationResult
# ---------------------------------------------------------------------------

def test_ai_validation_result_default_construction():
    from app.ai.contracts import AIValidationResult, RenderExecutionHints
    r = AIValidationResult(ok=True, hints=RenderExecutionHints())
    assert r.ok is True
    assert r.fixups == []
    assert r.warnings == []


def test_ai_validation_result_to_dict_has_expected_keys():
    from app.ai.contracts import AIValidationResult, RenderExecutionHints
    r = AIValidationResult(
        ok=True,
        hints=RenderExecutionHints(cut_interval_min=2.0),
        fixups=[{"field": "speed", "original": 3.0, "action": "clamped", "result": 1.5}],
        warnings=["advisory warning"],
    )
    d = r.to_dict()
    assert "ok" in d
    assert "hints" in d
    assert "fixups" in d
    assert "warnings" in d
    assert d["ok"] is True
    assert isinstance(d["hints"], dict)
    assert d["hints"]["cut_interval_min"] == 2.0
    assert len(d["fixups"]) == 1
    assert d["fixups"][0]["field"] == "speed"
    assert d["warnings"] == ["advisory warning"]


def test_ai_validation_result_ok_false_safe():
    from app.ai.contracts import AIValidationResult, RenderExecutionHints
    r = AIValidationResult(ok=False, hints=RenderExecutionHints())
    d = r.to_dict()
    assert d["ok"] is False


def test_ai_validation_result_nested_hints_to_dict():
    from app.ai.contracts import AIValidationResult, RenderExecutionHints
    r = AIValidationResult(
        ok=True,
        hints=RenderExecutionHints(source_knowledge_ids=["kb_001", "kb_002"]),
    )
    d = r.to_dict()
    assert d["hints"]["source_knowledge_ids"] == ["kb_001", "kb_002"]
