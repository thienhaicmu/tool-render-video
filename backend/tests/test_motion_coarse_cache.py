"""Unit tests for the B2-OPT-3 (ADR-008) coarse motion-path cache.

Verifies that:
  - put + get round-trips when the producer marks data full_source=True
  - get rejects entries missing the full_source marker (defence against
    accidental non-fuse writers poisoning the coarse store)
  - get returns None on missing / corrupt files
  - slice_motion_centers maps (window_start, window_dur) → correct sub-list
  - slice clamps over-/under-flow safely
"""
import json
from pathlib import Path

import pytest

from app.features.render.engine.motion.cache import (
    _motion_coarse_cache_get,
    _motion_coarse_cache_put,
    _motion_cache_key,
    slice_motion_centers,
)


def test_coarse_cache_round_trip(monkeypatch, tmp_path):
    # Redirect APP_DATA_DIR so we don't pollute the real cache.
    from app.features.render.engine.motion import cache as cache_mod
    monkeypatch.setattr(cache_mod, "APP_DATA_DIR", tmp_path)

    key = _motion_cache_key("coarse_v1", "/tmp/foo.mp4", 12345, 100, "9:16", 100, 100, "subject", "vlog")
    centers = [(100, 200), (110, 210), (120, 220)]
    fps = 30.0
    _motion_coarse_cache_put(key, centers, fps)

    out = _motion_coarse_cache_get(key)
    assert out is not None
    centers_back, fps_back = out
    assert centers_back == centers
    assert fps_back == fps


def test_coarse_cache_get_rejects_non_full_source(monkeypatch, tmp_path):
    from app.features.render.engine.motion import cache as cache_mod
    monkeypatch.setattr(cache_mod, "APP_DATA_DIR", tmp_path)

    cache_dir = tmp_path / "cache" / "motion_path_coarse"
    cache_dir.mkdir(parents=True)
    bad_key = "deadbeef"
    # Simulate a misconfigured writer that DID NOT set full_source=True.
    (cache_dir / f"{bad_key}.json").write_text(
        json.dumps({"centers": [[1, 2]], "fps": 30.0}),  # missing "full_source"
        encoding="utf-8",
    )
    out = _motion_coarse_cache_get(bad_key)
    assert out is None
    # And the corrupt entry was unlinked so it can't poison future reads.
    assert not (cache_dir / f"{bad_key}.json").exists()


def test_coarse_cache_get_returns_none_when_missing(tmp_path, monkeypatch):
    from app.features.render.engine.motion import cache as cache_mod
    monkeypatch.setattr(cache_mod, "APP_DATA_DIR", tmp_path)
    assert _motion_coarse_cache_get("never_written_key") is None


def test_slice_motion_centers_basic():
    # 30 fps, 5 seconds = 150 centers (one per frame).
    centers = [(i, i * 2) for i in range(150)]
    sliced = slice_motion_centers(centers, fps=30.0, window_start_sec=1.0, window_duration_sec=2.0)
    # frames 30..91 inclusive (start at 30, length ~60+1 due to +1 in slicer).
    assert len(sliced) == 61
    assert sliced[0] == (30, 60)
    assert sliced[-1] == (90, 180)


def test_slice_motion_centers_clamps_overflow():
    centers = [(i, i) for i in range(30)]
    # Asking for a 5-second window starting at 0.5s but only 1s of data.
    sliced = slice_motion_centers(centers, fps=30.0, window_start_sec=0.5, window_duration_sec=5.0)
    # Clamps to len(centers) — we get the tail starting at frame 15.
    assert len(sliced) <= len(centers)
    assert sliced[0] == (15, 15)


def test_slice_motion_centers_empty_on_bad_input():
    assert slice_motion_centers([], 30.0, 0.0, 1.0) == []
    assert slice_motion_centers([(1, 1)], 0.0, 0.0, 1.0) == []
    assert slice_motion_centers([(1, 1)], 30.0, 5.0, 1.0) == []
