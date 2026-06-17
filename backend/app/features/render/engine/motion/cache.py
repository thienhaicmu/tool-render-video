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
from functools import wraps
from pathlib import Path

from app.core.config import APP_DATA_DIR
from app.services.metrics import CACHE_LOOKUPS_TOTAL

# UP28.1 — Motion path cache
_MOTION_CACHE_TTL_SEC = 72 * 3600


def _instrument_cache(cache_label: str):
    """Perf-opt Phase 3 — emit render_cache_lookups_total{cache, outcome}.

    Pure observation; never alters return value or raises. Mirrors the
    decorator already shipped in `pipeline/pipeline_cache.py`.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            result = fn(*args, **kwargs)
            try:
                outcome = "hit" if result is not None else "miss"
                CACHE_LOOKUPS_TOTAL.labels(cache=cache_label, outcome=outcome).inc()
            except Exception:
                pass
            return result
        return wrapped
    return decorator


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

