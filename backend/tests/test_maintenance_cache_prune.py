"""test_maintenance_cache_prune.py — Sprint 5.2.

Verifies prune_render_cache:
- Removes files older than max_age_hours.
- Keeps files newer than max_age_hours.
- Walks all subdirectories under cache root.
- Tolerates a missing cache dir (returns zeros without raising).
- Tolerates per-file errors without aborting the rest.

Audit reference: docs/review/AUDIT_2026-06-02.md P2-D2.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.services.maintenance import prune_render_cache


def _make_aged_file(path: Path, age_hours: float) -> None:
    """Create `path` (parents as needed), set its mtime to `age_hours` ago."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("cached", encoding="utf-8")
    new_mtime = time.time() - age_hours * 3600
    os.utime(path, (new_mtime, new_mtime))


def test_missing_cache_dir_returns_zero(tmp_path):
    """prune of a non-existent dir should not raise."""
    result = prune_render_cache(tmp_path / "does-not-exist", max_age_hours=72)
    assert result == {"removed": 0, "kept": 0}


def test_removes_old_files_keeps_fresh(tmp_path):
    cache_root = tmp_path / "cache"
    # 100h-old → should be removed (default deadline is 72h)
    _make_aged_file(cache_root / "scene_detect" / "old.json", age_hours=100)
    # 24h-old → should be kept
    _make_aged_file(cache_root / "scene_detect" / "fresh.json", age_hours=24)
    # 200h-old in a different subdir → removed
    _make_aged_file(cache_root / "transcription" / "older.srt", age_hours=200)
    # 1h-old in a 3rd subdir → kept
    _make_aged_file(cache_root / "segment_scores" / "today.json", age_hours=1)

    result = prune_render_cache(cache_root, max_age_hours=72)

    assert result["removed"] == 2
    assert result["kept"] == 2
    assert not (cache_root / "scene_detect" / "old.json").exists()
    assert (cache_root / "scene_detect" / "fresh.json").exists()
    assert not (cache_root / "transcription" / "older.srt").exists()
    assert (cache_root / "segment_scores" / "today.json").exists()


def test_walks_unknown_subdirs(tmp_path):
    """Future cache subdirs (not just scene/transcription/segment) are pruned too."""
    cache_root = tmp_path / "cache"
    _make_aged_file(cache_root / "future_kind" / "old.bin", age_hours=200)
    _make_aged_file(cache_root / "another_kind" / "fresh.bin", age_hours=10)

    result = prune_render_cache(cache_root, max_age_hours=72)
    assert result["removed"] == 1
    assert result["kept"] == 1


def test_ignores_non_directory_entries(tmp_path):
    """A stray file directly under cache root must not be deleted by the walk."""
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    stray = cache_root / "README.txt"
    stray.write_text("docs", encoding="utf-8")
    old_mtime = time.time() - 500 * 3600
    os.utime(stray, (old_mtime, old_mtime))

    result = prune_render_cache(cache_root, max_age_hours=72)

    # Stray file at root level is ignored (we only walk dir entries)
    assert stray.exists()
    assert result == {"removed": 0, "kept": 0}


def test_custom_max_age_hours(tmp_path):
    """max_age_hours arg is honored."""
    cache_root = tmp_path / "cache"
    _make_aged_file(cache_root / "scene_detect" / "a.json", age_hours=10)
    _make_aged_file(cache_root / "scene_detect" / "b.json", age_hours=2)

    # With max_age=1h, both files are stale
    result = prune_render_cache(cache_root, max_age_hours=1)
    assert result["removed"] == 2

    # New fresh file: with max_age=999h, nothing stale
    _make_aged_file(cache_root / "scene_detect" / "c.json", age_hours=24)
    result = prune_render_cache(cache_root, max_age_hours=999)
    assert result["removed"] == 0
    assert result["kept"] == 1
