"""
manifest_writer.py — Atomic read/write helpers for BaseClipManifest JSON files.

Each rendered clip gets a manifest.json written beside its other artifacts:
  work_dir/part_{n}/manifest.json

Writes are atomic: content is written to a .tmp sibling then renamed via
os.replace() so readers never see a partial file.

Manifest failures MUST NOT crash render jobs.  All public functions log a
warning on error and return None / empty list rather than raising.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

from app.domain.manifests import BaseClipManifest

logger = logging.getLogger("app.services.manifest_writer")


def manifest_path(work_dir: Path, part_no: int) -> Path:
    """Return the canonical path for a part's manifest file."""
    return work_dir / f"part_{part_no}" / "manifest.json"


def write_manifest(work_dir: Path, manifest: BaseClipManifest) -> Optional[Path]:
    """Atomically write *manifest* to disk.

    Returns the path written on success, None on failure.
    Never raises — render jobs must not be interrupted by manifest I/O errors.
    """
    target = manifest_path(work_dir, manifest.part_no)
    tmp = target.with_suffix(".json.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(str(tmp), str(target))
        return target
    except Exception as exc:
        logger.warning(
            "manifest_write_failed job_id=%s part_no=%d path=%s: %s",
            manifest.job_id,
            manifest.part_no,
            target,
            exc,
        )
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def read_manifest(work_dir: Path, part_no: int) -> Optional[BaseClipManifest]:
    """Read and deserialize the manifest for *part_no*.

    Returns None if the file is missing or corrupt.
    Never raises.
    """
    path = manifest_path(work_dir, part_no)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return BaseClipManifest.from_dict(data)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning(
            "manifest_read_failed part_no=%d path=%s: %s",
            part_no,
            path,
            exc,
        )
        return None


def read_all_manifests(work_dir: Path) -> list[BaseClipManifest]:
    """Read all part_*/manifest.json files under *work_dir*.

    Skips missing or corrupt files silently (logs a warning per failure).
    Returns manifests sorted by part_no ascending.
    """
    results: list[BaseClipManifest] = []
    try:
        part_dirs = sorted(work_dir.glob("part_*"), key=lambda p: _part_no_from_dir(p))
    except Exception as exc:
        logger.warning("manifest_glob_failed work_dir=%s: %s", work_dir, exc)
        return results

    for part_dir in part_dirs:
        part_no = _part_no_from_dir(part_dir)
        if part_no < 0:
            continue
        m = read_manifest(work_dir, part_no)
        if m is not None:
            results.append(m)

    return results


def _part_no_from_dir(part_dir: Path) -> int:
    """Extract the integer part number from a 'part_N' directory name.

    Returns -1 if the name does not match the expected pattern.
    """
    name = part_dir.name
    if not name.startswith("part_"):
        return -1
    try:
        return int(name[5:])
    except ValueError:
        return -1
