"""Tests for rewrite_subtitle dispatcher — v2 segmented return type."""
import pytest


_KW = dict(
    srt_segmented="[0.0 - 5.0] Hello world",
    clip_duration_sec=5.0,
    target_language="en-US",
    tone="",
    api_key="fake",
    model=None,
)

_SAMPLE_SEGMENTS = [{"start": 0.0, "end": 5.0, "text": "Xin chào"}]


def test_dispatch_to_named_provider(monkeypatch):
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: _SAMPLE_SEGMENTS,
    )
    from app.features.render.ai.llm.rewrite import rewrite_subtitle
    out = rewrite_subtitle(provider="gemini", **_KW)
    assert out == _SAMPLE_SEGMENTS


def test_unknown_provider_falls_to_gemini(monkeypatch):
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: _SAMPLE_SEGMENTS,
    )
    from app.features.render.ai.llm.rewrite import rewrite_subtitle
    assert rewrite_subtitle(provider="bogus", **_KW) == _SAMPLE_SEGMENTS


def test_fallback_chain_enabled(monkeypatch):
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", True)
    call_log = []

    def _gemini(**kw):
        call_log.append("gemini")
        return None

    def _openai(**kw):
        call_log.append("openai")
        return _SAMPLE_SEGMENTS

    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle", _gemini,
    )
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.openai.rewrite_subtitle", _openai,
    )
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    assert out == _SAMPLE_SEGMENTS
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
        return _SAMPLE_SEGMENTS

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


def test_provider_returning_none_does_not_raise(monkeypatch):
    import app.features.render.ai.llm.rewrite as rewrite_mod
    monkeypatch.setattr(rewrite_mod, "_LLM_FALLBACK_ENABLED", False)
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: None,
    )
    out = rewrite_mod.rewrite_subtitle(provider="gemini", **_KW)
    assert out is None


def test_dispatcher_returns_list_of_dicts(monkeypatch):
    """v2 contract: return type is list[dict] with start/end/text keys."""
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.rewrite_subtitle",
        lambda **kw: _SAMPLE_SEGMENTS,
    )
    from app.features.render.ai.llm.rewrite import rewrite_subtitle
    out = rewrite_subtitle(provider="gemini", **_KW)
    assert isinstance(out, list)
    assert all(isinstance(s, dict) for s in out)
    assert all({"start", "end", "text"} <= set(s.keys()) for s in out)
