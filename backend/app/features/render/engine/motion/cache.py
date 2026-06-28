"""Motion-path cache helpers — filesystem-backed lookup keyed by source video.

Sprint 6.D-3.1 — extracted verbatim from motion_crop.py (lines 16–46 of the
pre-extraction file). No logic changes; pure relocation. The cache stores
the result of motion-detection passes so a re-render against the same
source skips the expensive OpenCV+MediaPipe per-frame scan.

Cache layout: APP_DATA_DIR/cache/motion_path/<key>.json
TTL:          72 hours (file-mtime-based eviction on read)
Pruned by:    services/maintenance.py:prune_render_cache (Sprint 5.2)
"""
from __future__ import annotations

import hashlib
import json
import time

from app.core.config import APP_DATA_DIR
# Perf-opt Phase 3 — shared cache-instrumentation decorator (single
# definition lives in app.services.metrics to avoid drift between modules).
from app.services.metrics import instrument_cache as _instrument_cache

# UP28.1 — Motion path cache
_MOTION_CACHE_TTL_SEC = 72 * 3600


def _motion_cache_key(*parts) -> str:
    return hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()


@_instrument_cache("motion_path")
def _motion_path_cache_get(key: str):
    try:
        cache_file = APP_DATA_DIR / "cache" / "motion_path" / f"{key}.json"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _MOTION_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        centers = [tuple(c) for c in data["centers"]]
        return centers, float(data["fps"])
    except Exception:
        return None


def _motion_path_cache_put(key: str, centers: list, fps: float) -> None:
    try:
        cache_dir = APP_DATA_DIR / "cache" / "motion_path"
        cache_dir.mkdir(parents=True, exist_ok=True)
        data = {"centers": [list(c) for c in centers], "fps": fps}
        (cache_dir / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


# ─── B2-OPT-3 (ADR-008, 2026-06-28): coarse motion-path cache ──────────────
#
# The fine cache above is keyed on (source + mtime + size + start + end +
# aspect + scale + reframe + content_type) so any change to clip boundaries
# invalidates it. In practice the LLM selector emits different
# (start, end) values on every re-render → fine cache never hits across
# re-renders. Production-log analysis (10 771 lines) showed zero
# `motion_cache_hit` events.
#
# The coarse layer drops (start, end) so the same source can hit the cache
# regardless of which window the current part needs. Centers are stored
# for the FULL source video; the caller slices to its window after read.
# Coarse hits are only safe when the underlying motion scan covered the
# WHOLE source — i.e. when `render_motion_aware_crop` runs in
# `_fuse_window_mode` (input_path = full source). The producer-side
# helper below stamps a `full_source=True` marker in the JSON so a
# misconfigured non-fuse writer never poisons the coarse cache.

@_instrument_cache("motion_path_coarse")
def _motion_coarse_cache_get(key: str):
    """Read coarse cache entry. Returns (centers, fps) or None. Defensive:
    rejects entries missing the `full_source=True` marker (which would
    indicate a non-fuse writer accidentally wrote per-clip data here)."""
    try:
        cache_file = APP_DATA_DIR / "cache" / "motion_path_coarse" / f"{key}.json"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _MOTION_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if not data.get("full_source"):
            # Safety: someone wrote per-clip data into the coarse store.
            # Treat as corrupt; drop and miss so the caller re-scans.
            cache_file.unlink(missing_ok=True)
            return None
        centers = [tuple(c) for c in data["centers"]]
        return centers, float(data["fps"])
    except Exception:
        return None


def _motion_coarse_cache_put(key: str, centers: list, fps: float) -> None:
    """Write coarse cache entry. Caller MUST ensure `centers` covers the
    FULL source video (only safe in fuse-window mode)."""
    try:
        cache_dir = APP_DATA_DIR / "cache" / "motion_path_coarse"
        cache_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "centers": [list(c) for c in centers],
            "fps": fps,
            "full_source": True,
        }
        (cache_dir / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def slice_motion_centers(
    centers: list,
    fps: float,
    window_start_sec: float,
    window_duration_sec: float,
) -> list:
    """Slice full-source motion centers down to a [start, start+duration]
    window. Returns the sub-list of (x, y) tuples for that window.

    The caller in fuse-window mode encodes frames from
    `start_frame_offset` to `start_frame_offset + window_frame_count`
    of the OpenCV capture; this slice mirrors that addressing so the
    crop-box positions stay aligned with the emitted video frames.

    Defensive: clamps both bounds, returns at least an empty list on
    any inconsistency. Caller falls back to fresh scan when result is
    smaller than expected.
    """
    try:
        if not centers or fps <= 0:
            return []
        start_idx = max(0, int(round(window_start_sec * fps)))
        end_idx = min(len(centers), start_idx + int(round(window_duration_sec * fps)) + 1)
        if end_idx <= start_idx:
            return []
        return list(centers[start_idx:end_idx])
    except Exception:
        return []

