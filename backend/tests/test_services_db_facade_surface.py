"""Pin the ``app.services.db`` facade surface (audit FINDING-A14 progress).

The facade was a 49-LOC re-export shim used by ~18 callers. Phase 1
identified it as a maintenance hazard: a schema change to any backing
repo (jobs / creator / feedback / download) ripples through 18 import
sites even when each caller only needs one repo.

The audit's sunset strategy is to migrate callers off the facade per
repo and then prune the corresponding re-export.

State after Batch 8-3 (2026-06-06):

- download_repo (5 helpers): NO callers go through the facade.
  Re-export removed.
- creator_repo (2 helpers):  NO callers go through the facade.
  Re-export removed.
- jobs_repo (11 helpers):    callers still use the facade path.
  Re-export retained.
- feedback_repo (4 helpers): callers still use the facade path.
  Re-export retained.
- connection helpers:        retained — still the most-used entry.

This test file locks the contract. If a future commit re-introduces a
removed re-export, or removes one that still has callers, CI fails.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Surface pinning
# ---------------------------------------------------------------------------

_EXPECTED_FACADE_NAMES: frozenset[str] = frozenset({
    # connection helpers
    "close_thread_conn", "db_conn", "get_conn", "init_db",
    "_json_dumps", "_json_loads", "_thread_conn", "_utc_now",
    "_utc_now_iso",
    # jobs_repo — callers still through facade
    "clear_part_output", "delete_job", "get_job",
    "list_job_parts", "list_job_parts_bulk", "list_jobs",
    "list_jobs_page", "save_error_kind", "update_job_progress",
    "upsert_job", "upsert_job_part",
    # feedback_repo — callers still through facade
    "upsert_clip_feedback", "get_clip_feedback",
    "list_feedback_for_channel", "delete_clip_feedback",
})

_NAMES_THAT_MUST_NOT_BE_REEXPORTED: frozenset[str] = frozenset({
    # download_repo — every caller imports from app.db.download_repo directly
    "create_download_job", "update_download_job", "get_download_job",
    "list_download_jobs", "delete_download_job",
    # creator_repo — every caller imports from app.db.creator_repo directly
    "get_creator_prefs", "upsert_creator_prefs",
})


def _facade_public_surface() -> set[str]:
    mod = importlib.import_module("app.services.db")
    return {
        name for name in dir(mod)
        if not name.startswith("__")
        and name not in {"logging", "logger"}  # incidental imports
    }


def test_expected_names_are_present():
    surface = _facade_public_surface()
    missing = _EXPECTED_FACADE_NAMES - surface
    assert not missing, (
        f"app.services.db is missing expected re-exports: {sorted(missing)}. "
        "If you removed one intentionally, also update _EXPECTED_FACADE_NAMES "
        "AND migrate any callers that still depend on it."
    )


def test_removed_names_are_not_present():
    surface = _facade_public_surface()
    leaked = _NAMES_THAT_MUST_NOT_BE_REEXPORTED & surface
    assert not leaked, (
        f"app.services.db re-introduced removed names: {sorted(leaked)}. "
        "These helpers should be imported directly from app.db.download_repo "
        "or app.db.creator_repo. If you genuinely need them on the facade, "
        "update _NAMES_THAT_MUST_NOT_BE_REEXPORTED and migrate callers."
    )


# ---------------------------------------------------------------------------
# Caller audit — make sure no production code reaches for a removed name
# through the facade
# ---------------------------------------------------------------------------

def _app_python_files() -> list[Path]:
    root = Path(__file__).resolve().parent.parent / "app"
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


@pytest.mark.parametrize("removed_name", sorted(_NAMES_THAT_MUST_NOT_BE_REEXPORTED))
def test_no_production_caller_imports_removed_name_from_facade(removed_name: str):
    """Source-level grep: no ``.py`` in app/ imports a removed name through
    ``app.services.db``. Catches a caller that tries to add one back.
    """
    needle = f"from app.services.db import"
    offenders: list[tuple[Path, int, str]] = []
    for path in _app_python_files():
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if needle in line and removed_name in line:
                offenders.append((path, line_no, line.strip()))
    assert not offenders, (
        f"{removed_name} is imported through app.services.db at:\n"
        + "\n".join(f"  {p}:{ln}  {src}" for p, ln, src in offenders)
        + f"\nImport from app.db.download_repo / app.db.creator_repo directly."
    )
