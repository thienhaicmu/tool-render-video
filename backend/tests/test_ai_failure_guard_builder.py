"""Tests for CreatorContextBuilder — Sacred Contract #3 (AI modules return None on failure).

Covers the builder-level exception handling that wraps the DB layer,
complementing the provider-level tests in test_sacred_contract_3_ai_return_none.py.
"""
import pytest
from unittest.mock import MagicMock

from app.domain.creator_context import CreatorContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patched_build(monkeypatch, side_effect):
    """Patch app.db.creator_repo.get_creator_context with a callable."""
    monkeypatch.setattr(
        "app.db.creator_repo.get_creator_context",
        side_effect,
    )
    from app.features.render.ai.context import builder as _builder_mod
    import importlib
    importlib.reload(_builder_mod)
    return _builder_mod.CreatorContextBuilder()


# ---------------------------------------------------------------------------
# CreatorContextBuilder.build() — exception / empty / valid paths
# ---------------------------------------------------------------------------

def test_creator_context_builder_db_failure_returns_none(monkeypatch):
    """build() returns None when DB raises — Sacred Contract #3."""
    def _raise():
        raise RuntimeError("DB boom")

    monkeypatch.setattr("app.db.creator_repo.get_creator_context", _raise)
    from app.features.render.ai.context.builder import CreatorContextBuilder
    assert CreatorContextBuilder().build() is None


def test_creator_context_builder_empty_context_returns_none(monkeypatch):
    """build() returns None when the persisted context is_empty()."""
    monkeypatch.setattr(
        "app.db.creator_repo.get_creator_context",
        lambda: CreatorContext(),  # default-constructed → is_empty() True
    )
    from app.features.render.ai.context.builder import CreatorContextBuilder
    assert CreatorContextBuilder().build() is None


def test_creator_context_builder_valid_returns_context(monkeypatch):
    """build() returns the context when it has real editorial information."""
    ctx = CreatorContext(channel_name="Test Channel", brand_voice="viral")
    monkeypatch.setattr(
        "app.db.creator_repo.get_creator_context",
        lambda: ctx,
    )
    from app.features.render.ai.context.builder import CreatorContextBuilder
    result = CreatorContextBuilder().build()
    assert result is not None
    assert result.channel_name == "Test Channel"


def test_build_creator_context_convenience_wrapper_returns_none_on_failure(monkeypatch):
    """Module-level build_creator_context() returns None when DB raises."""
    def _raise():
        raise RuntimeError("DB boom")

    monkeypatch.setattr("app.db.creator_repo.get_creator_context", _raise)
    from app.features.render.ai.context.builder import build_creator_context
    assert build_creator_context() is None
