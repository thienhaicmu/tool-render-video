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
    assert result == {"removed": 0, "kept": 0, "freed_bytes": 0}


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
    assert result == {"removed": 0, "kept": 0, "freed_bytes": 0}


# ---------------------------------------------------------------------------
# Sprint 6 P1 — freed_bytes observability + periodic wire (CLAUDE.md Issue 3)
# ---------------------------------------------------------------------------


def test_freed_bytes_matches_removed_file_sizes(tmp_path):
    """freed_bytes should equal the sum of pre-unlink st_size for every
    removed file, so the periodic log line carries an honest disk-savings
    metric. Captured BEFORE unlink because stat() after unlink would fail."""
    cache_root = tmp_path / "cache"
    # Two stale files with deterministic sizes.
    old_a = cache_root / "scene_detect" / "old_a.json"
    old_b = cache_root / "transcription" / "old_b.srt"
    _make_aged_file(old_a, age_hours=100)
    _make_aged_file(old_b, age_hours=100)
    # Overwrite with known byte counts.
    old_a.write_bytes(b"a" * 1000)
    old_b.write_bytes(b"b" * 4000)
    # Restore stale mtime since write_bytes resets it.
    stale_mtime = time.time() - 100 * 3600
    os.utime(old_a, (stale_mtime, stale_mtime))
    os.utime(old_b, (stale_mtime, stale_mtime))
    # One fresh file should not contribute to freed_bytes.
    fresh = cache_root / "segment_scores" / "fresh.json"
    _make_aged_file(fresh, age_hours=1)
    fresh.write_bytes(b"f" * 2000)
    fresh_mtime = time.time() - 1 * 3600
    os.utime(fresh, (fresh_mtime, fresh_mtime))

    result = prune_render_cache(cache_root, max_age_hours=72)

    assert result["removed"] == 2
    assert result["kept"] == 1
    assert result["freed_bytes"] == 5000  # 1000 + 4000, fresh untouched


def test_freed_bytes_zero_when_nothing_stale(tmp_path):
    cache_root = tmp_path / "cache"
    _make_aged_file(cache_root / "scene_detect" / "fresh.json", age_hours=1)

    result = prune_render_cache(cache_root, max_age_hours=72)
    assert result["removed"] == 0
    assert result["freed_bytes"] == 0


def test_periodic_cleanup_source_pins_render_cache_call():
    """Sprint 6 P1 closure of CLAUDE.md Issue 3: prune_render_cache must
    appear inside _run_periodic_cleanup, not just inside startup. Source-
    pin so a future edit that accidentally drops the periodic call surfaces
    here rather than as a silent disk leak on long-running servers."""
    import inspect
    from app import main as main_module
    src = inspect.getsource(main_module._run_periodic_cleanup)
    assert "prune_render_cache(CACHE_DIR" in src, (
        "Sprint 6 P1 contract broken: _run_periodic_cleanup no longer "
        "calls prune_render_cache. CLAUDE.md Issue 3 residual gap has "
        "regressed — long-running servers will stop pruning stale render "
        "caches between restarts."
    )
    assert "cache_freed_mb" in src, (
        "freed_bytes metric was dropped from the periodic cleanup log "
        "line. Operators will lose visibility on cache disk savings."
    )


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
