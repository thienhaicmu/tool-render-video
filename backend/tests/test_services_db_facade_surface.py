"""Guard: ``app.services.db`` was retired in Batch 9 (audit FINDING-A14 closure).

The 49-LOC re-export facade was sunset in two steps:
- Batch 8-3 (commit 0f933b5): removed download_repo + creator_repo
  re-exports after a sweep showed zero callers went through the facade
  for those repos.
- Batch 9 (this commit): migrated every remaining caller — 21 files,
  23 import statements — to import directly from
  ``app.db.connection``, ``app.db.jobs_repo`` or ``app.db.feedback_repo``.
  The facade module was then deleted entirely.

This file becomes a regression guard: ``app.services.db`` must NOT come
back, and no ``.py`` under ``backend/app`` may import from it. If a
future commit re-introduces the facade or adds a caller, this test
fails in CI.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_facade_module_is_gone():
    """``app.services.db`` MUST NOT be importable. If you re-create it,
    update the migration plan in the commit message and document the
    audit cycle that motivated bringing the facade back.
    """
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.services.db")


def test_facade_file_is_gone():
    """The file on disk must not exist either — even an empty stub
    re-creates the dependency path."""
    facade_path = (
        Path(__file__).resolve().parent.parent
        / "app" / "services" / "db.py"
    )
    assert not facade_path.exists(), (
        f"{facade_path} re-appeared. The facade was deleted in Batch 9 "
        "(audit A14 closure). Import directly from app.db.* instead."
    )


def _app_python_files() -> list[Path]:
    root = Path(__file__).resolve().parent.parent / "app"
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_production_caller_imports_from_facade():
    """Source-level grep: zero `.py` under app/ may say
    ``from app.services.db import …``. The pattern is intentionally narrow
    so a comment that mentions the path (e.g. an audit-history note) is
    not a false positive.
    """
    needle = "from app.services.db import"
    offenders: list[tuple[Path, int, str]] = []
    for path in _app_python_files():
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if needle in stripped:
                offenders.append((path, line_no, stripped))
    assert not offenders, (
        "app.services.db imports re-appeared. They must use the direct "
        "app.db.* modules:\n"
        + "\n".join(f"  {p}:{ln}  {src}" for p, ln, src in offenders)
    )
