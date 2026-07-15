"""Remove render/runtime history while preserving project and master data.

This is deliberately standalone: it does not import the app, start a server,
or build anything. It defaults to a dry run. Use ``--confirm`` only while the
application is stopped.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


HISTORY_TABLES = (
    "clip_feedback",
    "job_parts",
    "render_ab_scores",
    "platform_metrics",
    "assets",
    "download_jobs",
    "acquisition_queue",
    "jobs",
)
RUNTIME_DIRS = (
    "cache", "temp", "logs", "reports", "story_plan_runs", "backups",
    "playwright", "smoke-test-output", "smoke-test-output-batch10",
    "smoke-test-output-batch10R", "tmp",
)
MODEL_CACHE_DIRS = ("huggingface", "whisper_cache", "torch", "fontconfig")


def _db_counts(db_path: Path) -> dict[str, int]:
    if not db_path.is_file():
        return {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        existing = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0])
            for table in HISTORY_TABLES if table in existing
        }
    finally:
        conn.close()


def _snapshot_sqlite(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.part")
    partial.unlink(missing_ok=True)
    src = dst = None
    try:
        src = sqlite3.connect(str(source))
        dst = sqlite3.connect(str(partial))
        src.backup(dst)
        dst.commit()
    finally:
        if dst is not None:
            dst.close()
        if src is not None:
            src.close()
    partial.replace(target)


def _clean_db(db_path: Path) -> dict[str, int]:
    if not db_path.is_file():
        return {}
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        existing = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        deleted: dict[str, int] = {}
        for table in HISTORY_TABLES:
            if table not in existing:
                continue
            deleted[table] = int(conn.execute(f"DELETE FROM [{table}]").rowcount or 0)
        conn.commit()
        conn.execute("VACUUM")
        return deleted
    finally:
        conn.close()
        for suffix in ("-wal", "-shm"):
            db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    return 0


def _safe_data_dir(data_root: Path, name: str) -> Path:
    target = (data_root / name).resolve()
    if target.parent != data_root.resolve():
        raise RuntimeError(f"refusing to clean path outside data root: {target}")
    return target


def _remove_tree(path: Path) -> list[str]:
    """Best-effort removal so one open log does not block other cleanup."""
    skipped: list[str] = []
    if not path.exists():
        return skipped
    for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        try:
            if child.is_file() or child.is_symlink():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                child.rmdir()
        except OSError:
            skipped.append(str(child))
    try:
        path.rmdir()
    except OSError:
        skipped.append(str(path))
    return skipped


def clean_runtime_data(project_root: Path, *, confirm: bool, backup: bool,
                       include_model_caches: bool) -> dict:
    data_root = (project_root / "data").resolve()
    if not data_root.is_dir():
        raise FileNotFoundError(f"data directory not found: {data_root}")

    db_path = data_root / "app.db"
    table_counts = _db_counts(db_path)
    names = list(RUNTIME_DIRS)
    if include_model_caches:
        names.extend(MODEL_CACHE_DIRS)
    dirs = {name: _safe_data_dir(data_root, name)
            for name in names if (data_root / name).exists()}
    plan = {
        "database": str(db_path), "tables": table_counts,
        "directories": {name: str(path) for name, path in dirs.items()},
        "directory_bytes": {name: _size(path) for name, path in dirs.items()},
        "include_model_caches": include_model_caches,
    }
    if not confirm:
        return plan

    backup_path = None
    if backup and db_path.is_file():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = project_root / ".runtime-cleanup-backups" / f"app-{stamp}.db"
        _snapshot_sqlite(db_path, backup_path)
    plan["deleted_tables"] = _clean_db(db_path)
    skipped: dict[str, list[str]] = {}
    for name, path in dirs.items():
        remaining = _remove_tree(path)
        if remaining:
            skipped[name] = remaining
    plan["backup_path"] = str(backup_path) if backup_path else ""
    plan["skipped"] = skipped
    return plan


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Keep master/project data and remove render history/runtime data."
    )
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="project root")
    parser.add_argument("--confirm", action="store_true",
                        help="perform deletion; otherwise dry run")
    parser.add_argument("--no-backup", action="store_true",
                        help="skip the external SQLite backup")
    parser.add_argument("--include-model-caches", action="store_true",
                        help="also delete Whisper/HuggingFace/Torch/font caches")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = clean_runtime_data(
            args.project.expanduser().resolve(), confirm=args.confirm,
            backup=not args.no_backup, include_model_caches=args.include_model_caches,
        )
    except (FileNotFoundError, OSError, RuntimeError, sqlite3.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(("CLEANED" if args.confirm else "DRY RUN") + ": " + result["database"])
    print("Database rows:", result.get("tables", {}))
    for name, path in result.get("directories", {}).items():
        size = result["directory_bytes"][name] / (1024 * 1024)
        print(f"  - {name}: {size:.1f} MiB ({path})")
    if args.confirm:
        print("Deleted rows:", result.get("deleted_tables", {}))
        if result.get("backup_path"):
            print("SQLite backup:", result["backup_path"])
        if result.get("skipped"):
            print("Skipped open files/directories:", result["skipped"])
        print("Preserved: V3 library, manifests, asset library, BGM, projects, AI memory.")
    else:
        print("Nothing was deleted. Add --confirm after reviewing this list.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
