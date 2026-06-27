"""Tests for rewrite_subtitle dispatcher — provider routing + fallback chain + Sacred #3."""
import pytest


_KW = dict(
    text="Hello world",
    target_duration_sec=10.0,
    target_language="en-US",
    tone="",
    api_key="fake",
    model=None,
)


def test_dispatch_to_named_provider(monkeypatch):
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: "REWRITTEN-GEMINI",
    )
    from app.features.render.ai.llm.rewrite import rewrite_subtitle
    out = rewrite_subtitle(provider="gemini", **_KW)
    assert out == "REWRITTEN-GEMINI"


def test_unknown_provider_falls_to_gemini(monkeypatch):
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: "REWRITTEN",
    )
    from app.features.render.ai.llm.rewrite import rewrite_subtitle
    assert rewrite_subtitle(provider="bogus", **_KW) == "REWRITTEN"


def test_fallback_chain_enabled(monkeypatch):
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", True)
    call_log = []

    def _gemini(**kw):
        call_log.append("gemini")
        return None

    def _openai(**kw):
        call_log.append("openai")
        return "OK"

    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle", _gemini,
    )
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.openai.rewrite_subtitle", _openai,
    )
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    assert out == "OK"
    assert call_log == ["gemini", "openai"]


def test_fallback_disabled_returns_primary_only(monkeypatch):
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", False)
    call_log = []

    def _gemini(**kw):
        call_log.append("gemini")
        return None

    def _openai(**kw):
        call_log.append("openai")
        return "OK"

    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle", _gemini,
    )
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.openai.rewrite_subtitle", _openai,
    )
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    assert out is None
    assert call_log == ["gemini"]


def test_all_providers_return_none(monkeypatch):
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", True)
    for p in ("gemini", "openai", "claude"):
        monkeypatch.setattr(
            f"app.features.render.ai.llm.providers.{p}.rewrite_subtitle",
            lambda **kw: None,
        )
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    assert out is None


def test_provider_callable_returning_none_does_not_raise(monkeypatch):
    # Sacred #3 spirit at the dispatcher boundary: a provider that returns
    # None instead of raising must surface as None (and trigger fallback if
    # enabled), never propagate as an exception.
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", False)
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: None,
    )
    # Must not raise:
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    assert out is None
