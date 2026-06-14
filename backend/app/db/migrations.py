"""Schema migration runner — additive-only, idempotent, offline-safe.

Sprint 6.B: complements (does NOT replace) the existing init_db() +
_ensure_columns() approach in connection.py. init_db() runs first to
build/migrate the baseline schema; this runner then applies any newer
migrations recorded in numbered files under backend/app/db/migration_steps/.

File convention:
  - Filename matches regex `[0-9]+_.+\\.py`, e.g. `0002_add_user_prefs.py`
  - Module exports:
        VERSION: int        — unique, monotonically increasing
        NAME:    str        — short slug describing the migration
        up(conn)            — applies the change to a sqlite3.Connection
  - Additive only. No DROP, no ALTER RENAME, no column-type changes.
    CLAUDE.md enforces this at code review time; the runner does not.

Schema:
    CREATE TABLE schema_versions (
        version    INTEGER NOT NULL PRIMARY KEY,
        name       TEXT    NOT NULL,
        applied_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

Each migration runs in its own transaction. On failure, the transaction
is rolled back and MigrationError is raised. The wrapper in init_db()
catches that so app startup still succeeds.

Phase 2 (future, separate sprint) would carve the existing baseline body
of init_db()/_ensure_columns() into versioned migration files. For now
the baseline stays in connection.py and migrations only handle changes
made AFTER this commit.
"""
from __future__ import annotations

import importlib.util
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# Default location: backend/app/db/migration_steps/
_DEFAULT_STEPS_DIR = Path(__file__).resolve().parent / "migration_steps"


class MigrationError(Exception):
    """Raised when a migration file is malformed or fails to apply."""


@dataclass(frozen=True)
class Migration:
    """One discovered migration file's contract."""
    version: int
    name: str
    up: Callable[[sqlite3.Connection], None]


# ── schema_versions table ────────────────────────────────────────────────────


def _ensure_schema_versions_table(conn: sqlite3.Connection) -> None:
    """Create schema_versions if missing. Idempotent — safe to call repeatedly."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_versions (
            version    INTEGER NOT NULL PRIMARY KEY,
            name       TEXT    NOT NULL,
            applied_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    """Return the set of versions already recorded as applied."""
    _ensure_schema_versions_table(conn)
    rows = conn.execute("SELECT version FROM schema_versions").fetchall()
    return {int(r[0]) for r in rows}


# ── Discovery ────────────────────────────────────────────────────────────────


def discover_migrations(steps_dir: Path | None = None) -> list[Migration]:
    """Load every migration file under steps_dir, sorted by VERSION ascending.

    Each file must define VERSION (int), NAME (str), and up (callable).
    Files starting with `_` (e.g. `__init__.py`) are skipped.
    Duplicate VERSION across files raises MigrationError.
    """
    root = steps_dir if steps_dir is not None else _DEFAULT_STEPS_DIR
    if not root.exists():
        return []

    discovered: list[Migration] = []
    # Only match files whose name starts with digits and contains an underscore.
    for path in sorted(root.glob("[0-9]*.py")):
        if path.name.startswith("_") or "_" not in path.stem:
            continue
        module_name = f"app.db.migration_steps.{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise MigrationError(f"cannot load spec for {path.name}")
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise MigrationError(f"failed to import {path.name}: {exc}") from exc

        for attr in ("VERSION", "NAME", "up"):
            if not hasattr(module, attr):
                raise MigrationError(f"{path.name}: missing required attribute {attr!r}")
        if not isinstance(module.VERSION, int):
            raise MigrationError(f"{path.name}: VERSION must be int, got {type(module.VERSION).__name__}")
        if not isinstance(module.NAME, str) or not module.NAME:
            raise MigrationError(f"{path.name}: NAME must be a non-empty str")
        if not callable(module.up):
            raise MigrationError(f"{path.name}: up must be callable")

        discovered.append(Migration(version=module.VERSION, name=module.NAME, up=module.up))

    discovered.sort(key=lambda m: m.version)

    seen: set[int] = set()
    for m in discovered:
        if m.version in seen:
            raise MigrationError(f"duplicate VERSION={m.version} (in file with NAME={m.name!r})")
        seen.add(m.version)
    return discovered


# ── Runner ───────────────────────────────────────────────────────────────────


def run_pending_migrations(
    conn: sqlite3.Connection,
    steps_dir: Path | None = None,
) -> dict:
    """Apply every discovered migration whose version is not yet recorded.

    Each migration runs in its own transaction. On failure, the migration's
    changes are rolled back and MigrationError is raised — the caller (e.g.
    init_db()) decides whether that's fatal. Already-applied migrations
    found in earlier startups are skipped.

    Returns: {"applied": [version,...], "skipped": [version,...], "available": int}
    """
    available = discover_migrations(steps_dir)
    already = applied_versions(conn)

    applied: list[int] = []
    skipped: list[int] = []

    for m in available:
        if m.version in already:
            skipped.append(m.version)
            continue
        try:
            conn.execute("BEGIN")
            m.up(conn)
            conn.execute(
                "INSERT INTO schema_versions (version, name) VALUES (?, ?)",
                (m.version, m.name),
            )
            conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            raise MigrationError(
                f"migration {m.version:04d}_{m.name} failed: {exc}"
            ) from exc
        applied.append(m.version)
        logger.info("schema migration applied: %04d_%s", m.version, m.name)

    return {
        "applied": applied,
        "skipped": skipped,
        "available": len(available),
    }
