"""pipeline_cache.py — Render cache helpers (scene, transcription, segment scores).

Extracted from render_pipeline.py (lines 175–264) as part of C-1 decomposition.
All logic is identical — this is a mechanical lift, not a rewrite.
"""

import hashlib
import json
import shutil
import time
from pathlib import Path

from app.core.config import APP_DATA_DIR

_RENDER_CACHE_TTL_SEC = 72 * 3600  # 72 h


def _render_cache_key(*parts) -> str:
    return hashlib.md5("|".join(str(p) for p in parts).encode()).hexdigest()


def _scene_cache_get(source_path: str) -> list | None:
    try:
        sp = Path(source_path)
        if not sp.exists():
            return None
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size)
        cache_file = APP_DATA_DIR / "cache" / "scene_detect" / f"{key}.json"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _scene_cache_put(source_path: str, scenes: list) -> None:
    try:
        sp = Path(source_path)
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size)
        cache_dir = APP_DATA_DIR / "cache" / "scene_detect"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{key}.json").write_text(json.dumps(scenes), encoding="utf-8")
    except Exception:
        pass


def _transcription_cache_get(source_path: str, model_name: str, cache_suffix: str) -> Path | None:
    try:
        sp = Path(source_path)
        if not sp.exists():
            return None
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size, model_name, cache_suffix)
        cache_file = APP_DATA_DIR / "cache" / "transcription" / f"{key}.srt"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return cache_file
    except Exception:
        return None


def _transcription_cache_put(source_path: str, model_name: str, cache_suffix: str, srt_path: Path) -> None:
    try:
        if not srt_path.exists() or srt_path.stat().st_size == 0:
            return
        sp = Path(source_path)
        st = sp.stat()
        key = _render_cache_key(source_path, st.st_mtime, st.st_size, model_name, cache_suffix)
        cache_dir = APP_DATA_DIR / "cache" / "transcription"
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(srt_path), str(cache_dir / f"{key}.srt"))
    except Exception:
        pass


def _score_cache_get(key: str) -> list | None:
    try:
        cache_file = APP_DATA_DIR / "cache" / "segment_scores" / f"{key}.json"
        if not cache_file.exists():
            return None
        if time.time() - cache_file.stat().st_mtime > _RENDER_CACHE_TTL_SEC:
            cache_file.unlink(missing_ok=True)
            return None
        return json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def _score_cache_put(key: str, scored: list) -> None:
    try:
        cache_dir = APP_DATA_DIR / "cache" / "segment_scores"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{key}.json").write_text(json.dumps(scored), encoding="utf-8")
    except Exception:
        pass
