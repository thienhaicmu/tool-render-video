"""Sprint 7.3 — content-addressable ASS cache helpers.

Pins the _ass_cache_key / _ass_cache_get / _ass_cache_put triplet introduced
in backend/app/orchestration/pipeline_cache.py. All tests redirect APP_DATA_DIR
to tmp_path via monkeypatch so they don't touch the real cache.

Per docs/review/SPRINT_7_3_ASS_CONTENT_CACHE_2026-06-05.md (Commit 1).
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.orchestration import pipeline_cache


_BASE_KWARGS = dict(
    writer="bounce",
    style="viral",
    scale_y=106,
    font_name="Bungee",
    font_size=72,
    margin_v=180,
    play_res_y=720,
    play_res_x=1080,
    x_percent=50.0,
    highlight_per_word=True,
    base_color="",
    highlight_color="",
    outline_size=0,
)


def _write_srt(path: Path, body: str = "1\n00:00:00,000 --> 00:00:01,000\nHello world\n\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


@pytest.fixture
def _cache_dir(tmp_path, monkeypatch) -> Path:
    """Redirect APP_DATA_DIR so pipeline_cache writes to tmp_path/cache/ass."""
    monkeypatch.setattr(pipeline_cache, "APP_DATA_DIR", tmp_path)
    return tmp_path / "cache" / "ass"


# ---------------------------------------------------------------------------
# Section 1: key determinism + sensitivity (the load-bearing contract)
# ---------------------------------------------------------------------------


class TestKeyDeterminism:
    def test_same_inputs_same_key(self, tmp_path):
        srt = _write_srt(tmp_path / "a.srt")
        a = pipeline_cache._ass_cache_key(srt_path=srt, **_BASE_KWARGS)
        b = pipeline_cache._ass_cache_key(srt_path=srt, **_BASE_KWARGS)
        assert a == b
        assert a is not None
        # SHA-256 hex = 64 chars
        assert len(a) == 64

    def test_different_srt_bytes_different_key(self, tmp_path):
        a_srt = _write_srt(tmp_path / "a.srt", body="1\n00:00:00,000 --> 00:00:01,000\nA\n\n")
        b_srt = _write_srt(tmp_path / "b.srt", body="1\n00:00:00,000 --> 00:00:01,000\nB\n\n")
        a = pipeline_cache._ass_cache_key(srt_path=a_srt, **_BASE_KWARGS)
        b = pipeline_cache._ass_cache_key(srt_path=b_srt, **_BASE_KWARGS)
        assert a != b


class TestKeySensitiveToEveryParam:
    """Changing ANY single ASS-determining input must change the hash, so
    cache hits never deliver stale ASS for a config the renderer actually
    differs on."""

    @pytest.mark.parametrize("field,new_value", [
        ("writer", "karaoke"),
        ("style", "clean"),
        ("scale_y", 100),
        ("font_name", "Roboto"),
        ("font_size", 48),
        ("margin_v", 240),
        ("play_res_y", 1080),
        ("play_res_x", 1920),
        ("x_percent", 45.0),
        ("highlight_per_word", False),
        ("base_color", "&HFFFFFF&"),
        ("highlight_color", "&H00FFFF&"),
        ("outline_size", 2),
    ])
    def test_changing_one_param_changes_key(self, tmp_path, field, new_value):
        srt = _write_srt(tmp_path / "a.srt")
        baseline = pipeline_cache._ass_cache_key(srt_path=srt, **_BASE_KWARGS)
        mutated_kwargs = {**_BASE_KWARGS, field: new_value}
        mutated = pipeline_cache._ass_cache_key(srt_path=srt, **mutated_kwargs)
        assert baseline != mutated, (
            f"Mutating {field}={new_value!r} did not change cache key — cache "
            f"would deliver stale ASS for a config the renderer differs on."
        )


# ---------------------------------------------------------------------------
# Section 2: defensive — missing/empty/error
# ---------------------------------------------------------------------------


class TestKeyDefensive:
    def test_missing_srt_returns_none(self, tmp_path):
        missing = tmp_path / "does-not-exist.srt"
        assert pipeline_cache._ass_cache_key(srt_path=missing, **_BASE_KWARGS) is None

    def test_unreadable_srt_returns_none(self, tmp_path, monkeypatch):
        """If read_bytes raises, key returns None — never raises into caller."""
        srt = _write_srt(tmp_path / "a.srt")
        # Patch Path.read_bytes to raise OSError simulating a permissions issue.
        original = Path.read_bytes

        def _explode(self):
            if str(self) == str(srt):
                raise OSError("simulated permission denied")
            return original(self)

        monkeypatch.setattr(Path, "read_bytes", _explode)
        assert pipeline_cache._ass_cache_key(srt_path=srt, **_BASE_KWARGS) is None


# ---------------------------------------------------------------------------
# Section 3: get/put roundtrip
# ---------------------------------------------------------------------------


class TestGetPutRoundtrip:
    def test_get_misses_when_cache_empty(self, _cache_dir):
        assert pipeline_cache._ass_cache_get("a" * 64) is None

    def test_put_then_get_returns_path_with_identical_bytes(self, tmp_path, _cache_dir):
        src = tmp_path / "produced.ass"
        src.write_bytes(b"[Script Info]\nTitle: test\n")
        key = "deadbeef" * 8  # 64 hex chars

        pipeline_cache._ass_cache_put(key, src)
        hit = pipeline_cache._ass_cache_get(key)

        assert hit is not None
        assert hit.exists()
        assert hit.read_bytes() == src.read_bytes()
        assert hit.parent == _cache_dir

    def test_get_returns_none_for_unknown_key(self, tmp_path, _cache_dir):
        src = tmp_path / "produced.ass"
        src.write_bytes(b"present")
        pipeline_cache._ass_cache_put("aaaa" * 16, src)
        # Different key → miss.
        assert pipeline_cache._ass_cache_get("bbbb" * 16) is None

    def test_put_tolerates_missing_src(self, _cache_dir):
        missing = Path("/tmp/definitely-does-not-exist-ass.ass")
        # Should silently no-op, not raise.
        pipeline_cache._ass_cache_put("c" * 64, missing)
        assert pipeline_cache._ass_cache_get("c" * 64) is None

    def test_put_tolerates_empty_src(self, tmp_path, _cache_dir):
        empty = tmp_path / "empty.ass"
        empty.write_bytes(b"")
        pipeline_cache._ass_cache_put("d" * 64, empty)
        # Empty source is treated as "don't cache" — get returns None.
        assert pipeline_cache._ass_cache_get("d" * 64) is None


# ---------------------------------------------------------------------------
# Section 4: TTL eviction (matches existing 72h render-cache contract)
# ---------------------------------------------------------------------------


class TestTtlEviction:
    def test_get_evicts_stale_entry(self, tmp_path, _cache_dir):
        """File mtime > _RENDER_CACHE_TTL_SEC ago → get returns None AND unlinks
        the stale file (lazy eviction matches the sibling caches in
        pipeline_cache.py)."""
        src = tmp_path / "produced.ass"
        src.write_bytes(b"stale")
        key = "e" * 64
        pipeline_cache._ass_cache_put(key, src)
        cached = _cache_dir / f"{key}.ass"
        assert cached.exists()

        # Backdate to 100h ago (well past 72h TTL).
        stale_mtime = time.time() - 100 * 3600
        os.utime(cached, (stale_mtime, stale_mtime))

        result = pipeline_cache._ass_cache_get(key)
        assert result is None
        assert not cached.exists(), "Stale cache file should have been unlinked on lazy eviction."

    def test_get_returns_fresh_entry(self, tmp_path, _cache_dir):
        src = tmp_path / "produced.ass"
        src.write_bytes(b"fresh")
        key = "f" * 64
        pipeline_cache._ass_cache_put(key, src)
        # Within TTL (just-written).
        assert pipeline_cache._ass_cache_get(key) is not None


# ---------------------------------------------------------------------------
# Section 5: maintenance interaction — prune_render_cache picks up cache/ass/
# ---------------------------------------------------------------------------


class TestPruneRenderCacheCoversAssSubdir:
    """prune_render_cache walks every subdir of CACHE_DIR via iterdir() — the
    cache/ass/ subdir we introduce in Sprint 7.3 is picked up automatically
    by the subdir-agnostic test pin at
    test_maintenance_cache_prune.py::test_walks_unknown_subdirs. This case
    documents that the new subdir indeed lives under the right root and the
    prune helper accepts it."""

    def test_old_ass_files_pruned(self, tmp_path):
        from app.services.maintenance import prune_render_cache

        cache_root = tmp_path / "cache"
        old = cache_root / "ass" / "old.ass"
        fresh = cache_root / "ass" / "fresh.ass"
        old.parent.mkdir(parents=True, exist_ok=True)
        old.write_bytes(b"stale")
        fresh.write_bytes(b"fresh")
        os.utime(old, (time.time() - 100 * 3600, time.time() - 100 * 3600))
        os.utime(fresh, (time.time() - 10 * 3600, time.time() - 10 * 3600))

        result = prune_render_cache(cache_root, max_age_hours=72)
        assert result["removed"] == 1
        assert result["kept"] == 1
        assert not old.exists()
        assert fresh.exists()
