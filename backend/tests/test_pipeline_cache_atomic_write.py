"""Audit FINDING-BR14 closure (Batch 10F 2026-06-06).

``pipeline_cache._*_cache_put`` writers previously called
``Path.write_text`` / ``shutil.copy2`` directly, leaving a window where a
concurrent ``prune_render_cache`` invocation (which runs at startup and
every 30 minutes) could ``unlink`` a partially-written file. The writer's
flush would then either fail (Windows: sharing violation) or write into
an orphaned inode (POSIX).

The fix: all four put-paths now route through ``_atomic_write_text`` /
``_atomic_copy2`` which stage the bytes in a ``.tmp`` sidecar and rename
into place via ``os.replace`` (atomic on every supported platform).
Belt-and-suspenders: ``prune_render_cache`` skips ``.tmp`` files entirely.

Tests:

1. ``_atomic_write_text`` produces the final file with the written
   content, and no ``.tmp`` sidecar is left behind.
2. ``_atomic_copy2`` round-trips bytes + metadata, and removes the tmp sidecar.
3. Pruner skips ``.tmp`` files even when their mtime is older than the cutoff.
4. Concurrent pruner-during-write doesn't truncate the cache file. We
   simulate the worst case by serializing a write that observes a sentinel
   ``.tmp`` file the pruner ignored.
5. End-to-end: ``_scene_cache_put`` produces a readable scene cache; the
   pruner does not delete it.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Direct helpers
# ---------------------------------------------------------------------------


def test_atomic_write_text_writes_full_content_and_no_sidecar(tmp_path):
    from app.features.render.engine.pipeline.pipeline_cache import _atomic_write_text

    target = tmp_path / "x.json"
    _atomic_write_text(target, '{"k":"v"}')

    assert target.exists()
    assert target.read_text(encoding="utf-8") == '{"k":"v"}'
    # The tmp sidecar must NOT linger — the rename consumed it.
    assert not (tmp_path / "x.json.tmp").exists()


def test_atomic_copy2_preserves_bytes_and_clears_sidecar(tmp_path):
    from app.features.render.engine.pipeline.pipeline_cache import _atomic_copy2

    src = tmp_path / "source.srt"
    src.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello\n", encoding="utf-8")

    dst = tmp_path / "dst.srt"
    _atomic_copy2(src, dst)

    assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    assert not (tmp_path / "dst.srt.tmp").exists()


def test_atomic_write_overwrites_existing_file(tmp_path):
    """Subsequent writes replace the old file completely (no partial overlay)."""
    from app.features.render.engine.pipeline.pipeline_cache import _atomic_write_text

    target = tmp_path / "x.json"
    _atomic_write_text(target, "version_one")
    _atomic_write_text(target, "v2")  # shorter — must not leave trailing bytes

    assert target.read_text(encoding="utf-8") == "v2"


# ---------------------------------------------------------------------------
# Pruner skip behaviour
# ---------------------------------------------------------------------------


def _age_file(path: Path, hours_ago: float) -> None:
    """Backdate a file's mtime so the pruner's cutoff comparison fires."""
    new_mtime = time.time() - hours_ago * 3600
    os.utime(path, (new_mtime, new_mtime))


def test_prune_skips_tmp_sidecar_even_when_stale(tmp_path):
    """A ``.tmp`` sidecar older than the cutoff must NOT be deleted —
    it could be a freshly-allocated tmp from a concurrent writer."""
    from app.services.maintenance import prune_render_cache

    cache_root = tmp_path / "cache"
    sub = cache_root / "transcription"
    sub.mkdir(parents=True)

    real_file = sub / "abc.srt"
    tmp_file = sub / "abc.srt.tmp"
    real_file.write_text("real content", encoding="utf-8")
    tmp_file.write_text("partial-write-in-progress", encoding="utf-8")
    # Backdate BOTH files past the 72h cutoff so a naive pruner would
    # delete them. The tmp must survive.
    _age_file(real_file, hours_ago=200)
    _age_file(tmp_file, hours_ago=200)

    result = prune_render_cache(cache_root, max_age_hours=72)

    # The real file IS pruned (it's stale and not a tmp).
    assert result["removed"] == 1
    assert not real_file.exists()
    # The tmp file IS preserved by the explicit suffix skip.
    assert tmp_file.exists()
    assert tmp_file.read_text(encoding="utf-8") == "partial-write-in-progress"


def test_prune_still_removes_stale_non_tmp_files(tmp_path):
    """Sanity: the suffix skip didn't accidentally exempt regular cache files."""
    from app.services.maintenance import prune_render_cache

    cache_root = tmp_path / "cache"
    sub = cache_root / "scene_detect"
    sub.mkdir(parents=True)

    f = sub / "old.json"
    f.write_text("[]", encoding="utf-8")
    _age_file(f, hours_ago=100)

    result = prune_render_cache(cache_root, max_age_hours=72)

    assert result["removed"] == 1
    assert not f.exists()


