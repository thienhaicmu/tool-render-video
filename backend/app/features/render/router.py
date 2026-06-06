"""Backwards-compatible facade for the render APIRouter (audit FINDING-A03).

The original ``features/render/router.py`` was a 1,195-LOC god controller
that mixed 19 endpoints across 4 responsibility lines (admin / prepare /
lifecycle / read). Per the 2026-06-06 audit, it has been split into a
``routers/`` subpackage:

- routers/_common.py    — shared validators + process_render + queue helper
- routers/utility.py    — admin / diagnostics endpoints
- routers/prepare.py    — source preview / preview-session endpoints
- routers/lifecycle.py  — process / upload / test / quick / resume / retry / cancel
- routers/read.py       — per-job read endpoints (media, thumbnail, subtitle)

This module is preserved as a thin facade for backwards compatibility:
- ``router`` re-exports the combined APIRouter from the subpackage.
- ``process_render`` and ``evict_stale_preview_sessions`` are re-exported
  so existing callers (main.py, editing_service.py) keep working without
  any import path changes.

New code should import directly from the appropriate sub-router file or
from ``app.features.render.routers`` — not from this facade.
"""
from app.features.render.engine.preview.session_service import (
    evict_stale_preview_sessions,  # re-exported: main.py imports it from here
)
from app.features.render.routers import router  # noqa: F401 — public re-export
from app.features.render.routers._common import (
    process_render,  # re-exported: editing_service.py imports it from here
)

__all__ = ["router", "process_render", "evict_stale_preview_sessions"]
