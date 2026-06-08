"""Re-export shim for the legacy ``app.models.schemas`` import path.

Audit-2026-06-06 MT-2 (Batch 10I, 2026-06-06): the original 570-LOC
monolith was split by domain so the schemas layer no longer has a
single oversized file:

- ``app.models.render``  — PrepareSourceRequest, QuickProcessRequest,
                            TextLayer* helpers, RenderRequest, RenderRequestStrict.
- ``app.models.jobs``    — JobStatusResponse.

This file remains as the canonical import path so all 17 existing
consumers (``from app.models.schemas import …``) keep working without
edits. New code SHOULD prefer the direct module paths above; both
paths are equivalent and stay in sync.

The Channel schemas (ChannelCreate / ChannelInfo) were removed in
Batch 10H along with the orphan /api/channels surface — see
``test_channels_surface_gone.py`` for the regression guard.
"""
from __future__ import annotations

from app.models.jobs import JobStatusResponse
from app.models.render import (
    PrepareSourceRequest,
    QuickProcessRequest,
    RenderRequest,
    RenderRequestStrict,
    TextLayerBackground,
    TextLayerConfig,
    TextLayerOutline,
    TextLayerShadow,
)

__all__ = [
    "JobStatusResponse",
    "PrepareSourceRequest",
    "QuickProcessRequest",
    "RenderRequest",
    "RenderRequestStrict",
    "TextLayerBackground",
    "TextLayerConfig",
    "TextLayerOutline",
    "TextLayerShadow",
]
