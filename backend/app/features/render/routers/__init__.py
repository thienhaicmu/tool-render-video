"""features/render/routers — split sub-routers (audit FINDING-A03 closure).

The previous monolithic ``features/render/router.py`` carried 19 endpoints
across ~1,195 LOC. Per the 2026-06-06 audit, it was a god controller —
prepare / render lifecycle / per-job read / admin endpoints mixed in one
file. This subpackage decomposes the controller along the four
responsibility lines the audit recommended.

The ``router`` exported below combines all four sub-routers under the
``/api/render`` prefix. ``main.py`` imports it the same way it always
did (``from app.features.render.router import router``), so the
deployment surface is unchanged.

Backwards compatibility: the original ``features/render/router.py``
module is preserved as a thin facade that re-exports ``router`` plus
the helpers other modules import from it (``process_render``,
``_queue_render_job``, ``_load_session``, ``evict_stale_preview_sessions``).
"""
from fastapi import APIRouter

from .lifecycle import router as _lifecycle_router
from .prepare import router as _prepare_router
from .read import router as _read_router
from .utility import router as _utility_router

router = APIRouter(prefix="/api/render", tags=["render"])

router.include_router(_utility_router)
router.include_router(_prepare_router)
router.include_router(_lifecycle_router)
router.include_router(_read_router)

__all__ = ["router"]
