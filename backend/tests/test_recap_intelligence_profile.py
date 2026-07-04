"""Tests for RECAP_INTELLIGENCE_PROFILE (2026-07-04 architecture-review upgrade).

The profile collapses six recap Story-Intelligence env flags into one dial
(basic | standard | max) WITHOUT changing default behaviour: with no profile and
no individual override, every flag resolves byte-identically to its pre-profile
default. Individual env vars always override the profile.
"""
from __future__ import annotations

import importlib

import pytest

from app.features.render.ai.llm.recap_profile import recap_flag, active_profile

_FLAGS = (
    "RECAP_TWO_PASS", "RECAP_EDITORIAL_PASS", "STORY_INTELLIGENCE_HOIST_ENABLED",
    "RECAP_SNAP_TO_SHOTS_ENABLED", "RECAP_TRIM_TO_BAND", "RECAP_PER_EPISODE_NARRATION",
)

# Pre-profile hard defaults (the shipped behaviour before this module existed).
_LEGACY = {
    "RECAP_TWO_PASS": True,
    "RECAP_EDITORIAL_PASS": False,
    "STORY_INTELLIGENCE_HOIST_ENABLED": True,
    "RECAP_SNAP_TO_SHOTS_ENABLED": True,
    "RECAP_TRIM_TO_BAND": True,
    "RECAP_PER_EPISODE_NARRATION": False,
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for f in (*_FLAGS, "RECAP_INTELLIGENCE_PROFILE"):
        monkeypatch.delenv(f, raising=False)
    yield


def test_no_profile_is_legacy_default():
    assert active_profile() == ""
    for f in _FLAGS:
        assert recap_flag(f) is _LEGACY[f], f


def test_standard_profile_equals_legacy(monkeypatch):
    monkeypatch.setenv("RECAP_INTELLIGENCE_PROFILE", "standard")
    for f in _FLAGS:
        assert recap_flag(f) is _LEGACY[f], f


def test_basic_profile_reduces_llm_but_keeps_guards(monkeypatch):
    monkeypatch.setenv("RECAP_INTELLIGENCE_PROFILE", "basic")
    assert recap_flag("RECAP_TWO_PASS") is False
    assert recap_flag("STORY_INTELLIGENCE_HOIST_ENABLED") is False
    assert recap_flag("RECAP_EDITORIAL_PASS") is False
    # Deterministic guards stay ON — cheap + always improve output.
    assert recap_flag("RECAP_SNAP_TO_SHOTS_ENABLED") is True
    assert recap_flag("RECAP_TRIM_TO_BAND") is True


def test_max_profile_enables_all_passes(monkeypatch):
    monkeypatch.setenv("RECAP_INTELLIGENCE_PROFILE", "max")
    assert recap_flag("RECAP_EDITORIAL_PASS") is True
    assert recap_flag("RECAP_PER_EPISODE_NARRATION") is True
    assert recap_flag("RECAP_TWO_PASS") is True


def test_individual_env_overrides_profile(monkeypatch):
    monkeypatch.setenv("RECAP_INTELLIGENCE_PROFILE", "basic")
    monkeypatch.setenv("RECAP_TWO_PASS", "1")
    assert recap_flag("RECAP_TWO_PASS") is True  # explicit env beats the profile


def test_unknown_profile_falls_back_to_legacy(monkeypatch):
    monkeypatch.setenv("RECAP_INTELLIGENCE_PROFILE", "bogus")
    assert active_profile() == ""
    for f in _FLAGS:
        assert recap_flag(f) is _LEGACY[f], f


def test_unrecognised_env_value_falls_through(monkeypatch):
    monkeypatch.setenv("RECAP_TWO_PASS", "maybe")
    # not a recognised truthy/falsy → hard default (True)
    assert recap_flag("RECAP_TWO_PASS") is True


def test_comprehension_stage_reads_profile(monkeypatch):
    """is_hoist_enabled must reflect the profile (basic → hoist OFF)."""
    import app.features.render.engine.pipeline.comprehension_stage as cs
    importlib.reload(cs)
    monkeypatch.setenv("RECAP_INTELLIGENCE_PROFILE", "basic")
    assert cs.is_hoist_enabled() is False
    monkeypatch.setenv("RECAP_INTELLIGENCE_PROFILE", "standard")
    assert cs.is_hoist_enabled() is True
