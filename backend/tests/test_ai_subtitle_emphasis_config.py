"""
test_ai_subtitle_emphasis_config.py — Tests for Phase 5.5 AISubtitleEmphasisConfig.

Verifies:
- Valid emphasis styles → applied=True
- No subtitle_emphasis_style → applied=False, rejected_reason="no_subtitle_emphasis_hint"
- Unknown style → applied=False, rejected_reason="invalid_emphasis_style"
- execution_hints=None → enabled=False
- source_knowledge_ids preserved in to_dict()
- Never raises on garbage input
- to_dict() has all required keys
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_hints(style=None, source_ids=None):
    """Build a minimal execution hints dict."""
    h = {}
    if style is not None:
        h["subtitle_emphasis_style"] = style
    if source_ids is not None:
        h["source_knowledge_ids"] = source_ids
    return h


# ---------------------------------------------------------------------------
# Valid styles → applied=True
# ---------------------------------------------------------------------------

def test_valid_strong_hint_applied():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": "strong"})
    assert cfg.applied is True
    assert cfg.emphasis_style == "strong"
    assert cfg.rejected_reason is None


def test_valid_medium_hint_applied():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": "medium"})
    assert cfg.applied is True
    assert cfg.emphasis_style == "medium"


def test_valid_subtle_hint_applied():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": "subtle"})
    assert cfg.applied is True
    assert cfg.emphasis_style == "subtle"


def test_valid_word_only_hint_applied():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": "word_only"})
    assert cfg.applied is True
    assert cfg.emphasis_style == "word_only"


# ---------------------------------------------------------------------------
# No subtitle_emphasis_style → applied=False
# ---------------------------------------------------------------------------

def test_no_subtitle_emphasis_style_rejected():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"cut_interval_min": 2.0})
    assert cfg.applied is False
    assert cfg.rejected_reason == "no_subtitle_emphasis_hint"


def test_empty_dict_no_subtitle_emphasis():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({})
    # Empty dict → enabled=False (no data at all)
    assert cfg.applied is False


# ---------------------------------------------------------------------------
# Unknown style → invalid_emphasis_style
# ---------------------------------------------------------------------------

def test_unknown_style_rejected():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": "ultra_heavy"})
    assert cfg.applied is False
    assert cfg.rejected_reason == "invalid_emphasis_style"


def test_empty_string_style_rejected():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": ""})
    assert cfg.applied is False
    assert cfg.rejected_reason == "invalid_emphasis_style"


# ---------------------------------------------------------------------------
# execution_hints=None → enabled=False
# ---------------------------------------------------------------------------

def test_none_execution_hints_disabled():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config(None)
    assert cfg.enabled is False
    assert cfg.applied is False


# ---------------------------------------------------------------------------
# RenderExecutionHints instance accepted
# ---------------------------------------------------------------------------

def test_render_execution_hints_instance_accepted():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    from app.ai.contracts import RenderExecutionHints
    h = RenderExecutionHints(subtitle_emphasis_style="strong", source_knowledge_ids=["k1"])
    cfg = build_ai_subtitle_emphasis_config(h)
    assert cfg.applied is True
    assert cfg.emphasis_style == "strong"
    assert "k1" in cfg.source_knowledge_ids


# ---------------------------------------------------------------------------
# source_knowledge_ids preserved
# ---------------------------------------------------------------------------

def test_source_knowledge_ids_preserved():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    ids = ["kb_001", "kb_002", "kb_003"]
    cfg = build_ai_subtitle_emphasis_config({
        "subtitle_emphasis_style": "medium",
        "source_knowledge_ids": ids,
    })
    assert cfg.applied is True
    assert cfg.source_knowledge_ids == ids


def test_source_knowledge_ids_preserved_in_to_dict():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    ids = ["x", "y"]
    cfg = build_ai_subtitle_emphasis_config({
        "subtitle_emphasis_style": "subtle",
        "source_knowledge_ids": ids,
    })
    d = cfg.to_dict()
    assert d["source_knowledge_ids"] == ids


# ---------------------------------------------------------------------------
# Never raises on garbage input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_input", [
    None,
    {},
    [],
    42,
    "not_a_dict",
    {"random_key": "random_value", "another": 123},
    {"subtitle_emphasis_style": None},
    {"subtitle_emphasis_style": 12345},
    {"subtitle_emphasis_style": []},
    {"subtitle_emphasis_style": "ultra_heavy"},
    {"source_knowledge_ids": "not_a_list"},
])
def test_never_raises_on_garbage_input(bad_input):
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    # Must not raise under any circumstances
    cfg = build_ai_subtitle_emphasis_config(bad_input)
    assert isinstance(cfg.applied, bool)


# ---------------------------------------------------------------------------
# to_dict() has all required keys
# ---------------------------------------------------------------------------

def test_to_dict_has_all_required_keys():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": "strong"})
    d = cfg.to_dict()
    required_keys = {
        "enabled", "emphasis_style", "source_knowledge_ids",
        "applied", "rejected_reason", "validation_fixups",
    }
    assert required_keys.issubset(d.keys())


def test_to_dict_applied_false_has_all_keys():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config(None)
    d = cfg.to_dict()
    required_keys = {
        "enabled", "emphasis_style", "source_knowledge_ids",
        "applied", "rejected_reason", "validation_fixups",
    }
    assert required_keys.issubset(d.keys())


# ---------------------------------------------------------------------------
# Default construction
# ---------------------------------------------------------------------------

def test_default_construction():
    from app.ai.subtitle_hints import AISubtitleEmphasisConfig
    cfg = AISubtitleEmphasisConfig()
    assert cfg.enabled is False
    assert cfg.emphasis_style is None
    assert cfg.source_knowledge_ids == []
    assert cfg.applied is False
    assert cfg.rejected_reason is None
    assert cfg.validation_fixups == []


# ---------------------------------------------------------------------------
# enabled flag
# ---------------------------------------------------------------------------

def test_enabled_true_when_hints_present():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config({"subtitle_emphasis_style": "strong"})
    assert cfg.enabled is True


def test_enabled_false_when_none():
    from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config
    cfg = build_ai_subtitle_emphasis_config(None)
    assert cfg.enabled is False
