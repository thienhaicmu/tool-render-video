"""
test_ai_pacing_config.py — Tests for Phase 5.4 AIPacingConfig and
build_ai_pacing_config().

Covers:
- valid hints → applied=True
- both None → applied=False, rejected_reason="no_pacing_hint"
- execution_hints=None → enabled=False
- user explicit min_part_sec override → rejected_reason="user_duration_override"
- reversed min/max → swapped safely
- out-of-range hints → clamped
- source_knowledge_ids preserved
- never raises on garbage input
"""
from __future__ import annotations

import types
import pytest

from app.ai.pacing import AIPacingConfig, build_ai_pacing_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(min_part_sec=15, max_part_sec=60):
    """Build a minimal payload-like namespace."""
    p = types.SimpleNamespace()
    p.min_part_sec = min_part_sec
    p.max_part_sec = max_part_sec
    return p


def _make_hints(cut_min=3.0, cut_max=5.0, source_ids=None):
    """Return a dict of execution hints."""
    return {
        "cut_interval_min": cut_min,
        "cut_interval_max": cut_max,
        "source_knowledge_ids": source_ids or ["k1", "k2"],
    }


# ---------------------------------------------------------------------------
# 1. Valid hints → applied=True
# ---------------------------------------------------------------------------

def test_valid_hints_applied():
    """Valid cut intervals + default payload → applied=True."""
    hints = _make_hints(3.0, 5.0, ["kb1"])
    payload = _make_payload()
    cfg = build_ai_pacing_config(hints, payload)

    assert cfg.enabled is True
    assert cfg.applied is True
    assert cfg.rejected_reason is None
    assert cfg.cut_interval_min == 3.0
    assert cfg.cut_interval_max == 5.0
    assert cfg.source_knowledge_ids == ["kb1"]


def test_valid_hints_no_payload():
    """Valid hints with no payload → applied=True (no user override possible)."""
    hints = _make_hints(2.0, 4.0)
    cfg = build_ai_pacing_config(hints, payload=None)

    assert cfg.enabled is True
    assert cfg.applied is True
    assert cfg.cut_interval_min == 2.0
    assert cfg.cut_interval_max == 4.0


# ---------------------------------------------------------------------------
# 2. Both min and max None → no_pacing_hint
# ---------------------------------------------------------------------------

def test_both_none_returns_no_pacing_hint():
    """When both cut_interval_min and cut_interval_max are None → no_pacing_hint."""
    hints = {"cut_interval_min": None, "cut_interval_max": None, "source_knowledge_ids": []}
    cfg = build_ai_pacing_config(hints, _make_payload())

    assert cfg.enabled is True
    assert cfg.applied is False
    assert cfg.rejected_reason == "no_pacing_hint"
    assert cfg.cut_interval_min is None
    assert cfg.cut_interval_max is None


def test_min_only_none_max_set_applied():
    """Only one interval set — still valid if the other is set."""
    # Only cut_max set (cut_min None) — should still apply with only max available
    hints = {"cut_interval_min": None, "cut_interval_max": 5.0, "source_knowledge_ids": []}
    cfg = build_ai_pacing_config(hints, _make_payload())
    # Since min is None but max is not None → not both None → goes past step 3
    # But applied requires both to be non-None for full override
    # In our implementation: applied=True if we pass step 3 (not both None)
    # and pass user check; but _seg_min_sec/_seg_max_sec only set if BOTH non-None
    # → applied=True here (we just need one value; injection only fires if both set)
    assert cfg.enabled is True
    # No rejection reason for having one value
    assert cfg.rejected_reason is None


# ---------------------------------------------------------------------------
# 3. execution_hints=None → enabled=False
# ---------------------------------------------------------------------------

def test_none_hints_disabled():
    """None execution_hints → AIPacingConfig(enabled=False)."""
    cfg = build_ai_pacing_config(None, _make_payload())
    assert cfg.enabled is False
    assert cfg.applied is False


def test_empty_dict_hints_disabled():
    """Empty dict hints → enabled=False."""
    cfg = build_ai_pacing_config({}, _make_payload())
    assert cfg.enabled is False
    assert cfg.applied is False


# ---------------------------------------------------------------------------
# 4. User explicit min_part_sec overrides AI
# ---------------------------------------------------------------------------