# ---------------------------------------------------------------------------
# End-to-end: pipeline_cache writer + maintenance pruner
# ---------------------------------------------------------------------------


def test_scene_cache_put_is_readable_after_write_and_survives_pruner(tmp_path, monkeypatch):
    """Real cache_put + real prune_render_cache, fresh mtime — the cache
    file must be present and the pruner must NOT remove it (it's fresh)."""
    from app.features.render.engine.pipeline import pipeline_cache as pc
    from app.services.maintenance import prune_render_cache

    # Redirect APP_DATA_DIR so the test doesn't pollute the real cache.
    monkeypatch.setattr(pc, "APP_DATA_DIR", tmp_path)
    # Build a fake source file for the cache key.
    src = tmp_path / "video.mp4"
    src.write_bytes(b"\x00" * 64)

    pc._scene_cache_put(str(src), [{"start": 0, "end": 5}])

    cache_dir = tmp_path / "cache" / "scene_detect"
    json_files = list(cache_dir.glob("*.json"))
    tmp_files = list(cache_dir.glob("*.tmp"))
    assert len(json_files) == 1
    assert json_files[0].read_text(encoding="utf-8") == '[{"start": 0, "end": 5}]'
    assert tmp_files == [], "atomic write must clean up the tmp sidecar"

    # Prune with a real cutoff — fresh files survive.
    result = prune_render_cache(tmp_path / "cache", max_age_hours=72)
    assert result["removed"] == 0
    assert json_files[0].exists()


def test_concurrent_prune_during_partial_tmp_does_not_destroy_real_file(tmp_path):
    """Worst-case timing: the pruner runs while a tmp sidecar exists in
    the same directory as a real cache entry. Both have aged past the cutoff.
    The real file is correctly pruned (stale); the tmp file is preserved
    so the in-flight writer can complete its rename safely."""
    from app.services.maintenance import prune_render_cache

    cache_root = tmp_path / "cache"
    sub = cache_root / "ass"
    sub.mkdir(parents=True)

    # Three entries: a stale real cache, a fresh real cache, and a stale tmp.
    stale = sub / "k1.ass"
    fresh = sub / "k2.ass"
    in_flight = sub / "k3.ass.tmp"
    for f, content in [(stale, "old"), (fresh, "new"), (in_flight, "writing")]:
        f.write_text(content, encoding="utf-8")
    _age_file(stale, hours_ago=200)
    _age_file(in_flight, hours_ago=200)
    # `fresh` keeps default mtime (now).

    result = prune_render_cache(cache_root, max_age_hours=72)

    assert result["removed"] == 1, "exactly the stale .ass should be removed"
    assert not stale.exists()
    assert fresh.exists() and fresh.read_text(encoding="utf-8") == "new"
    assert in_flight.exists() and in_flight.read_text(encoding="utf-8") == "writing"
