"""Sprint 6 P1 N.2 — H3 quality fix from the Whisper defer audit.

Pins:
- When SUBTITLE_PER_PART_MODEL env var is unset, the per-part Whisper model
  defaults to ctx.tuned["whisper_model"] (the source-level model the render
  profile resolved to).
- When SUBTITLE_PER_PART_MODEL is set explicitly, that wins (user override
  preserved — Sacred Contract #2 backward-compat).
- Defensive fallback to "small" if ctx.tuned dict is missing the key.

The per-part Whisper call itself is NOT removed (per the Whisper defer
audit at docs/review/SPRINT_6_P1_WHISPER_DEFER_2026-06-05.md). Only the
DEFAULT model is lifted from the historical hard-coded "small" to the
profile-resolved value, so users on quality/best profiles don't silently
get per-part subtitles capped below their source-level SRT.

The pin lives at the env-var resolution layer rather than at the
transcribe_with_adapter call site so we can verify the contract without
having to construct a full PartRenderContext + RenderPreflightResult
fixture (which the asset planner integration tests do via heavier
setup). The N.2 change is a 4-line patch to a single line; this test
asserts the patch's semantics directly.
"""
from __future__ import annotations

import os
from unittest.mock import patch


def _resolve_per_part_model(tuned: dict, env: dict | None = None) -> str:
    """Mirror of the production resolution at part_asset_planner.py:206.

    Kept in the test rather than imported from the production module so the
    test fails informatively if the production line drifts away from the
    documented N.2 semantics — the source-pin test in
    test_module_source_invariants below catches that drift.
    """
    if env is None:
        env = os.environ
    return env.get("SUBTITLE_PER_PART_MODEL", tuned.get("whisper_model", "small"))


# ---------------------------------------------------------------------------
# Section 1: profile-driven default (the N.2 fix proper)
# ---------------------------------------------------------------------------


class TestPerPartModelDefaultsToSourceLevel:
    def test_fast_profile_defaults_to_base(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUBTITLE_PER_PART_MODEL", None)
            model = _resolve_per_part_model({"whisper_model": "base"})
        assert model == "base"

    def test_balanced_profile_defaults_to_small(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUBTITLE_PER_PART_MODEL", None)
            model = _resolve_per_part_model({"whisper_model": "small"})
        assert model == "small"

    def test_quality_profile_defaults_to_large_v3(self):
        """The H3 irony case — before N.2 this was capped at 'small'."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUBTITLE_PER_PART_MODEL", None)
            model = _resolve_per_part_model({"whisper_model": "large-v3"})
        assert model == "large-v3"

    def test_best_profile_defaults_to_large_v3(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUBTITLE_PER_PART_MODEL", None)
            model = _resolve_per_part_model({"whisper_model": "large-v3"})
        assert model == "large-v3"


# ---------------------------------------------------------------------------
# Section 2: explicit env var still wins (Sacred Contract #2 backward-compat)
# ---------------------------------------------------------------------------


class TestExplicitEnvVarWinsOverProfileDefault:
    def test_explicit_small_overrides_quality_profile(self):
        with patch.dict(os.environ, {"SUBTITLE_PER_PART_MODEL": "small"}):
            model = _resolve_per_part_model({"whisper_model": "large-v3"})
        assert model == "small"

    def test_explicit_tiny_overrides_balanced_profile(self):
        with patch.dict(os.environ, {"SUBTITLE_PER_PART_MODEL": "tiny"}):
            model = _resolve_per_part_model({"whisper_model": "small"})
        assert model == "tiny"

    def test_explicit_large_v3_overrides_fast_profile(self):
        with patch.dict(os.environ, {"SUBTITLE_PER_PART_MODEL": "large-v3"}):
            model = _resolve_per_part_model({"whisper_model": "base"})
        assert model == "large-v3"


# ---------------------------------------------------------------------------
# Section 3: defensive fallback when tuned dict is missing the key
# ---------------------------------------------------------------------------


class TestDefensiveFallback:
    def test_empty_tuned_dict_falls_back_to_small(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUBTITLE_PER_PART_MODEL", None)
            model = _resolve_per_part_model({})
        assert model == "small"

    def test_tuned_dict_with_other_keys_falls_back_to_small(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SUBTITLE_PER_PART_MODEL", None)
            # Real ctx.tuned has video_preset, video_crf, transition_sec too.
            # If whisper_model is missing for any reason, we don't crash.
            model = _resolve_per_part_model({"video_preset": "slow", "video_crf": 15})
        assert model == "small"


# ---------------------------------------------------------------------------
# Section 4: source pin — the production line still matches our test mirror
# ---------------------------------------------------------------------------


class TestModuleSourceInvariants:
    """Sentinel pins on the production source to catch the case where a
    future edit changes part_asset_planner.py:206 in a way that drifts away
    from the N.2 contract — without updating this test."""

    def test_per_part_model_resolves_via_env_var_then_tuned(self):
        import inspect
        from app.orchestration.stages import part_asset_planner
        src = inspect.getsource(part_asset_planner)
        # SUBTITLE_PER_PART_MODEL must still be the explicit env-var override
        # (the existing PIN at tests/test_phase0_hotfixes.py:77 also pins
        # this string — duplicating here is intentional, see N.2 commit
        # message).
        assert 'SUBTITLE_PER_PART_MODEL' in src
        # The production code must read whisper_model from ctx.tuned as
        # the default — drift away from this is the H3 regression coming
        # back.
        assert 'ctx.tuned.get("whisper_model"' in src, (
            'Sprint 6 P1 N.2 contract broken: per-part Whisper model no '
            'longer defaults to ctx.tuned["whisper_model"] — the H3 quality '
            'regression has likely been reintroduced.'
        )
