"""Tests for multi-provider LLM fallback chain — Sprint C-1.

Verifies LLM_FALLBACK_ENABLED=1 behavior:
- Disabled (default): only the primary provider is called.
- Enabled, primary returns None: next provider in SUPPORTED_PROVIDERS is tried.
- Enabled, all return None: select_render_plan returns None.
- Enabled, secondary succeeds: its plan is returned.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _no_disabled_providers(monkeypatch):
    """Keep the fallback-chain tests hermetic: a repo .env that locks
    openai/claude (LLM_DISABLED_PROVIDERS) must not leak in and remove them
    from the chain these tests exercise."""
    monkeypatch.delenv("LLM_DISABLED_PROVIDERS", raising=False)
    yield


_SRT = "1\n00:00:01,000 --> 00:00:02,000\nHello world"
_CALL_KWARGS = dict(
    srt_content=_SRT,
    output_count=1,
    min_sec=5.0,
    max_sec=60.0,
    video_duration=120.0,
)


# ---------------------------------------------------------------------------
# Fallback disabled (default) — only primary called
# ---------------------------------------------------------------------------

def test_fallback_disabled_primary_only(monkeypatch):
    """When LLM_FALLBACK_ENABLED is False (default), only the primary provider is invoked."""
    import app.features.render.ai.llm as llm_mod
    monkeypatch.setattr(llm_mod, "_LLM_FALLBACK_ENABLED", False)

    call_log: list[str] = []

    def _gemini(**_kw):
        call_log.append("gemini")
        return None  # returns None — but fallback is disabled so chain stops

    def _openai(**_kw):
        call_log.append("openai")
        return MagicMock()

    with patch("app.features.render.ai.llm.providers.gemini.select_render_plan", _gemini), \
         patch("app.features.render.ai.llm.providers.openai.select_render_plan", _openai):
        result = llm_mod.select_render_plan(provider="gemini", **_CALL_KWARGS)

    assert result is None
    assert call_log == ["gemini"], f"Only primary should be called, got {call_log}"


# ---------------------------------------------------------------------------
# Fallback enabled, primary returns None → secondary tried
# ---------------------------------------------------------------------------

def test_fallback_enabled_primary_returns_none_secondary_called(monkeypatch):
    """When fallback is enabled and primary returns None, the next provider is tried."""
    import app.features.render.ai.llm as llm_mod
    monkeypatch.setattr(llm_mod, "_LLM_FALLBACK_ENABLED", True)

    call_log: list[str] = []
    fake_plan = MagicMock()

    def _gemini(**_kw):
        call_log.append("gemini")
        return None

    def _openai(**_kw):
        call_log.append("openai")
        return fake_plan

    with patch("app.features.render.ai.llm.providers.gemini.select_render_plan", _gemini), \
         patch("app.features.render.ai.llm.providers.openai.select_render_plan", _openai):
        result = llm_mod.select_render_plan(provider="gemini", **_CALL_KWARGS)

    assert result is fake_plan
    assert "gemini" in call_log
    assert "openai" in call_log


# ---------------------------------------------------------------------------
# Fallback enabled, all providers return None → final result is None
# ---------------------------------------------------------------------------

def test_fallback_enabled_all_return_none(monkeypatch):
    """When fallback is enabled but every provider returns None, result is None."""
    import app.features.render.ai.llm as llm_mod
    monkeypatch.setattr(llm_mod, "_LLM_FALLBACK_ENABLED", True)

    with patch("app.features.render.ai.llm.providers.gemini.select_render_plan", lambda **_kw: None), \
         patch("app.features.render.ai.llm.providers.openai.select_render_plan", lambda **_kw: None), \
         patch("app.features.render.ai.llm.providers.claude.select_render_plan", lambda **_kw: None):
        result = llm_mod.select_render_plan(provider="gemini", **_CALL_KWARGS)

    assert result is None


# ---------------------------------------------------------------------------
# Fallback enabled, secondary succeeds → returns secondary plan
# ---------------------------------------------------------------------------

def test_fallback_enabled_secondary_succeeds(monkeypatch):
    """When primary fails and secondary succeeds, the secondary plan is returned."""
    import app.features.render.ai.llm as llm_mod
    monkeypatch.setattr(llm_mod, "_LLM_FALLBACK_ENABLED", True)

    fake_plan = MagicMock()

    with patch("app.features.render.ai.llm.providers.gemini.select_render_plan", lambda **_kw: None), \
         patch("app.features.render.ai.llm.providers.openai.select_render_plan", lambda **_kw: None), \
         patch("app.features.render.ai.llm.providers.claude.select_render_plan", lambda **_kw: fake_plan):
        result = llm_mod.select_render_plan(provider="gemini", **_CALL_KWARGS)

    assert result is fake_plan


# ---------------------------------------------------------------------------
# LLM_DISABLED_PROVIDERS locks providers out of the fallback chain
# ---------------------------------------------------------------------------

def test_disabled_providers_removed_from_chain(monkeypatch):
    """openai/claude locked via LLM_DISABLED_PROVIDERS are never called; only
    gemini runs even with fallback enabled."""
    import app.features.render.ai.llm as llm_mod
    monkeypatch.setattr(llm_mod, "_LLM_FALLBACK_ENABLED", True)
    monkeypatch.setenv("LLM_DISABLED_PROVIDERS", "openai,claude")

    call_log: list[str] = []

    def _mk(name):
        def _impl(**_kw):
            call_log.append(name)
            return None
        return _impl

    with patch("app.features.render.ai.llm.providers.gemini.select_render_plan", _mk("gemini")), \
         patch("app.features.render.ai.llm.providers.openai.select_render_plan", _mk("openai")), \
         patch("app.features.render.ai.llm.providers.claude.select_render_plan", _mk("claude")):
        result = llm_mod.select_render_plan(provider="gemini", **_CALL_KWARGS)

    assert result is None
    assert call_log == ["gemini"], f"Only gemini should run, got {call_log}"


def test_disabled_primary_falls_back_to_gemini(monkeypatch):
    """If the chosen primary is disabled, the chain never empties — it falls
    back to gemini so a render always has a provider."""
    import app.features.render.ai.llm as llm_mod
    monkeypatch.setattr(llm_mod, "_LLM_FALLBACK_ENABLED", True)
    monkeypatch.setenv("LLM_DISABLED_PROVIDERS", "openai,claude")
    assert llm_mod._provider_chain("openai") == ["gemini"]
    assert llm_mod._provider_chain("gemini") == ["gemini"]