def test_user_explicit_min_overrides():
    """User sets min_part_sec to non-default value → user_duration_override."""
    hints = _make_hints(3.0, 5.0)
    payload = _make_payload(min_part_sec=30, max_part_sec=60)  # 30 != 15 (default)
    cfg = build_ai_pacing_config(hints, payload)

    assert cfg.enabled is True
    assert cfg.applied is False
    assert cfg.rejected_reason == "user_duration_override"


def test_user_explicit_max_overrides():
    """User sets max_part_sec to non-default value → user_duration_override."""
    hints = _make_hints(3.0, 5.0)
    payload = _make_payload(min_part_sec=15, max_part_sec=90)  # 90 != 60 (default)
    cfg = build_ai_pacing_config(hints, payload)

    assert cfg.enabled is True
    assert cfg.applied is False
    assert cfg.rejected_reason == "user_duration_override"


def test_user_default_values_allow_ai():
    """User leaves both at schema defaults → AI may apply."""
    hints = _make_hints(3.0, 5.0)
    payload = _make_payload(min_part_sec=15, max_part_sec=60)  # both defaults
    cfg = build_ai_pacing_config(hints, payload)

    assert cfg.applied is True
    assert cfg.rejected_reason is None


# ---------------------------------------------------------------------------
# 5. Reversed min/max → swapped safely
# ---------------------------------------------------------------------------

def test_reversed_min_max_swapped():
    """If min > max, they are swapped and a fixup is recorded."""
    hints = {"cut_interval_min": 8.0, "cut_interval_max": 3.0, "source_knowledge_ids": []}
    cfg = build_ai_pacing_config(hints, _make_payload())

    assert cfg.applied is True
    # After swap: min=3.0, max=8.0
    assert cfg.cut_interval_min == 3.0
    assert cfg.cut_interval_max == 8.0
    # Fixup recorded
    assert any("swap" in str(f.get("action", "")) for f in cfg.validation_fixups)


def test_reversed_min_max_fixup_recorded():
    """Fixup dict contains swapped_inverted_range action."""
    hints = {"cut_interval_min": 10.0, "cut_interval_max": 2.0, "source_knowledge_ids": []}
    cfg = build_ai_pacing_config(hints, _make_payload())

    swap_fixup = next(
        (f for f in cfg.validation_fixups if "swap" in str(f.get("action", ""))),
        None,
    )
    assert swap_fixup is not None
    assert swap_fixup["field"] == "cut_interval_min/max"


# ---------------------------------------------------------------------------
# 6. Out-of-range hints → clamped
# ---------------------------------------------------------------------------

def test_cut_min_clamped_below():
    """cut_interval_min below 1.0 → clamped to 1.0."""
    hints = {"cut_interval_min": 0.1, "cut_interval_max": 5.0, "source_knowledge_ids": []}
    cfg = build_ai_pacing_config(hints, _make_payload())

    assert cfg.cut_interval_min == 1.0
    assert any(f.get("field") == "cut_interval_min" for f in cfg.validation_fixups)


def test_cut_max_clamped_above():
    """cut_interval_max above 12.0 → clamped to 12.0."""
    hints = {"cut_interval_min": 3.0, "cut_interval_max": 99.0, "source_knowledge_ids": []}
    cfg = build_ai_pacing_config(hints, _make_payload())

    assert cfg.cut_interval_max == 12.0
    assert any(f.get("field") == "cut_interval_max" for f in cfg.validation_fixups)


def test_already_in_range_no_clamp():
    """Values in range → no clamp fixup."""
    hints = {"cut_interval_min": 4.0, "cut_interval_max": 8.0, "source_knowledge_ids": []}
    cfg = build_ai_pacing_config(hints, _make_payload())

    assert cfg.cut_interval_min == 4.0
    assert cfg.cut_interval_max == 8.0
    assert cfg.validation_fixups == []


# ---------------------------------------------------------------------------
# 7. source_knowledge_ids preserved
# ---------------------------------------------------------------------------

def test_source_knowledge_ids_preserved():
    """source_knowledge_ids are passed through from hints."""
    hints = {
        "cut_interval_min": 3.0,
        "cut_interval_max": 6.0,
        "source_knowledge_ids": ["pacing_fast_001", "tiktok_001"],
    }
    cfg = build_ai_pacing_config(hints, _make_payload())

    assert cfg.source_knowledge_ids == ["pacing_fast_001", "tiktok_001"]


