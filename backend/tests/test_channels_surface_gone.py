"""Audit FINDING-API05 closure (Batch 10H 2026-06-06).

The six orphan ``/api/channels/*`` endpoints (and their backing
``routes/channels.py`` + ``ChannelCreate`` / ``ChannelInfo`` schemas)
were deleted after the audit confirmed zero FE callers since the
Phase 4F.5A upload-pipeline retirement.

This file is the regression guard. The surface MUST NOT come back
without a written product decision.

Pins:

1. ``app.routes.channels`` is not importable — the module is gone.
2. ``ChannelCreate`` / ``ChannelInfo`` are not exported from
   ``app.models.schemas`` (the only consumers were inside the deleted route).
3. ``list_channels`` is not exported from ``app.services.channel_service``.
   ``ensure_channel`` survives because the render pipeline still calls it.
4. ``GET /api/channels`` returns 404 against a freshly-mounted FastAPI app
   with the production router set.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


def test_routes_channels_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.routes.channels")


def test_channel_schemas_not_exported():
    """``ChannelCreate`` / ``ChannelInfo`` lived in ``app.models.schemas``;
    deletion left the rest of the module intact."""
    from app.models import schemas

    assert not hasattr(schemas, "ChannelCreate"), (
        "ChannelCreate re-appeared in app.models.schemas. The /api/channels "
        "surface was deleted in Batch 10H (audit FINDING-API05 closure). "
        "Adding it back requires an approved product decision."
    )
    assert not hasattr(schemas, "ChannelInfo")


def test_ensure_channel_survives_but_list_channels_is_gone():
    """``ensure_channel`` is called by the render pipeline + main.py startup
    (default channel ``k1``) — it MUST stay. ``list_channels`` was the orphan
    accessor used only by the deleted route — it must go."""
    from app.services import channel_service

    assert hasattr(channel_service, "ensure_channel"), (
        "ensure_channel is consumed by render_pipeline + main.py startup. "
        "Removing it breaks every render."
    )
    assert not hasattr(channel_service, "list_channels"), (
        "list_channels re-appeared. Its only caller was routes/channels.py, "
        "which was deleted in Batch 10H."
    )


def test_get_api_channels_returns_404_via_test_client():
    """Mount the production main app and confirm /api/channels is gone.

    Uses the real ``app.main:app`` so the router-set + prefix wiring is
    exactly what production sees. A 404 here means the channels_router
    was successfully unmounted; a 200 would mean someone re-added it.
    """
    from app.main import app

    client = TestClient(app)
    for path in (
        "/api/channels",
        "/api/channels/",
        "/api/channels/k1",
        "/api/channels/scan",
        "/api/channels/root",
    ):
        resp = client.get(path)
        assert resp.status_code == 404, (
            f"{path} returned {resp.status_code} — channels surface "
            "re-appeared. Audit FINDING-API05 closure breached."
        )
