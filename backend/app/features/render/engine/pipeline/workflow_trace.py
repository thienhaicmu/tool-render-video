"""Backwards-compat shim — workflow_trace moved to app.core.tracing.

Audit FINDING-A08 (2026-06-06): the workflow-trace module was previously
hosted under the render-engine feature even though the download feature
also imported from it. That cross-feature reach is a layering violation
the Phase 3 review flagged as "wrong-direction" coupling.

The implementation now lives at ``app.core.tracing``. This module
remains as a re-export so existing imports from
``app.features.render.engine.pipeline.workflow_trace`` continue to
resolve. New code should import directly from ``app.core.tracing``.
"""
from app.core.tracing import *  # noqa: F401,F403 — public re-export
from app.core.tracing import (  # explicit names for static analyzers
    _RENDER_EVENT_MAP,
    _feed_render_event,
    dl_job_done,
    dl_job_fail,
    dl_job_start,
)

__all__ = [
    "_RENDER_EVENT_MAP",
    "_feed_render_event",
    "dl_job_done",
    "dl_job_fail",
    "dl_job_start",
]