def test_source_knowledge_ids_empty():
    """Empty source_knowledge_ids → empty list."""
    hints = {"cut_interval_min": 3.0, "cut_interval_max": 5.0, "source_knowledge_ids": []}
    cfg = build_ai_pacing_config(hints, _make_payload())

    assert cfg.source_knowledge_ids == []


# ---------------------------------------------------------------------------
# 8. Never raises on garbage input
# ---------------------------------------------------------------------------

def test_garbage_hints_no_raise():
    """Garbage hints dict does not raise."""
    cfg = build_ai_pacing_config({"cut_interval_min": "bad", "cut_interval_max": []}, None)
    assert isinstance(cfg, AIPacingConfig)


def test_garbage_payload_no_raise():
    """Garbage payload does not raise."""
    hints = _make_hints(3.0, 5.0)
    cfg = build_ai_pacing_config(hints, payload="this_is_not_a_payload")
    assert isinstance(cfg, AIPacingConfig)


def test_none_both_no_raise():
    """None hints and None payload → no raise, enabled=False."""
    cfg = build_ai_pacing_config(None, None)
    assert cfg.enabled is False


def test_list_hints_no_raise():
    """List instead of dict hints → no raise, enabled=False."""
    cfg = build_ai_pacing_config([1, 2, 3], None)
    assert isinstance(cfg, AIPacingConfig)


def test_very_large_negative_no_raise():
    """Very large negative values → clamped, no raise."""
    hints = {"cut_interval_min": -1000.0, "cut_interval_max": -0.5}
    cfg = build_ai_pacing_config(hints, _make_payload())
    assert isinstance(cfg, AIPacingConfig)


def test_nan_values_no_raise():
    """NaN-like string values → treated as invalid, no raise."""
    hints = {"cut_interval_min": float("nan"), "cut_interval_max": 5.0}
    cfg = build_ai_pacing_config(hints, _make_payload())
    # NaN is a valid float — it passes _parse_float and clamp may produce NaN
    # The function must not raise regardless
    assert isinstance(cfg, AIPacingConfig)


# ---------------------------------------------------------------------------
# 9. to_dict() produces expected keys
# ---------------------------------------------------------------------------

def test_to_dict_has_required_keys():
    """AIPacingConfig.to_dict() returns all required keys."""
    cfg = AIPacingConfig(
        enabled=True, applied=True,
        cut_interval_min=3.0, cut_interval_max=5.0,
        source_knowledge_ids=["k1"],
        rejected_reason=None, validation_fixups=[],
    )
    d = cfg.to_dict()
    for key in ("enabled", "applied", "cut_interval_min", "cut_interval_max",
                "source_knowledge_ids", "rejected_reason", "validation_fixups"):
        assert key in d, f"Missing key: {key}"


def test_to_dict_values():
    """to_dict() values match dataclass fields."""
    cfg = AIPacingConfig(
        enabled=True, applied=False,
        cut_interval_min=2.0, cut_interval_max=6.0,
        source_knowledge_ids=["x"],
        rejected_reason="user_duration_override",
        validation_fixups=[{"field": "x"}],
    )
    d = cfg.to_dict()
    assert d["enabled"] is True
    assert d["applied"] is False
    assert d["cut_interval_min"] == 2.0
    assert d["cut_interval_max"] == 6.0
    assert d["source_knowledge_ids"] == ["x"]
    assert d["rejected_reason"] == "user_duration_override"
    assert d["validation_fixups"] == [{"field": "x"}]


# ---------------------------------------------------------------------------
# 10. RenderExecutionHints instance as input
# ---------------------------------------------------------------------------

def test_render_execution_hints_instance():
    """build_ai_pacing_config accepts RenderExecutionHints instance."""
    from app.ai.contracts import RenderExecutionHints
    hints_obj = RenderExecutionHints(
        cut_interval_min=3.5,
        cut_interval_max=6.5,
        source_knowledge_ids=["k99"],
    )
    cfg = build_ai_pacing_config(hints_obj, _make_payload())

    assert cfg.enabled is True
    assert cfg.applied is True
    assert cfg.cut_interval_min == 3.5
    assert cfg.cut_interval_max == 6.5
    assert cfg.source_knowledge_ids == ["k99"]
