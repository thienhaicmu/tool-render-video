"""
Sprint 3.2 — pin the CreatorContextBuilder contract:

- build() returns None when no persisted context exists (cold path)
- build() returns None when the persisted context is empty (equivalent
  to none configured — AI prompt should skip the editorial hint)
- build() returns the dataclass when populated
- build() NEVER raises — Sacred Contract #3 is absolute for AI modules
- the module-level convenience wrapper resolves to the same behaviour
- _enrich is a passthrough in Sprint 3 (seam for Sprint 4 enrichment)
"""
from unittest import mock

import pytest

from app.ai.context.creator_context import (
    CreatorContextBuilder,
    build_creator_context,
)
from app.domain.creator_context import CreatorContext


class TestBuildReturnsNone:
    def test_returns_none_when_repo_has_no_context(self):
        builder = CreatorContextBuilder()
        with mock.patch.object(builder, "_fetch_persisted", return_value=None):
            assert builder.build() is None

    def test_returns_none_when_persisted_context_is_empty(self):
        """An empty CreatorContext is functionally equivalent to None —
        the builder normalises to None so the LLM pipeline can
        short-circuit cleanly."""
        builder = CreatorContextBuilder()
        with mock.patch.object(builder, "_fetch_persisted", return_value=CreatorContext()):
            assert builder.build() is None

    def test_returns_none_on_internal_exception(self):
        """Sacred Contract #3 — any internal raise is swallowed."""
        builder = CreatorContextBuilder()
        with mock.patch.object(builder, "_fetch_persisted", side_effect=RuntimeError("boom")):
            assert builder.build() is None


class TestBuildReturnsContext:
    def test_returns_persisted_context_when_populated(self):
        builder = CreatorContextBuilder()
        sentinel = CreatorContext(channel_name="K1", brand_voice="authentic")
        with mock.patch.object(builder, "_fetch_persisted", return_value=sentinel):
            result = builder.build()
        assert result is not None
        assert result.channel_name == "K1"
        assert result.brand_voice == "authentic"

    def test_enrich_is_passthrough_in_sprint_3(self):
        """Sprint 4 will mix in derived signals here. Sprint 3 pins
        that _enrich is currently a true identity function."""
        builder = CreatorContextBuilder()
        ctx_in = CreatorContext(channel_name="K1")
        ctx_out = builder._enrich(ctx_in)
        assert ctx_out is ctx_in  # same object — no copy, no mutation

    def test_build_calls_enrich_before_returning(self):
        """When the persisted context is non-empty, build() must route
        through _enrich. Sprint 4 readers depend on this so monkey-
        patching _enrich is enough to add new biases."""
        builder = CreatorContextBuilder()
        seeded = CreatorContext(channel_name="K1")
        enriched = CreatorContext(channel_name="K1-enriched")
        with mock.patch.object(builder, "_fetch_persisted", return_value=seeded), \
             mock.patch.object(builder, "_enrich", return_value=enriched) as m_enrich:
            result = builder.build()
        m_enrich.assert_called_once_with(seeded)
        assert result is enriched


class TestModuleLevelWrapper:
    def test_wrapper_delegates_to_builder(self):
        """build_creator_context() is a convenience wrapper around
        CreatorContextBuilder().build(). The pipeline imports this
        rather than the class so tests can monkeypatch the symbol on
        a single import path."""
        with mock.patch(
            "app.ai.context.creator_context.CreatorContextBuilder"
        ) as m_cls:
            m_inst = m_cls.return_value
            m_inst.build.return_value = CreatorContext(channel_name="K1")
            result = build_creator_context()
        assert result is not None
        assert result.channel_name == "K1"
        m_cls.assert_called_once_with()
        m_inst.build.assert_called_once_with()


class TestRealFetchIntegration:
    """Smoke through the real `db.creator_repo.get_creator_context` path
    using the same DB isolation helper the dataclass repo tests use.
    Anchors that the builder's internal import wiring matches the
    repo's exported symbol."""

    @pytest.fixture
    def isolated_db(self, tmp_path, monkeypatch):
        import threading
        import app.db.connection as conn
        from app.db.connection import init_db
        test_db = tmp_path / "test_app.db"
        monkeypatch.setattr(conn, "DATABASE_PATH", test_db)
        monkeypatch.setattr(conn, "_ACTIVE_DB_PATH", None)
        monkeypatch.setattr(conn, "_tls", threading.local())
        init_db()
        yield test_db

    def test_build_returns_none_on_fresh_db(self, isolated_db):
        assert CreatorContextBuilder().build() is None

    def test_build_returns_persisted_after_upsert(self, isolated_db):
        from app.db.creator_repo import upsert_creator_context
        seeded = CreatorContext(channel_name="K1 Cooking", brand_voice="authentic")
        upsert_creator_context(seeded)
        result = CreatorContextBuilder().build()
        assert result == seeded

    def test_module_wrapper_round_trip(self, isolated_db):
        from app.db.creator_repo import upsert_creator_context
        seeded = CreatorContext(channel_name="K1", language="vi")
        upsert_creator_context(seeded)
        assert build_creator_context() == seeded
