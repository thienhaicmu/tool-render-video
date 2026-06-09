"""Sprint I-B — per-channel CreatorContext unit tests.

All tests monkeypatch the repo helpers — no real DB required.

1. Per-channel row exists → returned (not global).
2. No per-channel row → falls back to global singleton.
3. Neither exists → returns None.
4. upsert_creator_context_for_channel writes to channel table, not global.
5. build_creator_context(channel_code="vn") passes channel_code to repo.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

from app.domain.creator_context import CreatorContext


def _make_ctx(**kwargs) -> CreatorContext:
    defaults = dict(
        creator_id="c1", channel_name="Test", brand_voice="friendly",
        target_audience="gen-z", content_pillars=["edu"],
        market="vn", language="vi", notes="",
    )
    defaults.update(kwargs)
    return CreatorContext(**defaults)


# 1. Per-channel row exists → returned (not global)
def test_get_channel_returns_per_channel_row(monkeypatch):
    channel_ctx = _make_ctx(channel_name="VN Channel")
    monkeypatch.setattr(
        "app.db.creator_repo.get_creator_context_for_channel",
        lambda code: channel_ctx,
    )
    from app.features.render.ai.context.builder import CreatorContextBuilder
    result = CreatorContextBuilder(channel_code="vn").build()
    assert result is not None
    assert result.channel_name == "VN Channel"


# 2. No per-channel row → falls back to global singleton
def test_get_channel_falls_back_to_global(monkeypatch):
    global_ctx = _make_ctx(channel_name="Global")

    def _fake_for_channel(code):
        from app.db.creator_repo import get_creator_context
        return get_creator_context()

    monkeypatch.setattr(
        "app.db.creator_repo.get_creator_context_for_channel",
        _fake_for_channel,
    )
    monkeypatch.setattr(
        "app.db.creator_repo.get_creator_context",
        lambda: global_ctx,
    )
    from app.features.render.ai.context.builder import CreatorContextBuilder
    result = CreatorContextBuilder(channel_code="vn").build()
    assert result is not None
    assert result.channel_name == "Global"


# 3. Neither per-channel nor global → returns None
def test_get_channel_neither_returns_none(monkeypatch):
    monkeypatch.setattr(
        "app.db.creator_repo.get_creator_context_for_channel",
        lambda code: None,
    )
    from app.features.render.ai.context.builder import CreatorContextBuilder
    result = CreatorContextBuilder(channel_code="vn").build()
    assert result is None


# 4. upsert_creator_context_for_channel writes to channel table, not global
def test_upsert_channel_does_not_touch_global():
    called_global = []
    channel_calls = []

    def _fake_upsert_channel(code, ctx):
        channel_calls.append(code)

    def _fake_upsert_global(ctx):
        called_global.append(True)

    # Patch at the settings module's namespace — it imports these names at the
    # top of the module, so patching the source (creator_repo) has no effect
    # once the module is loaded.
    with patch("app.routes.settings.upsert_creator_context", _fake_upsert_global), \
         patch("app.routes.settings.upsert_creator_context_for_channel", _fake_upsert_channel), \
         patch("app.routes.settings.get_creator_context_for_channel", return_value=None):
        from app.routes.settings import put_settings_creator_context
        from app.routes.settings import CreatorContextPayload
        put_settings_creator_context(CreatorContextPayload(), channel_code="vn")

    assert "vn" in channel_calls
    assert called_global == [], "global upsert must not be called when channel_code is set"


# 5. build_creator_context(channel_code="vn") passes channel_code to repo
def test_build_creator_context_passes_channel_code(monkeypatch):
    received = []

    def _fake_for_channel(code):
        received.append(code)
        return None

    monkeypatch.setattr(
        "app.db.creator_repo.get_creator_context_for_channel",
        _fake_for_channel,
    )
    from app.features.render.ai.context.builder import build_creator_context
    build_creator_context(channel_code="vn")
    assert received == ["vn"]
