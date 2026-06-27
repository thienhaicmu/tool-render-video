"""F2 (2026-06-27) — server-side render-preset application.

Pins the precedence contract of ``_apply_render_preset``:
explicit user value > preset value > default. A preset fills only the
fields the FE did not explicitly send (``model_fields_set``), and the
merged values are baked into the payload (so replay is preset-independent).
"""
from __future__ import annotations

import pytest

from app.domain.render_preset import RenderPreset
from app.features.render.routers import lifecycle
from app.models.render import RenderRequest


def _patch_preset(monkeypatch, preset: RenderPreset | None) -> None:
    # The helper does `from app.db.presets_repo import get_preset` at call
    # time, so patch the source module attribute.
    monkeypatch.setattr("app.db.presets_repo.get_preset", lambda _id: preset)


def test_no_preset_id_is_a_noop(monkeypatch):
    called = {"hit": False}
    monkeypatch.setattr(
        "app.db.presets_repo.get_preset",
        lambda _id: called.__setitem__("hit", True),
    )
    payload = RenderRequest(output_count=2)
    lifecycle._apply_render_preset(payload, user_set=set())
    assert called["hit"] is False  # short-circuits before any lookup
    assert payload.output_count == 2


def test_preset_fills_fields_user_did_not_send(monkeypatch):
    _patch_preset(monkeypatch, RenderPreset(
        preset_id="builtin-tiktok-viral",
        params={"output_count": 5, "video_type": "viral", "hook_strength": "aggressive"},
    ))
    payload = RenderRequest(render_preset_id="builtin-tiktok-viral")
    # user sent only render_preset_id
    lifecycle._apply_render_preset(payload, user_set={"render_preset_id"})
    assert payload.output_count == 5
    assert payload.video_type == "viral"
    assert payload.hook_strength == "aggressive"


def test_explicit_user_value_wins_over_preset(monkeypatch):
    _patch_preset(monkeypatch, RenderPreset(
        preset_id="builtin-tiktok-viral",
        params={"output_count": 5, "video_type": "viral"},
    ))
    payload = RenderRequest(render_preset_id="builtin-tiktok-viral", output_count=1)
    # user explicitly sent output_count → must win; video_type comes from preset
    lifecycle._apply_render_preset(payload, user_set={"render_preset_id", "output_count"})
    assert payload.output_count == 1            # user wins
    assert payload.video_type == "viral"        # preset fills the rest


def test_missing_preset_leaves_payload_untouched(monkeypatch):
    _patch_preset(monkeypatch, None)
    payload = RenderRequest(render_preset_id="does-not-exist", output_count=3)
    lifecycle._apply_render_preset(payload, user_set={"render_preset_id"})
    assert payload.output_count == 3


def test_lookup_exception_is_swallowed(monkeypatch):
    def _boom(_id):
        raise RuntimeError("db down")
    monkeypatch.setattr("app.db.presets_repo.get_preset", _boom)
    payload = RenderRequest(render_preset_id="builtin-tiktok-viral", output_count=4)
    # must not raise — preset application is best-effort
    lifecycle._apply_render_preset(payload, user_set={"render_preset_id"})
    assert payload.output_count == 4


def test_render_preset_id_is_on_the_public_wire():
    """F2 requires render_preset_id to be FE-facing so the picker can send it."""
    from app.models.render_public import FE_FACING_FIELDS, RenderRequestPublic
    assert "render_preset_id" in FE_FACING_FIELDS
    assert "render_preset_id" in RenderRequestPublic.model_fields
