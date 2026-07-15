"""Portable data synchronizer for a project clone.

This script intentionally does not import the application, start a server, or
run a build. It copies the runtime data that Git ignores, including the V3
visual library, and verifies every copied file with SHA-256.

Examples:
    python scripts/sync_data.py --source D:\\tool-render-video \
        --destination E:\\tool-render-video --profile portable
    python scripts/sync_data.py --source D:\\tool-render-video \
        --destination E:\\tool-render-video --profile full --include-sensitive
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MANIFEST_NAME = ".data-sync-manifest.json"
PORTABLE_EXCLUDED_DIRS = {
    "cache",
    "temp",
    "logs",
    "huggingface",
    "whisper_cache",
    "torch",
    "playwright",
    "installers",
    "cookies",
}
SENSITIVE_DIRS = {"cookies"}
VOLATILE_DB_SUFFIXES = {"-wal", "-shm"}


@dataclass(frozen=True)
class Entry:
    relative: str
    size: int
    sha256: str
    kind: str = "file"


def _sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _data_files(data_root: Path, *, profile: str, include_sensitive: bool) -> list[Path]:
    excluded = set() if profile == "full" else set(PORTABLE_EXCLUDED_DIRS)
    if not include_sensitive:
        excluded.update(SENSITIVE_DIRS)

    files: list[Path] = []
    if not data_root.is_dir():
        return files
    for path in sorted(data_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(data_root)
        parts = relative.parts
        if not parts or parts[0] in excluded:
            continue
        if path.name == MANIFEST_NAME or path.name.endswith(tuple(VOLATILE_DB_SUFFIXES)):
            continue
        files.append(path)
    return files


def _atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{target.name}.", suffix=".sync-part", dir=target.parent, delete=False
    ) as handle:
        partial = Path(handle.name)
    try:
        shutil.copy2(source, partial)
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)


def _sqlite_snapshot(source: Path, target: Path) -> None:
    """Create a consistent SQLite snapshot without importing app code."""
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.sync-part")
    partial.unlink(missing_ok=True)
    source_conn = None
    target_conn = None
    try:
        source_conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        target_conn = sqlite3.connect(str(partial))
        source_conn.backup(target_conn)
        target_conn.commit()
    finally:
        if target_conn is not None:
            target_conn.close()
        if source_conn is not None:
            source_conn.close()
    os.replace(partial, target)
    # A snapshot contains the committed WAL state, so stale target sidecars
    # must not be allowed to resurrect old pages on the next app start.
    for suffix in VOLATILE_DB_SUFFIXES:
        target.with_name(target.name + suffix).unlink(missing_ok=True)


def _copy_entry(source: Path, target: Path) -> None:
    if source.name in {"app.db", "ai_memory.db"}:
        try:
            _sqlite_snapshot(source, target)
            return
        except (OSError, sqlite3.Error):
            # Some old or partially-created SQLite files are not valid DBs.
            # Preserve them rather than making the whole data sync fail.
            target.with_name(f".{target.name}.sync-part").unlink(missing_ok=True)
    _atomic_copy(source, target)


def _validate_entry(path: Path, entry: Entry) -> None:
    if not path.is_file():
        raise RuntimeError(f"sync verification failed: missing {entry.relative}")
    actual_size = path.stat().st_size
    if actual_size != entry.size:
        raise RuntimeError(
            f"sync verification failed: size mismatch for {entry.relative} "
            f"({actual_size} != {entry.size})"
        )
    actual_hash = _sha256(path)
    if actual_hash != entry.sha256:
        raise RuntimeError(
            f"sync verification failed: checksum mismatch for {entry.relative}"
        )


def sync_data(
    source_root: Path,
    destination_root: Path,
    *,
    profile: str,
    include_sensitive: bool,
    verify: bool,
) -> tuple[list[Entry], int]:
    source_data = source_root / "data"
    target_data = destination_root / "data"
    source_files = _data_files(
        source_data, profile=profile, include_sensitive=include_sensitive
    )
    entries: list[Entry] = []
    total_bytes = 0
    for index, source in enumerate(source_files, start=1):
        relative = source.relative_to(source_data).as_posix()
        target = target_data / Path(*source.relative_to(source_data).parts)
        print(f"[{index}/{len(source_files)}] {relative}")
        _copy_entry(source, target)
        entry = Entry(relative, target.stat().st_size, _sha256(target))
        if verify:
            _validate_entry(target, entry)
        entries.append(entry)
        total_bytes += entry.size

    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(source_root.resolve()),
        "profile": profile,
        "include_sensitive": include_sensitive,
        "verified": verify,
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "files": [entry.__dict__ for entry in entries],
    }
    target_data.mkdir(parents=True, exist_ok=True)
    (target_data / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8"
    )
    return entries, total_bytes


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Gitignored runtime data between two project clones."
    )
    parser.add_argument("--source", required=True, type=Path, help="source project root")
    parser.add_argument(
        "--destination", required=True, type=Path, help="destination project root"
    )
    parser.add_argument(
        "--profile",
        choices=("portable", "full"),
        default="portable",
        help="portable excludes caches/models/logs; full includes all non-sensitive data",
    )
    parser.add_argument(
        "--include-sensitive",
        action="store_true",
        help="also copy data/cookies; never copies .env or API keys",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="skip SHA-256 verification (faster for very large full syncs)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    source = args.source.expanduser().resolve()
    destination = args.destination.expanduser().resolve()
    if not (source / "data").is_dir():
        print(f"ERROR: source data directory not found: {source / 'data'}", file=sys.stderr)
        return 2
    if source == destination:
        print("ERROR: source and destination must be different", file=sys.stderr)
        return 2

    verify = not args.no_verify
    print(f"Sync profile: {args.profile}")
    print(f"Source:      {source / 'data'}")
    print(f"Destination: {destination / 'data'}")
    print(f"Sensitive:   {'included' if args.include_sensitive else 'excluded'}")
    print(f"Verify:      {'SHA-256' if verify else 'off'}")
    entries, total_bytes = sync_data(
        source,
        destination,
        profile=args.profile,
        include_sensitive=args.include_sensitive,
        verify=verify,
    )
    print(
        f"DONE: {len(entries)} files, {total_bytes / (1024 * 1024):.1f} MiB "
        f"synced to {destination / 'data'}"
    )
    print(f"Manifest: {destination / 'data' / MANIFEST_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
