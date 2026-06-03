"""P3 Contract #7 — data/app.db sole job-state authority (import-graph).

Per CLAUDE.md Sacred Contract #7:

  `data/app.db` is the single source of truth for all job state.
  NEVER write to it with raw `sqlite3.connect()` calls outside the
  `backend/app/db/` module.

Rationale: the `app/db/connection.py` module sets WAL mode, registers
row factories, and manages thread-local connection state. Bypassing it
creates connections without WAL mode, without row factories, and in
incompatible isolation levels — all of which corrupt the consistency
guarantees the render pipeline depends on.

This test is the static guard: it walks `backend/app/**/*.py` with the
Python AST and flags any `sqlite3.connect(...)` call site that lives
outside the sanctioned allowlist. New violations fail this test with
the exact file path and line number, plus remediation guidance.

See docs/review/AUDIT_2026-06-02_followup_11.md for the closure record.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


# Sanctioned files allowed to call sqlite3.connect() directly:
#   - app/db/** — the sole-authority connection module per Contract #7
#   - app/services/db_backup.py — Sprint 6.A backup module (online .backup()
#     API on app.db; documented exception per its module docstring)
#   - app/services/cookie_extractor.py — reads BROWSER cookie databases
#     (not app.db); legitimate cross-purpose use of sqlite3
SANCTIONED_RELATIVE_PATHS = {
    # Paths are POSIX-style, relative to backend/app/.
    "db/connection.py",
    "db/__init__.py",
    "services/db_backup.py",
    "services/cookie_extractor.py",
}


def _backend_app_root() -> Path:
    """Return the absolute path to backend/app/."""
    # tests/ sits at backend/tests/, so up-two gives backend/, then +app.
    return (Path(__file__).resolve().parent.parent / "app").resolve()


def _find_sqlite3_connect_call_sites(root: Path) -> list[tuple[str, int]]:
    """Walk root recursively, AST-parse every .py, return [(rel_path, lineno)]
    for every `sqlite3.connect(...)` call site found."""
    hits: list[tuple[str, int]] = []
    for py in root.rglob("*.py"):
        try:
            source = py.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            tree = ast.parse(source, filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # Match: sqlite3.connect(...) — Attribute(value=Name('sqlite3'), attr='connect')
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "connect"
                and isinstance(func.value, ast.Name)
                and func.value.id == "sqlite3"
            ):
                rel = py.relative_to(root).as_posix()
                hits.append((rel, node.lineno))
    return hits


class TestDbSoleAuthorityImportGraph:
    """Sacred Contract #7 — only sanctioned modules may call sqlite3.connect()."""

    def test_no_unsanctioned_sqlite3_connect_calls(self):
        """Walk backend/app/ and assert every sqlite3.connect() call
        site lives in SANCTIONED_RELATIVE_PATHS. A new caller anywhere
        else is a Contract #7 violation."""
        root = _backend_app_root()
        all_hits = _find_sqlite3_connect_call_sites(root)
        violations = [
            (path, line) for (path, line) in all_hits
            if path not in SANCTIONED_RELATIVE_PATHS
        ]
        assert not violations, (
            "Contract #7 violation: sqlite3.connect() called outside "
            "the sanctioned db module:\n"
            + "\n".join(f"  - app/{path}:{line}" for path, line in violations)
            + "\n\nRemediation: route the call through "
              "app/db/connection.py::get_conn() (or its thread-local "
              "variant). Direct sqlite3.connect() calls bypass WAL "
              "mode, row factories, and the thread-local connection "
              "state the render pipeline depends on.\n"
            + "\nIf the new caller is legitimately sanctioned (e.g., "
              "a backup tool that needs the raw connection API), add "
              "its relative path to SANCTIONED_RELATIVE_PATHS in "
              "test_contract_db_sole_authority.py."
        )

    def test_sanctioned_paths_all_exist(self):
        """Sanity check: every sanctioned path is a real file. Catches
        typos or stale entries after refactors."""
        root = _backend_app_root()
        for rel in SANCTIONED_RELATIVE_PATHS:
            target = root / rel
            assert target.exists(), (
                f"Sanctioned path {rel!r} does not exist at {target}. "
                f"Remove it from SANCTIONED_RELATIVE_PATHS."
            )

    def test_db_connection_module_actually_uses_sqlite3_connect(self):
        """Positive control: app/db/connection.py SHOULD have at
        least one sqlite3.connect() call. If this fails, either the
        module was renamed/relocated or the connection model changed
        — both worth investigating."""
        root = _backend_app_root()
        all_hits = _find_sqlite3_connect_call_sites(root)
        db_connection_hits = [
            (path, line) for (path, line) in all_hits
            if path == "db/connection.py"
        ]
        assert db_connection_hits, (
            "Contract #7: db/connection.py has no sqlite3.connect() "
            "calls. Either the connection module moved, or the project "
            "switched away from raw sqlite3. Audit the new model and "
            "update SANCTIONED_RELATIVE_PATHS."
        )
