"""Architecture-review Batch D-3a (2026-06-30) — unified transcript cap.

Pins the contract of ``resolve_provider_max_srt_chars``:

  1. No env vars set → returns ``provider_default`` byte-for-byte
     (Sacred Contract #2 spirit — historical behaviour preserved).
  2. Only ``LLM_MAX_SRT_CHARS`` set → applied uniformly to every provider
     (global parity knob).
  3. Per-provider ``<PROVIDER>_MAX_SRT_CHARS`` wins over the global
     ``LLM_MAX_SRT_CHARS`` (highest specificity).
  4. Malformed env values fall through to the next priority level
     without raising — never crash a render on a bad env value.
  5. Empty-string env vars are treated as unset (defensive parsing).
"""
from __future__ import annotations

import pytest

from app.features.render.ai.llm.prompts import resolve_provider_max_srt_chars

_PROVIDER_DEFAULTS = {
    "CLAUDE_MAX_SRT_CHARS": 50000,
    "GEMINI_MAX_SRT_CHARS": 60000,
    "OPENAI_MAX_SRT_CHARS": 30000,
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip every transcript-cap env var so each test starts from the
    'no env vars set' baseline."""
    for key in ("LLM_MAX_SRT_CHARS", *_PROVIDER_DEFAULTS.keys()):
        monkeypatch.delenv(key, raising=False)
    yield


# ---------------------------------------------------------------------------
# Priority 3 — hardcoded default applies when no env var is set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_env,default", list(_PROVIDER_DEFAULTS.items()))
def test_returns_provider_default_when_no_env(provider_env, default):
    """Sacred Contract #2 spirit — bit-identical to pre-D-3 behaviour."""
    assert resolve_provider_max_srt_chars(default, provider_env) == default


# ---------------------------------------------------------------------------
# Priority 2 — LLM_MAX_SRT_CHARS supersedes the default for every provider
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider_env,default", list(_PROVIDER_DEFAULTS.items()))
def test_global_env_overrides_default(monkeypatch, provider_env, default):
    """Operators set LLM_MAX_SRT_CHARS once to align all three providers."""
    monkeypatch.setenv("LLM_MAX_SRT_CHARS", "80000")
    assert resolve_provider_max_srt_chars(default, provider_env) == 80000


def test_global_env_applies_uniformly_across_providers(monkeypatch):
    monkeypatch.setenv("LLM_MAX_SRT_CHARS", "45000")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 45000
    assert resolve_provider_max_srt_chars(60000, "GEMINI_MAX_SRT_CHARS") == 45000
    assert resolve_provider_max_srt_chars(30000, "OPENAI_MAX_SRT_CHARS") == 45000


# ---------------------------------------------------------------------------
# Priority 1 — per-provider env wins over the global one
# ---------------------------------------------------------------------------


def test_per_provider_env_wins_over_global(monkeypatch):
    monkeypatch.setenv("LLM_MAX_SRT_CHARS", "80000")
    monkeypatch.setenv("CLAUDE_MAX_SRT_CHARS", "40000")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 40000
    # The other providers still see the global value.
    assert resolve_provider_max_srt_chars(60000, "GEMINI_MAX_SRT_CHARS") == 80000


def test_each_provider_can_have_its_own_override_independently(monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_SRT_CHARS", "11111")
    monkeypatch.setenv("GEMINI_MAX_SRT_CHARS", "22222")
    monkeypatch.setenv("OPENAI_MAX_SRT_CHARS", "33333")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 11111
    assert resolve_provider_max_srt_chars(60000, "GEMINI_MAX_SRT_CHARS") == 22222
    assert resolve_provider_max_srt_chars(30000, "OPENAI_MAX_SRT_CHARS") == 33333


# ---------------------------------------------------------------------------
# Defensive — malformed env values fall through, never raise
# ---------------------------------------------------------------------------


def test_malformed_per_provider_falls_through_to_global(monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_SRT_CHARS", "garbage")
    monkeypatch.setenv("LLM_MAX_SRT_CHARS", "70000")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 70000


def test_malformed_global_falls_through_to_default(monkeypatch):
    monkeypatch.setenv("LLM_MAX_SRT_CHARS", "also-garbage")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 50000


def test_both_malformed_falls_through_to_default(monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_SRT_CHARS", "garbage")
    monkeypatch.setenv("LLM_MAX_SRT_CHARS", "more-garbage")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 50000


def test_negative_values_are_accepted_passthrough(monkeypatch):
    """Operators who set a negative value get what they asked for — the
    helper does not silently clamp. The downstream prompt builder would
    treat it as an effective no-truncation request."""
    monkeypatch.setenv("LLM_MAX_SRT_CHARS", "-1")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == -1


def test_empty_string_env_treated_as_unset(monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_SRT_CHARS", "")
    monkeypatch.setenv("LLM_MAX_SRT_CHARS", "")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 50000


def test_whitespace_only_env_treated_as_unset(monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_SRT_CHARS", "   ")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 50000


def test_whitespace_around_value_is_trimmed(monkeypatch):
    monkeypatch.setenv("CLAUDE_MAX_SRT_CHARS", "  40000  ")
    assert resolve_provider_max_srt_chars(50000, "CLAUDE_MAX_SRT_CHARS") == 40000


# ---------------------------------------------------------------------------
# Provider modules pick up the resolver at import time
# ---------------------------------------------------------------------------


def test_claude_module_uses_resolver_at_import():
    """Spot-check: the provider module's module-level _MAX_SRT_CHARS is a
    plain int (not a getenv() result) and matches what the resolver
    produces for the canonical (default=50000, env='CLAUDE_MAX_SRT_CHARS')
    pair in this test's clean-env state."""
    from app.features.render.ai.llm.providers import claude as _c
    assert isinstance(_c._MAX_SRT_CHARS, int)
    # Module was imported under whatever env existed at import time; here
    # we only assert it's an int — the resolver semantics are exhaustively
    # covered by the unit tests above.
