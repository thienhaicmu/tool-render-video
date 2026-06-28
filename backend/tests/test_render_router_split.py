"""Tests for the features/render/router.py → routers/ split (audit FINDING-A03).

Pins the post-split contract:
1. The endpoint surface is unchanged — the 19 routes that existed in the
   monolithic router are still mounted at the same paths and methods.
2. The legacy facade (``app.features.render.router``) still exposes the
   public helpers that external modules import from it
   (``router``, ``process_render``, ``evict_stale_preview_sessions``).
3. Each new sub-router file stays under the audit's god-file ceiling.
4. The combined APIRouter still carries the /api/render prefix.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from app.features.render.routers import router as combined_router


# Static catalogue of every endpoint that was on the pre-split router.
# Each entry is (method, path_with_prefix). If any of these disappear or
# a path mutates, the FE/Electron contract breaks — these tests must fail.
_EXPECTED_ENDPOINTS: set[tuple[str, str]] = {
    ("GET",    "/api/render/queue-status"),
    ("GET",    "/api/render/system-info"),
    ("POST",   "/api/render/cache/clear"),
    ("GET",    "/api/render/ai-diagnostics"),

    ("POST",   "/api/render/prepare-source"),
    ("DELETE", "/api/render/prepare-source/{session_id}"),
    ("GET",    "/api/render/preview-video/{session_id}"),
    ("GET",    "/api/render/preview-transcript/{session_id}"),

    ("POST",   "/api/render/process"),
    ("POST",   "/api/render/upload-local"),
    ("POST",   "/api/render/test-cloud-ai"),
    ("POST",   "/api/render/quick-process"),
    ("POST",   "/api/render/resume/{job_id}"),
    ("POST",   "/api/render/retry/{job_id}"),
    ("POST",   "/api/render/{job_id}/cancel"),
    # ADR-007 (2026-06-27): cancel-status added so FE can poll subprocess
    # teardown before re-enabling the Start-Render button.
    ("GET",    "/api/render/{job_id}/cancel-status"),

    # GET /api/render/jobs/{job_id} was removed in audit API03 closure
    # (2026-06-06). It was a byte-for-byte duplicate of GET /api/jobs/{id}
    # and the FE only ever called the canonical path.
    ("GET",    "/api/render/jobs/{job_id}/parts/{part_no}/media"),
    ("GET",    "/api/render/jobs/{job_id}/parts/{part_no}/thumbnail"),
    ("GET",    "/api/render/subtitle-preview"),
}


def _collect_routes(api_router: APIRouter) -> set[tuple[str, str]]:
    """Return (method, path) tuples for every route on ``api_router``."""
    collected: set[tuple[str, str]] = set()
    for route in api_router.routes:
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", None)
        if not path:
            continue
        for m in methods:
            # Skip the auto-added HEAD verb that FastAPI emits for GETs.
            if m == "HEAD":
                continue
            collected.add((m, path))
    return collected


# ---------------------------------------------------------------------------
# Endpoint surface preservation
# ---------------------------------------------------------------------------

def test_combined_router_has_prefix():
    """The /api/render prefix must remain on the combined router."""
    assert combined_router.prefix == "/api/render"


def test_combined_router_exposes_all_legacy_endpoints():
    """Every (method, path) that existed pre-split must still be reachable."""
    actual = _collect_routes(combined_router)
    missing = _EXPECTED_ENDPOINTS - actual
    assert not missing, (
        f"endpoint surface shrunk: {sorted(missing)}. "
        f"Audit FINDING-A03 split must preserve EVERY pre-existing path."
    )


def test_combined_router_does_not_add_unexpected_endpoints():
    """A surprise endpoint usually means a typo or accidental decorator."""
    actual = _collect_routes(combined_router)
    extra = actual - _EXPECTED_ENDPOINTS
    assert not extra, f"unexpected endpoint(s) appeared after split: {sorted(extra)}"


def test_combined_router_route_count_is_19():
    # 18 → 19 after ADR-007 added GET /{job_id}/cancel-status (2026-06-27).
    # Was 19 pre-audit; the API03 duplicate /api/render/jobs/{id} was deleted →
    # back to 18; now 19 again with cancel-status.
    actual = _collect_routes(combined_router)
    assert len(actual) == 19, f"expected 19 routes, got {len(actual)}: {sorted(actual)}"


# ---------------------------------------------------------------------------
# Facade re-exports (main.py + editing_service.py depend on these)
# ---------------------------------------------------------------------------

def test_legacy_facade_reexports_router():
    """app.features.render.router.router must still be the same APIRouter."""
    from app.features.render import router as facade
    assert facade.router is combined_router


def test_legacy_facade_reexports_process_render():
    """editing_service.py imports process_render from the facade."""
    from app.features.render.router import process_render
    from app.features.render.routers._common import process_render as src
    assert process_render is src


def test_legacy_facade_reexports_evict_stale_preview_sessions():
    """main.py periodic cleanup imports this from the facade."""
    from app.features.render.engine.preview.session_service import (
        evict_stale_preview_sessions as src,
    )
    from app.features.render.router import evict_stale_preview_sessions
    assert evict_stale_preview_sessions is src


# ---------------------------------------------------------------------------
# Per-sub-router LOC ceiling (closes the audit god-file concern)
# ---------------------------------------------------------------------------

def _routers_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "app" / "features" / "render" / "routers"


def test_no_sub_router_exceeds_god_file_ceiling():
    """Each sub-router file must stay under the audit's 800-LOC god-file
    ceiling. The monolithic predecessor was 1,195 LOC.
    """
    routers_dir = _routers_dir()
    for path in sorted(routers_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        loc = sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
        assert loc < 800, f"{path.name} is {loc} LOC — exceeds the 800-LOC god-file ceiling"


def test_legacy_facade_is_thin():
    """The legacy router.py must remain a thin re-export facade, not grow back."""
    facade_path = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "router.py"
    )
    loc = sum(1 for _ in facade_path.read_text(encoding="utf-8").splitlines())
    assert loc < 100, (
        f"features/render/router.py is {loc} LOC — the facade must stay thin "
        "(< 100 LOC). New endpoints must live in the routers/ subpackage."
    )
