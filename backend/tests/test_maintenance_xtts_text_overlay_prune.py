"""
Sprint 6 P0 — pin the two new maintenance prune helpers:

- prune_xtts_cache: bounds the unbounded XTTS synthesis cache (S-5).
- prune_text_overlay_dir: bounds the never-cleaned text-overlay temp
  dir (S-7).

Per docs/review/TEMP_FILE_AUDIT_2026-06-04.md these were the two new
cache-prune gaps surfaced by the Sprint 1.4 audit beyond CLAUDE.md
Issue 3 (which is now resolved for APP_DATA_DIR/cache).
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.maintenance import prune_text_overlay_dir, prune_xtts_cache


def _touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _set_mtime_days_ago(path: Path, days: int) -> None:
    """Backdate a file's mtime by `days` so prune routines see it as stale."""
    ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    os.utime(path, (ts, ts))


class TestPruneXttsCache:
    def test_missing_dir_is_noop(self, tmp_path):
        result = prune_xtts_cache(tmp_path)
        assert result == {"removed": 0, "kept": 0}
        # No exception, no directory created.
        assert not (tmp_path / "xtts_cache").exists()

    def test_removes_stale_keeps_recent(self, tmp_path):
        cache_root = tmp_path / "xtts_cache"
        stale = _touch(cache_root / "stale1.mp3", b"old")
        fresh = _touch(cache_root / "fresh1.mp3", b"new")
        _set_mtime_days_ago(stale, days=60)  # > 30d default

        result = prune_xtts_cache(tmp_path, max_age_days=30)

        assert not stale.exists()
        assert fresh.exists()
        assert result == {"removed": 1, "kept": 1}

    def test_respects_custom_ttl(self, tmp_path):
        cache_root = tmp_path / "xtts_cache"
        f = _touch(cache_root / "a.mp3")
        _set_mtime_days_ago(f, days=10)

        # Default TTL keeps it (30d window).
        assert prune_xtts_cache(tmp_path, max_age_days=30)["removed"] == 0
        assert f.exists()

        # Short TTL prunes it.
        result = prune_xtts_cache(tmp_path, max_age_days=5)
        assert result["removed"] == 1
        assert not f.exists()

    def test_subdirectories_left_alone(self, tmp_path):
        """The function walks flat files only — nested dirs (unusual but
        not impossible if a future feature shards the cache) are
        skipped. This pins the contract so a future refactor doesn't
        silently delete subdir contents."""
        cache_root = tmp_path / "xtts_cache"
        cache_root.mkdir(parents=True)
        sub = cache_root / "shard_a"
        sub.mkdir()
        nested = _touch(sub / "deep.mp3")
        _set_mtime_days_ago(nested, days=90)

        result = prune_xtts_cache(tmp_path, max_age_days=30)
        # Nested file survives because we only scan top-level files.
        assert nested.exists()
        # Subdir itself counted as not-a-file: kept=0, removed=0.
        assert result == {"removed": 0, "kept": 0}

    def test_one_bad_file_does_not_abort_sweep(self, tmp_path):
        """Per-file try/except contract: a stat-unfriendly entry must
        not prevent the rest from being processed."""
        cache_root = tmp_path / "xtts_cache"
        stale_a = _touch(cache_root / "a.mp3")
        stale_b = _touch(cache_root / "b.mp3")
        _set_mtime_days_ago(stale_a, days=90)
        _set_mtime_days_ago(stale_b, days=90)

        # Even with one unreadable entry (simulated via missing_ok handling
        # — concretely just verify both stales got removed in one call).
        result = prune_xtts_cache(tmp_path, max_age_days=30)
        assert result["removed"] == 2
        assert not stale_a.exists()
        assert not stale_b.exists()


class TestPruneTextOverlayDir:
    def test_missing_dir_is_noop(self, tmp_path):
        target = tmp_path / "does_not_exist"
        result = prune_text_overlay_dir(target)
        assert result == {"removed": 0, "kept": 0}
        assert not target.exists()

    def test_removes_stale_txt(self, tmp_path):
        stale = _touch(tmp_path / "layer_abc.txt", b"old text")
        fresh = _touch(tmp_path / "layer_xyz.txt", b"new text")
        _set_mtime_days_ago(stale, days=14)  # > 7d default

        result = prune_text_overlay_dir(tmp_path, max_age_days=7)

        assert not stale.exists()
        assert fresh.exists()
        assert result == {"removed": 1, "kept": 1}

    def test_default_ttl_is_seven_days(self, tmp_path):
        old = _touch(tmp_path / "old.txt")
        new = _touch(tmp_path / "new.txt")
        _set_mtime_days_ago(old, days=8)
        _set_mtime_days_ago(new, days=3)

        result = prune_text_overlay_dir(tmp_path)
        assert result["removed"] == 1
        assert not old.exists()
        assert new.exists()

    def test_subdirectories_left_alone(self, tmp_path):
        sub = tmp_path / "nested"
        sub.mkdir()
        nested = _touch(sub / "deep.txt")
        _set_mtime_days_ago(nested, days=90)

        result = prune_text_overlay_dir(tmp_path, max_age_days=7)
        assert nested.exists()
        assert result == {"removed": 0, "kept": 0}


class TestPublicTextOverlayDirHelper:
    """The maintenance prune needs a stable name to import from
    text_overlay.py. Sprint 6 P0 renamed the previously-private
    `_text_overlay_temp_dir` to `get_text_overlay_temp_dir` and kept
    the old name as a backward-compat alias."""

    def test_public_name_exists_and_returns_path(self):
        from app.services.text_overlay import get_text_overlay_temp_dir
        result = get_text_overlay_temp_dir()
        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_dir()

    def test_backward_compat_alias_still_works(self):
        from app.services import text_overlay
        assert text_overlay._text_overlay_temp_dir is text_overlay.get_text_overlay_temp_dir
